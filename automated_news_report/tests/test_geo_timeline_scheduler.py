# tests/test_geo_timeline_scheduler.py
import sys
import os
import unittest
import sqlite3
import datetime as real_datetime
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import youtube_uploader
from youtube_uploader import get_geo_scheduled_upload_time, GEO_TIMELINE_SLOTS, DB_PATH
import config


class TestGeoTimelineScheduler(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(str(DB_PATH))
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM uploads")
        self.backup_uploads = cursor.fetchall()
        cursor.execute("DELETE FROM uploads")
        self.conn.commit()

    def tearDown(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM uploads")
        for row in self.backup_uploads:
            cursor.execute(
                "INSERT INTO uploads (run_id, channel_key, title, description, tags, status, publish_time, video_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row
            )
        self.conn.commit()
        self.conn.close()

    def test_slots_structure(self):
        """Verify the 6 defined geo-timeline slots cover 4:30 PM to 5:00 AM IST."""
        self.assertEqual(len(GEO_TIMELINE_SLOTS), 6)
        
        # Slot 1: 16:30 - 17:30 IST
        self.assertEqual(GEO_TIMELINE_SLOTS[0]["start_hour"], 16)
        self.assertEqual(GEO_TIMELINE_SLOTS[0]["start_min"], 30)
        self.assertEqual(GEO_TIMELINE_SLOTS[0]["end_hour"], 17)
        self.assertEqual(GEO_TIMELINE_SLOTS[0]["end_min"], 30)
        
        # Slot 6: 03:30 - 04:45 IST
        self.assertEqual(GEO_TIMELINE_SLOTS[5]["start_hour"], 3)
        self.assertEqual(GEO_TIMELINE_SLOTS[5]["start_min"], 30)
        self.assertEqual(GEO_TIMELINE_SLOTS[5]["end_hour"], 4)
        self.assertEqual(GEO_TIMELINE_SLOTS[5]["end_min"], 45)
        self.assertTrue(GEO_TIMELINE_SLOTS[5].get("next_day"))

    def test_six_sequential_slots_distribution(self):
        """Verify 6 sequential videos map cleanly to the 6 slots without collisions and within 5:00 AM boundary."""
        channel_key = "newscup"
        scheduled_utc_times = []
        cursor = self.conn.cursor()

        for i in range(6):
            pub_time = get_geo_scheduled_upload_time(channel_key)
            scheduled_utc_times.append(pub_time)
            
            # Save into DB so subsequent calls see the existing batch
            cursor.execute(
                "INSERT INTO uploads (run_id, channel_key, status, publish_time) VALUES (?, ?, ?, ?)",
                (f"test_run_{i}", channel_key, "scheduled", pub_time)
            )
            self.conn.commit()

        # Convert all to IST
        ist_times = []
        for pt in scheduled_utc_times:
            pt_clean = pt.replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(pt_clean).astimezone(timezone.utc)
            dt_ist = dt_utc + timedelta(hours=5.5)
            ist_times.append(dt_ist.replace(tzinfo=None))

        # Check strictly increasing without collision
        for i in range(len(ist_times) - 1):
            self.assertLess(ist_times[i], ist_times[i+1], f"Video {i} ({ist_times[i]}) is not before Video {i+1} ({ist_times[i+1]})")
            diff_mins = (ist_times[i+1] - ist_times[i]).total_seconds() / 60.0
            self.assertGreaterEqual(diff_mins, 20.0, f"Spacing between video {i} and {i+1} is too small: {diff_mins}m")

        # Verify last video is before 5:00 AM next-day boundary
        last_time = ist_times[-1]
        first_time = ist_times[0]
        # Next-day 5:00 AM relative to the batch start
        if first_time.hour < 5:
            boundary_dt = datetime(first_time.year, first_time.month, first_time.day, 5, 0, 0)
        else:
            boundary_dt = datetime(first_time.year, first_time.month, first_time.day, 5, 0, 0) + timedelta(days=1)
        self.assertLessEqual(last_time, boundary_dt, f"Last scheduled time {last_time} exceeds 5:00 AM boundary {boundary_dt}")


if __name__ == "__main__":
    unittest.main()
