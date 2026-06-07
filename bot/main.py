import logging
import threading
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.config import settings
from bot.handlers import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = f"/webhook/{settings.bot_token}"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 10000


def start_celery_worker():
    """Start Celery worker in a separate thread."""
    from services.celery_app import celery_app
    worker = celery_app.Worker(loglevel="info")
    worker.start()


async def on_startup(app):
    """Set webhook on startup."""
    try:
        webhook_url = f"{settings.webhook_url}{WEBHOOK_PATH}"
        await app["bot"].set_webhook(webhook_url, drop_pending_updates=True)
        logger.info(f"Webhook set to {webhook_url}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")


async def health_check(request):
    """Health check endpoint for UptimeRobot."""
    return web.Response(text="OK")


def main():
    """Start the bot with webhook."""
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

    # Create aiohttp app
    app = web.Application()
    app["bot"] = bot
    app.on_startup.append(on_startup)

    # Setup webhook handler
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Health check endpoint
    app.router.add_get("/health", health_check)

    # Start web server
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


if __name__ == "__main__":
    main()