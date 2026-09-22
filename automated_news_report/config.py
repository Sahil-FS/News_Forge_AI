# config.py -- Central configuration for AI News-to-Video Generator

import os

# Load .env file if present (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed -- use OS environment variables directly

DEBUG_MODE = os.environ.get("DEBUG_MODE", "true").lower() == "true"

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
AUDIO_DIR  = os.path.join(OUTPUT_DIR, "audio")
IMAGE_DIR  = os.path.join(OUTPUT_DIR, "images")

for d in (OUTPUT_DIR, AUDIO_DIR, IMAGE_DIR):
    os.makedirs(d, exist_ok=True)

# ── News source ───────────────────────────────────────────────────────────────
RSS_FEED_URL = "https://feeds.bbci.co.uk/news/rss.xml"

# ── Script generation ─────────────────────────────────────────────────────────
NUM_SENTENCES = 5          # scenes in the final video

# ── Piper TTS ─────────────────────────────────────────────────────────────────
PIPER_EXECUTABLE = os.environ.get("PIPER_EXECUTABLE", "piper/piper.exe")
PIPER_MODEL      = os.environ.get(
    "PIPER_MODEL",
    "./piper/en_US-lessac-medium.onnx"
)

# ── Video (Short-Form defaults) ───────────────────────────────────────────────
VIDEO_WIDTH   = 1080
VIDEO_HEIGHT  = 1920
VIDEO_FPS     = 24
SCENE_DURATION = 5          # seconds per scene (overridden by audio length)
OUTPUT_VIDEO   = os.path.join(OUTPUT_DIR, "news_video.mp4")
LONG_VIDEO_OUTPUT = os.path.join(OUTPUT_DIR, "news_video_long.mp4")

def _ensure_placeholder():
    """Create default placeholder and logo images if they don't exist."""
    from PIL import Image as _PI, ImageDraw as _PID
    import os

    _assets_dir = os.path.join(BASE_DIR, "assets")
    os.makedirs(_assets_dir, exist_ok=True)

    # 1. Placeholder image
    _path = os.path.join(_assets_dir, "placeholder.jpg")
    if not os.path.isfile(_path):
        _img = _PI.new("RGB", (1080, 1920), (13, 17, 35))
        _draw = _PID.Draw(_img)
        try:
            from PIL import ImageFont
            _font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 80)
        except Exception:
            from PIL import ImageFont
            _font = ImageFont.load_default()
        _draw.text((540, 960), "AI NEWS", font=_font, fill=(220, 30, 30), anchor="mm")
        _img.save(_path, "JPEG", quality=85)
        print(f"[ASSETS] Created placeholder image: {_path}")

    # 2. Logo image
    _logo_path = os.path.join(_assets_dir, "logo.png")
    if not os.path.isfile(_logo_path):
        _img = _PI.new("RGBA", (200, 200), (13, 17, 35, 255))
        _draw = _PID.Draw(_img)
        _draw.ellipse([20, 20, 180, 180], fill=(220, 30, 30, 255))
        try:
            from PIL import ImageFont
            _font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 100)
        except Exception:
            from PIL import ImageFont
            _font = ImageFont.load_default()
        _draw.text((100, 100), "G", font=_font, fill=(255, 255, 255, 255), anchor="mm")
        _img.save(_logo_path, "PNG")
        print(f"[ASSETS] Created logo image: {_logo_path}")

_ensure_placeholder()

# ── Wikimedia Commons ─────────────────────────────────────────────────────────
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "NewsVideoBot/1.0 (educational project)"}

# ── Scene Planning ────────────────────────────────────────────────────────────
SCENE_MIN_WORDS       = 6     # minimum words per scene caption (matches MIN_WORDS in scene_planner)
SCENE_MAX_WORDS       = 12    # capped at 12 for mobile caption display readability
SCENE_TARGET_MIN      = 8     # minimum number of scenes
SCENE_TARGET_MAX      = 8     # target 8 scenes × ~5s = 40s content + ~5s outro = ~45s total

# ── Video Timeline ────────────────────────────────────────────────────────────
MAX_SCENE_TOTAL_SECS  = 85.0  # maximum total content duration before compression
MIN_SCENE_TOTAL_SECS  = 35.0  # minimum total duration before expansion
MAX_SCENE_DURATION    = 9.0   # per-scene audio cap
MIN_SCENE_DURATION    = 2.0   # per-scene audio floor
VISUAL_CUT_THRESHOLD  = 2.8   # scenes longer than this get a B-roll mid-cut
CAPTION_LEAD_SECS     = 0.10  # caption appears this many seconds before spoken word

