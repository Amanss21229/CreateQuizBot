-- ============================================================
--  Quiz Bot Manager — Neon DB (PostgreSQL) Schema
--  Run this in your Neon SQL editor or psql client.
--  All statements use IF NOT EXISTS / DO NOTHING so they are
--  safe to re-run on a database that already has the tables.
-- ============================================================

-- ── Users (main-bot users) ────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Bots registered by users ──────────────────────────────
CREATE TABLE IF NOT EXISTS bots (
    id           BIGSERIAL PRIMARY KEY,
    token        TEXT UNIQUE NOT NULL,
    bot_username TEXT,
    bot_name     TEXT,
    owner_id     BIGINT NOT NULL,
    status       TEXT DEFAULT 'active',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);

-- ── Users who have interacted with a sub-bot ──────────────
CREATE TABLE IF NOT EXISTS bot_users (
    id         BIGSERIAL PRIMARY KEY,
    bot_id     BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    username   TEXT,
    first_name TEXT,
    joined_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (bot_id, user_id)
);

-- ── Groups/channels connected to a sub-bot ────────────────
CREATE TABLE IF NOT EXISTS bot_groups (
    id             BIGSERIAL PRIMARY KEY,
    bot_id         BIGINT NOT NULL,
    group_id       BIGINT NOT NULL,
    group_name     TEXT,
    group_username TEXT,
    group_type     TEXT,
    language       TEXT DEFAULT 'en',
    added_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (bot_id, group_id)
);

-- ── Per-bot settings ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_settings (
    bot_id                        BIGINT PRIMARY KEY,
    welcome_text                  TEXT DEFAULT 'Welcome! 🎯 I am a Quiz Bot.',
    welcome_image_file_id         TEXT,
    quiz_management_group_id      BIGINT,
    quiz_management_group_name    TEXT,
    join_for_updates_link         TEXT,
    meet_owner_link               TEXT,
    force_join_link               TEXT,
    force_join_chat_id            BIGINT,
    language                      TEXT DEFAULT 'en',
    CONSTRAINT fk_bot_settings_bot FOREIGN KEY (bot_id) REFERENCES bots (id)
);

-- ── Force-join channels per sub-bot (up to 5) ─────────────
CREATE TABLE IF NOT EXISTS bot_force_joins (
    id      BIGSERIAL PRIMARY KEY,
    bot_id  BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    link    TEXT NOT NULL,
    title   TEXT,
    UNIQUE (bot_id, chat_id),
    CONSTRAINT fk_bot_force_joins_bot FOREIGN KEY (bot_id) REFERENCES bots (id)
);

-- ── Quizzes captured from the management group ────────────
CREATE TABLE IF NOT EXISTS quizzes (
    id                        BIGSERIAL PRIMARY KEY,
    bot_id                    BIGINT NOT NULL,
    question                  TEXT NOT NULL,
    options                   TEXT NOT NULL,   -- JSON array
    correct_option            INTEGER NOT NULL,
    explanation               TEXT,
    mgmt_group_message_id     BIGINT,
    confirmation_msg_id       BIGINT DEFAULT 0,
    created_at                TIMESTAMPTZ DEFAULT NOW()
);

-- ── Records of a quiz being sent to a specific group ──────
CREATE TABLE IF NOT EXISTS quiz_sends (
    id         BIGSERIAL PRIMARY KEY,
    quiz_id    BIGINT NOT NULL,
    group_id   BIGINT NOT NULL,
    message_id BIGINT,
    poll_id    TEXT,
    sent_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Individual user attempts on a quiz poll ───────────────
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id              BIGSERIAL PRIMARY KEY,
    bot_id          BIGINT NOT NULL,
    quiz_id         BIGINT NOT NULL,
    poll_id         TEXT NOT NULL,
    user_id         BIGINT NOT NULL,
    group_id        BIGINT NOT NULL,
    selected_option INTEGER,
    is_correct      SMALLINT DEFAULT 0,
    marks           INTEGER DEFAULT 0,
    attempted_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (poll_id, user_id)
);

-- ============================================================
--  Indexes (optional but recommended for performance)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_bots_owner       ON bots (owner_id);
CREATE INDEX IF NOT EXISTS idx_bots_status      ON bots (status);
CREATE INDEX IF NOT EXISTS idx_bot_users_bot    ON bot_users (bot_id);
CREATE INDEX IF NOT EXISTS idx_bot_groups_bot   ON bot_groups (bot_id);
CREATE INDEX IF NOT EXISTS idx_quizzes_bot      ON quizzes (bot_id);
CREATE INDEX IF NOT EXISTS idx_quiz_sends_quiz  ON quiz_sends (quiz_id);
CREATE INDEX IF NOT EXISTS idx_attempts_bot     ON quiz_attempts (bot_id);
CREATE INDEX IF NOT EXISTS idx_attempts_poll    ON quiz_attempts (poll_id);
