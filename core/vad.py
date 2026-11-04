"""Silero VAD — strictly CPU (ONNX, ~30 MB RAM). Falls back to WebRTC VAD if unavailable."""
import numpy as np
from core.bus import BUS


class VAD:
    """Frame-level speech probability. Runs on the Ryzen CPU so the RTX 3050 stays free."""

    def __init__(self, cfg: dict):
        a = cfg.get("audio", {})
        self.rate = a.get("sample_rate", 16000)
        self.threshold = float(a.get("vad_threshold", 0.22))
        self.backend = "silero"
        self._win = 512 if self.rate == 16000 else 256
        self._buf = np.zeros(self._win, dtype=np.float32)
        try:
            import torch
            torch.set_num_threads(1)                       # keep it off the GPU and light on CPU
            self.model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", onnx=True, trust_repo=True)
            self.torch = torch
            BUS.emit("sys", "Silero VAD armed (CPU/ONNX)")
        except Exception as e:
            import webrtcvad
            self.backend = "webrtc"
            self.model = webrtcvad.Vad(a.get("vad_aggressiveness", 2))
            BUS.emit("sys", f"Silero unavailable ({e}); using WebRTC VAD on CPU")

    def is_speech(self, frame: bytes) -> bool:
        if self.backend == "webrtc":
            return self.model.is_speech(frame, self.rate)
        pcm = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        n = len(pcm)
        if n >= self._win:
            self._buf = pcm[-self._win:]
        else:
            self._buf = np.concatenate([self._buf[n:], pcm])
        tensor = self.torch.from_numpy(self._buf)
        try:
            p = float(self.model(tensor, self.rate).item())
            return p >= self.threshold
        except Exception:
            return False

    def reset(self):
        """Reset internal buffer and model recurrent state to prevent drift."""
        self._buf = np.zeros(self._win, dtype=np.float32)
        try:
            if hasattr(self.model, "reset_states"):
                self.model.reset_states()
        except Exception:
            pass
