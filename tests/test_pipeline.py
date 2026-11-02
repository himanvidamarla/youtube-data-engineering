
import os
import pandas as pd
import pytest

from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text

load_dotenv()

@pytest.fixture(scope="module")
def db_engine():

    url = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME")
    )

    engine = create_engine(url)

    yield engine

    engine.dispose()


# ==========================================
# UNIT-STYLE DATA VALIDATION TESTS
# ==========================================

def test_processed_csv_exists():

    assert os.path.exists(
        "data/processed/api_videos.csv"
    )


def test_processed_csv_has_records():

    df = pd.read_csv("data/processed/api_videos.csv")

    assert len(df) > 0


def test_video_ids_are_present():

    df = pd.read_csv("data/processed/api_videos.csv")

    assert df["video_id"].notna().all()
    assert (df["video_id"].str.strip() != "").all()


def test_metrics_are_non_negative():

    df = pd.read_csv("data/processed/api_videos.csv")

    for column in ["views", "likes", "comment_count"]:
        assert (df[column] >= 0).all()


# ==========================================
# DATABASE INTEGRATION TESTS
# ==========================================

def test_database_connection(db_engine):

    with db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1")
        ).scalar_one()

    assert result == 1


def test_warehouse_contains_videos(db_engine):

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM dim_video")
        ).scalar_one()

    assert count > 0


def test_fact_table_contains_records(db_engine):

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM fact_video_performance")
        ).scalar_one()

    assert count > 0


def test_no_duplicate_daily_snapshots(db_engine):

    with db_engine.connect() as conn:

        count = conn.execute(text("""
            SELECT COUNT(*)
            FROM (
                SELECT video_key, date_key
                FROM fact_video_performance
                GROUP BY video_key, date_key
                HAVING COUNT(*) > 1
            ) duplicates
        """)).scalar_one()

    assert count == 0


def test_fact_records_have_valid_dimensions(db_engine):

    with db_engine.connect() as conn:

        count = conn.execute(text("""
            SELECT COUNT(*)
            FROM fact_video_performance f
            LEFT JOIN dim_video v
                ON f.video_key = v.video_key
            LEFT JOIN dim_date d
                ON f.date_key = d.date_key
            WHERE v.video_key IS NULL
               OR d.date_key IS NULL
        """)).scalar_one()

    assert count == 0
