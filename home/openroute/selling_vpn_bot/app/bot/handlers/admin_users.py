import asyncio
import logging
import re
import uuid
import httpx
from datetime import timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.callback_data import CallbackData
from sqlalchemy import select

from app.bot.filters.admin import AdminFilter
from app.bot.admin_keyboards import get_admin_server_list_for_bulk, AdminServerCallback, get_admin_reply_keyboard
from app.db.database import async_session_maker
from app.db.models import SshServer, SshAccount, User, utcnow
from app.services.account_types import ACCOUNT_TYPE_V2RAY
from app.services.ssh.linux import LinuxSSHManager

logger = logging.getLogger(__name__)

router = Router(name="admin_users_router")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

from app.services.connection_links import build_import_link
from datetime import datetime, timezone
from app.core.config import settings


USERNAME_RE = re.compile(r"^[a-zA-Z0-9-_@.]+$")


def _validate_username(username: str) -> str:
    username = username.strip()
    if not (3 <= len(username) <= 128):
        raise ValueError("Username only can be 3 to 128 characters.")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Username can only contain alphanumeric characters, -, _, @, and .")
    if re.search(r"[-_@.]{2,}", username):
        raise ValueError("Username cannot have consecutive special characters")
    return username


async def _pg_get_token(client: httpx.AsyncClient) -> str:
    """Authenticate with PasarGuard and return the access token."""
    resp = await client.post(
        "/api/admin/token",
        data={
            "username": settings.PASARGUARD_ADMIN_USERNAME,
            "password": settings.PASARGUARD_ADMIN_PASSWORD,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _pg_create_user(
    client: httpx.AsyncClient,
    token: str,
    username: str,
    expire_days: int,
    data_limit_gb: int,
    note: str = "",
) -> dict:
    """Create a user in PasarGuard via the raw API. Returns the full response dict."""
    # Build expiry timestamp (seconds since epoch, or None for no expiry)
    expire_ts = None
    if expire_days and expire_days > 0:
        expire_ts = int(
            (datetime.now(tz=timezone.utc) + timedelta(days=expire_days)).timestamp()
        )

    # Build data limit in bytes (None = unlimited)
    data_limit_bytes = None
    if data_limit_gb and data_limit_gb > 0:
        data_limit_bytes = data_limit_gb * 1024 * 1024 * 1024

    payload = {
        "username": username,
        "status": "active",
    }
    if expire_ts is not None:
        payload["expire"] = expire_ts
    if data_limit_bytes is not None:
        payload["data_limit"] = data_limit_bytes
    if note:
        payload["note"] = note
    # Add user to the configured PasarGuard group at creation time
    from app.core.config import settings as _settings
    if _settings.PASARGUARD_GROUP_ID:
        payload["group_ids"] = [int(_settings.PASARGUARD_GROUP_ID)]

    logger.info(f"[PasarGuard] Creating user payload: {payload}")

    resp = await client.post(
        "/api/user",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    if resp.status_code not in (200, 201):
        detail = resp.text.strip()
        logger.error(f"[PasarGuard] Create user failed {resp.status_code}: {detail}")
        raise RuntimeError(f"PasarGuard create_user failed {resp.status_code}: {detail}")

    return resp.json()


async def _pg_get_user(
    client: httpx.AsyncClient, token: str, username: str
) -> dict:
    """Fetch a PasarGuard user by username to get subscription_url and full details."""
    try:
        resp = await client.get(
            f"/api/user/by-username/{username}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"[PasarGuard] Get user {username} returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"[PasarGuard] Get user failed (non-fatal): {e}")
    return {}


async def _pg_get_groups(
    client: httpx.AsyncClient, token: str
) -> list:
    """Fetch available groups from PasarGuard."""
    try:
        resp = await client.get(
            "/api/groups",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"[PasarGuard] Get groups failed: {e}")
    return []


# --- Single User Create FSM ---
class CreateUserFSM(StatesGroup):
    server = State()
    username = State()
    duration = State()
    traffic = State()

@router.message(F.text.in_({"ساخت کاربر", "ساخت کاربر V2Ray"}))
async def create_user_start(message: Message, state: FSMContext):
    await state.set_state(CreateUserFSM.server)
    await message.answer("لطفاً سرور مورد نظر جهت ساخت اکانت را انتخاب کنید:", reply_markup=await get_admin_server_list_for_bulk())

@router.callback_query(CreateUserFSM.server, AdminServerCallback.filter(F.action == "select_bulk"))
async def create_user_server(callback: CallbackQuery, callback_data: AdminServerCallback, state: FSMContext):
    await state.update_data(server_id=callback_data.server_id)
    await state.set_state(CreateUserFSM.username)
    await callback.message.edit_text("✅ سرور انتخاب شد.\n\nلطفاً نام کاربری (انگلیسی و بدون فاصله) را وارد کنید:")

@router.message(CreateUserFSM.username)
async def create_user_username(message: Message, state: FSMContext):
    try:
        username = _validate_username(message.text or "")
    except ValueError as exc:
        await message.answer(f"❌ نام کاربری نامعتبر است: {exc}\n\nنام کاربری باید فقط شامل حروف/عدد/`-`/`_`/`@`/`.` باشد و بین 3 تا 128 کاراکتر باشد.")
        return

    await state.update_data(username=username)
    await state.set_state(CreateUserFSM.duration)
    await message.answer("لطفاً مدت اعتبار اکانت را به روز وارد کنید (مثلا: 30):")

@router.message(CreateUserFSM.duration)
async def create_user_duration(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return
    await state.update_data(duration=int(message.text))
    await state.set_state(CreateUserFSM.traffic)
    await message.answer("لطفاً محدودیت ترافیک را به گیگابایت وارد کنید (برای نامحدود 0 وارد کنید):")

@router.message(CreateUserFSM.traffic)
async def create_user_traffic(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return
        
    data = await state.get_data()
    server_id = data['server_id']
    username = data['username']
    duration = data['duration']
    traffic = int(message.text)
    
    status_msg = await message.answer("⏳ در حال ساخت اکانت در پنل PasarGuard و پایگاه داده...")
    
    async with async_session_maker() as session:
        server = await session.get(SshServer, server_id)
        if not server:
            await status_msg.edit_text("❌ سرور یافت نشد.")
            await state.clear()
            return
            
        # Check if user exists
        existing = await session.scalar(select(SshAccount).where(SshAccount.ssh_username == username))
        if existing:
            await status_msg.edit_text("❌ این نام کاربری قبلاً در دیتابیس ثبت شده است.")
            await state.clear()
            return
            
        try:
            # Create user via raw httpx calls to the PasarGuard API
            async with httpx.AsyncClient(
                base_url=settings.PASARGUARD_API_BASE,
                verify=False,
                timeout=30.0,
            ) as client:
                # Step 1: Authenticate
                access_token = await _pg_get_token(client)

                # Step 2: Create the user
                user_data = await _pg_create_user(
                    client=client,
                    token=access_token,
                    username=username,
                    expire_days=duration,
                    data_limit_gb=traffic,
                    note=f"Created by bot admin for user {message.from_user.id}",
                )
                logger.info(f"[PasarGuard] User created response: {user_data}")

                # Step 3: Extract VLESS UUID from proxy settings
                vless_id = ""
                proxy_settings = user_data.get("proxy_settings") or {}
                vless_cfg = proxy_settings.get("vless") or {}
                vless_id = vless_cfg.get("id") or ""

                # If no UUID found, generate one (will need to be set in panel manually)
                if not vless_id:
                    vless_id = str(uuid.uuid4())

                # Step 4: Fetch user to get the real token-based subscription_url
                # (creation response does NOT include subscription_url)
                user_detail = await _pg_get_user(client, access_token, username)
                logger.info(f"[PasarGuard] User detail: group_ids={user_detail.get('group_ids')}, sub={user_detail.get('subscription_url')}")

                # Step 5: Build subscription link (served by PasarGuard panel)
                sub_url = user_detail.get("subscription_url") or user_data.get("subscription_url") or ""
                if sub_url.startswith("http"):
                    # Already absolute URL
                    import_link = sub_url
                elif sub_url:
                    # Relative path — prepend the PasarGuard base
                    base = settings.PASARGUARD_API_BASE.rstrip("/")
                    import_link = f"{base}{sub_url}"
                else:
                    # Fallback: should not normally happen
                    import_link = f"{settings.PASARGUARD_API_BASE.rstrip('/')}/sub/{username}"

                # Step 6: Parse expiry (API returns ISO string like '2026-07-23T15:51:29Z')
                expire_raw = user_data.get("expire")
                if isinstance(expire_raw, (int, float)) and expire_raw:
                    expires_at = datetime.fromtimestamp(expire_raw, tz=timezone.utc)
                elif isinstance(expire_raw, str) and expire_raw:
                    try:
                        expires_at = datetime.fromisoformat(expire_raw.replace("Z", "+00:00"))
                    except ValueError:
                        expires_at = utcnow() + timedelta(days=duration)
                else:
                    expires_at = utcnow() + timedelta(days=duration)

        except Exception as e:
            logger.error(f"Failed to create user in PasarGuard: {e}", exc_info=True)
            await status_msg.edit_text(
                f"❌ خطا در ساخت اکانت در پنل PasarGuard.\n\n"
                f"جزئیات خطا: <code>{str(e)[:300]}</code>",
                parse_mode="HTML",
            )
            await state.clear()
            return
            
        # Save to DB
        new_acc = SshAccount(
            user_id=message.from_user.id, # Assigned to the admin who created it
            server_id=server.id,
            ssh_username=username,
            ssh_password=vless_id,
            import_link=import_link,
            duration_days=duration,
            traffic_limit_gb=traffic if traffic > 0 else None,
            expires_at=expires_at,
            status="active",
            service_type=ACCOUNT_TYPE_V2RAY,
        )
        session.add(new_acc)
        await session.commit()
        
    vless_link = build_import_link(username, vless_id)
    report = (
        "✅ **اکانت V2Ray با موفقیت ساخته شد!**\n\n"
        f"👤 نام کاربری: `{username}`\n"
        f"🔑 شناسه (UUID): `{vless_id}`\n"
        f"🖥 سرور: {server.name}\n"
        f"📅 اعتبار: {duration} روز\n"
        f"🌐 ترافیک: {'نامحدود' if traffic == 0 else f'{traffic} GB'}\n\n"
        f"🔗 **لینک اتصال Reality:**\n`{vless_link}`\n\n"
        f"🌐 **لینک ساب اسکریپشن:**\n`{import_link}`"
    )
    await status_msg.edit_text(report, parse_mode="Markdown")
    await state.clear()

# --- Search User FSM ---
class SearchUserFSM(StatesGroup):
    username = State()

@router.message(F.text == "کاربران")
async def search_user_start(message: Message, state: FSMContext):
    await state.set_state(SearchUserFSM.username)
    await message.answer("لطفاً نام کاربری را برای جستجو وارد کنید:\n(برای لغو /cancel را ارسال کنید)")

@router.message(SearchUserFSM.username)
async def search_user_execute(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("عملیات لغو شد.", reply_markup=get_admin_reply_keyboard())
        return
        
    username = message.text.strip()
    
    async with async_session_maker() as session:
        acc = await session.scalar(select(SshAccount).where(SshAccount.ssh_username == username))
        if not acc:
            await message.answer("❌ اکانتی با این نام کاربری یافت نشد. مجددا تلاش کنید:")
            return
            
        server = await session.get(SshServer, acc.server_id)
        
    limit = "نامحدود"
    report = (
        f"👤 **اطلاعات اکانت: {acc.ssh_username}**\n"
        f"وضعیت: {acc.status}\n"
        f"سرور: {server.name if server else 'نامشخص'}\n"
        f"مصرف: {acc.traffic_used_gb} از {limit}\n"
        f"انقضا: {acc.expires_at.strftime('%Y-%m-%d')}"
    )
    await message.answer(report)
    await state.clear()

# --- Edit Limit FSM ---
class EditLimitFSM(StatesGroup):
    username = State()
    traffic = State()
    duration = State()

@router.message(F.text == "اعمال محدودیت‌ها")
async def edit_limit_start(message: Message, state: FSMContext):
    await state.set_state(EditLimitFSM.username)
    await message.answer("لطفاً نام کاربری SSH اکانتی که قصد ویرایش آن را دارید وارد کنید:\n(لغو: /cancel)")

@router.message(EditLimitFSM.username)
async def edit_limit_user(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("عملیات لغو شد.")
        return
        
    username = message.text.strip()
    async with async_session_maker() as session:
        acc = await session.scalar(select(SshAccount).where(SshAccount.ssh_username == username))
        if not acc:
            await message.answer("❌ کاربری یافت نشد. مجددا وارد کنید:")
            return
            
    await state.update_data(account_id=acc.id)
    await state.set_state(EditLimitFSM.traffic)
    await message.answer(f"کاربر پیدا شد. محدودیت فعلی: {acc.traffic_limit_gb or 'نامحدود'} GB\nلطفاً محدودیت جدید ترافیک را وارد کنید (0 برای نامحدود):")

@router.message(EditLimitFSM.traffic)
async def edit_limit_traffic(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return
        
    await state.update_data(traffic=int(message.text))
    await state.set_state(EditLimitFSM.duration)
    await message.answer("لطفاً تعداد روزهایی که می‌خواهید به اعتبار اکانت اضافه شود را وارد کنید (برای عدم تغییر 0 بفرستید):")

@router.message(EditLimitFSM.duration)
async def edit_limit_duration(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return
        
    add_days = int(message.text)
    data = await state.get_data()
    
    async with async_session_maker() as session:
        acc = await session.get(SshAccount, data['account_id'])
        if not acc:
            await state.clear()
            return
            
        acc.traffic_limit_gb = data['traffic'] if data['traffic'] > 0 else None
        if add_days > 0:
            acc.expires_at = acc.expires_at + timedelta(days=add_days)
            acc.duration_days += add_days
            # Updates linux chage:
            server = await session.get(SshServer, acc.server_id)
            if server:
                ssh = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
                cmd = f"chage -E $(date -d '+{add_days} days' +%Y-%m-%d) {acc.ssh_username}"
                await ssh._run_command(server.ip_address, cmd)
            
        await session.commit()
        
    await message.answer("✅ تغییرات با موفقیت اعمال شد.")
    await state.clear()


# --- Admin User Wallet Reset Management ---

class AdminWalletCallback(CallbackData, prefix="admin_wallet"):
    action: str
    user_id: int

@router.message(F.text == "مدیریت کیف پول")
async def admin_manage_wallet_start(message: Message):
    async with async_session_maker() as session:
        users = (await session.scalars(
            select(User).where(User.id != 1).order_by(User.username.asc())
        )).all()
        
    if not users:
        await message.answer("❌ هیچ کاربری در سیستم یافت نشد.")
        return
        
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for u in users:
        name_str = f"@{u.username}" if u.username else f"ID: {u.id}"
        balance_str = f"({int(u.balance):,} ت)"
        builder.button(
            text=f"👤 {name_str} {balance_str}",
            callback_data=AdminWalletCallback(action="select_user", user_id=u.id)
        )
    builder.adjust(1)
    
    await message.answer("🔍 لیست کاربران سیستم. لطفاً کاربر مورد نظر را انتخاب کنید:", reply_markup=builder.as_markup())

@router.callback_query(AdminWalletCallback.filter(F.action == "select_user"))
async def admin_wallet_select_user(callback: CallbackQuery, callback_data: AdminWalletCallback):
    target_user_id = callback_data.user_id
    
    async with async_session_maker() as session:
        user = await session.get(User, target_user_id)
        if not user:
            await callback.answer("❌ کاربر یافت نشد.", show_alert=True)
            return
            
        username_str = f"@{user.username}" if user.username else "بدون نام کاربری"
        balance_val = int(user.balance)
        
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⚠️ صفر کردن موجودی کیف پول",
        callback_data=AdminWalletCallback(action="zero_balance", user_id=target_user_id)
    )
    builder.button(
        text="🔙 بازگشت به لیست کاربران",
        callback_data=AdminWalletCallback(action="list_users", user_id=0)
    )
    builder.adjust(1)
    
    report = (
        f"👤 **اطلاعات کیف پول کاربر:**\n\n"
        f"🆔 شناسه کاربر: <code>{target_user_id}</code>\n"
        f"👤 نام کاربری: {username_str}\n"
        f"💳 موجودی فعلی: <code>{balance_val:,}</code> تومان\n"
    )
    await callback.message.edit_text(report, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(AdminWalletCallback.filter(F.action == "list_users"))
async def admin_wallet_list_users(callback: CallbackQuery, callback_data: AdminWalletCallback):
    async with async_session_maker() as session:
        users = (await session.scalars(
            select(User).where(User.id != 1).order_by(User.username.asc())
        )).all()
        
    if not users:
        await callback.message.edit_text("❌ هیچ کاربری در سیستم یافت نشد.")
        return
        
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for u in users:
        name_str = f"@{u.username}" if u.username else f"ID: {u.id}"
        balance_str = f"({int(u.balance):,} ت)"
        builder.button(
            text=f"👤 {name_str} {balance_str}",
            callback_data=AdminWalletCallback(action="select_user", user_id=u.id)
        )
    builder.adjust(1)
    
    await callback.message.edit_text("🔍 لیست کاربران سیستم. لطفاً کاربر مورد نظر را انتخاب کنید:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(AdminWalletCallback.filter(F.action == "zero_balance"))
async def admin_wallet_zero(callback: CallbackQuery, callback_data: AdminWalletCallback):
    target_user_id = callback_data.user_id
    
    async with async_session_maker() as session:
        user = await session.get(User, target_user_id)
        if not user:
            await callback.answer("❌ کاربر یافت نشد.", show_alert=True)
            return
            
        user.balance = 0.0
        await session.commit()
        
        username_str = f"@{user.username}" if user.username else f"ID: {user.id}"
        
    await callback.answer("✅ موجودی صفر شد.")
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔙 بازگشت به لیست کاربران",
        callback_data=AdminWalletCallback(action="list_users", user_id=0)
    )
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"✅ موجودی کیف پول کاربر {username_str} با موفقیت صفر شد.",
        reply_markup=builder.as_markup()
    )
    
    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text="⚠️ موجودی کیف پول شما توسط مدیریت صفر شد."
        )
    except Exception as e:
        logger.error(f"Failed to notify user {target_user_id} about zeroed balance: {e}")
