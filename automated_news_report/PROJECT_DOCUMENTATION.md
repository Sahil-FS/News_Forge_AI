# 🎬 AI News-to-Video Generator — Complete Technical Documentation

**Last Updated:** April 28, 2026  
**Status:** Fully Functional | Phase 4 Development  
**Author:** Sahil-FS  
**Repository:** https://github.com/Sahil-FS/automated_news_report

---

## 📋 TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [Full Folder Structure](#2-full-folder-structure)
3. [File-by-File Breakdown](#3-file-by-file-breakdown)
4. [End-to-End Data Flow](#4-end-to-end-data-flow)
5. [Technologies & Dependencies](#5-technologies--dependencies)
6. [Internal Module Connections](#6-internal-module-connections)
7. [Execution Process (Step-by-Step)](#7-execution-process-step-by-step)
8. [Output System](#8-output-system)
9. [Current Limitations & Issues](#9-current-limitations--issues)
10. [Improvement Suggestions](#10-improvement-suggestions)
11. [Important GitHub Note](#11-important-github-note)

---

# 1. PROJECT OVERVIEW

## What It Does

The **AI News-to-Video Generator** is a fully automated pipeline that converts real-world news articles (from BBC RSS feeds) into **short-form vertical videos (9:16 aspect ratio)** suitable for platforms like:
- Instagram Reels
- TikTok
- YouTube Shorts

## Final Output

**Single MP4 file:** `output/news_video.mp4`
- **Resolution:** 1080×1920 (vertical)
- **Format:** MP4
- **Duration:** 45–55 seconds (adjustable)
- **Content:** 6–12 scenes with synchronized audio, captions, and images
- **Quality:** Ready-to-publish on social media

## Core Goal

Create **zero-manual-editing news videos** that:
- Are **fully automated** from news fetch to video delivery
- Maintain **news-style credibility** (professional pacing, captions, branding)
- Use **AI-generated scripts** that are contextually accurate
- Include **realistic voice narration** (Piper TTS)
- Display **relevant images** (Pexels API + Wikipedia fallback)
- Run **completely offline** (except for image/news fetching)

---

# 2. FULL FOLDER STRUCTURE

```
automated_news_report/
│
├── 📄 main.py                          # Master orchestrator for both formats
├── 📄 config.py                        # Centralized settings & branding parameters
├── 📄 news_fetcher.py                  # RSS parser & premium editorial scraper
├── 📄 script_generator.py              # Ollama script engine (short-form)
├── 📄 long_form_script_generator.py    # Structured script engine (long-form)
├── 📄 scene_planner.py                 # Sentence chunker & spaCy NER context extractor
├── 📄 image_fetcher.py                 # Priority 0 scraping, Pexels API, and PIL card generator
├── 📄 voice_generator.py               # Kokoro TTS (Primary) & Piper (Fallback) generator
├── 📄 video_builder.py                 # Renders short-form vertical (9:16) MP4
├── 📄 long_form_video_builder.py       # Renders long-form landscape (16:9) MP4
├── 📄 ui_server.py                     # Web console dashboard server (Flask)
├── 📄 db_manager.py                    # SQLite database coordinator
├── 📄 db.sqlite                        # Tracking DB for processed articles and stats
├── 📄 channel_profiles.py              # Voice and identity profiles per channel
├── 📄 chapter_generator.py             # YouTube chapter segmentation generator
├── 📄 thumbnail_generator.py           # Programmatic overlay image builder (PIL)
├── 📄 analytics_puller.py              # YouTube analytics retrieval client
├── 📄 sync_analytics.py                # Pulls and syncs channel statistics to DB
├── 📄 youtube_uploader.py              # YouTube Data API upload pipeline
├── 📄 video_review.py                  # Pipeline execution validator and reviewer
├── 📄 README.md                        # Primary setup & instruction manual
├── 📄 PROJECT_DOCUMENTATION.md         # Detailed system design specs (This file)
├── 📄 VIDEO_QUALITY_ANALYSIS_REPORT.md # Auto-generated execution report
│
├── 🗂️ piper/                          # Fallback TTS Engine files
│   ├── piper.exe                       # Piper compiler binary
│   ├── en_US-lessac-medium.onnx        # Medium voice model
│   └── en_US-lessac-medium.onnx.json   # Voice configuration file
│
├── 🗂️ templates/                      # Web UI template views (HTML)
├── 🗂️ assets/                         # Branding images, logo resources, and placeholders
│
├── 🗂️ output/                         # Auto-generated assets directory
│   ├── audio/                          # Scene audio files (WAVs)
│   ├── images/                         # Scraped images and PIL neon cards
│   ├── news_video.mp4                  # Final rendered vertical video (9:16)
│   └── news_video_long.mp4             # Final rendered landscape video (16:9)
│
├── 🗂️ .venv/                          # Local Python virtual environment
└── 📝 execution.log                    # System activity logs
```

---

# 3. FILE-BY-FILE BREAKDOWN

## 3.1 **main.py** — Pipeline Orchestrator

### Purpose
Central orchestrator that runs the entire pipeline sequentially. Manages:
- Output directory initialization
- Pipeline step execution
- Error handling and validation

### Key Functions

| Function | Purpose | Input | Output |
|----------|---------|-------|--------|
| `main()` | Runs the 5-step pipeline | None | Final video path or error |
| `preflight()` | Validates environment setup | None | Boolean (success/fail) |

### Execution Flow

```python
1. Clean output directory (FORCE fresh run)
2. Fetch latest BBC news article
3. Generate news script from article
4. Plan scenes (split script into 6-12 scenes)
5. For each scene:
   - Fetch relevant image (Pexels → Wikipedia)
   - Generate audio narration (Piper TTS)
6. Validate all scene assets
7. Build final video (MoviePy)
8. Return video path or error
```

### Key Features

- **Unique RUN ID** — UUID4 prefix for tracking runs
- **Clean output directory** — `shutil.rmtree()` removes cached assets
- **Pre-render validation** — Checks each scene has text, audio, image
- **Metadata injection** — Adds headline, news_source to every scene
- **Error handling** — Logs which scenes failed and why

### Sample Output

```
[RUN ID]: a1b2c3d4
[ENV] Python: C:\Users\sahil\Documents\AI_NEWs_GENERATOR\.venv\Scripts\python.exe

[1/5] Fetching latest news...
[NewsFetcher] Article: "Ukraine Hits Russian Supply Lines..."

[2/5] Generating script...
[ScriptGen] Script preview: "This is a breaking story about..."

[3/5] Planning scenes...
[ScenePlanner] 8 scenes planned

[4/5] Fetching images and generating audio...
[ImageFetcher] Scene 0: Found relevant image
[VoiceGen] Scene 0 audio generated

[5/5] Building video...
[SUCCESS] Video created: output/news_video.mp4
```

---

## 3.2 **config.py** — Central Configuration

### Purpose
Centralized configuration management. Defines:
- File paths
- API keys
- Model paths
- Video parameters

### Configuration Variables

```python
# ── Paths ────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
AUDIO_DIR  = os.path.join(OUTPUT_DIR, "audio")
IMAGE_DIR  = os.path.join(OUTPUT_DIR, "images")

# ── News Source ──────────────────────────────────────────────
RSS_FEED_URL = "https://feeds.bbci.co.uk/news/rss.xml"

# ── Script Generation ────────────────────────────────────────
NUM_SENTENCES = 5          # Target scenes (overridden by dynamic calculation)

# ── Piper TTS (Local, Offline) ──────────────────────────────
PIPER_EXECUTABLE = "piper/piper.exe"
PIPER_MODEL = "./piper/en_US-lessac-medium.onnx"

# ── Video Rendering ─────────────────────────────────────────
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS    = 24
SCENE_DURATION = 5         # Fallback (overridden by audio duration)
OUTPUT_VIDEO = os.path.join(OUTPUT_DIR, "news_video.mp4")

# ── Wikipedia API ────────────────────────────────────────────
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "NewsVideoBot/1.0 (educational)"}
```

### Key Features

- **Environment variable override** — `PIPER_EXECUTABLE`, `PIPER_MODEL` can be set in OS
- **Auto-directory creation** — `os.makedirs(..., exist_ok=True)` for all output folders
- **Centralized changes** — Modify one file, all modules use updated values

---

## 3.3 **news_fetcher.py** — RSS News Source

### Purpose
Fetch the latest BBC news article via RSS feed parsing.

### Key Functions

| Function | Input | Output |
|----------|-------|--------|
| `fetch_latest_article()` | RSS feed URL (default BBC) | `{title, link, summary}` dict |

### Implementation Details

**Parsing Flow:**
```python
1. Parse RSS feed using feedparser
2. Extract first entry (latest article)
3. Get: title, link, summary
4. Strip HTML tags from summary (naive regex)
5. Fallback: use title if summary is empty
6. Return dict with all three fields
```

**Error Handling:**
- Raises `RuntimeError` if feed is unreachable
- Raises `RuntimeError` if no entries in feed
- Handles parse errors gracefully

**Sample Output:**

```python
{
    "title": "Ukraine Hits Russian Supply Lines in Donetsk",
    "link": "https://bbc.com/news/world-...",
    "summary": "Ukrainian forces have attacked Russian military positions 
               in eastern Donetsk, damaging supply lines crucial to Moscow's 
               offensive operations, military sources say..."
}
```

### Dependencies

- `feedparser` — RSS parsing
- `re` — HTML tag stripping
- `config.RSS_FEED_URL` — BBC feed URL

---

## 3.4 **script_generator.py** — NLP & Ollama Script Generation

### Purpose
Convert a crawled news article into a high-impact, **professional news script** for short-form social videos that:
- Targets a 45–55 seconds narration length (~120–162 words at 2.5 wps)
- Features a highly engaging, context-matched attention hook
- Employs a **Dynamic Context-Aware Prompt Architecture** using local Ollama (`llama3`)
- Implements two layers of verification (Structure/Relevance Audit + Geopolitical Entity Fact-Checking)
- Gracefully falls back to a TF-IDF extractive spaCy processor if Ollama is rate-limited, times out, or fails verification.

### Key Functions

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `summarise()` | Full article text | Final clean script | Main orchestration entry point. Manages the 3-attempt Ollama retry loop and fallback pipelines. |
| `detect_context()` | spaCy doc | `tense` \| `serious` \| `politics` \| `positive` \| `informative` \| `neutral` | Categorizes emotional context using additive keyword/override weights to configure voice/speed and prompt styles. |
| `generate_script_with_ollama()` | Article text, target words, context | Raw generated script | Formulates a highly tailored context prompt and calls the local Ollama API. |
| `generate_dynamic_cta()` | Headline, context | Dict of CTA lines | Generates a 3-line headline-linked social engagement card using local Ollama, avoiding banned topics. |
| `_script_relevance_ok()` | Generated script, source, spaCy doc | Boolean | Audit: Rejects scripts with >12 out-of-article terms or zero matching named entities to stop LLM hallucinations. |
| `_fact_check_entities()` | Script, source text | Validated script | Sanitizer: Strips specific sentences containing hallucinated PERSON/ORG entities, preserving allowed global organizations. |
| `_spacy_fallback_script()` | Source text, spaCy doc, context | Extractive script | High-quality factual fallback selecting and re-ordering the best frequency-scored article sentences. |
| `validate_script()` | Script, target words | Boolean | Structural audit verifying hook length, capitalization, and checking for excessive generic filler phrases. |
| `clean_caption_text()` | Raw text | Cleaned text | Removes ANSI escape sequences, non-ASCII characters, and standardizes whitespaces. |

### Context Detection & Override System

**Emotional Contexts:** `tense` | `serious` | `politics` | `positive` | `informative` | `neutral`

**Classification Logic:**
- **Violence Override:** If active violence or conflict words are detected (e.g., `airstrike`, `ceasefire`, `hostage`, `shelling`, `clash`), the `tense` classification is locked in to ensure high-gravity reporting.
- **Tense Neutralisers:** Suppresses tension in favor of `politics` if ceremonial words (e.g., `state visit`, `tribute`, `memorial`, `trade deal`) are present *without* active violence.
- **Additive Scoring:** Categories compete on token matching. If `tense` and `politics` score closely, `tense` is given priority (war > diplomacy).

### Dynamic Context-Aware Prompt Architecture

Instead of feeding a single static prompt to the LLM, the system dynamically swaps out the **extraction rules** and **8-sentence structures** based on the detected emotional context:

#### 1. Serious / Tense (War, Conflicts, Disasters)
*   **Extraction focus:** Exact death/casualty numbers, specific locations, official quotes, government response, and ongoing risk warnings.
*   **8-Sentence Structure:**
    1.  **Hook:** Attention-grabbing shocking fact/number.
    2.  **Scale:** Scope of destruction/conflict scale (deaths, locations, damage).
    3.  **Location:** Casualty details of the hardest-hit area.
    4.  **Eyewitness:** Vivid story or key quotes.
    5.  **Impact:** Damage to infrastructure, supply lines, or safety.
    6.  **Response:** Military or emergency services official declarations.
    7.  **Ongoing:** Current risk warnings or rescue operations.
    8.  **Close:** Powerful final line explaining the stakes.

#### 2. Politics (Elections, Legislation, Summits)
*   **Extraction focus:** Key political figures, bills, treaty details, opposition reactions, debates, and implementation roadmaps.
*   **8-Sentence Structure:**
    1.  **Hook:** Surprising political development or milestone.
    2.  **Context:** Background of the debate and figures involved.
    3.  **Key Decision:** Specific law, agreement, or vote details.
    4.  **Impact:** Immediate changes and who it directly affects.
    5.  **Reaction:** Public sentiment or statements from opposition.
    6.  **Official Response:** State defense or justification.
    7.  **Ongoing:** Upcoming votes, debates, or implementations.
    8.  **Close:** Long-term political outlook or significance.

#### 3. Positive / Informative / Neutral (Science, Tech, Milestones)
*   **Extraction focus:** Breakthrough milestones, technology details, creator credits, expert analysis, and next launch phases.
*   **8-Sentence Structure:**
    1.  **Hook:** The major discovery or milestone that grabs attention.
    2.  **Context:** Why this development changes the field.
    3.  **Details:** Technical specifications, vehicle/instrument launch facts.
    4.  **Impact:** Long-term improvements to industry or public life.
    5.  **Key Figure:** Action or quotes from researchers or creators.
    6.  **Global Response:** Expert reactions or international analysis.
    7.  **Next Steps:** Immediate roadmap or upcoming developments.
    8.  **Close:** Future potential or global impact.

### Structured Citation Tagging & Speech Sanitization
- **Narrative Evidence Layering:** Scripts generated by both the short-form and long-form engines include explicit evidence-based citation markers to ground statements.
- **Support Tags:**
  - `[QUOTE: "text"]`: Highlights direct spoken testimonies.
  - `[TWEET: "user: text"]`: Highlights public statements, tweets, or social posts.
  - `[DOCUMENT: "fact"]`: Highlights official documents, agreements, or legal filings.
- **Narrative Reading Translation (`main.py`):**
  - Before voiceover generation, regex rules clean these brackets so that Kokoro/Piper read them naturally.
  - For `QUOTE` and `DOCUMENT`, the brackets are removed and only the text is spoken (the card provides the visual context).
  - For `TWEET`, the voiceover translates it into standard speech: `According to [user], [text]`.

### Word Count & Validation Controls
- **Target Word Range:** 120 to 162 words for short-form (vertical), 200–300 words for long-form (landscape).
- **LLM Safety Guard:** If the source article is under 300 characters, Ollama is bypassed completely. The pipeline jumps straight to spaCy extractive fallback to prevent severe LLM hallucinations on sparse information.
- **Filler Rejection:** If the script contains 2 or more generic cliches (e.g. *"serves as a reminder"*, *"underscores the importance"*, *"only time will tell"*), the script is rejected and Ollama regenerates.

### Script Cleanup Pipeline
To prepare the text for speech synthesis and subtitle overlay, the script passes through multiple regex filters:
1.  **Meta-Commentary Stripper:** Erases introductory LLM filler (e.g., *"Here is the script you requested..."*).
2.  **Label Cleaner:** Removes structural labels (*"Hook:"*, *"1. Scale --"*) generated during structured output.
3.  **Bare Digit Sentence Merger:** Joins sentences terminating on bare numbers to avoid speech fragment cuts.
4.  **Speech Typo Overlay Fixer:** Swaps common typos (e.g., `ceasfire` $\rightarrow$ `ceasefire`) before audio generation.

### Dependencies
- `spacy` (loaded with `en_core_web_sm`) — entity recognition, semantic grammar scoring.
- `requests` — local Ollama server communication (`http://localhost:11434`).
- `re` — multi-stage pattern cleaners.
- `heapq` — sentence scoring for fallback.

---

## 3.5 **scene_planner.py** — Scene Segmentation & Context Tagging

### Purpose
Split the script into **6–12 scenes**, each with:
- Scene text (~8–12 words per scene for caption readability)
- Keyword (for image search)
- Scene type (politics | war | technology | business | disaster | general)
- Named entity context (persons, locations, organizations)

### Key Functions

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `plan_scenes()` | Full script | List of scene dicts | Main segmentation entry |
| `extract_context_entities()` | Full script | Entity dict | NER extraction (PERSON, GPE, ORG, EVENT) |
| `_detect_scene_type()` | Scene text | Scene type string | Classify scene category |
| `detect_visual_context()` | Scene text | Visual context | Determine image search anchor |
| `extract_keywords()` | Scene text | Keywords string | Extract meaningful words |
| `_strict_chunk_sentence()` | Long sentence | List of chunks | Break sentences into caption-sized pieces |
| `calculate_scene_count()` | Full script | Integer | Dynamically compute scene count |

### Scene Planning Algorithm

```python
1. Calculate dynamic scene count (6–12)
   - Estimate video duration: words / 2.5 wps
   - Target 5 seconds per scene
   - Result: typically 6–10 scenes

2. Split script into N scenes
   - Try sentence boundaries first
   - Break long sentences into 8–12 word chunks
   - Merge short scenes if <8 words

3. For each scene:
   a) Extract keyword using spaCy NER
   b) Detect scene type (war | politics | tech | etc.)
   c) Extract named entities for image anchoring

4. Post-process:
   - Remove empty/weak scenes
   - Enforce minimum word count
   - Guard against bad caption breaks
```

### Named Entity Recognition (NER) System

**Extracted Entity Types:**

| Type | Examples | Purpose |
|------|----------|---------|
| PERSON | Trump, Biden, Zelensky | Image query anchor |
| GPE (Location) | Washington DC, Ukraine, London | Country context derivation |
| ORG | FBI, White House, NATO, BBC | Institutional context |
| EVENT | G7 Summit, Correspondents Dinner | Event-specific imagery |

**Country Context Derivation (3-tier fallback):**

1. **Tier 1 — Direct GPE extraction**
   ```python
   Washington DC → United States
   London → United Kingdom
   Kyiv → Ukraine
   ```

2. **Tier 2 — ORG-to-Country mapping** (if no GPE found)
   ```python
   Pentagon → United States
   Kremlin → Russia
   10 Downing Street → United Kingdom
   ```

3. **Tier 3 — Person name lookup** (last resort)
   ```python
   Keir Starmer → United Kingdom
   Putin → Russia
   Macron → France
   ```

### Scene Type Detection

Uses **whole-word regex matching** (prevents substring collisions):

```python
# Politics detection
Keywords: government, president, minister, election, parliament, congress
Pattern: \b(government|president|minister|...)\b

# War detection
Keywords: war, conflict, military, attack, ceasefire, gunfire, bomb
Pattern: \b(war|conflict|military|...)\b

# Technology detection
Keywords: technology, AI, software, innovation, algorithm, robot, cybersecurity
Pattern: \b(technology|AI|software|...)\b

# Disaster detection
Keywords: flood, earthquake, disaster, storm, hurricane, tsunami, wildfire
Pattern: \b(flood|earthquake|...)\b

# Business detection
Keywords: market, economy, finance, stock, business, trade, inflation
Pattern: \b(market|economy|...)\b
```

### Caption Chunking Strategy

**Objective:** Break long sentences into **readable caption chunks** (~10 words per caption)

**Algorithm (4 stages):**

**Stage 1 — Natural split points** (rule-based)
- Look for conjunctions in middle third of sentence
- Split triggers: "prompting", "forcing", "causing", "and", "but", "because"
- Validate: both halves ≥8 words, no weak ending word

**Stage 2 — Comma boundaries** (clause detection)
- Find natural comma within middle third
- Both halves must be ≥8 words
- Left chunk must not end with weak word

**Stage 3 — Midpoint fallback** (with guards)
- Try splitting at 50% position ± offset
- Guard 1: left chunk no weak endings
- Guard 2: right chunk no location continuations (Hilton, Association)
- Guard 3: no uppercase proper noun phrases crossing boundary

**Stage 4 — Preserve whole sentence**
- If nothing works, return sentence unchanged
- Never break grammar for word count

**Weak Ending Words:** a, an, the, at, in, on, of, for, to, by, with, and, but, or

**Location Continuations:** Hilton, Hotel, House, Palace, Building, Street, Avenue, University, Hospital, Church

### Sample Output

**Input Script:**
```
"This just happened and it's raising serious concerns. Ukraine's military 
struck Russian supply lines in eastern Donetsk. The attack targeted 
ammunition depots and logistics hubs."
```

**Generated Scenes:**

```python
[
  {
    "text": "This just happened and it's raising serious concerns.",
    "keyword": "Ukraine military attack",
    "type": "war",
    "entities": {
      "location": "Donetsk",
      "person": "",
      "org": "",
      "country_context": "Ukraine",
      "all_locations": ["Donetsk", ...],
      "all_orgs": [...]
    }
  },
  {
    "text": "Ukraine's military struck Russian supply lines.",
    "keyword": "military supply lines attack",
    "type": "war",
    "entities": {...}
  },
  {
    "text": "The attack targeted ammunition depots and logistics hubs.",
    "keyword": "ammunition depot attack",
    "type": "war",
    "entities": {...}
  }
]
```

### Dependencies

- `spacy` — NER and NLP
- `re` — Regex word boundary matching
- `config` — Scene duration constants

---

## 3.6 **image_fetcher.py** — Image Acquisition & Fallback System

### Purpose
Resolve and download **exactly one high-quality portrait (9:16) image** for each visual scene. The acquisition pipeline:
- Integrates local and network caching subsystems to prevent API rate-limiting and performance bottlenecks.
- Deploys a rigorous 7-tier priority hierarchy that puts realistic, verified news photography above AI-generated visuals.
- Applies strict anti-clipart, anti-toy, and anti-cartoon filters to preserve professional journalistic credibility.
- Supports B-roll alt image retrieval for visual cuts in longer scenes.

### Key Functions

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `fetch_image()` | Scene dict, index | Image file path | Main orchestration entry point. Reviews caches and manages the priority hierarchy. |
| `_check_local_cache()` | Query hash | Path or None | Checks if a valid cached image (>10 KB) matching the query hash exists in the local directory. |
| `_build_semantic_query()` | Scene dict | Query string | Compiles a natural-language search query from top nouns, verbs, and entities in the scene text. |
| `_build_query()` | Scene dict | List of queries | Ranks semantic queries with emotional boosts (e.g. `real conflict scene` or `government meeting`). |
| `_pexels_image_url()` | Query, type | URL or None | Queries Pexels API requesting 9:16 portrait photography. |
| `_should_reject_image()` | URL, query | Boolean | Credibility guard: filters out illustrations, cliparts, drawings, vectors, toys, or miniatures. |
| `_download()` | URL, path | Boolean | Downloads files atomically, verifying content size and type. |
| `fetch_wikipedia_person()` | Person name | Image URL or None | Hits Wikipedia API to find verified public portraits for named entities. |
| `generate_ai_image()` | Context query | Local path or None | Issues context queries to Pollinations.ai as a high-fidelity contextual graphic fallback. |

### Process Locks & Local Caching Systems

#### 1. Local Image Hash Cache (Query-Level)
*   **Mechanism:** Before initiating any remote API requests (Pexels, Unsplash, Wikipedia), the system generates an MD5 hash of the compiled search query string.
*   **Lookup:** It searches for `output/images/cache_[query_hash].jpg`. If a matching file exists on disk and is larger than 10 KB, the download step is bypassed completely, and the local image is reused instantly. This reduces network footprint by up to 80% on re-runs of similar news topics.

#### 2. Map Image Local Cache Lock (Geocoding-Level)
*   **Mechanism:** Geographic geocoding and CartoDB base tile compilation are extremely rate-limit sensitive.
*   **Lock:** If a previously compiled map stinger exists at `output/images/map_stinger.jpg` on the current run, the geocoding step (`geopy` and `staticmap`) is locked and skipped. The pipeline loads the local map directly, preventing Nominatim geocoding bans and slashing scene planning delays to 0ms.

### Image Priority Hierarchy & Specialized Engines

To maintain visual realism, credibility, and long-term retention, the fetcher utilizes a multi-layered procurement stack:

#### 1. Programmatic PIL Evidence Graphics (`generate_evidence_graphic`)
- For scenes containing structured citation tags (`quote_card`, `tweet_overlay`, or `evidence_graphic`), the fetcher **bypasses standard search APIs entirely**.
- It programmatically draws a dark, neon-accented card overlay directly onto a solid dark background image:
  - **Quote Cards:** Draws a left-aligned red stripe, quotation mark icon, wrapped quote body, and speaker attribution.
  - **Tweet Overlays:** Draws a Twitter/X card style layout with user profiles, handles, tweet content, and date stamps.
  - **Evidence Graphics:** Draws fact-highlight lists or data sheets for document citations.
- This maintains visual consistency across news commentaries and solves the problem of finding generic stock cliparts for highly specific quotes.

#### 2. Article-Level Editorial Scraping (Priority 0)
- Before calling generic APIs, the scraper (`scrape_editorial_image`) hits the article URL directly with custom headers.
- It parses `og:image` and `twitter:image` tags to download the exact editorial hero image used by the news publisher, guaranteeing the highest fact-relevance.

#### 3. General 7-Tier Hierarchy
If the scene is a general narration scene (not a citation card) and Priority 0 scraper returns nothing, it falls back through:
```
[START GENERAL SEARCH]
         ↓
[Tier 1: Wiki Person Portrait] ─── (Matches named PERSON entity from NER) ─→ [SUCCESS]
         ↓ (fail/none)
[Tier 2: Pexels News Photo] ────── (Realistic landscape/portrait photo) ──→ [SUCCESS]
         ↓ (fail/none)
[Tier 3: Wikimedia Topic Search] ─ (Matches specific ORG or GPE entity) ─→ [SUCCESS]
         ↓ (fail/none)
[Tier 4: Unsplash Stock Photo] ─── (Broad stock photo query matching key) → [SUCCESS]
         ↓ (fail/none)
[Tier 5: Pollinations AI Photo] ── (Generates photojournalistic image) ───→ [SUCCESS]
         ↓ (fail/none)
[Tier 6: Solid Dark Fallback] ──── (1080x1920 solid blue-grey color) ─────→ [SUCCESS]
```

#### 4. Anti-Stock Drift & AI Realism Prompts
- **Illustration Filter:** Custom rejection regex matches image URLs containing illustration, drawing, clipart, vectors, 3D, rendering, or models.
- **AI Prompt Tuning:** When Pollinations.ai is triggered as a fallback, it appends strict photojournalism anchors to prompts (e.g. `"... photojournalistic press photo, realistic details, news broadcast capture, taken on dslr 35mm lens, no rendering, no CGI"`) to prevent stock-looking artificial drawings.


### Query Boosting & Journalistic Suffixes

Semantic queries are automatically appended with context boosts and safety suffixes to pull authentic photography instead of stock marketing graphics:
- **Tense / War Boost:** `"... real conflict scene news realistic photo"`
- **Politics Boost:** `"... government meeting official news photo"`
- **Serious / Emergency Boost:** `"... emergency response scene news photo"`
- **Space / Technology Boost:** `"... aerospace launch scientific realistic photo"`
- **General Safety Suffix:** `"news realistic photo"` (appended to all text queries to guide search engine algorithms away from illustrations or commercial clipart).

### API Rejections (Journalistic Integrity Filters)
Images are automatically rejected if their source URL contains:
- `clipart`, `vector`, `cartoon`, `illustration`, `sketch`, `drawing`
- `toy`, `miniature`, `action figure`, `lego`, `diorama`, `playmobil`
- `render`, `3d`, `abstract`, `graphic`, `logo`
- Commercial terms: `shopping`, `retail`, `coupon`, `cash` (unless the story context is explicitly business/finance).

### Dependencies
- `requests` — API calling with backoff retries.
- `urllib` — Atomically handles download pipes.
- `hashlib` — Generates stable cache MD5 keys.
- `config` — Reads fallback API endpoints and directory paths.

---

## 3.7 **voice_generator.py** — Kokoro & Piper TTS Audio Generation

### Purpose
Convert scene narration texts into high-fidelity, professional WAV files using **Kokoro TTS** (primary neural model) and **Piper TTS** (high-speed offline fallback). The audio system:
- Dynamically selects voices and adjusts speed rates based on the story category.
- Synthesizes highly expressive, natural human-like speech with full offline capability.
- Normalizes all generated audios to standard broadcast levels (EBU R128 at -23 LUFS).
- Dynamically trims silent decays to guarantee fast, non-overlapping scene transitions.

### Key Functions

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `generate_audio()` | Scene text, index, context | WAV file path | Main orchestration entry point. Synthesizes WAV via Kokoro or Piper fallback. |
| `generate_audio_kokoro()` | Text, path, context | Boolean | Primary generator: runs Kokoro TTS pipeline with dynamic voice/speed context. |
| `normalize_audio()` | WAV file path | Boolean | Audio normalizer: calls ffmpeg loudnorm (`I=-23:TP=-1:LRA=11`) to balance loudness. |
| `trim_audio_silence()` | WAV path, thresholds | Boolean | Silence trimmer: runs ffmpeg silencedetect to crop trailing silence to an 80ms decay tail. |
| `_check_piper()` | None | Boolean | Fallback validator: verifies Piper.exe and ONNX medium voice model files exist. |
| `_merge_wavs()` | List of fragment paths | Boolean | Fragment merger: merges individual sentence WAVs into a single seamless scene audio track. |

### 1. Primary Engine: Kokoro TTS (`hexgrad/Kokoro-82M`)
*   **What is Kokoro?** A state-of-the-art offline neural text-to-speech engine. It produces highly human-like inflections, pauses, and natural expressions.
*   **Initialization:** Loads a single Hugging Face KPipeline instance configured with English codes (`lang_code='a'`) for offline execution.
*   **NumPy 2.x Audio Tensors Patch:** The engine yields individual torch tensors per token. The module intercepts these tensors, detaches them safely from torch memory, converts them to standard NumPy float32 arrays, and cleanly concatenates them using `numpy.concatenate()` before writing to disk using standard soundfile writing. This avoids any NumPy version mismatches or memory allocation errors.

### 2. Secondary/Fallback Engine: Piper TTS (ONNX Offline Runtime)
*   **When used:** Activated automatically if `kokoro`, `soundfile`, or `espeak-ng` system packages are not installed or fail to import on the host machine.
*   **Subprocess Execution:** Runs local `piper.exe` subprocess command passing speech text via `stdin`:
    ```bash
    echo "[text]" | ./piper/piper.exe --model ./piper/en_US-lessac-medium.onnx --length_scale 1.15 --output_file [path]
    ```
*   **Sentence Splitting & Pause Inserting:** Piper can sound monotone when reading long paragraphs. To resolve this, if the scene contains multiple sentences, the fallback engine splits the text at punctuation, generates separate ONNX WAVs for each sentence, inserts a deterministically-timed silence fragment (`PAUSE_AFTER_SENTENCE = 0.4` seconds) between sentence tracks, and merges the final WAVs using Python `wave` streams.

### Dynamic Context-Aware Voice and Speed Map

Narration tone and pace adapt dynamically to the emotional context of the news story:

#### A. Voice Allocation Map
A voice pool containing premium American and British neural voices is maintained:
- `af_nova` — Warm, neutral professional American female (Default for business and technology).
- `am_adam` — Firm, authoritative American male (Default for war and politics stories).
- `af_sarah` — Warm, narrative American female (Default for positive and human-interest stories).
- `bm_george` — Authoritative British male with BBC-style gravitas (Default for emergencies, tense, and serious topics).
- *Fallback Roulette:* Rotates between all pool voices deterministically based on the current day of the year (`date.today().tm_yday`), providing narrative variety across pipeline runs.

#### B. Speed Scale Map
Speech rates are adjusted dynamically to optimize user retention and fit the gravity of the topic:
- **Default categories:** Forced to **1.22x speed** to ensure fast-paced, modern news delivery.
- **Verdict / Serious segment scenes:** Decelerated to **0.90x speed** to preserve gravity, weight, and dramatic impact during final announcements.
- Fallback engines (Piper) map to default length scales matching the active voice settings.

### Post-Processing & Audio Engineering

#### 1. EBU R128 Broadcast Normalization (`normalize_audio`)
To guarantee that the voice narration is perfectly audible over ambient audio without clipping, the WAV is normalized:
- **Filter:** ffmpeg `loudnorm` filter with parameters: `I=-23:TP=-1:LRA=11`.
- **Target:** -23 LUFS integrated loudness, with true peaks limited to -1 dBTP.
- **Conversion:** Encodes to 22,050 Hz Mono 16-bit PCM WAV.

#### 2. Decay Silence Trimming (`trim_audio_silence`)
To prevent awkward pauses between scene cuts and timeline overlaps in captions:
- **Detection:** Uses ffmpeg `silencedetect` at a threshold of `-45.0 dB`.
- **Trimming:** Crops trailing silence, keeping exactly `keep_tail_s = 0.08` seconds (80ms) of natural reverb decay. This guarantees tight scene transitions while preventing narration cutoffs.

### Error Handling & Validation
- **Regeneration Force:** For every execution run, standard voice syntheses delete any pre-existing audio files in the output folder. This ensures new narrative generations never mismatch with old scene files.
- **Subprocess Failures:** Handled gracefully. If `piper.exe` crashes or times out (>60s), the engine reports failure without crashing the master pipeline, allowing subsequent scenes to attempt synthesis.
- **Format Integrity:** Outputs are validated dynamically. Files under 1 KB are flagged as empty errors and rejected, prompting emergency extractive fallbacks.

### Dependencies
- `kokoro` & `soundfile` — Primary speech synthesis.
- `numpy` — Concatenates PyTorch audio tensors.
- `wave` — Direct wave file header merging.
- `subprocess` — Executes the local Piper ONNX compiler.

---

---

## 3.8 **video_builder.py** — Final Video Assembly (MoviePy)

### Purpose
Assemble final MP4 video with:
- Scene images as backgrounds
- Progressive captions (word-by-word)
- Audio narration (synchronized)
- Branding elements (breaking news banner, lower-third crawl, brand bar)
- Professional styling (gradient overlays, text cards)

### Key Functions

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `build_video()` | List of scene dicts | MP4 file path | Main video builder |
| `_make_background()` | Image path, W, H | numpy array (RGB) | Load & scale image to frame |
| `_make_gradient_overlay()` | W, H | numpy array (RGBA) | Create fade gradient |
| `_make_text_card()` | Text, W, H | numpy array (RGBA) | Render styled text pill |
| `_make_progressive_caption()` | Text, duration, W, H | VideoClip | Frame-based progressive captions |
| `_make_breaking_news_banner()` | W, H | numpy array (RGBA) | Red "BREAKING NEWS" bar (scene 0 only) |
| `_make_lower_third()` | Headline, source, W, H | numpy array (RGBA) | Professional lower-third crawl |
| `distribute_word_timings()` | Words, total_duration | List of (start, end) tuples | Calculate word display timings |
| `_font()` | Size, bold | PIL Font | Load system font with fallback |

### Video Parameters

```python
VIDEO_WIDTH  = 1080         # pixels (9:16 vertical format)
VIDEO_HEIGHT = 1920         # pixels
VIDEO_FPS    = 24           # frames per second
ACCENT_COLOR = (220, 50, 50)   # Breaking News Red (RGB)
BAR_HEIGHT   = 90           # Branding bottom bar height
BRAND_NAME   = "AI NEWS"    # Lower banner branding text
```

### Video Composition (Layer Stack)

**Per-frame composition (bottom to top):**

```
Layer 6 — Branding Bottom Bar (RGBA)
         └─ Solid dark strip at y=1830 with "AI NEWS" logo

Layer 5 — Text Overlay (RGBA)
         └─ Progressive captions card (last 12 words with current in yellow)

Layer 4 — Breaking News Banner (RGBA)
         └─ Red "🔴 BREAKING NEWS | LIVE" bar (Scene 0 only)

Layer 3 — Lower-Third Crawl (RGBA)
         └─ News Headline | Source | Location (placed at y=1700)

Layer 2 — Gradient Overlay (RGBA)
         └─ Transparent-to-black fade (covers lower 55% of the frame)

Layer 1 — Ken Burns Zoom Background Image (RGB)
         └─ Portrait scaled (cover mode) with B-roll mid-scene cuts

Base — Solid Dark Background (RGB)
       └─ Solid dark blue-grey (15, 23, 42) fallback fill
```

### Advanced Timeline Orchestration & Stability Guards

#### 1. Dynamic Scene Drop (Compression Guard)
To prevent narration and captions from overlapping during timeline compression (e.g. if the video runs too long), `video_builder.py` deploys a dynamic drop guard:
*   **Scale Factor Calculation:** Reads all scene audio durations. If total duration exceeds the limit, it calculates the required timeline compression scale factor.
*   **Threshold:** If the compression scale drops below $0.95$ (meaning high overlap risk), the pipeline enters **Emergency Scene Drop Mode**.
*   **Dropping Logic:** It preserves the crucial Hook (Scene 0) and the final conclusion/CTA outro. It then dynamically drops the middle scene(s), re-numbers indices, and re-computes timeline boundaries. This guarantees $1.0\times$ natural speed delivery without speech overlaps.

#### 2. Mid-Scene B-Roll Cuts
To keep the visual presentation dynamic and high-engagement:
*   If a scene's audio duration exceeds **5.2 seconds**, a static background becomes repetitive.
*   **Cuts:** The builder fetches an alternative query image (B-roll) and executes a clean visual cut exactly halfway through the scene duration, preserving the continuous audio narration and subtitle sequence.

#### 3. Geographic Map Stingers
*   For geopolitical news stories, the system integrates localized maps.
*   **Attribution:** Resolves country contexts using whole-word NLP matches (e.g. Gaza, Israel, Ukraine, Taiwan).
*   **Drawing:** Geocodes regional coordinates with `geopy` and compiles a beautiful static map using CartoDB satellite or dark tiles. 
*   **Placement:** Injected as a 2.5-second top corner overlay to establish location context instantly.

#### 4. Dynamic Background Music Ducking
*   To create a highly premium, broadcast-quality audio experience, background music is programmatically ducked when key evidence overlays are displayed.
*   **Segment Mapping:** At timeline composition time, the builder maps the start and end timestamps of all scenes assigned with a citation type (`quote_card`, `tweet_overlay`, or `evidence_graphic`).
*   **Vector Volume Filter:** A MoviePy audio volume filter function `.fl(filter_fn)` is applied to the background music track. The filter maps timestamps `t` (supporting both float values and NumPy arrays) and automatically scales the music volume down from default levels (`0.12`) to a near-silent level (`0.025`) during these segments.
*   **Pacing Effect:** This emphasizes primary source evidence cards and replicates the professional audio pacing of premium high-retention commentary networks.

### Scene Rendering Algorithm

```python
For each scene in scenes:

  1. COMPRESSION CHECK
     - Calculate cumulative timeline duration.
     - Drop middle scenes if scale < 0.95; update indices.

  2. BASE BACKGROUND (Ken Burns & B-Rolls)
     - Load primary image. Apply minor Gaussian blur (radius=0.8) to soften edges.
     - Apply continuous Ken Burns zoom-in effect (scale 1.0 -> 1.08).
     - If duration > 5.2s, stitch B-roll image at mid-duration.

  3. GRADIENT OVERLAY
     - Draw Transparent (y=864) to 85% Black (y=1920) vertical gradient.
     - Keeps the upper frame clear for faces while guaranteeing subtitle legibility.

  4. TEXT COMPONENT COMPOSITION
     - Render Scene 0 Red Breaking News Header.
     - Draw Lower-Third News Crawl: Headline | Source | Location (GPE).
     - Render word-by-word highlighted progressive captions pill.

  5. AUDIO BINDING
     - Load scene EBU-normalized mono WAV.
     - Extract exact duration and bind WAV as the scene clip's audio channel.
```

### Progressive Caption System

**Goal:** Subtitles fade in word-by-word synced to speech, highlighting the active spoken word in gold to maximize viewer retention.

**Algorithm:**
1.  **Tokenization:** Splits scene narration text into an array of words.
2.  **Timing Distribution:** Calculates duration weights based on character length (shorter words like *in*, *to* receive shorter durations; long terms receive longer blocks).
3.  **Visible Window:** Subtitles are capped at 12 visible words on screen to prevent card overflow. As speech progresses, older words scroll off.
4.  **Highlighting:** PIL draws a dark, rounded text pill (radius=22px) with a left red accent stripe. Spoken words are rendered in white, while the current active word is painted in Bright Gold (`255, 215, 0`).

**Timing Map Example:**
```
Scene duration: 4.8 seconds
Text: "Israel announces a ceasefire in Lebanon."

Word Timings (calculated weight):
  0.0s - 0.7s : "Israel" (highlighted)
  0.7s - 1.4s : "announces" (highlighted)
  1.4s - 1.8s : "a"
  1.8s - 2.8s : "ceasefire"
  2.8s - 3.2s : "in"
  3.2s - 4.8s : "Lebanon."
```

### Text Styling

**Pill Text Card Layout:**
```
┌──────────────────────────────────────────┐
│ ▌ Israel announces a ceasefire           │
│   in Lebanon.                            │
└──────────────────────────────────────────┘
```
- **Accent Stripe:** Left-aligned Red bar (`220, 50, 50`) at 100% opacity, 8px width.
- **Card Background:** Rounded Pill (radius=22px) colored in Charcoal (`10, 10, 10`) at 75% opacity.
- **Text Font:** Arial Bold, 48 pt.
- **Active Spoken Word:** Gold (`255, 215, 0`).
- **Inactive Spoken Words:** Clean White (`255, 255, 255`).

### Breaking News Banner (Scene 0)

```
┌─────────────────────────────────────────────────────┐
│ 🔴 BREAKING NEWS                             LIVE   │
└─────────────────────────────────────────────────────┘
  
  Height: 72 px
  Background: Crimson Red (220, 30, 30) @ 95% opacity
  Text: Bold White, 30 pt
  Right Badge: "LIVE" in red on white pill card
```

### Lower-Third Crawl Layout
- Placed 110px above the branding bar.
- Shows: `[SOURCE] TITLE | [LOCATION]` in clean white text on a translucent charcoal bar.

---
┌─────────────────────────────────────────────────────┐
│ [RED] UKRAINE HITS RUSSIAN SUPPLY LINES  BBC NEWS   │
│ 10 DOWNING STREET, LONDON                           │
└─────────────────────────────────────────────────────┘

Height: 110 px
Background: Dark (8, 8, 18) @ 82% opacity
Left stripe: Red (10 px wide)
Top border: White line (subtle, 60% opacity)
Headline: White, Bold, 34 pt (truncated to 38 chars)
Location: Grey, Regular, 24 pt
Source: Right-aligned, grey, 22 pt
```

### Font Management

**Cross-platform font loading:**

```python
Windows:
  - C:/Windows/Fonts/arialbd.ttf (bold)
  - C:/Windows/Fonts/arial.ttf (regular)

Linux:
  - /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
  - /usr/share/fonts/truetype/liberation/LiberationSans-*.ttf

macOS:
  - /Library/Fonts/Arial*.ttf

Fallback: PIL default font (if none found)
```

### Audio Synchronization

**Critical:** Video duration must equal **audio duration**, never:
- Shorter (audio cuts off)
- Longer (silence at end)
- Repeated (audio loops)

```python
# Correct approach:
for scene in scenes:
  audio_path = scene["audio_path"]
  audio_clip = AudioFileClip(audio_path)
  scene_duration = audio_clip.duration  # READ from audio
  
  # Build video clip with this exact duration
  scene_video = create_scene_video(..., duration=scene_duration)
  # Attach audio
  scene_video = scene_video.set_audio(audio_clip)
```

### MoviePy Workflow

```python
1. For each scene:
   - Create background image clip (ImageClip)
   - Create overlays (caption, banner, lower-third)
   - Composite all layers (CompositeVideoClip)
   - Set duration = audio duration
   - Attach audio track (AudioFileClip)
   - Append to scene_clips list

2. Concatenate all scene clips
   - concatenate_videoclips(scene_clips)

3. Render to MP4
   - write_videofile(OUTPUT_VIDEO, fps=24, verbose=False, logger=None)

4. Cleanup
   - Close all clips
   - Remove temporary files
```

### Output Format

**Final MP4:**
- **Codec:** H.264 (AVC)
- **Resolution:** 1080×1920 (9:16 vertical)
- **Frame Rate:** 24 fps
- **Audio:** AAC, 48 kHz, Mono
- **Duration:** 45–55 seconds
- **File size:** ~30–50 MB (typical)
- **Quality:** High (suitable for social media)

### Dependencies

- `PIL (Pillow)` — Image loading, text rendering
- `numpy` — Array manipulation
- `moviepy` — Video compositing & rendering
- `config` — VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, OUTPUT_VIDEO

---

## 3.9 **video_review.py** — Quality Analysis & Metrics

### Purpose
Automated quality review of the generated video. Runs the **entire pipeline as a subprocess** and analyzes output.

### Key Functions

| Function | Input | Output | Purpose |
|----------|-------|--------|---------|
| `preflight()` | None | Boolean | Check venv, main.py exist |
| `run_main_pipeline()` | None | (stdout, code, elapsed) | Execute main.py subprocess |
| `verify_output()` | run_start_time | dict with is_valid, mtime, size | Verify video was created this run |
| `get_video_duration()` | None | float (seconds) | Read duration via MoviePy |
| `parse_stdout()` | stdout_lines, exit_code | ParsedRun object | Extract pipeline metrics |
| `generate_report()` | ParsedRun, duration, etc. | Markdown string | Create review report |

### Execution Flow

```
1. PREFLIGHT
   ├─ Validate venv Python exists
   ├─ Validate main.py exists
   └─ Validate venv paths correct

2. RUN MAIN PIPELINE
   ├─ Set FORCE_REFRESH=1 env var
   ├─ Execute: .venv\Scripts\python.exe main.py
   ├─ Capture stdout in real-time
   ├─ Record elapsed time
   └─ Capture exit code

3. VERIFY OUTPUT
   ├─ Check output/news_video.mp4 exists
   ├─ Verify file was modified after run start
   ├─ Record file size, modification time
   └─ Return is_valid boolean

4. READ DURATION
   ├─ Import MoviePy (from venv)
   ├─ Open video file
   ├─ Read .duration attribute
   ├─ Close clip
   └─ Return float (seconds)

5. PARSE METRICS
   ├─ Extract article title from stdout
   ├─ Extract context (tense | politics | etc.)
   ├─ Extract scene count
   ├─ Extract image success rate
   ├─ Extract audio success rate
   └─ Build ParsedRun object

6. GENERATE REPORT
   ├─ Calculate quality scores
   ├─ Check against target duration (45–55s)
   ├─ Verify caption consistency
   ├─ Assess image coverage
   ├─ Output Markdown report
   └─ Save to VIDEO_QUALITY_ANALYSIS_REPORT.md
```

### Quality Metrics

**Duration Check:**
```python
TARGET_DUR_LOW  = 45.0 seconds (minimum)
TARGET_DUR_HIGH = 55.0 seconds (maximum)

Status:
  ✅ PASS if 45 ≤ actual ≤ 55
  ⚠️  WARN if 40 ≤ actual < 45 (slightly short)
  ❌ FAIL if actual < 40 or actual > 55
```

**Scene Analysis:**
```python
- Count of scenes generated
- Audio generation success rate (%)
- Image acquisition success rate (%)
- Average scene duration
- Caption word count per scene
```

**Context Classification:**
```python
Detected contexts:
  - tense (war, conflict)
  - serious (disaster)
  - politics (government, elections)
  - positive (achievements)
  - informative (technology, science)
  - neutral (other)
```

### Report Output

**Format:** Markdown file `VIDEO_QUALITY_ANALYSIS_REPORT.md`

**Structure:**
```markdown
# Video Quality Analysis Report
Timestamp: [generation time]
Run Duration: [X.X seconds]

## Executive Summary
Status: [PASS/WARN/FAIL]
Video Duration: [XX.X seconds]
Status: [✅ Within target | ⚠️ Slightly short | ❌ Outside range]

## Pipeline Metrics
- Article Title: [title]
- Detected Context: [context]
- Scenes Generated: [N]
- Images Acquired: [N] / [N] ([%]%)
- Audio Generated: [N] / [N] ([%]%)
- Pipeline Runtime: [X.X seconds]

## Scene Breakdown
[Table with scene details]

## Observations
- [Issue 1]
- [Issue 2]
- [Strength 1]
```

### Stdout Parsing Regex Patterns

```python
Article title:
  r"\[NewsFetcher\] Article: (.+)"

Context:
  r"\[ScriptGen\] Context detected: '([^']+)'"

Scene count:
  r"\[ScenePlanner\] (\d+) scenes planned"

Image success:
  r"\[ImageFetcher\] Scene (\d+): Found|SUCCESS"

Audio success:
  r"\[VoiceGen\] Audio saved -> .*/scene_(\d+)_"

Final success:
  r"\[SUCCESS\] Video created: (.+)"
```

### Environment Validation

```python
# CRITICAL: Must run in .venv
if ".venv" not in sys.executable:
  print("❌ ERROR: Not running in virtual environment")
  exit(1)

VENV_PYTHON = ".venv\Scripts\python.exe"
MAIN_SCRIPT = "main.py"
```

### Dependencies

- `subprocess` — Run main.py
- `os` — File I/O, paths
- `re` — Stdout parsing
- `moviepy.VideoFileClip` — Duration reading
- `time` — Performance tracking
- `pathlib.Path` — Path utilities

---

## 3.10 **VIDEO_QUALITY_ANALYSIS_REPORT.md** — Auto-Generated Report

### Purpose
Markdown file automatically generated by `video_review.py` after each run.

### Contents

- Pipeline execution metrics
- Duration check results
- Image/audio success rates
- Scene-by-scene breakdown
- Context classification
- Issues and observations

**Example:**
```markdown
# Video Quality Analysis Report
Generated: 2026-04-28 14:32:15

## Status: ✅ PASS
Duration: 51.2 seconds (target: 45–55s)

## Metrics
- Scenes: 8
- Images: 8/8 (100%)
- Audio: 8/8 (100%)
- Context: war

## Issues: None detected
```

## 3.11 **long_form_script_generator.py** — Deep-Dive Narrative Script Engine

### Purpose
Generates high-retention, detailed news narration scripts for landscape (16:9) formats.
- **Word Range:** 200–300 words, structured to fit a 2-to-3 minute video target.
- **5-Layer Architecture:**
  1. **Hook:** A high-impact opening question or major statement.
  2. **Context:** Deeper background explaining how the situation escalated.
  3. **Evidence:** Direct primary source citations inside special bracket tags (e.g. `[QUOTE: "..."]`, `[TWEET: "..."]`, or `[DOCUMENT: "..."]`).
  4. **Analysis:** Explaining secondary statistics, analytics, or counter-arguments.
  5. **Impact / Outro:** The final verdict, stakes, or call to action.

---

## 3.12 **long_form_video_builder.py** — Landscape (16:9) Video Compositor

### Purpose
Composes landscape-format H.264 / AAC MP4 videos at 1920×1080 resolution.
- **Dynamic Audio Ducking:** Implements moviepy custom vectorized filter `.fl()` mappings. When an evidence-tagged scene (e.g. a quote or tweet card) is active, the engine ducks the background music volume from normal levels (`0.12`) to a near-silent level (`0.025`) to increase speech intelligibility.
- **Layout Layers:**
  - Layer 1: Background image with soft Gaussian blur (0.8 radius) and Ken Burns pan/zoom.
  - Layer 2: Main visual card or programmatic quote card layout.
  - Layer 3: Geographic static map stinger (CartoDB dark/light tiles overlay).
  - Layer 4: Lower-third crawling ticker presenting article headline, source, and locations.
  - Layer 5: Subtitle overlays (word-by-word gold active word highlighting).
  - Layer 6: Brand overlay bar and logo.

---

## 3.13 **ui_server.py** — Local Web Control Dashboard

### Purpose
Runs a local Flask-based web application to orchestrate, customize, and review pipeline runs.
- **Dashboard Interface:** Provides forms to choose format (vertical/landscape/both), category, and channel profiles.
- **Real-Time Logs:** Streams console output of ongoing generation tasks using Server-Sent Events (SSE).
- **Execution Manager:** Spawns runs in background thread workers and stores statuses.
- **Video Player:** Lists past renders and serves output MP4s, logs, and generated quality reports.

---

## 3.14 **db_manager.py** — Database Interface & Schema

### Purpose
Manages connections to the local SQLite database (`db.sqlite`).
- **Tables Managed:**
  - `articles`: Track processed RSS news links to avoid duplicate reports.
  - `videos`: Store metadata of successful runs, duration, and output paths.
  - `analytics`: Maintain channel statistics (views, impressions, subscribers) synced from API reports.

---

## 3.15 **channel_profiles.py** — Identity Settings

### Purpose
Encapsulates brand identity properties.
- **Profiles:** Maps channels (`newscup`, `newscup_india`) to customized voice accents, speech speeds (Default Kokoro 1.22x speed pacing, verdict 0.90x speed), logos, color palettes, and outro scripts.

---

## 3.16 **youtube_uploader.py** — Automatic YouTube Publisher

### Purpose
Coordinates automated API publishing of completed MP4 clips.
- **Data API v3:** Authenticates via local client secrets (`client_secrets_newscup.json`) and token caches.
- **Automation:** Uploads to the correct channel, attaches title, tags, description templates, sets category ID to `25` (News & Politics), and defaults to "private" mode for moderator review.

---

## 3.17 **thumbnail_generator.py** — Cover Graphics Engine

### Purpose
Draws horizontal (1280×720) and vertical (1080×1920) cover thumbnails.
- Composites scene images with heavy black-to-transparent overlays.
- Draws large high-contrast text layers with borders and drop-shadows.
- Places brand logos and red border frames.

---


# 4. END-TO-END DATA FLOW

## Complete Pipeline Walkthrough

```text
┌─────────────────────────────────────────────────────────────┐
│ INPUT: 8 News RSS Feeds (BBC, Sky, DW, etc.)                │
│ (Scored and selected automatically)                         │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
        ┌──────────────────────────────┐
        │  1. NEWS FETCHER             │
        │  news_fetcher.py             │
        │  (feedparser + bs4)          │
        └──────────────────────────────┘
                       ↓
        ┌──────────────────────────────────────┐
        │ OUTPUT: Article Dict                 │
        │ {                                    │
        │   "title": "Ukraine Hits...",        │
        │   "summary": "Ukrainian forces...",  │
        │   "link": "https://bbc.com/..."      │
        │ }                                    │
        └──────────────────────────────────────┘
                       ↓
        ┌──────────────────────────────┐
        │  2. SCRIPT GENERATOR         │
        │  script_generator.py         │
        │  (Ollama Llama3 + regex filter)│
        └──────────────────────────────┘
                       ↓
        ┌────────────────────────────────────────────┐
        │ OUTPUT: Full News Script (~75 words)       │
        │ "This just happened and it's raising       │
        │ serious concerns. Ukraine's military       │
        │ struck Russian supply lines..."            │
        └────────────────────────────────────────────┘
                       ↓
        ┌──────────────────────────────┐
        │  3. SCENE PLANNER            │
        │  scene_planner.py            │
        │  (NER extraction, chunking)  │
        └──────────────────────────────┘
                       ↓
        ┌──────────────────────────────────────┐
        │ OUTPUT: 6–12 Scene Objects           │
        │ [{                                   │
        │   "text": "This just happened...",   │
        │   "keyword": "Ukraine military",     │
        │   "type": "war",                     │
        │   "entities": {...}                  │
        │ }, ...]                              │
        └──────────────────────────────────────┘
              ↙              ↓              ↘
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │ IMAGE        │  │ VOICE        │  │ SCENE DATA   │
   │ FETCHER      │  │ GENERATOR    │  │ (stored)     │
   │              │  │              │  │              │
   └──────────────┘  └──────────────┘  └──────────────┘
         ↓                  ↓                  ↓
    ┌─────────────┐   ┌──────────┐      ┌──────────┐
    │ DuckDuckGo  │   │ Kokoro   │      │ Keyword, │
    │   (Primary) │   │   TTS    │      │  Type,   │
    │      ↓      │   │ (local)  │      │ NER data │
    │ Pexels/Wiki │   │    ↓     │      │          │
    │ (fallback)  │   │ scene_XX │      │          │
    │      ↓      │   │ _HASH    │      │          │
    │ Dark fill   │   │ .wav     │      │          │
    │             │   │          │      │          │
    │ scene_XX    │   │ (1–8 MB) │      │          │
    │ .jpg        │   │          │      │          │
    └─────────────┘   └──────────┘      └──────────┘
         ↓                  ↓                  ↓
    ┌──────────────────────────────────────────────┐
    │  Scene Dict (enriched)                        │
    │  {                                           │
    │    "text": "Ukraine's military...",          │
    │    "keyword": "Ukraine military",            │
    │    "type": "war",                            │
    │    "image_path": "output/images/scene_00.jpg"│
    │    "audio_path": "output/audio/scene_00_....│
    │    "headline": "Ukraine Hits Russian...",    │
    │    "news_source": "BBC News",                │
    │    "entities": {...}                         │
    │  }                                           │
    └──────────────────────────────────────────────┘
         ↓ (all scenes combined)
    ┌──────────────────────────────────────────────┐
    │  4. VIDEO BUILDER                             │
    │  video_builder.py                            │
    │  (MoviePy composition + rendering)            │
    └──────────────────────────────────────────────┘
         ↓
    ┌───────────────────────────────────────────────┐
    │ OUTPUT: Final MP4 Video                       │
    │                                              │
    │ output/news_video.mp4                        │
    │ - Resolution: 1080×1920 (9:16)               │
    │ - Duration: 45–55 seconds                    │
    │ - 6–12 scenes with:                          │
    │   * Background images                        │
    │   * Progressive captions (word-by-word)      │
    │   * Synchronized audio narration             │
    │   * Branding elements (banner, crawl, bar)   │
    │ - ~30–50 MB file size                        │
    │ - Ready for social media                     │
    └───────────────────────────────────────────────┘
```

## Data Structures (Key Formats)

### Article Dict
```python
{
  "title": str,       # News headline
  "summary": str,     # Article excerpt
  "link": str         # Source URL
}
```

### Scene Dict (intermediate)
```python
{
  "text": str,           # Scene narration (8–12 words)
  "keyword": str,        # Image search keyword
  "type": str,           # "war" | "politics" | "technology" | etc.
  "entities": {          # Named entity context
    "person": str,
    "location": str,
    "org": str,
    "country_context": str,
    "all_persons": [str],
    "all_locations": [str],
    "all_orgs": [str]
  }
}
```

### Scene Dict (enriched with assets)
```python
{
  "text": str,
  "keyword": str,
  "type": str,
  "image_path": str,     # Full path to scene_XX.jpg
  "audio_path": str,     # Full path to scene_XX_HASH.wav
  "headline": str,       # Article headline (from main.py)
  "news_source": str,    # "BBC News"
  "entities": {...}
}
```

---

# 5. TECHNOLOGIES & DEPENDENCIES

## Programming Language & Runtime

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12+ | Primary language |
| .venv | Built-in | Virtual environment (isolation) |
| sys | Built-in | Python introspection |
| os | Built-in | File I/O, paths |
| subprocess | Built-in | Execute Piper TTS binary |
| re | Built-in | Regex (text cleaning) |
| time | Built-in | Performance tracking |
| hashlib | Built-in | MD5 hash (filename generation) |
| json | Built-in | JSON parsing |
| urllib | Built-in | HTTP requests, URL parsing |
| pathlib | Built-in | Path utilities |

## Core Libraries

| Library | Version | Purpose | Used By |
|---------|---------|---------|---------|
| **feedparser** | Latest | RSS feed parsing | news_fetcher.py |
| **spaCy** | 3.x+ | NLP (NER, tokenization) | script_generator.py, scene_planner.py |
| **spacy** model | en_core_web_sm | English language model | Both NLP modules |
| **Pillow (PIL)** | 10.x+ | Image processing, text rendering | video_builder.py |
| **numpy** | 1.24+ | Array operations, image buffers | video_builder.py |
| **moviepy** | 1.0.3 | Video compositing & rendering | video_builder.py, video_review.py |
| **requests** | 2.31+ | HTTP (Pexels API) | image_fetcher.py |

## External Services

| Service | Type | Purpose | Authentication |
|---------|------|---------|-----------------|
| **Pexels API** | REST | Image search | API key (free, 200 req/hour) |
| **BBC RSS Feed** | RSS | News articles | No auth (public feed) |
| **Wikipedia API** | REST | Image fallback | No auth (public API) |

## Machine Learning Models

| Model | Size | Purpose | Source | Format |
|-------|------|---------|--------|--------|
| **en_core_web_sm** | ~40 MB | spaCy English NLP | huggingface.co | PyTorch |
| **en_US-lessac-medium.onnx** | 60.27 MB | Piper TTS voice | huggingface.co/rhasspy | ONNX |
| **libtashkeel_model.ort** | ~5 MB | Arabic text prep | rhasspy/piper | ONNX |

## System Tools

| Tool | Purpose | Installed By |
|------|---------|--------------|
| **ffmpeg** | Video encoding (H.264) | Manual installation |
| **piper.exe** | TTS inference engine | Manual download |
| **ONNX Runtime** | Model inference | piper binary includes |

## Environment Configuration

```python
# Variable Resolution Order:
# 1. OS environment variables (highest priority)
# 2. config.py hardcoded values (fallback)

Environment Variables Used:
  - PIPER_EXECUTABLE (optional)
  - PIPER_MODEL (optional)
  - PEXELS_API_KEY (optional, has hardcoded fallback)
  - FORCE_REFRESH (set by video_review.py)
```

## Dependency Tree

```
main.py
├── news_fetcher.py → feedparser
├── script_generator.py → spacy, re, heapq
├── scene_planner.py → spacy, re
├── image_fetcher.py → requests, re, urllib
├── voice_generator.py → subprocess, os, hashlib
├── video_builder.py → PIL, numpy, moviepy
└── config.py → os

video_review.py
├── subprocess
├── os, re, time
├── moviepy (VideoFileClip)
└── pathlib
```

---

# 6. INTERNAL MODULE CONNECTIONS

## Module Interaction Map

```
┌─────────────────────────────────────────────────────────┐
│ main.py (ORCHESTRATOR)                                  │
│ - Imports all modules                                   │
│ - Calls functions sequentially                          │
│ - Manages output directory                              │
│ - Handles validation & errors                           │
└────┬────────────────┬───────────────┬──────────────┬────┘
     │                │               │              │
     ↓                ↓               ↓              ↓
┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌─────────┐
│ news_fetcher │ │ script_gen   │ │scene_plan │ │ image   │
│              │ │              │ │           │ │ fetcher │
│ Returns:     │ │ Uses:        │ │ Uses:     │ │         │
│ {article}    │ │ - spaCy      │ │ - spaCy   │ │ Uses:   │
└──────────────┘ │ - feedparser │ │ - regex   │ │ - Pexels│
                 │              │ │ - NER     │ │ - Wiki  │
                 │ Returns:     │ │           │ │ - Reqs  │
                 │ script (str) │ │ Returns:  │ │         │
                 └──────────────┘ │ scenes[]  │ │ Returns:│
                                  │ (dicts)   │ │ paths   │
                                  └───────────┘ │ (str)   │
                                                └─────────┘
                                                     ↓
                                            ┌─────────────────┐
                                            │ voice_generator │
                                            │                 │
                                            │ Uses:           │
                                            │ - Piper (exe)   │
                                            │ - subprocess    │
                                            │                 │
                                            │ Returns:        │
                                            │ WAV paths (str) │
                                            └─────────────────┘
                                                     ↓
                        ┌────────────────────────────┴────────────────┐
                        ↓                                             ↓
                   ┌──────────────┐                        ┌───────────────────┐
                   │Enriched Scene│                        │  video_builder.py │
                   │  (dict with  │                        │                   │
                   │all assets)   │                        │ Uses:             │
                   └──────────────┘                        │ - PIL/numpy       │
                        ↓                                  │ - MoviePy         │
                        └─────────────────────────────────→│ - config          │
                                                           │                   │
                                                           │ Returns:          │
                                                           │ MP4 file path     │
                                                           └───────────────────┘
                                                                    ↓
                                                           ┌──────────────────┐
                                                           │  output/          │
                                                           │  news_video.mp4   │
                                                           └──────────────────┘
```

---

# Recent Updates
- `script_generator.py` was updated to use `llama3` as the Ollama model candidate instead of `qwen3.5:cloud`.
- The Ollama command now points to the local Windows executable at `C:\Users\Darshan\AppData\Local\Programs\Ollama\ollama.exe`.
- These notes are added so the project documentation matches the current repository state.

## Function Call Chain

```python
# MAIN ORCHESTRATION
main.py::main()
  ├─ news_fetcher.fetch_latest_article()
  │  └─ feedparser.parse(RSS_FEED_URL)
  │
  ├─ script_generator.summarise(article_text)
  │  ├─ spacy.nlp(text)
  │  ├─ detect_context(doc)
  │  ├─ generate_hook(doc, context)
  │  ├─ build_story(doc)
  │  ├─ generate_ending(context)
  │  └─ _trim_script(script, max_words)
  │
  ├─ scene_planner.plan_scenes(script)
  │  ├─ extract_context_entities(script)  # NER
  │  ├─ calculate_scene_count(script)
  │  ├─ _strict_chunk_sentence(sent)       # Break long sentences
  │  └─ _detect_scene_type(scene_text)
  │
  ├─ For each scene:
  │  ├─ image_fetcher.fetch_image(scene, idx)
  │  │  ├─ _build_semantic_query(scene)
  │  │  ├─ _build_query(scene)  # ranked list
  │  │  ├─ _pexels_image_url(query)  # API call
  │  │  │  └─ requests.get(PEXELS_SEARCH)
  │  │  └─ _download(url, path)
  │  │     └─ urllib.request.urlopen()
  │  │
  │  └─ voice_generator.generate_audio(text, idx)
  │     ├─ _check_piper()
  │     └─ subprocess.run([PIPER_EXECUTABLE, ...])
  │        └─ piper.exe (binary)
  │
  └─ video_builder.build_video(scenes)
     ├─ For each scene:
     │  ├─ _make_background(image_path, W, H)
     │  ├─ _make_gradient_overlay(W, H)
     │  ├─ _make_breaking_news_banner() [scene 0]
     │  ├─ _make_progressive_caption(text, duration)
     │  └─ _make_lower_third(headline, source, loc)
     │
     ├─ AudioFileClip(scene["audio_path"])
     ├─ CompositeVideoClip([layers])
     ├─ concatenate_videoclips(scene_clips)
     └─ write_videofile(OUTPUT_VIDEO)
```

## Data Flow Between Modules

```
Article Data Flow:
  article (dict) → script (str) → scenes (list[dict]) → enriched scenes
  
  Where enriched scenes add:
    + image_path (from image_fetcher)
    + audio_path (from voice_generator)
    + headline, news_source (from main.py)

Config Usage:
  All modules read from config.py:
    - news_fetcher → RSS_FEED_URL
    - script_generator → NUM_SENTENCES (rarely used, dynamic instead)
    - scene_planner → (no direct, uses config via other modules)
    - image_fetcher → IMAGE_DIR, WIKI_API, WIKI_HEADERS
    - voice_generator → PIPER_EXECUTABLE, PIPER_MODEL, AUDIO_DIR
    - video_builder → VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, OUTPUT_VIDEO

Asset Directories:
  - output/audio/ ← voice_generator writes
  - output/images/ ← image_fetcher writes
  - output/news_video.mp4 ← video_builder writes
```

---

# 7. EXECUTION PROCESS (STEP-BY-STEP)

## What Happens When You Run: `python main.py`

### **Step 0: Environment Initialization**

```python
print("[ENV] Python:", sys.executable)
print("[ENV] Python Version:", sys.version)

# Output:
# [ENV] Python: C:\...\AI_NEWs_GENERATOR\.venv\Scripts\python.exe
# [ENV] Python Version: 3.12.0 (main, Oct 2 2023, ...)
```

**Actions:**
- Print Python executable path (for debugging)
- Print Python version
- Add current directory to `sys.path` for module imports
- Generate unique RUN ID (UUID4 prefix)

### **Step 1: Output Directory Reset (Force Fresh Run)**

```python
OUTPUT_DIR = "output"
if os.path.exists(OUTPUT_DIR):
  shutil.rmtree(OUTPUT_DIR)  # DELETE entire directory

os.makedirs(os.path.join(OUTPUT_DIR, "audio"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "images"), exist_ok=True)

# Output:
# [SYSTEM] Output directory reset — fresh run enabled
```

**Rationale:**
- Prevents stale audio/images from previous runs
- Ensures clean state for new pipeline execution
- Avoids cache mismatches between script & audio

### **Step 2: Fetch Latest BBC News**

```python
article = fetch_latest_article()
# Calls: feedparser.parse("https://feeds.bbci.co.uk/news/rss.xml")

# Output:
# [NewsFetcher] Fetching feed: https://feeds.bbci.co.uk/news/rss.xml
# [NewsFetcher] Article: "Ukraine Hits Russian Supply Lines..."

# Returns:
article = {
  "title": "Ukraine Hits Russian Supply Lines in Donetsk",
  "summary": "Ukrainian forces have attacked...",
  "link": "https://bbc.com/news/world-europe-..."
}
```

**Error Cases:**
- Feed unreachable → Raises `RuntimeError`
- No entries in feed → Raises `RuntimeError`
- Parse error → Logged, but continues if entries exist

### **Step 3: Generate News Script**

```python
full_text = f"""
TITLE: {article['title']}
SUMMARY: {article['summary']}
TASK: Explain this news clearly...
"""

script = summarise(full_text)

# Output:
# [2/5] Generating script...
# [ScriptGen] Context detected: 'war'
# [ScriptGen] Hook: "This just happened and it's raising serious concerns."
# [ScriptGen] Body sentences: 4
# [ScriptGen] Final → 82 words ≈ 37s | 7 scenes | context='war'
# Script preview: "This just happened and it's raising serious concerns..."

# Returns:
script = "This just happened and it's raising serious concerns. Ukraine's military struck Russian supply lines in eastern Donetsk. The attack targeted ammunition depots and logistics hubs. Ukrainian officials confirm the operation was successful. NATO analysts say this disrupts Moscow's offensive capabilities. More updates are expected soon."
```

**Internal Steps (in script_generator.summarise):**

```python
1. Load spaCy model (en_core_web_sm)
2. Parse text through NLP pipeline
3. Detect context: extract keywords, check tense neutralisers
   → Result: "war"
4. Generate hook:
   - Select highest-scoring sentence from doc
   - Prefix with context-matched opener
   → "This just happened and it's raising serious concerns. Ukraine's military struck..."
5. Build body: score sentences by frequency + NER
   → Extract 4–6 top sentences
6. Generate ending: context-matched closer
   → "More updates are expected soon."
7. Trim to target word count (70–120 words for 30–55s video)
8. Validate: strong opening, no weak sentences
9. Return final script
```

### **Step 4: Plan Scenes**

```python
scenes = plan_scenes(script)

# Output:
# [3/5] Planning scenes...
# [ScenePlanner] Detected context: PERSON=['Zelensky'], ORG=['NATO'], LOC=['Donetsk', 'Ukraine']
# [ScenePlanner] Country context: 'Ukraine'
# [ScenePlanner] 7 scenes planned:
# [ScenePlanner] Scene 0 => type='war' | keyword='Ukraine military' | TEXT="This just happened and it's raising serious concerns."...
# [ScenePlanner] Scene 1 => type='war' | keyword='military attack' | TEXT="Ukraine's military struck Russian supply lines."...
# ... (6 more scenes)

# Returns:
scenes = [
  {
    "text": "This just happened and it's raising serious concerns.",
    "keyword": "Ukraine military",
    "type": "war",
    "entities": {
      "person": "Zelensky",
      "location": "Donetsk",
      "country_context": "Ukraine",
      "all_persons": ["Zelensky"],
      "all_orgs": ["NATO"],
      "all_locations": ["Donetsk", "Ukraine"]
    }
  },
  # ... (6 more scene dicts)
]
```

**Internal Steps (in scene_planner.plan_scenes):**

```python
1. Extract named entities (PERSON, GPE, ORG, EVENT)
2. Derive country context (3-tier: GPE → ORG → PERSON)
3. Calculate scene count: duration / 5 seconds per scene
   → ~7–8 scenes for typical script
4. Split script into chunks:
   - Try sentence boundaries
   - For long sentences: call _strict_chunk_sentence()
     (break at conjunctions, commas, or 50% midpoint)
   - Merge short chunks (<8 words)
5. For each chunk:
   - Extract keyword (top 3–4 meaningful words)
   - Detect scene type (war | politics | tech | etc.)
   - Store extracted entities
6. Return list of scene dicts
```

### **Step 5: Inject Metadata**

```python
news_source = "BBC News"
for scene in scenes:
  scene["headline"] = article["title"]
  scene["news_source"] = news_source

# Now each scene has:
# {
#   "text": "...",
#   "keyword": "...",
#   "type": "...",
#   "entities": {...},
#   "headline": "Ukraine Hits Russian Supply Lines...",
#   "news_source": "BBC News"
# }
```

### **Step 6: Fetch Images & Generate Audio**

```python
# Output:
# [4/5] Fetching images and generating audio...

for idx, scene in enumerate(scenes):
  # FETCH IMAGE
  scene["image_path"] = fetch_image(scene, idx)
  # Output: [ImageFetcher] Pexels found 'Ukraine military war...' → [URL]
  #         [ImageFetcher] Saved 450 KB → output/images/scene_00.jpg
  
  # GENERATE AUDIO
  scene["audio_path"] = generate_audio(scene["text"], idx)
  # Output: [VoiceGen] Generating audio for scene 0...
  #         [VoiceGen] Audio saved → output/audio/scene_00_a1b2c3d4.wav
```

**For Each Scene (parallel processing):**

```
Image Fetching Algorithm:
  1. Build semantic query from scene text
  2. Build ranked list of backup queries
  3. Try Pexels API:
     - Query: "Ukraine military war news realistic photo"
     - Params: orientation=portrait, per_page=5
     - Parse response, get first acceptable URL
  4. If Pexels fails → try Wikipedia
  5. If Wikipedia fails → use dark fallback (no image_path set)
  6. Download image to output/images/scene_XX.jpg
  7. Validate file (>2 KB, not error page)
  8. Return path

Audio Generation Algorithm:
  1. Check Piper executable exists
  2. Check model file exists
  3. Generate unique WAV filename (scene_XX_HASH)
  4. Delete if cached (force regeneration)
  5. Execute: echo "[text]" | piper --model [...] --output_file [wav]
  6. Capture stdout/stderr
  7. Validate output file (>1 KB)
  8. Return path
```

### **Step 7: Pre-Render Validation**

```python
# Output:
# [VALIDATE] Running pre-render scene checks...

for idx, scene in enumerate(scenes):
  issues = []
  if not scene.get("text", "").strip():
    issues.append("empty text")
  if not scene.get("audio_path") or not os.path.isfile(scene["audio_path"]):
    issues.append("missing audio")
  if not scene.get("image_path") or not os.path.isfile(scene["image_path"]):
    issues.append("no image — dark fallback will be used")
  
  if issues:
    print(f"[VALIDATE] Scene {idx:02d} warnings: {', '.join(issues)}")
  else:
    print(f"[VALIDATE] Scene {idx:02d} OK")

# Output:
# [VALIDATE] Scene 00 OK
# [VALIDATE] Scene 01 OK
# [VALIDATE] Scene 02 warnings: no image — dark fallback will be used
# [VALIDATE] 7 scenes ready for render
```

**Purpose:**
- Catch missing assets before video build (fail-fast)
- Log which scenes will use fallbacks
- Ensure audio is always present (critical)

### **Step 8: Build Video**

```python
# Output:
# [5/5] Building video...

output_path = build_video(scenes)

# Output:
# [VideoBuilder] Building video (7 scenes, 1080×1920)...
# [VideoBuilder] Scene 0 — 4.8s | audio=Y | image=Y | [BREAKING NEWS BANNER]
# [VideoBuilder] Scene 1 — 5.2s | audio=Y | image=Y
# [VideoBuilder] Scene 2 — 4.9s | audio=Y | image=N | [DARK FALLBACK]
# [VideoBuilder] Scene 3 — 5.1s | audio=Y | image=Y
# [VideoBuilder] Scene 4 — 5.0s | audio=Y | image=Y
# [VideoBuilder] Scene 5 — 4.7s | audio=Y | image=Y
# [VideoBuilder] Scene 6 — 4.3s | audio=Y | image=Y
# [VideoBuilder] Rendering MP4... (may take 30–90 seconds)
# [VideoBuilder] [DONE] Total video: 34.0s
# [SUCCESS] Video created: output/news_video.mp4
```

**Internal Steps (in video_builder.build_video):**

```python
1. For each scene:
   a) Load background image (or use dark fill)
   b) Create gradient overlay (transparent top → 85% black bottom)
   c) Create breaking news banner (if scene 0)
   d) Create progressive captions (word-by-word)
   e) Create lower-third crawl (headline, source, location)
   f) Load audio file, get duration
   g) Stack all layers using CompositeVideoClip
   h) Set clip duration = audio duration
   i) Attach audio track to video clip

