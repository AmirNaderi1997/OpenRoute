from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.database import async_session_maker
from app.db.models import User, SshAccount, SshServer
from app.core.config import settings
from app.core.topics_manager import get_manager_group_id, get_topic_id
from app.services.connection_links import get_connection_details
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY, service_type_label
from app.services.pricing import (
    PLAN_PRICES_TOMAN,
    get_discount_preview,
    get_plan_data_limit_gb,
    get_plan_max_connections,
    get_plan_price_toman,
    get_plan_price_usd,
    get_plan_title,
    get_plan_volume_label,
    mark_discount_code_as_used,
)
from app.services.ssh_account_service import create_remote_account, renew_remote_account, generate_password
from app.services.ssh.linux import LinuxSSHManager
from app.services.ssh.remote_provisioner import RemoteProvisionerClient

from app.bot.lexicon import Lexicon
from app.bot.keyboards import (
    get_main_menu, 
    get_server_list, 
    get_plan_list, 
    get_confirm_purchase,
    get_account_actions,
    get_back_button,
    MenuCallback,
    BuyCallback,
    AccountCallback
)

router = Router(name="user_menu_router")


def _build_account_text(acc: SshAccount) -> str:
    connection = get_connection_details(acc.ssh_username, acc.ssh_password, service_type=acc.service_type)
    import_link = str(acc.import_link or connection["import_link"])
    if acc.service_type == ACCOUNT_TYPE_SSH:
        return (
            "👤 <b>مشخصات سرویس:</b>\n\n"
            f"🧩 نوع سرویس: <code>{service_type_label(acc.service_type)}</code>\n"
            f"👤 نام کاربری: <code>{acc.ssh_username}</code>\n"
            f"🔐 رمز عبور: <code>{acc.ssh_password}</code>\n"
            f"🖥 هاست: <code>{connection['host']}</code>\n"
            f"🔌 پورت: <code>{connection['port']}</code>\n"
            "🔒 نوع اتصال: <code>SSH</code>\n"
            f"📅 انقضا: {acc.expires_at.strftime('%Y/%m/%d')}\n"
            f"📥 لینک اتصال سریع:\n<code>{import_link}</code>\n"
        )
    return (
        "👤 <b>مشخصات سرویس:</b>\n\n"
        f"🧩 نوع سرویس: <code>{service_type_label(acc.service_type)}</code>\n"
        f"👤 نام کاربری: <code>{acc.ssh_username}</code>\n"
        f"🔑 شناسه (UUID): <code>{acc.ssh_password}</code>\n"
        f"🖥 هاست: <code>{connection['host']}</code>\n"
        f"🔌 پورت: <code>{connection['port']}</code>\n"
        "🔒 نوع اتصال: <code>VLESS Reality</code>\n"
        f"📅 انقضا: {acc.expires_at.strftime('%Y/%m/%d')}\n"
        f"📥 لینک اتصال سریع:\n<code>{import_link}</code>\n"
    )



def _build_select_plan_text() -> str:
    return "🛒 <b>لطفاً سرویسی که می‌خواهید خریداری کنید را انتخاب کنید!</b>"


