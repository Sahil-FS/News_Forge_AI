"""Database manager for persisting multi-channel platform state."""

from __future__ import annotations

import sqlite3
import time
import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "db.sqlite"


def promote_scheduled_uploads() -> None:
    """Find scheduled uploads in the database whose publish_time has passed and mark them as uploaded."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT run_id, publish_time FROM uploads WHERE status='scheduled'")
        rows = cursor.fetchall()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        promoted = []
        
        for row in rows:
            r_id = row["run_id"]
            pub_str = row["publish_time"]
            if pub_str:
                if pub_str.endswith("Z"):
                    pub_str = pub_str[:-1] + "+00:00"
                try:
                    pub_dt = datetime.datetime.fromisoformat(pub_str)
                    if pub_dt <= now_utc:
                        cursor.execute("UPDATE uploads SET status='uploaded' WHERE run_id=?", (r_id,))
                        promoted.append(r_id)
                except Exception as e:
                    print(f"[DB] Error parsing publish_time for run {r_id}: {e}")
        
        if promoted:
            conn.commit()
            print(f"[DB] Auto-promoted {len(promoted)} scheduled run(s) to 'uploaded'.")
        conn.close()
    except Exception as e:
        print(f"[DB Error] promote_scheduled_uploads failed: {e}")


def get_videos_due_for_analytics_sync(min_age_hours: float = 24.0, max_sync_age_hours: float = 72.0) -> list[dict]:
    """
    Find uploaded videos that are mature enough to have YouTube analytics (>min_age_hours old)
    and either have never been synced or haven't been synced in max_sync_age_hours.
    """
    promote_scheduled_uploads()
    conn = get_db_connection()
    cursor = conn.cursor()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    due_videos = []
    
    try:
        cursor.execute("""
            SELECT u.run_id, u.channel_key, u.video_url, u.publish_time,
                   va.updated_at as last_synced_at
            FROM uploads u
            LEFT JOIN video_analytics va ON u.run_id = va.run_id
            WHERE u.status = 'uploaded' AND u.video_url IS NOT NULL
        """)
        rows = cursor.fetchall()
        for row in rows:
            url = row["video_url"]
            if not url or "youtube.com" not in url or "8aa7425fa64" in url:
                continue
            pub_str = row["publish_time"]
            if pub_str:
                if pub_str.endswith("Z"):
                    pub_str = pub_str[:-1] + "+00:00"
                try:
                    pub_dt = datetime.datetime.fromisoformat(pub_str)
                    age_hours = (now_utc - pub_dt).total_seconds() / 3600.0
                    if age_hours < min_age_hours:
                        continue  # Too new, YouTube analytics won't have processed yet
                except Exception:
                    pass
            
            last_sync = row["last_synced_at"]
            if last_sync is None:
                due_videos.append(dict(row))
            else:
                sync_age_hours = (time.time() - last_sync) / 3600.0
                if sync_age_hours >= max_sync_age_hours:
                    due_videos.append(dict(row))
    except Exception as e:
        print(f"[DB Error] get_videos_due_for_analytics_sync failed: {e}")
    finally:
        conn.close()
    return due_videos


def get_milestone_pace_status(target_views: int = 10_000_000, target_subscribers: int = 1_000, target_days: int = 90) -> dict:
    """
    Calculate progress towards the 90-day milestone (e.g. 10M views & 1000 subscribers)
    and return adaptive production adjustments.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now_ts = time.time()
    
    try:
        cursor.execute("SELECT id, start_timestamp FROM growth_milestones ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            # Look at earliest upload to estimate true start time
            cursor.execute("SELECT MIN(publish_time) FROM uploads WHERE status='uploaded'")
            earliest_row = cursor.fetchone()
            start_ts = now_ts
            if earliest_row and earliest_row[0]:
                try:
                    pub_str = earliest_row[0].replace("Z", "+00:00")
                    start_ts = datetime.datetime.fromisoformat(pub_str).timestamp()
                except Exception:
                    start_ts = now_ts
            cursor.execute("""
                INSERT INTO growth_milestones (target_views, target_subscribers, start_timestamp, target_days, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (target_views, target_subscribers, start_ts, target_days, now_ts))
            conn.commit()
        else:
            start_ts = row["start_timestamp"]

        # Aggregate current channel metrics
        cursor.execute("SELECT SUM(views), SUM(subscribers_gained), COUNT(*) FROM video_analytics WHERE is_outlier=0")
        agg = cursor.fetchone()
        total_views = int(agg[0] or 0)
        total_subs = int(agg[1] or 0)
        total_videos = int(agg[2] or 0)

        days_elapsed = max(0.5, (now_ts - start_ts) / 86400.0)
        days_remaining = max(1.0, target_days - days_elapsed)
        
        expected_daily_velocity = target_views / target_days
        expected_views_to_date = expected_daily_velocity * days_elapsed
        pace_ratio = round(total_views / max(1.0, expected_views_to_date), 3)
        required_daily_velocity = round(max(0, target_views - total_views) / days_remaining)

        # Adaptive production parameters based on pace
        if pace_ratio >= 1.0:
            pace_status = "ahead"
            viral_threshold = 65
            recommended_word_target = 200
            recommended_cut_speed = 2.8
            speed_boost = 1.0
        elif pace_ratio >= 0.5:
            pace_status = "behind"
            viral_threshold = 72
            recommended_word_target = 160
            recommended_cut_speed = 2.4
            speed_boost = 1.08
        else:
            pace_status = "critically_behind"
            viral_threshold = 75
            recommended_word_target = 140
            recommended_cut_speed = 2.0
            speed_boost = 1.15

        return {
            "target_views": target_views,
            "target_subscribers": target_subscribers,
            "target_days": target_days,
            "days_elapsed": round(days_elapsed, 1),
            "days_remaining": round(days_remaining, 1),
            "total_views": total_views,
            "total_subscribers": total_subs,
            "total_synced_videos": total_videos,
            "pace_ratio": pace_ratio,
            "pace_status": pace_status,
            "required_daily_velocity": required_daily_velocity,
            "adaptive_viral_threshold": viral_threshold,
            "adaptive_word_target": recommended_word_target,
            "adaptive_cut_speed": recommended_cut_speed,
            "adaptive_speed_boost": speed_boost,
        }
    except Exception as e:
        print(f"[DB Error] get_milestone_pace_status: {e}")
        return {
            "target_views": target_views,
            "pace_status": "default",
            "adaptive_viral_threshold": 70,
            "adaptive_word_target": 180,
            "adaptive_cut_speed": 2.4,
            "adaptive_speed_boost": 1.0,
        }
    finally:
        conn.close()



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

    # 10. Growth milestones table (90-day targets)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS growth_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_views INTEGER DEFAULT 10000000,
        target_subscribers INTEGER DEFAULT 1000,
        start_timestamp REAL,
        target_days INTEGER DEFAULT 90,
        created_at REAL NOT NULL
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
