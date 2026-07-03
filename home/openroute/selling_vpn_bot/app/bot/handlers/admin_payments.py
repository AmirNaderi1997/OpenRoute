from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.services.payment_pipeline import (
    execute_manual_balance_credit,
    execute_payment_approval,
    execute_payment_decline,
    retry_payment_activation,
)
from app.services.connection_links import get_connection_details
from app.db.database import async_session_maker
from app.db.models import SshAccount, SshServer, User, SupportTicket, TicketMessage, Payment
from app.services.account_types import ACCOUNT_TYPE_V2RAY
from app.services.ssh.remote_provisioner import RemoteProvisionerClient
from app.services.ssh_account_service import renew_remote_account
from app.bot.lexicon import Lexicon
from app.core.config import settings
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)
router = Router(name="admin_payments_router")

class AdminReplyTicketFSM(StatesGroup):
    waiting_for_reply = State()

@router.callback_query(F.data.startswith("adm_pay_approve_"))
async def handle_admin_approve(callback: CallbackQuery):
    payment_id = int(callback.data.split("_")[3])
    
    success, result_type = await execute_payment_approval(payment_id)
    if success:
        orig = callback.message.text or callback.message.caption or ""
        if result_type == "auto_activated":
            new_text = orig + "\n\n✅ <b>تایید شد و اکانت به صورت خودکار برای کاربر ارسال گردید.</b>"
            alert_text = "✅ تایید شد و اکانت به صورت خودکار ساخته و برای کاربر ارسال گردید."
        elif result_type == "capacity_full":
            new_text = orig + "\n\n✅ <b>تایید شد (شارژ کیف پول)، اما به دلیل تکمیل ظرفیت، اکانت به صورت خودکار فعال نشد.</b>"
            alert_text = "✅ تایید شد (کیف پول شارژ شد) اما ظرفیت سرور برای فعال‌سازی خودکار کافی نبود."
        elif result_type == "wallet_only":
            new_text = orig + "\n\n✅ <b>این پرداخت تایید شد و کیف پول کاربر شارژ گردید.</b>"
            alert_text = "✅ پرداخت تایید شد و کیف پول کاربر با موفقیت شارژ گردید."
        else:
            new_text = orig + "\n\n✅ <b>این پرداخت توسط شما تایید شد.</b>"
            alert_text = f"✅ پرداخت تایید شد. وضعیت: {result_type}"
            
        if callback.message.caption is not None:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(new_text, reply_markup=None)
            
        await callback.answer(alert_text, show_alert=True)
    else:
        if result_type.startswith("ssh_error:"):
            error_details = result_type.split(":", 1)[1]
            orig = callback.message.text or callback.message.caption or ""
            new_text = orig + "\n\n✅ <b>تایید شد (موجودی شارژ شد)، اما فعال‌سازی اکانت به دلیل خطای سرور با شکست مواجه شد.</b>"
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            retry_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 تلاش مجدد فعال‌سازی", callback_data=f"adm_pay_retry_{payment_id}")]
            ])
            
            if callback.message.caption is not None:
                await callback.message.edit_caption(caption=new_text, reply_markup=retry_kb)
            else:
                await callback.message.edit_text(new_text, reply_markup=retry_kb)
                
            try:
                await callback.message.reply(
                    f"🔴 <b>خطای Provisioning (ارتباط با سرور):</b>\n\n"
                    f"کد پرداخت: <code>{payment_id}</code>\n"
                    f"جزئیات خطا:\n<code>{error_details}</code>\n\n"
                    f"اقدام مورد نیاز: بررسی وضعیت سرور و فعال‌سازی دستی سرویس کاربر.",
                )
            except Exception as e:
                logger.error(f"Failed to reply with granular details: {e}")
                
            await callback.answer("تایید شد اما خطای ارتباط با سرور رخ داد. مبلغ در کیف پول کاربر محفوظ است.", show_alert=True)
        else:
            await callback.answer("خطا در تایید. ممکن است توسط ادمین دیگری پردازش شده باشد.", show_alert=True)