2. Concatenate all scene clips into single video clip

3. Render to MP4:
   - Codec: H.264
   - Resolution: 1080×1920
   - FPS: 24
   - Quality: High (default FFmpeg preset)
   - Duration: Sum of all scene durations

4. Close all clip objects

5. Return output file path
```

### **Step 9: Final Success Report**

```python
# Output:
# ============================================================
#   AI News-to-Video Generator
# ============================================================
#
# [SUCCESS] Video created: output/news_video.mp4
#
# ============================================================
```

**If Error:**
```python
# Output:
# ============================================================
#   AI News-to-Video Generator
# ============================================================
#
# [ERROR] Video build failed: [error description]
#
# ============================================================
# [Exception traceback]
```

---

# 8. OUTPUT SYSTEM

## Directory Structure

```
output/                           # Auto-created by config.py
├── audio/                        # Scene audio files
│   ├── scene_00_a1b2c3d4.wav     # Scene 0 (4.8 seconds)
│   ├── scene_01_e5f6g7h8.wav     # Scene 1 (5.2 seconds)
│   └── scene_XX_HASH.wav         # Pattern: scene_[idx:2d]_[MD5:8].wav
│
├── images/                       # Scene background images
│   ├── scene_00.jpg              # Scene 0 image
│   ├── scene_01.jpg              # Scene 1 image
│   └── scene_XX.jpg              # Pattern: scene_[idx:2d].jpg
│
├── news_video.mp4 ⭐             # FINAL OUTPUT VIDEO
├── news_video_ambient.wav        # Temporary (not used in Phase 4)
└── news_video_tmp_audio.m4a      # Temporary (cleanup on next run)
```

## File Naming Conventions

### Audio Files

```
Pattern: scene_[IDX:02d]_[HASH:8].wav

