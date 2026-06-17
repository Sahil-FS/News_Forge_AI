import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("Importing scene_planner...")
import scene_planner
print("Imported scene_planner.")
print("Importing image_fetcher...")
import image_fetcher
print("Imported image_fetcher.")

import long_form_script_generator
print("Imported long_form_script_generator.")
import long_form_video_builder
print("Imported long_form_video_builder.")
import thumbnail_generator
print("Imported thumbnail_generator.")
print("All imports tested successfully!")
