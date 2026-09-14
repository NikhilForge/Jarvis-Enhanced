@echo off
REM JARVIS-6 launcher for Windows 11
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  pip install --upgrade pip
  pip install -r requirements.txt
  echo Installing Chromium for browser automation...
  python -m playwright install chromium
) else (
  call .venv\Scripts\activate
)
REM openWakeWord does not always bundle pretrained model files with the pip package.
REM Download the Hey Jarvis ONNX model once before starting the assistant.
python -c "from openwakeword import utils; utils.download_models(['hey_jarvis'])"
if errorlevel 1 (
  echo Failed to download the Hey Jarvis wake-word model.
  pause
  exit /b 1
)

if not exist models\kokoro-v1.0.onnx (
  echo Downloading Kokoro-82M ...
  curl -L -o models\kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
  curl -L -o models\voices-v1.0.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
)
if not exist data\voiceprint.json (
  echo No voiceprint found. Enrolling your voice ^(20 seconds^)...
  python scripts\enroll_voice.py
)
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo IMPORTANT: edit .env and paste your Gemini API key into GEMINI_API_KEY.
  echo Then run this file again.
  pause
  exit /b 1
)
findstr /B "GEMINI_API_KEY=" .env >nul
if errorlevel 1 (
  echo GEMINI_API_KEY is missing from .env
  pause
  exit /b 1
)
start "" http://127.0.0.1:8765
python main.py %*