Example: scene_00_a1b2c3d4.wav

Where:
  - IDX = Scene index (0-padded to 2 digits)
    scene_00, scene_01, ..., scene_12
  - HASH = First 8 chars of MD5(scene_text)
    Ensures same text always generates same filename
    (though file is always regenerated due to force_refresh)
```

### Image Files

```
Pattern: scene_[IDX:02d].jpg

Example: scene_00.jpg, scene_01.jpg, ...

Where:
  - IDX = Scene index (0-padded to 2 digits)
  - Format: JPEG (lossy, ~400–600 KB typical)
  - Orientation: Portrait (9:16)
  - Resolution: Variable (Pexels originals, then letterboxed/cropped)
```

### Final Video

```
Path: output/news_video.mp4

Fixed name (no timestamp):
  - Overwritten on each run
  - Enables simple scripting (always know output path)
  - Suitable for CI/CD pipelines
  - User must manually back up if keeping multiple runs

Specifications:
  - Codec: H.264 (AVC)
  - Container: MP4
  - Resolution: 1080×1920 (9:16 vertical)
  - Frame rate: 24 fps
  - Audio: AAC, 48 kHz, Mono (embedded)
  - Duration: 45–55 seconds (varies by article length)
  - File size: ~30–50 MB (typical, depends on image complexity)
  - Quality: High (suitable for social media)
