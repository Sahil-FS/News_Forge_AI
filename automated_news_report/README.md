# AI News-to-Video Generator

Automatically converts the latest BBC news into a short, vertical (1080×1920)
video suitable for TikTok / Instagram Reels / YouTube Shorts — using only free,
local tools.

```text
Multiple RSS Feeds (BBC, Sky, DW, etc.)
       ↓
  feedparser & bs4 → Headline Scoring & Selection
       ↓
   Ollama (Llama3) → News-style script generation & formatting
       ↓
  scene planner   → Scenes + NER context + Map Geocoding
       ↓
  DuckDuckGo/Pexels/Wiki → Primary & Alt image per scene (w/ clipart filter)
  Kokoro TTS      → One WAV narration per scene (fallback to Piper)
       ↓
   MoviePy        → 1080×1920 MP4 (Visual cuts, captions, dynamic outro)
```

---

## Project Structure

```
automated_news_report/
├── main.py                     # E2E pipeline orchestrator
├── config.py                   # Central settings, voice/branding configs
├── news_fetcher.py             # Feedparser article acquisition & scraper
├── script_generator.py         # Ollama script engine & context detection
├── long_form_script_generator.py # Deep-dive narrative structured script writer
├── scene_planner.py            # Sentence chunking & spaCy NER analysis
├── image_fetcher.py            # Editorial scraping, Pexels, PIL card drawer
├── voice_generator.py          # Neural Kokoro TTS engine & audio cleanup
├── video_builder.py            # Renders short-form vertical (9:16) MP4
├── long_form_video_builder.py  # Renders long-form landscape (16:9) MP4
├── ui_server.py                # Local web control dashboard
├── db_manager.py               # SQLite tracking manager
├── youtube_uploader.py         # Automated OAuth YouTube upload pipeline
├── piper/                      # Fallback TTS runtime files & voices
├── assets/                     # Brand logos, fallback placeholders
├── output/                     # Auto-created directory for WAVs & final MP4s
└── README.md
```

---

## Installation

### Step 1 — Python dependencies

Install all required Python packages using the provided requirements.txt:

```bash
pip install -r requirements.txt
```

This will install:
- `ddgs` (DuckDuckGo search for image fetching)
- `feedparser` & `beautifulsoup4` (for RSS parsing and web scraping)
- `spacy` (for NLP and Named Entity Recognition)
- `numpy` & `Pillow` (for data array handling and image processing)
- `moviepy` (for video rendering)
- `geopy` (for map stinger generation)
- `kokoro`, `soundfile`, `torch` (for high-quality neural TTS generation)

> **MoviePy ≥ 1.0.3** is required. If `pip install moviepy` installs v2,
> pin it:  `pip install "moviepy==1.0.3"`

### Step 2 — spaCy language model

```bash
python -m spacy download en_core_web_sm
```

### Step 3 — Ollama (for AI script generation)

Ollama is used to generate news scripts using local AI models.

1. Download and install Ollama from https://ollama.com/
2. Pull the required model:
   ```bash
   ollama pull llama3
   ```
3. Ensure Ollama is running in the background.

### Step 4 — Kokoro TTS & espeak-ng (Primary Voice Engine)

Kokoro is a high-quality, lightweight neural TTS engine running locally.

1. Install system prerequisites (Windows):
   ```powershell
   winget install espeak-ng
   ```
2. The python packages (`kokoro` and `soundfile`) are included in `requirements.txt`.
3. The pipeline will automatically download the required `hexgrad/Kokoro-82M` voice model on first run.

### Step 5 — Piper TTS (Offline Fallback Engine)

Piper is used as a fast, offline fallback if Kokoro is unavailable.

#### a) Download the Piper binary

Go to https://github.com/rhasspy/piper/releases and download the archive for
your platform, e.g.:

| Platform | File |
|---|---|
| Linux x86-64 | `piper_linux_x86_64.tar.gz` |
| macOS arm64  | `piper_macos_aarch64.tar.gz` |
| Windows      | `piper_windows_amd64.zip` |

