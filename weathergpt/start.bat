@echo off
echo ============================================================
echo Starting WeatherGPT Disaster Intelligence Platform (SIH26068)
echo ============================================================
cd /d "%~dp0"

echo [1/2] Checking dependencies...
python -m pip install -r requirements.txt

echo [2/2] Launching WeatherGPT Command Center on http://localhost:8000
python -m uvicorn weathergpt_backend:app --host 0.0.0.0 --port 8000 --reload

pause
