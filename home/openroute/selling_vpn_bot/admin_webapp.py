import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, func
from typing import Dict, Any, List, Optional

from app.db.database import async_session_maker
from app.db.models import User, SshServer, SshAccount, Payment, SupportTicket, TicketMessage
from app.api.dependencies.webapp_auth import admin_webapp_required
from app.services.account_types import service_type_label
from app.services.ssh.remote_provisioner import RemoteProvisionerClient
from app.services.ssh_account_service import lock_remote_account, renew_remote_account
from app.services.pricing import decode_payment_metadata
from app.core.config import settings
from aiogram import Bot
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def _get_telegram_file_url(file_id: str) -> Optional[str]:
    """Fetch a downloadable HTTPS URL for a Telegram file_id."""
    try:
        from app.bot import bot
        file = await bot.get_file(file_id)
        token = settings.BOT_TOKEN
        return f"https://api.telegram.org/file/bot{token}/{file.file_path}"
    except Exception as e:
        logger.warning(f"Could not resolve Telegram file URL for {file_id}: {e}")
        return None


async def _extract_receipt_url(gateway_tx_id: Optional[str]) -> tuple[Optional[str], bool]:
    """
    Parse gateway_tx_id and return (receipt_url, is_document).
    Returns (None, False) if no image receipt is stored.
    """
    if not gateway_tx_id:
        return None, False
    meta = decode_payment_metadata(gateway_tx_id)
    base_ref = meta.get("base_ref") or ""
    if not base_ref:
        return None, False
    is_doc = False
    file_id = base_ref
    if ":" in base_ref:
        prefix, rest = base_ref.split(":", 1)
        if prefix == "photo":
            file_id = rest
        elif prefix == "doc":
            file_id = rest
            is_doc = True
        else:
            # Not a Telegram file reference (e.g. nowpayments_invoice or url)
            return None, False
    url = await _get_telegram_file_url(file_id)
    return url, is_doc

# Protect all routes in this router with admin_webapp_required
router = APIRouter(dependencies=[Depends(admin_webapp_required)])

# --- Schemas ---
class AddServerRequest(BaseModel):
    name: str
    ip_address: str
    ssh_port: int
    root_password: str

class ToggleAccountRequest(BaseModel):
    action: str  # "lock" or "unlock"

class BroadcastRequest(BaseModel):
    message: str

# --- Endpoints ---

@router.get("/stats")
async def get_system_stats() -> Dict[str, Any]:
    async with async_session_maker() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        active_accounts = await session.scalar(
            select(func.count(SshAccount.id)).where(SshAccount.status == "active")
        )
        total_bandwidth_gb = await session.scalar(
            select(func.sum(SshAccount.traffic_used_gb))
        ) or 0.0
        # Placeholder for revenue
        total_revenue = 0.0 
        
    return {
        "total_users": total_users,
        "active_ssh_accounts": active_accounts,
        "total_bandwidth_gb": float(total_bandwidth_gb),
        "total_revenue": total_revenue
    }

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

@router.get("/servers")
async def get_servers() -> List[Dict[str, Any]]:
    async with async_session_maker() as session:
        servers = (await session.scalars(select(SshServer))).all()
        
        result = []
        for srv in servers:
            # Count active accounts
            active_accs = await session.scalar(
                select(func.count(SshAccount.id)).where(SshAccount.server_id == srv.id, SshAccount.status == "active")
            )
            # Async Ping
            is_online = await ping_server(srv.ip_address, srv.ssh_port)
            
            result.append({
                "id": srv.id,
                "name": srv.name,
                "ip_address": srv.ip_address,
                "ssh_port": srv.ssh_port,
                "service_type": srv.service_type,
                "service_label": service_type_label(srv.service_type),
                "status": "Online" if is_online else "Offline",
                "active_accounts": active_accs
            })
    return result

@router.post("/servers", status_code=status.HTTP_201_CREATED)
async def add_server(req: AddServerRequest) -> Dict[str, Any]:
    async with async_session_maker() as session:
        new_srv = SshServer(
            name=req.name,
            ip_address=req.ip_address,
            ssh_port=req.ssh_port,
            root_password=req.root_password,
            status="active"
        )
        session.add(new_srv)
        await session.commit()
        return {"status": "success", "server_id": new_srv.id}

@router.get("/users")
async def get_users(page: int = 1, limit: int = 10, search: str = "") -> Dict[str, Any]:
    offset = (page - 1) * limit
    async with async_session_maker() as session:
        query = select(User)
        if search:
            query = query.where(User.username.ilike(f"%{search}%"))
            
        total_count = await session.scalar(select(func.count()).select_from(query.subquery()))
        
        query = query.offset(offset).limit(limit)
        users = (await session.scalars(query)).all()
        
        users_data = []
        for u in users:
            accounts = (await session.scalars(
                select(SshAccount).where(SshAccount.user_id == u.id)
            )).all()
            acc_data = [{
                "id": a.id,
                "username": a.ssh_username,
                "service_type": a.service_type,
                "service_label": service_type_label(a.service_type),
                "status": a.status,
                "traffic_used_gb": float(a.traffic_used_gb),
                "traffic_limit_gb": a.traffic_limit_gb,
                "expires_at": a.expires_at.isoformat()
            } for a in accounts]
            
            users_data.append({
                "id": u.id,
                "username": u.username,
                "balance": float(u.balance),
                "accounts": acc_data
            })
            
    return {
        "total": total_count,
        "page": page,
        "limit": limit,
        "users": users_data
    }

