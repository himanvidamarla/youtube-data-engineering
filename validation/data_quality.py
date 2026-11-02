
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text

load_dotenv()

db_url = URL.create(
    "postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    database=os.getenv("DB_NAME")
)

engine = create_engine(db_url)


def run_check(conn, name, query, expected=0):
    result = conn.execute(text(query)).scalar_one()

    passed = result == expected

    print(
        f"{'PASS' if passed else 'FAIL'} | "
        f"{name} | Result: {result}"
    )

    return passed


def main():

    print("\n========== DATA QUALITY REPORT ==========\n")

    checks = []

    with engine.connect() as conn:

        # 1. Missing video IDs in staging
        checks.append(run_check(
            conn,
            "Missing video IDs",
            """
            SELECT COUNT(*)
            FROM stg_youtube_trending
            WHERE video_id IS NULL
               OR TRIM(video_id) = ''
            """
        ))

        # 2. Missing trending dates
        checks.append(run_check(
            conn,
            "Missing trending dates",
            """
            SELECT COUNT(*)
            FROM stg_youtube_trending
            WHERE trending_date IS NULL
            """
        ))

        # 3. Negative engagement metrics
        checks.append(run_check(
            conn,
            "Negative metrics",
            """
            SELECT COUNT(*)
            FROM fact_video_performance
            WHERE views < 0
               OR likes < 0
               OR dislikes < 0
               OR comments < 0
            """
        ))

        # 4. Duplicate video/date snapshots
        checks.append(run_check(
            conn,
            "Duplicate fact records",
            """
            SELECT COUNT(*)
            FROM (
                SELECT video_key, date_key
                FROM fact_video_performance
                GROUP BY video_key, date_key
                HAVING COUNT(*) > 1
            ) duplicates
            """
        ))

        # 5. Orphaned video references
        checks.append(run_check(
            conn,
            "Orphaned video references",
            """
            SELECT COUNT(*)
            FROM fact_video_performance f
            LEFT JOIN dim_video v
                ON f.video_key = v.video_key
            WHERE v.video_key IS NULL
            """
        ))

        # 6. Orphaned date references
        checks.append(run_check(
            conn,
            "Orphaned date references",
            """
            SELECT COUNT(*)
            FROM fact_video_performance f
            LEFT JOIN dim_date d
                ON f.date_key = d.date_key
            WHERE d.date_key IS NULL
            """
        ))

        # 7. Videos without channel mapping
        checks.append(run_check(
            conn,
            "Videos without channel mapping",
            """
            SELECT COUNT(*)
            FROM dim_video
            WHERE channel_key IS NULL
            """
        ))

    passed = sum(checks)
    total = len(checks)

    print("\n========== FINAL RESULT ==========")
    print(f"Checks passed: {passed}/{total}")
    print(f"Checks failed: {total - passed}/{total}")

    if passed == total:
        print("DATA QUALITY: ALL CHECKS PASSED")
    else:
        print("DATA QUALITY: ISSUES FOUND")

    engine.dispose()

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
