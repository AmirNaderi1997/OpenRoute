from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy import select
from app.db.database import async_session_maker
from app.db.models import User

class BlockedUserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data):
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            
        if user_id:
            async with async_session_maker() as session:
                user = await session.scalar(select(User).where(User.id == user_id))
                if user and getattr(user, "is_blocked", False):
                    if isinstance(event, Message):
                        try:
                            await event.answer("⚠️ حساب کاربری شما مسدود شده است و دسترسی به ربات ندارید.")
                        except Exception:
                            pass
                    elif isinstance(event, CallbackQuery):
                        try:
                            await event.answer("⚠️ حساب کاربری شما مسدود شده است.", show_alert=True)
                        except Exception:
                            pass
                    return
        return await handler(event, data)
