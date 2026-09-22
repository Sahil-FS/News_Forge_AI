"""
youtube_uploader.py -- YouTube API uploader with per-channel token caching.

Supports:
- Two channels: newscup (English) and newscup_india (Hindi)
- Non-interactive OAuth: browser pops once, token is saved for all future runs
- Automatic token refresh without re-authentication
- Simulated upload fallback when Google API libraries are not installed
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = BASE_DIR / "db.sqlite"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",          # upload videos
    "https://www.googleapis.com/auth/yt-analytics.readonly",   # read real view/retention stats
    "https://www.googleapis.com/auth/youtube.readonly",         # read video metadata & comments
]

# YouTube category IDs
CATEGORY_NEWS_AND_POLITICS = "25"


# ── Credential helpers ─────────────────────────────────────────────────────────

def _get_secrets_path(channel_key: str) -> Path:
    """Return the client secrets file for this channel (channel-specific or shared)."""
    channel_specific = BASE_DIR / f"client_secrets_{channel_key}.json"
    if channel_specific.exists():
        return channel_specific
    shared = BASE_DIR / "client_secrets.json"
    if shared.exists():
        return shared
    raise FileNotFoundError(
        f"[Upload] No OAuth client secrets file found.\n"
        f"  Expected: {channel_specific}\n"
        f"  Or:       {shared}\n"
        f"  → Follow the setup guide to download client_secrets.json from Google Cloud Console."
    )


def _get_credentials(channel_key: str):
    """
    Load saved OAuth2 credentials for this channel.
    If no token exists OR it is expired and cannot be refreshed,
    opens a browser window once to let the operator authenticate.
    Saves the token so all future runs are fully automatic.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import google_auth_oauthlib.flow

    token_path   = BASE_DIR / f"token_{channel_key}.json"
    secrets_path = _get_secrets_path(channel_key)

    creds = None

    # 1. Load existing token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            print(f"[Upload] Could not load saved token ({e}) — will re-authenticate.")
            creds = None

    # 2. Refresh if expired
    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            import time
            for attempt in range(3):
                try:
                    print(f"[Upload] Refreshing expired token for {channel_key} (attempt {attempt + 1}/3)...")
                    creds.refresh(Request())
                    with open(str(token_path), "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                    print(f"[Upload] Token refreshed and saved -> {token_path.name}")
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if "invalid_grant" in err_str:
                        print(f"[Upload] Token permanently revoked ({e}) — will re-authenticate.")
                        creds = None
                        break
                    print(f"[Upload] Token refresh temporary network error: {e}")
                    if attempt < 2:
                        print(f"[Upload] Waiting 5 seconds before retrying...")
                        time.sleep(5)
                    else:
                        print(f"[Upload] All token refresh attempts failed — will re-authenticate.")
                        creds = None

    # 3. Full OAuth flow (only when no valid token exists)
    if not creds or not creds.valid:
        print(f"[Upload] Opening browser for one-time OAuth login ({channel_key})...")
        print(f"[Upload] Using secrets file: {secrets_path}")
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            str(secrets_path), SCOPES
        )
        creds = flow.run_local_server(port=0, open_browser=True)

        # Save token for all future runs
        with open(str(token_path), "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"[Upload] Token saved -> {token_path.name}")
        print(f"[Upload] Future uploads for '{channel_key}' will be fully automatic.")

    return creds


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _register_upload(run_id: str, channel_key: str, title: str, description: str, tags: str) -> None:
    """Insert a pending upload record before starting the upload."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT OR REPLACE INTO uploads
               (run_id, channel_key, title, description, tags, status)
               VALUES (?, ?, ?, ?, ?, 'uploading')""",
            (run_id, channel_key, title[:500], description[:5000], tags[:500])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Upload DB] Could not register upload record: {e}")


