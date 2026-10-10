# PowerShell script to execute the Video Generation Pipeline
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PythonExe = Join-Path $ScriptDir "automated_news_report\.venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment not found at automated_news_report\.venv" -ForegroundColor Red
    Write-Host "Please follow SETUP.md to create your environment." -ForegroundColor Yellow
    exit 1
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "[WARN] FFmpeg was not detected on your system PATH!" -ForegroundColor Yellow
    Write-Host "Install via: winget install Gyan.FFmpeg" -ForegroundColor Gray
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[WARN] Ollama was not detected on your system PATH!" -ForegroundColor Yellow
    Write-Host "Pipeline will use extractive spaCy fallback if Ollama is offline." -ForegroundColor Gray
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  News Forge AI - Running Pipeline" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

& $PythonExe (Join-Path $ScriptDir "automated_news_report\main.py") @args