```

## Video Composition

### Scene Duration Calculation

```python
For each scene:
  1. Load audio WAV file
  2. Read duration from WAV header (moviepy.AudioFileClip.duration)
  3. Use this as scene_duration (not 5-second fallback)
  4. Create video clip with exact duration
  5. Sync caption display to this duration

Final video duration:
  = SUM(all scene durations)
  = typically 45–55 seconds
```

### Frame Composition (Per-Frame Rendering)

**Layer Order (bottom to top):**

```
1. BASE LAYER
   └─ Image (RGB, 1080×1920)
      OR Dark fill if missing

2. GRADIENT OVERLAY
   └─ Transparent to 85% black (RGBA)
      Covers lower 55% of frame

3. BREAKING NEWS BANNER (Scene 0 Only)
   └─ Red bar with "BREAKING NEWS | LIVE"
      Height: 72 px
      Position: Top of frame

4. LOWER-THIRD CRAWL
   └─ Headline | Source | Location
      Height: 110 px
      Position: Above brand bar

5. PROGRESSIVE CAPTIONS
   └─ Words fade in gradually
      Rendered word-by-word based on time
      Last 12 words shown, current word highlighted

6. BRANDING BAR
   └─ "AI NEWS" logo (bottom)
      Height: 90 px
```

## Output Characteristics

### Video Quality

| Aspect | Value | Notes |
|--------|-------|-------|
| Bitrate | Auto (default) | ~2–4 Mbps for H.264 |
| Quality | High | Suitable for Instagram/TikTok |
| Artifacts | Minimal | Smooth motion, no compression blocks |
| Color | 8-bit RGB | Full gamut |

### Caption Quality

- **Font:** Arial (or system sans-serif)
- **Size:** 48 pt (readable on mobile, not oversized)
- **Color:** White + Yellow highlight
- **Background:** Dark pill-shaped card (75% opacity)
- **Word timing:** Proportional to word length

### Audio Quality

- **Sample rate:** 22,050 Hz (standard for speech TTS)
- **Channels:** Mono (sufficient for narration)
- **Bit depth:** 16-bit PCM
- **Codec (in MP4):** AAC (24–32 kbps, compressed)
- **Loudness:** Normalized by MoviePy

---

# 9. CURRENT LIMITATIONS & ISSUES

## Known Limitations

### 1. **Image Relevance Issues**

**Problem:** 
- Pexels queries sometimes return generic or partially relevant images
- Semantic query builder may not capture nuanced context
- "News realistic photo" suffix helps but is not perfect

**Example:**
```
Query: "military conflict news realistic photo"
Returned: (sometimes) generic soldiers, not the specific conflict
```

**Impact:** Medium (images are visible but may not match perfectly)

**Root Cause:**
- Pexels API is keyword-based (not vision-AI driven)
- No real-time news image corpus
- Query builder is rule-based, not neural

---

### 2. **Voice Lacks Human-Like Modulation**

**Problem:**
- Piper TTS produces clear but monotone speech
- No emphasis, pausing, or emotional inflection
- All sentences read at same pace/tone
- Single voice (no variation)

**Example:**
```
"This is a serious situation" 
→ reads as neutral statement (no gravity)

