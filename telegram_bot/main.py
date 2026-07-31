"""
Entry point — starts the main bot and all active subbots.
"""
import asyncio
import logging
import os
import sys

from telegram.ext import Application

import database as db
from config import MAIN_BOT_TOKEN
from main_bot import build_main_app
import bot_manager

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main():
    logger.info("Initialising database...")
    db.init_db()

    logger.info("Launching active subbots in background threads...")
    await bot_manager.launch_all_active()

    logger.info("Starting main bot...")
    app = build_main_app(MAIN_BOT_TOKEN)

    async with app:
        await app.initialize()
        await app.start()
        logger.info("Main bot is running. Press Ctrl+C to stop.")
        from telegram import Update as _Update
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=_Update.ALL_TYPES,
        )
        # Block forever
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
