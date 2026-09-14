"""Microphone ingestion: 20 ms frames -> wake word -> VAD endpointing."""
import queue, time, numpy as np, sounddevice as sd
from core.bus import BUS
from core.vad import VAD


class AudioInput:
    def __init__(self, cfg: dict):
        a = cfg["audio"]
        self.rate = a["sample_rate"]
        self.frame = int(self.rate * a["frame_ms"] / 1000)
        self.vad = VAD(cfg)   # Silero on CPU
        self.silence_frames = a["silence_ms_to_endpoint"] // a["frame_ms"]
        self.device = a["input_device"]
        self.q: "queue.Queue[bytes]" = queue.Queue()
        self._stream = None
        w = a
        self.clap_enabled = bool(cfg.get("wakeword", {}).get("clap_to_wake", False))
        self.clap_min_gap = cfg.get("wakeword", {}).get("clap_min_gap_ms", 120) / 1000.0
        self.clap_max_gap = cfg.get("wakeword", {}).get("clap_max_gap_ms", 700) / 1000.0
        self.clap_cooldown = cfg.get("wakeword", {}).get("clap_cooldown_ms", 1200) / 1000.0
        self._last_clap = 0.0
        self._clap_times = []
        self._noise_floor = 0.015

    def start(self):
        def cb(indata, frames, t, status):
            self.q.put(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self.rate, blocksize=self.frame, dtype="int16",
            channels=1, callback=cb, device=self.device,
        )
        self._stream.start()
        BUS.emit("sys", f"audio input open @ {self.rate} Hz")

    def frames(self):
        while True:
            yield self.q.get()

    def level(self, frame: bytes) -> float:
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        return float(min(1.0, np.sqrt((x ** 2).mean()) * 6.0))


    def clap_triggered(self, frame: bytes) -> bool:
        """Best-effort double-clap detector using transient RMS + zero-crossing rate."""
        if not self.clap_enabled:
            return False
        now = time.monotonic()
        if now - self._last_clap < self.clap_cooldown:
            return False
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
        zcr = float(np.mean(x[:-1] * x[1:] < 0)) if len(x) > 1 else 0.0
        # A clap is a short, loud, broadband transient. These thresholds are intentionally conservative.
        if rms > max(0.12, self._noise_floor * 5.0) and zcr > 0.12:
            self._clap_times = [t for t in self._clap_times if now - t <= self.clap_max_gap]
            if not self._clap_times or now - self._clap_times[-1] >= self.clap_min_gap:
                self._clap_times.append(now)
                if len(self._clap_times) >= 2:
                    self._clap_times.clear()
                    self._last_clap = now
                    BUS.emit("wake", "double-clap wake triggered")
                    return True
        else:
            self._noise_floor = self._noise_floor * 0.98 + rms * 0.02
        return False

    def record_utterance(self, max_seconds: float = 15.0):
        """Collect frames until the VAD reports sustained silence."""
        collected, quiet, spoke = [], 0, False
        limit = int(max_seconds * self.rate / self.frame)
        for i, f in enumerate(self.frames()):
            collected.append(f)
            voiced = self.vad.is_speech(f)
            spoke = spoke or voiced
            quiet = 0 if voiced else quiet + 1
            BUS.emit("level", "", value=self.level(f))
            if spoke and quiet >= self.silence_frames:
                break
            if i >= limit:
                break
        pcm = b"".join(collected)
        return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    def close(self):
        if self._stream:
            self._stream.stop(); self._stream.close()
