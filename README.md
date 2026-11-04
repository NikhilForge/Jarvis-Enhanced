# JARVIS

> **A fully local, always-on voice AI assistant for Windows — powered by Gemini, Whisper, Kokoro TTS and Silero VAD.**

JARVIS runs entirely on your laptop. Wake word detection, speech recognition, text-to-speech and speaker verification never leave your machine. Only the reasoning request (plain text) is sent to the Gemini API.

---

## ✨ Features

| Category | Details |
|---|---|
| 🎙️ **Wake Word** | "Hey Jarvis" via openWakeWord (CPU ONNX), double-clap, or manual button |
| 🗣️ **Speech-to-Text** | faster-whisper (`base.en`) with Silero VAD endpointing — no cloud mic data |
| 🧠 **LLM Brain** | Gemini Flash (configurable model) with tool-calling and streaming output |
| 🔊 **Text-to-Speech** | Kokoro-82M ONNX (offline) or Windows SAPI — sentence-streamed for low latency |
| 🛡️ **Speaker ID** | Resemblyzer voiceprint — owner-only tools refused for unrecognised voices |
| 🌐 **Browser Control** | Playwright Chromium + desktop launch (Brave/Chrome/Edge) with YouTube automation |
| 🖥️ **Desktop Automation** | Launch apps, type text, click, hotkeys, screenshot, screen vision via Gemini |
| 📂 **File Access** | List, read, write and open local files (owner-gated) |
| 🔍 **Web Search** | DuckDuckGo search, full Playwright page reading |
| 🧩 **RAG Memory** | Local document indexing (all-MiniLM-L6-v2) with SQLite recall and ChromaDB archival |
| 📅 **Proactive** | Scheduled daily routines and in-session timers |
| 🏠 **Smart Home** | Home Assistant integration (optional) |
| 📊 **Live HUD** | WebSocket-driven Three.js orb dashboard at `http://localhost:8765` |
| 📈 **Metrics & Audit** | Latency logging (wake→STT, TTFT, TTS-first, RTF) and full audit trail |
| 🎓 **Self-learning** | Live SFT/DPO pair collection for future fine-tuning |

---

## 🏗️ Architecture

```
                  ┌─────────────────────────────────────────────┐
                  │               JARVIS Pipeline               │
                  │                                             │
  Microphone ──→  │  WakeWord (CPU) → STT (Whisper GPU/CPU)    │
                  │       ↓                                     │
                  │  Orchestrator → Skills (fast-path, 15ms)   │
                  │       ↓                 ↓ (no match)        │
                  │  LLM (Gemini API) ←─────┘                  │
                  │       ↓                                     │
                  │  Tool Execution (browser, desktop, fs…)     │
                  │       ↓                                     │
  Speakers ──←   │  TTS (Kokoro ONNX, sentence-streamed)       │
                  └──────────────┬──────────────────────────────┘
                                 │ WebSocket
                  ┌──────────────▼──────────────────────────────┐
                  │  HUD  http://localhost:8765  (Three.js orb) │
                  └─────────────────────────────────────────────┘
```

**Key design decisions:**
- All audio (mic → Whisper → Kokoro) stays local — Gemini never receives audio.
- Silero VAD (CPU ONNX) gates every frame; energy threshold set high enough to ignore Bluetooth mic hiss.
- Deterministic fast-path skills answer trivial commands in ~15 ms without touching the LLM.
- Tool calls are one-at-a-time; the LLM waits for each result before continuing.

---

## 📋 Requirements

