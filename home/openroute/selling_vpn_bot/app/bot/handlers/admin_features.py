import io
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from app.bot.filters.admin import AdminFilter
from app.db.database import async_session_maker
from app.db.models import User, SshAccount, SshServer, DiscountCode
from app.services.ssh.linux import LinuxSSHManager
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY
from app.services.pricing import discount_scope_label, normalize_discount_code, normalize_discount_payment_method

import matplotlib
matplotlib.use('Agg') # Necessary for environments without a display/GUI
import matplotlib.pyplot as plt

from app.worker.reporters import broadcast_admin_report
from app.core.config import settings
from app.core.topics_manager import (
    clear_topics,
    get_manager_group_id,
    load_topics,
    set_manager_group_id,
    set_topic_id,
)

router = Router(name="admin_features_router")
router.message.filter(AdminFilter())


class DiscountCodeFSM(StatesGroup):
    waiting_for_create_payload = State()

TOPIC_DEFINITIONS = (
    ("tickets", "🎫 تیکت‌ها"),
    ("registrations", "👥 ثبت‌نام کاربران"),
    ("stats", "📊 آمار و وضعیت"),
    ("payments", "💰 تراکنش‌های مالی"),
)


async def _get_pasarguard_users() -> list[dict]:
    async with httpx.AsyncClient(
        base_url=settings.PASARGUARD_API_BASE,
        verify=False,
        timeout=30.0,
    ) as client:
        token_response = await client.post(
            "/api/admin/token",
            data={
                "username": settings.PASARGUARD_ADMIN_USERNAME,
                "password": settings.PASARGUARD_ADMIN_PASSWORD,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]

        users_response = await client.get(
            "/api/users",
            params={"offset": 0, "limit": 1000},
            headers={"Authorization": f"Bearer {token}"},
        )
        users_response.raise_for_status()
        return users_response.json().get("users", [])


def _parse_pasarguard_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def ensure_forum_topics(bot, group_id: int) -> tuple[list[str], list[str]]:
    existing_topics = load_topics()
    reused_keys: list[str] = []
    created_keys: list[str] = []

    for topic_key, topic_name in TOPIC_DEFINITIONS:
        if existing_topics.get(topic_key):
            reused_keys.append(topic_key)
            continue

        created = await bot.create_forum_topic(chat_id=group_id, name=topic_name)
        set_topic_id(topic_key, created.message_thread_id)
        created_keys.append(topic_key)

    return reused_keys, created_keys


async def reset_forum_topics(bot, group_id: int, max_thread_id: int = 300) -> dict[str, int]:
    # Remove all non-General forum topics in a bounded range, then recreate the canonical set.
    for thread_id in range(2, max_thread_id + 1):
        try:
            await bot.close_forum_topic(chat_id=group_id, message_thread_id=thread_id)
        except Exception:
            pass

        try:
            await bot.delete_forum_topic(chat_id=group_id, message_thread_id=thread_id)
        except Exception:
            pass

    clear_topics()
    created_topics: dict[str, int] = {}
    for topic_key, topic_name in TOPIC_DEFINITIONS:
        created = await bot.create_forum_topic(chat_id=group_id, name=topic_name)
        set_topic_id(topic_key, created.message_thread_id)
        created_topics[topic_key] = created.message_thread_id

    return created_topics

@router.message(F.text == "آمار کلی")
async def generate_stats_chart(message: Message):
    status_msg = await message.answer("در حال محاسبه آمار و رسم نمودار...")
    
    async with async_session_maker() as session:
        total_users = await session.scalar(select(func.count(User.id))) or 0
        active_accounts = await session.scalar(
            select(func.count(SshAccount.id)).where(SshAccount.status == "active")
        ) or 0
        total_bw = await session.scalar(select(func.sum(SshAccount.traffic_used_gb))) or 0.0
        
    # Generate Chart
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(8, 5))
    
    categories = ['Users', 'Active VPNs', 'Traffic (GB)']
    values = [total_users, active_accounts, float(total_bw)]
    
    bars = ax.bar(categories, values, color=['#4F46E5', '#10B981', '#F59E0B'])
    ax.set_title('General Statistics', fontsize=16, pad=20)
    
    # Add values on top of bars
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom')
                    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    buf.seek(0)
    plt.close(fig)
    
    photo = BufferedInputFile(buf.read(), filename="stats.png")
    caption = f"📊 **آمار کلی سیستم**\n\n👥 کل کاربران تلگرامی: {total_users}\n🟢 اکانت‌های فعال SSH: {active_accounts}\n🌐 مجموع ترافیک مصرفی: {total_bw:.2f} GB"
    
    await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
    await status_msg.delete()

