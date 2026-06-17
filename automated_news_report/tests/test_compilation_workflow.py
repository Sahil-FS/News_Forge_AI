import unittest
import os
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from script_generator import generate_compilation_script
from scene_planner import plan_scenes, tag_special_scenes
from image_fetcher import build_split_screen_collage, IMAGE_DIR

class TestCompilationWorkflow(unittest.TestCase):
    def test_generate_compilation_script(self):
        articles = [
            {"title": "Suryakumar Yadav makes statement on MI conflict", "summary": "Suryakumar Yadav has posted an update clarifying his stand on Mumbai Indians controversy.", "full_article_text": "Suryakumar Yadav unfollowed the MI management on Instagram following a row over captaincy."},
            {"title": "Shashank on Shreyas Iyer team dispute", "summary": "Shashank expressed support for Shreyas Iyer following team decisions.", "full_article_text": "Shashank posted a tweet praising Shreyas Iyer after the match selection spat."},
            {"title": "Tilak Varma stars in India win", "summary": "Tilak Varma scored a crucial fifty to help India defeat South Africa.", "full_article_text": "Tilak Varma played a crucial role in India's victory against South Africa in the latest match."}
        ]
        
        # Mocking the LLM call to return mock scripts
        with patch("script_generator._run_ollama_model") as mock_ollama:
            mock_ollama.side_effect = [
                ("Suryakumar Yadav unfollowed the MI management on Instagram. This has sparked a massive row among cricket fans. The controversy continues to build.", "", 0),
                ("Shashank posted a tweet in support of Shreyas Iyer. The team dispute remains unresolved. Fans are divided on the issue.", "", 0),
                ("Tilak Varma scored a crucial fifty against South Africa. India secured a dramatic victory in the match. The series is now level.", "", 0)
            ]
            script = generate_compilation_script(articles)
            
        self.assertIsNotNone(script)
        # Verify transition markers
        self.assertIn("[STORY 1:", script)
        self.assertIn("[STORY 2:", script)
        self.assertIn("[STORY 3:", script)
        
    def test_scene_planner_compilation_tagging(self):
        script = (
            "[STORY 1: UNFOLLOW 😱]\n"
            "Suryakumar Yadav unfollowed the MI management on Instagram.\n"
            "This has sparked a massive row among cricket fans.\n"
            "[STORY 2: THE GUIDANCE]\n"
            "Shashank posted a tweet in support of Shreyas Iyer.\n"
            "The team dispute remains unresolved."
        )
        
        scenes = plan_scenes(script)
        self.assertIsNotNone(scenes)
        
        # Verify we have transition scenes
        transitions = [s for s in scenes if s.get("type") == "transition"]
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[0]["text"], "STORY 1: UNFOLLOW 😱")
        self.assertEqual(transitions[1]["text"], "STORY 2: THE GUIDANCE")
        
        # Verify social mockup tagging
        social_scenes = [s for s in scenes if s.get("is_social_mockup")]
        self.assertTrue(len(social_scenes) > 0)
        
        # Verify split screen tagging
        split_scenes = [s for s in scenes if s.get("is_split_screen")]
        self.assertTrue(len(split_scenes) > 0)
        
    @patch("image_fetcher.fetch_image")
    def test_build_split_screen_collage(self, mock_fetch_image):
        # Create temp source images
        from PIL import Image
        temp_dir = Path(IMAGE_DIR)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        img1_path = temp_dir / "temp_ent1.jpg"
        img2_path = temp_dir / "temp_ent2.jpg"
        
        Image.new("RGB", (600, 800), (255, 0, 0)).save(img1_path)
        Image.new("RGB", (800, 600), (0, 0, 255)).save(img2_path)
        
        mock_fetch_image.side_effect = [str(img1_path), str(img2_path)]
        
        scene = {
            "text": "Suryakumar Yadav clashed with MI management.",
            "type": "sports",
            "is_split_screen": True,
            "split_entities": ["Suryakumar Yadav", "MI management"]
        }
        
        collage_path = build_split_screen_collage(scene, 1)
        self.assertIsNotNone(collage_path)
        self.assertTrue(os.path.exists(collage_path))
        
        # Verify dimensions of output collage (1080x1920)
        with Image.open(collage_path) as result_img:
            self.assertEqual(result_img.size, (1080, 1920))
            
        # Clean up temp files
        if img1_path.exists(): img1_path.unlink()
        if img2_path.exists(): img2_path.unlink()
        if Path(collage_path).exists(): Path(collage_path).unlink()

if __name__ == "__main__":
    unittest.main()