Should emphasize: THIS is SERIOUS
```

**Impact:** Medium (professionalism reduced, but content clear)

**Root Cause:**
- Piper uses fixed voice model (no SSML control)
- Neural TTS is improving but still pre-computed
- Would need custom model training for per-sentence emotion

---

### 3. **Scene Pacing Inconsistency**

**Problem:**
- Scenes vary in length (4–6 seconds)
- No visual pacing consistency
- Some scenes feel rushed, others slow
- No scene transitions or connective flow

**Example:**
```
Scene 1: 4.2 seconds (feels rushed)
Scene 2: 5.8 seconds (feels slow)
Scene 3: 4.5 seconds (rushed again)
```

**Impact:** Medium (viewer experience less smooth)

**Root Cause:**
- Audio duration drives scene length
- Piper TTS has variable speech rate
- No post-processing to normalize duration

**Workaround:**
- Could add minimum scene duration (extend silence)
- Could re-record audio at fixed pace
- Could add visual transitions

---

### 4. **Context Not Always Clear in First Line**

**Problem:**
- Hook may not immediately establish what news is about
- First line sometimes generic ("This just happened...")
- Viewer may miss context before first scene plays

**Example:**
```
Hook: "This just happened and it's raising serious concerns."
↓ (no additional context until scene 2)
Reader doesn't know: WHO, WHERE, WHAT