@router.message(F.text == "اتصال‌ها")
async def show_connections(message: Message):
    status_msg = await message.answer("⏳ در حال بررسی سرورها برای اتصال‌های فعال... (این عملیات ممکن است کمی طول بکشد)")

    async with async_session_maker() as session:
        ssh_servers = (
            await session.scalars(
                select(SshServer)
                .join(SshAccount, SshAccount.server_id == SshServer.id)
                .where(SshAccount.service_type == ACCOUNT_TYPE_SSH)
                .distinct()
            )
        ).all()

    report = "🌐 **وضعیت اتصال‌های زنده (Real-Time)**\n\n"
    total_connections = 0

    for server in ssh_servers:
        try:
            ssh = LinuxSSHManager(
                ssh_port=server.ssh_port,
                root_password=server.root_password,
            )
            cmd = "ps -ef | grep -E 'sshd: .*@notty|dropbear.*[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | grep -v grep | wc -l"
            out = await ssh._run_command(server.ip_address, cmd)
            count = int(out.strip()) if out and out.strip().isdigit() else 0

            report += f"🖥 **{server.name}**: {count} اتصال SSH فعال\n"
            total_connections += count
        except Exception:
            report += f"🖥 **{server.name}**: خطا در دریافت اتصال‌های SSH\n"

    try:
        pasarguard_users = await _get_pasarguard_users()
        online_cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
        online_v2ray = sum(
            1
            for user in pasarguard_users
            if user.get("status") == "active"
            and (
                (online_at := _parse_pasarguard_datetime(user.get("online_at")))
                is not None
            )
            and online_at >= online_cutoff
        )
        report += f"🖥 **PasarGuard V2Ray**: {online_v2ray} کاربر آنلاین در ۳ دقیقه اخیر\n"
        total_connections += online_v2ray
    except Exception:
        report += "🖥 **PasarGuard V2Ray**: خطا در دریافت وضعیت آنلاین\n"

    report += f"\nمجموع کاربران متصل در این لحظه: {total_connections}"
    await status_msg.edit_text(report, parse_mode="Markdown")

@router.message(F.text == "ثبت ترافیک")
async def sync_traffic(message: Message):
    status_msg = await message.answer("⏳ در حال همگام‌سازی و محاسبه ترافیک زنده تمامی کاربران از روی سرورها...")

    async with async_session_maker() as session:
        accounts = (
            await session.scalars(
                select(SshAccount).where(SshAccount.status == "active")
            )
        ).all()

        updated_v2ray = 0
        updated_ssh = 0
        failures = 0

        try:
            pasarguard_users = {
                user["username"]: user
                for user in await _get_pasarguard_users()
                if user.get("username")
            }
        except Exception:
            pasarguard_users = {}
            failures += 1

        servers = {
            server.id: server
            for server in (
                await session.scalars(select(SshServer))
            ).all()
        }

        for account in accounts:
            try:
                if account.service_type == ACCOUNT_TYPE_V2RAY:
                    remote_user = pasarguard_users.get(account.ssh_username)
                    if not remote_user:
                        continue
                    account.traffic_used_gb = round(
                        int(remote_user.get("used_traffic") or 0) / (1024 ** 3),
                        6,
                    )
                    updated_v2ray += 1
                    continue

                server = servers.get(account.server_id)
                if not server:
                    failures += 1
                    continue
                ssh = LinuxSSHManager(
                    ssh_port=server.ssh_port,
                    root_password=server.root_password,
                )
                traffic_bytes = await ssh.get_user_traffic(
                    server.ip_address,
                    account.ssh_username,
                )
                account.traffic_used_gb = round(traffic_bytes / (1024 ** 3), 6)
                updated_ssh += 1
            except Exception:
                failures += 1

        await session.commit()
        total_bw = await session.scalar(select(func.sum(SshAccount.traffic_used_gb))) or 0.0

    report = (
        "📈 **گزارش لحظه‌ای ترافیک**\n\n"
        "✅ ترافیک مصرفی سرورها با موفقیت دریافت و در پایگاه داده ثبت شد!\n"
        f"🔐 اکانت‌های SSH بروزشده: {updated_ssh}\n"
        f"🌐 اکانت‌های V2Ray بروزشده: {updated_v2ray}\n"
        f"⚠️ خطاها: {failures}\n"
        f"📊 حجم کل مصرفی تمامی کاربران: {float(total_bw):.6f} GB\n\n"
        "جهت مشاهده مصرف دقیق هر اکانت به تفکیک و نمودار مصرف، از منوی پایین وارد **پنل وب** شوید."
    )
    await status_msg.edit_text(report, parse_mode="Markdown")

