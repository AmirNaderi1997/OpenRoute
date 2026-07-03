from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.bot.lexicon import Lexicon
from app.bot.keyboards import (
    get_wallet_menu,
    get_back_button,
    MenuCallback,
    BuyCallback,
    get_card_recharge_keyboard,
    PaymentCallback,
    get_payment_methods
)
from app.db.database import async_session_maker
from app.db.models import User, Payment
from app.services.payment_pipeline import notify_admins_of_pending_payment
# Crypto disabled
from app.services.nowpayments import create_nowpayments_invoice, TOMAN_TO_USD_RATE
from app.services.account_types import service_type_label
from app.db.models import SshServer
from app.services.pricing import (
    discount_failure_message,
    encode_payment_metadata,
    get_discount_preview,
    get_plan_price_toman,
    get_plan_price_usd,
    get_plan_title,
    normalize_discount_code,
)

router = Router(name="wallet_router")

class WalletRechargeFSM(StatesGroup):
    wait_amount = State()
    wait_payment_click = State()
    wait_discount_code = State()
    wait_receipt = State()


def _resolve_selected_discount_payment_method(selected_method: str | None) -> str | None:
    if selected_method == "card":
        return "card_to_card"
    if selected_method == "crypto":
        return "crypto"
    return None


def _build_wallet_amount_review_text(
    selected_method: str,
    original_amount: int,
    entered_usd_amount: float | None,
    discount_applied: bool,
    payable_amount: int,
    payable_usd_amount: float | None,
    discount_code: str | None,
) -> str:
    if selected_method == "crypto":
        usd_val = entered_usd_amount or (float(original_amount) / TOMAN_TO_USD_RATE)
        pay_usd_val = payable_usd_amount or (float(payable_amount) / TOMAN_TO_USD_RATE)
        base = (
            "🪙 <b>شارژ کیف پول با رمز ارز</b>\n\n"
            f"🪙 مبلغ شارژ درخواستی: <code>{usd_val:.2f} USD</code> (معادل <code>{original_amount:,}</code> تومان)"
        )
        if discount_applied:
            base += f"\n🏷 مبلغ قابل پرداخت با کد {discount_code or '-'}: <code>{pay_usd_val:.2f} USD</code> (معادل <code>{payable_amount:,}</code> تومان)"
        return base
    else:
        base = (
            "💳 <b>شارژ کیف پول با کارت به کارت</b>\n\n"
            f"💳 مبلغ شارژ درخواستی: <code>{original_amount:,}</code> تومان"
        )
        if discount_applied:
            base += f"\n🏷 مبلغ قابل پرداخت با کد {discount_code or '-'}: <code>{payable_amount:,}</code> تومان"
        return base


def _build_wallet_amount_review_keyboard(show_discount: bool):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ادامه", callback_data="wallet_proceed_payment")
    if show_discount:
        builder.button(text="🏷 کد تخفیف", callback_data=PaymentCallback(method="discount_code"))
    builder.button(text="🔙 بازگشت", callback_data=MenuCallback(action="wallet"))
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def _build_discounted_card_instruction(original_amount: int, payable_amount: int, is_wallet_charge: bool) -> str:
    base_text = Lexicon.get_card_instruction(payable_amount)
    if payable_amount == original_amount:
        return base_text

    credit_text = "کیف پول شما" if is_wallet_charge else "سرویس شما"
    return (
        f"{base_text}\n\n"
        f"🏷 مبلغ اصلی: <code>{original_amount:,}</code> تومان\n"
        f"💵 مبلغ قابل پرداخت با کد تخفیف: <code>{payable_amount:,}</code> تومان\n"
        f"✅ پس از تایید، {credit_text} بر اساس مبلغ اصلی محاسبه خواهد شد."
    )


