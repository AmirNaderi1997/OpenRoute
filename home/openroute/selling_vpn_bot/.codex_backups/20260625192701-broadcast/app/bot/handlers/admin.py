import asyncio
import io
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.bot.filters.admin import AdminFilter
from app.bot.admin_lexicon import AdminLexicon
from app.bot.admin_keyboards import (
    get_admin_servers_menu,
    get_admin_accounts_menu,
    get_admin_server_list_for_bulk,
    get_admin_back_button,
    get_admin_reply_keyboard,
    AdminMenuCallback,
    AdminMenuCallback,
    AdminServerCallback,
    AdminSshCallback
)
from app.services.ssh.linux import LinuxSSHManager
from app.services.account_types import ACCOUNT_TYPE_SSH
from app.services.connection_links import get_connection_details
from app.db.models import utcnow
from datetime import timedelta

router = Router(name="admin_router")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

class AddServerFSM(StatesGroup):
    name = State()
    ip_port = State()
    password = State()

class BulkCreateFSM(StatesGroup):
    select_server = State()
    upload_file = State()


class CreateSingleSshFSM(StatesGroup):
    select_server = State()
    username = State()
    duration = State()

# --- Main Dashboard ---
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    text = "👋 به پنل مدیریت پیشرفته خوش آمدید.\nلطفاً از منوی پایین یک گزینه را انتخاب کنید:"
    await message.answer(text, reply_markup=get_admin_reply_keyboard())

@router.callback_query(AdminMenuCallback.filter(F.action == "main"))
async def back_to_admin_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    text = "بازگشت به منوی اصلی. (از کیبورد پایین استفاده کنید)"
    await callback.message.answer(text, reply_markup=get_admin_reply_keyboard())
    await callback.answer()

@router.callback_query(AdminMenuCallback.filter(F.action == "servers"))
async def back_to_admin_servers(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(AdminLexicon.SERVER_MGMT, reply_markup=get_admin_servers_menu())
    await callback.answer()

@router.callback_query(AdminMenuCallback.filter(F.action == "accounts"))
async def back_to_admin_accounts(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(AdminLexicon.SSH_MGMT, reply_markup=get_admin_accounts_menu())
    await callback.answer()


@router.message(F.text == "ساخت کاربر SSH")
async def create_single_ssh_start_text(message: Message, state: FSMContext):
    await state.set_state(CreateSingleSshFSM.select_server)
    await message.answer("لطفاً سرور SSH مورد نظر را انتخاب کنید:", reply_markup=await get_admin_server_list_for_bulk())


@router.callback_query(AdminSshCallback.filter(F.action == "add_single"))
async def create_single_ssh_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateSingleSshFSM.select_server)
    await callback.message.edit_text("لطفاً سرور SSH مورد نظر را انتخاب کنید:", reply_markup=await get_admin_server_list_for_bulk())


@router.callback_query(CreateSingleSshFSM.select_server, AdminServerCallback.filter(F.action == "select_bulk"))
async def create_single_ssh_pick_server(callback: CallbackQuery, callback_data: AdminServerCallback, state: FSMContext):
    await state.update_data(server_id=callback_data.server_id)
    await state.set_state(CreateSingleSshFSM.username)
    await callback.message.edit_text("نام کاربری SSH را وارد کنید:")


@router.message(CreateSingleSshFSM.username)
async def create_single_ssh_username(message: Message, state: FSMContext):
    username = (message.text or "").strip()
    if not username:
        await message.answer("نام کاربری معتبر نیست.")
        return
    await state.update_data(username=username)
    await state.set_state(CreateSingleSshFSM.duration)
    await message.answer("مدت اعتبار اکانت SSH را به روز وارد کنید:")


@router.message(CreateSingleSshFSM.duration)
async def create_single_ssh_duration(message: Message, state: FSMContext):
    if not (message.text or "").isdigit():
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return

    data = await state.get_data()
    server_id = int(data["server_id"])
    username = data["username"]
    duration = int(message.text)
    password = "".join(__import__("secrets").choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(10))
    status_msg = await message.answer("⏳ در حال ساخت اکانت SSH روی سرور...")

    from app.db.database import async_session_maker
    from app.db.models import SshServer, SshAccount
    from sqlalchemy import select

    async with async_session_maker() as session:
        server = await session.get(SshServer, server_id)
        if not server:
            await status_msg.edit_text("❌ سرور یافت نشد.")
            await state.clear()
            return

        existing = await session.scalar(select(SshAccount).where(SshAccount.ssh_username == username))
        if existing:
            await status_msg.edit_text("❌ این نام کاربری قبلاً ثبت شده است.")
            await state.clear()
            return

        ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
        success = await ssh_manager.create_system_user(server.ip_address, username, password, duration)
        if not success:
            await status_msg.edit_text("❌ ساخت اکانت SSH روی VPS ناموفق بود.")
            await state.clear()
            return

        expires_at = utcnow() + timedelta(days=duration)
        connection = get_connection_details(username, password, service_type=ACCOUNT_TYPE_SSH)
        account = SshAccount(
            user_id=message.from_user.id,
            server_id=server.id,
            ssh_username=username,
            ssh_password=password,
            import_link=str(connection["import_link"]),
            duration_days=duration,
            traffic_limit_gb=None,
            expires_at=expires_at,
            status="active",
            service_type=ACCOUNT_TYPE_SSH,
        )
        session.add(account)
        await session.commit()

    await status_msg.edit_text(
        "✅ اکانت SSH با موفقیت ساخته شد.\n\n"
        f"👤 نام کاربری: <code>{username}</code>\n"
        f"🔐 رمز عبور: <code>{password}</code>\n"
        f"🖥 سرور: {server.name}\n"
        f"📅 اعتبار: {duration} روز\n"
        f"🔗 لینک اتصال:\n<code>{connection['import_link']}</code>",
        parse_mode="HTML",
    )
    await state.clear()

@router.message(F.text == "سرورهای VPS")
async def admin_servers_menu_text(message: Message):
    await message.answer(AdminLexicon.SERVER_MGMT, reply_markup=get_admin_servers_menu())

async def ping_server(ip: str, port: int) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=2.0
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

@router.callback_query(AdminServerCallback.filter(F.action == "add"))
async def add_server_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddServerFSM.name)
    await callback.message.edit_text(AdminLexicon.ADD_SERVER_NAME, reply_markup=get_admin_back_button("servers").as_markup())
    await callback.answer()