@router.message(Command("report"))
async def trigger_manual_report(message: Message):
    if message.chat.type in {"group", "supergroup"}:
        set_manager_group_id(message.chat.id)
    status_msg = await message.answer("⏳ در حال تولید گزارش دوره‌ای و ارسال به گروه مدیران...")
    await broadcast_admin_report(message.bot)
    await status_msg.edit_text("✅ گزارش با موفقیت تولید و به تاپیک **آمار و وضعیت** ارسال شد!", parse_mode="Markdown")

@router.message(Command("setup_topics"))
async def setup_forum_topics(message: Message):
    if message.chat.type in {"group", "supergroup"}:
        group_id = message.chat.id
        set_manager_group_id(group_id)
    else:
        group_id = get_manager_group_id()

    if not group_id:
        await message.answer("⚠️ خطا: شناسه گروه مدیران (MANAGER_GROUP_ID) تنظیم نشده است.")
        return
        
    status_msg = await message.answer("⏳ در حال بررسی و اتصال تاپیک‌های اختصاصی گروه مدیران...")
    
    try:
        reused_keys, created_keys = await ensure_forum_topics(message.bot, group_id)
        if created_keys:
            await status_msg.edit_text("✅ تاپیک‌ها با موفقیت متصل شدند و سیستم اطلاع‌رسانی به همان بخش‌ها وصل شد!")
            return

        await status_msg.edit_text("✅ تاپیک‌ها از قبل تنظیم شده بودند. هیچ بخش تکراری جدیدی ساخته نشد.")
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در ساخت تاپیک‌ها:\n\n{str(e)}\n\nتوجه: مطمئن شوید قابلیت Topics در گروه فعال است و ربات دسترسی مدیریت Topics را دارد.")


@router.message(Command("reset_topics"))
async def reset_topics(message: Message):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("این دستور فقط داخل گروه مدیران قابل استفاده است.")
        return

    group_id = message.chat.id
    set_manager_group_id(group_id)
    status_msg = await message.answer("⏳ در حال حذف بخش‌های تکراری و بازسازی تاپیک‌های اصلی گروه...")

    try:
        created_topics = await reset_forum_topics(message.bot, group_id)
        await status_msg.edit_text(
            "✅ بخش‌های تکراری حذف شدند و فقط تاپیک‌های اصلی بازسازی شدند.\n\n"
            f"tickets={created_topics['tickets']}\n"
            f"registrations={created_topics['registrations']}\n"
            f"stats={created_topics['stats']}\n"
            f"payments={created_topics['payments']}"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ خطا در پاکسازی تاپیک‌ها:\n\n{str(e)}\n\n"
            "مطمئن شوید ربات دسترسی مدیریت Topics را در گروه دارد."
        )

@router.message(Command("groupid"))
async def show_group_id(message: Message):
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("این دستور فقط داخل گروه قابل استفاده است.")
        return

    current_manager_group_id = get_manager_group_id()
    await message.answer(
        "🧭 شناسه این گروه:\n"
        f"<code>{message.chat.id}</code>\n\n"
        "گروه مدیران فعلی:\n"
        f"<code>{current_manager_group_id or 'not set'}</code>"
    )


@router.message(F.text == "راهنما")
async def help_command(message: Message):
    text = (
        "📚 **راهنمای مدیریت پنل:**\n\n"
        "- **آمار کلی**: رسم نمودار لحظه‌ای از وضعیت سیستم.\n"
        "- **اتصال‌ها**: رصد تعداد اتصالات زنده (کاربران آنلاین).\n"
        "- **ثبت ترافیک**: همگام‌سازی مصرف کاربران با دیتابیس.\n"
        "- **پنل وب**: پورتال گرافیکی مدیریت کامل اکانت‌ها و تیکت‌ها.\n"
        "- **افزودن/سرورهای VPS**: مدیریت سرورهای توزیع ترافیک.\n"
        "- **خروج از ربات**: قطع دسترسی ادمین فعلی."
    )
    await message.answer(text)


