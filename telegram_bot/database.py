import psycopg2
import psycopg2.extras
import psycopg2.pool
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DATABASE_URL

# ── Connection pool (thread-safe — subbots run in separate threads) ────────────
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 20, DATABASE_URL)
    return _pool


class _DB:
    """Context manager: borrows a connection from the pool, auto-commits/rollbacks."""
    def __enter__(self):
        self.conn = _get_pool().getconn()
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self.cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.cur.close()
        _get_pool().putconn(self.conn)


def init_db():
    """Verify Neon DB connectivity. Tables are created via neon_schema.sql."""
    with _DB() as cur:
        cur.execute("SELECT 1")


# ─── User helpers ─────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, first_name: str, last_name: str = ""):
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE
              SET username=EXCLUDED.username,
                  first_name=EXCLUDED.first_name,
                  last_name=EXCLUDED.last_name
            """,
            (user_id, username or "", first_name or "", last_name or "")
        )


def get_all_users() -> List[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM users ORDER BY created_at")
        return [dict(r) for r in cur.fetchall()]


def count_users() -> int:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        return cur.fetchone()["n"]


# ─── Bot helpers ──────────────────────────────────────────────────────────────

def add_bot(token: str, bot_username: str, bot_name: str, owner_id: int) -> int:
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO bots(token, bot_username, bot_name, owner_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (token, bot_username, bot_name, owner_id)
        )
        bot_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO bot_settings(bot_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (bot_id,)
        )
    return bot_id


def get_bot_by_token(token: str) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM bots WHERE token=%s AND status!='deleted'",
            (token,)
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_bot_by_id(bot_id: int) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM bots WHERE id=%s", (bot_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_bots_by_owner(owner_id: int) -> List[Dict]:
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM bots WHERE owner_id=%s AND status!='deleted' ORDER BY created_at DESC",
            (owner_id,)
        )
        return [dict(r) for r in cur.fetchall()]


def get_all_active_bots() -> List[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM bots WHERE status='active'")
        return [dict(r) for r in cur.fetchall()]


def get_all_bots() -> List[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM bots WHERE status!='deleted' ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]


def set_bot_status(bot_id: int, status: str):
    with _DB() as cur:
        cur.execute("UPDATE bots SET status=%s WHERE id=%s", (status, bot_id))


def delete_bot(bot_id: int):
    with _DB() as cur:
        cur.execute(
            "UPDATE bots SET status='deleted', deleted_at=NOW() WHERE id=%s",
            (bot_id,)
        )


def count_bots_by_status(status: str) -> int:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bots WHERE status=%s", (status,))
        return cur.fetchone()["n"]


def count_all_bots() -> int:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bots WHERE status!='deleted'")
        return cur.fetchone()["n"]


# ─── Bot settings ─────────────────────────────────────────────────────────────

def get_bot_settings(bot_id: int) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM bot_settings WHERE bot_id=%s", (bot_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def update_bot_settings(bot_id: int, **kwargs):
    if not kwargs:
        return
    cols = ", ".join(f"{k}=%s" for k in kwargs)
    vals = list(kwargs.values()) + [bot_id]
    with _DB() as cur:
        cur.execute(f"UPDATE bot_settings SET {cols} WHERE bot_id=%s", vals)


def get_bot_language(bot_id: int) -> str:
    with _DB() as cur:
        cur.execute("SELECT language FROM bot_settings WHERE bot_id=%s", (bot_id,))
        row = cur.fetchone()
    return row["language"] if row and row["language"] else "en"


def set_bot_language(bot_id: int, language: str):
    with _DB() as cur:
        cur.execute(
            "UPDATE bot_settings SET language=%s WHERE bot_id=%s",
            (language, bot_id)
        )
    migrate_legacy_force_joins()


# ─── Force-join helpers ───────────────────────────────────────────────────────

def get_force_joins(bot_id: int) -> list:
    with _DB() as cur:
        cur.execute(
            "SELECT chat_id, link, title FROM bot_force_joins WHERE bot_id=%s ORDER BY id",
            (bot_id,)
        )
        return [dict(r) for r in cur.fetchall()]


def add_force_join(bot_id: int, chat_id: int, link: str, title: str = ""):
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO bot_force_joins(bot_id, chat_id, link, title)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(bot_id, chat_id) DO UPDATE
              SET link=EXCLUDED.link, title=EXCLUDED.title
            """,
            (bot_id, chat_id, link, title or "")
        )