def _build_buy_summary(plan_name: str, balance: int, original_price: int, payable_price: int, discount_applied: bool) -> str:
    plan_id = 1
    for pid, pprice in PLAN_PRICES_TOMAN.items():
        if original_price == pprice:
            plan_id = pid
            break

    if discount_applied and payable_price != original_price:
        price_block = (
            f"💵 <b>قیمت اصلی کارت‌به‌کارت:</b> {original_price:,} تومان\n"
            f"🏷 <b>مبلغ قابل پرداخت با کد تخفیف:</b> {payable_price:,} تومان\n"
        )
    else:
        usd_price = get_plan_price_usd(plan_id)
        price_block = (
            f"💳 <b>قیمت کارت‌به‌کارت:</b> {original_price:,} تومان\n"
            f"🪙 <b>قیمت رمزارزی:</b> {usd_price:.2f} دلار\n"
        )

    volume = get_plan_volume_label(plan_id)

    return (
        "📋 <b>پیش فاکتور شما:</b>\n"
        f"👤 <b>نام کاربری:</b> <code>{settings.REMOTE_VPN_USERNAME_PREFIX}10xx</code>\n"
        f"🔐 <b>نام سرویس:</b> {plan_name}\n"
        f"📅 <b>مدت اعتبار:</b> 30 روز\n"
        f"{price_block}"
        f"👥 <b>حجم اکانت:</b> {volume}\n"
        "📝 <b>یادداشت محصول:</b> اشتراک اختصاصی یکماهه بدون مرز ؛ ip ثابت و بدون محدودیت کاربری با قابلیت به روز رسانی و نشان دادن حجم و روز مصرفی\n"
        f"💵 <b>موجودی کیف پول شما:</b> {balance:,} تومان\n\n"
        "💰 <b>سفارش شما آماده پرداخت است</b>"
    )

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    
    try:
        await message.delete()
    except Exception:
        pass
        
    args = command.args if (command and command.args) else None
    if args and args.startswith("reply_ticket_"):
        ticket_id = int(args.split("_")[2])
        async with async_session_maker() as session:
            user = await session.get(User, message.from_user.id)
            is_admin = user.is_admin if user else False
            
        if not is_admin:
            await message.answer("⚠️ شما دسترسی به پنل مدیریت تیکت‌ها را ندارید.")
            return
            
        from app.bot.handlers.admin_payments import AdminReplyTicketFSM
        await state.set_state(AdminReplyTicketFSM.waiting_for_reply)
        await state.update_data(ticket_id=ticket_id)
        
        await message.answer(f"✍️ لطفاً پاسخ خود را برای تیکت <b>#{ticket_id}</b> وارد کنید:\n(برای انصراف /cancel را بفرستید)")
        return

    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == message.from_user.id))
        if not user:
            user = User(
                id=message.from_user.id,
                username=message.from_user.username,
                language_code=message.from_user.language_code or "en"
            )
            session.add(user)
            await session.commit()
            
            # Notify admins of new registration
            group_id = get_manager_group_id()
            topic_id = get_topic_id("registrations")
            if group_id and topic_id:
                try:
                    import html
                    if user.username:
                        user_display = f"@{html.escape(user.username)}"
                    else:
                        user_display = "<i>بدون نام کاربری</i>"
                    alert_text = f"👥 <b>ثبت‌نام جدید</b>\n\n👤 کاربر: {user_display}\n🆔 آیدی: <code>{user.id}</code>"
                    await message.bot.send_message(
                        chat_id=group_id,
                        message_thread_id=topic_id,
                        text=alert_text
                    )
                except Exception as e:
                    import logging
                    logging.getLogger("user_menu").error(f"Failed to send registration notification to group {group_id} topic {topic_id}: {e}", exc_info=True)
        
        is_admin = user.is_admin if user else False

    if not is_admin:
        from aiogram.types import ReplyKeyboardRemove
        await message.answer("👋 خوش آمدید!", reply_markup=ReplyKeyboardRemove())
        
    await message.answer(Lexicon.get_welcome_text(), reply_markup=get_main_menu())

@router.callback_query(MenuCallback.filter(F.action == "main"))
async def go_to_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(Lexicon.get_welcome_text(), reply_markup=get_main_menu())

@router.callback_query(MenuCallback.filter(F.action == "support"))
async def show_support(callback: CallbackQuery):
    await callback.message.edit_text(Lexicon.SUPPORT, reply_markup=get_back_button().as_markup())

@router.callback_query(MenuCallback.filter(F.action == "tutorial"))
async def show_tutorial(callback: CallbackQuery):
    await callback.message.edit_text(Lexicon.TUTORIAL, reply_markup=get_back_button().as_markup())

