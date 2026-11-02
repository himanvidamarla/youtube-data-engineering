
import os
import pandas as pd

from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text

# =====================================================
# 1. CONFIGURATION AND DATABASE CONNECTION
# =====================================================

load_dotenv()

required_variables = [
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD"
]

missing = [key for key in required_variables if not os.getenv(key)]

if missing:
    raise ValueError(f"Missing environment variables: {missing}")

db_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME")
)

engine = create_engine(db_url)


# =====================================================
# 2. READ AND CLEAN API DATA
# =====================================================

def read_api_data():

    file_path = "data/processed/api_videos.csv"

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"Processed API file not found: {file_path}"
        )

    df = pd.read_csv(file_path)

    if df.empty:
        raise ValueError("API dataset is empty")

    print("Records received:", len(df))

    required_columns = [
        "video_id",
        "trending_date",
        "title",
        "channel_title",
        "category_id",
        "publish_time",
        "tags",
        "views",
        "likes",
        "dislikes",
        "comment_count",
        "comments_disabled",
        "ratings_disabled",
        "video_error_or_removed",
        "description",
        "duration"
    ]

    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns in API CSV: {missing_columns}"
        )

    df = df[required_columns].copy()

    # Clean identifiers and dates
    df["video_id"] = df["video_id"].astype("string").str.strip()

    df["trending_date"] = pd.to_datetime(
        df["trending_date"],
        errors="coerce"
    ).dt.date

    df["publish_time"] = pd.to_datetime(
        df["publish_time"],
        errors="coerce",
        utc=True
    )

    # Convert numeric fields
    numeric_columns = [
        "category_id",
        "views",
        "likes",
        "dislikes",
        "comment_count"
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Reject invalid identifiers, dates and metrics
    df = df.dropna(
        subset=[
            "video_id",
            "trending_date",
            "views",
            "likes",
            "comment_count"
        ]
    )

    df = df[df["video_id"] != ""]

    metric_columns = [
        "views",
        "likes",
        "comment_count"
    ]

    for col in metric_columns:
        df = df[df[col] >= 0]
        df[col] = df[col].astype("int64")

    # Dislikes are not publicly available through this API.
    # Store zero as a placeholder for the current schema.
    df["dislikes"] = 0

    df["category_id"] = df["category_id"].astype("Int64")

    # Keep one latest record per video per snapshot date
    df = df.drop_duplicates(
        subset=["video_id", "trending_date"],
        keep="last"
    )

    if df.empty:
        raise ValueError("No valid records remain after cleaning")

    print("Cleaned records:", len(df))

    return df


# =====================================================
# 3. LOAD STAGING TABLE
# =====================================================

def load_staging(df):

    with engine.begin() as conn:

        # Keep previous staging records.
        # Prevent duplicate video/date combinations.
        conn.execute(text("""
            CREATE TEMP TABLE incoming_youtube_data
            (LIKE stg_youtube_trending INCLUDING DEFAULTS)
            ON COMMIT DROP
        """))

        df.to_sql(
            "incoming_youtube_data",
            conn,
            if_exists="append",
            index=False,
            chunksize=500
        )

        conn.execute(text("""
            INSERT INTO stg_youtube_trending (
                video_id,
                trending_date,
                title,
                channel_title,
                category_id,
                publish_time,
                tags,
                views,
                likes,
                dislikes,
                comment_count,
                comments_disabled,
                ratings_disabled,
                video_error_or_removed,
                description,
                duration
            )
            SELECT
                video_id,
                trending_date,
                title,
                channel_title,
                category_id,
                publish_time,
                tags,
                views,
                likes,
                dislikes,
                comment_count,
                comments_disabled,
                ratings_disabled,
                video_error_or_removed,
                description,
                duration
            FROM incoming_youtube_data
        """))

    print("Staging load completed.")


# =====================================================
# 4. POPULATE WAREHOUSE DIMENSIONS AND FACT TABLE
# =====================================================

def load_warehouse():

    with engine.begin() as conn:

        # ---------------------------------------------
        # CHANNEL DIMENSION
        # ---------------------------------------------

        conn.execute(text("""
            INSERT INTO dim_channel (channel_title)
            SELECT DISTINCT channel_title
            FROM stg_youtube_trending
            WHERE channel_title IS NOT NULL
              AND TRIM(channel_title) <> ''
            ON CONFLICT (channel_title) DO NOTHING
        """))

        # ---------------------------------------------
        # VIDEO DIMENSION
        # ---------------------------------------------

        conn.execute(text("""
            INSERT INTO dim_video (
                video_id,
                channel_key,
                title,
                category_id,
                publish_time,
                duration
            )
            SELECT DISTINCT ON (s.video_id)
                s.video_id,
                c.channel_key,
                s.title,
                s.category_id,
                s.publish_time,
                s.duration
            FROM stg_youtube_trending s
            LEFT JOIN dim_channel c
                ON c.channel_title = s.channel_title
            ORDER BY
                s.video_id,
                s.loaded_at DESC
            ON CONFLICT (video_id)
            DO UPDATE SET
                channel_key = EXCLUDED.channel_key,
                title = EXCLUDED.title,
                category_id = EXCLUDED.category_id,
                publish_time = EXCLUDED.publish_time,
                duration = EXCLUDED.duration
        """))

        # ---------------------------------------------
        # DATE DIMENSION
        # ---------------------------------------------

        conn.execute(text("""
            INSERT INTO dim_date (
                date_key,
                full_date,
                year,
                month,
                day,
                week_number,
                day_name
            )
            SELECT DISTINCT
                TO_CHAR(trending_date, 'YYYYMMDD')::INTEGER,
                trending_date,
                EXTRACT(YEAR FROM trending_date)::INTEGER,
                EXTRACT(MONTH FROM trending_date)::INTEGER,
                EXTRACT(DAY FROM trending_date)::INTEGER,
                EXTRACT(WEEK FROM trending_date)::INTEGER,
                TO_CHAR(trending_date, 'FMDay')
            FROM stg_youtube_trending
            ON CONFLICT (date_key) DO NOTHING
        """))

        # ---------------------------------------------
        # FACT TABLE: INCREMENTAL DAILY SNAPSHOTS
        # ---------------------------------------------

        conn.execute(text("""
            INSERT INTO fact_video_performance (
                video_key,
                date_key,
                views,
                likes,
                dislikes,
                comments
            )
            SELECT
                v.video_key,
                d.date_key,
                s.views,
                s.likes,
                s.dislikes,
                s.comment_count
            FROM (
                SELECT DISTINCT ON (
                    video_id,
                    trending_date
                )
                    *
                FROM stg_youtube_trending
                ORDER BY
                    video_id,
                    trending_date,
                    loaded_at DESC
            ) s
            JOIN dim_video v
                ON v.video_id = s.video_id
            JOIN dim_date d
                ON d.full_date = s.trending_date

            ON CONFLICT (video_key, date_key)
            DO UPDATE SET
                views = EXCLUDED.views,
                likes = EXCLUDED.likes,
                dislikes = EXCLUDED.dislikes,
                comments = EXCLUDED.comments
        """))

    print("Warehouse dimensions and fact table loaded.")


# =====================================================
# 5. DISPLAY LOAD SUMMARY
# =====================================================

def show_summary():

    tables = [
        "stg_youtube_trending",
        "dim_channel",
        "dim_video",
        "dim_date",
        "fact_video_performance"
    ]

    print("\n========== LOAD SUMMARY ==========")

    with engine.connect() as conn:

        for table in tables:

            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

            print(f"{table}: {count}")

        duplicate_count = conn.execute(text("""
            SELECT COUNT(*)
            FROM (
                SELECT video_key, date_key
                FROM fact_video_performance
                GROUP BY video_key, date_key
                HAVING COUNT(*) > 1
            ) duplicates
        """)).scalar_one()

        print("Duplicate video/date records:", duplicate_count)

    print("==================================")


# =====================================================
# 6. MAIN EXECUTION
# =====================================================

def main():

    print("\nStarting YouTube Data Warehouse Pipeline...\n")

    df = read_api_data()

    load_staging(df)

    load_warehouse()

    show_summary()

    print("\nPIPELINE EXECUTED SUCCESSFULLY!")


if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print("\nPIPELINE FAILED!")
        print("Error:", error)
        raise

    finally:
        engine.dispose()