@router.post("/accounts/{account_id}/toggle")
async def toggle_account(account_id: int, req: ToggleAccountRequest) -> Dict[str, Any]:
    if req.action not in ["lock", "unlock"]:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    async with async_session_maker() as session:
        account = await session.get(SshAccount, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
            
        if req.action == "lock":
            await lock_remote_account(session, account)
            account.status = "locked"
        else:
            await renew_remote_account(session, account, duration_days=30)
            
        await session.commit()
        return {"status": "success", "account_status": account.status}

from app.services.payment_pipeline import execute_payment_approval, execute_payment_decline, retry_payment_activation
from app.worker.backups import run_database_backup

@router.post("/backup/trigger")
async def trigger_backup() -> Dict[str, Any]:
    filepath = await run_database_backup()
    if filepath:
        return {"status": "success", "filepath": filepath}
    raise HTTPException(status_code=500, detail="Backup failed")

@router.post("/payments/{payment_id}/approve")
async def approve_payment(payment_id: int) -> Dict[str, Any]:
    success, result_type = await execute_payment_approval(payment_id)
    if success:
        return {"status": "success", "message": f"Payment approved: {result_type}"}
    raise HTTPException(status_code=400, detail="Failed to approve or already processed")

@router.post("/payments/{payment_id}/retry")
async def retry_payment(payment_id: int) -> Dict[str, Any]:
    success, result_type = await retry_payment_activation(payment_id)
    if success:
        return {"status": "success", "message": f"Payment activation retried: {result_type}"}
    raise HTTPException(status_code=400, detail=f"Payment activation retry failed: {result_type}")

@router.post("/payments/{payment_id}/decline")
async def decline_payment(payment_id: int) -> Dict[str, Any]:
    success = await execute_payment_decline(payment_id)
    if success:
        return {"status": "success", "message": "Payment declined"}
    raise HTTPException(status_code=400, detail="Failed to decline")

@router.get("/payments")
async def get_payments() -> Dict[str, Any]:
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(Payment, User, SshServer)
            .join(User, Payment.user_id == User.id)
            .outerjoin(SshServer, Payment.server_id == SshServer.id)
            .where(Payment.status.in_(["pending", "processing", "provisioning_failed"]))
            .order_by(Payment.created_at.desc())
            .limit(100)
        )).all()

        payments_list = []
        for payment, user, server in rows:
            receipt_url, receipt_is_doc = await _extract_receipt_url(payment.gateway_tx_id)
            payments_list.append({
                "id": payment.id,
                "user_id": payment.user_id,
                "username": user.username,
                "amount": float(payment.amount),
                "payment_method": payment.payment_method,
                "service_type": payment.service_type,
                "service_label": service_type_label(payment.service_type),
                "card_last_four": payment.card_last_four,
                "gateway_tx_id": payment.gateway_tx_id,
                "server_id": payment.server_id,
                "server_name": server.name if server else "شارژ کیف پول",
                "status": payment.status,
                "created_at": payment.created_at.isoformat(),
                "retryable": payment.status == "provisioning_failed" and payment.server_id is not None,
                "receipt_url": receipt_url,
                "receipt_is_doc": receipt_is_doc,
            })

        return {"payments": payments_list}


@router.get("/payments/{payment_id}/receipt")
async def get_payment_receipt(payment_id: int) -> Dict[str, Any]:
    """Returns the receipt file URL for a specific payment (admin only)."""
    async with async_session_maker() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="تراکنش یافت نشد")
    receipt_url, receipt_is_doc = await _extract_receipt_url(payment.gateway_tx_id)
    return {
        "payment_id": payment_id,
        "receipt_url": receipt_url,
        "receipt_is_doc": receipt_is_doc,
    }

@router.get("/tickets")
async def get_tickets() -> Dict[str, Any]:
    async with async_session_maker() as session:
        tickets = (await session.scalars(select(SupportTicket).order_by(SupportTicket.updated_at.desc()))).all()
        return {
            "tickets": [{
                "id": t.id,
                "user_id": t.user_id,
                "subject": t.subject,
                "status": t.status,
                "updated_at": t.updated_at.isoformat()
            } for t in tickets]
        }

@router.get("/tickets/{ticket_id}/messages")
async def get_admin_ticket_messages(ticket_id: int) -> Dict[str, Any]:
    async with async_session_maker() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket:
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
                "status": ticket.status,
                "user_id": ticket.user_id
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

class AdminReplyRequest(BaseModel):
    text: str

@router.post("/tickets/{ticket_id}/reply", status_code=status.HTTP_201_CREATED)
async def admin_reply_to_ticket(ticket_id: int, req: AdminReplyRequest) -> Dict[str, Any]:
    async with async_session_maker() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="تیکت یافت نشد")
            
        ticket.status = "resolved" # Set status as resolved when admin replies
        
        reply = TicketMessage(
            ticket_id=ticket_id,
            sender="admin",
            text=req.text
        )
        session.add(reply)
        await session.commit()
        
        # Optionally send notification inside Telegram to user here
        
        return {
            "status": "success",
            "message_id": reply.id
        }

async def process_broadcast(message_text: str):
    from app.db.database import async_session_maker
    from app.db.models import User
    from app.bot import bot
    from sqlalchemy import select
    import asyncio
    from aiogram.exceptions import TelegramAPIError
    import logging
    
    async with async_session_maker() as session:
        result = await session.execute(select(User.id))
        all_chat_ids = result.scalars().all()
        
    for chat_id in all_chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=message_text)
        except TelegramAPIError as e:
            logging.error(f"WebApp Broadcast failed for {chat_id}: {e}")
        await asyncio.sleep(0.05)

@router.post("/broadcast")
async def webapp_broadcast(req: BroadcastRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    background_tasks.add_task(process_broadcast, req.message)
    return {"status": "success", "detail": "ارسال همگانی در پس‌زمینه آغاز شد."}
