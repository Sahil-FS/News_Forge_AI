# PowerShell script to start the Operator UI server
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PythonExe = Join-Path $ScriptDir "automated_news_report\.venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Virtual environment not found at automated_news_report\.venv" -ForegroundColor Red
    Write-Host "Please follow SETUP.md to create your environment." -ForegroundColor Yellow
    exit 1
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  News Forge AI - Operator Web UI Dashboard" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "[INFO] Starting Web UI on http://localhost:8088" -ForegroundColor Green
Write-Host "[INFO] Press Ctrl+C to stop the server." -ForegroundColor Gray

& $PythonExe (Join-Path $ScriptDir "automated_news_report\ui_server.py") @args
