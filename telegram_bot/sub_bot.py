"""
Subbot logic — each quiz bot created by users runs this module.
"""
import logging
import asyncio
from datetime import datetime
import pytz

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes,
    PollAnswerHandler, ChatMemberHandler, filters
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import TelegramError

import database as db
from config import (
    ADMIN_ID, OWNER_CONTACT_LINK, OWNER_USERNAME,
    MARKS_CORRECT, MARKS_WRONG, MARKS_NOT_ATTEMPTED,
    GLOBAL_LEADERBOARD_LIMIT, TIMEZONE
)

logger = logging.getLogger(__name__)

# ─── Conversation states ──────────────────────────────────────────────────────
SET_WELCOME_TEXT = 10
SET_WELCOME_IMAGE = 11
SET_MGMT_GROUP = 12
SET_JOIN_LINK = 13
SET_OWNER_LINK = 14

# ─── Helpers ──────────────────────────────────────────────────────────────────

def user_link(user_id: int, name: str) -> str:
    return f"<a href='tg://user?id={user_id}'>{name}</a>"


def get_bot_id_from_app(app: Application) -> int:
    return app.bot_data.get("bot_id", 0)


async def check_force_join(bot_id: int, user_id: int, app: Application) -> bool:
    """Returns True if user is allowed (no force join or already joined)."""
    settings = db.get_bot_settings(bot_id)
    if not settings or not settings.get('force_join_chat_id'):
        return True
    chat_id = settings['force_join_chat_id']
    try:
        member = await app.bot.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR,
                              ChatMemberStatus.OWNER):
            return True
    except Exception:
        pass
    return False


async def send_force_join_msg(update: Update, settings: dict):
    link = settings.get('force_join_link', '#')
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel / Group", url=link)],
    ])
    text = (
        "⛔ <b>Access Restricted!</b>\n\n"
        "You must join our channel/group to use this bot.\n\n"
        "👇 Click the button below to join, then try again."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def send_inactive_msg(update: Update):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Owner", url=OWNER_CONTACT_LINK)],
    ])
    text = (
        "🔴 <b>Bot is Not Active</b>\n\n"
        "This bot is currently inactive.\n"
        "Please contact the owner for help."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


def is_subowner(bot_id: int, user_id: int) -> bool:
    bot = db.get_bot_by_id(bot_id)
    return bot is not None and bot['owner_id'] == user_id


def is_main_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID


def settings_keyboard(bot_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Set/Update Welcome Message", callback_data=f"set_welcome:{bot_id}")],
        [InlineKeyboardButton("🏘️ Set/Update Quiz Management Group", callback_data=f"set_mgmt_group:{bot_id}")],
        [InlineKeyboardButton("🔗 Set/Update Join For Updates Link", callback_data=f"set_join_link:{bot_id}")],
        [InlineKeyboardButton("👤 Set/Update Meet the Owner Link", callback_data=f"set_owner_link:{bot_id}")],
        [InlineKeyboardButton("◀️ Back", callback_data=f"settings_back:{bot_id}")],
    ])


def build_welcome_keyboard(settings: dict) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("➕ Add Me to Your Group", url="https://t.me/{botusername}?startgroup=true")],
    ]
    if settings.get('join_for_updates_link'):
        buttons.append([InlineKeyboardButton("📢 Join For Updates", url=settings['join_for_updates_link'])])
    if settings.get('meet_owner_link'):
        buttons.append([InlineKeyboardButton("👤 Meet the Owner", url=settings['meet_owner_link'])])
    return InlineKeyboardMarkup(buttons)


