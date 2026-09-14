"""Kokoro-82M ONNX (<0.5 GB). Sentences are spoken as soon as the LLM closes them."""
import re, numpy as np, sounddevice as sd
from core.bus import BUS

SENT_END = re.compile(r"(?<=[.!?])\s+")


class TTS:
    def __init__(self, cfg: dict):
        t = cfg["tts"]
        self.cfg = t
        from kokoro_onnx import Kokoro
        self.engine = Kokoro(t["model_path"], t["voices_path"])
        BUS.emit("tts", f"kokoro-82m ready · voice {t['voice']}")

    def stop(self):
        """Cut playback immediately (barge-in)."""
        try:
            sd.stop()
        except Exception:
            pass

    def say(self, text: str):
        if not text.strip():
            return
        samples, rate = self.engine.create(
            text, voice=self.cfg["voice"], speed=self.cfg["speed"], lang="en-us"
        )
        BUS.emit("tts", f'speaking "{text[:60]}"')
        for i in range(0, len(samples), 1024):
            chunk = samples[i:i + 1024]
            BUS.emit("level", "", value=float(min(1.0, np.abs(chunk).mean() * 8)))
        sd.play(samples, rate); sd.wait()
        BUS.emit("level", "", value=0.05)

    def stream_sentences(self, token_iter, stop=None):
        """Consume LLM tokens, flush to Kokoro the millisecond a sentence closes."""
        buf, full = "", ""
        for tok in token_iter:
            if stop is not None and stop.is_set():
                break
            buf += tok; full += tok
            if SENT_END.search(buf) or len(buf) > 240:
                parts = SENT_END.split(buf)
                for p in parts[:-1]:
                    self.say(p.strip())
                buf = parts[-1]
        if buf.strip() and not (stop is not None and stop.is_set()):
            self.say(buf.strip())
        return full
