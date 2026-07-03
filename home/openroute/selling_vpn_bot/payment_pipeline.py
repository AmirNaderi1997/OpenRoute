import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import select

from app.db.database import async_session_maker
from app.db.models import Payment, User, SshServer, SshAccount
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY, service_type_label
from app.services.connection_links import get_connection_details
from app.services.pricing import (
    decode_payment_metadata,
    get_plan_data_limit_gb,
    get_plan_max_connections,
    get_plan_title,
    get_plan_volume_label,
    mark_discount_code_as_used,
)
from app.services.ssh_account_service import create_remote_account
from app.core.config import settings
from app.core.topics_manager import get_manager_group_id, get_topic_id
from app.bot.lexicon import Lexicon

logger = logging.getLogger(__name__)


def _get_bot():
    """Lazy import to avoid circular dependency with app.bot."""
    from app.bot import bot
    return bot


PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_PROCESSING = "processing"
PAYMENT_STATUS_COMPLETED = "completed"
PAYMENT_STATUS_FAILED = "failed"
PAYMENT_STATUS_PROVISIONING_FAILED = "provisioning_failed"


async def _send_payment_notification(
    target_chat_id: int,
    msg: str,
    kb,
    file_id: str | None,
    is_doc: bool,
    message_thread_id: int | None = None,
) -> None:
    if file_id:
        if is_doc:
            await _get_bot().send_document(
                chat_id=target_chat_id,
                message_thread_id=message_thread_id,
                document=file_id,
                caption=msg,
                reply_markup=kb,
            )
        else:
            await _get_bot().send_photo(
                chat_id=target_chat_id,
                message_thread_id=message_thread_id,
                photo=file_id,
                caption=msg,
                reply_markup=kb,
            )
        return

    await bot.send_message(
        chat_id=target_chat_id,
        message_thread_id=message_thread_id,
        text=msg,
        reply_markup=kb,
    )

async def notify_admins_of_pending_payment(payment_id: int):
    try:
        async with async_session_maker() as session:
            payment = await session.get(Payment, payment_id)
            if not payment:
                return
            user = await session.get(User, payment.user_id)
            server = await session.get(SshServer, payment.server_id) if payment.server_id else None
            
            # Create inline keyboard manually to avoid circular imports
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="تایید پرداخت ✅", callback_data=f"adm_pay_approve_{payment_id}"),
                    InlineKeyboardButton(text="رد پرداخت ❌", callback_data=f"adm_pay_decline_{payment_id}")
                ],
                [
                    InlineKeyboardButton(text="اضافه کردن دستی موجودی 🔄", callback_data=f"adm_pay_manual_add_{payment_id}"),
                    InlineKeyboardButton(text="بلاک کردن کاربر 🔴", callback_data=f"adm_pay_block_user_{payment_id}")
                ]
            ])
            
            import html
            
            # Fetch user details
            user_username = user.username or "N/A"
            user_fullname = user.username or f"User {user.id}"
                
            service_username = "N/A (شارژ کیف پول)"
            product_name = "N/A (شارژ کیف پول)"
            volume = "N/A"
            
            if payment.server_id:
                service_prefix = settings.SSH_VPN_USERNAME_PREFIX if payment.service_type == ACCOUNT_TYPE_SSH else settings.REMOTE_VPN_USERNAME_PREFIX
                service_username = f"{service_prefix}10xx"
                    
                from app.services.pricing import PLAN_PRICES_TOMAN
                plan_id = None
                for pid, pprice in PLAN_PRICES_TOMAN.items():
                    if int(payment.amount) == pprice:
                        plan_id = pid
                        break
                
                product_name = f"{service_type_label(payment.service_type)} - {get_plan_title(plan_id)}"
                volume = get_plan_volume_label(plan_id)
            
            payment_meta = decode_payment_metadata(payment.gateway_tx_id)
            payable_toman = payment_meta["payable_toman"]
            payment_amount_line = f"مبلغ پرداختی: {int(payment.amount):,} تومان 💸"
            if isinstance(payable_toman, int) and payable_toman != int(payment.amount):
                payment_amount_line = (
                    f"مبلغ سرویس/شارژ: {int(payment.amount):,} تومان 💸\n"
                    f"مبلغ قابل پرداخت با تخفیف: {payable_toman:,} تومان 🏷"
                )

            msg = (
                "🔴 یک پرداخت جدید انجام شده است .\n\n"
                "🔘🔘🔘🔘🔘\n\n"
                "خرید سرویس جدید\n"
                f"نام کاربری سرویس :\n<code>{html.escape(service_username)}</code>\n"
                f"نام محصول : {html.escape(product_name)}\n"
                f"({volume})1Month\n"
                f"حجم محصول : {volume}\n"
                "زمان محصول : 30 روز\n"
                f"نام اکانت کاربر : {html.escape(user_fullname)} 👤\n"
                f"شناسه کاربر: <code>{user.id}</code> 👤\n"
                f"موجودی فعلی کاربر : {int(user.balance):,} تومان 💸\n"
                f"کد پیگیری پرداخت: <code>{payment.id}</code> 🛒\n"
                f"نام کاربری: @{html.escape(user_username)} ⚜️\n"
                f"{payment_amount_line}\n\n"
                "توضیحات:\n"
                "✍️ در صورت درست بودن رسید پرداخت را تایید نمایید."
            )
            
            group_id = get_manager_group_id()
            topic_id = get_topic_id("payments")
            
            file_id = payment_meta["base_ref"]
            is_doc = False
            if file_id:
                if ":" in file_id:
                    prefix, file_id = file_id.split(":", 1)
                    if prefix == "doc":
                        is_doc = True

            if group_id and topic_id:
                try:
                    await _send_payment_notification(group_id, msg, kb, file_id, is_doc, message_thread_id=topic_id)
                except Exception as e:
                    logger.error(f"Failed to notify payment topic {group_id}/{topic_id}: {e}")
            elif group_id:
                try:
                    await _send_payment_notification(group_id, msg, kb, file_id, is_doc)
                except Exception as e:
                    logger.error(f"Failed to notify manager group {group_id}: {e}")

    except Exception as e:
        logger.error(f"Error in notify_admins_of_pending_payment for payment {payment_id}: {e}", exc_info=True)

