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
from telegram.error import TelegramError

import database as db
from config import ADMIN_ID, OWNER_CONTACT_LINK, OWNER_USERNAME

logger = logging.getLogger(__name__)

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
        uname = f"@{g['group_username']}" if g['group_username'] else "Private"
        groups_text += f"  • {g['group_name']} ({uname})\n"
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
    users = db.get_all_users()
    bots = db.get_all_active_bots()
    ok, fail = 0, 0
    for u in users:
        try:
            await update.message.reply_to_message.copy(chat_id=u['user_id'])
            ok += 1
        except Exception:
            fail += 1
    # Also send to all subbot users
    for b in bots:
        bot_users = db.get_bot_users(b['id'])
        for bu in bot_users:
            try:
                await update.message.reply_to_message.copy(chat_id=bu['user_id'])
                ok += 1
            except Exception:
                fail += 1
    await update.message.reply_text(f"📢 Broadcast complete!\n✅ Sent: {ok}\n❌ Failed: {fail}")


async def cmd_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /forward to forward it.")
        return
    users = db.get_all_users()
    bots = db.get_all_active_bots()
    ok, fail = 0, 0
    for u in users:
        try:
            await update.message.reply_to_message.forward(chat_id=u['user_id'])
            ok += 1
        except Exception:
            fail += 1
    for b in bots:
        bot_users = db.get_bot_users(b['id'])
        for bu in bot_users:
            try:
                await update.message.reply_to_message.forward(chat_id=bu['user_id'])
                ok += 1
            except Exception:
                fail += 1
    await update.message.reply_text(f"📤 Forward complete!\n✅ Sent: {ok}\n❌ Failed: {fail}")


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /info @username or /info user_id")
        return
    query_str = args[0].lstrip("@")
    conn = __import__('database').get_conn()
    # Try as bot username
    bot_row = conn.execute(
        "SELECT * FROM bots WHERE bot_username=? AND status!='deleted'", (query_str,)
    ).fetchone()
    if bot_row:
        bot = dict(bot_row)
        owner = conn.execute("SELECT * FROM users WHERE user_id=?", (bot['owner_id'],)).fetchone()
        conn.close()
        owner_info = dict(owner) if owner else {}
        await update.message.reply_text(
            f"🤖 <b>Bot Info</b>\n\n"
            f"Name: {bot['bot_name']}\n"
            f"Username: @{bot['bot_username']}\n"
            f"Status: {bot['status']}\n\n"
            f"👤 <b>Owner:</b>\n"
            f"Name: {owner_info.get('first_name', 'N/A')}\n"
            f"ID: <code>{owner_info.get('user_id', 'N/A')}</code>\n"
            f"Username: @{owner_info.get('username', 'N/A')}",
            parse_mode=ParseMode.HTML
        )
        return
    # Try as user
    try:
        uid = int(query_str)
        user_row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    except ValueError:
        user_row = conn.execute("SELECT * FROM users WHERE username=?", (query_str,)).fetchone()
    conn.close()
    if user_row:
        u = dict(user_row)
        user_bots = db.get_bots_by_owner(u['user_id'])
        bots_text = ""
        for b in user_bots:
            bots_text += f"  • {b['bot_name']} (@{b['bot_username']}) [{b['status']}]\n"
        await update.message.reply_text(
            f"👤 <b>User Info</b>\n\n"
            f"Name: {u['first_name']}\n"
            f"ID: <code>{u['user_id']}</code>\n"
            f"Username: @{u.get('username', 'N/A')}\n\n"
            f"🤖 <b>Bots Created ({len(user_bots)}):</b>\n{bots_text or 'None'}",
            parse_mode=ParseMode.HTML
        )
        return
    await update.message.reply_text("❌ No bot or user found with that username/ID.")


async def cmd_globalforward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import bot_manager
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a message with /Globalforward.")
        return
    # Forward to all main-bot users
    users = db.get_all_users()
    ok, fail = 0, 0
    for u in users:
        try:
            await update.message.reply_to_message.forward(chat_id=u['user_id'])
            ok += 1
        except Exception:
            fail += 1
    # Forward to all subbot users + their groups via each subbot's application
    bots = db.get_all_active_bots()
    for b in bots:
        bot_users = db.get_bot_users(b['id'])
        bot_groups = db.get_bot_groups(b['id'])
        app = bot_manager.get_app(b['id'])
        if not app:
            continue
        for bu in bot_users:
            try:
                await app.bot.forward_message(chat_id=bu['user_id'],
                                              from_chat_id=update.message.reply_to_message.chat_id,
                                              message_id=update.message.reply_to_message.message_id)
                ok += 1
            except Exception:
                fail += 1
        for g in bot_groups:
            try:
                await app.bot.forward_message(chat_id=g['group_id'],
                                              from_chat_id=update.message.reply_to_message.chat_id,
                                              message_id=update.message.reply_to_message.message_id)
                ok += 1
            except Exception:
                fail += 1
    await update.message.reply_text(f"🌐 Global Forward complete!\n✅ Sent: {ok}\n❌ Failed: {fail}")


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

    return app
