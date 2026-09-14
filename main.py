"""JARVIS-6 entrypoint.

  python main.py            full pipeline (needs Ollama + models pulled)
  python main.py --hud      HUD only, synthetic events (no models required)
"""
import argparse, asyncio, random, sys, threading, time, yaml
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from core.bus import BUS
from core.audit import Audit


def hud_only():
    import server
    def fake():
        time.sleep(1.5)
        script = [("wake", "wake word fired · confidence 0.96"),
                  ("state", "listening"), ("stt", 'partial → "open vs code and"'),
                  ("stt", 'final → "open vs code and summarise my notes"'),
                  ("state", "thinking"), ("llm", "first-partial routing: tools prefetched"),
                  ("tool", 'desktop.launch_app({"app": "Code"})'),
                  ("mem", "archival_search('notes') → 3 chunks"),
                  ("state", "speaking"), ("tts", "kokoro stream open"),
                  ("state", "idle")]
        while True:
            for ch, tx in script:
                BUS.emit(ch, tx, state=tx if ch == "state" else None)
                for _ in range(12):
                    BUS.emit("level", "", value=random.random() * 0.7)
                    time.sleep(0.05)
            time.sleep(2)
    threading.Thread(target=fake, daemon=True).start()
    server.start(None)


def full():
    import server
    from core.audio_in import AudioInput
    from core.wakeword import WakeWord
    from core.stt import STT
    from core.llm import LLM
    from core.tts import TTS
    from core.memory import Memory
    from core.speaker_id import SpeakerID
    from core.metrics import Metrics
    from core.orchestrator import Orchestrator
    from core.rag import DocRAG
    from core.learning import Learning
    from core.audit import Audit
    from core.proactive import Proactive
    import tools.assistant  # noqa: F401
    import tools.browser    # noqa: F401
    import tools.vision     # noqa: F401

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    print("· loading local speech models + Gemini agent tools…")
    tts = TTS(cfg)
    rag = DocRAG(cfg)
    learning = Learning(cfg)
    audit = Audit(cfg)
    proactive = Proactive(cfg, speak=tts.say)
    orch = Orchestrator(cfg, AudioInput(cfg), WakeWord(cfg), STT(cfg), LLM(cfg), tts,
                        Memory(cfg), SpeakerID(cfg), Metrics(cfg),
                        rag=rag, learning=learning, proactive=proactive, audit=audit)
    if cfg.get("rag", {}).get("index_on_start"):
        threading.Thread(target=rag.index, daemon=True).start()
    for hhmm, line in (cfg.get("proactive", {}).get("routines") or {}).items():
        proactive.schedule_daily(hhmm, line)
    print(f"· HUD → http://{cfg['server']['host']}:{cfg['server']['port']}")
    server.start(orch)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--hud", action="store_true", help="run the HUD with synthetic events only")
    a = p.parse_args()
    hud_only() if a.hud else full()