@router.callback_query(MenuCallback.filter(F.action == "my_accounts"))
async def show_accounts(callback: CallbackQuery):
    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == callback.from_user.id))
        if not user:
            accounts = []
        else:
            accounts = (await session.scalars(
                select(SshAccount)
                .options(selectinload(SshAccount.server))
                .where(SshAccount.user_id == user.id)
            )).all()

    if not accounts:
        await callback.message.edit_text(Lexicon.NO_ACCOUNTS, reply_markup=get_back_button().as_markup())
        return

    if len(accounts) == 1:
        await callback.message.edit_text(
            _build_account_text(accounts[0]),
            reply_markup=get_account_actions(accounts[0].id),
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        builder.button(
            text=f"🔑 {acc.ssh_username} [{service_type_label(acc.service_type)}] ({acc.status})",
            callback_data=AccountCallback(action="view", account_id=acc.id),
        )
    builder.attach(get_back_button())
    builder.adjust(1)
    await callback.message.edit_text(
        "👤 <b>سرویس‌های فعال شما:</b>\n\nلطفاً یکی از سرویس‌های خود را برای مشاهده جزئیات و عملیات انتخاب کنید.",
        reply_markup=builder.as_markup(),
    )

@router.callback_query(MenuCallback.filter(F.action == "gift_start"))
async def gift_start_handler(callback: CallbackQuery):
    await callback.answer("⏳ در حال بررسی...", show_alert=False)
    
    from app.db.database import async_session_maker
    from app.db.models import User, SshAccount, SshServer
    from app.services.ssh_account_service import create_remote_account
    from app.services.connection_links import get_connection_details
    from app.bot.lexicon import Lexicon
    
    user_id = callback.from_user.id
    
    async with async_session_maker() as session:
        # Check if the user already has any account (trial or purchase) in the database
        stmt = select(SshAccount).where(SshAccount.user_id == user_id)
        existing_acc = (await session.execute(stmt)).scalars().first()
        if existing_acc:
            await callback.message.edit_text(
                "⚠️ <b>دریافت ناموفق هدیه</b>\n\n"
                "کاربر گرامی، طرح هدیه فقط برای کاربران جدید که تا کنون هیچ اشتراکی تهیه نکرده‌اند فعال است.",
                reply_markup=get_back_button().as_markup()
            )
            return
            
        # Get first active server
        server = (await session.scalars(select(SshServer).where(SshServer.status == "active", SshServer.service_type == ACCOUNT_TYPE_V2RAY))).first()
        if not server:
            await callback.message.edit_text(
                "❌ متاسفانه در حال حاضر هیچ سرور فعالی برای ارائه هدیه وجود ندارد. لطفا بعدا تلاش کنید.",
                reply_markup=get_back_button().as_markup()
            )
            return
            
        try:
            # Create a 1-day, 1GB data limit trial account
            account, import_link = await create_remote_account(
                session=session,
                user_id=user_id,
                server_id=server.id,
                duration_days=1,
                max_connections=1,
                data_limit_gb=1,
                service_type=ACCOUNT_TYPE_V2RAY,
            )
            await session.commit()
            
            connection = get_connection_details(account.ssh_username, account.ssh_password, service_type=account.service_type)
            
            # Send connection details
            success_text = (
                "🎁 <b>اشتراک هدیه شما با موفقیت فعال شد!</b>\n\n"
                "این اشتراک دارای محدودیت <b>۱ روز زمان</b> و <b>۱ گیگابایت ترافیک</b> می‌باشد:\n\n"
                + Lexicon.purchase_success(
                    account.service_type,
                    account.ssh_username,
                    account.ssh_password,
                    import_link,
                    str(connection.get("path", "")),
                    str(connection["host"]),
                    connection["port"],
                )
            )
            await callback.message.edit_text(success_text, reply_markup=get_back_button().as_markup())
            
        except Exception as e:
            import logging
            logging.getLogger("user_menu").error(f"Failed to create gift account: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ خطایی در ثبت و ایجاد اشتراک هدیه رخ داد. لطفاً با پشتیبانی در ارتباط باشید.",
                reply_markup=get_back_button().as_markup()
            )

# --- Purchase Flow ---

@router.callback_query(MenuCallback.filter(F.action == "buy_start"))
async def buy_step_server(callback: CallbackQuery):
    from app.db.database import async_session_maker
    async with async_session_maker() as session:
        servers = (await session.scalars(select(SshServer).where(SshServer.status == "active"))).all()
    await callback.answer()
    await callback.message.edit_text(Lexicon.SELECT_SERVER, reply_markup=get_server_list(servers))

@router.callback_query(BuyCallback.filter(F.step == "plan"))
async def buy_step_plan(callback: CallbackQuery, callback_data: BuyCallback):
    from app.db.database import async_session_maker
    async with async_session_maker() as session:
        server = await session.get(SshServer, callback_data.server_id)
    if not server:
        await callback.answer("سرور یافت نشد.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        _build_select_plan_text(),
        reply_markup=get_plan_list(server_id=callback_data.server_id, service_type=server.service_type)
    )

@router.callback_query(BuyCallback.filter(F.step == "confirm"))
async def buy_step_confirm(callback: CallbackQuery, callback_data: BuyCallback, state: FSMContext):
    from app.db.database import async_session_maker
    from app.db.models import SshServer, User
    
    plan_id = callback_data.plan_id
    server_id = callback_data.server_id
    
    plan_name = get_plan_title(plan_id)
    price = get_plan_price_toman(plan_id)
    
    await callback.answer()

    async with async_session_maker() as session:
        server = await session.get(SshServer, server_id)
        if not server:
            await callback.answer("سرور یافت نشد.", show_alert=True)
            return
        
        user = await session.scalar(select(User).where(User.id == callback.from_user.id))
        balance = int(user.balance) if user else 0
        
    await state.update_data(
        purchase_server_id=server_id,
        purchase_plan_id=plan_id,
        purchase_original_amount=price,
        purchase_payable_amount=price,
        purchase_payable_usd=get_plan_price_usd(plan_id),
        purchase_discount_applied=False,
        purchase_discount_code=None,
    )

    summary = _build_buy_summary(plan_name, balance, price, price, False)
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 پرداخت و دریافت سرویس", callback_data=BuyCallback(step="pay", server_id=server_id, plan_id=plan_id))
    builder.button(text="🏷 کد تخفیف", callback_data=BuyCallback(step="discount", server_id=server_id, plan_id=plan_id))
    builder.button(text="🏡 بازگشت به منوی اصلی", callback_data=MenuCallback(action="main"))
    builder.adjust(1, 1, 1)
    
    await callback.message.edit_text(summary, reply_markup=builder.as_markup())

@router.callback_query(BuyCallback.filter(F.step == "discount"))
async def prompt_purchase_discount_code(callback: CallbackQuery, callback_data: BuyCallback, state: FSMContext):
    await state.update_data(
        discount_target="purchase",
        purchase_server_id=callback_data.server_id,
        purchase_plan_id=callback_data.plan_id,
    )
    from app.bot.handlers.wallet import WalletRechargeFSM
    await state.set_state(WalletRechargeFSM.wait_discount_code)
    await callback.message.edit_text(
        "🏷 کد تخفیف را برای خرید سرویس ارسال کنید.",
        reply_markup=get_back_button("main").as_markup(),
    )

@router.callback_query(BuyCallback.filter(F.step == "pay"))
async def buy_step_pay(callback: CallbackQuery, callback_data: BuyCallback, state: FSMContext):
    await callback.answer("⏳ در حال پردازش...", show_alert=False)
    
    from app.db.database import async_session_maker
    from app.db.models import User, SshServer
    price = get_plan_price_toman(callback_data.plan_id)
    server_id = callback_data.server_id
    plan_id = callback_data.plan_id
    data = await state.get_data()
    payable_price = int(data.get("purchase_payable_amount", price))
    discount_code = data.get("purchase_discount_code") if data.get("purchase_discount_applied") else None

    if discount_code:
        async with async_session_maker() as session:
            preview = await get_discount_preview(
                session,
                original_toman=price,
                original_usd=get_plan_price_usd(plan_id),
                discount_code=discount_code,
                payment_method="wallet",
            )
        if not preview["discount_applied"]:
            from aiogram.utils.keyboard import InlineKeyboardBuilder

            builder = InlineKeyboardBuilder()
            builder.button(text="💳 کارت به کارت", callback_data=BuyCallback(step="pay_select_card", server_id=server_id, plan_id=plan_id))
            builder.button(text="💰 پرداخت آنلاین رمز ارز", callback_data=BuyCallback(step="pay_select_crypto", server_id=server_id, plan_id=plan_id))
            builder.button(text="❌ بستن لیست", callback_data=BuyCallback(step="confirm", server_id=server_id, plan_id=plan_id))
            builder.adjust(1, 1, 1)
            await callback.message.edit_text(
                "🏷 این کد تخفیف برای خرید مستقیم از کیف پول معتبر نیست.\n"
                "لطفاً یکی از روش‌های پرداخت مجاز را انتخاب کنید.",
                reply_markup=builder.as_markup(),
            )
            return
        payable_price = int(preview["payable_toman"] or price)
    
    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == callback.from_user.id))
        if not user:
            await callback.answer("خطا در تایید هویت کاربر.", show_alert=True)
            return

        if float(user.balance) < payable_price:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text="💳 کارت به کارت", callback_data=BuyCallback(step="pay_select_card", server_id=server_id, plan_id=plan_id))
            builder.button(text="💰 پرداخت آنلاین رمز ارز", callback_data=BuyCallback(step="pay_select_crypto", server_id=server_id, plan_id=plan_id))
            builder.button(text="❌ بستن لیست", callback_data=BuyCallback(step="confirm", server_id=server_id, plan_id=plan_id))
            builder.adjust(1, 1, 1)
            
            await callback.message.edit_text(
                "در حال پردازش... ⏳\n\n📝 موجودی حساب شما کافی نمی باشد یک روش پرداخت از لیست پایین انتخاب نمایید",
                reply_markup=builder.as_markup()
            )
            return
            
        server = await session.get(SshServer, callback_data.server_id)
        if not server:
            await callback.answer("سرور یافت نشد.", show_alert=True)
            return
            
        user.balance = float(user.balance) - payable_price
        await mark_discount_code_as_used(
            session,
            discount_code if isinstance(discount_code, str) else None,
            user_id=user.id,
            payment_id=None,
        )
        plan_id = callback_data.plan_id
        gb_limit = get_plan_data_limit_gb(plan_id)
        
        account, import_link = await create_remote_account(
            session=session,
            user_id=user.id,
            server_id=server.id,
            duration_days=30,
            max_connections=get_plan_max_connections(plan_id),
            data_limit_gb=gb_limit,
            service_type=server.service_type or ACCOUNT_TYPE_V2RAY,
        )
        await session.commit()
        connection = get_connection_details(account.ssh_username, account.ssh_password, service_type=account.service_type)
        
        # 5. Send connection details directly to user
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
        await callback.message.edit_text(success_text, reply_markup=get_back_button().as_markup())
        
        # 6. Notify admins in payments topic (informational only - no action buttons needed!)
        group_id = get_manager_group_id()
        topic_id = get_topic_id("payments")
        
        import html
        user_name = user.username or str(user.id)
        alert_text = (
            f"⚡️ <b>خرید مستقیم سرویس (کیف پول)</b>\n\n"
            f"👤 کاربر: @{html.escape(user_name)}\n"
            f"🆔 آیدی عددی: <code>{user.id}</code>\n"
            f"🖥 سرور: {html.escape(server.name)}\n"
            f"🔑 نام کاربری اکانت: <code>{html.escape(account.ssh_username)}</code>\n"
            f"💵 هزینه پلن: <code>{payable_price:,}</code> تومان\n\n"
            f"✅ سرویس به صورت خودکار فعال و برای کاربر ارسال گردید."
        )
        
        sent_to_group = False
        if group_id and topic_id:
            try:
                await callback.bot.send_message(
                    chat_id=group_id,
                    message_thread_id=topic_id,
                    text=alert_text
                )
                sent_to_group = True
            except Exception as e:
                import logging
                logging.getLogger("user_menu").error(f"Failed to send purchase notification to group: {e}")
                
        if not sent_to_group:
            # Fallback to direct admin messages
            admins = (await session.scalars(select(User).where(User.is_admin == True))).all()
            for admin in admins:
                if admin.id:
                    try:
                        await callback.bot.send_message(chat_id=admin.id, text=alert_text)
                    except Exception as e:
                        import logging
                        logging.getLogger("user_menu").error(f"Failed to send purchase notification to admin {admin.id}: {e}")


