# JARVIS-6 v5 upgrade

This version switches the default reasoning backend from local Ollama to Gemini API.

Implemented:
- Gemini API key via `.env` / `GEMINI_API_KEY`
- Gemini function calling mapped to the existing local tool registry
- Local-only microphone, wake word, STT, TTS, memory and tool execution
- "Hey Jarvis" offline wake word
- Double-clap wake
- Local HUD "WAKE JARVIS" button
- Stronger owner-only enforcement for desktop/files/memory tools
- Fixed fast-path context handling for stop/timer/volume
- Fixed built-in openWakeWord model-path resolution
- Removed stale Ollama pull from the default Windows launcher
- Updated README and HUD to distinguish local execution from Gemini cloud reasoning

Important:
Gemini API use is not covered simply by a consumer Gemini subscription. API access/limits/billing are controlled separately in Google AI Studio/Cloud Billing.


## v6.1 wake-word fix
- Automatically downloads the official `hey_jarvis` openWakeWord model when it is missing.
- `run.bat` provisions the wake-word model before starting JARVIS.
- Wake-word startup now raises a clear model-path error instead of an ONNXRuntime `NO_SUCHFILE` traceback.