@router.callback_query(AdminServerCallback.filter(F.action == "list"))
async def list_servers_callback(callback: CallbackQuery):
    from app.db.database import async_session_maker
    from app.db.models import SshServer, SshAccount
    from sqlalchemy import select, func
    
    async with async_session_maker() as session:
        servers = (await session.scalars(select(SshServer))).all()
        
        report = "📋 <b>لیست سرورهای VPS:</b>\n\n"
        if not servers:
            report += "❌ هیچ سروری ثبت نشده است."
        else:
            for srv in servers:
                # Count active accounts on this server
                active_accs = await session.scalar(
                    select(func.count(SshAccount.id)).where(SshAccount.server_id == srv.id, SshAccount.status == "active")
                ) or 0
                
                # Check server status online/offline using ping_server
                is_online = await ping_server(srv.ip_address, srv.ssh_port)
                status_str = "🟢 آنلاین" if is_online else "🔴 آفلاین"
                
                report += (
                    f"🖥 <b>سرور: {srv.name}</b>\n"
                    f"🌐 آی‌پی: <code>{srv.ip_address}</code>\n"
                    f"🔌 پورت: <code>{srv.ssh_port}</code>\n"
                    f"👤 اکانت‌های فعال: <code>{active_accs}</code>\n"
                    f"⚡️ وضعیت: {status_str}\n"
                    f"---------------------\n"
                )
    await callback.message.edit_text(report, reply_markup=get_admin_back_button("servers").as_markup())
    await callback.answer()

