"""
Log Router
──────────
• Forwards every private non-command message to LOG_GROUP via the main bot.
  Only the main bot needs to be a member of the log group.
• When the admin replies to any forwarded message in the log group the reply
  is delivered back to the original user via the bot they messaged.
"""
import asyncio
import logging
from typing import Optional

from telegram import Bot, Update
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import ContextTypes

import bot_manager
import database as db
from config import LOG_GROUP_ID, ADMIN_ID

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _send_any(bot: Bot, chat_id: int, msg) -> bool:
    """Re-send any message type to chat_id via the given bot."""
    try:
        if msg.text:
            await bot.send_message(
                chat_id=chat_id,
                text=msg.text,
                entities=msg.entities or None,
            )
        elif msg.photo:
            await bot.send_photo(
                chat_id=chat_id,
                photo=msg.photo[-1].file_id,
                caption=msg.caption,
                caption_entities=msg.caption_entities or None,
            )
        elif msg.video:
            await bot.send_video(
                chat_id=chat_id,
                video=msg.video.file_id,
                caption=msg.caption,
                caption_entities=msg.caption_entities or None,
            )
        elif msg.document:
            await bot.send_document(
                chat_id=chat_id,
                document=msg.document.file_id,
                caption=msg.caption,
                caption_entities=msg.caption_entities or None,
            )
        elif msg.audio:
            await bot.send_audio(
                chat_id=chat_id,
                audio=msg.audio.file_id,
                caption=msg.caption,
                caption_entities=msg.caption_entities or None,
            )
        elif msg.sticker:
            await bot.send_sticker(chat_id=chat_id, sticker=msg.sticker.file_id)
        elif msg.voice:
            await bot.send_voice(
                chat_id=chat_id,
                voice=msg.voice.file_id,
                caption=msg.caption,
            )
        elif msg.video_note:
            await bot.send_video_note(
                chat_id=chat_id,
                video_note=msg.video_note.file_id,
            )
        elif msg.animation:
            await bot.send_animation(
                chat_id=chat_id,
                animation=msg.animation.file_id,
                caption=msg.caption,
            )
        elif msg.contact:
            await bot.send_contact(
                chat_id=chat_id,
                phone_number=msg.contact.phone_number,
                first_name=msg.contact.first_name,
                last_name=msg.contact.last_name or "",
            )
        elif msg.location:
            await bot.send_location(
                chat_id=chat_id,
                latitude=msg.location.latitude,
                longitude=msg.location.longitude,
            )
        else:
            return False
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await _send_any(bot, chat_id, msg)
    except (Forbidden, BadRequest) as e:
        logger.warning("_send_any: %s → chat %s: %s", bot.username, chat_id, e)
        return False
    except Exception as e:
        logger.error("_send_any unexpected error: %s", e)
        return False


async def _do_forward(main_bot: Bot, msg, user, header: str, source_key: str):
    """Send header + content copy to log group and persist the message mapping."""
    try:
        header_msg = await main_bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=header,
            parse_mode="HTML",
        )
        # Copy content to log group using file_ids (cross-bot accessible)
        sent = await _send_any(main_bot, LOG_GROUP_ID, msg)
        if not sent:
            # Fallback: nothing else to forward (e.g. unsupported type)
            return

        # We need the message_id of the content copy to map replies.
        # _send_any doesn't return it, so we fetch the last message id we just sent.
        # Strategy: store header_msg.message_id + (header_msg.message_id + 1) heuristically,
        # but more reliably: re-send via a wrapper that returns the sent message.
        # Instead, store header message id — admin can reply to it.
        db.save_log_message(header_msg.message_id, user.id, source_key)
        # Also store header+1 as a best-effort for the content message
        db.save_log_message(header_msg.message_id + 1, user.id, source_key)
    except Exception as e:
        logger.error("_do_forward error: %s", e)


async def _do_forward_full(main_bot: Bot, msg, user, header: str, source_key: str):
    """Like _do_forward but returns content message id for accurate mapping."""
    try:
        header_msg = await main_bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=header,
            parse_mode="HTML",
        )
        content_msg = await _send_any_returning(main_bot, LOG_GROUP_ID, msg)
        # Store both message IDs so admin can reply to either
        db.save_log_message(header_msg.message_id, user.id, source_key)
        if content_msg:
            db.save_log_message(content_msg.message_id, user.id, source_key)
    except Exception as e:
        logger.error("_do_forward_full error: %s", e)


