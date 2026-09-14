"""Latency + resource profiling: TTFT, RTF, end-to-end, VRAM and system RAM ceilings."""
import json, os, time
from collections import deque
from core.bus import BUS

try:
    import psutil
except Exception:
    psutil = None


class Metrics:
    def __init__(self, cfg: dict):
        self.log_path = cfg.get("metrics", {}).get("log_path", "data/metrics.jsonl")
        self.vram_ceiling = cfg.get("metrics", {}).get("vram_ceiling_gb", 6.0)
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        self.recent = deque(maxlen=50)
        self._t = {}
        self._nvml = None
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
            self._gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            pass

    def mark(self, key: str):
        self._t[key] = time.perf_counter()

    def since(self, key: str) -> float:
        return (time.perf_counter() - self._t.get(key, time.perf_counter())) * 1000.0

    def vram_gb(self) -> float:
        if not self._nvml:
            return 0.0
        info = self._nvml.nvmlDeviceGetMemoryInfo(self._gpu)
        return info.used / 1024 ** 3

    def ram_gb(self) -> float:
        return psutil.virtual_memory().used / 1024 ** 3 if psutil else 0.0

    def sample(self):
        v, r = self.vram_gb(), self.ram_gb()
        if v > self.vram_ceiling:
            BUS.emit("sys", f"VRAM ceiling breached: {v:.2f} GB > {self.vram_ceiling} GB")
        BUS.emit("res", f"vram {v:.2f} GB · ram {r:.1f} GB", vram=v, ram=r)
        return v, r

    def record(self, turn: dict):
        turn["ts"] = time.time()
        turn["vram_gb"], turn["ram_gb"] = self.sample()
        self.recent.append(turn)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(turn) + "\n")
        BUS.emit(
            "perf",
            "wake→stt {stt:.0f} ms · ttft {ttft:.0f} ms · tts-first {tts:.0f} ms · e2e {e2e:.0f} ms · rtf {rtf:.2f}".format(
                stt=turn.get("stt_ms", 0), ttft=turn.get("ttft_ms", 0),
                tts=turn.get("tts_first_ms", 0), e2e=turn.get("e2e_ms", 0), rtf=turn.get("rtf", 0)),
            **turn,
        )
