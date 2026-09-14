"""Silero VAD — strictly CPU (ONNX, ~30 MB RAM). Falls back to WebRTC VAD if unavailable."""
import numpy as np
from core.bus import BUS


class VAD:
    """Frame-level speech probability. Runs on the Ryzen CPU so the RTX 3050 stays free."""

    def __init__(self, cfg: dict):
        a = cfg["audio"]
        self.rate = a["sample_rate"]
        self.threshold = a.get("vad_threshold", 0.5)
        self.backend = "silero"
        self._buf = np.zeros(0, dtype=np.float32)
        self._win = 512 if self.rate == 16000 else 256
        try:
            import torch
            torch.set_num_threads(1)                       # keep it off the GPU and light on CPU
            self.model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", onnx=True, trust_repo=True)
            self.torch = torch
            BUS.emit("sys", "Silero VAD armed (CPU/ONNX)")
        except Exception as e:
            import webrtcvad
            self.backend = "webrtc"
            self.model = webrtcvad.Vad(a["vad_aggressiveness"])
            BUS.emit("sys", f"Silero unavailable ({e}); using WebRTC VAD on CPU")

    def is_speech(self, frame: bytes) -> bool:
        if self.backend == "webrtc":
            return self.model.is_speech(frame, self.rate)
        pcm = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        self._buf = np.concatenate([self._buf, pcm])
        voiced = False
        while len(self._buf) >= self._win:
            chunk, self._buf = self._buf[: self._win], self._buf[self._win :]
            p = float(self.model(self.torch.from_numpy(chunk), self.rate).item())
            voiced = voiced or p >= self.threshold
        return voiced
