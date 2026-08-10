"""
Main bot handlers — the central hub bot.
"""
import logging
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, RetryAfter, Forbidden, BadRequest

import database as db
from config import ADMIN_ID, OWNER_CONTACT_LINK, OWNER_USERNAME, LOG_GROUP_ID
import log_router

logger = logging.getLogger(__name__)

# User guidance and support links shown in the main bot's /start menu.
GUIDANCE_VIDEO_URL = "https://youtu.be/MgKKDL3552o?si=c-MDBuADT8e0SPy2"
OWNER_SUPPORT_URL = "https://t.me/Aman_PersonalBot"

# ─── Conversation states ──────────────────────────────────────────────────────
WAITING_TOKEN = 1
CONFIRM_DELETE = 2
# bot_manager is imported lazily to avoid circular imports

# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID


def user_link(user_id: int, name: str) -> str:
    return f"<a href='tg://user?id={user_id}'>{name}</a>"


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Create Quiz Bot", callback_data="create_bot")],
        [InlineKeyboardButton("📋 My Bots", callback_data="my_bots")],
        [InlineKeyboardButton("🎥 Tutorial: Create, Manage & Earn", url=GUIDANCE_VIDEO_URL)],
        [InlineKeyboardButton("🆘 Contact Owner for Help", url=OWNER_SUPPORT_URL)],
    ])


# ─── /start ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name or "")
    text = (
        f"👋 <b>Hello, {user.first_name}!</b>\n\n"
        "Welcome to <b>Quiz Bot Manager</b> 🎯\n\n"
        "I can help you create and manage your own Quiz Bots! "
        "Use the buttons below to get started.\n\n"
        "📌 <i>What would you like to do?</i>"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)


async def myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🪪 <b>Your Telegram User ID:</b>\n<code>{uid}</code>\n\n"
        "Set this as <code>ADMIN_ID</code> in your environment variables to activate admin access.",
        parse_mode=ParseMode.HTML
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 <b>Quiz Bot Manager — Help</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "👤 <b>For Everyone</b>\n"
        "┌ /start — Open the main menu\n"
        "├ /help — Show this help message\n"
        "└ /myid — Get your Telegram user ID\n\n"

        "🤖 <b>Managing Your Bots</b>\n"
        "┌ Tap <b>🤖 Create Quiz Bot</b> — Connect a new bot using its token\n"
        "└ Tap <b>📋 My Bots</b> — View status, stats, or delete your bots\n\n"

        "📝 <b>How to Get a Bot Token</b>\n"
        "┌ 1. Open @BotFather on Telegram\n"
        "├ 2. Send /newbot and follow the steps\n"
        "└ 3. Copy the token and paste it here\n\n"

        "💡 <i>Each bot you create becomes a full quiz bot your audience can use!</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ─── Create Bot flow ──────────────────────────────────────────────────────────

HOW_TO_GET_TOKEN = """
🤖 <b>How to Get Your Bot Token</b>

Follow these simple steps:

<b>Step 1</b> 👉 Open Telegram and search for <b>@BotFather</b>

<b>Step 2</b> 👉 Start a chat with BotFather and send:
<code>/newbot</code>

<b>Step 3</b> 👉 BotFather will ask for your <b>bot's name</b>
   ➡️ Example: <i>My Quiz Bot</i>

<b>Step 4</b> 👉 Then it asks for a <b>username</b> (must end with "bot")
   ➡️ Example: <i>myquizbot</i> or <i>my_quiz_bot</i>

<b>Step 5</b> 🎉 BotFather will send you a <b>token</b> that looks like:
<code>1234567890:ABCdefGhIjKlMnOpQrStUvWxYz123456789</code>

<b>Step 6</b> 📋 Copy that token and send it to me here!

━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ <b>Important:</b>
• Never share your token with anyone!
• The token gives full control over your bot.
• Keep it safe like a password.
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔽 <b>Now paste your bot token below:</b>
"""

CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_token")]])


async def cb_create_bot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(HOW_TO_GET_TOKEN, reply_markup=CANCEL_KB, parse_mode=ParseMode.HTML)
    return WAITING_TOKEN