async def _notify_admins_of_provisioning_failure(payment_id: int, error_details: str):
    try:
        group_id = get_manager_group_id()
        topic_id = get_topic_id("payments")
        msg = (
            f"🔴 <b>خطای Provisioning:</b>\n\n"
            f"کد پرداخت: <code>{payment_id}</code>\n"
            f"وضعیت: پرداخت تایید شده است، اما فعال‌سازی سرویس با خطا مواجه شد.\n\n"
            f"جزئیات خطا:\n<code>{error_details}</code>\n\n"
            f"برای تلاش مجدد از دکمه «تلاش مجدد فعال‌سازی» یا پنل مدیریت استفاده کنید."
        )
        if group_id and topic_id:
            await _get_bot().send_message(chat_id=group_id, message_thread_id=topic_id, text=msg)
        elif group_id:
            await _get_bot().send_message(chat_id=group_id, text=msg)
    except Exception as e:
        logger.error(f"Failed to notify admins of provisioning failure for payment {payment_id}: {e}")


async def _activate_service_for_payment(session, payment: Payment, user: User) -> tuple[bool, str]:
    server = await session.get(SshServer, payment.server_id)
    if not server:
        payment.status = PAYMENT_STATUS_PROVISIONING_FAILED
        await session.commit()
        return False, "server_not_found"

    from app.services.pricing import PLAN_PRICES_TOMAN
    plan_id = None
    for pid, pprice in PLAN_PRICES_TOMAN.items():
        if int(payment.amount) == pprice:
            plan_id = pid
            break

    gb_limit = get_plan_data_limit_gb(plan_id) if plan_id else None
    max_connections = get_plan_max_connections(plan_id) if plan_id else 1

    try:
        # Always create a FRESH, EXCLUSIVE account for this buyer and this payment.
        # Even if the buyer already has active services, this produces a brand-new
        # unique ssh_username, password, and import_link tied only to them.
        account, import_link = await create_remote_account(
            session=session,
            user_id=user.id,
            server_id=server.id,
            duration_days=30,
            max_connections=max_connections,
            data_limit_gb=gb_limit,
            payment_id=payment.id,  # FK trace: Payment → SshAccount
            service_type=payment.service_type or server.service_type or ACCOUNT_TYPE_V2RAY,
        )

        # Direct service purchases (card/crypto) should not touch wallet balance.
        # Wallet-only purchases are handled separately in execute_payment_approval().
        payment.status = PAYMENT_STATUS_COMPLETED
        await session.commit()

    except Exception as provision_err:
        logger.error(f"SSH provisioning failed for payment {payment.id}: {provision_err}")
        payment.status = PAYMENT_STATUS_PROVISIONING_FAILED
        await session.commit()

        capacity_msg = (
            "⚠️ <b>پرداخت شما تایید شد!</b>\n\n"
            "پرداخت شما در سیستم ثبت شد اما به دلیل اختلال ارتباطی با سرور، "
            "فعال‌سازی خودکار انجام نشد.\n"
            "نیازی به پرداخت مجدد نیست — مدیریت به زودی سرویس را فعال می‌کند."
        )
        try:
            await _get_bot().send_message(chat_id=user.id, text=capacity_msg)
        except Exception as e:
            logger.error(f"Failed to send SSH fail msg to user: {e}")

        return False, f"ssh_error:{str(provision_err)}"

    connection = get_connection_details(
        account.ssh_username,
        account.ssh_password,
        service_type=account.service_type,
    )

    success_text = (
        f"✅ <b>سرویس شما با موفقیت فعال و ارسال شد!</b>\n\n"
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
    try:
        await _get_bot().send_message(chat_id=user.id, text=success_text)
    except Exception as e:
        logger.error(f"Failed to send success msg to user: {e}")

    return True, "auto_activated"


async def execute_payment_approval(payment_id: int) -> tuple[bool, str]:
    """
    Executes the payment approval.
    - Wallet-only payments: credits balance immediately and notifies user.
    - Service purchases: delegates to _activate_service_for_payment which
      provisions the SSH account and handles balance deduction atomically.
    Returns (success_bool, result_type).
    """
    try:
        async with async_session_maker() as session:
            # 1. Lock state to processing (idempotency guard)
            payment = await session.get(Payment, payment_id)
            if not payment or payment.status != PAYMENT_STATUS_PENDING:
                return False, "invalid"

            payment.status = PAYMENT_STATUS_PROCESSING
            await session.commit()

            # 2. Fetch user
            user = await session.get(User, payment.user_id)
            if not user:
                payment.status = PAYMENT_STATUS_FAILED
                await session.commit()
                return False, "user_not_found"

            payment_meta = decode_payment_metadata(payment.gateway_tx_id)
            discount_code = payment_meta.get("discount_code")

            # 3a. SERVICE PURCHASE — delegate entirely to _activate_service_for_payment.
            #     That function handles provisioning + balance deduction atomically.
            #     Do NOT add balance here (it would be subtracted again by the function).
            if payment.server_id:
                await mark_discount_code_as_used(
                    session,
                    discount_code if isinstance(discount_code, str) else None,
                    user_id=user.id,
                    payment_id=payment.id,
                )
                await session.commit()
                return await _activate_service_for_payment(session, payment, user)

            # 3b. WALLET-ONLY RECHARGE — credit balance immediately.
            user.balance = float(user.balance or 0.0) + float(payment.amount)
            payment.status = PAYMENT_STATUS_COMPLETED
            await mark_discount_code_as_used(
                session,
                discount_code if isinstance(discount_code, str) else None,
                user_id=user.id,
                payment_id=payment.id,
            )
            await session.commit()

            recharge_msg = (
                "✅ <b>پرداخت شما تایید شد!</b>\n\n"
                f"💰 کیف پول شما با موفقیت شارژ گردید.\n"
                f"💵 مبلغ شارژ: <code>{int(payment.amount):,}</code> تومان\n"
                f"💳 موجودی جدید: <code>{int(user.balance):,}</code> تومان\n\n"
                "هم‌اکنون می‌توانید از بخش «خرید اشتراک» نسبت به تهیه سرویس خود اقدام کنید."
            )
            try:
                await _get_bot().send_message(chat_id=user.id, text=recharge_msg)
            except Exception as e:
                logger.error(f"Failed to send success msg to user: {e}")

            return True, "wallet_only"

    except Exception as e:
        logger.error(f"Wallet recharge pipeline error: {e}")
        return False, f"error: {str(e)}"


async def execute_manual_balance_credit(payment_id: int) -> tuple[bool, str, int | None, int | None]:
    """
    Credits the user's wallet with the exact recorded payment amount and marks
    the payment completed without service provisioning.
    """
    try:
        async with async_session_maker() as session:
            payment = await session.get(Payment, payment_id)
            if not payment or payment.status != PAYMENT_STATUS_PENDING:
                return False, "invalid", None, None

            user = await session.get(User, payment.user_id)
            if not user:
                payment.status = PAYMENT_STATUS_FAILED
                await session.commit()
                return False, "user_not_found", None, None

            payment_meta = decode_payment_metadata(payment.gateway_tx_id)
            discount_code = payment_meta.get("discount_code")

            credited_amount = int(payment.amount)
            user.balance = float(user.balance or 0.0) + float(payment.amount)
            payment.status = PAYMENT_STATUS_COMPLETED
            await mark_discount_code_as_used(
                session,
                discount_code if isinstance(discount_code, str) else None,
                user_id=user.id,
                payment_id=payment.id,
            )
            await session.commit()

            current_balance = int(user.balance)
            try:
                await _get_bot().send_message(
                    chat_id=user.id,
                    text=(
                        "✅ <b>پرداخت شما به صورت دستی توسط مدیریت شارژ شد.</b>\n\n"
                        f"💵 مبلغ شارژ: <code>{credited_amount:,}</code> تومان\n"
                        f"💳 موجودی جدید: <code>{current_balance:,}</code> تومان"
                    ),
                )
            except Exception as notify_err:
                logger.error(f"Failed to notify user {user.id} of manual balance credit: {notify_err}")

            return True, "wallet_manually_credited", credited_amount, current_balance
    except Exception as e:
        logger.error(f"Error in execute_manual_balance_credit for payment {payment_id}: {e}", exc_info=True)
        return False, "error", None, None



async def retry_payment_activation(payment_id: int) -> tuple[bool, str]:
    try:
        async with async_session_maker() as session:
            payment = await session.get(Payment, payment_id)
            if not payment:
                return False, "not_found"
            if payment.status != PAYMENT_STATUS_PROVISIONING_FAILED:
                return False, "not_retryable"
            if not payment.server_id:
                return False, "wallet_payment"

            user = await session.get(User, payment.user_id)
            if not user:
                payment.status = PAYMENT_STATUS_FAILED
                await session.commit()
                return False, "user_not_found"

            payment.status = PAYMENT_STATUS_PROCESSING
            await session.commit()

            success, result_type = await _activate_service_for_payment(session, payment, user)
            if not success and result_type.startswith("ssh_error:"):
                await _notify_admins_of_provisioning_failure(payment_id, result_type.split(":", 1)[1])
            return success, result_type
    except Exception as e:
        logger.error(f"Payment activation retry error for {payment_id}: {e}")
        return False, f"error:{str(e)}"


async def execute_payment_decline(payment_id: int) -> bool:
    try:
        async with async_session_maker() as session:
            payment = await session.get(Payment, payment_id)
            if not payment or payment.status not in [PAYMENT_STATUS_PENDING, PAYMENT_STATUS_PROCESSING]:
                return False
                
            payment.status = PAYMENT_STATUS_FAILED
            user = await session.get(User, payment.user_id)
            await session.commit()
            
            if user:
                try:
                    await _get_bot().send_message(chat_id=user.id, text=Lexicon.PAYMENT_ERROR)
                except Exception:
                    pass
            return True
    except Exception as e:
        logger.error(f"Error in execute_payment_decline for payment {payment_id}: {e}", exc_info=True)
        return False