def remove_all_force_joins(bot_id: int):
    with _DB() as cur:
        cur.execute("DELETE FROM bot_force_joins WHERE bot_id=%s", (bot_id,))


def migrate_legacy_force_joins():
    """One-time migration: copy old single force_join from bot_settings → bot_force_joins."""
    with _DB() as cur:
        cur.execute(
            """
            SELECT bot_id, force_join_link, force_join_chat_id
            FROM bot_settings
            WHERE force_join_link IS NOT NULL AND force_join_chat_id IS NOT NULL
            """
        )
        rows = cur.fetchall()
        for row in rows:
            cur.execute(
                """
                INSERT INTO bot_force_joins(bot_id, chat_id, link, title)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(bot_id, chat_id) DO NOTHING
                """,
                (row["bot_id"], row["force_join_chat_id"], row["force_join_link"], "Channel")
            )


def get_group_language(bot_id: int, group_id: int) -> str:
    with _DB() as cur:
        cur.execute(
            "SELECT language FROM bot_groups WHERE bot_id=%s AND group_id=%s",
            (bot_id, group_id)
        )
        row = cur.fetchone()
    return row["language"] if row and row["language"] else "en"


def set_group_language(bot_id: int, group_id: int, language: str):
    with _DB() as cur:
        cur.execute(
            "UPDATE bot_groups SET language=%s WHERE bot_id=%s AND group_id=%s",
            (language, bot_id, group_id)
        )


# ─── Bot users ────────────────────────────────────────────────────────────────

def upsert_bot_user(bot_id: int, user_id: int, username: str, first_name: str):
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO bot_users(bot_id, user_id, username, first_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(bot_id, user_id) DO UPDATE
              SET username=EXCLUDED.username, first_name=EXCLUDED.first_name
            """,
            (bot_id, user_id, username or "", first_name or "")
        )


def count_bot_users(bot_id: int) -> int:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bot_users WHERE bot_id=%s", (bot_id,))
        return cur.fetchone()["n"]


def get_bot_users(bot_id: int) -> List[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM bot_users WHERE bot_id=%s", (bot_id,))
        return [dict(r) for r in cur.fetchall()]


# ─── Bot groups ───────────────────────────────────────────────────────────────

def upsert_bot_group(bot_id: int, group_id: int, group_name: str, group_username: str, group_type: str):
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO bot_groups(bot_id, group_id, group_name, group_username, group_type)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(bot_id, group_id) DO UPDATE
              SET group_name=EXCLUDED.group_name,
                  group_username=EXCLUDED.group_username
            """,
            (bot_id, group_id, group_name or "", group_username or "", group_type or "")
        )


def remove_bot_group(bot_id: int, group_id: int):
    with _DB() as cur:
        cur.execute(
            "DELETE FROM bot_groups WHERE bot_id=%s AND group_id=%s",
            (bot_id, group_id)
        )


def get_bot_groups(bot_id: int) -> List[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM bot_groups WHERE bot_id=%s", (bot_id,))
        return [dict(r) for r in cur.fetchall()]


def count_bot_groups(bot_id: int) -> int:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bot_groups WHERE bot_id=%s", (bot_id,))
        return cur.fetchone()["n"]


# ─── Quiz helpers ─────────────────────────────────────────────────────────────

def add_quiz(bot_id: int, question: str, options: list, correct_option: int,
             explanation: str, mgmt_msg_id: int, confirmation_msg_id: int = 0) -> int:
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO quizzes(bot_id, question, options, correct_option, explanation,
                                mgmt_group_message_id, confirmation_msg_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (bot_id, question, json.dumps(options), correct_option,
             explanation or "", mgmt_msg_id, confirmation_msg_id)
        )
        return cur.fetchone()["id"]


def update_quiz_correct_option(quiz_id: int, correct_option: int):
    with _DB() as cur:
        cur.execute(
            "UPDATE quizzes SET correct_option=%s WHERE id=%s",
            (correct_option, quiz_id)
        )


def update_quiz_confirmation_msg(quiz_id: int, confirmation_msg_id: int):
    with _DB() as cur:
        cur.execute(
            "UPDATE quizzes SET confirmation_msg_id=%s WHERE id=%s",
            (confirmation_msg_id, quiz_id)
        )


def get_quiz_by_mgmt_msg(bot_id: int, msg_id: int) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM quizzes WHERE bot_id=%s AND mgmt_group_message_id=%s",
            (bot_id, msg_id)
        )
        row = cur.fetchone()
    if row:
        d = dict(row)
        d["options"] = json.loads(d["options"])
        return d
    return None


