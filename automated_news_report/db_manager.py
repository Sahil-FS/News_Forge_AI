"""Database manager for persisting multi-channel platform state."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "db.sqlite"


def get_db_connection() -> sqlite3.Connection:
    """Get connection to the SQLite database with dict factory enabled."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply any missing columns to existing database tables."""
    cursor = conn.cursor()

    def _column_exists(table: str, column: str) -> bool:
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    # video_configurations — columns added in later phases
    vc_additions = [
        ("pause_after_sentence",  "REAL    DEFAULT 0.20"),
        ("visual_cut_threshold",  "REAL    DEFAULT 2.8"),
        ("primary_color",         "TEXT    DEFAULT '#b91c1c'"),
        ("accent_color",          "TEXT    DEFAULT '#0f766e'"),
        ("badge_color",           "TEXT    DEFAULT '#b91c1c'"),
        ("font_family",           "TEXT    DEFAULT 'C:/Windows/Fonts/arialbd.ttf'"),
        ("has_anchor",            "INTEGER DEFAULT 0"),
        ("has_map_stinger",       "INTEGER DEFAULT 0"),
        ("primary_location",      "TEXT    DEFAULT ''"),
    ]
    for col, col_def in vc_additions:
        if not _column_exists("video_configurations", col):
            cursor.execute(
                f"ALTER TABLE video_configurations ADD COLUMN {col} {col_def}"
            )

    # video_analytics — outlier and analytics loop additions
    if not _column_exists("video_analytics", "is_outlier"):
        cursor.execute(
            "ALTER TABLE video_analytics ADD COLUMN is_outlier INTEGER DEFAULT 0"
        )

    va_additions = [
        ("geographic_demographics_json", "TEXT"),
        ("age_gender_demographics_json", "TEXT"),
        ("retention_spikes_json", "TEXT"),
        ("retention_dips_json", "TEXT"),
        ("hook_retention_ratio", "REAL DEFAULT 0.0"),
    ]
    for col, col_def in va_additions:
        if not _column_exists("video_analytics", col):
            cursor.execute(
                f"ALTER TABLE video_analytics ADD COLUMN {col} {col_def}"
            )

    # uploads — publish_time and video_url
    if not _column_exists("uploads", "publish_time"):
        cursor.execute(
            "ALTER TABLE uploads ADD COLUMN publish_time TEXT"
        )
    if not _column_exists("uploads", "video_url"):
        cursor.execute(
            "ALTER TABLE uploads ADD COLUMN video_url TEXT"
        )

    conn.commit()
    print("[DB] Schema migration check complete.")


