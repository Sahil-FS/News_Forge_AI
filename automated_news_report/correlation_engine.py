"""Correlation Engine for the automated news feedback loop system."""

from __future__ import annotations

import sqlite3
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "db.sqlite"


class CorrelationEngine:
    @staticmethod
    def get_db_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def detect_and_flag_outliers(cls, channel_key: str, std_multiplier: float = 3.0) -> None:
        """
        Detect and flag viral outliers (views > mean + multiplier * std_dev)
        for a given channel so they don't skew optimization templates.
        """
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        try:
            # Query all uploaded video views for this channel
            cursor.execute("""
                SELECT va.run_id, va.views 
                FROM video_analytics va
                JOIN video_configurations vc ON va.run_id = vc.run_id
                WHERE vc.channel_key = ?
            """, (channel_key,))
            rows = cursor.fetchall()
            if len(rows) < 5:
                # Not enough data to run outlier detection
                return

            views_list = [row["views"] for row in rows]
            mean = np.mean(views_list)
            std = np.std(views_list)
            threshold = mean + (std_multiplier * std)

            # Reset outlier flags first
            cursor.execute("""
                UPDATE video_analytics 
                SET is_outlier = 0 
                WHERE run_id IN (
                    SELECT va.run_id 
                    FROM video_analytics va
                    JOIN video_configurations vc ON va.run_id = vc.run_id
                    WHERE vc.channel_key = ?
                )
            """, (channel_key,))

            # Mark outliers
            outliers = [row["run_id"] for row in rows if row["views"] > threshold]
            for run_id in outliers:
                cursor.execute("UPDATE video_analytics SET is_outlier = 1 WHERE run_id = ?", (run_id,))
                print(f"[Outlier Detection] Marked run {run_id} as a viral outlier (Views: {views_list[views_list.index(next(x for x in views_list if x > threshold))]}, threshold: {threshold:.1f})")
            
            conn.commit()
        except Exception as e:
            print(f"[Outlier Engine Error]: {e}")
        finally:
            conn.close()

    @classmethod
    @classmethod
    def get_optimized_pacing_and_style(cls, channel_key: str, format_mode: str, explore: bool = True, epsilon: float = 0.20) -> dict:
        """
        Analyzes historical data for a channel/format to output optimal parameters.
        Uses an Epsilon-Greedy strategy (exploration vs exploitation):
          - (1 - epsilon) of the time (80%): Exploits the top historical performers.
          - epsilon of the time (20%): Explores controlled variants to generate parameter variance
            needed for statistical correlation.
        """
        import random
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        
        # Default fallback values from config.py
        defaults = {
            "pause_after_sentence": 0.20,
            "visual_cut_threshold": 2.8,
            "primary_color": "#b91c1c" if "india" not in channel_key else "#0f766e",
            "accent_color": "#0f766e" if "india" not in channel_key else "#b91c1c",
            "badge_color": "#b91c1c" if "india" not in channel_key else "#0f766e",
            "font_family": "C:/Windows/Fonts/arialbd.ttf",
            "has_anchor": 1,
            "has_map_stinger": 1,
            "optimal_post_hour": 8 if "india" in channel_key else 14, # default to morning IST vs evening UTC
            "is_exploration": 0,
        }

        try:
            # Check if we have enough run records
            cursor.execute("""
                SELECT COUNT(*) FROM video_analytics va
                JOIN video_configurations vc ON va.run_id = vc.run_id
                WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0
            """, (channel_key, format_mode))
            
            count = cursor.fetchone()[0]
            if count >= 3:
                # 1. Pacing & Pacing gaps (AVD / Retention correlated)
                cursor.execute("""
                    SELECT vc.pause_after_sentence, vc.visual_cut_threshold, va.average_percentage_viewed
                    FROM video_configurations vc
                    JOIN video_analytics va ON vc.run_id = va.run_id
                    WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0 AND va.average_percentage_viewed > 0
                    ORDER BY va.average_percentage_viewed DESC
                    LIMIT 3
                """, (channel_key, format_mode))
                top_retention_rows = cursor.fetchall()
                
                if top_retention_rows:
                    defaults["pause_after_sentence"] = round(float(np.mean([r["pause_after_sentence"] for r in top_retention_rows])), 2)
                    defaults["visual_cut_threshold"] = round(float(np.mean([r["visual_cut_threshold"] for r in top_retention_rows])), 1)

                # Check correlation between visual_cut_threshold and retention safely (avoid stddev = 0 division)
                cursor.execute("""
                    SELECT vc.visual_cut_threshold, va.average_percentage_viewed
                    FROM video_configurations vc
                    JOIN video_analytics va ON vc.run_id = va.run_id
                    WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0 AND va.average_percentage_viewed > 0
                """, (channel_key, format_mode))
                all_rows = cursor.fetchall()
                if len(all_rows) >= 5:
                    thresholds = [r["visual_cut_threshold"] for r in all_rows]
                    retentions = [r["average_percentage_viewed"] for r in all_rows]
                    std_thresh = float(np.std(thresholds))
                    std_ret = float(np.std(retentions))
                    
                    if std_thresh > 0.05 and std_ret > 0.5:
                        corr = np.corrcoef(thresholds, retentions)[0, 1]
                        if not np.isnan(corr) and corr < -0.1:
                            print(f"[Correlation Engine] Negative correlation ({corr:.2f}) found between visual_cut_threshold and retention. Nudging cut threshold down.")
                            top_threshold = defaults["visual_cut_threshold"] - 0.2
                            defaults["visual_cut_threshold"] = max(1.8, round(top_threshold, 1))
                        elif not np.isnan(corr) and corr > 0.1:
                            print(f"[Correlation Engine] Positive correlation ({corr:.2f}) found. Nudging visual_cut_threshold up.")
                            top_threshold = defaults["visual_cut_threshold"] + 0.2
                            defaults["visual_cut_threshold"] = min(4.0, round(top_threshold, 1))

                # 2. Colors & Typography (CTR Correlated)
                cursor.execute("""
                    SELECT vc.primary_color, vc.accent_color, vc.badge_color, vc.font_family, va.impression_ctr
                    FROM video_configurations vc
                    JOIN video_analytics va ON vc.run_id = va.run_id
                    WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0
                    ORDER BY va.impression_ctr DESC
                    LIMIT 3
                """, (channel_key, format_mode))
                top_ctr_rows = cursor.fetchall()

                if top_ctr_rows:
                    from collections import Counter
                    defaults["primary_color"] = Counter([r["primary_color"] for r in top_ctr_rows]).most_common(1)[0][0]
                    defaults["accent_color"] = Counter([r["accent_color"] for r in top_ctr_rows]).most_common(1)[0][0]
                    defaults["badge_color"] = Counter([r["badge_color"] for r in top_ctr_rows]).most_common(1)[0][0]
                    defaults["font_family"] = Counter([r["font_family"] for r in top_ctr_rows]).most_common(1)[0][0]

                # 3. Optimize Upload Timing
                cursor.execute("""
                    SELECT u.publish_time, va.views
                    FROM uploads u
                    JOIN video_analytics va ON u.run_id = va.run_id
                    WHERE u.channel_key = ? AND va.is_outlier = 0 AND u.publish_time IS NOT NULL AND va.views > 0
                    ORDER BY va.views DESC
                    LIMIT 10
                """, (channel_key,))
                timing_rows = cursor.fetchall()
                
                if timing_rows:
                    import re
                    hours = []
                    for row in timing_rows:
                        time_str = row["publish_time"]
                        match = re.search(r'[T\s](\d{2}):', time_str)
                        if match:
                            hours.append(int(match.group(1)))
                    if hours:
                        from collections import Counter
                        defaults["optimal_post_hour"] = Counter(hours).most_common(1)[0][0]

        except Exception as e:
            print(f"[Correlation Engine Error]: {e}")
        finally:
            conn.close()

        # Epsilon-Greedy Parameter Exploration (A/B Testing)
        if explore and random.random() < epsilon:
            # Exploration variant: introduce controlled variance to discover higher retention drivers
            cut_candidates = [2.0, 2.3, 2.6, 3.0, 3.4]
            pause_candidates = [0.15, 0.18, 0.25, 0.30]
            defaults["visual_cut_threshold"] = random.choice(cut_candidates)
            defaults["pause_after_sentence"] = random.choice(pause_candidates)
            defaults["is_exploration"] = 1
            print(f"[Correlation Engine] [A/B EXPLORATION] Cut Speed={defaults['visual_cut_threshold']}s | Pause={defaults['pause_after_sentence']}s")
        else:
            defaults["is_exploration"] = 0
            # Milestone Governor: Accelerate pacing if behind 90-day target trajectory
            try:
                from db_manager import get_milestone_pace_status
                pace_info = get_milestone_pace_status()
                if pace_info.get("pace_status") in ("critically_behind", "behind"):
                    adaptive_cut = pace_info.get("adaptive_cut_speed", 2.0)
                    defaults["visual_cut_threshold"] = min(defaults["visual_cut_threshold"], adaptive_cut)
            except Exception:
                pass
            print(f"[Correlation Engine] [EXPLOIT BEST] Cut Speed={defaults['visual_cut_threshold']}s | Pause={defaults['pause_after_sentence']}s | Post Hour={defaults.get('optimal_post_hour', 12)}:00 UTC")

        return defaults

    @classmethod
    def get_top_performing_script_contexts(cls, channel_key: str, category: str, format_mode: str, limit: int = 3) -> list[dict]:
        """
        Retrieves high-performing script templates from similar channels/categories/formats
        to inject into the generation prompts as context references.
        Prioritizes scripts with verified positive audience retention.
        """
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        scripts = []
        try:
            # 1. First try matching category with non-zero retention
            cursor.execute("""
                SELECT vc.script_text, vc.hook_text, va.average_percentage_viewed, va.views
                FROM video_configurations vc
                JOIN video_analytics va ON vc.run_id = va.run_id
                WHERE vc.channel_key = ? AND vc.category = ? AND vc.format = ? AND va.is_outlier = 0
                  AND va.average_percentage_viewed > 0.0
                ORDER BY va.average_percentage_viewed DESC, va.views DESC
                LIMIT ?
            """, (channel_key, category, format_mode, limit))
            
            rows = cursor.fetchall()
            for r in rows:
                scripts.append({
                    "script_text": r["script_text"],
                    "hook_text": r["hook_text"],
                    "retention": r["average_percentage_viewed"]
                })

            # 2. If not enough for this category, broaden to all categories for this channel
            if len(scripts) < limit:
                needed = limit - len(scripts)
                cursor.execute("""
                    SELECT vc.script_text, vc.hook_text, va.average_percentage_viewed, va.views
                    FROM video_configurations vc
                    JOIN video_analytics va ON vc.run_id = va.run_id
                    WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0
                      AND va.average_percentage_viewed > 0.0
                    ORDER BY va.average_percentage_viewed DESC, va.views DESC
                    LIMIT ?
                """, (channel_key, format_mode, needed))
                for r in cursor.fetchall():
                    if not any(s["hook_text"] == r["hook_text"] for s in scripts):
                        scripts.append({
                            "script_text": r["script_text"],
                            "hook_text": r["hook_text"],
                            "retention": r["average_percentage_viewed"]
                        })

            # 3. Fallback: top by views if retention was zero across all
            if not scripts:
                cursor.execute("""
                    SELECT vc.script_text, vc.hook_text, va.average_percentage_viewed, va.views
                    FROM video_configurations vc
                    JOIN video_analytics va ON vc.run_id = va.run_id
                    WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0 AND va.views > 0
                    ORDER BY va.views DESC
                    LIMIT ?
                """, (channel_key, format_mode, limit))
                for r in cursor.fetchall():
                    scripts.append({
                        "script_text": r["script_text"],
                        "hook_text": r["hook_text"],
                        "retention": r["average_percentage_viewed"]
                    })
        except Exception as e:
            print(f"[Script Context Injection Error]: {e}")
        finally:
            conn.close()
            
        return scripts

    @classmethod
    def get_optimized_scheduling_offset(cls, channel_key: str, country: str) -> int | None:
        """
        Retrieves the optimal posting hour (0-23 in UTC) for a specific target country,
        optionally learning from the database if there are high-performing videos targeting that country.
        
        If no data exists, returns None so uploader fallback mappings can be used.
        """
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT u.publish_time, va.views
                FROM uploads u
                JOIN video_analytics va ON u.run_id = va.run_id
                JOIN video_configurations vc ON u.run_id = vc.run_id
                WHERE u.channel_key = ? AND vc.primary_location = ? AND va.is_outlier = 0
                  AND u.publish_time IS NOT NULL AND va.views > 0
                ORDER BY va.views DESC
                LIMIT 5
            """, (channel_key, country))
            
            rows = cursor.fetchall()
            if rows:
                import re
                from collections import Counter
                hours = []
                for row in rows:
                    time_str = row["publish_time"]
                    match = re.search(r'\b(\d{2}):', time_str)
                    if match:
                        hours.append(int(match.group(1)))
                if hours:
                    return Counter(hours).most_common(1)[0][0]
        except Exception as e:
            print(f"[Correlation Engine] get_optimized_scheduling_offset error: {e}")
        finally:
            conn.close()
        return None

    @classmethod
    def get_hook_retention_traits(cls, channel_key: str, limit: int = 3) -> list[dict]:
        """
        Retrieve hook examples and hook traits from past videos with the highest hook_retention_ratio
        and positive views.
        """
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        traits = []
        try:
            cursor.execute("""
                SELECT vc.hook_text, vc.script_text, va.hook_retention_ratio, va.views
                FROM video_configurations vc
                JOIN video_analytics va ON vc.run_id = va.run_id
                WHERE vc.channel_key = ? AND va.hook_retention_ratio > 0.0 AND va.views > 0
                ORDER BY va.views DESC, va.hook_retention_ratio DESC
                LIMIT ?
            """, (channel_key, limit))
            for row in cursor.fetchall():
                hook = row["hook_text"]
                if not hook or not hook.strip():
                    script = row["script_text"] or ""
                    hook = script[:150] + "..." if len(script) > 150 else script
                
                traits.append({
                    "hook_text": hook.strip(),
                    "hook_retention_ratio": row["hook_retention_ratio"]
                })
        except Exception as e:
            print(f"[Correlation Engine] get_hook_retention_traits error: {e}")
        finally:
            conn.close()
        return traits

    @classmethod
    def generate_learning_diagnostics(cls, channel_key: str) -> None:
        """
        Analyze database records to generate and print a self-learning diagnostic report
        directly to the terminal console during preflight execution.
        """
        import datetime
        
        print("\n" + "=" * 65)
        print(f"  [AI AUDIT] SELF-LEARNING DIAGNOSTICS & SYSTEM AUDIT ({channel_key.upper()})")
        print("=" * 65)
        
        conn = None
        def _safe_text(val):
            if not val:
                return ""
            return str(val).encode("ascii", errors="replace").decode("ascii")

        try:
            conn = cls.get_db_connection()
            cursor = conn.cursor()
            
            # 1. Spacing Safety Guard Check
            cursor.execute("""
                SELECT publish_time, title FROM uploads 
                WHERE channel_key=? AND (status='uploaded' OR status='scheduled' OR status='uploading')
                ORDER BY publish_time DESC LIMIT 1
            """, (channel_key,))
            last_row = cursor.fetchone()
            
            if last_row and last_row[0]:
                pub_str = last_row[0]
                if pub_str.endswith("Z"):
                    pub_str = pub_str[:-1] + "+00:00"
                last_pub = datetime.datetime.fromisoformat(pub_str).astimezone(datetime.timezone.utc)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                diff = now_utc - last_pub
                diff_mins = int(diff.total_seconds() / 60)
                
                print("[SAFETY] Spacing Audit:")
                print(f"  * Last Upload:  \"{_safe_text(last_row[1][:45])}...\"")
                
                if last_pub > now_utc:
                    next_in = int((last_pub - now_utc).total_seconds() / 60)
                    print(f"  * Next Scheduled: in {next_in} minutes")
                else:
                    print(f"  * Time Elapsed: {diff_mins} minutes ago")
                
                if diff < datetime.timedelta(minutes=120):
                    remaining = 120 - diff_mins
                    print(f"  * [!] WARNING: Spacing interval is too short! Spacing Guard is ACTIVE.")
                    print(f"  * [SHIELD] Your next upload schedule will be safely pushed by +{remaining} minutes.")
                else:
                    print("  * [OK] Spacing check passed. Spacing Guard is idle (interval > 2 hours).")
            else:
                print("[SAFETY] Spacing Audit: No previous uploads found in database.")
                
            # 2. Timing and Pacing Recommendations
            pacing = cls.get_optimized_pacing_and_style(channel_key, "short")
            opt_hour = pacing.get("optimal_post_hour", 12)
            
            print("\n[OPTIMIZER] Learned Scheduling & Video Parameters:")
            print(f"  * Learned Optimal Post Hour: {opt_hour:02d}:00 UTC")
            print(f"  * Optimal Narration Pause:   {pacing.get('pause_after_sentence', 0.2)}s")
            print(f"  * Optimal Visual Cut Speed:  {pacing.get('visual_cut_threshold', 2.8)}s")
            print(f"  * Optimal Brand Colors:      {pacing.get('primary_color')} (Primary) | {pacing.get('accent_color')} (Accent)")
            
            # 3. Topic & Category Recommendation
            cursor.execute("""
                SELECT vc.category, AVG(va.views) as avg_views, COUNT(*) as video_count
                FROM video_analytics va
                JOIN video_configurations vc ON va.run_id = vc.run_id
                WHERE vc.channel_key = ? AND va.is_outlier = 0 AND va.views > 0
                GROUP BY vc.category
                ORDER BY avg_views DESC
            """, (channel_key,))
            cat_rows = cursor.fetchall()
            
            cursor.execute("""
                SELECT vc.detected_context, AVG(va.views) as avg_views, COUNT(*) as video_count
                FROM video_analytics va
                JOIN video_configurations vc ON va.run_id = vc.run_id
                WHERE vc.channel_key = ? AND va.is_outlier = 0 AND va.views > 0
                GROUP BY vc.detected_context
                ORDER BY avg_views DESC
            """, (channel_key,))
            ctx_rows = cursor.fetchall()
            
            if cat_rows or ctx_rows:
                print("\n[AUDIENCE] Top-Performing Categories & Contexts:")
                if cat_rows:
                    best_cat = cat_rows[0]
                    print(f"  * Best Category: '{_safe_text(best_cat[0])}' (Avg Views: {int(best_cat[1]):,} across {best_cat[2]} videos)")
                if ctx_rows:
                    best_ctx = ctx_rows[0]
                    print(f"  * Best Context:  '{_safe_text(best_ctx[0])}' (Avg Views: {int(best_ctx[1]):,} across {best_ctx[2]} videos)")
            else:
                print("\n[AUDIENCE] Topic & Category Audit: Not enough historical statistics to run topic diagnostics.")
                
            # 4. Best Hooks Performance
            hooks = cls.get_hook_retention_traits(channel_key, limit=2)
            if hooks:
                print("\n[RETENTION] Learned High-Retention Hook Traits:")
                for idx, h in enumerate(hooks):
                    clean_hook = _safe_text(h['hook_text'].replace('\n', ' '))
                    if len(clean_hook) > 55:
                        clean_hook = clean_hook[:52] + "..."
                    print(f"  {idx+1}. Hook: \"{clean_hook}\" (Retention: {h['hook_retention_ratio']*100:.1f}%)")

            # 5. 90-Day Milestone Pace Tracker (10M Views, 1,000 Subs)
            try:
                from db_manager import get_milestone_pace_status
                pace = get_milestone_pace_status()
                print("\n[GROWTH] 90-Day Target Milestone Tracker (10M Views / 1,000 Subs):")
                v_pct = (pace.get('total_views', 0) / max(1, pace.get('target_views', 10000000))) * 100
                s_pct = (pace.get('total_subscribers', 0) / max(1, pace.get('target_subscribers', 1000))) * 100
                print(f"  * Day {pace.get('days_elapsed', 0):.1f} of {pace.get('target_days', 90)} | Total Views: {pace.get('total_views', 0):,} / {pace.get('target_views', 10000000):,} ({v_pct:.2f}%)")
                print(f"  * Total Subscribers: {pace.get('total_subscribers', 0):,} / {pace.get('target_subscribers', 1000):,} ({s_pct:.1f}%)")
                print(f"  * Required Daily Velocity: {int(pace.get('required_daily_velocity', 0)):,} views/day | Pace Status: [{pace.get('pace_status', 'unknown').upper()}]")
                print(f"  * Adaptive Production Directives:")
                print(f"      - Viral Threshold Gate:  {pace.get('adaptive_viral_threshold', 75)}/100")
                print(f"      - Script Target Words:   {pace.get('adaptive_word_target', 140)} words")
                print(f"      - Visual Cut Speed:      {pace.get('adaptive_cut_speed', 2.0)}s")
                print(f"      - Narration Speed Boost: {pace.get('adaptive_speed_boost', 1.15)}x")
            except Exception as _p_err:
                print(f"\n[GROWTH] Milestone tracker note: {_p_err}")
                    
        except Exception as e:
            print(f"[Diagnostics] Error generating report: {e}")
        finally:
            if conn:
                conn.close()
            
        print("=" * 65 + "\n")


