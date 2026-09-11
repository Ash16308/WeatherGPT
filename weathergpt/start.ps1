# PowerShell Launch Script for WeatherGPT
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Starting WeatherGPT Disaster Intelligence Platform (SIH26068)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Set-Location $PSScriptRoot

Write-Host "[1/2] Checking Python dependencies..." -ForegroundColor Yellow
python -m pip install -r requirements.txt

Write-Host "[2/2] Booting FastAPI Server on http://localhost:8000..." -ForegroundColor Green
python -m uvicorn weathergpt_backend:app --host 0.0.0.0 --port 8000 --reload
