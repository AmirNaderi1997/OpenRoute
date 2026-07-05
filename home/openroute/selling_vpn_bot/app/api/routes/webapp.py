import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, File, UploadFile, Form
from typing import Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from app.bot import bot
from app.db.database import async_session_maker
from app.db.models import SshAccount, User, SupportTicket, TicketMessage, Payment, SshServer
from app.api.dependencies.webapp_auth import webapp_auth
from app.core.config import settings
from app.core.topics_manager import get_manager_group_id, get_topic_id
from app.services.account_types import ACCOUNT_TYPE_V2RAY, service_type_label
from app.services.connection_links import get_connection_details
from app.services.nowpayments import create_nowpayments_invoice, TOMAN_TO_USD_RATE
from app.services.pricing import (
    get_plan_service_type,
    discount_failure_message,
    encode_payment_metadata,
    get_discount_preview,
    get_plan_price_toman,
    get_plan_price_usd,
    get_plan_title,
    get_plan_volume_label,
    normalize_discount_code,
)

router = APIRouter()

ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/gif", "image/bmp", "image/tiff", "image/heic", "image/heif",
}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif"}

# --- Schemas ---
class CreateTicketRequest(BaseModel):
    subject: str
    message: str

class CreateMessageRequest(BaseModel):
    text: str

class PlanPurchaseRequest(BaseModel):
    plan_id: int
    server_id: int | None = None
    discount_code: str | None = None


class PublicPlanCryptoRequest(BaseModel):
    telegram_identifier: str
    plan_id: int
    discount_code: str | None = None

class CryptoRechargeRequest(BaseModel):
    amount: float | None = None
    amount_usd: float | None = None
    discount_code: str | None = None


class DiscountPreviewRequest(BaseModel):
    amount: int | None = None
    amount_usd: float | None = None
    plan_id: int | None = None
    discount_code: str
    payment_method: str | None = None


async def ensure_user_exists(user_data: dict) -> User:
    user_id = user_data.get("id")
    username = user_data.get("username")
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if user:
            if username and user.username != username:
                user.username = username
                await session.commit()
            return user

        user = User(id=user_id, username=username)
        session.add(user)
        await session.commit()
        return user


async def _get_default_shop_server(session, service_type: str = ACCOUNT_TYPE_V2RAY) -> SshServer:
    server = await session.scalar(
        select(SshServer)
        .where(SshServer.status == "active", SshServer.service_type == service_type)
        .order_by(SshServer.id.asc())
        .limit(1)
    )
    if not server:
        raise HTTPException(status_code=400, detail="در حال حاضر هیچ سرور فعالی برای فروش موجود نیست.")
    return server


def _raise_discount_http_error(preview: Dict[str, Any]) -> None:
    raise HTTPException(
        status_code=400,
        detail=discount_failure_message(str(preview.get("failure_reason"))),
    )


def _looks_like_supported_image(file_bytes: bytes) -> bool:
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return True
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if file_bytes.startswith((b"GIF87a", b"GIF89a")):
        return True
    if file_bytes.startswith(b"BM"):
        return True
    if file_bytes[:4] in (b"II*\x00", b"MM\x00*"):
        return True
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return True
    if len(file_bytes) >= 12 and file_bytes[4:8] == b"ftyp":
        brand = file_bytes[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return True
    return False

async def notify_new_ticket(ticket_id: int, user_id: int, subject: str, text: str):
    try:
        group_id = get_manager_group_id()
        topic_id = get_topic_id("tickets")
        
        async with async_session_maker() as session:
            user = await session.get(User, user_id)
            admins = (await session.scalars(select(User).where(User.is_admin == True))).all()
            
        import html
        if user and user.username:
            user_display = f"@{html.escape(user.username)}"
        else:
            user_display = f"<code>{user_id}</code> (بدون نام کاربری)"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from app.core.config import settings
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✍️ پاسخ به تیکت", url=f"https://t.me/{settings.BOT_USERNAME}?start=reply_ticket_{ticket_id}")
            ]
        ])
        
        alert_text = (
            f"🎫 <b>تیکت جدید (وب‌اپ)</b>\n\n"
            f"👤 کاربر: {user_display}\n"
            f"📝 موضوع: {html.escape(subject)}\n\n"
            f"پیام: {html.escape(text)}"
        )
        
        sent_to_group = False
        if group_id:
            try:
                if topic_id:
                    try:
                        await bot.send_message(chat_id=group_id, message_thread_id=topic_id, text=alert_text, reply_markup=kb)
                    except Exception as e:
                        logging.getLogger("webapp").warning(
                            f"Ticket topic delivery failed; retrying manager group: {e}"
                        )
                        await bot.send_message(chat_id=group_id, text=alert_text, reply_markup=kb)
                else:
                    await bot.send_message(chat_id=group_id, text=alert_text, reply_markup=kb)
                sent_to_group = True
            except Exception as e:
                logging.getLogger("webapp").error(f"Failed to send ticket notification to group {group_id}: {e}")
                
        if not sent_to_group:
            for admin in admins:
                if admin.id:
                    try:
                        await bot.send_message(chat_id=admin.id, text=alert_text, reply_markup=kb)
                    except Exception as e:
                        logging.getLogger("webapp").error(f"Failed to notify admin fallback {admin.id}: {e}")
    except Exception as e:
        logging.getLogger("webapp").error(f"Error in notify_new_ticket: {e}", exc_info=True)