# ── Audio Post-Processing ─────────────────────────────────────────────────────
PAUSE_AFTER_SENTENCE  = 0.20  # silence gap between Piper TTS sentence fragments (reduced for faster pacing)
AUDIO_TAIL_BUFFER     = 0.30  # silence buffer added to final scene
SILENCE_KEEP_TAIL     = 0.08  # natural decay tail preserved after trimming
MAP_STINGER_DURATION  = 3.5    # minimum display time
MAP_STINGER_MAX       = 4.0    # reduced to 4.0s for introductory pacing
MAP_STINGER_MIN       = 3.5    # same as DURATION

# ── Script Generation ─────────────────────────────────────────────────────────
OLLAMA_URL            = "http://localhost:11434/api/generate"
OLLAMA_MODEL          = "llama3"
OOV_THRESHOLD         = 20    # raised from 18 — prevents false relevance rejections
SCRIPT_MIN_WORDS      = 80    # minimum acceptable script word count

# ── Dual-Format (Long-Form) Constants ─────────────────────────────────────────
LONG_VIDEO_WIDTH       = 1920
LONG_VIDEO_HEIGHT      = 1080
LONG_SCENE_TARGET_MIN  = 12
LONG_SCENE_TARGET_MAX  = 20
LONG_MAX_SCENE_TOTAL_SECS = 450.0
LONG_MIN_SCENE_TOTAL_SECS = 180.0

# ── Channel Branding & Identity Settings ──────────────────────────────────────
BRAND_NAME             = "The News Cup"
CHANNEL_NAME           = "TheNewsCup"
BRAND_FONT_PATH        = "C:/Windows/Fonts/arialbd.ttf"
BRAND_COLOR_PRIMARY    = (220, 30, 30)      # Red (matches logo)
BRAND_COLOR_SECONDARY  = (18, 18, 18)       # Near-black
BRAND_COLOR_ACCENT     = (220, 30, 30)      # Red accent
BRAND_COLOR_WHITE      = (255, 255, 255)    # White
BRAND_LOGO_PATH        = os.path.join(BASE_DIR, "assets", "newscup_logo.png")
CHANNEL_LOGO_PATH      = BRAND_LOGO_PATH

def _ensure_logo():
    """Ensure that the branding logo is created and available."""
    if not os.path.exists(BRAND_LOGO_PATH):
        try:
            from PIL import Image as _PI, ImageDraw as _PID
            _assets_dir = os.path.join(BASE_DIR, "assets")
            os.makedirs(_assets_dir, exist_ok=True)
            _img = _PI.new("RGBA", (200, 200), (13, 17, 35, 255))
            _draw = _PID.Draw(_img)
            _draw.ellipse([20, 20, 180, 180], fill=(220, 30, 30, 255))
            try:
                from PIL import ImageFont
                _font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 100)
            except Exception:
                from PIL import ImageFont
                _font = ImageFont.load_default()
            _draw.text((100, 100), "G", font=_font, fill=(255, 255, 255, 255), anchor="mm")
            _img.save(BRAND_LOGO_PATH, "PNG")
            print(f"[config] Fallback logo created at {BRAND_LOGO_PATH}")
        except Exception as e:
            print(f"[config] Failed to generate fallback logo: {e}")

_ensure_logo()

# ── Image Fetcher Tuning ─────────────────────────────────────────────────────
IMAGE_MIN_FILE_SIZE_KB     = 2        # minimum valid image file size in KB
IMAGE_MIN_DIMENSION_PX     = 100      # minimum image width or height in pixels
IMAGE_BRIGHTNESS_MAX       = 210      # reject images with avg brightness above this
IMAGE_BRIGHTNESS_MIN       = 15       # reject images with avg brightness below this
IMAGE_SOLID_COLOR_THRESHOLD = 10      # max RGB channel variance for solid-color rejection
POLLINATIONS_FAIL_LIMIT    = 2        # disable Pollinations after this many failures
POLLINATIONS_TIMEOUT_1     = 15       # first attempt timeout in seconds
POLLINATIONS_TIMEOUT_2     = 25       # second attempt timeout in seconds
ARTICLE_MAX_IMAGES         = 8        # max images to scrape from article page
OG_IMAGE_MIN_KB            = 2        # minimum og:image file size to accept
PEXELS_RESULTS_PER_PAGE    = 5        # results per Pexels API request
DDG_MAX_RESULTS            = 8        # max DuckDuckGo image results per query

# ── Video Builder Tuning ─────────────────────────────────────────────────────
KEN_BURNS_ZOOM_FACTOR      = 0.15     # Ken Burns zoom amount (1.0 → 1.0+factor)
KEN_BURNS_LANDSCAPE_FACTOR = 0.08     # Ken Burns zoom for landscape format
OUTRO_MIN_DURATION         = 1.0      # snappy outro floor (seconds) to prevent retention drops
OUTRO_MAX_DURATION         = 1.5      # maximum outro scene duration in seconds (<=1.5s max)
CAPTION_MAX_VISIBLE_WORDS  = 10       # max words shown in progressive caption
CAPTION_LEAD_SECS          = 0.10     # caption appears this many seconds early
AUDIO_TAIL_BUFFER_SECS     = 0.30     # buffer added to scene duration after audio
SCENE_COMPRESSION_MIN_SCALE = 0.95   # minimum compression before dropping scenes
SCENE_WORD_MIN_WEIGHT      = 0.8      # timing weight for short words (<=3 chars)
SCENE_WORD_MAX_WEIGHT      = 1.2      # timing weight for long words (>6 chars)
WORD_DISPLAY_MIN_SECS      = 0.10     # minimum per-word display time
WORD_DISPLAY_MAX_SECS      = 0.40     # maximum per-word display time

