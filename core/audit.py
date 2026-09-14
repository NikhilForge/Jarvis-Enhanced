"""Append-only local audit trail for JARVIS tool and safety events."""
import json, os, threading, time
from typing import Any

class Audit:
    def __init__(self, cfg):
        self.enabled = bool(cfg.get("audit", {}).get("enabled", True))
        self.path = os.path.expanduser(cfg.get("audit", {}).get("path", "data/audit.jsonl"))
        self._lock = threading.Lock()
        if self.enabled:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def record(self, event: str, **fields: Any):
        if not self.enabled:
            return
        entry = {"ts": time.time(), "event": event, **fields}
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def read(self, limit: int = 500):
        if not self.enabled or not os.path.exists(self.path):
            return []
        with self._lock:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-max(1, min(limit, 5000)):]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
