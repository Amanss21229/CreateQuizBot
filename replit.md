# Quiz Bot Manager

A Telegram bot system that lets users create and manage their own quiz bots (subbots). The main bot acts as a hub; subbots run as independent Telegram bots distributing quizzes to groups with leaderboards.

## Run & Operate

- `cd telegram_bot && python3 main.py` — start the main bot + all active subbots
- Set `ADMIN_ID` environment variable to your Telegram user ID (send `/myid` to the bot to find it)
- Set `MAIN_BOT_TOKEN` env var for production (already configured for dev)
- Set `DB_PATH` to `/data/quiz_bot.db` on Render (use a persistent disk)

## Stack

- Python 3.11
- python-telegram-bot v20.7 (async, with APScheduler job-queue)
- SQLite (via built-in sqlite3)
- pytz for IST timezone
- Threading: each subbot runs in its own thread with its own asyncio loop

## Where things live

```
telegram_bot/
├── main.py          — entry point (starts DB, subbots, main bot)
├── config.py        — all env-var-based configuration
├── database.py      — all SQLite schema + query functions
├── main_bot.py      — main hub bot handlers + admin commands
├── sub_bot.py       — quiz subbot handlers, quiz distribution, scheduler
├── bot_manager.py   — thread registry for managing running subbots
├── requirements.txt
├── Procfile         — for Render deployment
├── render.yaml      — Render deployment config
└── README.md        — full feature + deployment docs
```

## Architecture decisions

- Subbots run in daemon threads (one thread per bot) each with its own asyncio event loop — simple and isolated.
- Quiz polls are re-sent (not forwarded) to each group as new native Telegram quiz polls so answers are tracked per-group.
- PollAnswerHandler on each subbot tracks correct/wrong and updates marks (+4/−1).
- Daily 10 PM IST leaderboards are scheduled via APScheduler job_queue on each subbot.
- SQLite WAL mode for concurrent reads across threads.

## Product

Main bot (`@Aman_PersonalBot`):
- Users create quiz subbots by providing a BotFather token
- Manage subbots: view status, stats, delete
- Admin commands: /botstats, /botlist, /userlist, /broadcast, /forward, /info, /Globalforward

Subbots:
- Subowner sends quiz polls to a "management group", types `/send` in reply → bot distributes to all connected groups
- Auto leaderboards at 10 PM IST (group-specific + global top-50)
- Force-join gate, broadcast, forward, stats, /myRank, /leaderboard

## User preferences

- Python only
- Deploy on Render
- Bot username: @Aman_PersonalBot
- Contact link for inactive bots: https://t.me/Aman_PersonalBot

## Gotchas

- For force-join to work, the subbot must be an admin of the target channel/group.
- Quiz polls must be sent as "Quiz type" (not regular poll) in the management group.
- On Render, always mount a persistent disk at /data for the SQLite database.
- After redeploying, all active subbots are automatically relaunched from DB.
