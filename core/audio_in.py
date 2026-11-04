"""Microphone ingestion: 20 ms frames -> wake word -> VAD endpointing."""
import collections, queue, time, numpy as np, sounddevice as sd
from core.bus import BUS
from core.vad import VAD


def resolve_input_device(spec):
    """
    Robust device resolution by name or index.
    Filters out WDM-KS kernel drivers (hostapi 3) which fail on Bluetooth headsets.
    Prioritizes built-in laptop mic (Realtek MME) when spec is None or 'auto'.
    """
    try:
        devices = sd.query_devices()
    except Exception:
        return None

    valid_devices = [
        (idx, d) for idx, d in enumerate(devices)
        if d.get("max_input_channels", 0) > 0 and d.get("hostapi") in (0, 2)
    ]

    if spec is not None:
        s = str(spec).strip().lower()
        if s not in ("null", "none", "default", "", "auto"):
            # 1. Match against MME first (hostapi == 0)
            for idx, d in valid_devices:
                if d.get("hostapi") == 0 and s in d.get("name", "").lower():
                    return idx
            # 2. Match against any valid device (WASAPI)
            for idx, d in valid_devices:
                if s in d.get("name", "").lower():
                    return idx
            if s.isdigit():
                idx = int(s)
                if idx < len(devices) and devices[idx].get("max_input_channels", 0) > 0:
                    return idx

    # If spec is None or 'auto', prefer the laptop's Realtek microphone array
    for idx, d in valid_devices:
        name = d.get("name", "").lower()
        if d.get("hostapi") == 0 and "realtek" in name:
            return idx
    for idx, d in valid_devices:
        name = d.get("name", "").lower()
        if "realtek" in name:
            return idx
    for idx, d in valid_devices:
        name = d.get("name", "").lower()
        if d.get("hostapi") == 0 and "microphone" in name:
            return idx

    try:
        return sd.default.device[0]
    except Exception:
        return None