def get_quiz_by_confirmation_msg(bot_id: int, confirmation_msg_id: int) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM quizzes WHERE bot_id=%s AND confirmation_msg_id=%s",
            (bot_id, confirmation_msg_id)
        )
        row = cur.fetchone()
    if row:
        d = dict(row)
        d["options"] = json.loads(d["options"])
        return d
    return None


def get_quiz_by_id(quiz_id: int) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute("SELECT * FROM quizzes WHERE id=%s", (quiz_id,))
        row = cur.fetchone()
    if row:
        d = dict(row)
        d["options"] = json.loads(d["options"])
        return d
    return None


def add_quiz_send(quiz_id: int, group_id: int, message_id: int, poll_id: str):
    with _DB() as cur:
        cur.execute(
            "INSERT INTO quiz_sends(quiz_id, group_id, message_id, poll_id) VALUES (%s, %s, %s, %s)",
            (quiz_id, group_id, message_id, poll_id)
        )


def get_quiz_by_poll_id(poll_id: str) -> Optional[Dict]:
    with _DB() as cur:
        cur.execute(
            """
            SELECT qs.quiz_id, qs.group_id, q.bot_id, q.correct_option
            FROM quiz_sends qs
            JOIN quizzes q ON qs.quiz_id = q.id
            WHERE qs.poll_id = %s
            """,
            (poll_id,)
        )
        row = cur.fetchone()
    return dict(row) if row else None


def count_quizzes_sent(bot_id: int) -> int:
    with _DB() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM quiz_sends qs
            JOIN quizzes q ON qs.quiz_id = q.id
            WHERE q.bot_id = %s
            """,
            (bot_id,)
        )
        return cur.fetchone()["n"]


def count_attempts(bot_id: int) -> int:
    with _DB() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM quiz_attempts WHERE bot_id=%s",
            (bot_id,)
        )
        return cur.fetchone()["n"]


# ─── Quiz attempts ────────────────────────────────────────────────────────────

def record_attempt(bot_id: int, quiz_id: int, poll_id: str, user_id: int,
                   group_id: int, selected_option: int, is_correct: bool, marks: int):
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO quiz_attempts(bot_id, quiz_id, poll_id, user_id, group_id,
                                      selected_option, is_correct, marks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(poll_id, user_id) DO NOTHING
            """,
            (bot_id, quiz_id, poll_id, user_id, group_id,
             selected_option, int(is_correct), marks)
        )


# ─── Leaderboard helpers ──────────────────────────────────────────────────────

def get_group_leaderboard(bot_id: int, group_id: int) -> List[Dict]:
    with _DB() as cur:
        cur.execute(
            """
            SELECT
                bu.user_id,
                bu.username,
                bu.first_name,
                COUNT(qa.id)                                                        AS total_attempts,
                SUM(CASE WHEN qa.is_correct=1 THEN 1 ELSE 0 END)                   AS correct,
                SUM(CASE WHEN qa.is_correct=0 AND qa.selected_option IS NOT NULL
                         THEN 1 ELSE 0 END)                                         AS wrong,
                COALESCE(SUM(qa.marks), 0)                                          AS total_marks
            FROM bot_users bu
            LEFT JOIN quiz_attempts qa
                ON qa.user_id = bu.user_id
               AND qa.bot_id  = bu.bot_id
               AND qa.group_id = %s
            WHERE bu.bot_id = %s
            GROUP BY bu.user_id, bu.username, bu.first_name
            HAVING COUNT(qa.id) > 0 OR COALESCE(SUM(qa.marks), 0) > 0
            ORDER BY total_marks DESC, correct DESC
            """,
            (group_id, bot_id)
        )
        return [dict(r) for r in cur.fetchall()]


def get_global_leaderboard(bot_id: int, limit: int = 50) -> List[Dict]:
    with _DB() as cur:
        cur.execute(
            """
            SELECT
                bu.user_id,
                bu.username,
                bu.first_name,
                COALESCE(SUM(qa.marks), 0)                                          AS total_marks,
                SUM(CASE WHEN qa.is_correct=1 THEN 1 ELSE 0 END)                   AS correct,
                SUM(CASE WHEN qa.is_correct=0 AND qa.selected_option IS NOT NULL
                         THEN 1 ELSE 0 END)                                         AS wrong,
                COUNT(qa.id)                                                        AS total_attempts
            FROM bot_users bu
            LEFT JOIN quiz_attempts qa
                ON qa.user_id = bu.user_id AND qa.bot_id = bu.bot_id
            WHERE bu.bot_id = %s
            GROUP BY bu.user_id, bu.username, bu.first_name
            ORDER BY total_marks DESC, correct DESC
            LIMIT %s
            """,
            (bot_id, limit)
        )
        return [dict(r) for r in cur.fetchall()]