Better: "Ukraine hit Russian supply lines in Donetsk today."
```

**Impact:** Low (context clarifies in subsequent sentences)

**Root Cause:**
- Hook generation prioritizes *attention-grabbing* over *information*
- NER extraction may fail for novel entities
- Space constraints (hook ≤12 words)

**Fix in Phase 5:**
- Enforce WHO/WHERE/WHAT in first line validation
- Increase hook word limit to 15 words
- Add country context to hook prefix

---

### 5. **Fallback Images (Dark Scenes)**

**Problem:**
- ~10–15% of scenes fall back to dark blue-grey background
- Makes video appear unfinished
- Pexels sometimes has no results for niche queries

**Example:**
```
Scene: "NATO coordination discussed in Geneva"
Pexels query: "NATO coordination Geneva news realistic photo"
Result: No matching images
Fallback: Dark screen
```

**Impact:** Low-Medium (visual quality reduced)

**Root Cause:**
- Query specificity too high
- Pexels doesn't index all events
- Wikipedia fallback sometimes empty

**Mitigations:**
- Current: Dark fallback still renders captions/overlay
- Could: Broaden queries (NATO → government meeting)
- Could: Use public domain image library (Unsplash)

---

### 6. **No Real-Time News Footage**

**Problem:**
- Uses still images + TTS only
- No actual video clips from events
- Feels static compared to news broadcasts

**Example:**
```
Story: "Ukraine counteroffensive underway"
Current: Static image of Ukraine map + voice narration
Ideal: Video clip of actual combat/troop movement
```

**Impact:** Medium (acceptable for short-form, not broadcast-quality)

**Root Cause:**
- No source for free news video clips
- Rights/licensing issues complex
- Would require video compositing (higher complexity)

**Not Planned:** Complex integration, low priority for Phase 4

---

### 7. **Caption Text Overflow Risk**

**Problem:**
- Long words or scene text can overflow text card
- No automatic word wrapping if font is too large
- Captions on very small screens may be hard to read

**Example:**
```
Text: "Unprecedented military mobilization across..."
On mobile: Text overflows pill background
```

**Impact:** Low (rare, mostly on edge cases)

**Root Cause:**
- Fixed font size (48 pt) for consistency
- Pill width calculated from text length
- No adaptive sizing

**Mitigation:** Phase 4 validates captions ≤12 words per scene

---

### 8. **Piper Audio Quality Variability**

**Problem:**
- TTS quality varies by sentence structure
- Punctuation handling not perfect
- Some words pronounced incorrectly (named entities)

**Example:**
```
"Kyiv" → pronounced "Key-EV" (correct)
"Putin" → pronounced "POO-tin" (correct)
But: "Zelensky" → sometimes mispronounced

