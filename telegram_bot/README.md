# 🤖 Quiz Bot Manager

A powerful Telegram bot system that lets users create and manage their own quiz bots.

---

## 🚀 Features

### Main Bot
- **Create Quiz Bot** — Register any bot token to turn it into a quiz bot
- **My Bots** — Manage all your created bots (status, stats, delete)
- Inline keyboard-driven UI with cancel support

### Admin Commands (Main Bot Owner)
| Command | Description |
|---|---|
| `/botstats` | Total users, bots, active/inactive/deleted counts |
| `/botlist` | All registered bots with status |
| `/userlist` | All main bot users |
| `/broadcast` | Send a message to all users (reply to forward without sender name) |
| `/forward` | Forward a message to all users (shows sender name) |
| `/info @username` | Info about a bot or user |
| `/Globalforward` | Forward to all users + all subbot groups |
| `/myid` | Get your Telegram numeric user ID |

### Sub-Bots (Quiz Bots created by users)
- Welcome message with customisable image + text
- **Add me to Group**, **Join For Updates**, **Meet the Owner** buttons
- Quiz distribution to all connected groups
- Auto leaderboard every night at **10:00 PM IST**
- +4 correct / −1 wrong / 0 unattempted marking

### Sub-Bot Subowner Commands
| Command | Description |
|---|---|
| `/stats` | Total users, groups, quizzes sent, attempts |
| `/status` | Check if bot is active/inactive |
| `/setmgmt` | Set current group as quiz management group |
| `/send` | (Reply to quiz) Distribute quiz to all groups |
| `/broadcast` | Broadcast to all users and groups |
| `/forward` | Forward to all users and groups (shows sender) |
| `/fjoin <link>` | Set force-join channel/group |
| `/removefjoin` | Remove force-join requirement |
| `/leaderboard` | Show group or global leaderboard |
| `/myRank` | Show personal rank (group + global) |

### Main Admin Commands (Inside Sub-Bots)
| Command | Description |
|---|---|
| `/botstatus` | Detailed stats + active/inactive status |
| `/activate` | Activate an inactive bot |
| `/inactive` | Deactivate a bot |

---

## 🛠️ Setup

### 1. Install dependencies
```bash
cd telegram_bot
pip install -r requirements.txt
```

### 2. Set your Admin ID
Start the bot and send `/myid` to find your Telegram user ID, then set it:
```bash
export ADMIN_ID=123456789
```

### 3. Run locally
```bash
python main.py
```

---

## ☁️ Deploy on Render

1. Push this repo to GitHub
2. Create a new **Background Worker** service on [render.com](https://render.com)
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `python main.py`
5. Add **Environment Variables**:
   - `MAIN_BOT_TOKEN` — your bot token
   - `ADMIN_ID` — your Telegram user ID (run `/myid` first)
   - `DB_PATH` — `/data/quiz_bot.db`
6. Add a **Persistent Disk** mounted at `/data` (to preserve the database)
7. Deploy!

---

## 📐 Architecture

```
main.py
  └─ starts database
  └─ launches all active subbots (each in its own thread)
  └─ runs main bot (asyncio event loop)

bot_manager.py        — subbot thread registry
main_bot.py           — main bot handlers + admin commands
sub_bot.py            — quiz bot handlers + scheduler
database.py           — all SQLite operations
config.py             — environment-based configuration
```

---

## 📊 Marking Scheme
| Result | Marks |
|---|---|
| ✅ Correct answer | **+4** |
| ❌ Wrong answer | **−1** |
| ⏭️ Not attempted | **0** |

---

## ⚠️ Important Notes

- The bot token in `config.py` is just a fallback. **Always use environment variables in production.**
- For force-join to work, the sub-bot must be an **admin** of the channel/group.
- The database file is SQLite — for Render, always mount a persistent disk so data survives redeploys.
- Quiz polls must be sent as **Quiz type** (not regular polls) in the management group.
