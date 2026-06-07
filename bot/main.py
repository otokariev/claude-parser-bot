import asyncio
import logging
import threading

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot.config import settings
from bot.handlers import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def start_celery_worker():
    """Start Celery worker in a separate thread."""
    from services.celery_app import celery_app
    worker = celery_app.Worker(loglevel="info")
    worker.start()


async def main() -> None:
    """Initialize and start the bot."""
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Store FSM state in Redis
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Register routers
    dp.include_router(router)

    # Start Celery worker in background thread
    celery_thread = threading.Thread(target=start_celery_worker, daemon=True)
    celery_thread.start()
    logger.info("Celery worker started in background thread")

    logger.info("Starting bot...")

    # Skip pending updates on startup
    await bot.delete_webhook(drop_pending_updates=True)

    # Start polling
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())