def get_user_rank_in_group(bot_id: int, user_id: int, group_id: int) -> Dict:
    lb = get_group_leaderboard(bot_id, group_id)
    for i, entry in enumerate(lb):
        if entry["user_id"] == user_id:
            entry["rank"] = i + 1
            entry["total_users"] = len(lb)
            return entry
    return {}


def get_user_global_rank(bot_id: int, user_id: int) -> Dict:
    lb = get_global_leaderboard(bot_id, limit=9999)
    for i, entry in enumerate(lb):
        if entry["user_id"] == user_id:
            entry["rank"] = i + 1
            entry["total_users"] = len(lb)
            return entry
    return {}


# ─── Stats helpers ────────────────────────────────────────────────────────────

def get_main_bot_stats() -> Dict:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        total_users = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM bots WHERE status!='deleted'")
        total_bots = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM bots WHERE status='active'")
        active_bots = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM bots WHERE status='inactive'")
        inactive_bots = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM bots WHERE status='deleted'")
        deleted_bots = cur.fetchone()["n"]
    return {
        "total_users": total_users,
        "total_bots": total_bots,
        "active_bots": active_bots,
        "inactive_bots": inactive_bots,
        "deleted_bots": deleted_bots,
    }


def get_subbot_stats(bot_id: int) -> Dict:
    with _DB() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM bot_users WHERE bot_id=%s", (bot_id,))
        total_users = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM bot_groups WHERE bot_id=%s", (bot_id,))
        total_groups = cur.fetchone()["n"]
        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM quiz_sends qs
            JOIN quizzes q ON qs.quiz_id = q.id
            WHERE q.bot_id = %s
            """,
            (bot_id,)
        )
        total_quizzes = cur.fetchone()["n"]
        cur.execute(
            "SELECT COUNT(*) AS n FROM quiz_attempts WHERE bot_id=%s",
            (bot_id,)
        )
        total_attempts = cur.fetchone()["n"]
    return {
        "total_users": total_users,
        "total_groups": total_groups,
        "total_quizzes_sent": total_quizzes,
        "total_attempts": total_attempts,
        "generated_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
    }


# ─── Log message mapping ──────────────────────────────────────────────────────

def save_log_message(log_msg_id: int, user_id: int, source_key: str):
    """Map a message in the log group back to the original sender + bot."""
    with _DB() as cur:
        cur.execute(
            """
            INSERT INTO log_messages(log_msg_id, user_id, source_key)
            VALUES (%s, %s, %s)
            ON CONFLICT(log_msg_id) DO NOTHING
            """,
            (log_msg_id, user_id, source_key),
        )


def get_log_message(log_msg_id: int) -> Optional[Dict]:
    """Return the log entry for a given log-group message id, or None."""
    with _DB() as cur:
        cur.execute(
            "SELECT * FROM log_messages WHERE log_msg_id = %s",
            (log_msg_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ─── Stats helpers ────────────────────────────────────────────────────────────

def get_bot_full_stats(bot_id: int) -> Dict:
    with _DB() as cur:
        cur.execute("SELECT * FROM bots WHERE id=%s", (bot_id,))
        bot = cur.fetchone()
        if not bot:
            return {}
        bot = dict(bot)
        cur.execute("SELECT * FROM users WHERE user_id=%s", (bot["owner_id"],))
        owner = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS n FROM bot_users WHERE bot_id=%s", (bot_id,))
        total_users = cur.fetchone()["n"]
        cur.execute(
            "SELECT * FROM bot_groups WHERE bot_id=%s AND group_type IN ('group','supergroup')",
            (bot_id,)
        )
        groups = cur.fetchall()
        cur.execute(
            "SELECT * FROM bot_groups WHERE bot_id=%s AND group_type='channel'",
            (bot_id,)
        )
        channels = cur.fetchall()
    return {
        "bot": bot,
        "owner": dict(owner) if owner else {},
        "total_users": total_users,
        "total_groups": len(groups),
        "total_channels": len(channels),
        "groups": [dict(g) for g in groups],
        "channels": [dict(c) for c in channels],
    }