async def receive_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import bot_manager
    token = update.message.text.strip()
    user = update.effective_user
    processing_msg = await update.message.reply_text("⏳ Validating your token, please wait...")

    # Basic format check
    if ":" not in token or len(token) < 30:
        await processing_msg.edit_text(
            "❌ <b>Invalid token format!</b>\n\n"
            "A valid token looks like:\n"
            "<code>1234567890:ABCdefGhIjKlMnOpQrStUvWxYz123456789</code>\n\n"
            "Please try again or press Cancel.",
            reply_markup=CANCEL_KB,
            parse_mode=ParseMode.HTML
        )
        return WAITING_TOKEN

    # Check if already registered
    existing = db.get_bot_by_token(token)
    if existing:
        await processing_msg.edit_text(
            "⚠️ <b>This bot is already registered!</b>\n\n"
            "This token belongs to a bot that's already connected to the system.\n"
            "Check <b>My Bots</b> to manage your existing bots.",
            reply_markup=CANCEL_KB,
            parse_mode=ParseMode.HTML
        )
        return WAITING_TOKEN

    # Validate via Telegram API
    try:
        from telegram import Bot
        test_bot = Bot(token=token)
        bot_info = await test_bot.get_me()
    except TelegramError as e:
        await processing_msg.edit_text(
            f"❌ <b>Token validation failed!</b>\n\n"
            f"Error: <code>{str(e)}</code>\n\n"
            "Please make sure you copied the token correctly and try again.",
            reply_markup=CANCEL_KB,
            parse_mode=ParseMode.HTML
        )
        return WAITING_TOKEN

    # Save to database
    bot_id = db.add_bot(token, bot_info.username, bot_info.full_name, user.id)

    # Launch the subbot
    try:
        await bot_manager.launch_subbot(bot_id, token)
        launch_status = "✅ Your bot is now <b>LIVE</b>!"
    except Exception as e:
        logger.error(f"Failed to launch subbot {bot_id}: {e}")
        launch_status = "⚠️ Bot registered, but failed to start automatically. Contact admin."

    await processing_msg.edit_text(
        f"🎉 <b>Bot Connected Successfully!</b>\n\n"
        f"🤖 <b>Name:</b> {bot_info.full_name}\n"
        f"👤 <b>Username:</b> @{bot_info.username}\n"
        f"🆔 <b>Bot ID:</b> <code>{bot_info.id}</code>\n\n"
        f"{launch_status}\n\n"
        f"🔗 You can now access your bot: @{bot_info.username}\n\n"
        "Use <b>My Bots</b> to manage it anytime!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="go_home")]]),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def cancel_token(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "❌ <b>Cancelled.</b>\n\n"
        "No worries! Come back whenever you're ready 😊"
    )
    await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# ─── My Bots flow ─────────────────────────────────────────────────────────────

async def cb_my_bots(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    bots = db.get_bots_by_owner(user_id)

    if not bots:
        await query.edit_message_text(
            "📋 <b>My Bots</b>\n\n"
            "You haven't connected any bots yet!\n\n"
            "Click <b>Create Quiz Bot</b> to get started 🚀",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Create Quiz Bot", callback_data="create_bot")],
                [InlineKeyboardButton("🏠 Home", callback_data="go_home")],
            ]),
            parse_mode=ParseMode.HTML
        )
        return

    status_icon = {"active": "🟢", "inactive": "🔴"}
    buttons = []
    for b in bots:
        icon = status_icon.get(b['status'], "⚪")
        buttons.append([InlineKeyboardButton(
            f"{icon} {b['bot_name']} (@{b['bot_username']})",
            callback_data=f"bot_menu:{b['id']}"
        )])
    buttons.append([InlineKeyboardButton("🏠 Home", callback_data="go_home")])

    await query.edit_message_text(
        f"📋 <b>My Bots</b> ({len(bots)} bot{'s' if len(bots) != 1 else ''})\n\n"
        "🟢 = Active  |  🔴 = Inactive\n\n"
        "Tap a bot to manage it:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML
    )


async def cb_bot_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = int(query.data.split(":")[1])
    bot = db.get_bot_by_id(bot_id)
    if not bot or bot['owner_id'] != update.effective_user.id:
        await query.answer("❌ Bot not found or access denied.", show_alert=True)
        return

    status_icon = "🟢 Active" if bot['status'] == 'active' else "🔴 Inactive"
    await query.edit_message_text(
        f"🤖 <b>{bot['bot_name']}</b>\n"
        f"👤 @{bot['bot_username']}\n"
        f"📊 Status: {status_icon}\n\n"
        "What would you like to do?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 Bot Status", callback_data=f"bot_status:{bot_id}")],
            [InlineKeyboardButton("📊 Bot Stats", callback_data=f"bot_stats:{bot_id}")],
            [InlineKeyboardButton("🗑️ Delete Bot", callback_data=f"bot_delete_confirm:{bot_id}")],
            [InlineKeyboardButton("◀️ Back", callback_data="my_bots")],
        ]),
        parse_mode=ParseMode.HTML
    )