@router.callback_query(F.data.startswith("adm_pay_retry_"))
async def handle_admin_payment_retry(callback: CallbackQuery):
    payment_id = int(callback.data.split("_")[3])
    await callback.answer("⏳ در حال تلاش مجدد فعال‌سازی...", show_alert=False)

    success, result_type = await retry_payment_activation(payment_id)
    orig = callback.message.text or callback.message.caption or ""

    if success:
        new_text = orig + "\n\n✅ <b>تلاش مجدد موفق بود و سرویس برای کاربر ارسال شد.</b>"
        if callback.message.caption is not None:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer("✅ سرویس با موفقیت فعال شد.", show_alert=True)
        return

    if result_type.startswith("ssh_error:"):
        error_details = result_type.split(":", 1)[1]
        await callback.message.reply(
            f"🔴 <b>تلاش مجدد فعال‌سازی ناموفق بود.</b>\n\n"
            f"کد پرداخت: <code>{payment_id}</code>\n"
            f"جزئیات خطا:\n<code>{error_details}</code>"
        )
        await callback.answer("فعال‌سازی هنوز ناموفق است. وضعیت پرداخت قابل تلاش مجدد باقی ماند.", show_alert=True)
        return

    await callback.answer(f"امکان تلاش مجدد وجود ندارد: {result_type}", show_alert=True)

@router.callback_query(F.data.startswith("adm_pay_decline_"))
async def handle_admin_decline(callback: CallbackQuery):
    payment_id = int(callback.data.split("_")[3])
    await callback.answer("⏳ در حال لغو...", show_alert=False)
    
    success = await execute_payment_decline(payment_id)
    if success:
        orig = callback.message.text or callback.message.caption or ""
        new_text = orig + "\n\n❌ <b>این پرداخت توسط شما رد شد.</b>"
        if callback.message.caption is not None:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(new_text, reply_markup=None)
    else:
        await callback.answer("خطا در رد پرداخت.", show_alert=True)

@router.callback_query(F.data.startswith("adm_srv_buy_approve_"))
async def handle_srv_buy_approve(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[4])
    await callback.answer("⏳ در حال فعالسازی اکانت...", show_alert=False)
    
    async with async_session_maker() as session:
        account = await session.get(SshAccount, account_id)
        if not account or account.status != "pending":
            await callback.answer("❌ این درخواست معتبر نیست یا قبلاً بررسی شده است.", show_alert=True)
            return
            
        server = await session.get(SshServer, account.server_id)
        user = await session.get(User, account.user_id)
        if not server or not user:
            await callback.answer("❌ سرور یا کاربر یافت نشد.", show_alert=True)
            return
            
        provisioner = RemoteProvisionerClient()
        if await provisioner.user_exists(account.ssh_username):
            _, import_link = await renew_remote_account(session, account, duration_days=30)
        else:
            payload = await provisioner.create_account(
                username=account.ssh_username,
                password=account.ssh_password,
                expire_days=30,
                max_connections=account.max_connections,
            )
            account.expires_at = datetime.fromisoformat(str(payload["expires_at"]))
            account.status = "active"
            account.service_type = ACCOUNT_TYPE_V2RAY
            import_link = str(get_connection_details(account.ssh_username, account.ssh_password, service_type=account.service_type)["import_link"])
        account.import_link = import_link
        await session.commit()
        connection = get_connection_details(account.ssh_username, account.ssh_password, service_type=account.service_type)
        
        # Notify the user
        try:
            success_text = (
                f"✅ <b>سرویس شما توسط مدیریت تایید و فعال شد!</b>\n\n"
                + Lexicon.purchase_success(
                    account.service_type,
                    account.ssh_username,
                    account.ssh_password,
                    import_link,
                    str(connection["path"]),
                    str(connection["host"]),
                    connection["port"],
                )
            )
            await callback.bot.send_message(chat_id=account.user_id, text=success_text)
        except Exception as e:
            logger.error(f"Failed to notify user {account.user_id} of purchase approval: {e}")
            
    admin_user = callback.from_user.username or callback.from_user.first_name
    new_text = callback.message.text + f"\n\n✅ <b>تایید و ساخته شد</b> (توسط @{admin_user})"
    await callback.message.edit_text(new_text, reply_markup=None)
    await callback.answer("✅ با موفقیت فعال شد.", show_alert=True)

