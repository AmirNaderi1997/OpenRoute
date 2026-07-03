from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.core.config import settings
from app.db.database import async_session_maker
from app.db.models import User
from sqlalchemy import select

router = Router(name="admin_auth_router")

class AdminLoginFSM(StatesGroup):
    username = State()
    password = State()

@router.message(Command("admin_login"))
async def cmd_admin_login(message: Message, state: FSMContext):
    await state.set_state(AdminLoginFSM.username)
    await message.answer("🔐 لطفاً نام کاربری مدیریت را وارد کنید:")

@router.message(AdminLoginFSM.username)
async def process_admin_username(message: Message, state: FSMContext):
    await state.update_data(username=message.text)
    await state.set_state(AdminLoginFSM.password)
    await message.answer("🔑 لطفاً رمز عبور را وارد کنید:")

@router.message(AdminLoginFSM.password)
async def process_admin_password(message: Message, state: FSMContext):
    password = message.text
    try:
        await message.delete()  # Delete the password for security
    except Exception:
        pass

    data = await state.get_data()
    username = data.get("username")

    if username == settings.SUPERADMIN_USERNAME and password == settings.SUPERADMIN_PASSWORD:
        async with async_session_maker() as session:
            user = await session.scalar(select(User).where(User.id == message.from_user.id))
            if not user:
                user = User(
                    id=message.from_user.id,
                    username=message.from_user.username,
                    language_code=message.from_user.language_code or "en",
                    is_admin=True,
                )
                session.add(user)
            else:
                user.username = message.from_user.username
                user.language_code = message.from_user.language_code or user.language_code or "en"
                user.is_admin = True
            await session.commit()

        await message.answer("✅ <b>ورود موفقیت‌آمیز!</b>\nشما اکنون دسترسی مدیریت دارید. برای باز کردن پنل مدیریت، /admin را ارسال کنید.")
    else:
        await message.answer("❌ <b>اطلاعات ورود نادرست است!</b>")

    await state.clear()

@router.message(Command("admin_logout"))
async def cmd_admin_logout(message: Message):
    async with async_session_maker() as session:
        user = await session.get(User, message.from_user.id)
        if user and user.is_admin:
            user.is_admin = False
            await session.commit()
            await message.answer("🚪 <b>خروج موفقیت‌آمیز!</b>\nدسترسی مدیریت شما لغو شد. مینی اپ اکنون در حالت کاربری عادی (Client) باز خواهد شد.")
        else:
            await message.answer("⚠️ شما در حال حاضر دسترسی مدیریت ندارید.")