def update_upload_status(
    run_id: str,
    status: str,
    video_url: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Update upload state in SQLite and write a system log entry."""
    try:
        conn   = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        if video_url:
            cursor.execute(
                "UPDATE uploads SET status=?, video_url=? WHERE run_id=?",
                (status, video_url, run_id),
            )
        else:
            cursor.execute(
                "UPDATE uploads SET status=? WHERE run_id=?",
                (status, run_id),
            )
        conn.commit()
        conn.close()

        # System log
        try:
            from db_manager import log_to_db
            msg = f"[Upload] Run {run_id} -> '{status}'"
            if video_url:
                msg += f" | URL: {video_url}"
            if error_msg:
                msg += f" | Note: {error_msg}"
            log_to_db(run_id, msg, "INFO" if not error_msg else "WARNING")
        except Exception:
            pass

    except Exception as e:
        print(f"[Upload DB Error]: {e}")


# ── Main upload function ───────────────────────────────────────────────────────

def upload_video(
    run_id: str,
    channel_key: str,
    video_path: str,
    title: str,
    description: str,
    tags: str,
    category_id: str = CATEGORY_NEWS_AND_POLITICS,
    privacy_status: str = "private",
    publish_time: str | None = None,
) -> dict:
    """
    Upload a news video to YouTube for the given channel.

    - Attempts a real YouTube Data API v3 upload using saved OAuth tokens.
    - Falls back to a simulated upload log if Google libraries are missing.
    - Saves the video URL and status to the uploads table in db.sqlite.

    Args:
        run_id:         Unique pipeline run identifier.
        channel_key:    'newscup' or 'newscup_india'.
        video_path:     Absolute path to the MP4 file.
        title:          YouTube video title (max 100 chars).
        description:    Full YouTube description.
        tags:           Comma-separated tag string.
        category_id:    YouTube category ID (default: 25 = News & Politics).
        privacy_status: 'private', 'unlisted', or 'public'.
        publish_time:   ISO 8601 UTC time for scheduled publishing (optional).

    Returns:
        dict with keys: success (bool), video_id (str), url (str), simulated (bool)
    """
    print(f"\n[Upload] ─────────────────────────────────────────────")
    print(f"[Upload] Starting upload for run {run_id} | channel: {channel_key.upper()}")
    print(f"[Upload] File: {video_path}")
    print(f"[Upload] Title: {title[:80]}")

    # Register in DB before starting
    _register_upload(run_id, channel_key, title, description, tags)

    if not os.path.isfile(video_path):
        msg = f"Video file not found: {video_path}"
        print(f"[Upload] ERROR: {msg}")
        update_upload_status(run_id, "failed", error_msg=msg)
        return {"success": False, "error": msg, "simulated": False}

    # ── Real YouTube API path ─────────────────────────────────────────────────
    try:
        import googleapiclient.discovery
        import googleapiclient.errors
        from googleapiclient.http import MediaFileUpload
        import ssl
        import socket
        import http.client

        creds   = _get_credentials(channel_key)
        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

        # Build video resource body
        tag_list = [t.strip() for t in tags.split(",") if t.strip()][:30]
        body = {
            "snippet": {
                "title":           title[:100],
                "description":     description,
                "tags":            tag_list,
                "categoryId":      category_id,
            },
            "status": {
                "privacyStatus":          privacy_status,
                "selfDeclaredMadeForKids": False,   # NOT for kids
                "publicStatsViewable":    False,    # hide likes from public
                "embeddable":             True,     # allow embedding
                "license":                "youtube",
            },
        }

        if publish_time:
            # Scheduled videos must start as private
            body["status"]["publishAt"]      = publish_time
            body["status"]["privacyStatus"]  = "private"
            print(f"[Upload] Scheduled publish at: {publish_time}")

        print(f"[Upload] Privacy: {body['status']['privacyStatus']} | Tags: {len(tag_list)} | Likes hidden: True | Kids: False")

        media = MediaFileUpload(
            video_path,
            chunksize=5 * 1024 * 1024,  # 5 MB chunks for reliable resumption
            resumable=True,
            mimetype="video/mp4",
        )

        request  = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None

        print("[Upload] Uploading", end="", flush=True)
        max_chunk_retries = 5
        while response is None:
            chunk_success = False
            for attempt in range(max_chunk_retries):
                try:
                    status_info, response = request.next_chunk()
                    chunk_success = True
                    break
                except (ssl.SSLError, ConnectionResetError, http.client.IncompleteRead, socket.timeout, socket.error, googleapiclient.errors.HttpError) as e:
                    if isinstance(e, googleapiclient.errors.HttpError):
                        status_code = getattr(getattr(e, 'resp', None), 'status', 500)
                        if status_code < 500:
                            raise
                    
                    if attempt == max_chunk_retries - 1:
                        raise
                    delay = 2 ** attempt
                    print(f"\n[Upload] Transient upload error: {e}. Retrying in {delay}s... (Attempt {attempt+1}/{max_chunk_retries})")
                    time.sleep(delay)
            
            if not chunk_success:
                break

            if status_info:
                pct = int(status_info.progress() * 100)
                print(f"\r[Upload] Progress: {pct}% uploaded...", end="", flush=True)

        print()  # newline after progress
        video_id  = response.get("id", "unknown")
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"[Upload] SUCCESS! Video live at: {video_url}")
        status = "scheduled" if publish_time else "uploaded"
        print(f"[Upload] SUCCESS! Video status: {status} live/scheduled at: {video_url}")
        update_upload_status(run_id, status, video_url=video_url)
        
        # Save publish_time in db if scheduled
        if publish_time:
            try:
                conn = sqlite3.connect(str(DB_PATH))
                conn.execute("UPDATE uploads SET publish_time=? WHERE run_id=?", (publish_time, run_id))
                conn.commit()
                conn.close()
            except Exception as dberr:
                print(f"[Upload DB] Could not update publish_time: {dberr}")

        return {"success": True, "video_id": video_id, "url": video_url, "simulated": False}

    except ImportError:
        # Google API libraries not installed
        print("[Upload] Google API libraries not found.")
        print("[Upload] Install them with:")
        print("[Upload]   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        return _simulated_upload(run_id, video_path, "(google-api-python-client not installed)", publish_time)

    except FileNotFoundError as e:
        # Missing client_secrets.json
        print(f"[Upload] WARNING: {e}")
        return _simulated_upload(run_id, video_path, str(e), publish_time)

    except Exception as e:
        error_msg = str(e)
        print(f"[Upload] ERROR: Upload failed: {error_msg}")
        update_upload_status(run_id, "failed", error_msg=error_msg)
        return {"success": False, "error": error_msg, "simulated": False}


def _simulated_upload(run_id: str, video_path: str, reason: str, publish_time: str | None = None) -> dict:
    """Simulated upload fallback — logs progress but does not upload anything real."""
    import hashlib

    print("[Upload] ─── Simulated Upload Mode ───────────────────────")
    steps = [
        ("Initializing secure session...",          0.5),
        ("Reading video headers...",                0.5),
        ("Simulating chunk upload (50 MB/chunk)...", 1.0),
        ("Finalizing metadata...",                  0.5),
    ]
    for step_name, delay in steps:
        print(f"[Upload][Sim] {step_name}")
        time.sleep(delay)

    sim_id    = hashlib.md5(run_id.encode()).hexdigest()[:11]
    video_url = f"https://www.youtube.com/watch?v={sim_id}"
    note      = f"Simulated upload — real upload skipped ({reason})"

    print(f"[Upload][Sim] Registered simulated URL: {video_url}")
    status = "scheduled" if publish_time else "uploaded"
    update_upload_status(run_id, status, video_url=video_url, error_msg=note)
    
    # Save publish_time in db if scheduled
    if publish_time:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("UPDATE uploads SET publish_time=? WHERE run_id=?", (publish_time, run_id))
            conn.commit()
            conn.close()
        except Exception as dberr:
            print(f"[Upload DB] Could not update publish_time: {dberr}")
            
    return {"success": True, "video_id": sim_id, "url": video_url, "simulated": True}


def get_safe_upload_time(channel_key: str) -> str:
    """
    Calculate a safe publish_time (ISO 8601 UTC) for a new upload.
    Spaced by UPLOAD_SPACING_MINUTES from the last upload, plus a random jitter.
    """
    import sqlite3
    import random
    from datetime import datetime, timedelta, timezone
    import config
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT publish_time, status FROM uploads 
        WHERE channel_key=? AND (status='uploaded' OR status='scheduled' OR status='uploading')
        ORDER BY publish_time DESC LIMIT 1
    """, (channel_key,))
    row = cursor.fetchone()
    conn.close()
    
    now = datetime.now(timezone.utc)
    base_time = now
    
    spacing_minutes = getattr(config, "UPLOAD_SPACING_MINUTES", 150)
    jitter_min = getattr(config, "UPLOAD_JITTER_MIN", 15)
    jitter_max = getattr(config, "UPLOAD_JITTER_MAX", 45)
    
    if row and row[0]:
        try:
            pub_str = row[0]
            if pub_str.endswith("Z"):
                pub_str = pub_str[:-1] + "+00:00"
            last_pub = datetime.fromisoformat(pub_str)
            if last_pub > now:
                base_time = last_pub
            elif (now - last_pub) < timedelta(minutes=spacing_minutes):
                base_time = last_pub
        except Exception as e:
            print(f"[Scheduling] Failed to parse last publish_time '{row[0]}': {e}")
    
    if base_time == now:
        jitter_minutes = random.randint(jitter_min, jitter_max)
        scheduled_time = now + timedelta(minutes=jitter_minutes)
    else:
        jitter_minutes = random.randint(jitter_min, jitter_max)
        scheduled_time = base_time + timedelta(minutes=spacing_minutes + jitter_minutes)
        
    return scheduled_time.isoformat().replace("+00:00", "Z")