@router.callback_query(F.data.startswith("adm_srv_buy_decline_"))
async def handle_srv_buy_decline(callback: CallbackQuery):
    account_id = int(callback.data.split("_")[4])
    await callback.answer("⏳ در حال رد درخواست...", show_alert=False)
    
    async with async_session_maker() as session:
        account = await session.get(SshAccount, account_id)
        if not account or account.status != "pending":
            await callback.answer("❌ این درخواست معتبر نیست یا قبلاً بررسی شده است.", show_alert=True)
            return
            
        user = await session.get(User, account.user_id)
        if not user:
            await callback.answer("❌ کاربر یافت نشد.", show_alert=True)
            return
            
        price = 600000 if account.max_connections == 1 else 800000
        
        # Refund user balance
        user.balance = float(user.balance) + price
        
        # Reset account status back to inactive and unassigned
        account.status = "inactive"
        account.user_id = 1 # Assigned back to system_store
        await session.commit()
        
        # Notify the user
        try:
            decline_text = (
                f"❌ <b>خرید سرویس شما توسط مدیریت رد شد.</b>\n\n"
                f"💵 مبلغ <code>{price:,}</code> تومان به کیف پول شما بازگردانده شد."
            )
            await callback.bot.send_message(chat_id=user.id, text=decline_text)
        except Exception as e:
            logger.error(f"Failed to notify user {user.id} of purchase decline: {e}")
            
    admin_user = callback.from_user.username or callback.from_user.first_name
    new_text = callback.message.text + f"\n\n❌ <b>رد و بازگشت وجه انجام شد</b> (توسط @{admin_user})"
    await callback.message.edit_text(new_text, reply_markup=None)
    await callback.answer("❌ درخواست رد شد و هزینه عودت داده شد.", show_alert=True)

@router.message(AdminReplyTicketFSM.waiting_for_reply)
async def process_admin_ticket_reply(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ عملیات ارسال پاسخ لغو شد.")
        return
        
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    reply_text = message.text
    
    async with async_session_maker() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket:
            await message.answer("❌ خطای غیرمنتظره: تیکت یافت نشد.")
            await state.clear()
            return
            
        ticket.status = "resolved"
        
        reply = TicketMessage(
            ticket_id=ticket_id,
            sender="admin",
            text=reply_text
        )
        session.add(reply)
        await session.commit()
        
        # Notify the user
        try:
            user_notify = (
                f"✉️ <b>پاسخ جدید از پشتیبانی برای تیکت #{ticket_id}:</b>\n\n"
                f"{reply_text}"
            )
            await message.bot.send_message(chat_id=ticket.user_id, text=user_notify)
            await message.answer("✅ پاسخ شما با موفقیت ثبت و برای کاربر ارسال شد.")
        except Exception as e:
            logger.error(f"Failed to notify user {ticket.user_id} of ticket reply: {e}")
            await message.answer("⚠️ پاسخ در سیستم ثبت شد، اما ارسال پیام تلگرام به کاربر با خطا مواجه شد.")
            
    await state.clear()

@router.callback_query(F.data.startswith("adm_pay_manual_add_"))
async def handle_manual_add_click(callback: CallbackQuery):
    payment_id = int(callback.data.split("_")[4])
    await callback.answer("⏳ در حال پردازش خودکار...", show_alert=False)

    async with async_session_maker() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            await callback.answer("❌ تراکنش یافت نشد.", show_alert=True)
            return
        is_service_purchase = payment.server_id is not None

    original_msg = callback.message.text or callback.message.caption or ""
    admin_user = callback.from_user.username or callback.from_user.first_name or "admin"

    if is_service_purchase:
        success, result_type = await execute_payment_approval(payment_id)
        if success and result_type == "auto_activated":
            new_text = (
                original_msg
                + "\n\n✅ <b>سرویس خریداری شده با موفقییت برای کاربر ارسال شد.</b>\n"
                + f"👤 توسط @{admin_user}"
            )
            if callback.message.caption is not None:
                await callback.message.edit_caption(caption=new_text, reply_markup=None)
            else:
                await callback.message.edit_text(new_text, reply_markup=None)
            await callback.answer("✅ سرویس خریداری شده با موفقییت برای کاربر ارسال شد.", show_alert=True)
            return

        if not success and result_type.startswith("ssh_error:"):
            error_details = result_type.split(":", 1)[1]
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            retry_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 تلاش مجدد فعال‌سازی", callback_data=f"adm_pay_retry_{payment_id}")]
                ]
            )
            failed_text = (
                original_msg
                + "\n\n✅ <b>پرداخت تایید شد، اما ارسال خودکار سرویس با خطا مواجه شد.</b>"
            )
            if callback.message.caption is not None:
                await callback.message.edit_caption(caption=failed_text, reply_markup=retry_kb)
            else:
                await callback.message.edit_text(failed_text, reply_markup=retry_kb)
            await callback.message.reply(
                f"🔴 <b>خطای Provisioning (ارتباط با سرور):</b>\n\n"
                f"کد پرداخت: <code>{payment_id}</code>\n"
                f"جزئیات خطا:\n<code>{error_details}</code>"
            )
            await callback.answer("پرداخت تایید شد اما ارسال خودکار سرویس ناموفق بود.", show_alert=True)
            return

        await callback.answer("❌ این تراکنش معتبر نیست یا قبلاً پردازش شده است.", show_alert=True)
        return

    success, result_type, credited_amount, current_balance = await execute_manual_balance_credit(payment_id)
    if not success:
        if result_type == "user_not_found":
            await callback.answer("❌ کاربر این تراکنش یافت نشد.", show_alert=True)
            return
        await callback.answer("❌ این تراکنش معتبر نیست یا قبلاً پردازش شده است.", show_alert=True)
        return

    new_text = (
        original_msg
        + "\n\n✅ <b>کیف پول کاربر با موفقییت شارژ شد.</b>\n"
        + f"💵 مبلغ شارژ شده: <code>{credited_amount:,}</code> تومان\n"
        + f"💳 موجودی جدید کاربر: <code>{current_balance:,}</code> تومان\n"
        + f"👤 توسط @{admin_user}"
    )
    if callback.message.caption is not None:
        await callback.message.edit_caption(caption=new_text, reply_markup=None)
    else:
        await callback.message.edit_text(new_text, reply_markup=None)

    await callback.answer("✅ کیف پول کاربر با موفقییت شارژ شد.", show_alert=True)

