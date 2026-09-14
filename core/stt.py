"""faster-whisper small, CPU int8 — avoids CUDA/cuBLAS dependency."""
from faster_whisper import WhisperModel
from core.bus import BUS


class STT:
    def __init__(self, cfg: dict):
        s = cfg["stt"]
        self.cfg = s

        # Force CPU mode so Faster-Whisper does not require CUDA/cuBLAS DLLs.
        device = "cpu"
        compute_type = "int8"

        BUS.emit(
            "stt",
            f"loading faster-whisper {s['model']} on {device} ({compute_type})"
        )

        self.model = WhisperModel(
            s["model"],
            device=device,
            compute_type=compute_type,
        )

    def transcribe(self, audio, on_partial=None) -> str:
        segments, _info = self.model.transcribe(
            audio,
            language=self.cfg.get("language") or None,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )

        text = ""
        for seg in segments:
            text += seg.text

            if on_partial and self.cfg.get("first_partial_routing"):
                on_partial(text.strip())
                BUS.emit("stt", f'partial → "{text.strip()}"')

        text = text.strip()
        BUS.emit("stt", f'final → "{text}"')
        return text