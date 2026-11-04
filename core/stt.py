"""faster-whisper English speech recognition with domain prompting and acoustic beam search."""
import re
from faster_whisper import WhisperModel
from core.bus import BUS

PROMPT = "Hey Jarvis, open YouTube, Google, search, play music, browser, video, channel, shutdown, time, weather."

FUZZY_FIXES = [
    (re.compile(r"\b(?:new\s*to|u\s*tube|you\s*tube)\b", re.I), "YouTube"),
    (re.compile(r"\b(?:john'?s|jravis|jarves|jervis|javis)\b", re.I), "Jarvis"),
    (re.compile(r"\b(?:opne|oepn)\b", re.I), "open"),
]


class STT:
    def __init__(self, cfg: dict):
        s = cfg.get("stt", {})
        self.cfg = s
        device = "cpu"
        compute_type = "int8"
        model_name = s.get("model", "base.en")
        BUS.emit("stt", f"loading faster-whisper {model_name} on {device} ({compute_type})")
        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

    def transcribe(self, audio, on_partial=None) -> str:
        if audio is None or len(audio) == 0:
            return ""
        beam = int(self.cfg.get("beam_size", 3))
        segments, _info = self.model.transcribe(
            audio,
            language="en",
            beam_size=beam,
            initial_prompt=PROMPT,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
            condition_on_previous_text=False,
        )

        text = ""
        for seg in segments:
            text += seg.text
            if on_partial and self.cfg.get("first_partial_routing"):
                p_text = self._clean(text.strip())
                on_partial(p_text)
                BUS.emit("stt", f'partial → "{p_text}"')

        text = self._clean(text.strip())
        if text:
            BUS.emit("stt", f'final → "{text}"')
        return text

    def _clean(self, text: str) -> str:
        for pat, repl in FUZZY_FIXES:
            text = pat.sub(repl, text)
        return text
