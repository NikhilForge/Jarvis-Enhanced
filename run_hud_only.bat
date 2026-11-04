@echo off
cd /d "%~dp0"
call .venv\Scripts\activate 2>nul
pip install fastapi uvicorn pyyaml >nul 2>&1

REM Free port 8765 if an old instance is stuck
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8765 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

echo Starting JARVIS HUD on http://localhost:8765 ...
timeout /t 1 /nobreak >nul
start "" http://localhost:8765
python main.py --hud