Extract into `project/piper/`:

```bash
# Linux example
mkdir -p project/piper
tar -xzf piper_linux_x86_64.tar.gz -C project/piper --strip-components=1
```

#### b) Download a voice model

```bash
cd project/piper

# The ONNX model
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx

# The required JSON config
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

#### c) Make the binary executable (Linux / macOS)

```bash
chmod +x project/piper/piper
```

#### d) Quick test

```bash
echo "Hello world" | ./project/piper/piper \
  --model ./project/piper/en_US-lessac-medium.onnx \
  --output_file /tmp/test.wav
```

> **Tip — Piper not available?**  
> The pipeline still runs without Piper; scenes that have no audio will use a
> fixed 5-second duration instead.  Just install the binary later and re-run.

### Step 4 — ffmpeg (required by MoviePy)

```bash
# Ubuntu / Debian
sudo apt-get install ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# Windows — download from https://ffmpeg.org/download.html
# and add the bin/ folder to your PATH
```

---

## Configuration

All settings live in **`config.py`**:

| Variable | Default | Description |
|---|---|---|
| `RSS_FEED_URL` | BBC News | Any RSS feed URL |
| `NUM_SENTENCES` | `5` | Number of scenes |
| `PIPER_EXECUTABLE` | `./piper/piper` | Path to Piper binary |
| `PIPER_MODEL` | `./piper/en_US-lessac-medium.onnx` | Path to voice model |
| `SCENE_DURATION` | `5` | Fallback scene length (seconds) |
| `OUTPUT_VIDEO` | `output/news_video.mp4` | Final video path |

Override Piper paths with environment variables without editing the file:

```bash
export PIPER_EXECUTABLE=/usr/local/bin/piper
export PIPER_MODEL=/opt/voices/en_US-lessac-medium.onnx
```

---

## Usage
## Usage

```bash
# Run the pipeline end-to-end (defaults to vertical format)
python main.py

# Run with format, channel, category and test-mode arguments
python main.py --format both --channel newscup --category world --test-mode

# Available format options: vertical, landscape, both
# Available category options: world, politics, business, tech, science, entertainment, sports
# Available channel options: newscup, newscup_india
```

The final video files will be written to `output/news_video.mp4` (vertical) and `output/news_video_long.mp4` (landscape).

### Run the Web Dashboard

A local web application is available to monitor the pipeline and view output history:

```bash
python ui_server.py
```
Then navigate to `http://127.0.0.1:5000` in your web browser.

### Run individual modules

```bash
# Test the news fetcher
python news_fetcher.py

# Test the summariser
python script_generator.py

# Test image fetching
python image_fetcher.py

# Test Kokoro/Piper TTS voice generation
python voice_generator.py

# Smoke-test the video builder
python video_builder.py
```

---

### 1 · News Fetcher (`feedparser` & `bs4`)
Parses multiple regional and international RSS feeds (BBC, Sky News, Deutsche Welle, Al Jazeera, NDTV, Times of India, and ESPN) and scores headlines. Selects the most relevant, high-impact article, executes direct HTTP scrapers with auto-retries, and extracts clean, fact-dense content.

### 2 · Script Generator (`Ollama Llama3` + `spaCy`)
Uses a local LLM (Llama3 via Ollama) to write professional news narrations using a **Dynamic Context-Aware Prompt Architecture**.
- **Short-form & Long-form Script Engines (`script_generator.py` & `long_form_script_generator.py`):** Generates 200–300 words structured deep-dive narratives with 5-layer sequencing (Hook, Context, Core Evidence/Citations, Secondary Analysis, and Impact/Outro).
- **Evidence Tags:** Injects direct inline citations such as `[QUOTE: "text"]`, `[TWEET: "user: text"]`, or `[DOCUMENT: "fact"]` into the script flow.
- A spaCy-based extractive generator serves as a 100% factual fallback.