@router.message(F.text == "مدیریت کاربر")
async def show_all_users_info(message: Message):
    status_msg = await message.answer("⏳ در حال دریافت اطلاعات کاربران از دیتابیس و بررسی لاگ‌های سرور... (لطفاً منتظر بمانید)")
    
    from app.db.database import async_session_maker
    from app.db.models import SshServer, SshAccount
    from sqlalchemy import select
    from app.services.ssh.linux import LinuxSSHManager
    
    async with async_session_maker() as session:
        servers = (await session.scalars(select(SshServer))).all()
        accounts = (await session.scalars(select(SshAccount))).all()
        
    if not accounts:
        await status_msg.edit_text("❌ هیچ کاربری در دیتابیس ثبت نشده است.")
        return
        
    server_accounts = {}
    for acc in accounts:
        server_accounts.setdefault(acc.server_id, []).append(acc)
        
    report_lines = []
    
    for srv in servers:
        if srv.id not in server_accounts:
            continue
            
        report_lines.append(f"\n🖥 **سرور: {srv.name}**")
        report_lines.append("➖➖➖➖➖➖➖➖➖➖")
        
        lastlog_dict = {}
        try:
            ssh = LinuxSSHManager(ssh_port=srv.ssh_port, root_password=srv.root_password)
            users_list = " ".join([a.ssh_username for a in server_accounts[srv.id]])
            
            # Bash script to safely get last login
            script = f"""
            for u in {users_list}; do
              info=$(last -n 1 "$u" 2>/dev/null | head -n 1)
              if [[ "$info" == *"wtmp"* ]] || [[ -z "$info" ]]; then
                echo "$u|بدون اتصال"
              else
                date_str=$(echo "$info" | awk '{{print $4, $5, $6, $7}}')
                echo "$u|$date_str"
              fi
            done
            """
            
            out = await ssh._run_command(srv.ip_address, script)
            if out:
                for line in out.strip().split("\n"):
                    if "|" in line:
                        u, last_time = line.split("|", 1)
                        lastlog_dict[u] = last_time.strip()
        except Exception as e:
            report_lines.append(f"⚠️ خطای سرور: نتوانست به سرور متصل شود")
            
        for acc in server_accounts[srv.id]:
            limit = "نامحدود"
            last_conn = lastlog_dict.get(acc.ssh_username, "بدون اتصال")
            
            report_lines.append(
                f"👤 نام کاربری: `{acc.ssh_username}`\n"
                f"🔑 رمز عبور: `{acc.ssh_password}`\n"
                f"📊 مصرف ترافیک: {float(acc.traffic_used_gb):.2f} / {limit}\n"
                f"⏳ آخرین اتصال: {last_conn}\n"
                f"📅 انقضا: {acc.expires_at.strftime('%Y-%m-%d')}\n"
                "-----------------"
            )

    try:
        await status_msg.delete()
    except:
        pass
    
    # Send in chunks of 4000 characters
    full_text = "📋 **لیست کامل کاربران و وضعیت آن‌ها**\n" + "\n".join(report_lines)
    
    chunk = ""
    for line in full_text.split("\n"):
        if len(chunk) + len(line) + 1 > 4000:
            await message.answer(chunk, parse_mode="Markdown")
            chunk = line + "\n"
        else:
            chunk += line + "\n"
            
    if chunk.strip():
        await message.answer(chunk, parse_mode="Markdown")

# --- FSM Add Server Flow ---
@router.message(F.text == "افزودن VPS")
async def add_server_start_text(message: Message, state: FSMContext):
    await state.set_state(AddServerFSM.name)
    await message.answer(AdminLexicon.ADD_SERVER_NAME, reply_markup=get_admin_back_button("servers").as_markup())

@router.message(AddServerFSM.name)
async def add_server_ip(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddServerFSM.ip_port)
    
    # Send a new message, since the user just sent text, we can't edit it.
    # We could delete the user's message to keep it clean.
    try:
        await message.delete()
    except Exception:
        pass
    
    # Ideally, we should delete the previous bot message here, but for simplicity we'll just send a new one
    await message.answer(AdminLexicon.ADD_SERVER_IP, reply_markup=get_admin_back_button("servers").as_markup())

@router.message(AddServerFSM.ip_port)
async def add_server_password(message: Message, state: FSMContext):
    data = message.text.split()
    if len(data) != 2:
        await message.answer("فرمت نامعتبر! مجددا تلاش کنید:")
        return
        
    await state.update_data(ip=data[0], port=data[1])
    await state.set_state(AddServerFSM.password)
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(AdminLexicon.ADD_SERVER_PASS, reply_markup=get_admin_back_button("servers").as_markup())

@router.message(AddServerFSM.password)
async def add_server_save(message: Message, state: FSMContext):
    data = await state.get_data()
    
    from app.db.database import async_session_maker
    from app.db.models import SshServer
    
    async with async_session_maker() as session:
        new_srv = SshServer(
            name=data['name'],
            ip_address=data['ip'],
            ssh_port=int(data['port']),
            root_password=message.text,
            status="active"
        )
        session.add(new_srv)
        await session.commit()
    
    try:
        await message.delete()
    except Exception:
        pass
    
    await state.clear()
    await message.answer(AdminLexicon.ADD_SERVER_SUCCESS, reply_markup=get_admin_back_button("servers").as_markup())

# --- FSM Bulk Create Flow ---
@router.message(F.text.in_({"ساخت گروهی", "ساخت گروهی از VPS", "ساخت گروهی SSH"}))
async def bulk_create_start_text(message: Message, state: FSMContext):
    await state.set_state(BulkCreateFSM.select_server)
    await message.answer(AdminLexicon.BULK_CREATE_SERVER, reply_markup=await get_admin_server_list_for_bulk())

@router.callback_query(AdminSshCallback.filter(F.action == "add_bulk"))
async def bulk_create_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BulkCreateFSM.select_server)
    await callback.message.edit_text(AdminLexicon.BULK_CREATE_SERVER, reply_markup=await get_admin_server_list_for_bulk())