async def cb_bot_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = int(query.data.split(":")[1])
    bot = db.get_bot_by_id(bot_id)
    if not bot or bot['owner_id'] != update.effective_user.id:
        await query.answer("Access denied.", show_alert=True)
        return

    if bot['status'] == 'active':
        status_text = (
            "🟢 <b>Bot Status: ACTIVE</b>\n\n"
            "✅ Your bot is running smoothly!\n"
            "All features are working normally."
        )
    else:
        status_text = (
            "🔴 <b>Bot Status: INACTIVE</b>\n\n"
            "⚠️ Your bot is currently not working.\n"
            "Please contact the admin to reactivate it."
        )

    await query.edit_message_text(
        f"🤖 <b>{bot['bot_name']}</b> (@{bot['bot_username']})\n\n"
        + status_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Contact Admin", url=OWNER_CONTACT_LINK)],
            [InlineKeyboardButton("◀️ Back", callback_data=f"bot_menu:{bot_id}")],
        ]),
        parse_mode=ParseMode.HTML
    )


async def cb_bot_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = int(query.data.split(":")[1])
    bot = db.get_bot_by_id(bot_id)
    if not bot or bot['owner_id'] != update.effective_user.id:
        await query.answer("Access denied.", show_alert=True)
        return

    full = db.get_bot_full_stats(bot_id)
    quizzes = db.count_quizzes_sent(bot_id)
    attempts = db.count_attempts(bot_id)

    groups_text = ""
    for g in full.get('groups', [])[:10]:
        if g.get('group_username'):
            groups_text += f"  • <a href='https://t.me/{g['group_username']}'>{g['group_name']}</a>\n"
        else:
            groups_text += f"  • {g['group_name']} (Private)\n"
    if len(full.get('groups', [])) > 10:
        groups_text += f"  ... and {len(full['groups']) - 10} more\n"
    if not groups_text:
        groups_text = "  None yet\n"

    await query.edit_message_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"🤖 <b>Name:</b> {bot['bot_name']}\n"
        f"👤 <b>Username:</b> @{bot['bot_username']}\n\n"
        f"👥 <b>Total Users:</b> {full['total_users']}\n"
        f"🏘️ <b>Total Groups:</b> {full['total_groups']}\n"
        f"📺 <b>Total Channels:</b> {full['total_channels']}\n"
        f"📝 <b>Total Quizzes Sent:</b> {quizzes}\n"
        f"✅ <b>Total Answers Marked:</b> {attempts}\n\n"
        f"🏘️ <b>Connected Groups:</b>\n{groups_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data=f"bot_menu:{bot_id}")],
        ]),
        parse_mode=ParseMode.HTML
    )


async def cb_bot_delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_id = int(query.data.split(":")[1])
    bot = db.get_bot_by_id(bot_id)
    if not bot or bot['owner_id'] != update.effective_user.id:
        await query.answer("Access denied.", show_alert=True)
        return

    await query.edit_message_text(
        f"⚠️ <b>Delete Bot Confirmation</b>\n\n"
        f"Are you sure you want to permanently delete:\n\n"
        f"🤖 <b>{bot['bot_name']}</b> (@{bot['bot_username']})\n\n"
        "⛔ This action <b>cannot be undone!</b>\n"
        "The bot will be completely disconnected from the system.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Delete It", callback_data=f"bot_delete_yes:{bot_id}")],
            [InlineKeyboardButton("❌ No, Keep It", callback_data=f"bot_menu:{bot_id}")],
        ]),
        parse_mode=ParseMode.HTML
    )