Proper nouns: No way to force pronunciation
```

**Impact:** Low (mostly fine, occasional pronunciation errors)

**Root Cause:**
- Piper is English-general TTS
- No named entity pronunciation dictionary
- Would need custom phoneme markup (SSML)

---

### 9. **External Dependency: Pexels API**

**Problem:**
- Rate limited (200 requests/hour)
- Requires API key
- Internet required (not fully offline)
- Pexels could change API or require subscription

**Example:**
```
If Pexels API down:
  → All scenes fall back to dark backgrounds
  → Video still renders, but visually poor
```

**Impact:** Medium (mitigated by Wikipedia fallback)

**Mitigation:**
- Fallback to Wikipedia when Pexels rate-limited
- Dark fallback when both fail
- Could add local image library (not implemented)

---

### 10. **spaCy NER Occasionally Unreliable**

**Problem:**
- Named entity extraction sometimes misses entities
- False positives (labels random words as entities)
- Especially poor for novel/brand names

**Example:**
```
Article: "New Ukrainian drone called Osprey debuts"
Expected NER: PERSON=[..], ORG=[..], DEVICE=[Osprey]
Actual NER: Misses "Osprey" entirely
```

**Impact:** Low (affects image query quality, not core function)

**Root Cause:**
- spaCy trained on older news corpus
- New entities underrepresented
- Would need fine-tuned model

---

## Design Flaws

### 1. **No User Configuration UI**

**Issue:** Config is hardcoded in `config.py`
- Users must edit Python file to change parameters
- Error-prone (syntax mistakes break pipeline)

**Solution (Phase 5):** Config file (YAML/JSON) or CLI args

### 2. **Force Clean Output Directory**

**Issue:** Every run deletes output/
- No way to preserve previous videos without manual backup
- Accidents lose work

**Solution (Phase 5):** Option to preserve, version outputs with timestamps

### 3. **Limited Error Messages**

**Issue:** Some errors give generic messages
- User unsure what went wrong
- Difficult to debug

**Solution:** Phase 4 improved validation messages

---

# 10. IMPROVEMENT SUGGESTIONS

## Phase 5 Enhancements

### 1. **Implement Audio Emphasis Markup**

**Objective:** Add emotional emphasis to speech

**Approach:**
- Use SSML (Speech Synthesis Markup Language)
- Tag key phrases: `<emphasis level="strong">` around important words
- Increase speech rate for exciting news
- Decrease for serious news

**Example:**
```xml
This just happened and <emphasis level="strong">it's raising serious 
concerns</emphasis>. Ukraine's military <emphasis level="moderate">struck 
Russian supply lines</emphasis> in eastern Donetsk.
```

**Impact:** High (makes narration feel more natural)

**Effort:** Medium (Piper supports SSML, need to generate markup)

---

### 2. **Scene Duration Normalization**

**Objective:** Make all scenes roughly equal length (4–5 seconds)

**Approach:**
- Measure audio duration per scene
- Add silent padding if <4 seconds
- Break long scenes if >5 seconds into multiple scenes

**Example:**
```python
for scene in scenes:
  duration = get_audio_duration(scene["audio_path"])
  if duration < 4.0:
    # Pad with 0.5s silence
    extend_audio(scene["audio_path"], 0.5)
  elif duration > 5.5:
    # Split into two scenes
    split_scene(scene)
