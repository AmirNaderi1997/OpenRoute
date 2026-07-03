import asyncio
from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo
from app.core.config import settings

MENU_BUTTON_TEXT = "Open"

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text=MENU_BUTTON_TEXT,
            web_app=WebAppInfo(url=settings.MINIAPP_URL)
        )
    )
    try:
        await bot.set_my_name(name="Open Route")
    except Exception as e:
        print(f"Failed to set name: {e}")
    print("Menu button set successfully.")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
