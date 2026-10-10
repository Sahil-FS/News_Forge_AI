# Complete New-Device Setup & Deployment Guide: News Forge AI

This guide walks you through setting up and running **News Forge AI (Automated News Report)** from scratch on a new computer (such as a Windows 11 machine with an AMD Ryzen 7, 16 GB RAM, and an NVIDIA RTX GPU).

---

## 1. System Requirements & Compatibility

| Component | Minimum Specification | Recommended (Your Setup) |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 64-bit | Windows 11 64-bit |
| **Processor (CPU)** | 4-Core x86_64 CPU | AMD Ryzen 7 (8-Core / 16-Thread) |
| **System Memory (RAM)**| 8 GB | 16 GB DDR4/DDR5 |
| **Graphics (GPU)** | Integrated CPU graphics | **NVIDIA RTX GPU** (CUDA Acceleration) |
| **Free Storage** | 15 GB free disk space | 30 GB+ SSD space |
| **Network** | Broadband internet | Broadband (for RSS, stock media, and model downloads) |

---

## 2. Required External Software & Downloads

Before installing Python dependencies, install the following tools:

### A. Git
- **Download:** [https://git-scm.com/download/win](https://git-scm.com/download/win)
- **Winget Command:**
  ```powershell
  winget install --id Git.Git -e --source winget
  ```

### B. Python 3.12 (64-bit)
- **Version:** Python 3.12.x (Recommended: 3.12.8 or 3.12.10)
- **Important:** During installation, check the box **"Add python.exe to PATH"**.
- **Download:** [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
- **Winget Command:**
  ```powershell
  winget install --id Python.Python.3.12 -e --source winget
  ```

### C. FFmpeg (Essential for Video Rendering & Audio Normalization)
FFmpeg is used for H.264/AAC encoding, EBU R128 loudness normalization, and silence trimming.
- **Download:** [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) (Download `ffmpeg-release-essentials.zip`)
- **Winget Command (Easiest):**
  ```powershell
  winget install --id Gyan.FFmpeg -e --source winget
  ```
- **Verification:** Open a new PowerShell terminal and run:
  ```powershell
  ffmpeg -version
  ```

### D. Ollama (Local AI Model Engine)
Ollama runs the local LLM (`llama3`) for script generation. With your NVIDIA RTX GPU, Ollama will automatically accelerate inference via CUDA.
- **Download:** [https://ollama.com/download/windows](https://ollama.com/download/windows)
- **Installation:** Run the installer. Ollama will start automatically in your Windows system tray.
- **Verification:**
  ```powershell
  ollama --version
  ```

---

## 3. Step-by-Step Installation

### Step 1: Clone the Repository
Open PowerShell (or Windows Terminal) and clone the repository:

```powershell
git clone https://github.com/Sahil-FS/News_Forge_AI.git
cd News_Forge_AI
```

### Step 2: Create the Python Virtual Environment
Always run the project inside an isolated virtual environment (`.venv`):

```powershell
python -m venv automated_news_report\.venv
```

Activate the virtual environment:
```powershell
# Windows PowerShell
.\automated_news_report\.venv\Scripts\Activate.ps1
```
*(If PowerShell displays an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and retry).*

### Step 3: Install Project Dependencies
Upgrade pip and install all Python packages from `requirements.txt`:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **RTX GPU Acceleration Tip (Optional for Kokoro TTS & PyTorch):**  
> By default, standard `pip install torch` installs CPU wheels. To enable full CUDA GPU acceleration for PyTorch on your NVIDIA RTX card:
> ```powershell
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
> ```

### Step 4: Download the spaCy Language Model
Download the English NLP model used for entity recognition (NER) and script grammar parsing:

```powershell
python -m spacy download en_core_web_sm
```

### Step 5: Pull the Ollama LLM Model
Download the Llama 3 8B model into Ollama:

```powershell
ollama pull llama3
```
*Size: ~4.7 GB. On your NVIDIA RTX GPU, this will run at ~50–90 tokens/sec.*

---

## 4. Configuration & Environment Variables

### Step 1: Create your `.env` File
Copy `.env.example` to `.env`:

```powershell
# Inside the automated_news_report subfolder (or project root)
Copy-Item automated_news_report\.env.example automated_news_report\.env
```

### Step 2: Configure Environment Keys
Open `automated_news_report\.env` in an editor (e.g., VS Code or Notepad):

```powershell
notepad automated_news_report\.env
```

Key settings to review:
- **`PEXELS_API_KEY`** *(Recommended)*: Get a free key from [pexels.com/api](https://www.pexels.com/api/) to fetch HD stock b-roll and press images.
- **`UNSPLASH_ACCESS_KEY`** *(Optional)*: Secondary high-res photography source.
- **`DEBUG_MODE=true`**: Keeps full detailed logs enabled.
- **`NEWS_UI_PORT=8088`**: Port for the Operator UI server.
- **`AUTO_UPLOAD=false`**: Keep `false` until you configure YouTube credentials below.

---

## 5. Pre-Bundled Assets & Models (What's Already in the Repo)

You do **not** need to manually download the following files, as they are already tracked and included in the repository:
1. **Piper TTS Executable & DLLs:** Located in `automated_news_report/piper/` (`piper.exe`, `onnxruntime.dll`, `piper_phonemize.dll`, `espeak-ng.dll`).
2. **English Piper Voice Model:** `automated_news_report/piper/en_US-lessac-medium.onnx` + `.json` (~63 MB).
3. **Hindi Piper Voice Model:** `automated_news_report/piper/hi_IN-rohan-medium.onnx` + `.json` (~63 MB).
4. **Channel Logos & Placeholders:** Located in `automated_news_report/assets/` (`newscup_logo.png`, `logo.png`, `placeholder.jpg`).

---

## 6. Kokoro 82M TTS Setup (Primary Voice Engine)

The pipeline defaults to **Kokoro 82M**, which produces studio-quality news anchor narration.
- When you run the pipeline for the first time, Kokoro will automatically download the 82M weights (`hexgrad/Kokoro-82M`, ~330 MB) from Hugging Face into your local cache (`~/.cache/huggingface/hub/`).
- Phonemization is handled automatically on Windows via the included `espeakng-loader` package.

---

## 7. Database Initialization

The project uses an SQLite database (`db.sqlite`) to track runs, channels, RSS feeds, scheduling, and video analytics.
- **No manual migrations are needed.** The database automatically creates all tables and seeds default feeds on first run.
- To verify or manually pre-seed the database:
  ```powershell
  python -c "import sys; sys.path.insert(0, 'automated_news_report'); import db_manager; print('Database ready!')"
  ```

---

## 8. YouTube API Setup (One-Time Setup for Auto-Upload)

If you plan to use automated YouTube uploads:

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable:
   - **YouTube Data API v3**
   - **YouTube Analytics API**
   - **YouTube Reporting API**
3. Create OAuth 2.0 Client ID Credentials (Application type: **Desktop app**).
4. Download the JSON credentials and save as:
   - `automated_news_report/client_secrets_newscup.json` (for English channel), and/or
   - `automated_news_report/client_secrets_newscup_india.json` (for Hindi channel).
5. Run the one-time authentication command in your terminal:
   ```powershell
   cd automated_news_report
   python youtube_uploader.py --auth newscup
   ```
6. A browser window will open. Sign in to your Google Account and grant permissions.
7. A cached token (`token_newscup.json`) will be generated. All future uploads will run fully automatically without browser popups.

---

## 9. Running the Application

### Option A: Using the Operator Web UI (Recommended)
Double-click `run_ui.bat` or run in PowerShell:

```powershell
.\run_ui.bat
```
Then open your browser to **[http://localhost:8088](http://localhost:8088)**.  
From the dashboard you can:
- Trigger production runs for English (`newscup`) or Hindi (`newscup_india`).
- Select categories (World, Politics, Tech, Sports, Science, Business).
- Choose video format: Short-Form (9:16), Long-Form (16:9), or Both.
- Monitor real-time logs, approval stages, and video previews.

### Option B: Running the Pipeline via CLI
Double-click `run_pipeline.bat` or run directly in PowerShell:

```powershell
# Run English World News short-form video
python automated_news_report\main.py --channel newscup --category world --format short

# Run Hindi Desh news long-form video
python automated_news_report\main.py --channel newscup_india --category desh --format long

# Run dual-format production (both 9:16 vertical short and 16:9 widescreen long-form)
python automated_news_report\main.py --channel newscup --category technology --format both
```

### Option C: Batch Production Runner
To queue and generate a sequence of multiple videos scheduled across the day:

```powershell
python automated_news_report\batch_runner.py --count 6 --channel newscup --categories world,technology --ratio 4:2 --format short
```

---

## 10. Verification Checklist

Run these quick checks on the new computer to guarantee 100% operational readiness:

1. **Test Environment & Imports:**
   ```powershell
   python automated_news_report\test_imports.py
   ```
   *Expected Output: `All imports tested successfully!`*

2. **Run the Automated Test Suite:**
   ```powershell
   python -m unittest discover -s automated_news_report\tests -p "test_*.py"
   ```
   *Expected Output: `Ran 16 tests in ... OK`*

3. **Verify FFmpeg:**
   ```powershell
   ffmpeg -version
   ```

4. **Verify Ollama & Llama 3:**
   ```powershell
   ollama list
   ```
   *Should show `llama3:latest`.*

5. **Verify Kokoro TTS:**
   ```powershell
   python -c "import sys; sys.path.insert(0, 'automated_news_report'); import voice_generator; print('Kokoro Available:', voice_generator.KOKORO_AVAILABLE)"
   ```
   *Expected Output: `Kokoro Available: True`*

---

## 11. Troubleshooting Common Issues

| Issue / Error | Root Cause | Solution |
| :--- | :--- | :--- |
| `FileNotFoundError: ffmpeg not found` | FFmpeg is not installed or not in PATH | Install via `winget install Gyan.FFmpeg`, close and re-open PowerShell. |
| `Connection refused: http://localhost:11434` | Ollama service is not running | Start the Ollama app from the Windows Start menu. |
| `OSError: [E050] Can't find model 'en_core_web_sm'` | spaCy language model was not downloaded | Run `python -m spacy download en_core_web_sm`. |
| `Kokoro TTS: NOT AVAILABLE` | Missing soundfile, torch, or espeak backend | Run `pip install soundfile espeakng-loader kokoro>=0.9.4`. |
| `PEXELS_API_KEY WARNING` | Pexels API key not set in `.env` | Add key to `.env` or ignore (pipeline will fall back to DuckDuckGo/Wiki). |
| `No OAuth client secrets file found` | YouTube upload enabled without credentials | Place `client_secrets_*.json` in `automated_news_report/` or set `AUTO_UPLOAD=false` in `.env`. |
