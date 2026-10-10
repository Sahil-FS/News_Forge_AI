@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   News Forge AI - Video Generation Pipeline
echo ===================================================

cd /d "%~dp0"

set "VENV_PY=automated_news_report\.venv\Scripts\python.exe"

if not exist "!VENV_PY!" (
    echo [ERROR] Virtual environment not found at automated_news_report\.venv
    echo Please follow SETUP.md to create your virtual environment.
    pause
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [WARN] FFmpeg was not detected on your system PATH!
    echo Video building and audio normalization may fail or skip.
    echo Install via: winget install Gyan.FFmpeg
    echo.
)

where ollama >nul 2>&1
if errorlevel 1 (
    echo [WARN] Ollama was not detected on your system PATH!
    echo Pipeline will use extractive spaCy fallback instead of LLM script generation.
    echo.
)

echo [INFO] Running video production pipeline...
"!VENV_PY!" automated_news_report\main.py %*

echo.
echo Pipeline run finished.
pause