# ── Script Generator Tuning ──────────────────────────────────────────────────
OLLAMA_NUM_PREDICT         = 600      # max tokens for Ollama generation
OLLAMA_TEMPERATURE         = 0.58     # generation temperature
OLLAMA_TOP_P               = 0.85     # top-p sampling
OLLAMA_REPEAT_PENALTY      = 1.15     # repetition penalty
SCRIPT_MIN_INPUT_CHARS     = 300      # minimum input chars before using Ollama
SCRIPT_OOV_THRESHOLD       = 32       # max out-of-vocabulary terms before rejection
SCRIPT_MIN_VERBLESS_SENTENCES = 2     # reject if more than this many lack verbs

# ── Voice Generator Tuning ──────────────────────────────────────────────────
KOKORO_SAMPLE_RATE         = 24000    # Kokoro TTS output sample rate
KOKORO_LEAD_SILENCE_MS     = 120      # leading silence prepended to Kokoro output
SILENCE_DB_THRESHOLD       = -45.0    # dB level for silence detection
SILENCE_KEEP_TAIL_SECS     = 0.08     # natural decay tail preserved after trimming
SILENCE_MIN_TRIM_SECS      = 0.15     # minimum silence to remove before trimming
SILENCE_MIN_AUDIO_SECS     = 1.20     # don't trim audio shorter than this
PIPER_LENGTH_SCALE_EN      = 1.15     # Piper TTS length scale for English
PIPER_LENGTH_SCALE_HI      = 1.08     # Piper TTS length scale for Hindi

# ── Map Generator Tuning ────────────────────────────────────────────────────
MAP_TILE_ZOOM_CITY         = 10       # zoom level for city-level maps
MAP_TILE_ZOOM_COUNTRY      = 5        # zoom level for country-level maps
MAP_TILE_GRID_SIZE         = 3        # NxN grid of tiles to fetch
MAP_TILE_SIZE_PX           = 256      # standard tile size in pixels
MAP_TILE_FETCH_RETRIES     = 3        # retries per tile fetch
MAP_PIN_OUTER_RADIUS       = 22       # pin outer circle radius in pixels
MAP_PIN_INNER_RADIUS       = 18       # pin inner circle radius in pixels
MAP_PIN_DOT_RADIUS         = 6        # pin center dot radius in pixels
MAP_VIGNETTE_STRENGTH      = 0.80     # vignette darkness (0.0-1.0)
MAP_TILE_BACKOFF_SECS      = 0.5      # base backoff between tile retries


# ── YouTube Auto-Upload ───────────────────────────────────────────────────────
# Set AUTO_UPLOAD = True after you have run the one-time OAuth setup:
#   python youtube_uploader.py --auth newscup
#   python youtube_uploader.py --auth newscup_india
AUTO_UPLOAD                = os.environ.get("AUTO_UPLOAD", "true").lower() == "true"

# Privacy for auto-uploaded videos:
#   "private"   → only you can see it (safe default — review before publishing)
#   "unlisted"  → anyone with the link can see it
#   "public"    → immediately public
AUTO_UPLOAD_PRIVACY        = os.environ.get("AUTO_UPLOAD_PRIVACY", "private")

# YouTube category ID (25 = News & Politics)
AUTO_UPLOAD_CATEGORY_ID    = "25"

# YouTube Upload Spacing / Schedule Configuration (in minutes)
UPLOAD_SPACING_MINUTES     = int(os.environ.get("UPLOAD_SPACING_MINUTES", 100))
UPLOAD_JITTER_MIN          = int(os.environ.get("UPLOAD_JITTER_MIN", 15))
UPLOAD_JITTER_MAX          = int(os.environ.get("UPLOAD_JITTER_MAX", 45))
BATCH_COUNT                = int(os.environ.get("BATCH_COUNT", 6))

# Next-day boundary and safety spacing for batch schedules
BATCH_BOUNDARY_HOUR        = int(os.environ.get("BATCH_BOUNDARY_HOUR", 5))
BATCH_MIN_SPACING_MINUTES   = int(os.environ.get("BATCH_MIN_SPACING_MINUTES", 30))

# Install check reminder
_YT_DEPS = ["google-api-python-client", "google-auth-oauthlib", "google-auth-httplib2"]
