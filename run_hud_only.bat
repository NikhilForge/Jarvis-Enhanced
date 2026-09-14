@echo off
call .venv\Scripts\activate 2>nul
pip install fastapi uvicorn pyyaml >nul 2>&1
start "" http://127.0.0.1:8765
python main.py --hud
