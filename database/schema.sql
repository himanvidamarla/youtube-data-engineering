
-- ==========================================
-- YOUTUBE ANALYTICS DATA WAREHOUSE
-- ==========================================

-- 1. STAGING TABLE
-- Incoming records from the source CSV.

CREATE TABLE IF NOT EXISTS stg_youtube_trending (
    video_id VARCHAR(50),
    trending_date DATE,
    title TEXT,
    channel_title TEXT,
    category_id INTEGER,
    publish_time TIMESTAMPTZ,
    tags TEXT,
    views BIGINT,
    likes BIGINT,
    dislikes BIGINT,
    comment_count BIGINT,
    comments_disabled BOOLEAN,
    ratings_disabled BOOLEAN,
    video_error_or_removed BOOLEAN,
    description TEXT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. CHANNEL DIMENSION

CREATE TABLE IF NOT EXISTS dim_channel (
    channel_key BIGSERIAL PRIMARY KEY,
    channel_title TEXT NOT NULL UNIQUE
);

-- 3. VIDEO DIMENSION

CREATE TABLE IF NOT EXISTS dim_video (
    video_key BIGSERIAL PRIMARY KEY,
    video_id VARCHAR(50) NOT NULL UNIQUE,
    channel_key BIGINT REFERENCES dim_channel(channel_key),
    title TEXT,
    category_id INTEGER,
    publish_time TIMESTAMPTZ,
    duration VARCHAR(50)
);

-- 4. DATE DIMENSION

CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year INTEGER,
    month INTEGER,
    day INTEGER,
    week_number INTEGER,
    day_name VARCHAR(15)
);

-- 5. FACT TABLE

CREATE TABLE IF NOT EXISTS fact_video_performance (
    performance_key BIGSERIAL PRIMARY KEY,
    video_key BIGINT NOT NULL REFERENCES dim_video(video_key),
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    views BIGINT NOT NULL DEFAULT 0,
    likes BIGINT NOT NULL DEFAULT 0,
    dislikes BIGINT NOT NULL DEFAULT 0,
    comments BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT unique_video_snapshot
        UNIQUE (video_key, date_key),

    CONSTRAINT non_negative_metrics CHECK (
        views >= 0 AND
        likes >= 0 AND
        dislikes >= 0 AND
        comments >= 0
    )
);

-- 6. INDEXES FOR QUERY PERFORMANCE

CREATE INDEX IF NOT EXISTS idx_fact_date
ON fact_video_performance(date_key);

CREATE INDEX IF NOT EXISTS idx_fact_video
ON fact_video_performance(video_key);

CREATE INDEX IF NOT EXISTS idx_video_category
ON dim_video(category_id);

CREATE INDEX IF NOT EXISTS idx_staging_trending_date
ON stg_youtube_trending(trending_date);

-- ==========================================
-- END OF SCHEMA
-- ==========================================