```

**Impact:** Medium (smoother viewing experience)

**Effort:** Medium (audio processing needed)

---

### 3. **Smart Image Selection (Vision AI)**

**Objective:** Use vision model to rank images by relevance

**Approach:**
- For each query, fetch top 10 images from Pexels
- Use CLIP or similar to score relevance to scene text
- Pick highest-scoring image

**Example:**
```python
images = pexels_search("military attack").photos[:10]
scores = clip_score(scene_text, images)
best_image = images[scores.argmax()]
```

**Impact:** High (much better image-text alignment)

**Effort:** High (requires CLIP model, GPU)

---

### 4. **Add Video Transitions**

**Objective:** Smooth between scenes instead of hard cuts

**Approach:**
- Add fade, slide, or wipe transitions
- 0.3–0.5 second duration
- Use MoviePy video effects

**Example:**
```python
scene1_video = ...
scene2_video = ...

# Fade transition
transition = fade(scene1_video, scene2_video, duration=0.4)
```

**Impact:** Medium (feels more polished)

**Effort:** Medium (MoviePy has built-in effects)

---

### 5. **Subtitle Export (SRT Format)**

**Objective:** Generate subtitle file alongside video

**Approach:**
- Export scene timings and text as SRT
- Users can upload video + SRT to platforms

**Example:**
```srt
1
00:00:00,000 --> 00:00:04,800
This just happened and it's raising serious concerns.

2
00:00:04,800 --> 00:00:10,000
Ukraine's military struck Russian supply lines in eastern Donetsk.
```

**Impact:** Medium (improves accessibility)

**Effort:** Low (just need to write SRT format)

---

### 6. **Multi-Language Support**

**Objective:** Generate videos in different languages

**Approach:**
- Fetch articles in multiple languages (expand RSS)
- Use spaCy multilingual models
- Use Piper with different language models (30+ available)

**Example:**
```bash
python main.py --language es  # Spanish
python main.py --language fr  # French
python main.py --language de  # German
```

**Impact:** High (expands audience)

**Effort:** High (complex language handling)

---

### 7. **Hashtag & Tagging System**

**Objective:** Generate platform-specific hashtags & metadata

**Approach:**
- Extract keywords from context
- Generate trending hashtags for topic
- Output metadata JSON for platforms

**Example:**
```json
{
  "hashtags": ["#UkraineWar", "#Breaking", "#RealNews"],
  "topics": ["war", "Ukraine", "Russia"],
  "sentiment": "negative",
  "duration": "51.2s"
}
```

**Impact:** Medium (helps discoverability)

**Effort:** Medium (need hashtag database or API)

---

### 8. **Configurable Branding**

**Objective:** Allow users to customize logo, colors, fonts

**Approach:**
- Move to config file:
```yaml
branding:
  name: "AI NEWS"
  accent_color: [220, 50, 50]  # RGB
  font: "Arial"
  position: "bottom"
```

**Example:**
```bash
python main.py --config my_branding.yaml
```

**Impact:** Low (nice-to-have)

**Effort:** Low (just refactor config)

---

### 9. **Batch Processing Mode**

**Objective:** Process multiple articles in one run

**Approach:**
- Fetch top 5 BBC news articles
- Generate video for each
- Output: video_001.mp4, video_002.mp4, ...

**Example:**
```bash
python main.py --batch 5
```

**Impact:** High (productivity boost)

**Effort:** Medium (loop main pipeline, manage outputs)

---

### 10. **Cloud Deployment (Optional)**

**Objective:** Run on cloud infrastructure (AWS Lambda, etc.)

**Approach:**
- Containerize (Docker)
- Deploy to serverless
- Trigger via API call
- Return video URL

**Example:**
```bash
curl -X POST https://api.example.com/generate \
  -d '{"article_url": "https://bbc.com/news/..."}' \
  → Response: "https://cdn.example.com/output.mp4"
```

**Impact:** High (scalability)

**Effort:** Very High (Docker, Lambda, CDN, etc.)

---

## Performance Optimizations

### 1. **Parallel Image/Audio Fetching**

**Current:** Sequential (image then audio per scene)

**Optimization:** Use `concurrent.futures` or `asyncio`

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
  image_futures = [executor.submit(fetch_image, s, i) for i, s in enumerate(scenes)]
  audio_futures = [executor.submit(generate_audio, s["text"], i) for i, s in enumerate(scenes)]
  
  for i, (img_f, aud_f) in enumerate(zip(image_futures, audio_futures)):
    scenes[i]["image_path"] = img_f.result()
    scenes[i]["audio_path"] = aud_f.result()
```

**Impact:** 3–4x faster (from ~60s to ~20s)

**Effort:** Low (straightforward threading)

---

### 2. **GPU Video Rendering**

**Current:** CPU rendering via FFmpeg

**Optimization:** Use NVIDIA CUDA or Apple Metal

```python
# Requires: moviepy with GPU backend, OR
# ffmpeg compiled with hwaccel (h264_nvenc)
output_path = build_video(
  scenes,
  hwaccel='nvenc'  # NVIDIA GPU
)
```

**Impact:** 5–10x faster rendering (from ~60s to ~10s)

**Effort:** High (GPU setup, driver issues)

---

### 3. **Image Caching (FULLY IMPLEMENTED IN PHASE 20)**

**Implementation:** 
An MD5-hash cache lock checks if `output/images/cache_[query_hash].jpg` exists and is valid (>10KB) before making any network API calls. Similarly, a local Map cache lock skips Nominatim and CartoDB base tile geocoding if `map_stinger.jpg` is compiled for the current run.

**Impact:** Bypasses geocoding bans and Pexels rate limits entirely, cutting generation times on re-runs down to <1 second for asset acquisition.

---

## Architecture Improvements

### 1. **Dependency Injection**

**Current:** Hard imports in each module

```python
# Fragile
from config import PIPER_EXECUTABLE
```

**Better:**
```python
class AudioGenerator:
  def __init__(self, piper_path, model_path):
    self.piper = piper_path
    self.model = model_path
  
  def generate_audio(self, text):
    # Use self.piper, self.model
```

**Benefit:** Easier testing, swappable implementations

---

### 2. **Pipeline as DAG (Directed Acyclic Graph)**

**Current:** Sequential, linear flow

```python
result = main()  # All steps hardcoded
```

**Better:** Declarative DAG

```python
pipeline = Pipeline([
  Step("fetch_news", fetch_latest_article),
  Step("generate_script", summarise, depends_on="fetch_news"),
  Step("plan_scenes", plan_scenes, depends_on="generate_script"),
  Step("fetch_assets", fetch_image, depends_on="plan_scenes"),
  Step("build_video", build_video, depends_on="fetch_assets"),
])

result = pipeline.run()
```

**Benefit:** Reusable, can skip steps, parallelize

---

### 3. **Logging Instead of Print**

**Current:** `print()` statements throughout

```python
print("[VoiceGen] Audio saved -> ...")
```

**Better:** Python `logging` module

```python
import logging
logger = logging.getLogger("voice_generator")
logger.info("Audio saved -> ...")

# User controls verbosity:
logging.basicConfig(level=logging.DEBUG)  # Verbose
logging.basicConfig(level=logging.ERROR)   # Quiet
```

**Benefit:** Professional, configurable, structured

---

# 11. IMPORTANT GITHUB NOTE

## Large File Warning

**File:** `piper/en_US-lessac-medium.onnx`  
**Size:** 60.27 MB  
**GitHub Limit:** 50 MB recommended  
**Status:** ⚠️ Exceeds recommendation

### What This Means

- ✅ File is already pushed to GitHub
- ✅ Repository works correctly
- ✅ File is downloadable & usable
- ⚠️ GitHub warning shown (no action needed)
- ℹ️ May be slower to clone due to size

### Optional Solution: Git LFS (Large File Storage)

**If you want to clean this up:**

```bash
# 1. Install Git LFS
# Ubuntu/Debian:
sudo apt-get install git-lfs

# macOS:
brew install git-lfs

# Windows:
# Download from https://git-lfs.github.com/

# 2. Configure LFS for this file
git lfs track "piper/en_US-lessac-medium.onnx"

# 3. Commit the .gitattributes change
git add .gitattributes
git commit -m "Add LFS tracking for Piper model"

# 4. Force push
git push origin main --force
```

**Result:** File stored on LFS server, smaller clone

### Keep as-is (Recommended for Now)

**Advantages:**
- No extra setup needed
- Works on all machines immediately
- No LFS credentials required
- Single-file project doesn't benefit much

**Your project is live and working perfectly!** 🚀

---

## Summary

This **AI News-to-Video Generator** is a sophisticated, end-to-end automation pipeline that:

✅ **Fully automated** — news to video in <5 minutes  
✅ **AI-powered** — script generation, scene planning, voice synthesis  
✅ **Offline-capable** — minimal cloud dependencies (only image/news fetching)  
✅ **Production-ready** — outputs publication-quality videos  
✅ **Extensible** — modular design for future enhancements  

**Current Status:** Phase 4 (Stability & Realism)

**Next Steps:** Performance optimization, visual improvements, multi-language support

---

**END OF DOCUMENT**

---

*For questions or contributions,  see: https://github.com/Sahil-FS/automated_news_report*
