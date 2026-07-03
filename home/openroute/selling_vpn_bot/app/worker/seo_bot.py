import os
import re
import json
import logging
from datetime import datetime
from app.bot import bot
from app.core.config import settings

logger = logging.getLogger(__name__)

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "seo_settings.json")
INDEX_PATH = "/var/www/openroute_website/index.html"

# Pre-defined variations for automatic rotation
TITLES = [
    "خرید VPN اختصاصی و پرسرعت OpenRoute | تونل SSH و V2Ray Reality",
    "خرید فیلترشکن آی پی ثابت OpenRoute | بدون قطعی V2Ray و SSH",
    "فیلترشکن پرسرعت مخصوص گیم و برنامه‌نویسان - OpenRoute",
    "مسیریابی هوشمند و اینترنت بدون فیلتر با OpenRoute"
]

DESCRIPTIONS = [
    "با خرید اشتراک اختصاصی OpenRoute به اینترنت آزاد و پرسرعت متصل شوید. پشتیبانی از V2Ray Reality، تونل SSH نامحدود و سیستم هوشمند ضد قطعی در زمان خاموشی شبکه در ایران.",
    "سرویس عبور از فیلترینگ OpenRoute مخصوص توسعه‌دهندگان و گیمرها. آی‌پی ثابت واقعی، بدون قطعی در زمان اینترنت ملی، پشتیبانی سریع از طریق ربات تلگرام.",
    "خرید فیلترشکن پرسرعت با قابلیت تونل دوبل (SSH + VLESS Reality). اتصال پایدار، پینگ پایین مخصوص بازی و دور زدن فیلترینگ ابزارهای برنامه‌نویسی."
]

KEYWORDS_BASE = [
    "خرید vpn", "خرید فیلترشکن", "v2ray reality", "تونل ssh", "آی پی ثابت",
    "عبور از فیلترینگ", "اینترنت ملی", "کانفیگ vless", "پروکسی تلگرام", "مسیریابی هوشمند"
]

KEYWORDS_GAMING = ["vpn مخصوص گیم", "کاهش پینگ", "فیلترشکن آی پی ثابت", "پینگ پایین بازی"]
KEYWORDS_DEV = ["دور زدن تحریم گیت هاب", "پروکسی داکر", "فیلترشکن برنامه نویسان"]

def get_persian_date_label() -> str:
    now = datetime.now()
    month_names = {
        1: "فروردین", 2: "اردیبهشت", 3: "خرداد",
        4: "تیر", 5: "مرداد", 6: "شهریور",
        7: "مهر", 8: "آبان", 9: "آذر",
        10: "دی", 11: "بهمن", 12: "اسفند"
    }
    shamsi_year = now.year - 621
    if now.month == 6:
        shamsi_month = "تیر" if now.day >= 22 else "خرداد"
    else:
        shamsi_month = month_names.get(((now.month + 9) % 12) + 1, "تیر")
    return f"{shamsi_month} {shamsi_year}"

def load_seo_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load SEO settings: {e}")
    return {"enabled": True, "last_updated": None}

def save_seo_settings(data: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Failed to save SEO settings: {e}")

async def run_auto_seo_updater(force: bool = False):
    """
    Main job that runs automatically.
    Generates fresh SEO configurations and updates index.html.
    """
    settings_data = load_seo_settings()
    if not settings_data.get("enabled", True) and not force:
        logger.info("Auto SEO Pilot is disabled. Skipping update.")
        return

    if not os.path.exists(INDEX_PATH):
        logger.error(f"Website index.html not found at {INDEX_PATH}")
        return

    try:
        day_of_year = datetime.now().timetuple().tm_yday
        title = TITLES[day_of_year % len(TITLES)]
        description = DESCRIPTIONS[day_of_year % len(DESCRIPTIONS)]
        
        date_label = get_persian_date_label()
        keywords = KEYWORDS_BASE.copy()
        
        if day_of_year % 2 == 0:
            keywords.extend(KEYWORDS_GAMING)
        else:
            keywords.extend(KEYWORDS_DEV)
            
        keywords.append(f"خرید فیلترشکن {date_label}")
        keywords.append(f"خرید vpn {date_label}")
        
        keywords_str = ", ".join(keywords)

        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        html = re.sub(r'<title>.*?</title>', f'<title>{title}</title>', html, flags=re.IGNORECASE)
        html = re.sub(r'<meta\s+name="description"\s+content=".*?"\s*/?>', f'<meta name="description" content="{description}" />', html, flags=re.IGNORECASE)
        html = re.sub(r'<meta\s+content=".*?"\s+name="description"\s*/?>', f'<meta name="description" content="{description}" />', html, flags=re.IGNORECASE)
        html = re.sub(r'<meta\s+name="keywords"\s+content=".*?"\s*/?>', f'<meta name="keywords" content="{keywords_str}" />', html, flags=re.IGNORECASE)
        html = re.sub(r'<meta\s+content=".*?"\s+name="keywords"\s*/?>', f'<meta name="keywords" content="{keywords_str}" />', html, flags=re.IGNORECASE)

        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            f.write(html)

        settings_data["last_updated"] = datetime.now().isoformat()
        save_seo_settings(settings_data)

        logger.info("Website SEO metadata updated successfully.")

        group_id = settings.MANAGER_GROUP_ID
        if group_id:
            msg_text = (
                "🤖 **گزارش ربات خودکار سئو (Auto SEO Bot)**\n\n"
                "✅ کلمات کلیدی و متاتگ‌های وب‌سایت با موفقیت بروزرسانی و منتشر شدند:\n\n"
                f"🏷 **عنوان جدید:**\n`{title}`\n\n"
                f"📝 **توضیحات جدید:**\n`{description}`\n\n"
                f"🔑 **کلمات کلیدی فعال:**\n`{keywords_str}`\n\n"
                f"⏰ زمان بروزرسانی: `{datetime.now().strftime('%H:%M:%S')}`"
            )
            try:
                await bot.send_message(chat_id=group_id, text=msg_text, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to notify admin of SEO update: {e}")

    except Exception as e:
        logger.error(f"Error occurred in run_auto_seo_updater: {e}", exc_info=True)