async def notify_ticket_reply(user_id: int, ticket_id: int, text: str):
    try:
        group_id = get_manager_group_id()
        topic_id = get_topic_id("tickets")
        
        async with async_session_maker() as session:
            user = await session.get(User, user_id)
            ticket = await session.get(SupportTicket, ticket_id)
            admins = (await session.scalars(select(User).where(User.is_admin == True))).all()
            
        subj = ticket.subject if ticket else "نامشخص"
        import html
        if user and user.username:
            user_display = f"@{html.escape(user.username)}"
        else:
            user_display = f"<code>{user_id}</code> (بدون نام کاربری)"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from app.core.config import settings
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✍️ پاسخ به تیکت", url=f"https://t.me/{settings.BOT_USERNAME}?start=reply_ticket_{ticket_id}")
            ]
        ])
        
        alert_text = (
            f"💬 <b>پاسخ جدید کاربر (وب‌اپ)</b>\n\n"
            f"👤 کاربر: {user_display}\n"
            f"📝 تیکت: {html.escape(subj)}\n\n"
            f"پیام: {html.escape(text)}"
        )
        
        sent_to_group = False
        if group_id:
            try:
                if topic_id:
                    try:
                        await bot.send_message(chat_id=group_id, message_thread_id=topic_id, text=alert_text, reply_markup=kb)
                    except Exception as e:
                        logging.getLogger("webapp").warning(
                            f"Ticket reply topic delivery failed; retrying manager group: {e}"
                        )
                        await bot.send_message(chat_id=group_id, text=alert_text, reply_markup=kb)
                else:
                    await bot.send_message(chat_id=group_id, text=alert_text, reply_markup=kb)
                sent_to_group = True
            except Exception as e:
                logging.getLogger("webapp").error(f"Failed to send ticket reply notification to group {group_id}: {e}")
                
        if not sent_to_group:
            for admin in admins:
                if admin.id:
                    try:
                        await bot.send_message(chat_id=admin.id, text=alert_text, reply_markup=kb)
                    except Exception as e:
                        logging.getLogger("webapp").error(f"Failed to notify admin fallback {admin.id}: {e}")
    except Exception as e:
        logging.getLogger("webapp").error(f"Error in notify_ticket_reply: {e}", exc_info=True)

# --- Endpoints ---

@router.get("/dashboard")
async def get_dashboard(user_data: dict = Depends(webapp_auth)) -> Dict[str, Any]:
    """
    Returns the user's active SSH accounts and wallet balance.
    Requires validated Telegram Web App Data.
    """
    user_id = user_data.get("id")
    
    async with async_session_maker() as session:
        # Fetch user
        user = await session.get(User, user_id)
        balance = user.balance if user else 0.0
        
        # Fetch active accounts
        accounts_query = await session.scalars(
            select(SshAccount)
            .options(selectinload(SshAccount.server))
            .where(SshAccount.user_id == user_id, SshAccount.status == "active")
        )
        accounts = accounts_query.all()
        
        accounts_data = []
        for acc in accounts:
            connection = get_connection_details(acc.ssh_username, acc.ssh_password, service_type=acc.service_type)
            accounts_data.append({
                "id": acc.id,
                "username": acc.ssh_username,
                "service_type": acc.service_type,
                "service_label": service_type_label(acc.service_type),
                "ssh_password": acc.ssh_password,
                "uuid_token": None,
                "import_link": f"{settings.APP_BASE_URL.rstrip('/')}/sub/{acc.ssh_username}" if acc.service_type == ACCOUNT_TYPE_V2RAY else acc.import_link or connection["import_link"],
                "connection_host": connection["host"],
                "connection_port": connection["port"],
                "connection_path": connection["path"],
                "connection_security": connection["security"],
                "server_id": acc.server_id,
                "traffic_used_gb": float(acc.traffic_used_gb),
                "traffic_limit_gb": acc.traffic_limit_gb,
                "expires_at": acc.expires_at.isoformat()
            })

        available_servers = (await session.scalars(
            select(SshServer)
            .where(SshServer.status == "active")
            .order_by(SshServer.service_type.asc(), SshServer.id.asc())
        )).all()
        
    return {
        "status": "success",
        "user_id": user_id,
        "balance": float(balance),
        "accounts": accounts_data,
        "available_servers": [
            {
                "id": server.id,
                "name": server.name,
                "ip_address": server.ip_address,
                "ssh_port": server.ssh_port,
                "service_type": server.service_type,
                "service_label": service_type_label(server.service_type),
            }
            for server in available_servers
        ],
    }