### 3 · Scene Planner (`spaCy`)
Splits the generated script into caption-friendly visual scenes. Matches quote, tweet, and document bracketed tags to map scenes to specialized types: `quote_card`, `tweet_overlay`, or `evidence_graphic`. Uses NLP Named Entity Recognition (NER) to derive country contexts for geographic map stingers and generates scene-specific search queries.

### 4 · Image Fetcher (DuckDuckGo / Pexels / Wiki / AI)
Fetches and generates high-impact visual backgrounds:
- **Priority 0 Scraper:** Parses metadata tags (`og:image`, `twitter:image`) directly from the article URL.
- **Evidence Graphic Generator:** Programmatically generates styled PIL-based translucent overlay cards with cyberpunk neon borders, wrapped text, and custom metadata, bypassing web/stock search for quote, tweet, and document scenes.
- **Layered Fallbacks:** Searches Wikipedia person photo (P1), Pexels news-realistic photography (P1.5), Wikipedia topic fallback (P2), Unsplash (P3), and Pollinations.ai contextual AI images (P5.5 fallback).
- **Anti-Stock Drift:** Filters out generic illustrations, drawings, and renders (e.g. rejecting URLs or queries with `'3D'`, `'Render'`, `'Illustration'`), falling back to photojournalistic AI prompts.

### 5 · Voice Generator (Kokoro TTS / Piper)
Generates stunning, human-quality voice overs using **Kokoro TTS** (`hexgrad/Kokoro-82M` neural model) with voice mappings tailored to the emotional context.
- **Pacing Acceleration:** Forces English news speech speed to **1.22x** to ensure high audience retention, while slowing to **0.90x** for heavy, serious verdict segments.
- **Audio Prep:** Integrates automatic loudnorm normalization to EBU R128 (-23 LUFS) and decibel-level silence trimming (80ms natural decay tail). Piper TTS serves as a local ONNX fallback.

### 6 · Video Builders (`MoviePy` + `Pillow`)
Composes MP4s in vertical (`video_builder.py`, 1080×1920) and landscape (`long_form_video_builder.py`, 1920×1080) layouts.
- **Dynamic Audio Ducking:** Vectorized MoviePy filter operations automatically duck background music volume from normal levels (`0.12`) to a whisper level (`0.025`) during evidence, quote, and tweet scenes to elevate narrative impact.
- **Visual Filters:** Applies Gaussian blurs, Ken Burns pan/zooms, location map stingers, animated overlays, crawling lower-thirds, and dynamic outre/CTA cards.
- **Compression Guard:** Automatically compresses or drops middle scenes if duration parameters drop below safety thresholds, ensuring zero caption overlap.

---

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `OSError: en_core_web_sm not found` | `python -m spacy download en_core_web_sm` |
| `Piper executable not found` | Set `PIPER_EXECUTABLE` or edit `config.py` |
| `ffmpeg not found` | Install ffmpeg and ensure it is on `PATH` |
| Black video, no images | Wikimedia API may rate-limit; the blank fallback is used automatically |
| `moviepy` import error | Pin version: `pip install "moviepy==1.0.3"` |

---

## Recent Updates
- Updated `script_generator.py` to use `llama3` as the Ollama model candidate instead of `qwen3.5:cloud`.
- Confirmed the Ollama executable uses the Windows path `C:\Users\Darshan\AppData\Local\Programs\Ollama\ollama.exe`.
- These changes were added to reflect the current local environment and model setup.

---

## License

MIT — use freely, no attribution required.

---

## Additional Project Context

This repository builds a full local AI news-to-video generator that converts the latest BBC News RSS story into a vertical social video.

### What we are making

- A complete pipeline that turns news content into a short, vertical video suitable for TikTok / Instagram Reels / YouTube Shorts.
- The pipeline fetches the latest article, generates a concise script, plans story scenes, fetches supporting visuals, renders local speech, and composes the final MP4.
- The goal is to keep the process local where possible and use free / accessible tools with offline models.

### Core files and their relationships

