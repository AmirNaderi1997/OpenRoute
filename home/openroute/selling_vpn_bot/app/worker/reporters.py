import logging
from aiogram import Bot
from sqlalchemy import select, func

from app.db.database import async_session_maker
from app.db.models import SshAccount, Payment, SupportTicket, SshServer, User
from app.core.topics_manager import get_manager_group_id, get_topic_id

logger = logging.getLogger(__name__)

async def broadcast_admin_report(bot: Bot):
    """
    Compiles a system status report and sends it to the manager group.
    """
    logger.info("Compiling scheduled admin system report...")
    
    try:
        async with async_session_maker() as session:
            active_subs = await session.scalar(
                select(func.count(SshAccount.id)).where(SshAccount.status == "active")
            ) or 0
            
            pending_payments = await session.scalar(
                select(func.count(Payment.id)).where(Payment.status == "pending", Payment.payment_method == "card_to_card")
            ) or 0
            
            open_tickets = await session.scalar(
                select(func.count(SupportTicket.id)).where(SupportTicket.status == "open")
            ) or 0
            
            active_servers = await session.scalar(
                select(func.count(SshServer.id)).where(SshServer.status == "active")
            ) or 0
            
            admins = (await session.scalars(select(User).where(User.is_admin == True))).all()
            
        report_text = (
            "📊 <b>گزارش دوره‌ای سیستم</b>\n\n"
            f"🟢 اشتراک‌های فعال: {active_subs}\n"
            f"⏳ پرداخت‌های در انتظار تایید: {pending_payments}\n"
            f"🎫 تیکت‌های باز: {open_tickets}\n"
            f"🖥 سرورهای فعال: {active_servers}\n\n"
            "⏱ بروزرسانی خودکار سیستم"
        )
        
        sent_to_group = False
        group_id = get_manager_group_id()
        topic_id = get_topic_id("stats")
        if group_id and topic_id:
            try:
                await bot.send_message(
                    chat_id=group_id,
                    message_thread_id=topic_id,
                    text=report_text,
                    parse_mode="HTML"
                )
                logger.info(f"Report successfully sent to group {group_id} (Topic: {topic_id}).")
                sent_to_group = True
            except Exception as group_err:
                logger.error(f"Failed to send admin report to group: {group_err}")
                
        if not sent_to_group:
            logger.info("Admin report falling back to direct admin messaging.")
            for admin in admins:
                if admin.id:
                    try:
                        await bot.send_message(
                            chat_id=admin.id,
                            text=report_text,
                            parse_mode="HTML"
                        )
                    except Exception as admin_err:
                        logger.error(f"Failed to send admin report to admin fallback {admin.id}: {admin_err}")
    except Exception as e:
        logger.error(f"Failed to broadcast admin report: {e}", exc_info=True)