@router.get("/tickets")
async def get_user_tickets(user_data: dict = Depends(webapp_auth)) -> Dict[str, Any]:
    user_id = user_data.get("id")
    async with async_session_maker() as session:
        tickets_query = await session.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.updated_at.desc())
        )
        tickets = tickets_query.all()
        
        return {
            "tickets": [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "status": t.status,
                    "updated_at": t.updated_at.isoformat()
                }
                for t in tickets
            ]
        }

@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_user_ticket(req: CreateTicketRequest, background_tasks: BackgroundTasks, user_data: dict = Depends(webapp_auth)) -> Dict[str, Any]:
    user_id = user_data.get("id")
    async with async_session_maker() as session:
        ticket = SupportTicket(
            user_id=user_id,
            subject=req.subject,
            status="open"
        )
        session.add(ticket)
        await session.flush() # Populate ticket.id
        
        first_msg = TicketMessage(
            ticket_id=ticket.id,
            sender="user",
            text=req.message
        )
        session.add(first_msg)
        await session.commit()
        
        background_tasks.add_task(notify_new_ticket, ticket.id, user_id, req.subject, req.message)
        
        return {
            "status": "success",
            "ticket_id": ticket.id
        }

@router.get("/tickets/{ticket_id}/messages")
async def get_ticket_messages(ticket_id: int, user_data: dict = Depends(webapp_auth)) -> Dict[str, Any]:
    user_id = user_data.get("id")
    async with async_session_maker() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.user_id != user_id:
            raise HTTPException(status_code=404, detail="تیکت یافت نشد")
            
        messages_query = await session.scalars(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at.asc())
        )
        messages = messages_query.all()
        
        return {
            "ticket": {
                "id": ticket.id,
                "subject": ticket.subject,
                "status": ticket.status
            },
            "messages": [
                {
                    "id": m.id,
                    "sender": m.sender,
                    "text": m.text,
                    "created_at": m.created_at.isoformat()
                }
                for m in messages
            ]
        }

