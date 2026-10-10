@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   News Forge AI - Operator UI Server Launcher
echo ===================================================

cd /d "%~dp0"

set "VENV_PY=automated_news_report\.venv\Scripts\python.exe"

if not exist "!VENV_PY!" (
    echo [ERROR] Virtual environment not found at automated_news_report\.venv
    echo Please follow SETUP.md to create your virtual environment:
    echo   python -m venv automated_news_report\.venv
    echo   automated_news_report\.venv\Scripts\pip install -r requirements.txt
    echo   automated_news_report\.venv\Scripts\python -m spacy download en_core_web_sm
    pause
    exit /b 1
)

echo [INFO] Starting Operator Web UI on port 8088...
echo [INFO] Open in your browser: http://localhost:8088
echo [INFO] Press Ctrl+C in this console to stop the server.
echo.

"!VENV_PY!" automated_news_report\ui_server.py %*

pause
