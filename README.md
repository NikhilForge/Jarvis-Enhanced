# JARVIS-6 v6 — Gemini Local-First Voice Agent

A local-first Windows voice assistant with an offline wake word, local speech-to-text, local Kokoro speech synthesis, local memory/tools, a visible browser agent, screen vision through Gemini, and a local WebGL HUD.

**Important:** the application, microphone capture, wake word, STT, TTS, memory, browser control and desktop tools run on your laptop. When Gemini is enabled, the text/context or screen image needed for reasoning is sent to Google's Gemini API. This is therefore **local-first, not fully offline**.

## What v6 adds

- Gemini function-calling brain (`gemini-2.5-flash` by default)
- Multi-hop agent loop: tool → result → Gemini → next tool
- `browser.*` Playwright agent with persistent visible Chrome session
- `vision.analyze_screen` for Gemini screen understanding
- English + Hindi + Hinglish STT auto-detection
- Hey-Jarvis wake word, double-clap wake and HUD wake button
- Speaker verification for owner-only tools
- Human confirmation for destructive/external-impact actions
- Local RAG, memory, reminders, audit trail and learning logs
- WebGL HUD and live pipeline trace

Google's Gemini function-calling flow is intentionally used as the agent boundary: Gemini selects a declared function, the local Python app executes it, and the result is sent back for the next decision. citeturn0search6

Playwright is used for browser automation because its Python library supports headed Chromium/Chrome, persistent browser contexts, navigation, locators and screenshots. Install the browser binary with `playwright install chromium`. citeturn0search0turn0search2

## Quick start — Windows 11

1. Install Python 3.11 and an up-to-date NVIDIA driver if using CUDA Whisper.
2. Extract this folder.
3. Run `run.bat` once.
4. Edit `.env` and set:

```env
GEMINI_API_KEY=your_key_here
```

5. Run `run.bat` again.
6. Enrol your voice if prompted.
7. Open `http://127.0.0.1:8765`.
8. Say **Hey Jarvis**, double-clap, or click **WAKE JARVIS**.

The launcher installs the Chromium browser used by the local browser agent. Playwright's official installation instructions require the package plus browser binaries. citeturn0search0turn0search2

## Gemini model

`config.yaml` defaults to:

```yaml
llm:
  backend: gemini
  api_key_env: GEMINI_API_KEY
  model: gemini-2.5-flash
```

Gemini 2.5 Flash is listed by Google as a low-latency, high-volume reasoning model and supports function calling. citeturn0search12

Do not commit `.env` or expose the API key in the HUD or source code.

## Agent loop

```text
voice / button / clap
        ↓
local wake word
        ↓
local Whisper STT
        ↓
owner voice verification
        ↓
Gemini
        ↓
function call
        ↓
local tool
        ↓
tool result
        ↓
Gemini again
        ↓
next tool OR final answer
        ↓
local Kokoro TTS
```

This is deliberately a bounded agent loop. The orchestrator allows several sequential tool hops but still applies owner gates and confirmation gates before sensitive operations.

## Browser agent

The browser is visible by default. JARVIS can:

- open URLs
- search the web in a browser
- inspect page text
- click links/buttons
- fill inputs
- press keys
- create tabs
- list tabs
- take browser screenshots

Example requests:

- "Jarvis, open YouTube."
- "Search the web for the latest Python release and summarize it."
- "Open my college portal and show me the login page."
- "Go to the page I opened and find the assignment deadline."

The browser tools must not be used to bypass CAPTCHAs, MFA, paywalls or access controls. Purchases, messages, account changes and other consequential actions should require confirmation.

## Screen vision

Say:

> "Jarvis, look at my screen and tell me what's wrong."

The local app captures a screenshot and sends that image to the configured Gemini model for visual understanding. Gemini's API supports image inputs alongside text. citeturn0search11

The screenshot itself is not uploaded to a third-party storage service by JARVIS; it is included in the Gemini API request.

## Voice controls

- **Hey Jarvis** — local wake word
- **Double clap** — local transient detector
- **WAKE JARVIS** — local HUD button
- **Follow-up window** — short follow-ups after a response without repeating the wake word
- **Barge-in** — wake/stop playback while JARVIS is speaking

## Safety model

Owner-only tools require a matching enrolled voiceprint. Destructive tools also require confirmation.

Examples:

| Action | Policy |
|---|---|
| time/date | automatic |
| web research | automatic |
| open browser | owner voice |
| read/write personal files | owner voice |
| type/click on desktop | owner voice |
| shell command | owner voice + confirmation |
| delete file | owner voice + confirmation |
| shutdown/restart | owner voice + confirmation |
| smart-home service | owner voice + confirmation |
| purchases/messages/account changes | confirm before execution |

No language model can safely perform literally every possible computer action without a tool and permission boundary. v6 is designed so new capabilities can be added as narrowly scoped tools instead of giving Gemini unrestricted shell access.

## Local/offline components

| Component | Runs |
|---|---|
| Wake word | local CPU |
| Clap detector | local CPU |
| Whisper STT | local CPU/GPU |
| Speaker verification | local CPU |
| Kokoro TTS | local |
| Memory/RAG | local |
| Browser automation | local |
| Desktop automation | local |
| Gemini reasoning | Google API |
| Gemini screen vision | Google API |

## Project layout

```text
core/
  audio_in.py       microphone + clap detector
  wakeword.py       openWakeWord
  stt.py            faster-whisper
  llm.py            Gemini + tool calling + image understanding
  orchestrator.py   multi-hop agent loop + safety
  memory.py         local memory
  rag.py            local document RAG
  tts.py            Kokoro
  speaker_id.py     voice verification
  audit.py          audit trail

tools/
  registry.py       tool schema/permission registry
  system.py         OS power/process tools
  browser.py        Playwright browser agent
  vision.py         screen capture + Gemini vision
  assistant.py      reminders/RAG/learning tools

web/
  index.html        WebGL JARVIS HUD
```

## Known limitations

- Gemini requires internet access and API quota.
- Gemini subscription benefits and Gemini API billing/quotas are separate concepts; check your Google AI Studio/API billing status before assuming a consumer subscription includes API quota.
- Screen vision sends screenshots to Gemini when invoked.
- Browser websites can change their HTML, so no browser agent can guarantee every site forever.
- CAPTCHAs/MFA/payment confirmations are intentionally not bypassed.
- Kokoro voice output is primarily configured for English; Gemini can understand Hindi/Hinglish, but a dedicated Hindi TTS engine can be added later if native Hindi pronunciation becomes a priority.

## Next recommended v7

1. Native Hindi TTS fallback.
2. Gmail/Calendar connectors with confirmation gates.
3. GitHub skill for repository inspection, commits and pull requests.
4. VS Code skill for project navigation and terminal tasks.
5. Camera vision as an explicit opt-in tool.
6. Scheduled autonomous workflows with a permission profile.
7. Better browser locator recovery when a site changes.
8. A visual action planner that combines screenshot understanding with browser/desktop tools.