@router.post("/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
async def reply_to_ticket(ticket_id: int, req: CreateMessageRequest, background_tasks: BackgroundTasks, user_data: dict = Depends(webapp_auth)) -> Dict[str, Any]:
    user_id = user_data.get("id")
    async with async_session_maker() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.user_id != user_id:
            raise HTTPException(status_code=404, detail="تیکت یافت نشد")
            
        # Re-open if resolved or change status
        ticket.status = "open"
        
        reply = TicketMessage(
            ticket_id=ticket_id,
            sender="user",
            text=req.text
        )
        session.add(reply)
        await session.commit()
        
        background_tasks.add_task(notify_ticket_reply, user_id, ticket_id, req.text)
        
        return {
            "status": "success",
            "message_id": reply.id
        }


@router.post("/payments/discount/preview")
async def discount_preview(req: DiscountPreviewRequest, user_data: dict = Depends(webapp_auth)) -> Dict[str, Any]:
    await ensure_user_exists(user_data)

    original_toman: int | None = None
    original_usd: float | None = None
    if req.plan_id is not None:
        original_toman = get_plan_price_toman(req.plan_id)
        original_usd = get_plan_price_usd(req.plan_id)
    elif req.amount_usd is not None:
        original_usd = round(float(req.amount_usd), 2)
        original_toman = int(round(original_usd * TOMAN_TO_USD_RATE))
    elif req.amount is not None:
        original_toman = int(req.amount)
    else:
        raise HTTPException(status_code=400, detail="مبلغ یا پلن ارسال نشده است.")

    async with async_session_maker() as session:
        preview = await get_discount_preview(
            session,
            original_toman=original_toman,
            original_usd=original_usd,
            discount_code=req.discount_code,
            payment_method=req.payment_method,
        )

    if not preview["discount_applied"]:
        _raise_discount_http_error(preview)

    return {
        "status": "success",
        "discount_code": preview["discount_code"],
        "percent_off": preview["percent_off"],
        "original_toman": preview["original_toman"],
        "original_usd": preview["original_usd"],
        "payable_toman": preview["payable_toman"],
        "payable_usd": preview["payable_usd"],
    }

@router.post("/payments/charge")
async def webapp_recharge_payment(
    amount: int | None = Form(None),
    plan_id: int | None = Form(None),
    server_id: int | None = Form(None),
    discount_code: str | None = Form(None),
    file: UploadFile = File(...),
    user_data: dict = Depends(webapp_auth)
) -> Dict[str, Any]:
    user_id = user_data.get("id")
    await ensure_user_exists(user_data)

    payment_amount = amount
    payable_amount = amount
    payment_server_id = None
    payment_service_type = None
    product_name = "N/A (شارژ کیف پول - وب‌اپ)"
    service_username = "N/A (شارژ کیف پول - وب‌اپ)"
    volume = "N/A"
    normalized_discount_code = normalize_discount_code(discount_code)

    async with async_session_maker() as session:
        if plan_id is not None:
            payment_amount = get_plan_price_toman(plan_id)
            payable_amount = payment_amount
            if server_id is not None:
                server = await session.get(SshServer, server_id)
            else:
                server = await _get_default_shop_server(session, service_type=get_plan_service_type(plan_id))
            if not server:
                raise HTTPException(status_code=400, detail="سرور انتخابی یافت نشد.")
            payment_server_id = server.id
            payment_service_type = server.service_type
            product_name = f"{service_type_label(payment_service_type)} - {get_plan_title(plan_id)}"
            volume = get_plan_volume_label(plan_id)
        else:
            payable_amount = payment_amount

        preview = await get_discount_preview(
            session,
            original_toman=payment_amount,
            discount_code=normalized_discount_code,
            payment_method="card_to_card",
        )
        if normalized_discount_code and not preview["discount_applied"]:
            _raise_discount_http_error(preview)
        payable_amount = int(preview["payable_toman"] or payment_amount or 0)

    if payment_amount is None or payment_amount <= 0:
        raise HTTPException(status_code=400, detail="مبلغ وارد شده نامعتبر است.")
    
    # 1. Validate file is an image (screenshot only — no PDFs, ZIPs, etc.)
    uploaded_mime = (file.content_type or "").lower()
    uploaded_ext = ""
    if file.filename:
        import os as _os
        uploaded_ext = _os.path.splitext(file.filename.lower())[1]
    
    if uploaded_mime not in ALLOWED_IMAGE_MIME_TYPES and uploaded_ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="فقط تصویر (اسکرین‌شات) رسید پرداخت قابل قبول است. فایل‌های PDF و سایر فرمت‌ها پذیرفته نمی‌شوند."
        )

    # 2. Read file bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="رسید خالی یا نامعتبر است.")
    if not _looks_like_supported_image(file_bytes):
        raise HTTPException(
            status_code=400,
            detail="فقط فایل تصویری واقعی برای رسید پرداخت پذیرفته می‌شود."
        )
        
    # 2. Upload file to Telegram using the bot instance
    from aiogram.types import BufferedInputFile
    
    try:
        group_id = get_manager_group_id()
        topic_id = get_topic_id("payments")
        
        # Determine filename (always an image now)
        filename = file.filename or "receipt.jpg"
        # Ensure extension is valid; default to .jpg if unrecognised
        _fn_lower = filename.lower()
        if not any(_fn_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".heic", ".heif")):
            filename = "receipt.jpg"

        # We will create a pending payment in PostgreSQL
        async with async_session_maker() as session:
            payment = Payment(
                user_id=user_id,
                server_id=payment_server_id,
                amount=payment_amount,
                payment_method="card_to_card",
                status="pending",
                service_type=payment_service_type,
            )
            session.add(payment)
            await session.flush()  # Populate payment.id
            payment_id = payment.id
            await session.commit()
            
        # Create the admin keyboard & message details
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
        async with async_session_maker() as session:
            db_user = await session.get(User, user_id)
            user_username = db_user.username or "N/A"
            user_balance = db_user.balance
            
        user_fullname = "Unknown"
        try:
            chat = await bot.get_chat(user_id)
            user_fullname = chat.full_name or "Unknown"
        except Exception:
            user_fullname = user_username
            
        discount_line = (
            f"مبلغ قابل پرداخت با کد {normalized_discount_code}: {payable_amount:,} تومان 🏷\n\n"
            if normalized_discount_code and payable_amount != payment_amount
            else "\n"
        )
        msg = (
            "🔴 یک پرداخت جدید انجام شده است .\n\n"
            "🔘🔘🔘🔘🔘\n\n"
            "خرید سرویس جدید\n"
            f"نام کاربری سرویس :\n<code>{service_username}</code>\n"
            f"نام محصول : {product_name}\n"
            f"({volume})1Month\n"
            f"حجم محصول : {volume}\n"
            "زمان محصول : 30 روز\n"
            f"نام اکانت کاربر : {html.escape(user_fullname)} 👤\n"
            f"شناسه کاربر: <code>{user_id}</code> 👤\n"
            f"موجودی فعلی کاربر : {int(user_balance):,} تومان 💸\n"
            f"کد پیگیری پرداخت: <code>{payment_id}</code> 🛒\n"
            f"نام کاربری: @{html.escape(user_username)} ⚜️\n"
            f"مبلغ سرویس/شارژ: {payment_amount:,} تومان 💸\n"
            f"{discount_line}"
            "توضیحات:\n"
            "✍️ در صورت درست بودن رسید پرداخت را تایید نمایید."
        )
        
        telegram_msg = None
        sent_to_group = False
        logger = logging.getLogger("webapp_payments")

        async def _try_send(thread_id):
            """Send receipt strictly as a photo so only screenshot images are accepted."""
            nonlocal telegram_msg
            telegram_msg = await bot.send_photo(
                chat_id=group_id,
                message_thread_id=thread_id,
                photo=BufferedInputFile(file_bytes, filename=filename),
                caption=msg,
                reply_markup=kb
            )

        if group_id:
            # Try with topic first, then without if topic fails or is not set
            if topic_id:
                try:
                    await _try_send(topic_id)
                    sent_to_group = True
                except Exception as e:
                    logger.error(f"Failed to send to group topic {topic_id}: {e}")
                    # Fall back to group without topic
                    try:
                        await _try_send(None)
                        sent_to_group = True
                    except Exception as e2:
                        logger.error(f"Failed to send to group without topic: {e2}")
            else:
                try:
                    await _try_send(None)
                    sent_to_group = True
                except Exception as e:
                    logger.error(f"Failed to send to group: {e}")

        if not sent_to_group:
            raise HTTPException(status_code=500, detail="خطا در ارسال رسید به گروه مدیریت. لطفا بعداً مجدداً تلاش کنید.")

                        
        # Retrieve file_id from telegram_msg and save in DB
        file_id = None
        if telegram_msg and telegram_msg.photo:
            file_id = f"photo:{telegram_msg.photo[-1].file_id}"
                
        if file_id:
            async with async_session_maker() as session:
                payment = await session.get(Payment, payment_id)
                if payment:
                    payment.gateway_tx_id = encode_payment_metadata(
                        file_id,
                        payable_toman=payable_amount if payable_amount != payment_amount else None,
                        discount_code=normalized_discount_code if payable_amount != payment_amount else None,
                    )
                    await session.commit()
                    
        return {"status": "success", "message": "پرداخت با موفقیت ثبت شد و در انتظار تایید مدیریت است."}
        
    except HTTPException:
        if payment_id is not None:
            async with async_session_maker() as session:
                payment = await session.get(Payment, payment_id)
                if payment and payment.status == "pending":
                    payment.status = "failed"
                    await session.commit()
        raise
    except Exception as e:
        if payment_id is not None:
            async with async_session_maker() as session:
                payment = await session.get(Payment, payment_id)
                if payment and payment.status == "pending":
                    payment.status = "failed"
                    await session.commit()
        logging.getLogger("webapp_payments").error(f"Error handling webapp card payment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطا در ارتباط با تلگرام و ثبت رسید. لطفا مجددا تلاش کنید.")
    finally:
        pass  # shared bot session stays open


