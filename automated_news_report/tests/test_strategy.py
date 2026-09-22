import unittest
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from voice_generator import get_voice_for_format
from news_fetcher import check_story_continuity
from long_form_script_generator import generate_context_explainer_script
from db_manager import get_db_connection, init_db

class TestComplianceStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize database
        init_db()

    def test_voice_rotation(self):
        # Test briefing voice rotation
        voice_b, speed_b = get_voice_for_format("briefing", "neutral")
        self.assertIsNotNone(voice_b)
        self.assertTrue(speed_b > 0)
        
        # Test context voice (explainer)
        voice_c, speed_c = get_voice_for_format("context", "war")
        self.assertEqual(voice_c, "af_nova")
        self.assertEqual(speed_c, 0.95)  # war overrides to 0.95
        
        # Test tracker voice
        voice_t, speed_t = get_voice_for_format("tracker", "business")
        self.assertEqual(voice_t, "am_adam")
        self.assertEqual(speed_t, 1.05)  # business overrides to 1.05

    def test_story_continuity(self):
        # Add a tracked story to mock DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tracked_stories WHERE channel_key='test_channel'")
        cursor.execute("""
            INSERT INTO tracked_stories (story_key, headline, first_seen, last_updated, episode_count, channel_key, status)
            VALUES ('story_test_123', 'US Iran conflict drone strikes middle east tensions', 0.0, 0.0, 2, 'test_channel', 'active')
        """)
        conn.commit()
        conn.close()

        # Check story continuity matching (3 keywords overlap)
        matched = check_story_continuity("New reports on Iran conflict drone developments", "test_channel")
        self.assertIsNotNone(matched)
        self.assertEqual(matched["story_key"], "story_test_123")
        self.assertEqual(matched["episode_count"], 2)

        # Check non-matching story
        not_matched = check_story_continuity("Economic updates regarding European markets inflation", "test_channel")
        self.assertIsNone(not_matched)

    def test_explainer_structure(self):
        # Sample context explainer script with bold headers and varying colons/spacing
        script = (
            "**Paragraph 1 (HOOK)**: Why is the world oil market suddenly in chaos today?\n\n"
            "**Paragraph 2 (THE NEWS)**: Oil prices surged six percent this morning following supply disruptions. "
            "Major exporters announced reductions in shipments. Authorities are monitoring the situation closely.\n\n"
            "**Paragraph 3 (THE HISTORY)**: This is not happening in isolation. We saw similar disruptions during the 1970s energy crisis. "
            "Historically, supply shocks lead to long periods of high inflation. The current situation mirrors past conflicts.\n\n"
            "**Paragraph 4 (THE PLAYERS)**: Exporters have consistently used energy as geopolitical leverage. "
            "Governments have struggled to find alternative sources quickly. Regulatory bodies are intervening.\n\n"
            "**Paragraph 5 (THE STAKES)** If exporters continue cuts, then prices will double. If alternative supply is found, then markets will stabilize. "
            "The outcome depends on diplomatic negotiations. Industry experts remain divided.\n\n"
            "**Paragraph 6 (THE VERDICT)**: The News Cup assessment: This energy shock is a turning point. "
            "It proves that reliance on single-source energy is a strategic vulnerability."
        )
        
        import re
        paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()]
        self.assertEqual(len(paragraphs), 6)
        
        all_scenes = []
        for p_idx, p in enumerate(paragraphs):
            p_clean = re.sub(
                r'^[\s\*\#_`"]*(Paragraph \d+(\s*\([^)]+\))?|HOOK|THE NEWS|THE HISTORY|THE PLAYERS|THE STAKES|THE VERDICT)[\s\*\#_`":\-]*',
                '',
                p,
                flags=re.IGNORECASE
            ).strip()
            # Split sentences
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", p_clean) if s.strip()]
            p_scenes = [{"text": s} for s in sentences]
            if p_scenes:
                if p_idx < len(paragraphs) - 1:
                    p_scenes[-1]["is_paragraph_end"] = True
                if p_idx == len(paragraphs) - 1 or "assessment:" in p_clean.lower():
                    for s in p_scenes:
                        s["is_verdict"] = True
                all_scenes.extend(p_scenes)
                
        # Verify paragraph end and verdict markings
        self.assertTrue(all_scenes[0].get("is_paragraph_end"))
        self.assertTrue(all_scenes[-1].get("is_verdict"))
        
        # Verify that all labels were stripped completely
        for s in all_scenes:
            self.assertNotIn("Paragraph", s["text"])
            self.assertNotIn("HOOK", s["text"])
            self.assertNotIn("THE NEWS", s["text"])
            self.assertNotIn("THE VERDICT", s["text"])

    def test_dynamic_lookback(self):
        import time
        from news_fetcher import get_dynamic_lookback_hours
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM runs WHERE channel_key='test_channel_lookback'")
        
        now = time.time()
        
        # Test 1: 18 hours ago
        finished_18_h_ago = now - (18 * 3600)
        cursor.execute(
            "INSERT INTO runs (id, channel_key, category, format, stage, status, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run_lb_1", "test_channel_lookback", "general", "short", "complete", "success", finished_18_h_ago - 3600, finished_18_h_ago)
        )
        conn.commit()
        
        lb_1 = get_dynamic_lookback_hours("test_channel_lookback")
        # 18 hours + 1 hour buffer = 19.0
        self.assertAlmostEqual(lb_1, 19.0, places=1)
        
        # Test 2: 5 hours ago
        cursor.execute("DELETE FROM runs WHERE channel_key='test_channel_lookback'")
        finished_5_h_ago = now - (5 * 3600)
        cursor.execute(
            "INSERT INTO runs (id, channel_key, category, format, stage, status, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run_lb_2", "test_channel_lookback", "general", "short", "complete", "success", finished_5_h_ago - 3600, finished_5_h_ago)
        )
        conn.commit()
        
        lb_2 = get_dynamic_lookback_hours("test_channel_lookback")
        # 5 hours + 1 hour buffer = 6.0
        self.assertAlmostEqual(lb_2, 6.0, places=1)
        
        # Cleanup
        cursor.execute("DELETE FROM runs WHERE channel_key='test_channel_lookback'")
        conn.commit()
        conn.close()

if __name__ == "__main__":
    unittest.main()
