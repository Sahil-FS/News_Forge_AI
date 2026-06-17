#!/usr/bin/env python3
"""Premium Operator UI for the multi-channel AI news production platform."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from channel_profiles import get_channel_profile, public_channel_profiles
from db_manager import get_db_connection
from youtube_uploader import upload_video
from scene_planner import plan_scenes

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
PYTHON = sys.executable

_STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "returncode": None,
    "command": [],
    "channel": "newscup",
    "category": "world",
    "format": "both",
    "stage": "idle",
    "logs": [],
    "active_run_id": None,
}
_PROCESS = None
_LOCK = threading.Lock()


def _append_log(line: str) -> None:
    line = line.rstrip()
    if not line:
        return
    with _LOCK:
        _STATE["logs"].append(line)
        _STATE["logs"] = _STATE["logs"][-400:]
        
        # Check active run ID in log
        if "[RUN ID]:" in line:
            parts = line.split(":")
            if len(parts) > 1:
                _STATE["active_run_id"] = parts[1].strip()

        # Update run stages from print markers
        lowered = line.lower()
        if "[1/5]" in line:
            _STATE["stage"] = "news"
        elif "[2/5]" in line:
            _STATE["stage"] = "script"
        elif "[3/5]" in line:
            _STATE["stage"] = "scenes"
        elif "[4/5]" in line:
            _STATE["stage"] = "assets"
        elif "[5/5]" in line:
            _STATE["stage"] = "video"
        elif "success" in lowered:
            _STATE["stage"] = "complete"
        elif "error" in lowered:
            _STATE["stage"] = "error"


def _artifact_status() -> dict:
    candidates = {
        "article": OUTPUT_DIR / "article.json",
        "short_script": OUTPUT_DIR / "script.txt",
        "long_script": OUTPUT_DIR / "script_long.txt",
        "short_scenes": OUTPUT_DIR / "scenes.json",
        "long_scenes": OUTPUT_DIR / "scenes_long.json",
        "metadata": OUTPUT_DIR / "youtube_metadata.txt",
        "short_video": OUTPUT_DIR / "news_video.mp4",
        "long_video": OUTPUT_DIR / "news_video_long.mp4",
        "thumbnail_portrait": OUTPUT_DIR / "thumbnail_portrait.jpg",
        "thumbnail_landscape": OUTPUT_DIR / "thumbnail_landscape.jpg",
    }
    result = {}
    for key, path in candidates.items():
        exists = path.exists()
        if exists:
            if path.suffix == ".mp4":
                exists = path.stat().st_size > 100000
            else:
                exists = path.stat().st_size > 5
        result[key] = {
            "exists": exists,
            "path": str(path),
            "size": path.stat().st_size if path.exists() else 0,
        }
    return result


def _run_pipeline(payload: dict) -> None:
    global _PROCESS
    channel = payload.get("channel", "newscup")
    category = payload.get("category") or get_channel_profile(channel).default_category
    fmt = payload.get("format", "both")
    stage = payload.get("stage", "")
    skip_to = payload.get("skip_to", "")
    test_mode = bool(payload.get("test_mode", False))
    no_clean = bool(payload.get("no_clean", False))
    video_style = payload.get("video_style", "briefing")

    cmd = [PYTHON, str(BASE_DIR / "main.py"), "--channel", channel, "--category", category, "--format", fmt, "--video-style", video_style]
    if stage:
        cmd += ["--stage", stage]
    if skip_to:
        cmd += ["--skip-to", skip_to]
    if test_mode:
        cmd.append("--test-mode")
    if no_clean or skip_to:
        cmd.append("--no-clean")

    with _LOCK:
        _STATE.update({
            "running": True,
            "started_at": time.time(),
            "finished_at": None,
            "returncode": None,
            "command": cmd,
            "channel": channel,
            "category": category,
            "format": fmt,
            "video_style": video_style,
            "stage": "queued",
            "logs": [],
        })

    env = os.environ.copy()
    env["NEWS_CHANNEL"] = channel
    env["PYTHONUTF8"] = "1"

    try:
        _PROCESS = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert _PROCESS.stdout is not None
        for line in _PROCESS.stdout:
            _append_log(line)
        rc = _PROCESS.wait()
    except Exception as exc:
        _append_log(f"[UI] Pipeline launch failed: {exc}")
        rc = 1
    finally:
        with _LOCK:
            _STATE["running"] = False
            _STATE["finished_at"] = time.time()
            _STATE["returncode"] = rc
            if rc == 0 and _STATE["stage"] != "complete":
                _STATE["stage"] = "complete"
            elif rc != 0:
                _STATE["stage"] = "error"
            
            # Log run update in sqlite runs table on completion
            active_id = _STATE.get("active_run_id")
            if active_id:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE runs SET stage=?, status=?, finished_at=? WHERE id=?",
                        (_STATE["stage"], "success" if rc == 0 else "failed", time.time(), active_id)
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
        _PROCESS = None


_TEMPLATE_PATH = BASE_DIR / "templates" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except ConnectionError:
            self.close_connection = True

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        expected_key = os.environ.get("NEWS_UI_API_KEY", "").strip()
        if not expected_key:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == expected_key:
                return True
        self._send_json({"error": "Unauthorized"}, 401)
        return False

    def _send_html(self) -> None:
        try:
            with open(_TEMPLATE_PATH, "rb") as f:
                body = f.read()
        except Exception as e:
            body = f"Template loading failed: {e}".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url_parsed = urlparse(self.path)
        path = url_parsed.path
        query = parse_qs(url_parsed.query)

        # Serve static assets directly from output directory
        if path.startswith("/output/"):
            rel_path = path[8:]
            file_path = OUTPUT_DIR / rel_path
            
            # Prevent directory traversal
            if not file_path.resolve().is_relative_to(OUTPUT_DIR.resolve()):
                self._send_json({"error": "forbidden"}, 403)
                return

            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                if file_path.suffix == ".mp4":
                    self.send_header("Content-Type", "video/mp4")
                elif file_path.suffix == ".wav":
                    self.send_header("Content-Type", "audio/wav")
                elif file_path.suffix in (".jpg", ".jpeg"):
                    self.send_header("Content-Type", "image/jpeg")
                elif file_path.suffix == ".json":
                    self.send_header("Content-Type", "application/json")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(file_path.stat().st_size))
                self.end_headers()
                
                with open(file_path, "rb") as f:
                    # Write in chunks to prevent large memory prints
                    while chunk := f.read(64 * 1024):
                        self.wfile.write(chunk)
                return
            else:
                self._send_json({"error": "not found"}, 404)
                return

        if path == "/":
            self._send_html()
            return

        if not self._check_auth():
            return
        elif path == "/api/channels":
            self._send_json(public_channel_profiles())
        elif path == "/api/status":
            with _LOCK:
                payload = dict(_STATE)
                payload["artifacts"] = _artifact_status()
            self._send_json(payload)
        elif path == "/api/feeds":
            channel = query.get("channel", ["newscup"])[0]
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT category, url FROM feeds WHERE channel_key=? ORDER BY priority_rank", (channel,)
                )
                feeds_map = {}
                for row in cursor.fetchall():
                    cat = row["category"]
                    url = row["url"]
                    if cat not in feeds_map:
                        feeds_map[cat] = []
                    feeds_map[cat].append(url)
                conn.close()
                self._send_json(feeds_map)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/api/script":
            fmt = query.get("format", ["short"])[0]
            script_file = "script_long.txt" if fmt == "long" else "script.txt"
            script_path = OUTPUT_DIR / script_file
            if script_path.exists():
                with open(script_path, "r", encoding="utf-8") as f:
                    self._send_json({"script": f.read()})
            else:
                self._send_json({"script": ""})
        elif path == "/api/scenes":
            fmt = query.get("format", ["short"])[0]
            scenes_file = "scenes_long.json" if fmt == "long" else "scenes.json"
            scenes_path = OUTPUT_DIR / scenes_file
            if scenes_path.exists():
                with open(scenes_path, "r", encoding="utf-8") as f:
                    self._send_json(json.load(f))
            else:
                self._send_json([])
        elif path == "/api/metadata":
            meta_path = OUTPUT_DIR / "youtube_metadata.txt"
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                title_match = re.search(r"YOUTUBE TITLE:\n(.*?)\n\n", content)
                title = title_match.group(1).strip() if title_match else "Breaking News"
                
                desc_match = re.search(
                    r"YOUTUBE DESCRIPTION:\n(.*?)\n\n═", content, re.DOTALL
                )
                description = desc_match.group(1).strip() if desc_match else ""
                
                tag_match = re.search(
                    r"TAGS FOR YOUTUBE TAG BOX \(comma-separated\):\n(.*?)$", content, re.DOTALL
                )
                tags = [t.strip() for t in tag_match.group(1).split(",") if t.strip()] if tag_match else []
                
                self._send_json({"title": title, "description": description, "hashtags": tags})
            else:
                self._send_json({"title": "", "description": "", "hashtags": []})
        elif path == "/api/analytics":
            channel = query.get("channel", ["newscup"])[0]
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT va.*, vc.format, vc.category, vc.created_at
                    FROM video_analytics va
                    JOIN video_configurations vc ON va.run_id = vc.run_id
                    WHERE vc.channel_key = ? AND va.is_outlier = 0
                    ORDER BY vc.created_at DESC
                    LIMIT 10
                """, (channel,))
                rows = cursor.fetchall()
                
                videos = []
                for row in rows:
                    videos.append({
                        "run_id": row["run_id"],
                        "video_url": row["video_url"],
                        "views": row["views"],
                        "watch_time_hours": row["watch_time_hours"],
                        "avd": row["average_view_duration_seconds"],
                        "ctr": row["impression_ctr"],
                        "format": row["format"],
                        "category": row["category"],
                        "sentiment_positive": row["sentiment_positive"],
                        "sentiment_negative": row["sentiment_negative"]
                    })
                
                cursor.execute("""
                    SELECT va.retention_curve_json
                    FROM video_analytics va
                    JOIN video_configurations vc ON va.run_id = vc.run_id
                    WHERE vc.channel_key = ? AND va.is_outlier = 0
                    ORDER BY vc.created_at DESC
                    LIMIT 3
                """, (channel,))
                retention_rows = cursor.fetchall()
                
                curve = []
                if retention_rows:
                    parsed_curves = [json.loads(r["retention_curve_json"]) for r in retention_rows if r["retention_curve_json"]]
                    if parsed_curves:
                        num_steps = len(parsed_curves[0])
                        for step_idx in range(num_steps):
                            t_sum = 0
                            p_sum = 0
                            valid_count = 0
                            for pc in parsed_curves:
                                if step_idx < len(pc):
                                    t_sum += pc[step_idx]["t"]
                                    p_sum += pc[step_idx]["p"]
                                    valid_count += 1
                            if valid_count > 0:
                                curve.append({
                                    "t": int(t_sum / valid_count),
                                    "p": int(p_sum / valid_count)
                                })
                
                if not curve:
                    curve = [
                        {"t": 0, "p": 100}, {"t": 10, "p": 75}, {"t": 20, "p": 62},
                        {"t": 30, "p": 54}, {"t": 40, "p": 48}, {"t": 50, "p": 42}
                    ]
                
                conn.close()
                self._send_json({"videos": videos, "retention_curve": curve})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/api/tracked_stories":
            channel = query.get("channel", ["newscup"])[0]
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, story_key, headline, first_seen, last_updated, episode_count, story_summary, status "
                    "FROM tracked_stories WHERE channel_key=? ORDER BY last_updated DESC", (channel,)
                )
                rows = cursor.fetchall()
                stories = [dict(r) for r in rows]
                conn.close()
                self._send_json(stories)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/api/settings":
            env_vars = {}
            env_path = BASE_DIR / ".env"
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line and not line.strip().startswith("#"):
                            k, v = line.strip().split("=", 1)
                            env_vars[k.strip()] = v.strip()
            self._send_json(env_vars)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if not self._check_auth():
            return

        url_parsed = urlparse(self.path)
        path = url_parsed.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8") or "{}"
        payload = json.loads(body)

        if path == "/api/run":
            with _LOCK:
                if _STATE["running"]:
                    self._send_json({"error": "pipeline already running"}, 409)
                    return
            thread = threading.Thread(target=_run_pipeline, args=(payload,), daemon=True)
            thread.start()
            self._send_json({"ok": True})
            
        elif path == "/api/feeds":
            channel = payload.get("channel", "newscup")
            action = payload.get("action")
            category = payload.get("category", "general")
            url = payload.get("url", "")
            
            if not url:
                self._send_json({"error": "url is required"}, 400)
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if action == "add":
                    cursor.execute(
                        "INSERT OR IGNORE INTO feeds (channel_key, category, url) VALUES (?, ?, ?)",
                        (channel, category, url)
                    )
                elif action == "delete":
                    cursor.execute(
                        "DELETE FROM feeds WHERE channel_key=? AND category=? AND url=?",
                        (channel, category, url)
                    )
                conn.commit()
                conn.close()
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
                
        elif path == "/api/script":
            channel = payload.get("channel", "newscup")
            fmt = payload.get("format", "short")
            script_text = payload.get("script", "")
            
            script_file = "script_long.txt" if fmt == "long" else "script.txt"
            script_path = OUTPUT_DIR / script_file
            
            try:
                OUTPUT_DIR.mkdir(exist_ok=True)
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_text)
                
                # Resplit script into scenes immediately so downstream is aligned
                try:
                    scenes = plan_scenes(script_text)
                    scenes_file = "scenes_long.json" if fmt == "long" else "scenes.json"
                    with open(OUTPUT_DIR / scenes_file, "w", encoding="utf-8") as sf:
                        json.dump(scenes, sf, indent=4)
                    print(f"[UI] Script modified. Re-planned {len(scenes)} scenes.")
                except Exception as e:
                    print(f"[UI] Failed to re-plan scenes after script edit: {e}")
                    
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
                
        elif path == "/api/upload":
            channel = payload.get("channel", "newscup")
            fmt = payload.get("format", "short")
            title = payload.get("title", "Breaking News")
            description = payload.get("description", "")
            tags = payload.get("tags", "")
            
            video_file = "news_video_long.mp4" if fmt == "long" else "news_video.mp4"
            video_path = str(OUTPUT_DIR / video_file)
            
            # Setup DB record in uploads table
            run_id = payload.get("run_id")
            if not run_id:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id FROM runs WHERE channel_key=? ORDER BY started_at DESC LIMIT 1",
                        (channel,)
                    )
                    row = cursor.fetchone()
                    if row:
                        run_id = row["id"]
                    conn.close()
                except Exception:
                    pass
            if not run_id:
                run_id = "manual"

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO uploads (run_id, channel_key, title, description, tags, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, channel, title, description, tags, "pending")
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

            # Run upload in background thread to avoid HTTP connection timeouts
            def _upload_task():
                from youtube_uploader import get_safe_upload_time
                safe_pub_time = None
                try:
                    safe_pub_time = get_safe_upload_time(channel)
                    print(f"[UI Upload] Spacing checked. Scheduling upload at: {safe_pub_time}")
                except Exception as ex:
                    print(f"[UI Upload] Spacing check error: {ex}")

                res = upload_video(
                    run_id=run_id,
                    channel_key=channel,
                    video_path=video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    publish_time=safe_pub_time,
                )
            
            threading.Thread(target=_upload_task, daemon=True).start()
            self._send_json({"success": True, "video_id": "processing", "url": "https://youtube.com"})
            
        elif path == "/api/analytics/sync":
            channel = payload.get("channel", "newscup")
            force_mock = bool(payload.get("force_mock", False))
            
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Pull raw configurations to see if we need to auto-create simulated uploads
                cursor.execute(
                    "SELECT run_id, video_url FROM uploads WHERE channel_key=? AND status='uploaded'",
                    (channel,)
                )
                rows = cursor.fetchall()
                
                if not rows:
                    # Find completed configs
                    cursor.execute(
                        "SELECT run_id FROM video_configurations WHERE channel_key=?",
                        (channel,)
                    )
                    config_rows = cursor.fetchall()
                    for cr in config_rows:
                        r_id = cr["run_id"]
                        import hashlib
                        sim_id = hashlib.md5(r_id.encode()).hexdigest()[:11]
                        video_url = f"https://www.youtube.com/watch?v={sim_id}"
                        cursor.execute(
                            "INSERT OR IGNORE INTO uploads (run_id, channel_key, title, description, tags, status, video_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (r_id, channel, "Breaking News", "Mock Description", "news", "uploaded", video_url)
                        )
                    conn.commit()
                    
                    # Re-query
                    cursor.execute(
                        "SELECT run_id, video_url FROM uploads WHERE channel_key=? AND status='uploaded'",
                        (channel,)
                    )
                    rows = cursor.fetchall()
                
                conn.close()
                
                from analytics_puller import AnalyticsPuller
                synced_count = 0
                for row in rows:
                    run_id = row["run_id"]
                    video_url = row["video_url"]
                    if video_url:
                        AnalyticsPuller.sync_video_metrics(run_id, video_url, force_mock=force_mock)
                        synced_count += 1
                
                # Fetch rolling averages
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT AVG(va.views) as avg_views, AVG(va.impression_ctr) as avg_ctr, SUM(va.subscribers_gained) as total_subs
                    FROM video_analytics va
                    JOIN video_configurations vc ON va.run_id = vc.run_id
                    WHERE vc.channel_key = ? AND va.is_outlier = 0
                """, (channel,))
                summary_row = cursor.fetchone()
                
                summary = {
                    "avg_views": int(summary_row["avg_views"]) if summary_row and summary_row["avg_views"] is not None else 0,
                    "avg_ctr": round(float(summary_row["avg_ctr"]), 2) if summary_row and summary_row["avg_ctr"] is not None else 0.0,
                    "total_subs": summary_row["total_subs"] if summary_row and summary_row["total_subs"] is not None else 0
                }
                conn.close()
                
                self._send_json({"success": True, "synced": synced_count, "summary": summary})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
                
        elif path == "/api/settings":
            env_path = BASE_DIR / ".env"
            try:
                with open(env_path, "w", encoding="utf-8") as f:
                    for k, v in payload.items():
                        f.write(f"{k}={v}\n")
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    port = int(os.environ.get("NEWS_UI_PORT", "8088"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[UI] AI News Production Platform running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