async def _send_any_returning(bot: Bot, chat_id: int, msg):
    """Same as _send_any but returns the sent Message object."""
    try:
        if msg.text:
            return await bot.send_message(
                chat_id=chat_id, text=msg.text,
                entities=msg.entities or None)
        elif msg.photo:
            return await bot.send_photo(
                chat_id=chat_id, photo=msg.photo[-1].file_id,
                caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.video:
            return await bot.send_video(
                chat_id=chat_id, video=msg.video.file_id,
                caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.document:
            return await bot.send_document(
                chat_id=chat_id, document=msg.document.file_id,
                caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.audio:
            return await bot.send_audio(
                chat_id=chat_id, audio=msg.audio.file_id,
                caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.sticker:
            return await bot.send_sticker(chat_id=chat_id, sticker=msg.sticker.file_id)
        elif msg.voice:
            return await bot.send_voice(
                chat_id=chat_id, voice=msg.voice.file_id, caption=msg.caption)
        elif msg.video_note:
            return await bot.send_video_note(
                chat_id=chat_id, video_note=msg.video_note.file_id)
        elif msg.animation:
            return await bot.send_animation(
                chat_id=chat_id, animation=msg.animation.file_id, caption=msg.caption)
        elif msg.contact:
            return await bot.send_contact(
                chat_id=chat_id,
                phone_number=msg.contact.phone_number,
                first_name=msg.contact.first_name,
                last_name=msg.contact.last_name or "")
        elif msg.location:
            return await bot.send_location(
                chat_id=chat_id,
                latitude=msg.location.latitude,
                longitude=msg.location.longitude)
        return None
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await _send_any_returning(bot, chat_id, msg)
    except Exception as e:
        logger.warning("_send_any_returning: %s", e)
        return None


# ─── Public API ───────────────────────────────────────────────────────────────

async def forward_to_log(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    source_label: str,
    source_key: str,
) -> None:
    """
    Forward a private message to LOG_GROUP via the main bot.

    source_label  — human-readable bot name shown in the header,
                    e.g. "Main Bot" or "@QuizBot"
    source_key    — 'main' or str(bot_id), used to route admin replies back
    """
    if not LOG_GROUP_ID:
        return
    msg = update.message
    if not msg:
        return
    user = update.effective_user
    if not user or user.is_bot:
        return
    # Never log messages that come from the log group itself
    if update.effective_chat and update.effective_chat.id == LOG_GROUP_ID:
        return

    main_app = bot_manager.get_main_app()
    if not main_app:
        return
    main_bot_obj = main_app.bot

    uname = f"@{user.username}" if user.username else "—"
    header = (
        f"📩 <b>New Message</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{user.full_name}</b>  ({uname})\n"
        f"🆔 User ID: <code>{user.id}</code>\n"
        f"🤖 Bot: <b>{source_label}</b>"
    )

    main_loop = bot_manager.get_main_loop()

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    coro = _do_forward_full(main_bot_obj, msg, user, header, source_key)

    if current_loop is main_loop:
        # Already on the main loop — await directly
        await coro
    else:
        # On a subbot thread — fire-and-forget on the main loop
        asyncio.run_coroutine_threadsafe(coro, main_loop)


async def handle_log_reply(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Called when anyone sends a reply inside the log group.
    Only the ADMIN_ID is allowed to trigger reply routing.
    The reply (any content type) is delivered to the original user
    via whichever bot they originally messaged.
    """
    if not LOG_GROUP_ID:
        return
    msg = update.message
    if not msg or not msg.reply_to_message:
        return
    if msg.chat_id != LOG_GROUP_ID:
        return
    if not msg.from_user or msg.from_user.id != ADMIN_ID:
        return

    reply_to_id = msg.reply_to_message.message_id
    log_entry = db.get_log_message(reply_to_id)
    if not log_entry:
        # Not a tracked message — silently ignore
        return

    user_id = log_entry["user_id"]
    source_key = log_entry["source_key"]

    if source_key == "main":
        ok = await _send_any(ctx.bot, user_id, msg)
    else:
        bot_id = int(source_key)
        sub_app = bot_manager.get_app(bot_id)
        sub_loop = bot_manager.get_loop(bot_id)
        if not sub_app or not sub_loop or sub_loop.is_closed():
            await msg.reply_text("⚠️ That subbot is no longer running.")
            return
        cf = asyncio.run_coroutine_threadsafe(
            _send_any(sub_app.bot, user_id, msg), sub_loop
        )
        try:
            ok = await asyncio.wrap_future(cf)
        except Exception as e:
            logger.error("handle_log_reply subbot delivery error: %s", e)
            ok = False

    if ok:
        await msg.reply_text("✅ Delivered.", quote=True)
    else:
        await msg.reply_text(
            "❌ Could not deliver — user may have blocked the bot.", quote=True
        )