# ─── /start ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)
    user = update.effective_user

    if not bot_info:
        return

    # Register user
    db.upsert_bot_user(bot_id, user.id, user.username, user.first_name)

    # Check inactive
    if bot_info['status'] == 'inactive':
        await send_inactive_msg(update)
        return

    # Check force join
    settings = db.get_bot_settings(bot_id)
    if settings and settings.get('force_join_chat_id'):
        if not await check_force_join(bot_id, user.id, ctx.application):
            await send_force_join_msg(update, settings)
            return

    welcome_text = (settings or {}).get('welcome_text', 'Welcome! 🎯 I am a Quiz Bot.')
    welcome_image = (settings or {}).get('welcome_image_file_id')

    buttons = [[InlineKeyboardButton("➕ Add Me to Your Group",
                url=f"https://t.me/{(await ctx.application.bot.get_me()).username}?startgroup=true")]]
    if settings and settings.get('join_for_updates_link'):
        buttons.append([InlineKeyboardButton("📢 Join For Updates", url=settings['join_for_updates_link'])])
    if settings and settings.get('meet_owner_link'):
        buttons.append([InlineKeyboardButton("👤 Meet the Owner", url=settings['meet_owner_link'])])

    # Add settings button for subowner
    if is_subowner(bot_id, user.id):
        buttons.append([InlineKeyboardButton("⚙️ Set Your Bot", callback_data=f"open_settings:{bot_id}")])

    kb = InlineKeyboardMarkup(buttons)

    if welcome_image:
        await update.message.reply_photo(welcome_image, caption=welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ─── Settings flow ────────────────────────────────────────────────────────────

async def cb_open_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        await query.answer("⛔ Access denied.", show_alert=True)
        return

    settings_text = "⚙️ <b>Bot Settings</b>\n\nChoose what you want to set up:"
    settings_kb = settings_keyboard(bot_id)

    # Try plain-text edit first; if the message is a photo/media, fall back to
    # sending a new text message and deleting the old one.
    try:
        await query.edit_message_text(settings_text, reply_markup=settings_kb, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            # Message is a media message — send a fresh text message instead
            await query.message.reply_text(settings_text, reply_markup=settings_kb, parse_mode=ParseMode.HTML)
            await query.message.delete()
        except Exception:
            # Last resort: just reply without deleting
            await query.message.reply_text(settings_text, reply_markup=settings_kb, parse_mode=ParseMode.HTML)


async def cb_set_welcome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    ctx.user_data['setting_bot_id'] = bot_id
    await query.edit_message_text(
        "📝 <b>Set Welcome Message</b>\n\n"
        "Send me the welcome message for your bot.\n"
        "You can send:\n"
        "• Just <b>text</b> for a text-only welcome\n"
        "• A <b>photo with caption</b> for an image welcome\n\n"
        "<i>The caption/text will be the welcome message.</i>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"settings_back:{bot_id}")]]),
        parse_mode=ParseMode.HTML
    )
    return SET_WELCOME_TEXT


async def receive_welcome_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = ctx.user_data.get('setting_bot_id', get_bot_id_from_app(ctx.application))
    if not is_subowner(bot_id, update.effective_user.id):
        return ConversationHandler.END
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        text = update.message.caption or "Welcome! 🎯"
        db.update_bot_settings(bot_id, welcome_text=text, welcome_image_file_id=file_id)
        await update.message.reply_text("✅ <b>Welcome message with image saved!</b>", parse_mode=ParseMode.HTML,
                                        reply_markup=settings_keyboard(bot_id))
    else:
        db.update_bot_settings(bot_id, welcome_text=update.message.text,
                               welcome_image_file_id=None)
        await update.message.reply_text("✅ <b>Welcome message saved!</b>", parse_mode=ParseMode.HTML,
                                        reply_markup=settings_keyboard(bot_id))
    return ConversationHandler.END


async def cb_set_mgmt_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    ctx.user_data['setting_bot_id'] = bot_id
    await query.edit_message_text(
        "🏘️ <b>Set Quiz Management Group</b>\n\n"
        "Please forward any message from the group you want to set as the quiz management group, "
        "or simply send the group's <b>chat ID</b> (e.g., <code>-1001234567890</code>).\n\n"
        "💡 <i>Alternatively, use the /setmgmt command in your target group.</i>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"settings_back:{bot_id}")]]),
        parse_mode=ParseMode.HTML
    )
    return SET_MGMT_GROUP


async def receive_mgmt_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = ctx.user_data.get('setting_bot_id', get_bot_id_from_app(ctx.application))
    if not is_subowner(bot_id, update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        group_id = int(text)
        chat = await ctx.application.bot.get_chat(group_id)
        db.update_bot_settings(bot_id, quiz_management_group_id=group_id,
                               quiz_management_group_name=chat.title)
        await update.message.reply_text(
            f"✅ <b>Quiz Management Group set to:</b>\n{chat.title}",
            parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(bot_id)
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Could not set group. Make sure I'm a member there and the ID is correct.\nError: {e}",
            reply_markup=settings_keyboard(bot_id)
        )
    return ConversationHandler.END


async def cb_set_join_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    ctx.user_data['setting_bot_id'] = bot_id
    await query.edit_message_text(
        "🔗 <b>Set Join For Updates Link</b>\n\n"
        "Send me the invite link for your updates channel/group\n"
        "Example: <code>https://t.me/yourchannel</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"settings_back:{bot_id}")]]),
        parse_mode=ParseMode.HTML
    )
    return SET_JOIN_LINK


async def receive_join_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = ctx.user_data.get('setting_bot_id', get_bot_id_from_app(ctx.application))
    if not is_subowner(bot_id, update.effective_user.id):
        return ConversationHandler.END
    link = update.message.text.strip()
    db.update_bot_settings(bot_id, join_for_updates_link=link)
    await update.message.reply_text("✅ <b>Join For Updates link saved!</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(bot_id))
    return ConversationHandler.END


async def cb_set_owner_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    ctx.user_data['setting_bot_id'] = bot_id
    await query.edit_message_text(
        "👤 <b>Set Meet the Owner Link</b>\n\n"
        "Send me your personal Telegram link\n"
        "Example: <code>https://t.me/yourusername</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"settings_back:{bot_id}")]]),
        parse_mode=ParseMode.HTML
    )
    return SET_OWNER_LINK


async def receive_owner_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = ctx.user_data.get('setting_bot_id', get_bot_id_from_app(ctx.application))
    if not is_subowner(bot_id, update.effective_user.id):
        return ConversationHandler.END
    link = update.message.text.strip()
    db.update_bot_settings(bot_id, meet_owner_link=link)
    await update.message.reply_text("✅ <b>Meet the Owner link saved!</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=settings_keyboard(bot_id))
    return ConversationHandler.END


async def cb_settings_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)
    user = update.effective_user
    settings = db.get_bot_settings(bot_id)
    welcome_text = (settings or {}).get('welcome_text', 'Welcome! 🎯')
    welcome_image = (settings or {}).get('welcome_image_file_id')

    buttons = [[InlineKeyboardButton("➕ Add Me to Your Group",
                url=f"https://t.me/{(await ctx.application.bot.get_me()).username}?startgroup=true")]]
    if settings and settings.get('join_for_updates_link'):
        buttons.append([InlineKeyboardButton("📢 Join For Updates", url=settings['join_for_updates_link'])])
    if settings and settings.get('meet_owner_link'):
        buttons.append([InlineKeyboardButton("👤 Meet the Owner", url=settings['meet_owner_link'])])
    if is_subowner(bot_id, user.id):
        buttons.append([InlineKeyboardButton("⚙️ Set Your Bot", callback_data=f"open_settings:{bot_id}")])
    kb = InlineKeyboardMarkup(buttons)

    try:
        if welcome_image:
            await query.message.reply_photo(welcome_image, caption=welcome_text,
                                             reply_markup=kb, parse_mode=ParseMode.HTML)
            await query.message.delete()
        else:
            await query.edit_message_text(welcome_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    return ConversationHandler.END


# ─── /setmgmt — set mgmt group from within the group ─────────────────────────

async def cmd_setmgmt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    if update.effective_chat.type not in ('group', 'supergroup'):
        await update.message.reply_text("Use this command inside a group.")
        return
    chat = update.effective_chat
    db.update_bot_settings(bot_id, quiz_management_group_id=chat.id,
                           quiz_management_group_name=chat.title)
    await update.message.reply_text(
        f"✅ <b>This group has been set as the Quiz Management Group!</b>\n\n"
        f"📌 Group: {chat.title}\n"
        "Now send quiz polls here and reply with <code>/send</code> to distribute them.",
        parse_mode=ParseMode.HTML
    )


# ─── Quiz management: receive poll ───────────────────────────────────────────

async def receive_poll(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Step 1 of quiz flow:
    Subowner sends a quiz poll in the management group.
    Bot saves it immediately and instructs owner to reply with correct option.

    NOTE: Telegram hides correct_option_id from bots in groups,
    so we always ask the owner to specify the answer.
    """
    bot_id = get_bot_id_from_app(ctx.application)
    if not update.message or not update.message.poll:
        return

    sender_id = update.effective_user.id
    if not is_subowner(bot_id, sender_id):
        return

    settings = db.get_bot_settings(bot_id)
    mgmt_gid = (settings or {}).get('quiz_management_group_id')

    # Only accept from the quiz management group
    if not mgmt_gid or update.effective_chat.id != int(mgmt_gid):
        return

    poll = update.message.poll

    if poll.type != 'quiz':
        await update.message.reply_text(
            "⚠️ <b>Regular poll detected!</b>\n\n"
            "Please send a <b>Quiz</b> type poll (with a correct answer set).",
            parse_mode=ParseMode.HTML
        )
        return

    options = [opt.text for opt in poll.options]
    num_options = len(options)

    # Save quiz with placeholder correct_option (-1 = not set yet)
    quiz_id = db.add_quiz(
        bot_id=bot_id,
        question=poll.question,
        options=options,
        correct_option=-1,
        explanation=poll.explanation or "",
        mgmt_msg_id=update.message.message_id,
        confirmation_msg_id=0
    )

    opts_text = "\n".join(
        f"  {'ABCD'[i]}. {opt}" for i, opt in enumerate(options)
    )

    await update.message.reply_text(
        f"📥 <b>Quiz saved!</b>\n\n"
        f"📝 <b>Q:</b> {poll.question}\n\n"
        f"{opts_text}\n\n"
        f"↩️ <b>Reply to the quiz poll above</b> with the correct option:\n"
        f"<code>1</code>–<code>{num_options}</code>  or  "
        f"<code>{'</code> / <code>'.join(list('ABCD')[:num_options])}</code>\n\n"
        f"Quiz will be sent to all groups <b>automatically</b> after you set the answer.",
        parse_mode=ParseMode.HTML
    )


# ─── Step 2: owner replies to quiz poll with correct option ──────────────────

async def receive_correct_option(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Step 2 of quiz flow:
    Subowner replies DIRECTLY to the original quiz poll message with
    the correct option — e.g. '2', 'B', 'b'.

    Once validated, the quiz is distributed to all connected groups
    automatically after a 30-second countdown.
    """
    bot_id = get_bot_id_from_app(ctx.application)
    if not update.message or not update.message.text:
        return

    sender_id = update.effective_user.id
    if not is_subowner(bot_id, sender_id):
        return

    settings = db.get_bot_settings(bot_id)
    mgmt_gid = (settings or {}).get('quiz_management_group_id')
    if not mgmt_gid or update.effective_chat.id != int(mgmt_gid):
        return

    # Must be a reply to some message
    replied = update.message.reply_to_message
    if not replied:
        return

    # That replied-to message must be a quiz poll saved in our DB
    quiz = db.get_quiz_by_mgmt_msg(bot_id, replied.message_id)
    if not quiz:
        return  # not a quiz poll we know about — ignore silently

    text = update.message.text.strip().upper()

    # Accept: 1/2/3/4  OR  A/B/C/D
    letter_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
    options = quiz['options']
    num_options = len(options)

    correct_idx = None
    if text.isdigit():
        n = int(text)
        if 1 <= n <= num_options:
            correct_idx = n - 1
    elif text in letter_map and letter_map[text] < num_options:
        correct_idx = letter_map[text]

    if correct_idx is None:
        valid = ' / '.join(
            [str(i+1) for i in range(num_options)] +
            list('ABCD')[:num_options]
        )
        await update.message.reply_text(
            f"⚠️ Invalid option. Please reply with: {valid}"
        )
        return

    # Save correct answer
    db.update_quiz_correct_option(quiz['id'], correct_idx)

    groups = db.get_bot_groups(bot_id)
    target_groups = [
        g for g in groups
        if g['group_id'] != int(mgmt_gid)
    ]
    num_groups = len(target_groups)

    if num_groups == 0:
        await update.message.reply_text(
            f"✅ <b>Correct answer set:</b> {options[correct_idx]}\n\n"
            "⚠️ <b>No connected groups found!</b> Add the bot to groups first.",
            parse_mode=ParseMode.HTML
        )
        return

    # Send countdown message — we'll edit it after distribution
    status_msg = await update.message.reply_text(
        f"✅ <b>Correct answer set:</b> {options[correct_idx]}\n\n"
        f"⏳ Sending to <b>{num_groups}</b> group(s) in <b>30 seconds</b>…",
        parse_mode=ParseMode.HTML
    )

    # Schedule background distribution after 30 seconds
    asyncio.create_task(
        _auto_distribute(
            app=ctx.application,
            bot_id=bot_id,
            quiz_id=quiz['id'],
            mgmt_gid=int(mgmt_gid),
            status_chat_id=update.effective_chat.id,
            status_msg_id=status_msg.message_id,
            delay=30,
        )
    )


async def _auto_distribute(app, bot_id: int, quiz_id: int, mgmt_gid: int,
                            status_chat_id: int, status_msg_id: int, delay: int = 30):
    """Background task: wait `delay` seconds then send quiz to all connected groups."""
    await asyncio.sleep(delay)

    quiz = db.get_quiz_by_id(quiz_id)
    if not quiz or quiz['correct_option'] < 0:
        return

    groups = db.get_bot_groups(bot_id)
    target_groups = [g for g in groups if g['group_id'] != mgmt_gid]

    success, fail = 0, 0
    start = asyncio.get_event_loop().time()

    for grp in target_groups:
        try:
            sent = await app.bot.send_poll(
                chat_id=grp['group_id'],
                question=quiz['question'],
                options=quiz['options'],
                type='quiz',
                correct_option_id=quiz['correct_option'],
                explanation=quiz.get('explanation') or None,
                is_anonymous=False,
            )
            db.add_quiz_send(
                quiz['id'], grp['group_id'], sent.message_id,
                sent.poll.id if sent.poll else ""
            )
            success += 1
        except Exception as e:
            logger.warning(f"[auto_distribute] Failed for group {grp['group_id']}: {e}")
            fail += 1

    elapsed = round(asyncio.get_event_loop().time() - start, 1)

    # Edit the countdown message with the final report
    try:
        await app.bot.edit_message_text(
            chat_id=status_chat_id,
            message_id=status_msg_id,
            text=(
                f"📊 <b>Quiz Distribution Complete</b>\n\n"
                f"✅ Sent: <b>{success}</b> group(s)\n"
                f"❌ Failed: <b>{fail}</b>\n"
                f"⏱️ Time: <b>{elapsed}s</b>"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


# ─── /send — manual override ──────────────────────────────────────────────────

async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Manual override: reply to a saved quiz poll in the management group
    with /send to distribute it immediately (bypasses the 30-second wait).
    Useful if auto-distribution was skipped or you want to resend.
    """
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)

    if bot_info and bot_info['status'] == 'inactive':
        await send_inactive_msg(update)
        return

    if not is_subowner(bot_id, update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot owner can send quizzes.")
        return

    settings = db.get_bot_settings(bot_id)
    mgmt_gid = (settings or {}).get('quiz_management_group_id')

    if not mgmt_gid or update.effective_chat.id != int(mgmt_gid):
        await update.message.reply_text(
            "⚠️ /send only works in the quiz management group.\n"
            "Reply to a quiz poll with /send to distribute it immediately."
        )
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "↩️ Reply to a quiz poll message with /send to distribute it."
        )
        return

    quiz = db.get_quiz_by_mgmt_msg(bot_id, update.message.reply_to_message.message_id)
    if not quiz:
        await update.message.reply_text(
            "❌ No saved quiz found for that message.\n"
            "Send a quiz poll here first — the bot will save it automatically."
        )
        return

    if quiz['correct_option'] < 0:
        await update.message.reply_text(
            "⚠️ <b>Correct answer not set!</b>\n\n"
            "Reply to the quiz poll with the correct option (1/2/3/4 or A/B/C/D) first.",
            parse_mode=ParseMode.HTML
        )
        return

    groups = db.get_bot_groups(bot_id)
    target_groups = [g for g in groups if g['group_id'] != int(mgmt_gid)]

    if not target_groups:
        await update.message.reply_text(
            "⚠️ No connected groups yet! Add the bot to groups first."
        )
        return

    status_msg = await update.message.reply_text(
        f"⏳ Sending to {len(target_groups)} group(s)…"
    )
    success, fail = 0, 0
    start = asyncio.get_event_loop().time()

    for grp in target_groups:
        try:
            sent = await ctx.application.bot.send_poll(
                chat_id=grp['group_id'],
                question=quiz['question'],
                options=quiz['options'],
                type='quiz',
                correct_option_id=quiz['correct_option'],
                explanation=quiz.get('explanation') or None,
                is_anonymous=False,
            )
            db.add_quiz_send(quiz['id'], grp['group_id'], sent.message_id,
                             sent.poll.id if sent.poll else "")
            success += 1
        except Exception as e:
            logger.warning(f"cmd_send failed for group {grp['group_id']}: {e}")
            fail += 1

    elapsed = round(asyncio.get_event_loop().time() - start, 1)
    await status_msg.edit_text(
        f"📊 <b>Quiz Distribution Report</b>\n\n"
        f"✅ Sent: <b>{success}</b> group(s)\n"
        f"❌ Failed: <b>{fail}</b>\n"
        f"⏱️ Time: <b>{elapsed}s</b>",
        parse_mode=ParseMode.HTML
    )


# ─── Poll answer handler ──────────────────────────────────────────────────────

# ─── Congratulation & Roast message pools ─────────────────────────────────────

_CORRECT_MSGS = [
    "🎉 Waah {name}! Bilkul sahi jawab! <b>+{marks}</b> marks mil gaye! 🔥 Tu toh genius hai!",
    "🏆 {name} ne ek aur sahi jawab diya! <b>+{marks}</b> marks! Aage bhi aise hi chamkate raho! ✨",
    "🧠 Dimag toh hai {name} ke paas! Sahi jawab! <b>+{marks}</b> marks pocket mein! 💰",
    "💯 {name} — Perfect! Yahi toh chahiye tha! <b>+{marks}</b> marks add ho gaye! 🎯",
    "🌟 Kya baat hai {name}! Sahi pakda! <b>+{marks}</b> marks! Leaderboard mein aur upar jaoge! 🚀",
    "🔥 {name} is on fire! Correct answer! <b>+{marks}</b> marks! Koi rokne wala nahi hai! 💪",
    "🎊 Zabardast {name}! Bilkul sahi! <b>+{marks}</b> marks! Tu toh topper material hai! 📚",
    "😎 {name} ne fir se baazi maari! Correct! <b>+{marks}</b> marks! Champion ka jawaab! 🏅",
    "🥇 {name} — Gold standard answer! <b>+{marks}</b> marks! Keep it up! 👑",
    "⚡ {name} ne lightning speed se sahi jawab diya! <b>+{marks}</b> marks! Unbeatable! 🏆",
    "🎯 Bullseye {name}! Sahi jawab! <b>+{marks}</b> marks! Tu kahaan se padhta hai yaar? 📖",
    "✅ Correct! {name} phir se sab ko peeche chhod gaya! <b>+{marks}</b> marks mila! 😏",
    "🌈 Wah wah {name}! Ekdum sahi! <b>+{marks}</b> marks! Duniya dekh rahi hai tujhe! 🌍",
    "💥 {name} ka jawab CORRECT! <b>+{marks}</b> marks! Yeh banda rok nahi sakta koi! 🛑❌",
    "🦁 {name} jaise sher ka jawab — bilkul sahi! <b>+{marks}</b> marks! Roar! 🔊",
]

_WRONG_MSGS = [
    "😂 Arre {name}! Yeh kya jawab diya? <b>{marks}</b> marks! Kal thoda padhke aana! 📖",
    "🤦 {name} bhai... itna asaan sawal tha! <b>{marks}</b> marks! Kitaab kab se dost bani? 😅",
    "💀 {name} ka jawab sun ke toh question bhi ro pada! <b>{marks}</b> marks! Koshish karo! 😭",
    "🙈 {name} ne jo jawab diya woh sun ke teacher retire ho gayi! <b>{marks}</b> marks! 😆",
    "🤡 {name} — Confidence full, knowledge zero! <b>{marks}</b> marks! Google karo bhai! 🔍",
    "😬 {name} bhai, yeh wala jawab toh dictionary mein bhi galat likha hua hoga! <b>{marks}</b> marks!",
    "🫠 {name} ka jawab dekh ke AI bhi confuse ho gaya! <b>{marks}</b> marks! Kal aana! 📅",
    "😏 {name}, andaaze se jawab diya? Andaaza bhi galat! <b>{marks}</b> marks! Try again! 🎲",
    "🪄 {name} ne jawab aise diya jaise magic se aayega... nahi aaya! <b>{marks}</b> marks! ✨❌",
    "📉 {name} ka score dekhke leaderboard bhi sharmaaya! <b>{marks}</b> marks! Himmat rakho! 💪",
    "🤭 {name} bhai, ispe toh Google bhi tujhse agree nahi karega! <b>{marks}</b> marks! 😂",
    "🫣 {name} ne jawab chhupaane ki koshish ki... lekin galat tha fir bhi! <b>{marks}</b> marks!",
    "🐢 {name} — Slow bhi, galat bhi! <b>{marks}</b> marks! Koi nahi, agle quiz mein dekh lena! 🔄",
    "😴 {name} ne neend mein jawab diya lagta hai! <b>{marks}</b> marks! Uthke padhlo! ⏰",
    "🎭 {name} ka jawab ek nayi comedy movie ki script ban sakti hai! <b>{marks}</b> marks! 🎬",
]


async def poll_answer_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import random
    bot_id = get_bot_id_from_app(ctx.application)
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    first_name = answer.user.first_name or "User"
    db.upsert_bot_user(bot_id, user_id, answer.user.username, first_name)

    quiz_info = db.get_quiz_by_poll_id(poll_id)
    if not quiz_info:
        return

    selected = answer.option_ids[0] if answer.option_ids else None
    if selected is None:
        return  # user retracted answer

    is_correct = (selected == quiz_info['correct_option'])
    marks = MARKS_CORRECT if is_correct else MARKS_WRONG

    db.record_attempt(
        bot_id=bot_id,
        quiz_id=quiz_info['quiz_id'],
        poll_id=poll_id,
        user_id=user_id,
        group_id=quiz_info['group_id'],
        selected_option=selected,
        is_correct=is_correct,
        marks=marks
    )

    # ── Send congratulation or roast to the group ─────────────────────────────
    group_id = quiz_info['group_id']
    user_link = f'<a href="tg://user?id={user_id}">{first_name}</a>'
    marks_display = f"+{marks}" if marks > 0 else str(marks)

    pool = _CORRECT_MSGS if is_correct else _WRONG_MSGS
    template = random.choice(pool)
    msg = template.format(name=user_link, marks=marks_display)

    try:
        await ctx.application.bot.send_message(
            chat_id=group_id,
            text=msg,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"Could not send feedback to group {group_id}: {e}")


# ─── /help ────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 <b>Quiz Bot — Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "👤 <b>For Everyone</b>\n"
        "┌ /start — Welcome message & bot info\n"
        "├ /help — Show this commands list\n"
        "├ /leaderboard — Top scorers of this group\n"
        "└ /myRank — Your personal rank & score\n\n"

        "📝 <b>How Quizzes Work</b>\n"
        "┌ Quiz polls are sent here automatically\n"
        "├ Answer the poll to earn marks\n"
        "├ ✅ Correct answer → <b>+4 marks</b>\n"
        "└ ❌ Wrong answer → <b>-1 mark</b>\n\n"

        "🏆 <b>Leaderboard</b>\n"
        "└ Top scorers announced daily at 10 PM\n\n"

        "💡 <i>Use /adminhelp to see owner/admin commands</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ─── /adminhelp ───────────────────────────────────────────────────────────────

async def cmd_adminhelp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        await update.message.reply_text("⛔ This command is only for the bot owner.")
        return

    text = (
        "🛡️ <b>Admin & Owner Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "⚙️ <b>Bot Setup (Owner)</b>\n"
        "┌ /start — Open settings panel\n"
        "├ /setmgmt — Set this group as quiz management group\n"
        "│   (run this in the group you'll send quizzes from)\n"
        "└ /status — Show bot status & connected groups count\n\n"

        "📤 <b>Quiz Flow (Owner)</b>\n"
        "┌ 1. Send a Quiz poll in the management group\n"
        "├ 2. Reply to that poll with correct option: <code>1/2/3/4</code> or <code>A/B/C/D</code>\n"
        "├ 3. Quiz auto-distributes to all groups in 30 seconds\n"
        "└ /send — Manual override: reply to a saved quiz poll to send immediately\n\n"

        "📊 <b>Statistics (Owner)</b>\n"
        "┌ /stats — Total users, groups, quizzes sent\n"
        "└ /leaderboard — Group leaderboard (works everywhere)\n\n"

        "📣 <b>Broadcast (Owner)</b>\n"
        "┌ /broadcast <code>[text]</code> — Send a message to all bot users\n"
        "└ /forward — Reply to a message to forward it to all users\n\n"

        "🔗 <b>Force Join (Owner)</b>\n"
        "┌ /fjoin <code>[link]</code> — Set a force-join channel link\n"
        "└ /removefjoin — Remove the force-join requirement\n\n"

        "🔧 <b>Main Admin Only</b>\n"
        "┌ /activate — Activate this bot\n"
        "├ /inactive — Deactivate this bot\n"
        "└ /botstatus — Show current active/inactive status\n\n"

        "💡 <i>Users can use /help to see their commands</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ─── Group tracking ───────────────────────────────────────────────────────────

async def chat_member_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    new_status = result.new_chat_member.status

    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        db.upsert_bot_group(bot_id, chat.id, chat.title, chat.username or "", chat.type)
        if chat.type in ('group', 'supergroup'):
            try:
                await ctx.application.bot.send_message(
                    chat.id,
                    "👋 <b>Thanks for adding me!</b>\n\n"
                    "I'm a Quiz Bot. The bot owner will send quizzes here automatically. "
                    "Use /leaderboard to see rankings!",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
    elif new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        db.remove_bot_group(bot_id, chat.id)


# ─── /leaderboard ─────────────────────────────────────────────────────────────

async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)
    if bot_info and bot_info['status'] == 'inactive':
        await send_inactive_msg(update)
        return
    # Check force join
    settings = db.get_bot_settings(bot_id)
    if settings and settings.get('force_join_chat_id'):
        if not await check_force_join(bot_id, update.effective_user.id, ctx.application):
            await send_force_join_msg(update, settings)
            return

    if update.effective_chat.type in ('group', 'supergroup'):
        group_id = update.effective_chat.id
        group_name = update.effective_chat.title
        lb = db.get_group_leaderboard(bot_id, group_id)
        if not lb:
            await update.message.reply_text("📊 No quiz attempts yet in this group!")
            return

        chat_link = f"<a href='https://t.me/{update.effective_chat.username}'>{group_name}</a>" if update.effective_chat.username else group_name
        ist = pytz.timezone(TIMEZONE)
        date_str = datetime.now(ist).strftime("%d %B %Y")

        text = f"🏆 <b>Leaderboard — {chat_link}</b>\n"
        text += f"📅 <i>{date_str}</i>\n"
        text += "━" * 28 + "\n\n"

        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(lb[:20]):
            rank_icon = medals[i] if i < 3 else f"#{i+1}"
            name = entry.get('first_name') or "User"
            name_link = user_link(entry['user_id'], name)
            text += (
                f"{rank_icon} {name_link}\n"
                f"   ✅ {entry['correct']} correct | ❌ {entry['wrong']} wrong | "
                f"📝 {entry['total_attempts']} attempted | 🏅 {entry['total_marks']} pts\n\n"
            )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
    else:
        # Private chat — show global
        lb = db.get_global_leaderboard(bot_id, limit=GLOBAL_LEADERBOARD_LIMIT)
        if not lb:
            await update.message.reply_text("📊 No quiz attempts yet!")
            return
        ist = pytz.timezone(TIMEZONE)
        date_str = datetime.now(ist).strftime("%d %B %Y")
        text = f"🌍 <b>Global Leaderboard (Top {GLOBAL_LEADERBOARD_LIMIT})</b>\n"
        text += f"📅 <i>{date_str}</i>\n"
        text += "━" * 28 + "\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(lb):
            rank_icon = medals[i] if i < 3 else f"#{i+1}"
            name = entry.get('first_name') or "User"
            text += f"{rank_icon} {user_link(entry['user_id'], name)} — 🏅 {entry['total_marks']} pts\n"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ─── /myRank ──────────────────────────────────────────────────────────────────

async def cmd_myrank(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)
    if bot_info and bot_info['status'] == 'inactive':
        await send_inactive_msg(update)
        return
    settings = db.get_bot_settings(bot_id)
    if settings and settings.get('force_join_chat_id'):
        if not await check_force_join(bot_id, update.effective_user.id, ctx.application):
            await send_force_join_msg(update, settings)
            return

    user = update.effective_user
    global_rank = db.get_user_global_rank(bot_id, user.id)

    if update.effective_chat.type in ('group', 'supergroup'):
        group_rank = db.get_user_rank_in_group(bot_id, user.id, update.effective_chat.id)
        text = (
            f"📊 <b>Your Rankings</b>\n\n"
            f"👤 {user_link(user.id, user.first_name)}\n\n"
            f"🏘️ <b>In {update.effective_chat.title}:</b>\n"
        )
        if group_rank:
            text += (
                f"  🏆 Rank: #{group_rank['rank']} out of {group_rank['total_users']}\n"
                f"  ✅ Correct: {group_rank.get('correct', 0)}\n"
                f"  ❌ Wrong: {group_rank.get('wrong', 0)}\n"
                f"  📝 Attempted: {group_rank.get('total_attempts', 0)}\n"
                f"  🏅 Total Marks: {group_rank.get('total_marks', 0)}\n\n"
            )
        else:
            text += "  No attempts yet in this group.\n\n"
        text += "🌍 <b>Global:</b>\n"
        if global_rank:
            text += (
                f"  🏆 Rank: #{global_rank['rank']} out of {global_rank['total_users']}\n"
                f"  🏅 Total Marks: {global_rank.get('total_marks', 0)}\n"
            )
        else:
            text += "  No global attempts yet.\n"
    else:
        text = f"🌍 <b>Your Global Rank</b>\n\n👤 {user_link(user.id, user.first_name)}\n\n"
        if global_rank:
            text += (
                f"🏆 Rank: #{global_rank['rank']} out of {global_rank['total_users']}\n"
                f"✅ Correct: {global_rank.get('correct', 0)}\n"
                f"❌ Wrong: {global_rank.get('wrong', 0)}\n"
                f"📝 Attempted: {global_rank.get('total_attempts', 0)}\n"
                f"🏅 Total Marks: {global_rank.get('total_marks', 0)}\n"
            )
        else:
            text += "You haven't attempted any quizzes yet!"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ─── Subowner commands ────────────────────────────────────────────────────────

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    if update.effective_chat.type not in ('private',):
        return
    stats = db.get_subbot_stats(bot_id)
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total Users: <b>{stats['total_users']}</b>\n"
        f"🏘️ Total Groups: <b>{stats['total_groups']}</b>\n"
        f"📝 Quizzes Sent: <b>{stats['total_quizzes_sent']}</b>\n"
        f"✅ Answers Marked: <b>{stats['total_attempts']}</b>\n\n"
        f"🕐 Generated at: {stats['generated_at']}",
        parse_mode=ParseMode.HTML
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    bot_info = db.get_bot_by_id(bot_id)
    if bot_info['status'] == 'active':
        text = "🟢 <b>Bot Status: ACTIVE</b>\n\nYour bot is running smoothly! ✅"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data=f"open_settings:{bot_id}")]])
    else:
        text = ("🔴 <b>Bot Status: INACTIVE</b>\n\n"
                "Your bot is currently not working.\n"
                "Please contact the admin to reactivate it.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Contact for Activation", url=OWNER_CONTACT_LINK)],
            [InlineKeyboardButton("◀️ Back", callback_data=f"open_settings:{bot_id}")],
        ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def cmd_broadcast_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /broadcast to send it to all users and groups.")
        return
    users = db.get_bot_users(bot_id)
    groups = db.get_bot_groups(bot_id)
    ok, fail = 0, 0
    for u in users:
        try:
            await update.message.reply_to_message.copy(chat_id=u['user_id'])
            ok += 1
        except Exception:
            fail += 1
    for g in groups:
        try:
            await update.message.reply_to_message.copy(chat_id=g['group_id'])
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(f"📢 Broadcast done!\n✅ Sent: {ok}\n❌ Failed: {fail}")


async def cmd_forward_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /forward.")
        return
    users = db.get_bot_users(bot_id)
    groups = db.get_bot_groups(bot_id)
    ok, fail = 0, 0
    for u in users:
        try:
            await update.message.reply_to_message.forward(chat_id=u['user_id'])
            ok += 1
        except Exception:
            fail += 1
    for g in groups:
        try:
            await update.message.reply_to_message.forward(chat_id=g['group_id'])
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(f"📤 Forward done!\n✅ Sent: {ok}\n❌ Failed: {fail}")


async def cmd_fjoin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /fjoin <channel or group link>\nExample: /fjoin https://t.me/mychannel")
        return
    link = args[0].strip()
    try:
        # Try to get chat id from link
        username = link.split("t.me/")[-1].strip("/")
        chat = await ctx.application.bot.get_chat(f"@{username}")
        db.update_bot_settings(bot_id, force_join_link=link, force_join_chat_id=chat.id)
        await update.message.reply_text(
            f"✅ <b>Force Join set!</b>\n\n"
            f"Users must join <b>{chat.title}</b> to use this bot.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Could not set force join.\nError: {e}\n\n"
                                        "Make sure the bot is an admin of that channel/group.")


async def cmd_removefjoin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_subowner(bot_id, update.effective_user.id):
        return
    db.update_bot_settings(bot_id, force_join_link=None, force_join_chat_id=None)
    await update.message.reply_text("✅ <b>Force Join removed!</b>\nUsers can now use the bot freely.", parse_mode=ParseMode.HTML)


# ─── Main admin commands (in subbots) ────────────────────────────────────────

async def cmd_botstatus_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_main_admin(update.effective_user.id):
        return
    bot_info = db.get_bot_by_id(bot_id)
    stats = db.get_subbot_stats(bot_id)
    status_icon = "🟢" if bot_info['status'] == 'active' else "🔴"
    await update.message.reply_text(
        f"{status_icon} <b>Bot Status: {bot_info['status'].upper()}</b>\n\n"
        f"🤖 {bot_info['bot_name']} (@{bot_info['bot_username']})\n"
        f"👥 Users: {stats['total_users']}\n"
        f"🏘️ Groups: {stats['total_groups']}\n"
        f"📝 Quizzes Sent: {stats['total_quizzes_sent']}\n"
        f"✅ Attempts: {stats['total_attempts']}",
        parse_mode=ParseMode.HTML
    )


async def cmd_activate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_main_admin(update.effective_user.id):
        return
    db.set_bot_status(bot_id, 'active')
    await update.message.reply_text("✅ <b>Bot has been ACTIVATED!</b>\nAll features are now working.", parse_mode=ParseMode.HTML)


async def cmd_inactive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = get_bot_id_from_app(ctx.application)
    if not is_main_admin(update.effective_user.id):
        return
    db.set_bot_status(bot_id, 'inactive')
    await update.message.reply_text("🔴 <b>Bot has been DEACTIVATED!</b>\nUsers will see an inactive message.", parse_mode=ParseMode.HTML)


# ─── Daily leaderboard scheduler ─────────────────────────────────────────────

async def send_daily_leaderboards(ctx: ContextTypes.DEFAULT_TYPE):
    bot_id = ctx.job.data['bot_id']
    bot_info = db.get_bot_by_id(bot_id)
    if not bot_info or bot_info['status'] != 'active':
        return

    groups = db.get_bot_groups(bot_id)
    ist = pytz.timezone(TIMEZONE)
    date_str = datetime.now(ist).strftime("%d %B %Y")
    medals = ["🥇", "🥈", "🥉"]

    # Global leaderboard
    global_lb = db.get_global_leaderboard(bot_id, limit=GLOBAL_LEADERBOARD_LIMIT)
    global_text = f"🌍 <b>Global Leaderboard — Top {GLOBAL_LEADERBOARD_LIMIT}</b>\n"
    global_text += f"📅 <i>{date_str}</i>\n"
    global_text += "━" * 30 + "\n\n"
    if global_lb:
        for i, entry in enumerate(global_lb):
            rank_icon = medals[i] if i < 3 else f"#{i+1}"
            name = entry.get('first_name') or "User"
            global_text += f"{rank_icon} {user_link(entry['user_id'], name)} — 🏅 {entry['total_marks']} pts\n"
    else:
        global_text += "No attempts yet!"

    for grp in groups:
        group_id = grp['group_id']
        group_name = grp['group_name']
        group_username = grp.get('group_username', '')
        settings = db.get_bot_settings(bot_id)
        mgmt_gid = (settings or {}).get('quiz_management_group_id')
        if group_id == mgmt_gid:
            continue

        # Group leaderboard
        lb = db.get_group_leaderboard(bot_id, group_id)
        if lb:
            chat_link = (f"<a href='https://t.me/{group_username}'>{group_name}</a>"
                         if group_username else group_name)
            text = f"🏆 <b>Daily Leaderboard — {chat_link}</b>\n"
            text += f"📅 <i>{date_str}</i>\n"
            text += "━" * 30 + "\n\n"
            for i, entry in enumerate(lb[:20]):
                rank_icon = medals[i] if i < 3 else f"#{i+1}"
                name = entry.get('first_name') or "User"
                text += (
                    f"{rank_icon} {user_link(entry['user_id'], name)} | "
                    f"✅{entry['correct']} ❌{entry['wrong']} 🏅{entry['total_marks']}pts\n"
                )
            try:
                await ctx.application.bot.send_message(
                    group_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
                )
            except Exception as e:
                logger.warning(f"Failed to send group LB to {group_id}: {e}")

        # Global leaderboard
        try:
            await ctx.application.bot.send_message(
                group_id, global_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Failed to send global LB to {group_id}: {e}")


# ─── Handle all inactive-bot commands ────────────────────────────────────────

async def gate_inactive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Universal pre-check for inactive bots (non-owner messages)."""
    bot_id = get_bot_id_from_app(ctx.application)
    bot_info = db.get_bot_by_id(bot_id)
    user = update.effective_user
    if not bot_info or not user:
        return
    if bot_info['status'] == 'inactive' and not is_subowner(bot_id, user.id) and not is_main_admin(user.id):
        await send_inactive_msg(update)
        raise Exception("bot_inactive")


# ─── Build subbot application ─────────────────────────────────────────────────

def build_subbot_app(token: str, bot_id: int) -> Application:
    from config import LEADERBOARD_HOUR, LEADERBOARD_MINUTE, TIMEZONE
    import pytz
    from datetime import time as dt_time

    app = (
        Application.builder()
        .token(token)
        .build()
    )
    app.bot_data['bot_id'] = bot_id

    # Settings conversation
    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_set_welcome, pattern=r"^set_welcome:\d+$"),
            CallbackQueryHandler(cb_set_mgmt_group, pattern=r"^set_mgmt_group:\d+$"),
            CallbackQueryHandler(cb_set_join_link, pattern=r"^set_join_link:\d+$"),
            CallbackQueryHandler(cb_set_owner_link, pattern=r"^set_owner_link:\d+$"),
        ],
        states={
            SET_WELCOME_TEXT: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receive_welcome_text),
            ],
            SET_MGMT_GROUP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_mgmt_group),
            ],
            SET_JOIN_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_join_link),
            ],
            SET_OWNER_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_owner_link),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cb_settings_back, pattern=r"^settings_back:\d+$"),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("adminhelp", cmd_adminhelp))
    app.add_handler(CommandHandler("setmgmt", cmd_setmgmt))
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("myRank", cmd_myrank))
    # Subowner commands
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast_sub))
    app.add_handler(CommandHandler("forward", cmd_forward_sub))
    app.add_handler(CommandHandler("fjoin", cmd_fjoin))
    app.add_handler(CommandHandler("removefjoin", cmd_removefjoin))
    # Main admin commands
    app.add_handler(CommandHandler("botstatus", cmd_botstatus_admin))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CommandHandler("inactive", cmd_inactive))

    app.add_handler(settings_conv)
    app.add_handler(CallbackQueryHandler(cb_open_settings, pattern=r"^open_settings:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_settings_back, pattern=r"^settings_back:\d+$"))

    # Poll handlers
    app.add_handler(MessageHandler(filters.POLL, receive_poll))
    app.add_handler(PollAnswerHandler(poll_answer_handler))

    # Correct-option reply handler (management group: owner replies with "2" etc.)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.REPLY & ~filters.COMMAND,
        receive_correct_option
    ))

    # Group tracking
    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))

    # Schedule daily leaderboard at 10 PM IST
    ist_tz = pytz.timezone(TIMEZONE)
    app.job_queue.run_daily(
        send_daily_leaderboards,
        time=dt_time(hour=LEADERBOARD_HOUR, minute=LEADERBOARD_MINUTE, tzinfo=ist_tz),
        data={'bot_id': bot_id},
        name=f"daily_lb_{bot_id}"
    )

    return app
