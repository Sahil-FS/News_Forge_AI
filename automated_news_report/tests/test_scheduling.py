# tests/test_scheduling.py
import sys
import os
import unittest
import sqlite3
import types
import datetime as real_datetime
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import youtube_uploader
from youtube_uploader import get_geo_scheduled_upload_time, DB_PATH
import config

class TestDynamicScheduling(unittest.TestCase):
    def setUp(self):
        # Backup existing uploads table data to avoid interference
        self.conn = sqlite3.connect(str(DB_PATH))
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM uploads")
        self.backup_uploads = cursor.fetchall()
        cursor.execute("DELETE FROM uploads")
        self.conn.commit()
        
        # Save original sys.modules datetime
        self.orig_sys_datetime = sys.modules.get('datetime')

    def tearDown(self):
        # Restore original sys.modules
        if self.orig_sys_datetime:
            sys.modules['datetime'] = self.orig_sys_datetime

        # Restore backup data
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM uploads")
        for row in self.backup_uploads:
            cursor.execute(
                "INSERT INTO uploads (run_id, channel_key, title, description, tags, status, publish_time, video_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row
            )
        self.conn.commit()
        self.conn.close()

    def simulate_batch_run(self, start_dt_utc, channel_key, country, expected_tz_offset_hours):
        # Delete previous test uploads
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM uploads")
        self.conn.commit()

        print(f"\n--- Simulating batch from {start_dt_utc.isoformat()} UTC for country {country} ---")
        
        # Create a mock module
        mock_datetime_mod = types.ModuleType('datetime')
        for name in dir(real_datetime):
            setattr(mock_datetime_mod, name, getattr(real_datetime, name))

        class MockDatetime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                if tz:
                    return start_dt_utc.astimezone(tz)
                return start_dt_utc
            @classmethod
            def fromisoformat(cls, *args, **kwargs):
                return real_datetime.datetime.fromisoformat(*args, **kwargs)

        mock_datetime_mod.datetime = MockDatetime
        sys.modules['datetime'] = mock_datetime_mod

        # Run for 10 videos
        scheduled_times = []
        for i in range(10):
            pub_time = get_geo_scheduled_upload_time(channel_key, country=country)
            scheduled_times.append(pub_time)
            
            # Save to DB so subsequent runs see it
            cursor.execute(
                "INSERT INTO uploads (run_id, channel_key, status, publish_time) VALUES (?, ?, ?, ?)",
                (f"test_run_{i}", channel_key, "scheduled", pub_time)
            )
            self.conn.commit()

        # Verify and print
        for idx, pt in enumerate(scheduled_times, 1):
            pt_utc = datetime.fromisoformat(pt.replace("Z", "+00:00")).astimezone(timezone.utc)
            pt_local = (pt_utc + timedelta(hours=expected_tz_offset_hours)).replace(tzinfo=None)
            print(f"  Video {idx:02d}: UTC: {pt} | Local time: {pt_local.strftime('%Y-%m-%d %H:%M:%S')}")

        # Verify boundary conditions
        first_utc = datetime.fromisoformat(scheduled_times[0].replace("Z", "+00:00")).astimezone(timezone.utc)
        first_local = (first_utc + timedelta(hours=expected_tz_offset_hours)).replace(tzinfo=None)
        
        last_utc = datetime.fromisoformat(scheduled_times[-1].replace("Z", "+00:00")).astimezone(timezone.utc)
        last_local = (last_utc + timedelta(hours=expected_tz_offset_hours)).replace(tzinfo=None)
        
        # Boundary limit should be 5:00 AM on the day after first_local
        boundary_dt = datetime(first_local.year, first_local.month, first_local.day, 5, 0, 0) + timedelta(days=1)
        
        self.assertTrue(last_local <= boundary_dt, f"Last video {last_local} exceeds 5:00 AM boundary {boundary_dt}")
        print(f"  SUCCESS: All videos fit! Last is {last_local.strftime('%H:%M')} (Boundary is {boundary_dt.strftime('%m-%d %H:%M')})")

    def test_scheduling_all_hours(self):
        # June 17, 2026 runs
        # 1. India run at 12:00 PM IST (6:30 AM UTC)
        run_12_ist = datetime(2026, 6, 17, 6, 30, 0, tzinfo=timezone.utc)
        self.simulate_run_with_spacing(run_12_ist, "newscup_india", "IN", 5.5, 100)

        # 2. India run at 3:00 PM IST (9:30 AM UTC)
        run_15_ist = datetime(2026, 6, 17, 9, 30, 0, tzinfo=timezone.utc)
        self.simulate_run_with_spacing(run_15_ist, "newscup_india", "IN", 5.5, 100)

        # 3. US run at 12:00 PM EST (5:00 PM UTC)
        run_12_est = datetime(2026, 6, 17, 17, 0, 0, tzinfo=timezone.utc)
        self.simulate_run_with_spacing(run_12_est, "newscup", "US", 5.5, 100)

        # 4. US run at 10:00 PM EST (June 18, 3:00 AM UTC)
        run_22_est = datetime(2026, 6, 18, 3, 0, 0, tzinfo=timezone.utc)
        self.simulate_run_with_spacing(run_22_est, "newscup", "US", 5.5, 100)

    def simulate_run_with_spacing(self, start_dt_utc, channel_key, country, offset_hours, spacing):
        # Temporarily mock UPLOAD_SPACING_MINUTES
        orig_spacing = config.UPLOAD_SPACING_MINUTES
        config.UPLOAD_SPACING_MINUTES = spacing
        try:
            self.simulate_batch_run(start_dt_utc, channel_key, country, offset_hours)
        finally:
            config.UPLOAD_SPACING_MINUTES = orig_spacing

    def test_scheduling_excess_uploads(self):
        # US run at 12:00 PM EST (5:00 PM UTC)
        run_12_est = datetime(2026, 6, 17, 17, 0, 0, tzinfo=timezone.utc)
        
        # mock modules
        mock_datetime_mod = types.ModuleType('datetime')
        for name in dir(real_datetime):
            setattr(mock_datetime_mod, name, getattr(real_datetime, name))

        class MockDatetime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                if tz:
                    return run_12_est.astimezone(tz)
                return run_12_est
            @classmethod
            def fromisoformat(cls, *args, **kwargs):
                return real_datetime.datetime.fromisoformat(*args, **kwargs)

        mock_datetime_mod.datetime = MockDatetime
        sys.modules['datetime'] = mock_datetime_mod

        # First clean DB
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM uploads")
        self.conn.commit()

        # Let's schedule 10 videos as usual
        for i in range(10):
            pub_time = get_geo_scheduled_upload_time("newscup", country="US")
            cursor.execute(
                "INSERT INTO uploads (run_id, channel_key, status, publish_time) VALUES (?, ?, ?, ?)",
                (f"test_run_{i}", "newscup", "scheduled", pub_time)
            )
            self.conn.commit()

        # Now, try to schedule the 11th video.
        # This simulates the situation where the database already contains 10 uploads in the active batch.
        pub_time_11 = get_geo_scheduled_upload_time("newscup", country="US")
        
        # Verify that the 11th video fits before the 5:00 AM local boundary
        pt_utc = datetime.fromisoformat(pub_time_11.replace("Z", "+00:00")).astimezone(timezone.utc)
        pt_local = (pt_utc + timedelta(hours=5.5)).replace(tzinfo=None)
        boundary_dt = datetime(2026, 6, 18, 5, 0, 0)
        
        self.assertTrue(pt_local <= boundary_dt, f"11th video {pt_local} exceeds 5:00 AM boundary {boundary_dt}")
        print(f"  SUCCESS: 11th video fits! Scheduled at {pt_local.strftime('%Y-%m-%d %H:%M:%S')} (Boundary is {boundary_dt.strftime('%m-%d %H:%M')})")

if __name__ == "__main__":
    unittest.main()
