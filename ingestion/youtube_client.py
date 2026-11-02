
import os
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv

# Load credentials
load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY missing from .env file")

API_URL = "https://www.googleapis.com/youtube/v3/videos"

# Create output directories
Path("data/raw/youtube_api").mkdir(parents=True, exist_ok=True)
Path("data/processed").mkdir(parents=True, exist_ok=True)


def fetch_popular_videos():
    """Fetch up to 50 popular public YouTube videos."""

    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": "IN",
        "maxResults": 50,
        "key": API_KEY
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"YouTube API error {response.status_code}: "
            f"{response.text}"
        )

    return response.json()


def transform_response(data):
    """Convert API JSON into tabular records."""

    records = []

    for video in data.get("items", []):
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        details = video.get("contentDetails", {})

        records.append({
            "video_id": video.get("id"),
            "trending_date": datetime.now(timezone.utc).date(),
            "title": snippet.get("title"),
            "channel_title": snippet.get("channelTitle"),
            "category_id": snippet.get("categoryId"),
            "publish_time": snippet.get("publishedAt"),
            "tags": "|".join(snippet.get("tags", [])),
            "views": stats.get("viewCount", 0),
            "likes": stats.get("likeCount", 0),
            "dislikes": stats.get("dislikeCount", 0),
            "comment_count": stats.get("commentCount", 0),
            "comments_disabled": (
                "commentCount" not in stats
            ),
            "ratings_disabled": False,
            "video_error_or_removed": False,
            "description": snippet.get("description", ""),
            "duration": details.get("duration")
        })

    return pd.DataFrame(records)


def main():
    print("Fetching popular YouTube videos...")

    data = fetch_popular_videos()

    # Preserve original API response
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    raw_file = (
        Path("data/raw/youtube_api")
        / f"videos_{timestamp}.json"
    )

    with open(raw_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    # Transform JSON into tabular format
    df = transform_response(data)

    if df.empty:
        raise ValueError("API returned no video records")

    output_file = Path(
        "data/processed/api_videos.csv"
    )

    df.to_csv(output_file, index=False)

    print("\nINGESTION SUCCESSFUL!")
    print("Videos fetched:", len(df))
    print("Raw JSON:", raw_file)
    print("Processed CSV:", output_file)

    print("\nSample records:")
    print(
        df[[
            "video_id",
            "title",
            "views",
            "likes",
            "comment_count"
        ]].head(5).to_string(index=False)
    )


if __name__ == "__main__":
    main()
