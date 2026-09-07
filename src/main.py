import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.database.db import init_db
from src.database.repository import Repository
from src.handlers import common_router, profile_router, lessons_router, queue_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bot")


async def periodic_cleanup_task(repo: Repository):
    """Background task running every hour to automatically delete lessons after their day has passed."""
    while True:
        try:
            deleted = await repo.cleanup_expired_lessons()
            if deleted > 0:
                logger.info("Automatically removed %d expired lesson(s).", deleted)
        except Exception as e:
            logger.error("Error during expired lessons cleanup: %s", e)
        await asyncio.sleep(3600)


async def main():
    logger.info("Starting Laboratory Sign-Up Bot...")

    # Initialize SQLite database
    logger.info("Initializing database at: %s", settings.db_path)
    await init_db(settings.db_path)
    repo = Repository(settings.db_path)

    # Initial cleanup on startup
    deleted_initial = await repo.cleanup_expired_lessons()
    if deleted_initial > 0:
        logger.info("Cleaned up %d past lesson(s) on startup.", deleted_initial)

    # Start background cleanup task
    cleanup_task = asyncio.create_task(periodic_cleanup_task(repo))

    # Initialize bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Pass repo to all handlers
    dp["repo"] = repo

    # Register routers
    dp.include_router(common_router)
    dp.include_router(profile_router)
    dp.include_router(lessons_router)
    dp.include_router(queue_router)

    logger.info("Bot configured successfully. Beginning polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        cleanup_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