# ── Geo-Timeline Matrix Configuration ──────────────────────────────────────────
# 4:30 PM IST to 5:00 AM IST publishing window broken down into 6 strategic slots
GEO_TIMELINE_SLOTS = [
    {
        "slot": 1,
        "name": "India / Asian Geopolitics / Middle East",
        "start_hour": 16, "start_min": 30,
        "end_hour": 17, "end_min": 30,
        "regions": ["india", "asia", "middle east", "israel", "gaza", "iran", "china", "pakistan"],
        "categories": ["general", "politics", "war"]
    },
    {
        "slot": 2,
        "name": "UK / Europe / Transatlantic / Ukraine-Russia",
        "start_hour": 18, "start_min": 30,
        "end_hour": 19, "end_min": 30,
        "regions": ["uk", "europe", "ukraine", "russia", "germany", "france", "britain"],
        "categories": ["war", "politics", "general"]
    },
    {
        "slot": 3,
        "name": "Transatlantic & Global Business",
        "start_hour": 20, "start_min": 30,
        "end_hour": 21, "end_min": 30,
        "regions": ["global", "uk", "us", "transatlantic", "europe"],
        "categories": ["business", "markets", "economy", "general"]
    },
    {
        "slot": 4,
        "name": "US Politics, Supreme Court, Major US Policy",
        "start_hour": 22, "start_min": 30,
        "end_hour": 23, "end_min": 30,
        "regions": ["united states", "us", "usa", "washington", "america"],
        "categories": ["politics", "policy", "general"]
    },
    {
        "slot": 5,
        "name": "US Tech, Economy, AI Giants",
        "start_hour": 1, "start_min": 0, "next_day": True,
        "end_hour": 2, "end_min": 0,
        "regions": ["us", "silicon valley", "california", "global"],
        "categories": ["technology", "business", "ai", "general"]
    },
    {
        "slot": 6,
        "name": "US Prime Evening / Global Breaking Summary",
        "start_hour": 3, "start_min": 30, "next_day": True,
        "end_hour": 4, "end_min": 45,
        "regions": ["us", "global"],
        "categories": ["general", "breaking", "world"]
    },
]