async def _upsert_discount_code(
    *,
    code: str,
    percent_off: int,
    payment_method_scope: str,
    admin_user_id: int,
) -> tuple[str, bool]:
    async with async_session_maker() as session:
        existing = await session.scalar(select(DiscountCode).where(DiscountCode.code == code))
        if existing:
            existing.percent_off = percent_off
            existing.payment_method_scope = payment_method_scope
            existing.is_active = True
            existing.is_used = False
            existing.used_by_user_id = None
            existing.used_payment_id = None
            existing.used_at = None
            existing.created_by = admin_user_id
            await session.commit()
            return code, True

        session.add(
            DiscountCode(
                code=code,
                percent_off=percent_off,
                payment_method_scope=payment_method_scope,
                is_active=True,
                is_used=False,
                created_by=admin_user_id,
            )
        )
        await session.commit()
        return code, False


def _parse_discount_create_payload(raw_text: str) -> tuple[str | None, int | None, str | None]:
    parts = (raw_text or "").split()
    if len(parts) not in (3, 4):
        return None, None, None

    if parts[0].startswith("/discount_create"):
        parts = parts[1:]
    if len(parts) not in (2, 3):
        return None, None, None

    code = normalize_discount_code(parts[0])
    try:
        percent_off = int(parts[1])
    except ValueError:
        return code, None, None

    scope = normalize_discount_payment_method(parts[2] if len(parts) == 3 else "all")
    return code, percent_off, scope


@router.message(F.text == "مدیریت کد تخفیف")
async def start_discount_code_creation(message: Message, state: FSMContext):
    await state.set_state(DiscountCodeFSM.waiting_for_create_payload)
    await message.answer(
        "🏷 برای ساخت یا بروزرسانی کد تخفیف، پیام را با این فرمت ارسال کنید:\n\n"
        "<code>CODE PERCENT METHOD</code>\n\n"
        "نمونه‌ها:\n"
        "<code>SUMMER20 20 all</code>\n"
        "<code>CARD15 15 card</code>\n"
        "<code>CRYPTO10 10 crypto</code>\n\n"
        "مقادیر مجاز METHOD: <code>all</code>، <code>card</code>، <code>crypto</code>\n"
        "برای لغو: <code>/cancel</code>\n\n"
        "برای مشاهده کدها: <code>/discount_list</code>\n"
        "برای غیرفعالسازی: <code>/discount_disable CODE</code>"
    )