@router.callback_query(BulkCreateFSM.select_server, AdminServerCallback.filter(F.action == "select_bulk"))
async def bulk_create_upload(callback: CallbackQuery, callback_data: AdminServerCallback, state: FSMContext):
    await state.update_data(server_id=callback_data.server_id)
    await state.set_state(BulkCreateFSM.upload_file)
    await callback.message.edit_text(AdminLexicon.BULK_CREATE_FILE, reply_markup=get_admin_back_button("accounts").as_markup())

@router.message(BulkCreateFSM.upload_file, F.document)
async def bulk_create_process(message: Message, state: FSMContext):
    data = await state.get_data()
    server_id = data.get("server_id")
    
    status_msg = await message.answer(AdminLexicon.BULK_CREATE_START)
    
    try:
        file = await message.bot.get_file(message.document.file_id)
        content = await message.bot.download_file(file.file_path)
        text = content.read().decode('utf-8')
        
        accounts = []
        for line in text.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            u, p = line.split(':', 1)
            accounts.append((u, p))
            
        from app.db.database import async_session_maker
        from app.db.models import SshServer, SshAccount

        async with async_session_maker() as session:
            server = await session.get(SshServer, int(server_id))
            if not server:
                await status_msg.edit_text("❌ سرور یافت نشد.", reply_markup=get_admin_back_button("accounts").as_markup())
                return
                
            ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
            
            success_count = 0
            for u, p in accounts:
                existing = await session.scalar(select(SshAccount).where(SshAccount.ssh_username == u))
                if existing:
                    continue
                    
                duration = 30 # Default 30 days for bulk
                success = await ssh_manager.create_system_user(server.ip_address, u, p, duration)
                if success:
                    expires_at = utcnow() + timedelta(days=duration)
                    new_acc = SshAccount(
                        user_id=message.from_user.id,
                        server_id=server.id,
                        ssh_username=u,
                        ssh_password=p,
                        duration_days=duration,
                        traffic_limit_gb=None,
                        expires_at=expires_at,
                        service_type=ACCOUNT_TYPE_SSH,
                    )
                    session.add(new_acc)
                    success_count += 1
            
            await session.commit()
        
        await status_msg.edit_text(AdminLexicon.BULK_CREATE_SUCCESS.format(count=success_count), reply_markup=get_admin_back_button("accounts").as_markup())
        
    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در پردازش فایل: {e}", reply_markup=get_admin_back_button("accounts").as_markup())
    finally:
        await state.clear()
        try:
            await message.delete()
        except Exception:
            pass

# --- Broadcast Feature ---
from aiogram.exceptions import TelegramAPIError
import logging

class BroadcastFSM(StatesGroup):
    waiting_for_message = State()

@router.callback_query(AdminMenuCallback.filter(F.action == "broadcast"))
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastFSM.waiting_for_message)
    await callback.message.edit_text("📢 لطفاً پیام خود را (متن، عکس، یا ویدیو) جهت ارسال همگانی به همه کاربران ربات ارسال کنید.\nبرای لغو، دستور /cancel را بفرستید.")

@router.message(BroadcastFSM.waiting_for_message)
async def admin_broadcast_execute(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("✅ عملیات ارسال همگانی لغو شد.")
        return
        
    await state.clear()
    status_msg = await message.answer("⏳ در حال ارسال پیام همگانی... لطفاً منتظر بمانید.")
    
    # Query all users from PostgreSQL Database
    from app.db.database import async_session_maker
    from app.db.models import User
    from sqlalchemy import select
    
    async with async_session_maker() as session:
        result = await session.execute(select(User.id)) # id is the telegram_chat_id
        all_chat_ids = result.scalars().all()
        
    total_attempted = len(all_chat_ids)
    success_count = 0
    fail_count = 0
    
    for chat_id in all_chat_ids:
        try:
            # Use copy_to to effortlessly forward any type of media/text
            await message.copy_to(chat_id)
            success_count += 1
        except TelegramAPIError as e:
            # Catch exceptions like BotBlocked, ChatNotFound, UserDeactivated
            logging.error(f"Failed to broadcast to {chat_id}: {e}")
            fail_count += 1
            
        # RATE LIMITING: Telegram strictly limits broadcasting to ~30 msgs/sec.
        # We sleep for 0.05 seconds between messages (20 msgs/sec) to avoid FloodWait bans.
        await asyncio.sleep(0.05)
        
    # Final Report
    report = (
        "✅ <b>پایان ارسال پیام همگانی!</b>\n\n"
        f"👥 کل مخاطبان: {total_attempted}\n"
        f"🟢 ارسال موفق: {success_count}\n"
        f"🔴 ارسال ناموفق (مسدود/دیلیت اکانت): {fail_count}"
    )
    await status_msg.edit_text(report)