async def cb_bot_delete_yes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import bot_manager
    query = update.callback_query
    await query.answer()
    bot_id = int(query.data.split(":")[1])
    bot = db.get_bot_by_id(bot_id)
    if not bot or bot['owner_id'] != update.effective_user.id:
        await query.answer("Access denied.", show_alert=True)
        return

    bot_name = bot['bot_name']
    bot_username = bot['bot_username']

    # Stop the subbot
    await bot_manager.stop_subbot(bot_id)
    # Mark as deleted in DB
    db.delete_bot(bot_id)

    await query.edit_message_text(
        f"🗑️ <b>Bot Deleted Successfully</b>\n\n"
        f"✅ <b>{bot_name}</b> (@{bot_username}) has been permanently deleted.\n\n"
        "The bot has been disconnected from our system.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Home", callback_data="go_home")],
            [InlineKeyboardButton("📋 My Bots", callback_data="my_bots")],
        ]),
        parse_mode=ParseMode.HTML
    )


async def cb_go_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, ctx)


# ─── Admin commands ───────────────────────────────────────────────────────────

async def cmd_botstats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    stats = db.get_main_bot_stats()
    await update.message.reply_text(
        "📊 <b>Main Bot Statistics</b>\n\n"
        f"👥 Total Users: <b>{stats['total_users']}</b>\n"
        f"🤖 Total Bots: <b>{stats['total_bots']}</b>\n"
        f"🟢 Active Bots: <b>{stats['active_bots']}</b>\n"
        f"🔴 Inactive Bots: <b>{stats['inactive_bots']}</b>\n"
        f"🗑️ Deleted Bots: <b>{stats['deleted_bots']}</b>",
        parse_mode=ParseMode.HTML
    )


