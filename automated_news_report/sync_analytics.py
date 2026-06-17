"""
sync_analytics.py -- Standalone analytics sync tool.

Run this to pull real YouTube stats for all uploaded videos and feed them
into the learning system (correlation_engine.py).

Usage:
    python sync_analytics.py                    # sync all pending uploads
    python sync_analytics.py --channel newscup  # sync one channel only
    python sync_analytics.py --run-id abc12345  # sync one specific run
    python sync_analytics.py --status           # show current analytics DB state
"""

import argparse
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = BASE_DIR / "db.sqlite"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def sync_all(channel_key: str | None = None, run_id: str | None = None):
    """Sync analytics for all uploaded videos (or filter by channel / run)."""
    from analytics_puller import AnalyticsPuller

    conn = get_conn()
    cursor = conn.cursor()

    # Build query
    if run_id:
        cursor.execute(
            "SELECT run_id, channel_key, video_url FROM uploads WHERE run_id=? AND status='uploaded'",
            (run_id,)
        )
    elif channel_key:
        cursor.execute(
            "SELECT run_id, channel_key, video_url FROM uploads WHERE channel_key=? AND status='uploaded'",
            (channel_key,)
        )
    else:
        cursor.execute("SELECT run_id, channel_key, video_url FROM uploads WHERE status='uploaded'")

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("[Sync] No uploaded videos found to sync.")
        return

    print(f"[Sync] Found {len(rows)} video(s) to sync analytics for.")
    print("[Sync] Note: YouTube Analytics data takes 24-48 hours to become available after upload.")
    print()

    for row in rows:
        r_id  = row["run_id"]
        ch    = row["channel_key"]
        url   = row["video_url"]

        if not url or "youtube.com" not in url:
            print(f"[Sync] Skipping run {r_id} — no real YouTube URL (simulated upload).")
            continue

        print(f"[Sync] ─── Run: {r_id} | Channel: {ch} ───────────────────────")
        try:
            metrics = AnalyticsPuller.sync_video_metrics(r_id, url)
            print(f"[Sync] Done | Views: {metrics['views']:,} | "
                  f"Retention: {metrics['average_percentage_viewed']:.1f}% | "
                  f"CTR: {metrics['impression_ctr']:.2f}%")
        except Exception as e:
            print(f"[Sync] ERROR for run {r_id}: {e}")
        print()
        time.sleep(1)  # polite API rate limiting


def show_status():
    """Print current analytics state from the database."""
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT u.channel_key, u.run_id, u.video_url, u.status,
                   va.views, va.average_percentage_viewed, va.impression_ctr,
                   va.watch_time_hours, va.subscribers_gained, va.updated_at
            FROM uploads u
            LEFT JOIN video_analytics va ON u.run_id = va.run_id
            ORDER BY va.updated_at DESC
        """)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[Status] DB error: {e}")
        conn.close()
        return

    conn.close()

    if not rows:
        print("[Status] No uploads found in database.")
        return

    print(f"\n{'='*80}")
    print(f"  Analytics Status — {len(rows)} video(s)")
    print(f"{'='*80}")
    for r in rows:
        has_analytics = r["views"] is not None
        print(f"\n  Run:       {r['run_id']}  |  Channel: {r['channel_key']}")
        print(f"  URL:       {r['video_url'] or 'N/A'}")
        print(f"  Status:    {r['status']}")
        if has_analytics:
            print(f"  Views:     {int(r['views']):,}")
            print(f"  Retention: {r['average_percentage_viewed']:.1f}%")
            print(f"  CTR:       {r['impression_ctr']:.2f}%")
            print(f"  WatchTime: {r['watch_time_hours']:.1f} hrs")
            print(f"  Subs:      +{int(r['subscribers_gained'])}")
        else:
            print("  Analytics: (not yet synced)")
    print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="YouTube Analytics Sync Tool")
    parser.add_argument("--channel", choices=["newscup", "newscup_india"],
                        help="Sync only this channel")
    parser.add_argument("--run-id",  help="Sync a specific run ID")
    parser.add_argument("--status",  action="store_true",
                        help="Show current analytics state from DB")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        sync_all(channel_key=args.channel, run_id=args.run_id)


if __name__ == "__main__":
    main()
