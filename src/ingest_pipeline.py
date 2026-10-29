"""
=============================================================================
Video-Marketing-Analytics: Data Ingestion & SQLite Pipeline
File: src/ingest_pipeline.py
=============================================================================
Ingests raw video telemetry (575k+ records), channel demographics (15.8k+ channels
including 2,320 Indian creators), granular Shorts performance metrics, and Indian
programmatic CPM/AdEx benchmarks into a production SQLite database.
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np
import time

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

# Define Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "video_marketing_india.db")
RAW_DIR = os.path.join(DATA_DIR, "raw")

# YouTube Data API Category Mapping
CATEGORY_MAP = {
    1: "Film & Animation",
    2: "Autos & Vehicles",
    10: "Music",
    15: "Pets & Animals",
    17: "Sports",
    18: "Shorts",
    19: "Travel & Events",
    20: "Gaming",
    21: "Videoblogging",
    22: "People & Blogs",
    23: "Comedy",
    24: "Entertainment",
    25: "News & Politics",
    26: "Howto & Style",
    27: "Education",
    28: "Science & Technology",
    29: "Nonprofits & Activism",
    30: "Movies",
    31: "Anime/Animation",
    32: "Action/Adventure",
    33: "Classics",
    34: "Comedy (Movies)",
    35: "Documentary",
    36: "Drama",
    37: "Family",
    38: "Foreign",
    39: "Horror",
    40: "Sci-Fi/Fantasy",
    41: "Thriller",
    42: "Shorts",
    43: "Shows",
    44: "Trailers"
}

def create_database():
    start_time = time.time()
    print("[*] Initializing Video-Marketing-Analytics SQLite Database Pipeline...")
    print(f"[*] Target DB: {DB_PATH}")

    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("[+] Removed existing database file for a clean rebuild.")
        except Exception as e:
            print(f"[!] Warning removing existing DB: {e}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable WAL mode for high read/write performance
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA cache_size = 100000;")

    # ---------------------------------------------------------
    # 1. Ingest CPM & AdEx Benchmarks
    # ---------------------------------------------------------
    print("\n[1/5] Ingesting India CPM & AdEx Benchmarks...")
    cpm_csv = os.path.join(DATA_DIR, "india_cpm_adex_benchmarks.csv")
    df_cpm = pd.read_csv(cpm_csv)
    df_cpm.to_sql("cpm_benchmarks", conn, if_exists="replace", index=False)
    print(f"   [+] cpm_benchmarks table created: {len(df_cpm)} industry verticals.")

    formats_csv = os.path.join(DATA_DIR, "ad_format_inventory.csv")
    df_formats = pd.read_csv(formats_csv)
    df_formats.to_sql("ad_format_inventory", conn, if_exists="replace", index=False)
    print(f"   [+] ad_format_inventory table created: {len(df_formats)} ad formats.")

    # ---------------------------------------------------------
    # 2. Ingest Channel Info (15.8k channels, 2.3k Indian)
    # ---------------------------------------------------------
    print("\n[2/5] Ingesting Channel Demographics & Monthly Velocity...")
    ch_csv = os.path.join(RAW_DIR, "youtube_channel_info_v2.csv")
    df_ch = pd.read_csv(ch_csv)

    # Clean & enrich channel attributes
    df_ch['is_india'] = (df_ch['country'] == 'IN').astype(int)
    df_ch['subscriber_count'] = pd.to_numeric(df_ch['subscriber_count'], errors='coerce').fillna(0).astype(np.int64)
    df_ch['view_count'] = pd.to_numeric(df_ch['view_count'], errors='coerce').fillna(0).astype(np.int64)
    df_ch['video_count'] = pd.to_numeric(df_ch['video_count'], errors='coerce').fillna(0).astype(np.int64)
    df_ch['views_last_30_days'] = pd.to_numeric(df_ch['views_last_30_days'], errors='coerce').fillna(0).astype(np.int64)
    df_ch['videos_last_30_days'] = pd.to_numeric(df_ch['videos_last_30_days'], errors='coerce').fillna(0).astype(np.int64)

    # 30-day velocity metric
    df_ch['monthly_velocity_views_per_video'] = np.where(
        df_ch['videos_last_30_days'] > 0,
        df_ch['views_last_30_days'] / df_ch['videos_last_30_days'],
        0.0
    )

    df_ch.to_sql("channels", conn, if_exists="replace", index=False)
    india_count = df_ch['is_india'].sum()
    print(f"   [+] channels table created: {len(df_ch):,} channels ({india_count:,} verified Indian channels).")

    # ---------------------------------------------------------
    # 3. Ingest Shorts Granular Performance Datasets
    # ---------------------------------------------------------
    print("\n[3/5] Ingesting Granular YouTube Shorts Telemetry...")
    s1_csv = os.path.join(RAW_DIR, "YouTube_Shorts_Engagement_and_Growth_Velocity.csv")
    df_s1 = pd.read_csv(s1_csv)
    df_s1.columns = [c.lower().replace(' ', '_').replace('%', 'pct') for c in df_s1.columns]
    df_s1.to_sql("shorts_velocity", conn, if_exists="replace", index=False)

    s2_csv = os.path.join(RAW_DIR, "youtube_shorts_performance_dataset.csv")
    df_s2 = pd.read_csv(s2_csv)
    df_s2.to_sql("shorts_duration_performance", conn, if_exists="replace", index=False)
    print(f"   [+] shorts_velocity: {len(df_s1):,} rows | shorts_duration_performance: {len(df_s2):,} rows.")

    # ---------------------------------------------------------
    # 4. Ingest 575k Video Telemetry Database
    # ---------------------------------------------------------
    print("\n[4/5] Ingesting 575k Video Telemetry Dataset in Chunks...")
    big_csv = os.path.join(RAW_DIR, "YouTubeDataset_withChannelElapsed.csv")

    cols_to_read = [
        'videoId', 'channelId', 'videoCategoryId', 'videoViewCount',
        'videoLikeCount', 'videoDislikeCount', 'VideoCommentCount',
        'subscriberCount', 'channelViewCount', 'videoPublished',
        'elapsedtime', 'channelelapsedtime'
    ]

    chunksize = 100000
    total_videos = 0
    table_created = False

    for chunk in pd.read_csv(big_csv, usecols=cols_to_read, chunksize=chunksize):
        # Rename columns to clean snake_case
        chunk = chunk.rename(columns={
            'videoId': 'video_id',
            'channelId': 'channel_id',
            'videoCategoryId': 'category_id',
            'videoViewCount': 'views',
            'videoLikeCount': 'likes',
            'videoDislikeCount': 'dislikes',
            'VideoCommentCount': 'comments',
            'subscriberCount': 'channel_subscribers',
            'channelViewCount': 'channel_total_views',
            'videoPublished': 'published_at',
            'elapsedtime': 'video_elapsed_hours',
            'channelelapsedtime': 'channel_elapsed_hours'
        })

        # Numeric cleans
        chunk['views'] = pd.to_numeric(chunk['views'], errors='coerce').fillna(0).astype(np.int64)
        chunk['likes'] = pd.to_numeric(chunk['likes'], errors='coerce').fillna(0).astype(np.int64)
        chunk['comments'] = pd.to_numeric(chunk['comments'], errors='coerce').fillna(0).astype(np.int64)
        chunk['dislikes'] = pd.to_numeric(chunk['dislikes'], errors='coerce').fillna(0).astype(np.int64)
        chunk['channel_subscribers'] = pd.to_numeric(chunk['channel_subscribers'], errors='coerce').fillna(0).astype(np.int64)

        # Derived analytical signals
        safe_views = np.maximum(chunk['views'].values, 1)
        safe_subs = np.maximum(chunk['channel_subscribers'].values, 1)
        safe_hours = np.maximum(chunk['video_elapsed_hours'].values, 1)

        chunk['category_name'] = chunk['category_id'].map(CATEGORY_MAP).fillna("Other")
        chunk['engagement_rate'] = (chunk['likes'] + chunk['comments']) / safe_views
        chunk['like_ratio'] = chunk['likes'] / safe_views
        chunk['comment_ratio'] = chunk['comments'] / safe_views
        chunk['views_per_subscriber'] = chunk['views'] / safe_subs
        chunk['views_per_hour'] = chunk['views'] / safe_hours

        # Engagement Quality Score (EQS)
        # Weights comments higher (2.8x) due to active intent vs passive thumb tap
        chunk['eqs'] = ((chunk['likes'] + (chunk['comments'] * 2.8)) / safe_views) * 100.0

        if not table_created:
            chunk.to_sql("videos", conn, if_exists="replace", index=False)
            table_created = True
        else:
            chunk.to_sql("videos", conn, if_exists="append", index=False)

        total_videos += len(chunk)
        print(f"   -> Loaded {total_videos:,} / 575,610 videos...")

    # ---------------------------------------------------------
    # 5. Build High-Performance Indexes
    # ---------------------------------------------------------
    print("\n[5/5] Building SQLite Performance Indexes...")
    indexes = [
        ("idx_videos_vid", "videos(video_id)"),
        ("idx_videos_channel", "videos(channel_id)"),
        ("idx_videos_category", "videos(category_id)"),
        ("idx_videos_catname", "videos(category_name)"),
        ("idx_videos_views", "videos(views DESC)"),
        ("idx_videos_eqs", "videos(eqs)"),
        ("idx_channels_cid", "channels(channel_id)"),
        ("idx_channels_country", "channels(country)"),
        ("idx_channels_is_india", "channels(is_india)"),
        ("idx_channels_subs", "channels(subscriber_count DESC)"),
        ("idx_channels_views30d", "channels(views_last_30_days DESC)")
    ]

    for idx_name, idx_target in indexes:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_target};")
    conn.commit()
    print("   [+] All 11 indexes successfully built.")

    # ---------------------------------------------------------
    # Verification & Diagnostic Audit
    # ---------------------------------------------------------
    print("\n" + "="*60)
    print("      Video-Marketing-Analytics SQLITE PIPELINE VERIFICATION")
    print("="*60)

    tables = ["cpm_benchmarks", "ad_format_inventory", "channels", "shorts_velocity", "shorts_duration_performance", "videos"]
    for t in tables:
        count = cursor.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0]
        print(f"  * Table: {t:<28} -> {count:>10,d} rows")

    # Sample Aggregations
    print("\n--- Indian Channels Sample (Top 5 by 30-Day Views) ---")
    query_in = """
    SELECT channel_name, subscriber_count, views_last_30_days, category
    FROM channels
    WHERE is_india = 1
    ORDER BY views_last_30_days DESC
    LIMIT 5;
    """
    sample_ch = pd.read_sql_query(query_in, conn)
    print(sample_ch.to_string(index=False))

    print("\n--- Video Category Distribution & Mean Engagement Rate ---")
    query_cat = """
    SELECT 
        category_name,
        COUNT(*) as video_count,
        ROUND(AVG(views), 0) as avg_views,
        ROUND(AVG(engagement_rate) * 100, 2) as avg_engagement_pct,
        ROUND(AVG(eqs), 2) as avg_eqs
    FROM videos
    GROUP BY category_name
    ORDER BY video_count DESC
    LIMIT 10;
    """
    cat_summary = pd.read_sql_query(query_cat, conn)
    print(cat_summary.to_string(index=False))

    db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    elapsed = time.time() - start_time
    print(f"\n[+] Pipeline completed successfully in {elapsed:.2f} seconds!")
    print(f"[+] Total Database Size: {db_size_mb:.2f} MB")
    print("="*60)

    conn.close()

if __name__ == "__main__":
    create_database()

