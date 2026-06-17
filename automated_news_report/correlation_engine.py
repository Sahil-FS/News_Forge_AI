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
    def get_optimized_pacing_and_style(cls, channel_key: str, format_mode: str) -> dict:
        """
        Analyzes historical data for a channel/format to output optimal parameters.
        Returns a dictionary of recommended parameters.
        """
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
        }

        try:
            # Check if we have enough run records
            cursor.execute("""
                SELECT COUNT(*) FROM video_analytics va
                JOIN video_configurations vc ON va.run_id = vc.run_id
                WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0
            """, (channel_key, format_mode))
            
            count = cursor.fetchone()[0]
            if count < 3:
                # Return defaults if not enough historical statistics exist
                return defaults

            # 1. Pacing & Pacing gaps (AVD / Retention correlated)
            cursor.execute("""
                SELECT vc.pause_after_sentence, vc.visual_cut_threshold, va.average_percentage_viewed
                FROM video_configurations vc
                JOIN video_analytics va ON vc.run_id = va.run_id
                WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0
                ORDER BY va.average_percentage_viewed DESC
                LIMIT 3
            """, (channel_key, format_mode))
            top_retention_rows = cursor.fetchall()
            
            if top_retention_rows:
                # Average the top 3 pacing values
                defaults["pause_after_sentence"] = round(float(np.mean([r["pause_after_sentence"] for r in top_retention_rows])), 2)
                defaults["visual_cut_threshold"] = round(float(np.mean([r["visual_cut_threshold"] for r in top_retention_rows])), 1)

            # Let's check correlation between visual_cut_threshold and retention
            cursor.execute("""
                SELECT vc.visual_cut_threshold, va.average_percentage_viewed
                FROM video_configurations vc
                JOIN video_analytics va ON vc.run_id = va.run_id
                WHERE vc.channel_key = ? AND vc.format = ? AND va.is_outlier = 0
            """, (channel_key, format_mode))
            all_rows = cursor.fetchall()
            if len(all_rows) >= 5:
                thresholds = [r["visual_cut_threshold"] for r in all_rows]
                retentions = [r["average_percentage_viewed"] for r in all_rows]
                
                # Calculate Pearson correlation coefficient
                corr = np.corrcoef(thresholds, retentions)[0, 1]
                # If corr is negative, it means smaller thresholds (faster cuts) correlate with higher retention.
                # In that case, let's nudge the visual_cut_threshold down.
                if not np.isnan(corr) and corr < -0.1:
                    print(f"[Correlation Engine] Negative correlation ({corr:.2f}) found between visual_cut_threshold and retention. Nudging recommended cut threshold down.")
                    top_threshold = defaults["visual_cut_threshold"] - 0.3
                    defaults["visual_cut_threshold"] = max(1.8, round(top_threshold, 1))
                elif not np.isnan(corr) and corr > 0.1:
                    print(f"[Correlation Engine] Positive correlation ({corr:.2f}) found. Nudging visual_cut_threshold up.")
                    top_threshold = defaults["visual_cut_threshold"] + 0.3
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
                # Take the most popular value for categorical colors and fonts in the top CTR runs
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
                WHERE u.channel_key = ? AND va.is_outlier = 0 AND u.publish_time IS NOT NULL
                ORDER BY va.views DESC
                LIMIT 10
            """, (channel_key,))
            timing_rows = cursor.fetchall()
            
            if timing_rows:
                # Extract the hour of posting (format: 'YYYY-MM-DD HH:MM:SS' or ISO format)
                # Fallback parse hour
                import re
                hours = []
                for row in timing_rows:
                    time_str = row["publish_time"]
                    match = re.search(r'\b(\d{2}):', time_str)
                    if match:
                        hours.append(int(match.group(1)))
                if hours:
                    from collections import Counter
                    defaults["optimal_post_hour"] = Counter(hours).most_common(1)[0][0]

        except Exception as e:
            print(f"[Correlation Engine Error]: {e}")
        finally:
            conn.close()

        return defaults

    @classmethod
    def get_top_performing_script_contexts(cls, channel_key: str, category: str, format_mode: str, limit: int = 3) -> list[dict]:
        """
        Retrieves high-performing script templates from similar channels/categories/formats
        to inject into the generation prompts as context references.
        """
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        scripts = []
        try:
            cursor.execute("""
                SELECT vc.script_text, vc.hook_text, va.average_percentage_viewed, va.views
                FROM video_configurations vc
                JOIN video_analytics va ON vc.run_id = va.run_id
                WHERE vc.channel_key = ? AND vc.category = ? AND vc.format = ? AND va.is_outlier = 0
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
                  AND u.publish_time IS NOT NULL
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
        Retrieve hook examples and hook traits from past videos with the highest hook_retention_ratio.
        """
        conn = cls.get_db_connection()
        cursor = conn.cursor()
        traits = []
        try:
            cursor.execute("""
                SELECT vc.hook_text, vc.script_text, va.hook_retention_ratio, va.views
                FROM video_configurations vc
                JOIN video_analytics va ON vc.run_id = va.run_id
                WHERE vc.channel_key = ? AND va.hook_retention_ratio > 0.0
                ORDER BY va.hook_retention_ratio DESC, va.views DESC
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