@router.message(F.text == "خروج از ربات")
async def logout_admin(message: Message):
    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == message.from_user.id))
        if user:
            user.is_admin = False
            await session.commit()
    from aiogram.types import ReplyKeyboardRemove
    await message.answer("👋 شما از حساب مدیریت خارج شدید.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("discount_create"))
async def create_discount_code(message: Message):
    code, percent_off, payment_method_scope = _parse_discount_create_payload(message.text or "")
    if code is None or percent_off is None or payment_method_scope is None:
        await message.answer(
            "فرمت صحیح:\n<code>/discount_create CODE PERCENT METHOD</code>\n"
            "مثال:\n<code>/discount_create SUMMER10 10 all</code>\n"
            "<code>/discount_create CARD20 20 card</code>\n"
            "<code>/discount_create CRYPTO15 15 crypto</code>"
        )
        return
    if not code or percent_off <= 0 or percent_off >= 100:
        await message.answer("کد یا درصد نامعتبر است. درصد باید بین 1 تا 99 باشد.")
        return

    code, existed = await _upsert_discount_code(
        code=code,
        percent_off=percent_off,
        payment_method_scope=payment_method_scope,
        admin_user_id=message.from_user.id,
    )
    status_text = "بروزرسانی و فعال" if existed else "ساخته"
    await message.answer(
        f"کد تخفیف <code>{code}</code> با {percent_off}٪ {status_text} شد.\n"
        f"روش پرداخت مجاز: <b>{discount_scope_label(payment_method_scope)}</b>"
    )


@router.message(DiscountCodeFSM.waiting_for_create_payload)
async def process_discount_code_creation(message: Message, state: FSMContext):
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("✅ عملیات مدیریت کد تخفیف لغو شد.")
        return

    code, percent_off, payment_method_scope = _parse_discount_create_payload(message.text or "")
    if code is None or percent_off is None or payment_method_scope is None:
        await message.answer(
            "فرمت نامعتبر است. دوباره به این شکل بفرستید:\n"
            "<code>CODE PERCENT METHOD</code>\n"
            "مثال: <code>SUMMER20 20 all</code>"
        )
        return
    if not code or percent_off <= 0 or percent_off >= 100:
        await message.answer("کد یا درصد نامعتبر است. درصد باید بین 1 تا 99 باشد.")
        return

    code, existed = await _upsert_discount_code(
        code=code,
        percent_off=percent_off,
        payment_method_scope=payment_method_scope,
        admin_user_id=message.from_user.id,
    )
    await state.clear()
    status_text = "بروزرسانی و فعال" if existed else "ساخته"
    await message.answer(
        f"✅ کد تخفیف <code>{code}</code> با {percent_off}٪ {status_text} شد.\n"
        f"روش پرداخت مجاز: <b>{discount_scope_label(payment_method_scope)}</b>"
    )


@router.message(Command("discount_disable"))
async def disable_discount_code(message: Message):
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("فرمت صحیح:\n<code>/discount_disable CODE</code>")
        return

    code = normalize_discount_code(parts[1])
    async with async_session_maker() as session:
        discount = await session.scalar(select(DiscountCode).where(DiscountCode.code == code))
        if not discount:
            await message.answer("کد تخفیف پیدا نشد.")
            return
        discount.is_active = False
        await session.commit()

    await message.answer(f"کد تخفیف <code>{code}</code> غیرفعال شد.")


@router.message(Command("discount_list"))
async def list_discount_codes(message: Message):
    async with async_session_maker() as session:
        codes = (await session.scalars(select(DiscountCode).order_by(DiscountCode.created_at.desc()).limit(20))).all()

    if not codes:
        await message.answer("هیچ کد تخفیفی ثبت نشده است.")
        return

    lines = ["کدهای تخفیف اخیر:\n"]
    for item in codes:
        status = "فعال" if item.is_active else "غیرفعال"
        usage = "استفاده شده" if item.is_used else "استفاده نشده"
        lines.append(
            f"<code>{item.code}</code> | {item.percent_off}٪ | {discount_scope_label(item.payment_method_scope)} | {status} | {usage}"
        )
    await message.answer("\n".join(lines))

# --- Broadcast Feature ---
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
import logging

class BroadcastFSM(StatesGroup):
    waiting_for_message = State()

@router.message(F.text == "پیام همگانی")
async def admin_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(BroadcastFSM.waiting_for_message)
    await message.answer("📢 لطفاً پیام خود را (متن، عکس، یا ویدیو) جهت ارسال همگانی به همه کاربران ربات ارسال کنید.\nبرای لغو، دستور /cancel را بفرستید.")

@router.message(BroadcastFSM.waiting_for_message)
async def admin_broadcast_execute(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("✅ عملیات ارسال همگانی لغو شد.")
        return
        
    await state.clear()
    status_msg = await message.answer("⏳ در حال ارسال پیام همگانی... لطفاً منتظر بمانید.")
    
    async with async_session_maker() as session:
        result = await session.execute(
            select(User.id).where(User.is_blocked.is_(False), User.id > 0)
        )
        all_chat_ids = result.scalars().all()
        
    total_attempted = len(all_chat_ids)
    success_count = 0
    fail_count = 0
    
    for chat_id in all_chat_ids:
        try:
            await message.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            success_count += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await message.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                success_count += 1
            except TelegramAPIError as retry_exc:
                logging.error(f"Failed to broadcast to {chat_id} after retry: {retry_exc}")
                fail_count += 1
        except TelegramAPIError as e:
            logging.error(f"Failed to broadcast to {chat_id}: {e}")
            fail_count += 1
            if "chat not found" in str(e).lower() or "bot was blocked" in str(e).lower():
                async with async_session_maker() as session:
                    user = await session.get(User, chat_id)
                    if user:
                        user.is_blocked = True
                        await session.commit()
        except Exception as e:
            logging.exception(f"Unexpected broadcast failure for {chat_id}: {e}")
            fail_count += 1
            
        await asyncio.sleep(0.05)
        
    report = (
        "✅ **پایان ارسال پیام همگانی!**\n\n"
        f"👥 کل مخاطبان: {total_attempted}\n"
        f"🟢 ارسال موفق: {success_count}\n"
        f"🔴 ارسال ناموفق (مسدود/دیلیت اکانت): {fail_count}"
    )
    await status_msg.edit_text(report, parse_mode="Markdown")

@router.message(F.text == "اجرای سئو")
async def execute_seo_bot(message: Message):
    from app.worker.seo_bot import run_auto_seo_updater
    status_msg = await message.answer("⏳ در حال اجرای ربات خودکار سئو...")
    try:
        await run_auto_seo_updater(force=True)
        await status_msg.edit_text("✅ سئو با موفقیت بروزرسانی شد و متادیتاها اعمال شدند.")
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در اجرای سئو: {e}")
