# JARVIS Enhanced

**A powerful, always-on voice AI assistant for Windows — powered by Google Gemini, Whisper, Kokoro TTS, and Silero VAD.**

JARVIS Enhanced is a locally running Windows voice assistant designed to bring a hands-free AI experience to your desktop. It combines voice recognition, intelligent conversations, desktop automation, browser control, persistent memory, and a real-time 3D HUD.

Most of the audio pipeline runs locally on your machine. Wake-word detection, speech recognition, text-to-speech, and speaker verification remain on-device. Text-based reasoning requests are sent to the configured Gemini API.

> This repository contains enhancements and modifications to the original JARVIS project.

---

## ✨ Features

| Category | Features |
|---|---|
| 🎙️ **Wake Word Detection** | "Hey Jarvis" detection using openWakeWord, double-clap activation, and manual controls |
| 🗣️ **Speech Recognition** | faster-whisper with Silero VAD for local speech-to-text |
| 🧠 **AI Intelligence** | Google Gemini integration with configurable models, tool calling, and streaming responses |
| 🔊 **Text-to-Speech** | Kokoro ONNX neural TTS and Windows SAPI voices |
| 🛡️ **Speaker Verification** | Resemblyzer voiceprints and owner-only tool access |
| 🌐 **Browser Automation** | Playwright browser control, desktop browser launching, and YouTube automation |
| 🖥️ **Desktop Automation** | Launch applications, type text, click, execute hotkeys, capture screenshots, and analyse the screen |
| 📂 **File Management** | Local file listing, reading, writing, and opening with access restrictions |
| 🔍 **Web Search** | DuckDuckGo search and browser-based webpage reading |
| 🧩 **Persistent Memory** | Local document RAG, SQLite recall, and ChromaDB archival |
| 📅 **Proactive Assistant** | Scheduled routines, reminders, and in-session timers |
| 🏠 **Smart Home** | Optional Home Assistant integration |
| 📊 **3D HUD** | Real-time Three.js interface with WebSocket-driven updates |
| 📈 **Monitoring & Auditing** | Latency metrics, interaction logs, and audit exports |
| 🎓 **Self-Learning** | Collects SFT/DPO training pairs for future fine-tuning |

---

## 🏗️ Architecture

```text
                 ┌──────────────────────────────────────┐
                 │             JARVIS                   │
                 │                                      │
 Microphone ───► │ Wake Word Detection                  │
                 │          │                           │
                 │          ▼                           │
                 │ Speech-to-Text (Whisper)             │
                 │          │                           │
                 │          ▼                           │
                 │ Orchestrator                         │
                 │          │                           │
                 │     ┌────┴─────┐                     │
                 │     ▼          ▼                     │
                 │  Fast-path   Gemini API              │
                 │  Skills       │                      │
                 │     │         ▼                      │
                 │     │     Tool Execution             │
                 │     │  (Browser, Desktop, Files)     │
                 │     └────┬────┘                      │
                 │          ▼                           │
 Speakers ◄───── │ Text-to-Speech                       │
                 │ (Kokoro / Windows SAPI)              │
                 └──────────┬───────────────────────────┘
                            │
                         WebSocket
                            │
                 ┌──────────▼───────────────────────────┐
                 │       3D HUD Dashboard                │
                 │       http://localhost:8765           │
                 └──────────────────────────────────────┘
```

### Key Design Decisions

- **Local audio processing:** Microphone audio is processed locally through Whisper and the selected TTS engine.
- **Cloud-based reasoning:** Text-based conversation requests are sent to the Gemini API.
- **Fast-path execution:** Simple commands can be handled by deterministic skills without an LLM request.
- **Tool-based automation:** The assistant can invoke registered tools to interact with supported desktop applications and services.
- **Speaker verification:** Privileged operations are protected by voiceprint verification.
- **Real-time HUD:** The browser-based dashboard receives pipeline events through WebSockets.

---

## 📋 Requirements

| Requirement | Recommended |
|---|---|
| Operating System | Windows 11 (Windows 10 may work) |
| Python | 3.12 or 3.13 |
| GPU | NVIDIA GPU recommended; CPU mode supported |
| RAM | 8 GB minimum, 16 GB recommended |
| Microphone | Any supported input device |
| API Key | Google Gemini API key |

