"""
Manages all running subbot instances.
Each subbot runs in its own thread with its own asyncio event loop.
"""
import asyncio
import logging
import threading
from typing import Dict, Optional

from telegram.ext import Application

import database as db

logger = logging.getLogger(__name__)

# Registry: bot_id -> {app, thread, loop}
_registry: Dict[int, dict] = {}
_lock = threading.Lock()


def get_app(bot_id: int) -> Optional[Application]:
    with _lock:
        entry = _registry.get(bot_id)
        return entry['app'] if entry else None


def _run_subbot(bot_id: int, token: str):
    """Thread target: creates its own event loop and runs the subbot."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from sub_bot import build_subbot_app
    app = build_subbot_app(token, bot_id)

    with _lock:
        if bot_id in _registry:
            _registry[bot_id]['app'] = app
            _registry[bot_id]['loop'] = loop

    async def run():
        async with app:
            await app.initialize()
            await app.start()
            from telegram import Update as _Update
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=_Update.ALL_TYPES,
            )
            # Keep running until the stop event is set
            stop_event = _registry[bot_id]['stop_event']
            while not stop_event.is_set():
                await asyncio.sleep(1)
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    try:
        loop.run_until_complete(run())
    except Exception as e:
        logger.error(f"Subbot {bot_id} crashed: {e}")
    finally:
        loop.close()
        with _lock:
            _registry.pop(bot_id, None)
        logger.info(f"Subbot {bot_id} stopped.")


async def launch_subbot(bot_id: int, token: str):
    """Launch a subbot in a background thread."""
    with _lock:
        if bot_id in _registry:
            logger.info(f"Subbot {bot_id} already running.")
            return
        stop_event = threading.Event()
        _registry[bot_id] = {
            'app': None,
            'thread': None,
            'loop': None,
            'stop_event': stop_event,
        }

    t = threading.Thread(target=_run_subbot, args=(bot_id, token), daemon=True, name=f"subbot-{bot_id}")
    with _lock:
        _registry[bot_id]['thread'] = t
    t.start()
    logger.info(f"Launched subbot {bot_id} in thread {t.name}")

    # Give it a moment to initialise
    await asyncio.sleep(2)


async def stop_subbot(bot_id: int):
    """Signal a running subbot to stop."""
    with _lock:
        entry = _registry.get(bot_id)
    if not entry:
        return
    logger.info(f"Stopping subbot {bot_id}...")
    entry['stop_event'].set()
    # Don't join — daemon thread; will die on its own


async def launch_all_active():
    """Called at startup: launch every bot that is currently active."""
    bots = db.get_all_active_bots()
    logger.info(f"Starting {len(bots)} active subbots...")
    tasks = [launch_subbot(b['id'], b['token']) for b in bots]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All active subbots started.")
