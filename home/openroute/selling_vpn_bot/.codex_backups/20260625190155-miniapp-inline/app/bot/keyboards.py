from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from app.services.account_types import service_type_label
from app.services.pricing import get_service_plans

# Callback Data Factories
class MenuCallback(CallbackData, prefix="menu"):
    action: str

class BuyCallback(CallbackData, prefix="buy"):
    step: str
    server_id: int = 0
    plan_id: int = 0

class AccountCallback(CallbackData, prefix="acc"):
    action: str
    account_id: int = 0

def get_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="♻️ تمدید سرویس", callback_data=AccountCallback(action="renew", account_id=0))
    builder.button(text="🔐 خرید اشتراک", callback_data=MenuCallback(action="buy_start"))
    builder.button(text="🎁 گرفتن لینک هدیه", callback_data=MenuCallback(action="gift_start"))
    builder.button(text="🏦 کیف پول + شارژ", callback_data=MenuCallback(action="wallet"))
    builder.button(text="🛍 سرویس های من", callback_data=MenuCallback(action="my_accounts"))
    builder.button(text="📚 آموزش", callback_data=MenuCallback(action="tutorial"))
    builder.button(text="🎧 پشتیبانی", callback_data=MenuCallback(action="support"))
    builder.adjust(2, 1, 2, 2)
    return builder.as_markup()

def get_wallet_menu(balance: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 شارژ حساب", callback_data=MenuCallback(action="wallet_charge"))
    builder.button(text="🔙 بازگشت به منوی اصلی", callback_data=MenuCallback(action="main"))
    builder.adjust(1)
    return builder.as_markup()

def get_back_button(target: str = "main") -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 بازگشت", callback_data=MenuCallback(action=target))
    return builder

class PaymentCallback(CallbackData, prefix="pay"):
    method: str

def get_payment_methods(show_discount: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪙 پرداخت ارز دیجیتال", callback_data=PaymentCallback(method="crypto"))
    builder.button(text="💳 کارت به کارت", callback_data=PaymentCallback(method="card"))
    if show_discount:
        builder.button(text="🏷 کد تخفیف", callback_data=PaymentCallback(method="discount_code"))
    builder.attach(get_back_button())
    builder.adjust(1)
    return builder.as_markup()

def get_card_submit_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 ارسال ۴ رقم آخر کارت", callback_data=PaymentCallback(method="submit_card"))
    builder.attach(get_back_button("wallet"))
    builder.adjust(1)
    return builder.as_markup()

def get_server_list(servers: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    if not servers:
        builder.button(text="❌ هیچ سروری فعال نیست", callback_data="ignore")
    else:
        for server in servers:
            # Show name from DB
            builder.button(text=f"🌍 {server.name} [{service_type_label(getattr(server, 'service_type', None))}]", callback_data=BuyCallback(step="plan", server_id=server.id))
    
    back_btn = get_back_button("main")
    builder.attach(back_btn)
    builder.adjust(1)
    return builder.as_markup()

def get_plan_list(server_id: int, service_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    plans = get_service_plans(service_type)
    for plan in plans:
        builder.button(
            text=f"⚡️ {plan['title']} - {int(plan['price_toman']):,}تومان",
            callback_data=BuyCallback(step="confirm", server_id=server_id, plan_id=int(plan["id"])),
        )
    
    back_btn = get_back_button("buy_start")
    builder.attach(back_btn)
    builder.adjust(*([1] * (len(plans) + 1)))
    return builder.as_markup()

def get_confirm_purchase(server_id: int, plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ تایید و پرداخت", callback_data=BuyCallback(step="pay", server_id=server_id, plan_id=plan_id))
    
    # Passing server_id back so the user goes back to the specific server's plan list
    back_btn = InlineKeyboardBuilder()
    back_btn.button(text="🔙 بازگشت", callback_data=BuyCallback(step="plan", server_id=server_id))
    builder.attach(back_btn)
    builder.adjust(1, 1)
    return builder.as_markup()

def get_account_actions(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 تمدید", callback_data=AccountCallback(action="renew", account_id=account_id))
    builder.button(text="🔑 تغییر رمز", callback_data=AccountCallback(action="chpass", account_id=account_id))
    builder.button(text="📊 بروزرسانی وضعیت", callback_data=AccountCallback(action="stats", account_id=account_id))
    
    back_btn = get_back_button("my_accounts")
    builder.attach(back_btn)
    builder.adjust(2, 1, 1)
    return builder.as_markup()

def get_card_recharge_keyboard(amount: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="کپی شماره کارت 📋", callback_data="copy_card_num")
    builder.button(text="کپی مبلغ 📋", callback_data=f"copy_amount_val_{amount}")
    builder.button(text="✅ ادامه مراحل", callback_data="wallet_continue_recharge")
    builder.adjust(2, 1)
    return builder.as_markup()