@router.post("/payments/charge/crypto")
async def webapp_recharge_crypto(
    req: CryptoRechargeRequest,
    user_data: dict = Depends(webapp_auth)
) -> Dict[str, Any]:
    user_id = user_data.get("id")
    await ensure_user_exists(user_data)

    if req.amount_usd is not None:
        original_usd = round(float(req.amount_usd), 2)
        amount_toman = int(round(original_usd * TOMAN_TO_USD_RATE))
        amount_usd = original_usd
    elif req.amount is not None:
        amount_toman = int(req.amount)
        original_usd = round(float(amount_toman) / TOMAN_TO_USD_RATE, 2)
        amount_usd = original_usd
    else:
        raise HTTPException(status_code=400, detail="مبلغ وارد شده نامعتبر است.")

    if amount_toman <= 0 or amount_usd <= 0:
        raise HTTPException(status_code=400, detail="مبلغ وارد شده باید بزرگتر از صفر باشد.")

    normalized_discount_code = normalize_discount_code(req.discount_code)
    async with async_session_maker() as session:
        preview = await get_discount_preview(
            session,
            original_toman=amount_toman,
            original_usd=amount_usd,
            discount_code=normalized_discount_code,
            payment_method="crypto",
        )
    if normalized_discount_code and not preview["discount_applied"]:
        _raise_discount_http_error(preview)
    payable_toman = int(preview["payable_toman"] or amount_toman)
    payable_usd = float(preview["payable_usd"] or amount_usd)
        
    # Create a pending payment record in PostgreSQL
    async with async_session_maker() as session:
        payment = Payment(
            user_id=user_id,
            server_id=None,
            amount=amount_toman,
            payment_method="crypto",
            status="pending",
            service_type="wallet",
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()
        
    invoice_url, invoice_id = await create_nowpayments_invoice(
        payable_toman,
        str(payment_id),
        order_description=f"v2rayBundlenesse wallet top-up #{payment_id}",
        price_amount_usd=payable_usd,
    )
    
    if not invoice_url:
        async with async_session_maker() as session:
            db_pay = await session.get(Payment, payment_id)
            if db_pay:
                db_pay.status = "failed"
                await session.commit()
        raise HTTPException(status_code=500, detail="خطا در ایجاد درگاه پرداخت NOWPayments. لطفا بعداً تلاش کنید.")
        
    async with async_session_maker() as session:
        db_pay = await session.get(Payment, payment_id)
        if db_pay:
            base_ref = f"nowpayments_invoice:{invoice_id}" if invoice_id else f"url:{invoice_url}"
            db_pay.gateway_tx_id = encode_payment_metadata(
                base_ref,
                payable_toman=payable_toman,
                payable_usd=payable_usd,
                discount_code=normalized_discount_code,
            )
            await session.commit()
            
    return {"status": "success", "url": invoice_url}


@router.post("/payments/plan/crypto")
async def webapp_plan_crypto_payment(
    req: PlanPurchaseRequest,
    user_data: dict = Depends(webapp_auth)
) -> Dict[str, Any]:
    user_id = user_data.get("id")
    await ensure_user_exists(user_data)

    amount_toman = get_plan_price_toman(req.plan_id)
    amount_usd = get_plan_price_usd(req.plan_id)
    normalized_discount_code = normalize_discount_code(req.discount_code)

    async with async_session_maker() as session:
        preview = await get_discount_preview(
            session,
            original_toman=amount_toman,
            original_usd=amount_usd,
            discount_code=normalized_discount_code,
            payment_method="crypto",
        )
        if normalized_discount_code and not preview["discount_applied"]:
            _raise_discount_http_error(preview)
        payable_toman = int(preview["payable_toman"] or amount_toman)
        payable_usd = float(preview["payable_usd"] or amount_usd)
        if req.server_id is not None:
            server = await session.get(SshServer, req.server_id)
        else:
            server = await _get_default_shop_server(session)
        if not server:
            raise HTTPException(status_code=400, detail="سرور انتخابی یافت نشد.")
        payment = Payment(
            user_id=user_id,
            server_id=server.id,
            amount=amount_toman,
            payment_method="crypto",
            status="pending",
            service_type=server.service_type,
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()

    invoice_url, invoice_id = await create_nowpayments_invoice(
        payable_toman,
        str(payment_id),
        order_description=f"v2rayBundlenesse plan purchase #{payment_id}",
        price_amount_usd=payable_usd,
    )

    if not invoice_url:
        async with async_session_maker() as session:
            db_pay = await session.get(Payment, payment_id)
            if db_pay:
                db_pay.status = "failed"
                await session.commit()
        raise HTTPException(status_code=500, detail="خطا در ایجاد درگاه پرداخت NOWPayments. لطفا بعداً تلاش کنید.")

    async with async_session_maker() as session:
        db_pay = await session.get(Payment, payment_id)
        if db_pay:
            base_ref = f"nowpayments_invoice:{invoice_id}" if invoice_id else f"url:{invoice_url}"
            db_pay.gateway_tx_id = encode_payment_metadata(
                base_ref,
                payable_toman=payable_toman,
                payable_usd=payable_usd,
                discount_code=normalized_discount_code,
            )
            await session.commit()

    return {"status": "success", "url": invoice_url}


@router.post("/payments/submit_receipt_public")
async def submit_receipt_public(
    telegram_identifier: str = Form(...),
    plan_id: int = Form(...),
    discount_code: str | None = Form(None),
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    # Clean identifier
    identifier = telegram_identifier.strip()
    user_id = None
    user_username = None

    # Try integer first
    try:
        user_id = int(identifier.replace("@", ""))
    except ValueError:
        user_username = identifier.replace("@", "").strip()

    async with async_session_maker() as session:
        db_user = None
        if user_id:
            db_user = await session.get(User, user_id)
            if not db_user:
                # Create the user automatically if they entered their Telegram ID
                db_user = User(id=user_id, username=None)
                session.add(db_user)
                await session.commit()
                # Re-fetch
                db_user = await session.get(User, user_id)
        elif user_username:
            db_user = await session.scalar(
                select(User).where(User.username.ilike(user_username))
            )
            if not db_user:
                raise HTTPException(
                    status_code=400,
                    detail="کاربری با این نام کاربری یافت نشد. لطفاً ابتدا ربات تلگرام ما (@getopenroutebot) را استارت کنید تا حساب شما ثبت شود، یا از شناسه عددی تلگرام خود استفاده کنید."
                )
            user_id = db_user.id
            user_username = db_user.username

    # Now we have user_id, let's process the plan
    payment_amount = get_plan_price_toman(plan_id)
    payable_amount = payment_amount
    payment_service_type = get_plan_service_type(plan_id)
    product_name = f"{service_type_label(payment_service_type)} - {get_plan_title(plan_id)}"
    volume = get_plan_volume_label(plan_id)

    async with async_session_maker() as session:
        server = await _get_default_shop_server(session, service_type=payment_service_type)
        if not server:
            raise HTTPException(status_code=500, detail="هیچ سرور فعالی برای این سرویس وجود ندارد.")
        payment_server_id = server.id

        normalized_discount_code = normalize_discount_code(discount_code)
        preview = await get_discount_preview(
            session,
            original_toman=payment_amount,
            discount_code=normalized_discount_code,
            payment_method="card_to_card",
        )
        if normalized_discount_code and not preview["discount_applied"]:
            _raise_discount_http_error(preview)
        payable_amount = int(preview["payable_toman"] or payment_amount or 0)

    if payment_amount is None or payment_amount <= 0:
        raise HTTPException(status_code=400, detail="مبلغ پلن نامعتبر است.")

    # Validate file is image
    uploaded_mime = (file.content_type or "").lower()
    uploaded_ext = ""
    if file.filename:
        import os as _os
        uploaded_ext = _os.path.splitext(file.filename.lower())[1]

    if uploaded_mime not in ALLOWED_IMAGE_MIME_TYPES and uploaded_ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="فقط تصویر (اسکرین‌شات) رسید پرداخت قابل قبول است."
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="رسید خالی یا نامعتبر است.")
    if not _looks_like_supported_image(file_bytes):
        raise HTTPException(
            status_code=400,
            detail="فقط فایل تصویری واقعی برای رسید پرداخت پذیرفته می‌شود."
        )

    # Save to DB
    payment_id = None
    try:
        async with async_session_maker() as session:
            payment = Payment(
                user_id=user_id,
                server_id=payment_server_id,
                amount=payment_amount,
                payment_method="card_to_card",
                status="pending",
                service_type=payment_service_type,
            )
            session.add(payment)
            await session.flush()
            payment_id = payment.id
            await session.commit()

        # Create admin buttons
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

        user_fullname = "Unknown"
        try:
            chat = await bot.get_chat(user_id)
            user_fullname = chat.full_name or "Unknown"
        except Exception:
            user_fullname = user_username or "N/A"

        discount_line = (
            f"مبلغ قابل پرداخت با کد {normalized_discount_code}: {payable_amount:,} تومان 🏷\n\n"
            if normalized_discount_code and payable_amount != payment_amount
            else "\n"
        )

        import html
        msg = (
            "🌐 <b>ثبت رسید پرداخت از وب‌سایت</b>\n\n"
            "🔘🔘🔘🔘🔘\n\n"
            f"نام محصول : {product_name}\n"
            f"({volume})1Month\n"
            f"حجم محصول : {volume}\n"
            f"نام اکانت کاربر : {html.escape(user_fullname)} 👤\n"
            f"شناسه کاربر: <code>{user_id}</code> 👤\n"
            f"کد پیگیری پرداخت: <code>{payment_id}</code> 🛒\n"
            f"نام کاربری: @{html.escape(user_username or 'N/A')} ⚜️\n"
            f"مبلغ سرویس/شارژ: {payment_amount:,} تومان 💸\n"
            f"{discount_line}"
            "توضیحات:\n"
            "✍️ پرداخت از طریق وب‌سایت ثبت شده است. در صورت صحت رسید پرداخت را تایید نمایید."
        )

        group_id = get_manager_group_id()
        topic_id = get_topic_id("payments")

        filename = file.filename or "receipt.jpg"
        if not any(filename.lower().endswith(ext) for ext in ALLOWED_IMAGE_EXTENSIONS):
            filename = "receipt.jpg"

        telegram_msg = None
        sent_to_group = False

        async def _try_send(thread_id):
            nonlocal telegram_msg
            from aiogram.types import BufferedInputFile
            telegram_msg = await bot.send_photo(
                chat_id=group_id,
                message_thread_id=thread_id,
                photo=BufferedInputFile(file_bytes, filename=filename),
                caption=msg,
                reply_markup=kb
            )

        if group_id:
            if topic_id:
                try:
                    await _try_send(topic_id)
                    sent_to_group = True
                except Exception:
                    pass
            if not sent_to_group:
                try:
                    await _try_send(None)
                    sent_to_group = True
                except Exception as e:
                    logging.getLogger("webapp_payments").error(f"Failed to send public payment notification: {e}")

        if not sent_to_group:
            raise HTTPException(status_code=500, detail="خطا در ارسال رسید به گروه مدیریت. لطفا بعداً مجدداً تلاش کنید.")

        file_id = None
        if telegram_msg and telegram_msg.photo:
            file_id = f"photo:{telegram_msg.photo[-1].file_id}"

        if file_id:
            async with async_session_maker() as session:
                payment = await session.get(Payment, payment_id)
                if payment:
                    payment.gateway_tx_id = encode_payment_metadata(
                        file_id,
                        payable_toman=payable_amount if payable_amount != payment_amount else None,
                        discount_code=normalized_discount_code if payable_amount != payment_amount else None,
                    )
                    await session.commit()

        return {
            "status": "success",
            "message": "رسید شما با موفقیت ثبت شد و برای تایید به مدیران ارسال گردید. پس از تایید، اکانت شما در تلگرام ارسال خواهد شد.",
            "payment_id": payment_id
        }

    except HTTPException:
        if payment_id is not None:
            async with async_session_maker() as session:
                payment = await session.get(Payment, payment_id)
                if payment and payment.status == "pending":
                    payment.status = "failed"
                    await session.commit()
        raise
    except Exception as e:
        if payment_id is not None:
            async with async_session_maker() as session:
                payment = await session.get(Payment, payment_id)
                if payment and payment.status == "pending":
                    payment.status = "failed"
                    await session.commit()
        logging.getLogger("webapp_payments").error(f"Error handling public card payment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="خطا در ارتباط با تلگرام و ثبت رسید. لطفا مجددا تلاش کنید.")





@router.post("/payments/plan/crypto/public")
async def public_plan_crypto_payment(
    req: PublicPlanCryptoRequest
) -> Dict[str, Any]:
    identifier = req.telegram_identifier.strip()
    user_id = None
    user_username = None

    try:
        user_id = int(identifier.replace("@", ""))
    except ValueError:
        user_username = identifier.replace("@", "").strip()

    async with async_session_maker() as session:
        db_user = None
        if user_id:
            db_user = await session.get(User, user_id)
            if not db_user:
                db_user = User(id=user_id, username=None, full_name=None, is_active=True, wallet_balance=0)
                session.add(db_user)
                await session.flush()
        elif user_username:
            result = await session.execute(select(User).where(User.username == user_username))
            db_user = result.scalar_one_or_none()
            if not db_user:
                raise HTTPException(
                    status_code=400,
                    detail="کاربری با این نام کاربری یافت نشد. لطفاً ابتدا ربات تلگرام ما (@getopenroutebot) را استارت کنید تا حساب شما ثبت شود، یا از شناسه عددی تلگرام خود استفاده کنید."
                )
        if not db_user:
             raise HTTPException(status_code=400, detail="شناسه تلگرام نامعتبر است.")
             
        user_id = db_user.id
        
        amount_toman = get_plan_price_toman(req.plan_id)
        amount_usd = get_plan_price_usd(req.plan_id)
        normalized_discount_code = normalize_discount_code(req.discount_code)

        preview = await get_discount_preview(
            session,
            original_toman=amount_toman,
            original_usd=amount_usd,
            discount_code=normalized_discount_code,
            payment_method="crypto",
        )
        if normalized_discount_code and not preview["discount_applied"]:
            _raise_discount_http_error(preview)
            
        payable_toman = int(preview["payable_toman"] or amount_toman)
        payable_usd = float(preview["payable_usd"] or amount_usd)
        
        server = await _get_default_shop_server(session)
        if not server:
            raise HTTPException(status_code=400, detail="سرور انتخابی یافت نشد.")
            
        payment = Payment(
            user_id=user_id,
            server_id=server.id,
            amount=amount_toman,
            payment_method="crypto",
            status="pending",
            service_type=server.service_type,
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()

    invoice_url, invoice_id = await create_nowpayments_invoice(
        payable_toman,
        str(payment_id),
        order_description=f"OpenRoute plan purchase #{payment_id}",
        price_amount_usd=payable_usd,
    )

    if not invoice_url:
        async with async_session_maker() as session:
            db_pay = await session.get(Payment, payment_id)
            if db_pay:
                db_pay.status = "failed"
                await session.commit()
        raise HTTPException(status_code=500, detail="خطا در ایجاد درگاه پرداخت NOWPayments. لطفا بعداً تلاش کنید.")

    async with async_session_maker() as session:
        db_pay = await session.get(Payment, payment_id)
        if db_pay:
            base_ref = f"nowpayments_invoice:{invoice_id}" if invoice_id else f"url:{invoice_url}"
            db_pay.gateway_tx_id = encode_payment_metadata(
                base_ref,
                payable_toman=payable_toman,
                payable_usd=payable_usd,
                discount_code=normalized_discount_code,
            )
            await session.commit()

    return {"status": "success", "url": invoice_url}

