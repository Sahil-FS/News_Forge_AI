"""
analytics_puller.py -- Real YouTube Analytics API integration.

Pulls actual channel/video stats from YouTube Analytics API v2 and YouTube Data API v3.
Falls back to simulated data if credentials are not set up or API calls fail.

Stats pulled per video:
  - Views, Watch time (hours), AVD, Average % viewed
  - Subscribers gained
  - Impressions + CTR
  - Card CTR
  - Audience retention curve (elapsedVideoTimeRatio)
  - Traffic sources breakdown
  - Comment sentiment (via Ollama)

The correlation_engine.py then uses this data to auto-tune the next video's:
  - Pacing (pause length, cut speed) → correlated to retention
  - Colors / fonts                   → correlated to CTR
  - Posting hour                     → correlated to views
  - Script style / hook              → correlated to watch time
"""

from __future__ import annotations

import datetime
import json
import random
import time
import requests
from pathlib import Path

from config import OLLAMA_URL, OLLAMA_MODEL
from db_manager import get_db_connection

BASE_DIR = Path(__file__).resolve().parent


class AnalyticsPuller:

    # ── Sentiment ──────────────────────────────────────────────────────────────

    @staticmethod
    def classify_sentiment_with_ollama(comment_text: str) -> str:
        """Classify comment sentiment using local Ollama model."""
        if not comment_text or not comment_text.strip():
            return "NEUTRAL"

        prompt = (
            "Analyze the sentiment of this YouTube comment. "
            "Respond only with one of these three exact words: POSITIVE, NEUTRAL, or NEGATIVE.\n"
            "Do not output any explanation, punctuation, or other text.\n\n"
            f"Comment: \"{comment_text}\"\n\n"
            "Sentiment:"
        )
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=12)
            if response.status_code == 200:
                res_txt = response.json().get("response", "").strip().upper()
                for label in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
                    if label in res_txt:
                        return label
        except Exception as e:
            print(f"[Analytics Sentiment] Ollama check failed: {e}")
        return "NEUTRAL"

    # ── Public entry point ─────────────────────────────────────────────────────

    @classmethod
    def sync_video_metrics(cls, run_id: str, video_url: str, force_mock: bool = False) -> dict:
        """
        Pull analytics for a given video and store in db.sqlite.

        Tries real YouTube Analytics API first (requires saved OAuth token).
        Falls back to simulated data if API is unavailable.
        """
        print(f"[Analytics] Syncing stats for run {run_id} | {video_url}")

        # Load channel_key and format from DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT format, category, channel_key FROM video_configurations WHERE run_id=?",
            (run_id,)
        )
        config_row = cursor.fetchone()
        conn.close()

        format_mode = config_row["format"]   if config_row else "short"
        category    = config_row["category"] if config_row else "general"
        channel_key = config_row["channel_key"] if config_row else "newscup"

        # Skip simulated video URLs
        if force_mock or "8aa7425fa64" in video_url or len(video_url) < 35:
            print("[Analytics] Simulated video URL detected — skipping real API pull.")
            return cls._generate_simulated_metrics(run_id, video_url, format_mode, category, channel_key)

        # Try real API
        token_path = BASE_DIR / f"token_{channel_key}.json"
        if token_path.exists():
            try:
                print(f"[Analytics] Token found for {channel_key} — fetching real YouTube data...")
                return cls._fetch_real_youtube_metrics(run_id, video_url, channel_key)
            except Exception as e:
                print(f"[Analytics] Real API failed ({e}) — falling back to simulation.")

        print("[Analytics] No OAuth token found — using simulated data.")
        return cls._generate_simulated_metrics(run_id, video_url, format_mode, category, channel_key)

    # ── Real YouTube Analytics API ─────────────────────────────────────────────

    @classmethod
    def _analyze_retention_curve(cls, retention_points: list[dict]) -> tuple[list[dict], list[dict], float]:
        """
        Analyze a list of retention points to identify:
          - Spikes (timestamps where P(t) > P(t - 1))
          - Dips (timestamps where P(t) - P(t + 2) > 15%)
          - Hook retention ratio (watch percentage at t = 3s as a ratio, e.g. 0.85)
        """
        if not retention_points:
            return [], [], 0.0

        sorted_pts = sorted(retention_points, key=lambda x: x["t"])

        # Helper to get interpolated value at any time t
        def get_val(t_val):
            if t_val <= sorted_pts[0]["t"]:
                return sorted_pts[0]["p"]
            if t_val >= sorted_pts[-1]["t"]:
                return sorted_pts[-1]["p"]
            for idx in range(len(sorted_pts) - 1):
                p1, p2 = sorted_pts[idx], sorted_pts[idx+1]
                if p1["t"] <= t_val <= p2["t"]:
                    if p2["t"] == p1["t"]:
                        return p1["p"]
                    return p1["p"] + (t_val - p1["t"]) * (p2["p"] - p1["p"]) / (p2["t"] - p1["t"])
            return sorted_pts[-1]["p"]

        # Hook retention ratio at t = 3s
        hook_p = get_val(3.0)
        hook_ratio = round(hook_p / 100.0, 4)

        # Spikes: P(t) > P(t - 1)
        spikes = []
        for i in range(1, len(sorted_pts)):
            prev = sorted_pts[i-1]
            curr = sorted_pts[i]
            if curr["p"] > prev["p"]:
                spikes.append({"t": curr["t"], "p": curr["p"]})

        # Dips: P(t) - P(t + 2) > 15%
        dips = []
        for curr in sorted_pts:
            p_t = curr["p"]
            p_t2 = get_val(curr["t"] + 2.0)
            if p_t - p_t2 > 15.0:
                dips.append({"t": curr["t"], "drop": round(p_t - p_t2, 2)})

        return spikes, dips, hook_ratio

    # ── Real YouTube Analytics API ─────────────────────────────────────────────

    @classmethod
    def _fetch_real_youtube_metrics(cls, run_id: str, video_url: str, channel_key: str) -> dict:
        """
        Pull real stats from YouTube Analytics API v2 + YouTube Data API v3.
        Requires: google-api-python-client, valid token_{channel_key}.json with analytics scope.
        """
        import re
        import googleapiclient.discovery

        # Extract video ID
        match = re.search(r"v=([^&#]+)", video_url)
        if not match:
            raise ValueError(f"Could not extract video ID from: {video_url}")
        video_id = match.group(1)

        # Load credentials
        from youtube_uploader import _get_credentials
        creds = _get_credentials(channel_key)

        # Build both API clients
        yt_data      = googleapiclient.discovery.build("youtube",          "v3",  credentials=creds)
        yt_analytics = googleapiclient.discovery.build("youtubeAnalytics", "v2",  credentials=creds)

        today      = datetime.date.today().isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()

        # ── 1. Core metrics ────────────────────────────────────────────────────
        print(f"[Analytics] Pulling core metrics for video {video_id}...")
        core = yt_analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=today,
            metrics=(
                "views,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,subscribersGained,cardClickRate"
            ),
            filters=f"video=={video_id}",
        ).execute()

        rows = core.get("rows", [])
        if rows:
            r = rows[0]
            views               = int(float(r[0]))
            watch_time_hours    = round(float(r[1]) / 60.0, 2)
            avd_seconds         = round(float(r[2]), 1)
            avg_percent         = round(float(r[3]), 1)
            subscribers_gained  = int(float(r[4]))
            card_ctr            = round(float(r[5]), 2)
            # YouTube Analytics API v2 does not expose real impressions or impressionClickThroughRate in realtime query API.
            # Setting them to 0 or mapping impression_ctr to card_ctr as a proxy prevents API crashes.
            impressions         = 0
            impression_ctr      = card_ctr
        else:
            print("[Analytics] No core metric rows returned — video may be too new (data takes 24-48h).")
            views = watch_time_hours = avd_seconds = avg_percent = 0
            subscribers_gained = impressions = 0
            impression_ctr = card_ctr = 0.0

        # ── 2. Retention curve ────────────────────────────────────────────────
        retention_points = []
        try:
            print(f"[Analytics] Pulling retention curve for video {video_id}...")
            ret = yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=today,
                metrics="audienceWatchRatio",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={video_id}",
            ).execute()

            for ret_row in ret.get("rows", []):
                ratio       = float(ret_row[0])          # 0.0 → 1.0 through the video
                watch_ratio = float(ret_row[1]) * 100.0  # convert to percentage
                t_secs      = round(ratio * (avd_seconds / max(avg_percent / 100.0, 0.01)), 1)
                retention_points.append({"t": t_secs, "p": round(watch_ratio, 1)})
        except Exception as e:
            print(f"[Analytics] Retention curve failed: {e}")

        if not retention_points:
            retention_points = [{"t": 0, "p": 100}]

        # Analyze retention curve for spikes, dips, and hook ratio
        spikes, dips, hook_ratio = cls._analyze_retention_curve(retention_points)

        # ── 3. Traffic sources ────────────────────────────────────────────────
        traffic_sources = {}
        try:
            print(f"[Analytics] Pulling traffic sources for video {video_id}...")
            traffic = yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=today,
                metrics="views",
                dimensions="insightTrafficSourceType",
                filters=f"video=={video_id}",
            ).execute()

            source_map = {
                "YT_SEARCH":       "search",
                "BROWSE":          "browse",
                "RELATED_VIDEO":   "suggested",
                "SHORTS":          "shorts_feed",
                "NOTIFICATION":    "notifications",
                "EXTERNAL":        "external",
                "DIRECT":          "direct",
            }
            for t_row in traffic.get("rows", []):
                raw_src = t_row[0]
                key = source_map.get(raw_src, raw_src.lower())
                traffic_sources[key] = int(float(t_row[1]))
        except Exception as e:
            print(f"[Analytics] Traffic sources failed: {e}")

        # ── 4. Geographic report ──────────────────────────────────────────────
        geographic_data = {}
        try:
            print(f"[Analytics] Pulling geographic stats for video {video_id}...")
            geo_res = yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=today,
                metrics="views",
                dimensions="country",
                filters=f"video=={video_id}",
            ).execute()
            
            geo_rows = geo_res.get("rows", [])
            total_views = sum(float(r[1]) for r in geo_rows) if geo_rows else 0.0
            if total_views > 0:
                for r_row in geo_rows:
                    country_code = r_row[0]
                    views_count = float(r_row[1])
                    pct = round((views_count / total_views) * 100.0, 2)
                    geographic_data[country_code] = pct
        except Exception as e:
            print(f"[Analytics] Geographic report failed: {e}")

        # ── 5. Demographic report ─────────────────────────────────────────────
        demographic_data = {}
        try:
            print(f"[Analytics] Pulling demographic stats for video {video_id}...")
            demo_res = yt_analytics.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=today,
                metrics="viewerPercentage",
                dimensions="ageGroup,gender",
                filters=f"video=={video_id}",
            ).execute()
            
            for r_row in demo_res.get("rows", []):
                age_group = r_row[0]
                gender = r_row[1]
                percentage = float(r_row[2])
                key = f"{age_group}_{gender}"
                demographic_data[key] = round(percentage, 2)
        except Exception as e:
            print(f"[Analytics] Demographic report failed: {e}")

        # ── 6. Comment sentiment ──────────────────────────────────────────────
        sentiment_pos, sentiment_neu, sentiment_neg = 0.6, 0.3, 0.1
        try:
            print(f"[Analytics] Pulling comments for sentiment analysis...")
            comments_resp = yt_data.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=20,
                order="relevance",
            ).execute()

            texts = [
                item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
                for item in comments_resp.get("items", [])
            ]
            if texts:
                sentiments = [cls.classify_sentiment_with_ollama(t) for t in texts[:10]]
                total = len(sentiments)
                sentiment_pos = round(sentiments.count("POSITIVE") / total, 2)
                sentiment_neu = round(sentiments.count("NEUTRAL")  / total, 2)
                sentiment_neg = round(sentiments.count("NEGATIVE") / total, 2)
                print(f"[Analytics] Sentiment: +{sentiment_pos:.0%} N{sentiment_neu:.0%} -{sentiment_neg:.0%} ({total} comments)")
        except Exception as e:
            print(f"[Analytics] Comments/sentiment failed: {e}")

        metrics = {
            "views":                         views,
            "watch_time_hours":              watch_time_hours,
            "average_view_duration_seconds": avd_seconds,
            "average_percentage_viewed":     avg_percent,
            "subscribers_gained":            subscribers_gained,
            "impressions":                   impressions,
            "impression_ctr":                impression_ctr,
            "card_ctr":                      card_ctr,
            "retention_curve_json":          json.dumps(retention_points),
            "traffic_sources_json":          json.dumps(traffic_sources),
            "geographic_demographics_json":  json.dumps(geographic_data),
            "age_gender_demographics_json":  json.dumps(demographic_data),
            "retention_spikes_json":          json.dumps(spikes),
            "retention_dips_json":            json.dumps(dips),
            "hook_retention_ratio":          hook_ratio,
            "sentiment_positive":            sentiment_pos,
            "sentiment_neutral":             sentiment_neu,
            "sentiment_negative":            sentiment_neg,
        }

        cls._save_metrics_to_db(run_id, video_url, metrics)
        return metrics

    # ── Simulated fallback ─────────────────────────────────────────────────────

    @classmethod
    def _generate_simulated_metrics(
        cls, run_id: str, video_url: str, format_mode: str, category: str, channel_key: str
    ) -> dict:
        """Realistic simulated performance stats — used when real API is unavailable."""
        random.seed(run_id)

        if format_mode == "long":
            views       = random.randint(1500, 8000)
            avg_percent = random.uniform(35.0, 58.0)
            total_dur   = 300.0
            ctr         = random.uniform(3.5, 7.8)
        else:
            views       = random.randint(4500, 24000)
            avg_percent = random.uniform(65.0, 92.0)
            total_dur   = 45.0
            ctr         = random.uniform(5.5, 11.2)

        avd_seconds       = total_dur * (avg_percent / 100.0)
        impressions       = int(views / (ctr / 100.0))
        watch_time_hours  = round((views * avd_seconds) / 3600.0, 2)
        subscribers_gained = max(1, views // random.randint(80, 150))
        card_ctr          = round(random.uniform(0.8, 3.2), 2)

        steps = 5 if format_mode == "short" else 10
        retention_points = []
        for i in range(steps + 1):
            t_val         = int((total_dur / steps) * i)
            decay_factor  = 1.0 - (i / steps) * (1.0 - (avg_percent / 120.0))
            if i == 1:
                decay_factor *= random.uniform(0.80, 0.90)
            retention_points.append({"t": t_val, "p": max(1, int(100.0 * decay_factor))})

        spikes, dips, hook_ratio = cls._analyze_retention_curve(retention_points)

        traffic_sources = {
            "search":    int(views * random.uniform(0.1, 0.3)),
            "browse":    int(views * random.uniform(0.4, 0.6)),
            "suggested": int(views * random.uniform(0.15, 0.35)),
            ("shorts_feed" if format_mode == "short" else "other"): int(views * random.uniform(0.05, 0.15)),
        }

        # Simulate geographics
        geo_sim = {}
        if "india" in channel_key:
            geo_sim = {
                "IN": round(random.uniform(80.0, 95.0), 2),
                "US": round(random.uniform(1.0, 5.0), 2),
                "AE": round(random.uniform(1.0, 4.0), 2),
                "GB": round(random.uniform(0.5, 2.0), 2),
            }
        else:
            geo_sim = {
                "US": round(random.uniform(40.0, 60.0), 2),
                "GB": round(random.uniform(15.0, 25.0), 2),
                "CA": round(random.uniform(5.0, 10.0), 2),
                "AU": round(random.uniform(3.0, 7.0), 2),
                "IN": round(random.uniform(2.0, 8.0), 2),
            }
        total_geo = sum(geo_sim.values())
        geo_sim = {k: round((v / total_geo) * 100.0, 2) for k, v in geo_sim.items()}

        # Simulate demographics
        demo_sim = {}
        age_groups = ["age13-17", "age18-24", "age25-34", "age35-44", "age45-54", "age55-64", "age65-"]
        genders = ["male", "female"]
        raw_shares = {}
        for age in age_groups:
            for gender in genders:
                if age in ["age18-24", "age25-34"]:
                    weight = random.uniform(15.0, 35.0)
                elif age in ["age35-44", "age45-54"]:
                    weight = random.uniform(5.0, 15.0)
                else:
                    weight = random.uniform(0.5, 5.0)
                raw_shares[f"{age}_{gender}"] = weight
        total_demo = sum(raw_shares.values())
        demo_sim = {k: round((v / total_demo) * 100.0, 2) for k, v in raw_shares.items()}

        sentiment_pos = round(random.uniform(0.55, 0.82), 2)
        sentiment_neg = round(random.uniform(0.04, 0.15), 2)
        sentiment_neu = round(1.0 - (sentiment_pos + sentiment_neg), 2)

        metrics = {
            "views":                         views,
            "watch_time_hours":              watch_time_hours,
            "average_view_duration_seconds": round(avd_seconds, 1),
            "average_percentage_viewed":     round(avg_percent, 1),
            "subscribers_gained":            subscribers_gained,
            "impressions":                   impressions,
            "impression_ctr":                round(ctr, 2),
            "card_ctr":                      card_ctr,
            "retention_curve_json":          json.dumps(retention_points),
            "traffic_sources_json":          json.dumps(traffic_sources),
            "geographic_demographics_json":  json.dumps(geo_sim),
            "age_gender_demographics_json":  json.dumps(demo_sim),
            "retention_spikes_json":          json.dumps(spikes),
            "retention_dips_json":            json.dumps(dips),
            "hook_retention_ratio":          hook_ratio,
            "sentiment_positive":            sentiment_pos,
            "sentiment_neutral":             sentiment_neu,
            "sentiment_negative":            sentiment_neg,
        }

        cls._save_metrics_to_db(run_id, video_url, metrics)
        return metrics

    # ── DB write ───────────────────────────────────────────────────────────────

    @classmethod
    def _save_metrics_to_db(cls, run_id: str, video_url: str, metrics: dict) -> None:
        """Write analytics metrics to video_analytics table."""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO video_analytics (
                    run_id, video_url, views, watch_time_hours,
                    average_view_duration_seconds, average_percentage_viewed,
                    subscribers_gained, impressions, impression_ctr, card_ctr,
                    retention_curve_json, traffic_sources_json,
                    geographic_demographics_json, age_gender_demographics_json,
                    retention_spikes_json, retention_dips_json, hook_retention_ratio,
                    sentiment_positive, sentiment_neutral, sentiment_negative,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                video_url,
                metrics["views"],
                metrics["watch_time_hours"],
                metrics["average_view_duration_seconds"],
                metrics["average_percentage_viewed"],
                metrics["subscribers_gained"],
                metrics["impressions"],
                metrics["impression_ctr"],
                metrics["card_ctr"],
                metrics["retention_curve_json"],
                metrics["traffic_sources_json"],
                metrics.get("geographic_demographics_json"),
                metrics.get("age_gender_demographics_json"),
                metrics.get("retention_spikes_json"),
                metrics.get("retention_dips_json"),
                metrics.get("hook_retention_ratio", 0.0),
                metrics["sentiment_positive"],
                metrics["sentiment_neutral"],
                metrics["sentiment_negative"],
                time.time(),
            ))
            conn.commit()
            v = metrics["views"]
            r = metrics["average_percentage_viewed"]
            c = metrics["impression_ctr"]
            print(f"[Analytics] Saved to DB — Views: {v:,} | Retention: {r:.1f}% | CTR: {c:.2f}%")
        except Exception as e:
            print(f"[Analytics] DB write failed: {e}")
        finally:
            conn.close()

        # Outlier detection after every sync
        try:
            conn2 = get_db_connection()
            cursor2 = conn2.cursor()
            cursor2.execute("SELECT channel_key FROM video_configurations WHERE run_id=?", (run_id,))
            row2 = cursor2.fetchone()
            conn2.close()
            ch = row2["channel_key"] if row2 else "newscup"

            from correlation_engine import CorrelationEngine
            CorrelationEngine.detect_and_flag_outliers(channel_key=ch, std_multiplier=3.0)
        except Exception:
            pass