@router.callback_query(F.data.startswith("adm_pay_block_user_"))
async def handle_block_user_click(callback: CallbackQuery):
    payment_id = int(callback.data.split("_")[4])
    await callback.answer("⏳ در حال مسدود سازی...", show_alert=False)
    
    async with async_session_maker() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            await callback.answer("تراکنش یافت نشد.", show_alert=True)
            return
            
        user = await session.get(User, payment.user_id)
        if not user:
            await callback.answer("کاربر یافت نشد.", show_alert=True)
            return
            
        # Block user in DB
        user.is_blocked = True
        
        # Get active accounts
        accounts = (await session.scalars(
            select(SshAccount).where(SshAccount.user_id == user.id, SshAccount.status == "active")
        )).all()
        
        # Lock them on remote servers
        locked_count = 0
        for acc in accounts:
            try:
                provisioner = RemoteProvisionerClient()
                await provisioner.lock_account(acc.ssh_username)
                acc.status = "locked"
                locked_count += 1
            except Exception as e:
                logger.error(f"Failed to lock user {acc.ssh_username}: {e}")
                    
        await session.commit()
        
        # Notify user
        try:
            await callback.bot.send_message(
                chat_id=user.id,
                text="⚠️ <b>حساب کاربری شما به دلیل تخلف مسدود گردید و تمام سرویس‌های فعال شما لغو شد.</b>"
            )
        except Exception:
            pass
            
    original_msg = callback.message.text or callback.message.caption or ""
    new_text = original_msg + f"\n\n🔴 <b>کاربر مسدود شد و {locked_count} اکانت او لغو گردید.</b>"
    
    if callback.message.caption is not None:
        await callback.message.edit_caption(caption=new_text, reply_markup=None)
    else:
        await callback.message.edit_text(new_text, reply_markup=None)
        
    await callback.answer("❌ کاربر مسدود و سرویس‌های او لغو شد.", show_alert=True)
