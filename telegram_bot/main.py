"""
Entry point — starts the main bot and all active subbots.
Also exposes a lightweight HTTP health-check server so this can be
deployed as a Render *web* service (Render requires a bound port).
"""
import asyncio
import logging
import os
import sys

from aiohttp import web
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


# ─── Health-check HTTP server ─────────────────────────────────────────────────

async def handle_health(request):
    return web.Response(text="OK")

async def start_health_server():
    """Bind to $PORT (default 8080) so Render web service health checks pass."""
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health-check server listening on port %d", port)


# ─── Main entry point ─────────────────────────────────────────────────────────

async def main():
    logger.info("Initialising database...")
    db.init_db()

    logger.info("Starting health-check HTTP server...")
    await start_health_server()

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