@router.callback_query(MenuCallback.filter(F.action == "wallet"))
async def show_wallet(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session_maker() as session:
        user = await session.scalar(select(User).where(User.id == callback.from_user.id))
        if not user:
            # Auto-register if not found
            user = User(id=callback.from_user.id, username=callback.from_user.username)
            session.add(user)
            await session.commit()
            
        balance = int(user.balance)

    await callback.message.edit_text(
        Lexicon.WALLET.format(balance=balance),
        reply_markup=get_wallet_menu(balance)
    )

@router.callback_query(MenuCallback.filter(F.action == "wallet_charge"))
async def start_wallet_charge(callback: CallbackQuery, state: FSMContext):
    existing = await state.get_data()
    await state.set_state(WalletRechargeFSM.wait_payment_click)
    await state.update_data(
        wallet_charge_flow=True,
        selected_payment_method=None,
        amount=None,
        original_amount=None,
        payable_amount=None,
        entered_usd_amount=None,
        payable_usd_amount=None,
        discount_applied=False,
        discount_code=None,
        server_id=None,
        plan_id=None,
        prefill_amount_toman=existing.get("prefill_amount_toman"),
        prefill_amount_usd=existing.get("prefill_amount_usd"),
    )
    await callback.message.edit_text(
        "💵 لطفاً روش پرداخت مورد نظر خود را برای شارژ کیف پول انتخاب کنید:",
        reply_markup=get_payment_methods(show_discount=False)
    )

@router.message(WalletRechargeFSM.wait_amount)
async def process_recharge_amount_toman(message: Message, state: FSMContext):
    amount_str = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer(
            "❌ مبلغ وارد شده نامعتبر است. لطفاً فقط عدد بزرگتر از صفر (به تومان) وارد کنید:",
            reply_markup=get_back_button("wallet").as_markup()
        )
        return

    amount = int(amount_str)
    data = await state.get_data()
    selected_method = data.get("selected_payment_method", "card")
    
    await state.update_data(
        wallet_charge_flow=True,
        selected_payment_method=selected_method,
        amount=amount,
        original_amount=amount,
        payable_amount=amount,
        entered_usd_amount=float(amount) / TOMAN_TO_USD_RATE if selected_method == "crypto" else None,
        payable_usd_amount=float(amount) / TOMAN_TO_USD_RATE if selected_method == "crypto" else None,
        server_id=None,
        plan_id=None,
        discount_applied=False,
        discount_code=None,
    )
    await state.set_state(WalletRechargeFSM.wait_payment_click)
    await message.answer(
        _build_wallet_amount_review_text(
            selected_method,
            amount,
            float(amount) / TOMAN_TO_USD_RATE if selected_method == "crypto" else None,
            False,
            amount,
            float(amount) / TOMAN_TO_USD_RATE if selected_method == "crypto" else None,
            None
        ),
        reply_markup=_build_wallet_amount_review_keyboard(show_discount=True),
    )

@router.callback_query(BuyCallback.filter(F.step == "pay_select_card"))
async def handle_buy_select_card(callback: CallbackQuery, callback_data: BuyCallback, state: FSMContext):
    await callback.answer("⏳ در حال انتقال...", show_alert=False)
    
    server_id = callback_data.server_id
    plan_id = callback_data.plan_id
    
    # Determine the price based on plan_id
    original_amount = get_plan_price_toman(plan_id)
    data = await state.get_data()
    payable_amount = data.get("purchase_payable_amount", original_amount)
    discount_applied = bool(data.get("purchase_discount_applied")) and data.get("purchase_plan_id") == plan_id and data.get("purchase_server_id") == server_id
    discount_code = data.get("purchase_discount_code") if discount_applied else None

    if discount_code:
        async with async_session_maker() as session:
            preview = await get_discount_preview(
                session,
                original_toman=original_amount,
                original_usd=get_plan_price_usd(plan_id),
                discount_code=discount_code,
                payment_method="card_to_card",
            )
        if not preview["discount_applied"]:
            await callback.answer(discount_failure_message(str(preview.get("failure_reason"))), show_alert=True)
            return
        payable_amount = int(preview["payable_toman"] or original_amount)
    
    # Set FSM state and store variables
    await state.set_state(WalletRechargeFSM.wait_payment_click)
    await state.update_data(
        amount=original_amount,
        original_amount=original_amount,
        payable_amount=payable_amount,
        payable_usd_amount=None,
        server_id=server_id,
        plan_id=plan_id,
        discount_applied=discount_applied,
        discount_code=discount_code,
        wallet_charge_flow=False,
        selected_payment_method="card",
    )
    
    # Show card payment instructions
    await callback.message.edit_text(
        _build_discounted_card_instruction(original_amount, payable_amount, False),
        reply_markup=get_card_recharge_keyboard(payable_amount)
    )

@router.callback_query(PaymentCallback.filter(F.method == "card"))
async def handle_recharge_card(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ در حال انتقال...", show_alert=False)
    data = await state.get_data()
    if data.get("wallet_charge_flow"):
        await state.set_state(WalletRechargeFSM.wait_amount)
        await state.update_data(selected_payment_method="card")
        prefill_amount = data.get("prefill_amount_toman")
        example = f"\n\nمبلغ پیشنهادی برای این پرداخت: <code>{int(prefill_amount):,}</code>" if prefill_amount else "\n\nمثال: <code>600000</code>"
        await callback.message.edit_text(
            "💵 لطفاً مبلغ مورد نظر برای شارژ کیف پول خود را به <b>تومان</b> وارد کنید." + example,
            reply_markup=get_back_button("wallet").as_markup()
        )
        return

    original_amount = data.get("original_amount", data.get("amount", 0))
    payable_amount = data.get("payable_amount", original_amount)
    
    await callback.message.edit_text(
        _build_discounted_card_instruction(original_amount, payable_amount, False),
        reply_markup=get_card_recharge_keyboard(payable_amount)
    )

@router.callback_query(BuyCallback.filter(F.step == "pay_select_crypto"))
async def handle_buy_select_crypto(callback: CallbackQuery, callback_data: BuyCallback, state: FSMContext):
    await callback.answer("⏳ در حال ایجاد درگاه پرداخت...", show_alert=False)
    
    server_id = callback_data.server_id
    plan_id = callback_data.plan_id
    user_id = callback.from_user.id
    
    original_amount = get_plan_price_toman(plan_id)
    original_usd = get_plan_price_usd(plan_id)
    
    data = await state.get_data()
    payable_amount = data.get("purchase_payable_amount", original_amount)
    payable_usd = data.get("purchase_payable_usd", original_usd)
    discount_applied = bool(data.get("purchase_discount_applied")) and data.get("purchase_plan_id") == plan_id and data.get("purchase_server_id") == server_id
    discount_code = data.get("purchase_discount_code") if discount_applied else None

    async with async_session_maker() as session:
        if discount_code:
            preview = await get_discount_preview(
                session,
                original_toman=original_amount,
                original_usd=original_usd,
                discount_code=discount_code,
                payment_method="crypto",
            )
            if not preview["discount_applied"]:
                await callback.answer(discount_failure_message(str(preview.get("failure_reason"))), show_alert=True)
                return
            payable_amount = int(preview["payable_toman"] or original_amount)
            payable_usd = float(preview["payable_usd"] or original_usd)
            
        if server_id:
            server = await session.get(SshServer, server_id)
        else:
            server = None
        
        service_type = server.service_type if server else None
            
        payment = Payment(
            user_id=user_id,
            server_id=server_id,
            amount=original_amount,
            payment_method="crypto",
            status="pending",
            service_type=service_type,
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()

    invoice_url, invoice_id = await create_nowpayments_invoice(
        payable_amount,
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
        await callback.message.edit_text(
            "❌ خطا در ایجاد درگاه پرداخت رمز ارز. لطفا بعدا تلاش کنید یا به پشتیبانی پیام دهید.",
            reply_markup=get_back_button("buy_start").as_markup()
        )
        return

    async with async_session_maker() as session:
        db_pay = await session.get(Payment, payment_id)
        if db_pay:
            base_ref = f"nowpayments_invoice:{invoice_id}" if invoice_id else f"url:{invoice_url}"
            db_pay.gateway_tx_id = encode_payment_metadata(
                base_ref,
                payable_toman=payable_amount,
                payable_usd=payable_usd,
                discount_code=discount_code,
            )
            await session.commit()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 پرداخت آنلاین رمز ارز", url=invoice_url)
    builder.button(text="🔙 بازگشت", callback_data=BuyCallback(step="confirm", server_id=server_id, plan_id=plan_id))
    builder.adjust(1)

    service_lbl = service_type_label(service_type) if service_type else "N/A"
    await callback.message.edit_text(
        f"💸 <b>فاکتور پرداخت رمز ارز صادر شد</b>\n\n"
        f"🧩 سرویس: {service_lbl}\n"
        f"💵 مبلغ نهایی: <code>{payable_usd:.2f} USD</code> (معادل <code>{payable_amount:,}</code> تومان)\n\n"
        f"⚠️ لطفا روی دکمه زیر کلیک کرده و پرداخت خود را انجام دهید. پس از تایید شبکه، سرویس شما به طور خودکار تحویل داده خواهد شد.",
        reply_markup=builder.as_markup()
    )

@router.callback_query(PaymentCallback.filter(F.method == "crypto"))
async def handle_recharge_crypto(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ در حال انتقال...", show_alert=False)
    data = await state.get_data()
    
    if data.get("wallet_charge_flow"):
        await state.set_state(WalletRechargeFSM.wait_amount)
        await state.update_data(selected_payment_method="crypto")
        prefill_amount = data.get("prefill_amount_toman")
        example = f"\n\nمبلغ پیشنهادی برای این پرداخت: <code>{int(prefill_amount):,}</code>" if prefill_amount else "\n\nمثال: <code>600000</code>"
        await callback.message.edit_text(
            "🪙 لطفاً مبلغ مورد نظر برای شارژ با رمز ارز را به <b>تومان</b> وارد کنید." + example,
            reply_markup=get_back_button("wallet").as_markup()
        )
        return

    original_amount = int(data.get("original_amount", data.get("amount", 0)) or 0)
    original_usd = float(original_amount) / TOMAN_TO_USD_RATE
    
    payable_amount = int(data.get("payable_amount", original_amount))
    payable_usd = float(data.get("payable_usd_amount", original_usd))
    discount_code = data.get("discount_code") if data.get("discount_applied") else None
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        payment = Payment(
            user_id=user_id,
            server_id=None,
            amount=original_amount,
            payment_method="crypto",
            status="pending",
            service_type="wallet",
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()

    invoice_url, invoice_id = await create_nowpayments_invoice(
        payable_amount,
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
        await callback.message.edit_text(
            "❌ خطا در ایجاد درگاه پرداخت رمز ارز. لطفا بعدا تلاش کنید یا به پشتیبانی پیام دهید.",
            reply_markup=get_back_button("wallet").as_markup()
        )
        return

    async with async_session_maker() as session:
        db_pay = await session.get(Payment, payment_id)
        if db_pay:
            base_ref = f"nowpayments_invoice:{invoice_id}" if invoice_id else f"url:{invoice_url}"
            db_pay.gateway_tx_id = encode_payment_metadata(
                base_ref,
                payable_toman=payable_amount,
                payable_usd=payable_usd,
                discount_code=discount_code,
            )
            await session.commit()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 پرداخت آنلاین رمز ارز", url=invoice_url)
    builder.button(text="🔙 بازگشت", callback_data=MenuCallback(action="wallet"))
    builder.adjust(1)

    await callback.message.edit_text(
        f"💸 <b>فاکتور شارژ کیف پول صادر شد</b>\n\n"
        f"💵 مبلغ شارژ: <code>{payable_usd:.2f} USD</code> (معادل <code>{payable_amount:,}</code> تومان)\n\n"
        f"⚠️ لطفا روی دکمه زیر کلیک کرده و پرداخت خود را انجام دهید. پس از تایید شبکه، کیف پول شما به طور خودکار شارژ خواهد شد.",
        reply_markup=builder.as_markup()
    )

@router.callback_query(PaymentCallback.filter(F.method == "discount_code"))
async def prompt_discount_code(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("wallet_charge_flow"):
        original_amount = data.get("original_amount", data.get("amount", 0))
        if not original_amount:
            await callback.answer("ابتدا مبلغ شارژ را وارد کنید.", show_alert=True)
            return
        await state.update_data(discount_target="wallet")
    elif data.get("plan_id") or data.get("purchase_plan_id"):
        await state.update_data(discount_target="purchase")
    else:
        await callback.answer("ابتدا مبلغ یا سرویس را انتخاب کنید.", show_alert=True)
        return

    await state.set_state(WalletRechargeFSM.wait_discount_code)
    await callback.message.edit_text(
        "🏷 کد تخفیف را ارسال کنید.",
        reply_markup=get_back_button("main").as_markup(),
    )


@router.message(WalletRechargeFSM.wait_discount_code)
async def process_discount_code(message: Message, state: FSMContext):
    code = normalize_discount_code(message.text)
    data = await state.get_data()
    target = data.get("discount_target")
    if not code:
        await message.answer("کد تخفیف نامعتبر است.")
        return

    async with async_session_maker() as session:
        if target == "wallet":
            original_amount = int(data.get("original_amount", data.get("amount", 0)) or 0)
            if not original_amount:
                await state.set_state(WalletRechargeFSM.wait_payment_click)
                await message.answer("ابتدا مبلغ شارژ را وارد کنید.")
                return

            entered_usd_amount = data.get("entered_usd_amount")
            preview = await get_discount_preview(
                session,
                original_toman=original_amount,
                original_usd=float(entered_usd_amount) if entered_usd_amount is not None else None,
                discount_code=code,
                payment_method=_resolve_selected_discount_payment_method(data.get("selected_payment_method")),
            )
            if not preview["discount_applied"]:
                await message.answer(discount_failure_message(str(preview.get("failure_reason"))))
                return

            payable_amount = int(preview["payable_toman"] or original_amount)
            payable_usd_amount = preview["payable_usd"]
            await state.update_data(
                payable_amount=payable_amount,
                payable_usd_amount=payable_usd_amount,
                discount_applied=True,
                discount_code=code,
            )
            await state.set_state(WalletRechargeFSM.wait_payment_click)
            selected_method = data.get("selected_payment_method", "card")
            await message.answer(
                _build_wallet_amount_review_text(
                    selected_method,
                    original_amount,
                    float(entered_usd_amount) if entered_usd_amount is not None else None,
                    True,
                    payable_amount,
                    float(payable_usd_amount) if payable_usd_amount is not None else None,
                    code,
                ),
                reply_markup=_build_wallet_amount_review_keyboard(show_discount=True),
            )
            return

        plan_id = int(data.get("purchase_plan_id") or data.get("plan_id") or 0)
        server_id = int(data.get("purchase_server_id") or data.get("server_id") or 0)
        if not plan_id or not server_id:
            await message.answer("ابتدا سرویس را انتخاب کنید.")
            return

        original_toman = get_plan_price_toman(plan_id)
        original_usd = get_plan_price_usd(plan_id)
        preview = await get_discount_preview(
            session,
            original_toman=original_toman,
            original_usd=original_usd,
            discount_code=code,
        )
        if not preview["discount_applied"]:
            await message.answer(discount_failure_message(str(preview.get("failure_reason"))))
            return

        user = await session.scalar(select(User).where(User.id == message.from_user.id))
        balance = int(user.balance) if user else 0
        payable_toman = int(preview["payable_toman"] or original_toman)
        payable_usd = float(preview["payable_usd"] or original_usd)
        await state.update_data(
            purchase_server_id=server_id,
            purchase_plan_id=plan_id,
            purchase_original_amount=original_toman,
            purchase_payable_amount=payable_toman,
            purchase_payable_usd=payable_usd,
            purchase_discount_applied=True,
            purchase_discount_code=code,
        )
        plan_name = get_plan_title(plan_id)
        from app.bot.handlers.user_menu import _build_buy_summary
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        builder = InlineKeyboardBuilder()
        builder.button(text="💰 پرداخت و دریافت سرویس", callback_data=BuyCallback(step="pay", server_id=server_id, plan_id=plan_id))
        builder.button(text="🏷 کد تخفیف", callback_data=BuyCallback(step="discount", server_id=server_id, plan_id=plan_id))
        builder.button(text="🏡 بازگشت به منوی اصلی", callback_data=MenuCallback(action="main"))
        builder.adjust(1, 1, 1)
        await state.set_state(WalletRechargeFSM.wait_payment_click)
        await message.answer(
            _build_buy_summary(plan_name, balance, original_toman, payable_toman, True),
            reply_markup=builder.as_markup(),
        )

@router.callback_query(F.data == "wallet_proceed_payment")
async def handle_wallet_proceed_payment(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ در حال انتقال...", show_alert=False)
    data = await state.get_data()
    selected_method = data.get("selected_payment_method")
    original_amount = data.get("original_amount", 0)
    payable_amount = data.get("payable_amount", original_amount)

    if selected_method == "crypto":
        user_id = callback.from_user.id
        payable_usd = float(payable_amount) / TOMAN_TO_USD_RATE
        discount_code = data.get("discount_code") if data.get("discount_applied") else None

        async with async_session_maker() as session:
            payment = Payment(
                user_id=user_id,
                server_id=None,
                amount=original_amount,
                payment_method="crypto",
                status="pending",
                service_type="wallet",
            )
            session.add(payment)
            await session.flush()
            payment_id = payment.id
            await session.commit()

        invoice_url, invoice_id = await create_nowpayments_invoice(
            payable_amount,
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
            await callback.message.edit_text(
                "❌ خطا در ایجاد درگاه پرداخت رمز ارز. لطفا بعدا تلاش کنید یا به پشتیبانی پیام دهید.",
                reply_markup=get_back_button("wallet").as_markup()
            )
            return

        async with async_session_maker() as session:
            db_pay = await session.get(Payment, payment_id)
            if db_pay:
                base_ref = f"nowpayments_invoice:{invoice_id}" if invoice_id else f"url:{invoice_url}"
                db_pay.gateway_tx_id = encode_payment_metadata(
                    base_ref,
                    payable_toman=payable_amount,
                    payable_usd=payable_usd,
                    discount_code=discount_code,
                )
                await session.commit()

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="💳 پرداخت آنلاین رمز ارز", url=invoice_url)
        builder.button(text="🔙 بازگشت", callback_data=MenuCallback(action="wallet"))
        builder.adjust(1)

        await callback.message.edit_text(
            f"💸 <b>فاکتور شارژ کیف پول صادر شد</b>\n\n"
            f"💵 مبلغ شارژ: <code>{payable_usd:.2f} USD</code> (معادل <code>{payable_amount:,}</code> تومان)\n\n"
            f"⚠️ لطفا روی دکمه زیر کلیک کرده و پرداخت خود را انجام دهید. پس از تایید شبکه، کیف پول شما به طور خودکار شارژ خواهد شد.",
            reply_markup=builder.as_markup()
        )
    else:
        await state.set_state(WalletRechargeFSM.wait_payment_click)
        await callback.message.edit_text(
            _build_discounted_card_instruction(original_amount, payable_amount, True),
            reply_markup=get_card_recharge_keyboard(payable_amount)
        )

@router.callback_query(F.data == "copy_card_num")
async def handle_copy_card(callback: CallbackQuery):
    await callback.answer("شماره کارت ارسال شد")
    await callback.message.answer("<code>5859831130851222</code>")

@router.callback_query(F.data.startswith("copy_amount_val_"))
async def handle_copy_amount(callback: CallbackQuery):
    amount = callback.data.split("_")[3]
    await callback.answer("مبلغ ارسال شد")
    await callback.message.answer(f"<code>{amount}</code>")

@router.callback_query(F.data == "wallet_continue_recharge")
async def handle_wallet_continue_recharge(callback: CallbackQuery, state: FSMContext):
    # Transition to wait_receipt state
    await state.set_state(WalletRechargeFSM.wait_receipt)
    
    # Button to go back to main menu
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🏡 بازگشت به منوی اصلی", callback_data=MenuCallback(action="main"))
    
    await callback.message.edit_text(
        "در حال پردازش... ⏳\n\n🖼 تصویر رسید خود را ارسال نمایید",
        reply_markup=builder.as_markup()
    )

@router.message(WalletRechargeFSM.wait_receipt, F.photo)
async def process_recharge_receipt(message: Message, state: FSMContext):
    # Only photos (screenshots) are accepted
    file_id = message.photo[-1].file_id
    is_doc = False

    try:
        await message.delete()
    except Exception:
        pass

    # Get details from state
    state_data = await state.get_data()
    amount = state_data.get("original_amount", state_data.get("amount", 0))
    payable_amount = state_data.get("payable_amount", amount)
    server_id = state_data.get("server_id")  # could be None if direct wallet charge
    discount_applied = bool(state_data.get("discount_applied"))
    discount_code = state_data.get("discount_code")

    # Save prefix photo: in gateway_tx_id
    gateway_tx_id = encode_payment_metadata(
        f"photo:{file_id}",
        payable_toman=payable_amount if payable_amount != amount else None,
        discount_code=discount_code if discount_applied else None,
    )

    try:
        async with async_session_maker() as session:
            user = await session.scalar(select(User).where(User.id == message.from_user.id))
            if not user:
                await state.clear()
                return
                
            payment = Payment(
                user_id=user.id,
                server_id=server_id,
                amount=amount,
                payment_method="card_to_card",
                gateway_tx_id=gateway_tx_id,
                status="pending"
            )
            session.add(payment)
            await session.commit()
            
            # Trigger Admin Notification
            import asyncio
            asyncio.create_task(notify_admins_of_pending_payment(payment.id))
            
        await message.answer(
            "✅ رسید شما با موفقیت ثبت شد و پس از تایید مدیریت، کیف پول شما شارژ خواهد شد.\n\n"
            "⏳ منتظر بررسی و تایید توسط مدیریت بمانید.",
            reply_markup=get_back_button("main").as_markup()
        )
    except Exception as e:
        import logging
        logging.getLogger("wallet").error(f"Failed to save payment receipt: {e}", exc_info=True)
        await message.answer(
            "❌ خطا در ثبت رسید پرداخت. ممکن است این رسید قبلاً ارسال شده باشد.\n"
            "در صورت بروز مشکل با پشتیبانی تماس بگیرید.",
            reply_markup=get_back_button("main").as_markup()
        )
    await state.clear()

@router.message(WalletRechargeFSM.wait_receipt, F.document)
async def process_recharge_receipt_document(message: Message):
    """Reject all documents. Users must send the receipt as a photo/screenshot."""
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(
        "❌ فقط اسکرین‌شات رسید به صورت عکس قابل پذیرش است.\n"
        "لطفاً رسید را به شکل Photo ارسال کنید، نه Document یا فایل.\n"
        "فایل‌های PDF، ZIP و موارد مشابه پذیرفته نمی‌شوند.",
        reply_markup=get_back_button("main").as_markup()
    )


@router.message(WalletRechargeFSM.wait_receipt)
async def process_recharge_receipt_invalid(message: Message):
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(
        "❌ فرمت نامعتبر است. لطفاً تصویر (اسکرین‌شات) رسید پرداخت خود را ارسال کنید:",
        reply_markup=get_back_button("main").as_markup()
    )
