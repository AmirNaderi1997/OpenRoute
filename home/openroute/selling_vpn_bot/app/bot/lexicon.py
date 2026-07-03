import math

from app.core.config import settings
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY

class Lexicon:
    @staticmethod
    def get_welcome_text() -> str:
        return (
            "🌍 به OpenRoute خوش آمدید\n\n"
            "مسیر شما به اینترنت آزاد.\n\n"
            "OpenRoute با استفاده از زیرساختهای پرسرعت و پایدار، تجربهای مطمئن برای دسترسی به اینترنت فراهم میکند.\n\n"
            "⚡️ فعالسازی فوری\n"
            "🚀 سرعت و پایداری بالا\n"
            "🔒 امنیت و حفظ حریم خصوصی\n"
            "🛠 راهنمای نصب و پشتیبانی\n\n"
            "از منوی زیر میتوانید:\n"
            "• سرویس جدید تهیه کنید\n"
            "• اشتراک خود را تمدید کنید\n"
            "• وضعیت سرویسهای خود را مشاهده کنید\n"
            "• راهنمای نصب دریافت کنید\n"
            "• با پشتیبانی در ارتباط باشید\n\n"
            "به OpenRoute متصل شوید و بدون محدودیت آنلاین بمانید."
        )
    
    SUPPORT = (
        "👨‍💻 <b>پشتیبانی ۲۴ ساعته</b>\n\n"
        "موضوع درخواست خود را همین‌جا برای پشتیبانی ارسال کنید.\n"
        "پس از ثبت موضوع، ربات متن کامل پیام را از شما دریافت می‌کند.\n\n"
        "برای انصراف /cancel را بفرستید."
    )
    
    TUTORIAL = (
        "📚 <b>آموزش اتصال به سرویس‌های V2Ray Reality VPN</b>\n\n"
        "شما می‌توانید با استفاده از برنامه‌های زیر به سرویس ما متصل شوید:\n\n"
        "🍏 <b>کاربران iOS (آیفون و آیپد):</b>\n"
        "برنامه <b>V2Box</b> یا <b>Shadowrocket</b> یا <b>Streisand</b> را از App Store دانلود کرده و لینک اشتراک را وارد کنید.\n\n"
        "🤖 <b>کاربران Android (اندروید):</b>\n"
        "برنامه <b>v2rayNG</b> یا <b>Nekobox</b> را از Google Play/GitHub دانلود کرده و لینک اشتراک خود را وارد کنید.\n\n"
        "💻 <b>کاربران Windows (ویندوز):</b>\n"
        "برنامه <b>v2rayN</b> یا <b>Nekobox</b> را نصب کرده و لینک اشتراک را وارد نمایید.\n\n"
        "🍎 <b>کاربران macOS (مکینتاش):</b>\n"
        "از برنامه <b>V2Box</b> یا <b>FoXray</b> برای مک استفاده کنید.\n\n"
        "در صورت نیاز به راهنمایی بیشتر با پشتیبانی در ارتباط باشید."
    )
    
    SELECT_SERVER = "🌐 <b>مرحله ۱:</b> لطفاً سرور مورد نظر خود را انتخاب کنید:"
    SELECT_PLAN = (
        "⏱ <b>مرحله ۲:</b> لطفاً پلن زمانی و حجمی مورد نظر را انتخاب کنید:\n\n"
        "🥇 یک ماهه تک کاربره: <b>۶۰۰,۰۰۰ تومان</b>\n"
        "👥 یک ماهه دو کاربره: <b>۸۰۰,۰۰۰ تومان</b>"
    )
    
    def order_summary(server: str, plan: str, price: int) -> str:
        return (
            "🛒 <b>خلاصه سفارش شما</b>\n\n"
            f"📍 <b>سرور:</b> {server}\n"
            f"📦 <b>پلن:</b> {plan}\n"
            f"💵 <b>مبلغ قابل پرداخت:</b> {price:,} تومان\n\n"
            "آیا از خرید خود اطمینان دارید؟"
        )
        
    def purchase_success(
        service_type: str | None,
        user: str,
        pswd: str,
        import_link: str,
        ws_path: str,
        host: str | None = None,
        port: int | str | None = None,
    ) -> str:
        if service_type == ACCOUNT_TYPE_SSH:
            return (
                "🎉 <b>خرید شما با موفقیت انجام شد!</b>\n\n"
                "سرویس SSH شما آماده استفاده است. اطلاعات زیر را در کلاینت SSH یا برنامه تونل SSH وارد کنید:\n\n"
                f"👤 <b>نام کاربری:</b> <code>{user}</code>\n"
                f"🔑 <b>رمز عبور:</b> <code>{pswd}</code>\n"
                f"🖥 <b>هاست (Host):</b> <code>{host or settings.REMOTE_VPN_DOMAIN}</code>\n"
                f"🔌 <b>پورت:</b> <code>{port or settings.REMOTE_VPN_PUBLIC_PORT}</code>\n"
                "🔒 <b>نوع اتصال:</b> <code>Direct SSH</code>\n"
                f"📥 <b>لینک اتصال سریع (کلیک برای کپی):</b>\n"
                f"<code>{import_link}</code>\n\n"
                "از اعتماد شما سپاسگزاریم! 🌸"
            )

        if service_type == ACCOUNT_TYPE_V2RAY:
            return (
                "🎉 <b>خرید شما با موفقیت انجام شد!</b>\n\n"
                "سرویس PasarGuard / V2Ray شما آماده استفاده است.\n"
                "برای این سرویس نیازی به اطلاعات SSH ندارید. فقط لینک سابسکریپشن زیر را در یکی از برنامه‌های VPN مانند Streisand، NPV Tunnel، NetMod، v2rayNG یا Shadowrocket ایمپورت کنید:\n\n"
                f"📥 <b>لینک سابسکریپشن (کلیک برای کپی):</b>\n"
                f"<code>{import_link}</code>\n\n"
                "از اعتماد شما سپاسگزاریم! 🌸"
            )

        path_line = f"🧭 <b>مسیر:</b> <code>{ws_path}</code>\n" if ws_path else ""
        return (
            "🎉 <b>خرید شما با موفقیت انجام شد!</b>\n\n"
            f"👤 <b>نام کاربری:</b> <code>{user}</code>\n"
            f"🔑 <b>رمز عبور:</b> <code>{pswd}</code>\n"
            f"🖥 <b>هاست (Host):</b> <code>{host or settings.REMOTE_VPN_DOMAIN}</code>\n"
            f"🔌 <b>پورت:</b> <code>{port or settings.REMOTE_VPN_PUBLIC_PORT}</code>\n"
            f"{path_line}"
            f"📥 <b>لینک اتصال:</b>\n"
            f"<code>{import_link}</code>\n\n"
            "از اعتماد شما سپاسگزاریم! 🌸"
        )

        
    NO_ACCOUNTS = (
        "👤 <b>سرویس‌های من</b>\n\n"
        "شما در حال حاضر هیچ سرویس فعالی ندارید. برای خرید از منوی اصلی اقدام کنید."
    )
    
    WALLET = (
        "💳 <b>کیف پول شما</b>\n\n"
        "💰 <b>موجودی فعلی:</b> {balance:,} تومان\n\n"
        "برای شارژ کیف پول خود از طریق کارت به کارت یا پرداخت رمزارزی از دکمه‌های زیر استفاده کنید."
    )

    @staticmethod
    def progress_bar(used: float, total: float, length: int = 10) -> str:
        """Generates an emoji progress bar."""
        if total == 0:
            return "⬜️" * length + " (۰٪)"
        percentage = used / total
        filled_length = int(round(length * percentage))
        
        # Ensure filled_length is within bounds
        filled_length = max(0, min(length, filled_length))
        empty_length = length - filled_length
        
        bar = "🟩" * filled_length + "⬜️" * empty_length
        percent_str = f" ({math.floor(percentage * 100)}٪)"
        return bar + percent_str

    PAYMENT_METHOD = "💳 <b>انتخاب روش پرداخت</b>\n\nلطفاً یک روش را برای پرداخت انتخاب کنید:"
    CARD_INSTRUCTION = (
        "🏦 <b>پرداخت کارت به کارت</b>\n\n"
        "لطفاً مبلغ مورد نظر را به شماره کارت زیر واریز نمایید:\n\n"
        "💳 شماره کارت: <code>5859831130851222</code>\n"
        "👤 بنام: <b>امیرحسین نادری</b>\n\n"
        "پس از واریز، روی دکمه زیر کلیک کرده و ۴ رقم آخر کارت خود را ارسال کنید."
    )
    
    @staticmethod
    def get_card_instruction(amount: int) -> str:
        return (
            f"برای افزایش موجودی، مبلغ <b>{amount:,}</b> تومان را به شماره‌ی حساب زیر واریز کنید👇\n\n\n"
            "===================\n"
            "<code>5859831130851222</code>\n\n"
            "<b>امیرحسین نادری</b>\n"
            "===================\n\n"
            "❌ این تراکنش به مدت یک ساعت اعتبار دارد پس از آن امکان پرداخت این تراکنش امکان ندارد.\n"
            "‼️ مبلغ باید همان مبلغی که در بالا ذکر شده واریز نمایید.\n"
            "‼️ امکان پرداخت وجه از کیف پول نیست.\n"
            "‼️ مسئولیت واریز اشتباهی با شماست.\n"
            "🔝 بعد از پرداخت دکمه پرداخت کردم را زده سپس تصویر رسید را ارسال نمایید\n"
            "💵 بعد از تایید پرداختتون توسط ادمین کیف پول شما شارژ خواهد شد و در صورتی که سفارشی داشته باشین انجام خواهد شد"
        )

    CARD_ASK_4_DIGITS = "🔢 لطفاً <b>۴ رقم آخر</b> شماره کارت بانکی خود را ارسال کنید (مثال: 1234):"
    PAYMENT_ERROR = "اطلاعات پرداخت شما نامتعبر می باشد. درصورت خطا لطفا با پشتیبانی تماس بگیرید."
    
    SUPPORT_MENU = "🎧 <b>پشتیبانی</b>\n\nجهت ارتباط با تیم پشتیبانی و مطرح کردن مشکل خود، پیام خود را ارسال کنید:"
    TICKET_CREATED = "✅ پیام شما با موفقیت ثبت شد و به زودی توسط پشتیبانی بررسی می‌شود."
    
    # Admin Alerts
    ADMIN_NEW_PAYMENT = (
        "🚨 <b>درخواست پرداخت جدید</b>\n\n"
        "👤 کاربر: <code>{username}</code>\n"
        "💳 ۴ رقم آخر کارت: <code>{card_last_four}</code>\n"
        "💵 مبلغ: {amount} تومان\n"
        "📍 سرور انتخابی: {server_name}"
    )