- **OS:** Windows 11 (Windows 10 may work)
- **Python:** 3.12 or 3.13
- **GPU:** NVIDIA GPU recommended (Whisper INT8 on CUDA); CPU-only works but slower
- **RAM:** 8 GB minimum; 16 GB recommended
- **Microphone:** Any input device (Bluetooth headset supported with tuned gain)
- **API Key:** [Google Gemini API key](https://aistudio.google.com/app/apikey) (free tier works)

---

## 🚀 Quick Start

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/JARVIS.git
cd JARVIS
```

### 2. Add your Gemini API key

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

### 3. Run

**Double-click `run.bat`** — it will:
1. Create a `.venv` virtual environment
2. Install all dependencies
3. Download the Hey Jarvis wake-word ONNX model
4. Download Kokoro-82M TTS model files
5. Enrol your voiceprint (20 seconds of speech)
6. Open the HUD at `http://localhost:8765`
7. Start JARVIS

Or manually:

```bat
run.bat
```

```powershell
# PowerShell alternative
$env:PYTHONUTF8="1"
Set-Location "D:\JARVIS\Jarvis"
.\.venv\Scripts\python.exe main.py
```

---

## 🗂️ Project Structure

```
JARVIS/
├── main.py                  # Entrypoint (full pipeline or --hud demo mode)
├── server.py                # FastAPI + WebSocket HUD server (port 8765)
├── config.yaml              # All runtime settings
├── run.bat                  # One-click Windows launcher
├── requirements.txt         # Python dependencies
│
├── core/
│   ├── audio_in.py          # Microphone input, Silero VAD, AGC, pre-roll buffer
│   ├── wakeword.py          # openWakeWord CNN + double-clap detection
│   ├── stt.py               # faster-whisper speech-to-text
│   ├── llm.py               # Gemini API client, streaming, tool-call parsing
│   ├── tts.py               # Kokoro ONNX / SAPI TTS, sentence streaming
│   ├── orchestrator.py      # Main loop: wake → STT → LLM → TTS
│   ├── skills.py            # Deterministic fast-path (time, timers, YouTube, apps)
│   ├── memory.py            # Core memory, recall (SQLite), archival (ChromaDB)
│   ├── speaker_id.py        # Resemblyzer voiceprint enrollment & verification
│   ├── rag.py               # Local document RAG (sentence-transformers)
│   ├── proactive.py         # Scheduled routines and timers
│   ├── learning.py          # Live SFT/DPO pair collection
│   ├── metrics.py           # Latency and VRAM telemetry
│   ├── audit.py             # Full interaction audit trail (JSONL + CSV export)
│   ├── vad.py               # Silero VAD wrapper (falls back to WebRTC VAD)
│   └── bus.py               # In-process pub/sub event bus
│
├── tools/
│   ├── registry.py          # Tool decorator, voice-gate, app launcher with dedup
│   ├── browser.py           # Playwright browser + desktop URL launch (deduped)
│   ├── vision.py            # Screenshot capture + Gemini vision analysis
│   ├── system.py            # Power, processes, files, shell (owner-only)
│   ├── media.py             # System audio / media player control
│   ├── accessibility.py     # Narrator, magnifier, contrast, on-screen keyboard
│   └── assistant.py         # Memory tools (core_append, recall_search, etc.)
│
├── web/
│   ├── index.html           # Three.js orb HUD + WebSocket pipeline trace
│   └── three.module.js      # Bundled Three.js (local, no CDN)
│
├── models/                  # Kokoro ONNX model files (auto-downloaded by run.bat)
├── scripts/
│   ├── enroll_voice.py      # Voice enrollment script
│   └── verify_voice.py      # Voiceprint verification test
├── training/                # Optional fine-tuning scripts (Unsloth, DPO, SFT)
└── eval/                    # Latency, WER and tool-calling evaluation scripts
```

---

## ⚙️ Configuration

All settings live in [`config.yaml`](config.yaml). Key sections:

```yaml
audio:
  input_device: Airdopes        # Substring match — set to your mic name or "auto"
  input_gain: 3.0               # Software gain (boost quiet Bluetooth mics)
  silence_ms_to_endpoint: 850   # ms of silence to end recording
  vad_threshold: 0.20           # Silero VAD confidence threshold

llm:
  backend: gemini
  model: gemini-flash-lite-latest
  api_key_env: GEMINI_API_KEY   # reads from .env

stt:
  model: base.en                # Whisper model: tiny.en, base.en, small.en…
  device: cpu                   # or "cuda"

tts:
  engine: sapi                  # "sapi" (Windows voices) or "kokoro" (offline ONNX)
  voice: david

wakeword:
  model: hey_jarvis
  threshold: 0.28
  clap_to_wake: true            # double-clap alternative to voice wake

tools:
  browser:
    enabled: true
    headless: false             # set true to hide the Playwright window
  home_assistant:
    enabled: false              # set true + paste HA token to control smart home
```

---

## 🎤 Voice Commands

JARVIS understands natural English, Hindi, and Hinglish. Sample commands:

| Command | What happens |
|---|---|
| `"Hey Jarvis, what time is it?"` | Fast-path skill, answered in ~15 ms |
| `"Open YouTube and search for lofi hip hop"` | Opens search URL in browser |
| `"Open Notepad"` | Launches Notepad (or focuses existing window) |
| `"Search for Python tutorial on YouTube"` | YouTube search, deduped single tab |
| `"What's on my screen?"` | Screenshot + Gemini vision analysis |
| `"Set a timer for 10 minutes"` | Proactive timer scheduled |
| `"Shut down the computer"` | Owner-verified, confirmed before executing |
| `"Play next song"` | Media key forwarded to active player |
| `"Turn on high contrast"` | Windows Accessibility API |
| `"Remember that I prefer dark mode"` | Stored in persistent core memory |

---

## 🛡️ Privacy & Security

- **All audio stays local.** Whisper and Kokoro run on-device; no audio is ever sent to the cloud.
- **Only text reasoning goes to Gemini.** The API receives the conversation turn text — not your voice, not screenshots (unless you explicitly ask `"what's on my screen?"`).
- **Owner-only tool gate.** Commands that touch the filesystem, run shell commands, or control power require the enrolled voiceprint to clear the `privileged_threshold`. Strangers can ask the weather; they cannot shut down your PC.
- **Local RAG.** Document embeddings are stored on-disk in ChromaDB — not sent anywhere.
- **Audit trail.** Every interaction is logged to `data/audit.jsonl`. Export as CSV from the HUD.

---

## 🧪 HUD Demo Mode

Run the HUD with synthetic events (no models or API key needed):

```powershell
.\.venv\Scripts\python.exe main.py --hud
```

Then open `http://localhost:8765` to see the orb and pipeline trace.

---

## 🔧 Troubleshooting

**JARVIS can't hear me / orb moves but doesn't transcribe**
- Check `input_device` in `config.yaml` matches a substring of your mic name (shown in `[sys] audio input open on [...]` log line)
- Increase `input_gain` if using a Bluetooth headset (3.0–4.0 recommended)
- Lower `vad_threshold` to `0.15` if speech is not being detected

**Multiple browser tabs / app windows opening**
- Already fixed: `_launch_desktop_url` has 3.5-second URL deduplication; `desktop.launch_app` has 3-second per-app cooldown and focuses existing windows

**Port 8765 already in use**
- `run.bat` automatically kills the stale process; or run: `netstat -ano | findstr :8765` → `taskkill /f /pid <PID>`

**Kokoro TTS model missing**
- Run `run.bat` once; it auto-downloads from GitHub releases
- Or manually: download `kokoro-v1.0.onnx` and `voices-v1.0.bin` into `models/`

**`GEMINI_API_KEY` not found**
- Create a `.env` file in the project root: `GEMINI_API_KEY=your_key_here`
- Get a free key at [aistudio.google.com](https://aistudio.google.com/app/apikey)

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `faster-whisper` | Local speech-to-text (INT8 quantised) |
| `openwakeword` | "Hey Jarvis" wake-word detection |
| `kokoro-onnx` | Local neural TTS (Kokoro-82M) |
| `torch` + `torchaudio` | Silero VAD, speaker encoder |
| `google-generativeai` / `httpx` | Gemini API reasoning |
| `playwright` | Browser automation |
| `fastapi` + `uvicorn` | HUD WebSocket server |
| `pyautogui` + `psutil` | Desktop automation |
| `sentence-transformers` | Local RAG embeddings |
| `resemblyzer` | Speaker voiceprint verification |
| `pycaw` + `comtypes` | Windows audio / media control |

---

## 🗺️ Roadmap

- [ ] Linux / macOS support (audio and desktop layers)
- [ ] Local LLM fallback (Ollama / llama.cpp) when offline
- [ ] Multi-room audio via Snapcast
- [ ] Fine-tuned persona model via collected DPO pairs
- [ ] GUI settings panel (mic selector, model picker)

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [openWakeWord](https://github.com/dscripka/openWakeWord) — wake-word detection
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2 Whisper
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) — Kokoro TTS ONNX runtime
- [Silero VAD](https://github.com/snakers4/silero-vad) — neural voice activity detection
- [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) — speaker verification
- [Playwright](https://playwright.dev/) — browser automation

---

*Built for personal use on a Ryzen 5 7235HS + RTX 3050 6GB laptop.*