@router.callback_query(AccountCallback.filter())
async def handle_account_callback(callback: CallbackQuery, callback_data: AccountCallback, state: FSMContext):
    from app.db.database import async_session_maker
    from app.db.models import User, SshAccount, SshServer
    from datetime import datetime, timedelta
    
    action = callback_data.action
    account_id = callback_data.account_id
    
    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == callback.from_user.id))
        if not user:
            await callback.answer("کاربر یافت نشد.", show_alert=True)
            return
            
        if action == "renew" and account_id == 0:
            accounts = (await session.scalars(select(SshAccount).where(SshAccount.user_id == user.id))).all()
            if not accounts:
                await callback.answer("❌ شما هیچ سرویس فعالی برای تمدید ندارید.", show_alert=True)
                return
            
            if len(accounts) == 1:
                account_id = accounts[0].id
                # Fall through to renewal confirmation
                action = "renew_confirm"
            else:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                for acc in accounts:
                    builder.button(
                        text=f"🔑 {acc.ssh_username} [{service_type_label(acc.service_type)}] ({acc.status})", 
                        callback_data=AccountCallback(action="renew_confirm", account_id=acc.id)
                    )
                builder.button(text="🔙 بازگشت", callback_data=MenuCallback(action="main"))
                builder.adjust(1)
                await callback.message.edit_text(
                    "♻️ <b>لطفاً اکانتی که می‌خواهید تمدید کنید را انتخاب کنید:</b>",
                    reply_markup=builder.as_markup()
                )
                return

        if action == "view":
            account = await session.get(SshAccount, account_id)
            if not account or account.user_id != user.id:
                await callback.answer("اکانت یافت نشد.", show_alert=True)
                return

            await callback.message.edit_text(
                _build_account_text(account),
                reply_markup=get_account_actions(account.id),
            )
            return

        if action == "renew_confirm" or (action == "renew" and account_id > 0):
            account = await session.get(SshAccount, account_id)
            if not account or account.user_id != user.id:
                await callback.answer("اکانت یافت نشد.", show_alert=True)
                return
                
            price = 600000
            
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ تایید تمدید (۶۰۰,۰۰۰ تومان)", callback_data=AccountCallback(action="renew_execute", account_id=account.id))
            builder.button(text="🔙 انصراف", callback_data=MenuCallback(action="main"))
            builder.adjust(1)
            
            await callback.message.edit_text(
                f"🛒 <b>درخواست تمدید سرویس:</b>\n\n"
                f"👤 نام کاربری: <code>{account.ssh_username}</code>\n"
                f"💵 هزینه تمدید ۳۰ روزه: <code>600,000</code> تومان\n"
                f"💳 موجودی شما: <code>{int(user.balance):,}</code> تومان\n\n"
                f"آیا تایید می‌کنید؟",
                reply_markup=builder.as_markup()
            )
            return
            
        if action == "renew_execute":
            account = await session.get(SshAccount, account_id)
            if not account or account.user_id != user.id:
                await callback.answer("اکانت یافت نشد.", show_alert=True)
                return
                
            price = 600000
            if float(user.balance) < price:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                await state.update_data(
                    wallet_charge_flow=True,
                    prefill_amount_toman=price,
                    prefill_amount_usd=5.0,
                )
                builder = InlineKeyboardBuilder()
                builder.button(text="💳 شارژ کیف پول", callback_data=MenuCallback(action="wallet_charge"))
                builder.button(text="🔙 بازگشت", callback_data=MenuCallback(action="main"))
                builder.adjust(1)
                await callback.message.edit_text(
                    "❌ موجودی کیف پول شما کافی نیست.\n\n"
                    f"برای تمدید این سرویس حداقل <code>{price:,}</code> تومان نیاز دارید.",
                    reply_markup=builder.as_markup(),
                )
                return
                
            server = await session.get(SshServer, account.server_id)
            if not server:
                await callback.answer("سرور اکانت یافت نشد.", show_alert=True)
                return
                
            # Deduct balance
            user.balance = float(user.balance) - price
            
            new_expiry, _ = await renew_remote_account(session, account, duration_days=30)
            await session.commit()
            
            await callback.message.edit_text(
                f"✅ <b>سرویس شما با موفقیت تمدید شد!</b>\n\n"
                f"👤 نام کاربری: <code>{account.ssh_username}</code>\n"
                f"📅 تاریخ انقضای جدید: <code>{new_expiry.strftime('%Y/%m/%d')}</code>\n"
                f"💳 موجودی باقی‌مانده: <code>{int(user.balance):,}</code> تومان",
                reply_markup=get_back_button("main").as_markup()
            )
            return

        if action == "stats":
            account = await session.get(SshAccount, account_id)
            if not account or account.user_id != user.id:
                await callback.answer("اکانت یافت نشد.", show_alert=True)
                return

            traffic_bytes = 0
            try:
                if account.service_type == ACCOUNT_TYPE_SSH:
                    server = await session.get(SshServer, account.server_id)
                    if server:
                        ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
                        traffic_bytes = await ssh_manager.get_user_traffic(server.ip_address, account.ssh_username)
                else:
                    provisioner = RemoteProvisionerClient()
                    traffic_bytes = await provisioner.get_user_traffic(account.ssh_username)
            except Exception:
                traffic_bytes = 0

            used_gb = traffic_bytes / (1024 ** 3)
            status_text = (
                "📊 <b>وضعیت سرویس</b>\n\n"
                f"🧩 نوع سرویس: <code>{service_type_label(account.service_type)}</code>\n"
                f"👤 نام کاربری: <code>{account.ssh_username}</code>\n"
                f"📅 انقضا: <code>{account.expires_at.strftime('%Y/%m/%d')}</code>\n"
                f"🔌 وضعیت: <code>{account.status}</code>\n"
                f"👥 حداکثر اتصال همزمان: <code>{account.max_connections}</code>\n"
                f"📈 ترافیک مصرفی: <code>{used_gb:.2f} GB</code>\n"
            )
            await callback.message.edit_text(
                status_text,
                reply_markup=get_account_actions(account.id),
            )
            return

        if action == "chpass":
            account = await session.get(SshAccount, account_id)
            if not account or account.user_id != user.id:
                await callback.answer("اکانت یافت نشد.", show_alert=True)
                return

            new_password = generate_password()
            if account.service_type == ACCOUNT_TYPE_SSH:
                server = await session.get(SshServer, account.server_id)
                if not server:
                    await callback.answer("سرور اکانت یافت نشد.", show_alert=True)
                    return
                ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
                await ssh_manager._run_command(server.ip_address, f"echo '{account.ssh_username}:{new_password}' | chpasswd")
            else:
                provisioner = RemoteProvisionerClient()
                await provisioner.change_password(account.ssh_username, new_password)

            account.ssh_password = new_password
            account.import_link = get_connection_details(account.ssh_username, new_password, service_type=account.service_type)["import_link"]
            await session.commit()

            await callback.message.edit_text(
                "🔑 <b>رمز عبور سرویس با موفقیت تغییر کرد.</b>\n\n"
                f"👤 نام کاربری: <code>{account.ssh_username}</code>\n"
                f"🔐 رمز جدید: <code>{new_password}</code>\n"
                f"📥 لینک جدید:\n<code>{account.import_link}</code>",
                reply_markup=get_account_actions(account.id),
            )
            return

@router.message(Command("admin"))
async def cmd_admin_non_admin(message: Message, state: FSMContext):
    from aiogram.types import ReplyKeyboardRemove
    from app.bot.handlers.admin_auth import AdminLoginFSM

    await state.set_state(AdminLoginFSM.username)
    await message.answer(
        "🔐 دسترسی مدیریت فعال نیست. لطفاً نام کاربری مدیریت را وارد کنید:",
        reply_markup=ReplyKeyboardRemove(),
    )

@router.message(F.text.in_({
    "کاربران", "آمار کلی", "اتصال‌ها", "سرویس‌ها", "اعمال محدودیت‌ها", 
    "ثبت ترافیک", "ساخت گروهی", "ساخت گروهی SSH", "ساخت کاربر", "ساخت کاربر V2Ray", "ساخت کاربر SSH", "ساخت گروهی از VPS", 
    "پیام همگانی", "افزودن VPS", "سرورهای VPS", "راهنما", "مدیریت کاربر", 
    "خروج از ربات"
}))
async def handle_non_admin_admin_buttons(message: Message):
    from aiogram.types import ReplyKeyboardRemove
    await message.answer("⚠️ شما دسترسی به این بخش را ندارید.", reply_markup=ReplyKeyboardRemove())