async def cmd_botlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    bots = db.get_all_bots()
    if not bots:
        await update.message.reply_text("No bots registered yet.")
        return
    icon = {"active": "🟢", "inactive": "🔴", "deleted": "🗑️"}
    lines = []
    for b in bots:
        lines.append(f"{icon.get(b['status'], '⚪')} <b>{b['bot_name']}</b> | @{b['bot_username']} | ID: <code>{b['id']}</code>")
    # Split into chunks if too long
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 3800:
            await update.message.reply_text(f"🤖 <b>Bot List</b>\n\n{chunk}", parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(f"🤖 <b>Bot List</b>\n\n{chunk}", parse_mode=ParseMode.HTML)


async def cmd_userlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("No users yet.")
        return
    lines = []
    for u in users:
        uname = f"@{u['username']}" if u['username'] else "N/A"
        lines.append(f"• {user_link(u['user_id'], u['first_name'])} | {uname} | <code>{u['user_id']}</code>")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 3800:
            await update.message.reply_text(f"👥 <b>User List</b>\n\n{chunk}", parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(f"👥 <b>User List</b>\n\n{chunk}", parse_mode=ParseMode.HTML)


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /broadcast to send it to all users and connected bots.")
        return
    msg = update.message.reply_to_message
    # Collect unique user IDs across main-bot users + all subbot users
    seen: set = set()
    user_ids = []
    for u in db.get_all_users():
        if u['user_id'] not in seen:
            seen.add(u['user_id'])
            user_ids.append(u['user_id'])
    for b in db.get_all_active_bots():
        for bu in db.get_bot_users(b['id']):
            if bu['user_id'] not in seen:
                seen.add(bu['user_id'])
                user_ids.append(bu['user_id'])

    status = await update.message.reply_text(f"📢 Broadcasting to {len(user_ids)} users…")
    ok, fail = 0, 0
    for uid in user_ids:
        try:
            await ctx.application.bot.copy_message(
                chat_id=uid,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await ctx.application.bot.copy_message(
                    chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
                ok += 1
            except Exception:
                fail += 1
        except (Forbidden, BadRequest):
            fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # gentle rate-limit

    await status.edit_text(f"📢 Broadcast complete!\n✅ Sent: {ok}\n❌ Failed: {fail}")


async def cmd_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /forward to forward it.")
        return
    msg = update.message.reply_to_message
    # Collect unique user IDs across main-bot users + all subbot users
    seen: set = set()
    user_ids = []
    for u in db.get_all_users():
        if u['user_id'] not in seen:
            seen.add(u['user_id'])
            user_ids.append(u['user_id'])
    for b in db.get_all_active_bots():
        for bu in db.get_bot_users(b['id']):
            if bu['user_id'] not in seen:
                seen.add(bu['user_id'])
                user_ids.append(bu['user_id'])

    status = await update.message.reply_text(f"📤 Forwarding to {len(user_ids)} users…")
    ok, fail = 0, 0
    for uid in user_ids:
        try:
            await ctx.application.bot.forward_message(
                chat_id=uid,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await ctx.application.bot.forward_message(
                    chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
                ok += 1
            except Exception:
                fail += 1
        except (Forbidden, BadRequest):
            fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    await status.edit_text(f"📤 Forward complete!\n✅ Sent: {ok}\n❌ Failed: {fail}")


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage:\n"
            "  /info @botusername  — look up a subbot\n"
            "  /info @username     — look up a user\n"
            "  /info user_id       — look up by numeric ID"
        )
        return
    query_str = args[0].lstrip("@")

    # ── Try as bot username ──────────────────────────────────────────────────
    bot_info = db.get_bot_by_username(query_str) if hasattr(db, 'get_bot_by_username') else None
    if bot_info is None:
        # Fallback: direct query
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM bots WHERE bot_username=? AND status!='deleted'", (query_str,)
        ).fetchone()
        conn.close()
        bot_info = dict(row) if row else None

    if bot_info:
        # Fetch owner info
        conn = db.get_conn()
        owner_row = conn.execute(
            "SELECT * FROM users WHERE user_id=?", (bot_info['owner_id'],)
        ).fetchone()
        conn.close()
        owner = dict(owner_row) if owner_row else {}
        user_bots = db.get_bots_by_owner(bot_info['owner_id'])
        await update.message.reply_text(
            f"🤖 <b>Bot Info</b>\n\n"
            f"Name: <b>{bot_info['bot_name']}</b>\n"
            f"Username: @{bot_info['bot_username']}\n"
            f"Status: <code>{bot_info['status']}</code>\n"
            f"ID: <code>{bot_info['id']}</code>\n\n"
            f"👤 <b>Owner:</b>\n"
            f"Name: {owner.get('first_name', 'N/A')}\n"
            f"ID: <code>{owner.get('user_id', 'N/A')}</code>\n"
            f"Username: @{owner.get('username', 'N/A')}\n"
            f"Total bots: {len(user_bots)}",
            parse_mode=ParseMode.HTML
        )
        return

    # ── Try as user (numeric ID or username) ────────────────────────────────
    conn = db.get_conn()
    try:
        uid = int(query_str)
        user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    except ValueError:
        user_row = conn.execute("SELECT * FROM users WHERE username=?", (query_str,)).fetchone()
    conn.close()

    if user_row:
        u = dict(user_row)
        user_bots = db.get_bots_by_owner(u['user_id'])
        bots_text = "".join(
            f"  • {b['bot_name']} (@{b['bot_username']}) [{b['status']}]\n"
            for b in user_bots
        )
        await update.message.reply_text(
            f"👤 <b>User Info</b>\n\n"
            f"Name: {u.get('first_name', 'N/A')}\n"
            f"ID: <code>{u['user_id']}</code>\n"
            f"Username: @{u.get('username', 'N/A')}\n\n"
            f"🤖 <b>Bots Created ({len(user_bots)}):</b>\n{bots_text or 'None'}",
            parse_mode=ParseMode.HTML
        )
        return

    await update.message.reply_text("❌ No bot or user found with that username/ID.")


async def _send_content(bot, chat_id: int, msg) -> bool:
    """Send message content to chat_id using the given bot (works cross-token)."""
    try:
        if msg.text:
            await bot.send_message(chat_id=chat_id, text=msg.text,
                                   entities=msg.entities or None)
        elif msg.photo:
            await bot.send_photo(chat_id=chat_id, photo=msg.photo[-1].file_id,
                                 caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.video:
            await bot.send_video(chat_id=chat_id, video=msg.video.file_id,
                                 caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.document:
            await bot.send_document(chat_id=chat_id, document=msg.document.file_id,
                                    caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.audio:
            await bot.send_audio(chat_id=chat_id, audio=msg.audio.file_id,
                                 caption=msg.caption, caption_entities=msg.caption_entities or None)
        elif msg.sticker:
            await bot.send_sticker(chat_id=chat_id, sticker=msg.sticker.file_id)
        elif msg.voice:
            await bot.send_voice(chat_id=chat_id, voice=msg.voice.file_id,
                                 caption=msg.caption)
        elif msg.video_note:
            await bot.send_video_note(chat_id=chat_id, video_note=msg.video_note.file_id)
        elif msg.animation:
            await bot.send_animation(chat_id=chat_id, animation=msg.animation.file_id,
                                     caption=msg.caption)
        else:
            return False
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        try:
            return await _send_content(bot, chat_id, msg)
        except Exception:
            return False
    except (Forbidden, BadRequest):
        return False
    except Exception:
        return False


async def cmd_globalforward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import bot_manager
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /Globalforward.")
        return
    msg = update.message.reply_to_message
    main_bot = ctx.application.bot

    # Collect unique recipients: {user_id: bot_to_use}
    # Main-bot users → send via main bot
    seen_users: set = set()
    main_user_ids = []
    for u in db.get_all_users():
        if u['user_id'] not in seen_users:
            seen_users.add(u['user_id'])
            main_user_ids.append(u['user_id'])

    # Subbot users/groups → send via each subbot's loop (cross-loop safe)
    subbot_tasks = []  # list of (loop, bot, chat_id)
    for b in db.get_all_active_bots():
        app = bot_manager.get_app(b['id'])
        loop = bot_manager.get_loop(b['id'])
        if not app or not loop or loop.is_closed():
            continue
        for bu in db.get_bot_users(b['id']):
            if bu['user_id'] not in seen_users:
                seen_users.add(bu['user_id'])
                subbot_tasks.append((loop, app.bot, bu['user_id']))
        settings = db.get_bot_settings(b['id'])
        mgmt_gid = (settings or {}).get('quiz_management_group_id')
        for g in db.get_bot_groups(b['id']):
            if g['group_id'] != mgmt_gid:
                subbot_tasks.append((loop, app.bot, g['group_id']))

    total = len(main_user_ids) + len(subbot_tasks)
    status = await update.message.reply_text(f"🌐 Global Forward: sending to {total} recipients…")
    ok, fail = 0, 0

    # Send via main bot to main-bot users
    for uid in main_user_ids:
        if await _send_content(main_bot, uid, msg):
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)

    # Send via subbots using run_coroutine_threadsafe → wrap_future
    futures = []
    for (loop, sbot, chat_id) in subbot_tasks:
        cf = asyncio.run_coroutine_threadsafe(_send_content(sbot, chat_id, msg), loop)
        futures.append(asyncio.wrap_future(cf))

    if futures:
        results = await asyncio.gather(*futures, return_exceptions=True)
        for r in results:
            if r is True:
                ok += 1
            else:
                fail += 1

    await status.edit_text(f"🌐 Global Forward complete!\n✅ Sent: {ok}\n❌ Failed: {fail}")


# ─── Log forwarding & reply routing ──────────────────────────────────────────

async def forward_to_log_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Forward any private non-command message to the log group."""
    await log_router.forward_to_log(update, ctx, "Main Bot", "main")


async def handle_log_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Route admin replies in the log group back to the original user."""
    await log_router.handle_log_reply(update, ctx)


# ─── Build application ────────────────────────────────────────────────────────

def build_main_app(token: str) -> Application:
    app = Application.builder().token(token).build()

    # Conversation: create bot
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_create_bot, pattern="^create_bot$")],
        states={
            WAITING_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_token),
                CallbackQueryHandler(cancel_token, pattern="^cancel_token$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_token, pattern="^cancel_token$"),
            CommandHandler("cancel", cancel_token),
        ],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("botstats", cmd_botstats))
    app.add_handler(CommandHandler("botlist", cmd_botlist))
    app.add_handler(CommandHandler("userlist", cmd_userlist))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("forward", cmd_forward))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("Globalforward", cmd_globalforward))

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(cb_my_bots, pattern="^my_bots$"))
    app.add_handler(CallbackQueryHandler(cb_bot_menu, pattern=r"^bot_menu:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_bot_status, pattern=r"^bot_status:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_bot_stats, pattern=r"^bot_stats:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_bot_delete_confirm, pattern=r"^bot_delete_confirm:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_bot_delete_yes, pattern=r"^bot_delete_yes:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_go_home, pattern="^go_home$"))

    # ── Log group: route admin replies back to original users ─────────────────
    if LOG_GROUP_ID:
        app.add_handler(MessageHandler(
            filters.Chat(LOG_GROUP_ID) & filters.REPLY,
            handle_log_reply,
        ))

    # ── Forward all private non-command messages to log group ─────────────────
    # group=1 so ConversationHandler in group=0 still processes the message first
    if LOG_GROUP_ID:
        app.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            forward_to_log_main,
        ), group=1)

    return app
