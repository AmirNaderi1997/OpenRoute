from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from redis.asyncio.client import Redis
from app.core.config import settings

# Import the new unified routers
from app.bot.handlers.user_menu import router as user_menu_router
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.admin_features import router as admin_features_router
from app.bot.handlers.admin_users import router as admin_users_router
from app.bot.handlers.admin_auth import router as admin_auth_router
from app.bot.handlers.admin_payments import router as admin_payments_router
from app.bot.handlers.wallet import router as wallet_router

bot = Bot(
    token=settings.BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode="HTML")
)

redis = Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)
storage = RedisStorage(redis=redis)

dp = Dispatcher(storage=storage)

# Register BlockedUserMiddleware
from app.bot.middlewares.blocked import BlockedUserMiddleware
dp.message.middleware(BlockedUserMiddleware())
dp.callback_query.middleware(BlockedUserMiddleware())

# Include unified routers
dp.include_router(admin_auth_router)
dp.include_router(admin_router)
dp.include_router(admin_users_router)
dp.include_router(admin_features_router)
dp.include_router(user_menu_router)
dp.include_router(admin_payments_router)
dp.include_router(wallet_router)