def init_db() -> None:
    """Initialize SQLite database tables and pre-populate default profiles & feeds."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Channels table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        key TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        audience TEXT,
        language TEXT NOT NULL,
        language_label TEXT,
        default_category TEXT,
        supported_formats TEXT,
        source_policy TEXT,
        brand_name TEXT,
        channel_handle TEXT,
        primary_color TEXT,
        accent_color TEXT
    )
    """)

    # 2. Feeds table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_key TEXT NOT NULL,
        category TEXT NOT NULL,
        url TEXT NOT NULL,
        health TEXT NOT NULL DEFAULT 'healthy',
        priority_rank INTEGER DEFAULT 1,
        UNIQUE(channel_key, category, url)
    )
    """)

    # 3. Stories table (AI Story Ranking Engine & Fact Verification)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_key TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        link TEXT NOT NULL,
        summary TEXT,
        full_text TEXT,
        pub_date TEXT,
        score_importance INTEGER DEFAULT 50,
        score_recency INTEGER DEFAULT 50,
        score_virality INTEGER DEFAULT 50,
        score_relevance INTEGER DEFAULT 50,
        verification_score INTEGER DEFAULT 50,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected, completed
        UNIQUE(channel_key, link)
    )
    """)

    # 4. Runs table (Human Approval Workflow & Monitoring)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        channel_key TEXT NOT NULL,
        category TEXT NOT NULL,
        format TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'idle', -- queued, fetching, scripting, scenes, assets, video, review, upload, complete, failed
        status TEXT NOT NULL DEFAULT 'pending', -- pending, running, success, failed
        started_at REAL,
        finished_at REAL
    )
    """)

    # 5. Uploads table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS uploads (
        run_id TEXT PRIMARY KEY,
        channel_key TEXT NOT NULL,
        title TEXT,
        description TEXT,
        tags TEXT,
        status TEXT DEFAULT 'pending', -- pending, scheduled, uploading, uploaded, failed
        publish_time TEXT,
        video_url TEXT
    )
    """)

    # 6. System logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        level TEXT DEFAULT 'INFO',
        message TEXT,
        timestamp REAL
    )
    """)
    # 7. Video configurations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_configurations (
        run_id TEXT PRIMARY KEY,
        channel_key TEXT NOT NULL,
        format TEXT NOT NULL,
        category TEXT NOT NULL,
        script_text TEXT NOT NULL,
        script_word_count INTEGER NOT NULL,
        verification_score INTEGER DEFAULT 50,
        detected_context TEXT NOT NULL,
        hook_text TEXT,
        pause_after_sentence REAL NOT NULL,
        visual_cut_threshold REAL NOT NULL,
        scene_count INTEGER NOT NULL,
        primary_color TEXT NOT NULL,
        accent_color TEXT NOT NULL,
        badge_color TEXT NOT NULL,
        font_family TEXT NOT NULL,
        has_anchor INTEGER NOT NULL,
        has_map_stinger INTEGER NOT NULL,
        primary_location TEXT,
        created_at REAL NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(id)
    )
    """)

    # 8. Video analytics table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS video_analytics (
        run_id TEXT PRIMARY KEY,
        video_url TEXT NOT NULL,
        views INTEGER NOT NULL DEFAULT 0,
        watch_time_hours REAL NOT NULL DEFAULT 0.0,
        average_view_duration_seconds REAL NOT NULL DEFAULT 0.0,
        average_percentage_viewed REAL NOT NULL DEFAULT 0.0,
        subscribers_gained INTEGER NOT NULL DEFAULT 0,
        impressions INTEGER NOT NULL DEFAULT 0,
        impression_ctr REAL NOT NULL DEFAULT 0.0,
        card_ctr REAL NOT NULL DEFAULT 0.0,
        retention_curve_json TEXT,
        traffic_sources_json TEXT,
        geographic_demographics_json TEXT,
        age_gender_demographics_json TEXT,
        retention_spikes_json TEXT,
        retention_dips_json TEXT,
        hook_retention_ratio REAL DEFAULT 0.0,
        sentiment_positive REAL DEFAULT 0.0,
        sentiment_neutral REAL DEFAULT 0.0,
        sentiment_negative REAL DEFAULT 0.0,
        is_outlier INTEGER DEFAULT 0,
        updated_at REAL NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(id)
    )
    """)

    # 9. Tracked stories table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracked_stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        story_key TEXT NOT NULL UNIQUE,
        headline TEXT NOT NULL,
        first_seen REAL NOT NULL,
        last_updated REAL NOT NULL,
        episode_count INTEGER DEFAULT 1,
        story_summary TEXT,
        channel_key TEXT NOT NULL,
        status TEXT DEFAULT 'active'
    )
    """)

    conn.commit()
    _migrate_schema(conn)

    # Pre-populate channels if empty
    cursor.execute("SELECT COUNT(*) FROM channels")
    if cursor.fetchone()[0] == 0:
        print("[DB] Pre-populating channels...")
        try:
            from channel_profiles import CHANNEL_PROFILES
            for key, p in CHANNEL_PROFILES.items():
                cursor.execute("""
                INSERT INTO channels (
                    key, display_name, audience, language, language_label,
                    default_category, supported_formats, source_policy,
                    brand_name, channel_handle, primary_color, accent_color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p.key, p.display_name, p.audience, p.language, p.language_label,
                    p.default_category, ",".join(p.supported_formats), p.source_policy,
                    p.brand_name, p.channel_handle, p.primary_color, p.accent_color
                ))
            conn.commit()
            print("[DB] Channel population complete.")
        except Exception as e:
            print(f"[DB] Error populating channels: {e}")

    # Always ensure default feeds are inserted
    try:
        from channel_profiles import CHANNEL_PROFILES
        for key, p in CHANNEL_PROFILES.items():
            for cat, urls in p.feeds.items():
                for idx, url in enumerate(urls):
                    cursor.execute("""
                    INSERT OR IGNORE INTO feeds (channel_key, category, url, priority_rank)
                    VALUES (?, ?, ?, ?)
                    """, (p.key, cat, url, idx + 1))
        conn.commit()
        print("[DB] Default feeds verification complete.")
    except Exception as e:
        print(f"[DB] Error verifying default feeds: {e}")

    conn.close()


def log_to_db(run_id: str | None, message: str, level: str = "INFO") -> None:
    """Write a system log entry into the database system_logs table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_logs (run_id, level, message, timestamp) VALUES (?, ?, ?, ?)",
            (run_id, level, message, time.time())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB LOG ERROR] {e} | Original log: {message}")


# Initialize on import
init_db()
