CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    xp INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_question_posts (
    date DATE PRIMARY KEY,
    message_id BIGINT,
    thread_id BIGINT,
    channel_id BIGINT,
    posted_at TIMESTAMPTZ
);

ALTER TABLE daily_question_posts
ADD COLUMN IF NOT EXISTS thread_id BIGINT;
