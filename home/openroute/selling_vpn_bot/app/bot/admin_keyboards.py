from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters.callback_data import CallbackData

class AdminMenuCallback(CallbackData, prefix="admin_menu"):
    action: str

class AdminServerCallback(CallbackData, prefix="admin_srv"):
    action: str
    server_id: int = 0

class AdminSshCallback(CallbackData, prefix="admin_ssh"):
    action: str

def get_admin_back_button(target: str = "main") -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت به منوی مدیریت", callback_data=AdminMenuCallback(action=target))
    return builder

def get_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    # Row 1
    builder.row(
        KeyboardButton(text="کاربران"),
        KeyboardButton(text="آمار کلی")
    )
    # Row 2
    builder.row(
        KeyboardButton(text="اتصال‌ها")
    )
    # Row 3
    builder.row(
        KeyboardButton(text="اعمال محدودیت‌ها"),
        KeyboardButton(text="ثبت ترافیک")
    )
    # Row 4
    builder.row(
        KeyboardButton(text="ساخت کاربر V2Ray"),
        KeyboardButton(text="ساخت کاربر SSH")
    )
    # Row 5
    builder.row(
        KeyboardButton(text="ساخت گروهی SSH"),
        KeyboardButton(text="پیام همگانی")
    )
    # Row 6
    builder.row(
        KeyboardButton(text="افزودن VPS"),
        KeyboardButton(text="سرورهای VPS")
    )
    # Row 7
    builder.row(
        KeyboardButton(text="مدیریت کاربر"),
        KeyboardButton(text="مدیریت کیف پول"),
        KeyboardButton(text="راهنما")
    )
    # Row 8
    builder.row(
        KeyboardButton(text="مدیریت کد تخفیف"), KeyboardButton(text="اجرای سئو")
    )
    # Row 8
    builder.row(
        KeyboardButton(text="خروج از ربات")
    )
    
    return builder.as_markup(resize_keyboard=True)

def get_admin_servers_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ افزودن سرور جدید", callback_data=AdminServerCallback(action="add"))
    builder.button(text="📋 لیست سرورها", callback_data=AdminServerCallback(action="list"))
    builder.attach(get_admin_back_button())
    builder.adjust(1)
    return builder.as_markup()

def get_admin_accounts_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ ساخت اکانت SSH", callback_data=AdminSshCallback(action="add_single"))
    builder.button(text="📦 ساخت گروهی SSH", callback_data=AdminSshCallback(action="add_bulk"))
    builder.button(text="🔍 جستجوی کاربر/اکانت", callback_data=AdminSshCallback(action="search"))
    builder.attach(get_admin_back_button())
    builder.adjust(1)
    return builder.as_markup()

async def get_admin_server_list_for_bulk() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    from app.db.database import async_session_maker
    from app.db.models import SshServer
    from sqlalchemy import select
    
    async with async_session_maker() as session:
        servers = (await session.scalars(select(SshServer))).all()
        
    for srv in servers:
        status_emoji = "🟢" if srv.status == "active" else "🔴"
        builder.button(text=f"{status_emoji} {srv.name}", callback_data=AdminServerCallback(action="select_bulk", server_id=srv.id))
        
    builder.attach(get_admin_back_button("accounts"))
    builder.adjust(1)
    return builder.as_markup()
