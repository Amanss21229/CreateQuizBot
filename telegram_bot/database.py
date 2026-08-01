import sqlite3
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")   # wait up to 30s on lock
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id     INTEGER PRIMARY KEY,
        username    TEXT,
        first_name  TEXT,
        last_name   TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS bots (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        token        TEXT UNIQUE NOT NULL,
        bot_username TEXT,
        bot_name     TEXT,
        owner_id     INTEGER NOT NULL,
        status       TEXT DEFAULT 'active',
        created_at   TEXT DEFAULT (datetime('now')),
        deleted_at   TEXT
    );

    CREATE TABLE IF NOT EXISTS bot_users (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id     INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        username   TEXT,
        first_name TEXT,
        joined_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(bot_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS bot_groups (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id         INTEGER NOT NULL,
        group_id       INTEGER NOT NULL,
        group_name     TEXT,
        group_username TEXT,
        group_type     TEXT,
        language       TEXT DEFAULT 'en',
        added_at       TEXT DEFAULT (datetime('now')),
        UNIQUE(bot_id, group_id)
    );

    CREATE TABLE IF NOT EXISTS bot_settings (
        bot_id                        INTEGER PRIMARY KEY,
        welcome_text                  TEXT DEFAULT 'Welcome! 🎯 I am a Quiz Bot.',
        welcome_image_file_id         TEXT,
        quiz_management_group_id      INTEGER,
        quiz_management_group_name    TEXT,
        join_for_updates_link         TEXT,
        meet_owner_link               TEXT,
        force_join_link               TEXT,
        force_join_chat_id            INTEGER,
        language                      TEXT DEFAULT 'en',
        FOREIGN KEY (bot_id) REFERENCES bots(id)
    );

    CREATE TABLE IF NOT EXISTS quizzes (
        id                           INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id                       INTEGER NOT NULL,
        question                     TEXT NOT NULL,
        options                      TEXT NOT NULL,
        correct_option               INTEGER NOT NULL,
        explanation                  TEXT,
        mgmt_group_message_id        INTEGER,
        confirmation_msg_id          INTEGER,
        created_at                   TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS quiz_sends (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id   INTEGER NOT NULL,
        group_id  INTEGER NOT NULL,
        message_id INTEGER,
        poll_id   TEXT,
        sent_at   TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id          INTEGER NOT NULL,
        quiz_id         INTEGER NOT NULL,
        poll_id         TEXT NOT NULL,
        user_id         INTEGER NOT NULL,
        group_id        INTEGER NOT NULL,
        selected_option INTEGER,
        is_correct      INTEGER DEFAULT 0,
        marks           INTEGER DEFAULT 0,
        attempted_at    TEXT DEFAULT (datetime('now')),
        UNIQUE(poll_id, user_id)
    );
    """)
    conn.commit()

    # ── Migrations: add columns that may be missing in older DBs ──────────────
    migrations = [
        ("quizzes",       "confirmation_msg_id", "INTEGER DEFAULT 0"),
        ("bot_settings",  "language",            "TEXT DEFAULT 'en'"),
        ("bot_groups",    "language",            "TEXT DEFAULT 'en'"),
    ]
    for table, column, col_def in migrations:
        existing = [
            row[1]
            for row in c.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if column not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    conn.commit()
    conn.close()


# ─── User helpers ─────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, first_name: str, last_name: str = ""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO users(user_id,username,first_name,last_name) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, last_name=excluded.last_name",
        (user_id, username or "", first_name or "", last_name or "")
    )
    conn.commit()
    conn.close()


def get_all_users() -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_users() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


# ─── Bot helpers ──────────────────────────────────────────────────────────────

def add_bot(token: str, bot_username: str, bot_name: str, owner_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO bots(token,bot_username,bot_name,owner_id) VALUES(?,?,?,?)",
        (token, bot_username, bot_name, owner_id)
    )
    bot_id = c.lastrowid
    c.execute(
        "INSERT OR IGNORE INTO bot_settings(bot_id) VALUES(?)",
        (bot_id,)
    )
    conn.commit()
    conn.close()
    return bot_id


def get_bot_by_token(token: str) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bots WHERE token=? AND status!='deleted'", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_bot_by_id(bot_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_bots_by_owner(owner_id: int) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM bots WHERE owner_id=? AND status!='deleted' ORDER BY created_at DESC",
        (owner_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_active_bots() -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bots WHERE status='active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_bots() -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bots WHERE status!='deleted' ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_bot_status(bot_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE bots SET status=? WHERE id=?", (status, bot_id))
    conn.commit()
    conn.close()


def delete_bot(bot_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE bots SET status='deleted', deleted_at=datetime('now') WHERE id=?",
        (bot_id,)
    )
    conn.commit()
    conn.close()


def count_bots_by_status(status: str) -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM bots WHERE status=?", (status,)).fetchone()[0]
    conn.close()
    return n


def count_all_bots() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM bots WHERE status!='deleted'").fetchone()[0]
    conn.close()
    return n


# ─── Bot settings ─────────────────────────────────────────────────────────────

def get_bot_settings(bot_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM bot_settings WHERE bot_id=?", (bot_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_bot_settings(bot_id: int, **kwargs):
    if not kwargs:
        return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [bot_id]
    conn = get_conn()
    conn.execute(f"UPDATE bot_settings SET {cols} WHERE bot_id=?", vals)
    conn.commit()
    conn.close()


def get_bot_language(bot_id: int) -> str:
    """Return the language code for a bot ('en' or 'hi'). Defaults to 'en'."""
    conn = get_conn()
    row = conn.execute(
        "SELECT language FROM bot_settings WHERE bot_id=?", (bot_id,)
    ).fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return 'en'


def set_bot_language(bot_id: int, language: str):
    """Set the language for a bot ('en' or 'hi')."""
    conn = get_conn()
    conn.execute(
        "UPDATE bot_settings SET language=? WHERE bot_id=?", (language, bot_id)
    )
    conn.commit()
    conn.close()


def get_group_language(bot_id: int, group_id: int) -> str:
    """Return the language for a specific group ('en' or 'hi'). Defaults to 'en'."""
    conn = get_conn()
    row = conn.execute(
        "SELECT language FROM bot_groups WHERE bot_id=? AND group_id=?",
        (bot_id, group_id)
    ).fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return 'en'


def set_group_language(bot_id: int, group_id: int, language: str):
    """Set the language for a specific group ('en' or 'hi')."""
    conn = get_conn()
    conn.execute(
        "UPDATE bot_groups SET language=? WHERE bot_id=? AND group_id=?",
        (language, bot_id, group_id)
    )
    conn.commit()
    conn.close()


# ─── Bot users ────────────────────────────────────────────────────────────────

def upsert_bot_user(bot_id: int, user_id: int, username: str, first_name: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO bot_users(bot_id,user_id,username,first_name) VALUES(?,?,?,?) "
        "ON CONFLICT(bot_id,user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
        (bot_id, user_id, username or "", first_name or "")
    )
    conn.commit()
    conn.close()


def count_bot_users(bot_id: int) -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM bot_users WHERE bot_id=?", (bot_id,)).fetchone()[0]
    conn.close()
    return n


def get_bot_users(bot_id: int) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bot_users WHERE bot_id=?", (bot_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Bot groups ───────────────────────────────────────────────────────────────

def upsert_bot_group(bot_id: int, group_id: int, group_name: str, group_username: str, group_type: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO bot_groups(bot_id,group_id,group_name,group_username,group_type) VALUES(?,?,?,?,?) "
        "ON CONFLICT(bot_id,group_id) DO UPDATE SET group_name=excluded.group_name, group_username=excluded.group_username",
        (bot_id, group_id, group_name or "", group_username or "", group_type or "")
    )
    conn.commit()
    conn.close()


def remove_bot_group(bot_id: int, group_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM bot_groups WHERE bot_id=? AND group_id=?", (bot_id, group_id))
    conn.commit()
    conn.close()


def get_bot_groups(bot_id: int) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bot_groups WHERE bot_id=?", (bot_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_bot_groups(bot_id: int) -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM bot_groups WHERE bot_id=?", (bot_id,)).fetchone()[0]
    conn.close()
    return n


# ─── Quiz helpers ─────────────────────────────────────────────────────────────

def add_quiz(bot_id: int, question: str, options: list, correct_option: int,
             explanation: str, mgmt_msg_id: int, confirmation_msg_id: int = 0) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO quizzes(bot_id,question,options,correct_option,explanation,"
        "mgmt_group_message_id,confirmation_msg_id) VALUES(?,?,?,?,?,?,?)",
        (bot_id, question, json.dumps(options), correct_option,
         explanation or "", mgmt_msg_id, confirmation_msg_id)
    )
    quiz_id = c.lastrowid
    conn.commit()
    conn.close()
    return quiz_id


def update_quiz_correct_option(quiz_id: int, correct_option: int):
    conn = get_conn()
    conn.execute("UPDATE quizzes SET correct_option=? WHERE id=?",
                 (correct_option, quiz_id))
    conn.commit()
    conn.close()


def update_quiz_confirmation_msg(quiz_id: int, confirmation_msg_id: int):
    conn = get_conn()
    conn.execute("UPDATE quizzes SET confirmation_msg_id=? WHERE id=?",
                 (confirmation_msg_id, quiz_id))
    conn.commit()
    conn.close()


def get_quiz_by_mgmt_msg(bot_id: int, msg_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM quizzes WHERE bot_id=? AND mgmt_group_message_id=?",
        (bot_id, msg_id)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['options'] = json.loads(d['options'])
        return d
    return None


def get_quiz_by_confirmation_msg(bot_id: int, confirmation_msg_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM quizzes WHERE bot_id=? AND confirmation_msg_id=?",
        (bot_id, confirmation_msg_id)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['options'] = json.loads(d['options'])
        return d
    return None


def get_quiz_by_id(quiz_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['options'] = json.loads(d['options'])
        return d
    return None


def add_quiz_send(quiz_id: int, group_id: int, message_id: int, poll_id: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO quiz_sends(quiz_id,group_id,message_id,poll_id) VALUES(?,?,?,?)",
        (quiz_id, group_id, message_id, poll_id)
    )
    conn.commit()
    conn.close()


def get_quiz_by_poll_id(poll_id: str) -> Optional[Dict]:
    """Find quiz and group from a poll_id."""
    conn = get_conn()
    row = conn.execute(
        "SELECT qs.quiz_id, qs.group_id, q.bot_id, q.correct_option "
        "FROM quiz_sends qs JOIN quizzes q ON qs.quiz_id=q.id "
        "WHERE qs.poll_id=?",
        (poll_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_quizzes_sent(bot_id: int) -> int:
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM quiz_sends qs JOIN quizzes q ON qs.quiz_id=q.id WHERE q.bot_id=?",
        (bot_id,)
    ).fetchone()[0]
    conn.close()
    return n


def count_attempts(bot_id: int) -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE bot_id=?", (bot_id,)).fetchone()[0]
    conn.close()
    return n


# ─── Quiz attempts ────────────────────────────────────────────────────────────

def record_attempt(bot_id: int, quiz_id: int, poll_id: str, user_id: int,
                   group_id: int, selected_option: int, is_correct: bool, marks: int):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO quiz_attempts(bot_id,quiz_id,poll_id,user_id,group_id,selected_option,is_correct,marks) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (bot_id, quiz_id, poll_id, user_id, group_id, selected_option, int(is_correct), marks)
    )
    conn.commit()
    conn.close()


# ─── Leaderboard helpers ──────────────────────────────────────────────────────

def get_group_leaderboard(bot_id: int, group_id: int) -> List[Dict]:
    """Get leaderboard for a specific group."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            bu.user_id,
            bu.username,
            bu.first_name,
            COUNT(qa.id) AS total_attempts,
            SUM(CASE WHEN qa.is_correct=1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN qa.is_correct=0 AND qa.selected_option IS NOT NULL THEN 1 ELSE 0 END) AS wrong,
            COALESCE(SUM(qa.marks), 0) AS total_marks
        FROM bot_users bu
        LEFT JOIN quiz_attempts qa
            ON qa.user_id=bu.user_id AND qa.bot_id=bu.bot_id AND qa.group_id=?
        WHERE bu.bot_id=?
        GROUP BY bu.user_id
        HAVING total_attempts > 0 OR total_marks > 0
        ORDER BY total_marks DESC, correct DESC
    """, (group_id, bot_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_global_leaderboard(bot_id: int, limit: int = 50) -> List[Dict]:
    """Get global leaderboard across all groups for a bot."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            bu.user_id,
            bu.username,
            bu.first_name,
            COALESCE(SUM(qa.marks), 0) AS total_marks,
            SUM(CASE WHEN qa.is_correct=1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN qa.is_correct=0 AND qa.selected_option IS NOT NULL THEN 1 ELSE 0 END) AS wrong,
            COUNT(qa.id) AS total_attempts
        FROM bot_users bu
        LEFT JOIN quiz_attempts qa ON qa.user_id=bu.user_id AND qa.bot_id=bu.bot_id
        WHERE bu.bot_id=?
        GROUP BY bu.user_id
        ORDER BY total_marks DESC, correct DESC
        LIMIT ?
    """, (bot_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_rank_in_group(bot_id: int, user_id: int, group_id: int) -> Dict:
    lb = get_group_leaderboard(bot_id, group_id)
    for i, entry in enumerate(lb):
        if entry['user_id'] == user_id:
            entry['rank'] = i + 1
            entry['total_users'] = len(lb)
            return entry
    return {}


def get_user_global_rank(bot_id: int, user_id: int) -> Dict:
    lb = get_global_leaderboard(bot_id, limit=9999)
    for i, entry in enumerate(lb):
        if entry['user_id'] == user_id:
            entry['rank'] = i + 1
            entry['total_users'] = len(lb)
            return entry
    return {}


# ─── Stats helpers ────────────────────────────────────────────────────────────

def get_main_bot_stats() -> Dict:
    conn = get_conn()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_bots = conn.execute("SELECT COUNT(*) FROM bots WHERE status!='deleted'").fetchone()[0]
    active_bots = conn.execute("SELECT COUNT(*) FROM bots WHERE status='active'").fetchone()[0]
    inactive_bots = conn.execute("SELECT COUNT(*) FROM bots WHERE status='inactive'").fetchone()[0]
    deleted_bots = conn.execute("SELECT COUNT(*) FROM bots WHERE status='deleted'").fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "total_bots": total_bots,
        "active_bots": active_bots,
        "inactive_bots": inactive_bots,
        "deleted_bots": deleted_bots,
    }


def get_subbot_stats(bot_id: int) -> Dict:
    conn = get_conn()
    total_users = conn.execute("SELECT COUNT(*) FROM bot_users WHERE bot_id=?", (bot_id,)).fetchone()[0]
    total_groups = conn.execute("SELECT COUNT(*) FROM bot_groups WHERE bot_id=?", (bot_id,)).fetchone()[0]
    total_quizzes = conn.execute(
        "SELECT COUNT(*) FROM quiz_sends qs JOIN quizzes q ON qs.quiz_id=q.id WHERE q.bot_id=?",
        (bot_id,)
    ).fetchone()[0]
    total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE bot_id=?", (bot_id,)).fetchone()[0]
    conn.close()
    return {
        "total_users": total_users,
        "total_groups": total_groups,
        "total_quizzes_sent": total_quizzes,
        "total_attempts": total_attempts,
        "generated_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
    }


def get_bot_full_stats(bot_id: int) -> Dict:
    """Full stats including owner info, channels, admins."""
    conn = get_conn()
    bot = conn.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
    if not bot:
        conn.close()
        return {}
    bot = dict(bot)
    owner = conn.execute("SELECT * FROM users WHERE user_id=?", (bot['owner_id'],)).fetchone()
    total_users = conn.execute("SELECT COUNT(*) FROM bot_users WHERE bot_id=?", (bot_id,)).fetchone()[0]
    groups = conn.execute(
        "SELECT * FROM bot_groups WHERE bot_id=? AND group_type IN ('group','supergroup')",
        (bot_id,)
    ).fetchall()
    channels = conn.execute(
        "SELECT * FROM bot_groups WHERE bot_id=? AND group_type='channel'",
        (bot_id,)
    ).fetchall()
    conn.close()
    return {
        "bot": bot,
        "owner": dict(owner) if owner else {},
        "total_users": total_users,
        "total_groups": len(groups),
        "total_channels": len(channels),
        "groups": [dict(g) for g in groups],
        "channels": [dict(c) for c in channels],
    }