- `main.py` — orchestrates the pipeline end to end and resets `output/` for a fresh run.
- `config.py` — central settings for directories, feed URL, Piper model path, video resolution, and API endpoints.
- `news_fetcher.py` — uses `feedparser` to parse BBC RSS and return the latest article title, link, and summary.
- `script_generator.py` — uses spaCy NLP plus custom heuristics to clean text, score content, detect context, and build a short news narration.
- `scene_planner.py` — splits the generated script into scenes, extracts named entities and keywords, and creates metadata used by image/audio generation.
- `image_fetcher.py` — builds semantic image queries, fetches images from Pexels (primary), falls back to Wikimedia/Wikipedia when needed, and can generate a location map stinger.
- `voice_generator.py` — runs the Piper TTS binary with a local ONNX model to produce scene WAV files.
- `video_builder.py` — uses MoviePy + Pillow to render each vertical scene with images, overlays, text cards, branding, and audio.
- `video_review.py` — helper script that runs `main.py` inside `.venv`, validates the video output, and reports quality metrics.
- `PROJECT_DOCUMENTATION.md` and `VIDEO_QUALITY_ANALYSIS_REPORT.md` — supporting docs for design and review, outside the runtime pipeline.

### Technology used

- Python 3.12+
- feedparser & requests with retries for robust RSS parsing and article scraping
- spaCy (`en_core_web_sm`) for advanced NLP, semantic categorization, sentence chunking, and named entity recognition (NER)
- MoviePy for high-fidelity vertical video composition and rendering
- Pillow for beautiful rounded text pills, gradient overlays, and dynamic brand elements
- NumPy for sound array concatenation, timing calculations, and visual buffers
- Kokoro TTS with a local PyTorch neural engine for high-quality professional voice narration
- Piper TTS with a local ONNX runtime for an offline fallback voice engine
- geopy, staticmap, and CartoDB for generating location map stingers
- ffmpeg for EBU R128 (-23 LUFS) audio normalization, silence trimming, and H.264/AAC encoding

### Data sources and AI models

- **News feeds:** Multiple pools (BBC, Sky, DW, Reuters, NDTV, Times of India, ESPN, NASA RSS) categorized dynamically
- **Image resources:** Pexels API, Wikipedia Commons, Unsplash, and Pollinations.ai (AI images)
- **Local LLM Model:** Ollama `llama3` for news-narrative script writing and dynamic CTA outros
- **Primary TTS Model:** Kokoro-82M neural model (`hexgrad/Kokoro-82M` repo)
- **Fallback TTS Model:** Piper ONNX medium voice (`en_US-lessac-medium.onnx`)
- **NLP Model:** spaCy `en_core_web_sm` (v3.x)

### What changed in this repo

- Added multi-feed headline scoring replacing static single-feed fetching in `news_fetcher.py`.
- Replaced basic extractive summarization with direct Ollama (Llama3) script generation in `script_generator.py`.
- Implemented robust regex stripping of LLM meta-commentary (e.g. "Here is the script:") and removed orphan caption fragments ("civilians", "buildings").
- Added semantic and type-aware image query generation in `image_fetcher.py`, utilizing DuckDuckGo, Unsplash, Pexels, and Wikipedia.
- Implemented strict anti-clipart and toy filter rejection logic to ensure photojournalistic realism.
- Added visual cuts (B-roll) for longer scenes and dynamic Ken Burns zoom effects.
- Added location map stinger generation for stories with geographic entities.
- Upgraded primary TTS to Kokoro (`hexgrad/Kokoro-82M`) with a custom fallback to Piper TTS. Fixed numpy 2.x audio concatenation bugs.
- Implemented dynamic outro duration calculation bound to the exact length of the outro narration WAV.
- Added strict `.venv` checks in core modules to ensure the right environment is used.
- Added `video_review.py` to validate end-to-end pipeline execution and video duration.

### Output structure

- `output/audio/` — generated WAV files for each scene
- `output/images/` — downloaded scene images and map stinger
- `output/news_video.mp4` — final vertical news video