class AudioInput:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        a = cfg.get("audio", {})
        self.rate = a.get("sample_rate", 16000)
        self.frame = int(self.rate * a.get("frame_ms", 20) / 1000)
        self.vad = VAD(cfg)   # Silero on CPU with sliding window
        self.silence_frames = a.get("silence_ms_to_endpoint", 1000) // a.get("frame_ms", 20)
        self.device = resolve_input_device(a.get("input_device"))
        self.gain = float(a.get("input_gain", 3.0))
        self.q: "queue.Queue[bytes]" = queue.Queue()
        self._history = collections.deque(maxlen=30)  # 600ms circular pre-roll buffer
        self._stream = None
        self.clap_enabled = bool(cfg.get("wakeword", {}).get("clap_to_wake", False))
        self.clap_min_gap = cfg.get("wakeword", {}).get("clap_min_gap_ms", 120) / 1000.0
        self.clap_max_gap = cfg.get("wakeword", {}).get("clap_max_gap_ms", 700) / 1000.0
        self.clap_cooldown = cfg.get("wakeword", {}).get("clap_cooldown_ms", 1200) / 1000.0
        self._last_clap = 0.0
        self._clap_times = []
        self._noise_floor = 0.0015

    def start(self):
        dev = self.device
        channels = 1
        dev_name = "default"
        try:
            dev_info = sd.query_devices(dev, "input")
            dev_name = dev_info.get("name", str(dev))
            max_in = dev_info.get("max_input_channels", 1)
            # Laptop array mics usually offer 2 channels
            if max_in >= 2:
                channels = 2
        except Exception:
            pass

        gain = self.gain
        if channels == 1:
            def cb(indata, frames, t, status):
                if gain != 1.0:
                    arr = np.frombuffer(indata, dtype=np.int16).astype(np.float32) * gain
                    self.q.put(np.clip(arr, -32768, 32767).astype(np.int16).tobytes())
                else:
                    self.q.put(bytes(indata))
        else:
            def cb(indata, frames, t, status):
                # Downmix stereo to mono int16 by averaging channels and apply software gain
                arr = np.frombuffer(indata, dtype=np.int16).reshape(-1, 2).mean(axis=1)
                if gain != 1.0:
                    arr = arr * gain
                mono = np.clip(arr, -32768, 32767).astype(np.int16).tobytes()
                self.q.put(mono)

        self._stream = sd.RawInputStream(
            samplerate=self.rate, blocksize=self.frame, dtype="int16",
            channels=channels, callback=cb, device=self.device,
        )
        self._stream.start()
        BUS.emit("sys", f"audio input open on [{dev_name}] (gain {gain:.1f}x, {channels}ch -> 1ch)")

    def switch_device(self, new_spec) -> bool:
        """Switch input microphone device on the fly without restarting JARVIS."""
        try:
            self.close()
            resolved = resolve_input_device(new_spec)
            self.device = resolved
            self.start()
            return True
        except Exception as e:
            BUS.emit("sys", f"failed switching mic to {new_spec}: {e}")
            return False

    def frames(self):
        while True:
            f = self.q.get()
            self._history.append(f)
            yield f

    def level(self, frame: bytes) -> float:
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x)))
        return float(min(1.0, rms * 20.0))

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

    def record_utterance(self, max_seconds: float = 8.5) -> np.ndarray:
        """
        Record the user's voice command cleanly:
        1. Keeps ~600ms pre-roll frames so speech onset is preserved.
        2. Detects speech using Silero VAD without mic hiss false-positives.
        3. Endpoints cleanly after ~800-900ms post-speech pause so natural mid-sentence pauses aren't cut off.
        4. Applies AGC / peak normalization for optimal Whisper transcription accuracy.
        """
        collected = list(self._history)

        quiet = 0
        spoke = False
        limit = int(max_seconds * self.rate / self.frame)
        initial_silence_limit = int(4.5 * self.rate / self.frame)  # 4.5s timeout if user doesn't speak
        endpoint_silence = max(35, min(55, self.silence_frames))   # ~700-1100ms post-speech silence (default ~850ms)

        for i, f in enumerate(self.frames()):
            collected.append(f)
            x = np.frombuffer(f, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(x * x)))

            # Speech detection: trust neural Silero VAD; ignore low-level Bluetooth mic hiss
            vad_voiced = self.vad.is_speech(f)
            energy_voiced = (rms > max(0.010, self._noise_floor * 2.8))
            voiced = vad_voiced or energy_voiced

            if voiced:
                spoke = True
                quiet = 0
            else:
                if spoke:
                    quiet += 1

            BUS.emit("level", "", value=self.level(f))

            # Endpoint condition: user spoke real utterance and then paused for ~850ms
            if spoke and len(collected) >= 20 and quiet >= endpoint_silence:
                break

            # Timeout if the user never spoke within 4.5s
            if not spoke and i >= initial_silence_limit:
                break

            if i >= limit:
                break

            # Only adapt background noise floor before speech begins
            if not spoke and not voiced:
                self._noise_floor = self._noise_floor * 0.95 + rms * 0.05

        # Trim trailing silence frames so Whisper receives clean audio without trailing static
        if spoke and quiet > 15:
            excess = quiet - 10
            collected = collected[:-excess]

        pcm = b"".join(collected)
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        if len(audio) < int(self.rate * 0.3):  # Less than 300ms
            return np.zeros(0, dtype=np.float32)

        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        rms = float(np.sqrt(np.mean(audio * audio))) if len(audio) else 0.0

        # Discard only if completely silent and no speech was detected
        if not spoke and peak < 0.005 and rms < 0.001:
            return np.zeros(0, dtype=np.float32)

        # Automatic Gain Control / Peak Normalization so Whisper receives optimal volume
        if peak > 0.0005:
            target_gain = min(15.0, 0.85 / peak)
            audio = np.clip(audio * target_gain, -1.0, 1.0)

        return audio

    def close(self):
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