Get your Gemini API key: [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## 🚀 Installation & Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/NikhilForge/Jarvis-Enhanced.git
cd Jarvis-Enhanced
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure your API key

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Keep your `.env` file private. Never commit API keys or authentication tokens.

### 5. Launch JARVIS

**Recommended:**

Double-click:

```text
run.bat
```

The launcher is designed to prepare the environment, install dependencies, download required model files, enrol your voiceprint, start the HUD, and launch JARVIS.

Alternatively, run manually:

```powershell
$env:PYTHONUTF8="1"
python main.py
```

---

## 🗂️ Project Structure

```text
JARVIS-ENHANCED/
│
├── main.py
├── server.py
├── config.yaml
├── requirements.txt
├── run.bat
├── run_hud_only.bat
│
├── core/
│   ├── audio_in.py
│   ├── wakeword.py
│   ├── stt.py
│   ├── llm.py
│   ├── tts.py
│   ├── orchestrator.py
│   ├── skills.py
│   ├── memory.py
│   ├── speaker_id.py
│   ├── rag.py
│   ├── proactive.py
│   ├── learning.py
│   ├── metrics.py
│   ├── audit.py
│   ├── vad.py
│   └── bus.py
│
├── tools/
│   ├── registry.py
│   ├── browser.py
│   ├── vision.py
│   ├── system.py
│   ├── media.py
│   ├── accessibility.py
│   └── assistant.py
│
├── web/
│   ├── index.html
│   └── three.module.js
│
├── models/
├── scripts/
│   ├── enroll_voice.py
│   └── verify_voice.py
│
├── training/
└── eval/
```

---

## ⚙️ Configuration

Runtime settings are managed through `config.yaml`.

Example configuration:

```yaml
audio:
  input_device: auto
  input_gain: 3.0
  silence_ms_to_endpoint: 850
  vad_threshold: 0.20

llm:
  backend: gemini
  model: gemini-flash-lite-latest
  api_key_env: GEMINI_API_KEY

stt:
  model: base.en
  device: cpu

tts:
  engine: sapi
  voice: david

wakeword:
  model: hey_jarvis
  threshold: 0.28
  clap_to_wake: true

tools:
  browser:
    enabled: true
    headless: false

  home_assistant:
    enabled: false
```

**Note:** The values above are example defaults. Adjust them according to your hardware, installed models, and available integrations.

---

## 🎤 Example Voice Commands

JARVIS supports natural-language commands. Examples include:

| Voice Command | Action |
|---|---|
| "Hey Jarvis, what time is it?" | Answers using a fast-path skill |
| "Open YouTube and search for lofi hip hop" | Opens a YouTube search |
| "Open Notepad" | Launches or focuses Notepad |
| "Search for Python tutorials" | Performs a browser search |
| "What's on my screen?" | Captures and analyses the screen |
| "Set a timer for 10 minutes" | Schedules a timer |
| "Shut down the computer" | Requests confirmation before shutdown |
| "Play next song" | Sends a media-control command |
| "Turn on high contrast" | Activates Windows accessibility settings |
| "Remember that I prefer dark mode" | Stores information in persistent memory |

---

## 🛡️ Privacy & Security

- **Local audio processing:** Audio recognition and speech synthesis run locally.
- **API privacy:** Text-based reasoning requests are sent to the configured Gemini API.
- **Speaker verification:** Privileged tools use voiceprint verification.
- **Local memory:** RAG and memory databases are stored locally.
- **Audit logging:** Interactions can be recorded for debugging and auditing.
- **Credential protection:** API keys and tokens should be stored in `.env` and excluded from Git.

**Important:** Voice verification is an additional security layer, not a guarantee of protection against spoofing or unauthorised access. Review tool permissions before exposing the assistant to other users.

---

## 🧪 HUD Demo Mode

Run the HUD independently using synthetic events:

```powershell
python main.py --hud
```

Open your browser:

```text
http://localhost:8765
```

This allows you to explore the 3D interface without starting the complete voice pipeline.

---

## 🔧 Troubleshooting

### JARVIS cannot hear my voice

- Check `input_device` in `config.yaml`.
- Verify that Windows has microphone permissions enabled.
- Increase `input_gain` if the microphone input is too quiet.
- Try lowering `vad_threshold` if speech is not detected.

### Multiple browser tabs or application windows open

- Check the browser and desktop launch logic.
- Verify that application cooldown and URL deduplication are functioning correctly.

### Port 8765 is already in use

```powershell
netstat -ano | findstr :8765
```

Stop the process using the PID shown:

```powershell
taskkill /f /pid <PID>
```

### Kokoro TTS model missing

Run `run.bat` to allow the launcher to download the required model files, or follow the model setup instructions in the project.

### Gemini API key not found

- Check that `.env` exists in the project root.
- Confirm that the variable is named `GEMINI_API_KEY`.
- Restart JARVIS after updating the environment file.

---

## 📦 Core Dependencies

| Package | Purpose |
|---|---|
| `faster-whisper` | Local speech recognition |
| `openwakeword` | Wake-word detection |
| `kokoro-onnx` | Neural text-to-speech |
| `torch` / `torchaudio` | Audio processing and speaker encoding |
| `google-generativeai` / `httpx` | Gemini API integration |
| `playwright` | Browser automation |
| `fastapi` / `uvicorn` | HUD server |
| `pyautogui` / `psutil` | Desktop automation |
| `sentence-transformers` | Local RAG embeddings |
| `resemblyzer` | Speaker verification |
| `pycaw` / `comtypes` | Windows audio control |

---

## 🗺️ Roadmap

- [ ] Linux and macOS support
- [ ] Local LLM fallback using Ollama or llama.cpp
- [ ] Multi-room audio support
- [ ] Fine-tuned assistant persona
- [ ] GUI settings panel
- [ ] Expanded voice-command capabilities
- [ ] Further improvements to desktop automation and accessibility

---

## 📄 License & Attribution

This project is based on the original JARVIS repository:

[psycoks/Jarvis](https://github.com/psycoks/Jarvis)

**Jarvis Enhanced** includes modifications and additional functionality.

Please refer to the original repository's licensing terms and obtain the necessary permission before redistributing or relicensing its code. Do not assume that this project is MIT-licensed unless that permission is established.

---

## 🙏 Acknowledgements

Special thanks to the developers and maintainers of the open-source technologies that make this project possible:

- [openWakeWord](https://github.com/dscripka/openWakeWord)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [Resemblyzer](https://github.com/resemble-ai/Resemblyzer)
- [Playwright](https://playwright.dev/)
- [Three.js](https://threejs.org/)

---

**Built and enhanced by Nikhil.**

*An evolving desktop AI assistant, built to make everyday computer interaction more intelligent, natural, and hands-free.*