def get_geo_scheduled_upload_time(channel_key: str, country: str | None = None, category: str | None = None) -> str:
    """
    Calculate the next optimized publish time in UTC based on the Geo-Timeline Matrix (4:30 PM to 5:00 AM IST).
    Maps videos to 6 targeted regional & categorical slots with safe spacing and boundary enforcement.
    """
    from datetime import datetime, timedelta, timezone
    import sqlite3
    import random
    import config

    # 1. Lock scheduling offset to Indian Standard Time (IST, +5.5)
    offset = 5.5
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + timedelta(hours=offset)

    # 2. Determine batch run_day and locked next-day 5:00 AM boundary
    boundary_hour = getattr(config, "BATCH_BOUNDARY_HOUR", 5)
    if now_local.hour < boundary_hour:
        run_day = now_local.date() - timedelta(days=1)
        end_time_local = datetime(now_local.year, now_local.month, now_local.day, boundary_hour, 0, 0)
    else:
        run_day = now_local.date()
        tomorrow = now_local + timedelta(days=1)
        end_time_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, boundary_hour, 0, 0)

    # Convert boundary times to UTC for DB querying
    start_utc = (datetime(run_day.year, run_day.month, run_day.day, 4, 0, 0) - timedelta(hours=offset)).isoformat() + "Z"
    end_utc = (end_time_local - timedelta(hours=offset)).isoformat() + "Z"

    # 3. Check SQLite for existing uploads in the current active batch (within start_utc and end_utc)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT publish_time FROM uploads 
        WHERE channel_key=? AND (status='uploaded' OR status='scheduled' OR status='uploading')
        AND publish_time >= ? AND publish_time <= ?
        ORDER BY publish_time ASC
    """, (channel_key, start_utc, end_utc))
    rows = cursor.fetchall()
    conn.close()

    batch_count = getattr(config, "BATCH_COUNT", 6)
    n = len(rows)

    # Build slot datetimes for current run_day
    slot_windows = []
    for slot_def in GEO_TIMELINE_SLOTS:
        s_date = run_day + timedelta(days=1) if slot_def.get("next_day") else run_day
        s_start = datetime(s_date.year, s_date.month, s_date.day, slot_def["start_hour"], slot_def["start_min"], 0)
        s_end = datetime(s_date.year, s_date.month, s_date.day, slot_def["end_hour"], slot_def["end_min"], 0)
        slot_windows.append((slot_def, s_start, s_end))

    # Determine which slot to assign
    assigned_slot_idx = None

    # Check if category or country matches an unassigned slot
    if country or category:
        c_low = (country or "").lower().strip()
        cat_low = (category or "").lower().strip()
        for idx, (slot_def, s_start, s_end) in enumerate(slot_windows):
            if idx >= n:
                region_match = any(r in c_low for r in slot_def["regions"]) if c_low else False
                category_match = any(cat in cat_low for cat in slot_def["categories"]) if cat_low else False
                if region_match or category_match:
                    assigned_slot_idx = idx
                    break

    if assigned_slot_idx is None:
        assigned_slot_idx = min(n, len(slot_windows) - 1)

    slot_def, s_start, s_end = slot_windows[assigned_slot_idx]

    # Calculate target time within slot with gentle jitter (e.g. +5 to +25 minutes from slot start)
    jitter = random.randint(5, 25)
    scheduled_local = s_start + timedelta(minutes=jitter)
    print(f"[Scheduling] Mapped to Slot {slot_def['slot']} ({slot_def['name']}) -> {scheduled_local.strftime('%H:%M')} IST")

    # Safety guard 1: Never schedule in the past
    now_local_naive = now_local.replace(tzinfo=None)
    if scheduled_local < now_local_naive + timedelta(minutes=10):
        # Advance to earliest valid slot or now + 10m
        next_possible = None
        for idx in range(assigned_slot_idx + 1, len(slot_windows)):
            _, future_start, future_end = slot_windows[idx]
            if future_end > now_local_naive + timedelta(minutes=15):
                next_possible = max(future_start + timedelta(minutes=random.randint(5, 15)), now_local_naive + timedelta(minutes=10))
                break
        if next_possible:
            scheduled_local = next_possible
        else:
            scheduled_local = now_local_naive + timedelta(minutes=10)
        print(f"[Scheduling] Past slot adjusted: scheduled for local time {scheduled_local.strftime('%H:%M')} IST")

    # Safety guard 2: Spacing relative to last uploaded/scheduled video in batch
    if rows:
        try:
            last_pub_str = rows[-1][0]
            if last_pub_str.endswith("Z"):
                last_pub_str = last_pub_str[:-1] + "+00:00"
            last_pub_utc = datetime.fromisoformat(last_pub_str).astimezone(timezone.utc)
            last_pub_local = (last_pub_utc + timedelta(hours=offset)).replace(tzinfo=None)

            min_spacing = getattr(config, "BATCH_MIN_SPACING_MINUTES", 30)
            if (scheduled_local - last_pub_local).total_seconds() < min_spacing * 60:
                scheduled_local = last_pub_local + timedelta(minutes=min_spacing + random.randint(2, 8))
                print(f"[Scheduling] Spacing guard pushed slot forward to {scheduled_local.strftime('%H:%M')} IST")
        except Exception as e:
            print(f"[Scheduling] Spacing check exception: {e}")

    # Safety guard 3: Boundary enforcement check (5:00 AM next day)
    boundary_target = end_time_local - timedelta(minutes=15)
    if scheduled_local > boundary_target:
        print(f"[Scheduling] Scheduled time crosses 5:00 AM boundary: {scheduled_local.strftime('%H:%M')} > {boundary_target.strftime('%H:%M')}")
        if rows:
            try:
                last_pub_str = rows[-1][0]
                if last_pub_str.endswith("Z"):
                    last_pub_str = last_pub_str[:-1] + "+00:00"
                last_pub_utc = datetime.fromisoformat(last_pub_str).astimezone(timezone.utc)
                last_pub_local = (last_pub_utc + timedelta(hours=offset)).replace(tzinfo=None)
                available = (boundary_target - last_pub_local).total_seconds() / 60.0
                if available > 15:
                    scheduled_local = last_pub_local + timedelta(minutes=max(10, available / 2))
                else:
                    scheduled_local = boundary_target
            except Exception:
                scheduled_local = boundary_target
        else:
            scheduled_local = boundary_target
        print(f"[Scheduling] Boundary clamp applied: {scheduled_local.strftime('%H:%M')} IST")

    # Safety guard 4: Beyond slot 6 handling for large batches (e.g. n >= 6)
    if n >= len(slot_windows) and rows:
        try:
            last_pub_str = rows[-1][0]
            if last_pub_str.endswith("Z"):
                last_pub_str = last_pub_str[:-1] + "+00:00"
            last_pub_utc = datetime.fromisoformat(last_pub_str).astimezone(timezone.utc)
            last_pub_local = (last_pub_utc + timedelta(hours=offset)).replace(tzinfo=None)
            available = (boundary_target - last_pub_local).total_seconds() / 60.0
            if available > 15:
                scheduled_local = min(boundary_target, last_pub_local + timedelta(minutes=max(10, available / 2)))
            else:
                scheduled_local = boundary_target
        except Exception as e:
            print(f"[Scheduling] Extended slot calculation exception: {e}")

    # Final conversion to UTC
    scheduled_utc = scheduled_local - timedelta(hours=offset)
    scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)

    # Ensure never earlier than now_utc + 10m
    if scheduled_utc < now_utc + timedelta(minutes=10):
        scheduled_utc = now_utc + timedelta(minutes=10)

    return scheduled_utc.isoformat().replace("+00:00", "Z")



# ── Auth check helper ──────────────────────────────────────────────────────────

def check_auth_status(channel_key: str) -> dict:
    """
    Check if a valid saved token exists for this channel.
    Returns a dict with 'authenticated' (bool) and 'token_path' (str).
    """
    token_path = BASE_DIR / f"token_{channel_key}.json"
    if not token_path.exists():
        return {"authenticated": False, "token_path": str(token_path), "reason": "No token file found"}

    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.valid:
            return {"authenticated": True, "token_path": str(token_path), "reason": "Token valid"}
        if creds.expired and creds.refresh_token:
            return {"authenticated": True, "token_path": str(token_path), "reason": "Token expired but refreshable"}
        return {"authenticated": False, "token_path": str(token_path), "reason": "Token invalid — re-authenticate"}
    except ImportError:
        return {"authenticated": False, "token_path": str(token_path), "reason": "google-auth not installed"}
    except Exception as e:
        return {"authenticated": False, "token_path": str(token_path), "reason": str(e)}


def run_first_time_auth(channel_key: str) -> None:
    """
    Run the one-time browser OAuth flow for a channel.
    Call this once from the command line to save the token:
        python youtube_uploader.py --auth newscup
        python youtube_uploader.py --auth newscup_india
    """
    print(f"\n[Auth] Starting one-time OAuth setup for channel: {channel_key}")
    print(f"[Auth] A browser window will open -- log in with the Google account that owns @{channel_key}")
    try:
        creds  = _get_credentials(channel_key)
        status = check_auth_status(channel_key)
        print(f"[Auth] Authentication complete! Status: {status['reason']}")
    except Exception as e:
        print(f"[Auth] Authentication failed: {e}")


def upload_latest_output(channel_key: str):
    """Upload whatever video is currently sitting in output/news_video.mp4 using output/youtube_metadata.txt."""
    import re
    from pathlib import Path
    import uuid
    video_path = Path(__file__).resolve().parent / "output" / "news_video.mp4"
    meta_path = Path(__file__).resolve().parent / "output" / "youtube_metadata.txt"
    if not video_path.exists():
        print(f"[Upload] Error: {video_path} not found.")
        return
    title = "Breaking News"
    description = ""
    tags = "news, breaking news"
    if meta_path.exists():
        content = meta_path.read_text(encoding="utf-8")
        t_match = re.search(r"YOUTUBE TITLE:\s*\n([^\n]+)", content)
        if t_match:
            title = t_match.group(1).strip()
        d_match = re.search(r"YOUTUBE DESCRIPTION:\s*\n(.*?)(?=\n═|\n#|\Z)", content, re.DOTALL)
        if d_match:
            description = d_match.group(1).strip()
        tag_match = re.search(r"TAGS FOR YOUTUBE TAG BOX[^\n]*:\s*\n([^\n]+)", content)
        if tag_match:
            tags = tag_match.group(1).strip()
            
    run_id = uuid.uuid4().hex[:8]
    print(f"[Upload] Uploading latest output video: {title}")
    return upload_video(
        run_id=run_id,
        channel_key=channel_key,
        video_path=str(video_path),
        title=title,
        description=description,
        tags=tags,
    )


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube uploader / auth tool")
    parser.add_argument("--auth",   metavar="CHANNEL", help="Run first-time OAuth for a channel key (e.g. newscup)")
    parser.add_argument("--status", metavar="CHANNEL", help="Check auth status for a channel key")
    parser.add_argument("--upload-latest", metavar="CHANNEL", help="Upload the existing video sitting in output/news_video.mp4")
    args = parser.parse_args()

    if args.auth:
        run_first_time_auth(args.auth)
    elif args.status:
        result = check_auth_status(args.status)
        print(f"[Status] Channel:       {args.status}")
        print(f"[Status] Authenticated: {result['authenticated']}")
        print(f"[Status] Reason:        {result['reason']}")
        print(f"[Status] Token file:    {result['token_path']}")
    elif args.upload_latest:
        upload_latest_output(args.upload_latest)
    else:
        parser.print_help()
