import os

# ─── Main Bot Configuration ───────────────────────────────────────────────────
MAIN_BOT_TOKEN = os.environ.get("MAIN_BOT_TOKEN")
if not MAIN_BOT_TOKEN:
    raise RuntimeError(
        "MAIN_BOT_TOKEN environment variable is not set. "
        "Set it to your bot token from @BotFather before starting."
    )

# Your Telegram numeric user ID (get it by sending /myid to the bot first time)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Database file path
DB_PATH = os.environ.get("DB_PATH", "quiz_bot.db")

# Timezone for daily leaderboard (Indian Standard Time)
TIMEZONE = "Asia/Kolkata"

# Daily leaderboard time (24-hour format, IST)
LEADERBOARD_HOUR = 22   # 10 PM
LEADERBOARD_MINUTE = 0

# Contact link for inactive bot (main owner's Telegram username)
OWNER_CONTACT_LINK = "https://t.me/Aman_PersonalBot"
OWNER_USERNAME = "@Aman_PersonalBot"

# Marking scheme
MARKS_CORRECT = 4
MARKS_WRONG = -1
MARKS_NOT_ATTEMPTED = 0

# Top N users for global leaderboard
GLOBAL_LEADERBOARD_LIMIT = 50
