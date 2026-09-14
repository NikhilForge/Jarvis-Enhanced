"""Continuous learning loop.

Every turn is logged as a trainable sample. Operator feedback ("no, not like
that" / "perfect") turns the pair into a DPO preference row. training/ scripts
consume these JSONL files directly — the assistant improves from real use.
"""
import json, os, re, time
from core.bus import BUS

GOOD = re.compile(r"\b(perfect|nice|thanks|thank you|exactly|that'?s right|good job)\b", re.I)
BAD = re.compile(r"\b(no,? not|wrong|that'?s not|stop doing|try again|not like that)\b", re.I)


class Learning:
    def __init__(self, cfg: dict):
        l = cfg.get("learning", {})
        self.enabled = l.get("enabled", True)
        self.sft_path = l.get("sft_path", "data/live_sft.jsonl")
        self.dpo_path = l.get("dpo_path", "data/live_dpo.jsonl")
        self.min_pairs = l.get("min_pairs_before_retrain", 200)
        os.makedirs("data", exist_ok=True)
        self.last = None
        self.counts = {"sft": self._lines(self.sft_path), "dpo": self._lines(self.dpo_path)}

    @staticmethod
    def _lines(p):
        return sum(1 for _ in open(p, encoding="utf-8")) if os.path.exists(p) else 0

    def _append(self, path, obj, key):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.counts[key] += 1

    def record_turn(self, user: str, reply: str, tool_calls=None):
        if not self.enabled:
            return
        self.last = {"user": user, "reply": reply, "tools": tool_calls or [], "ts": time.time()}
        self._append(self.sft_path, {
            "messages": [{"role": "user", "content": user},
                         {"role": "assistant", "content": reply}],
            "tools": tool_calls or [],
        }, "sft")

    def feedback(self, utterance: str) -> str | None:
        """Called with the *next* utterance; converts praise/criticism into signal."""
        if not self.enabled or not self.last:
            return None
        if GOOD.search(utterance):
            self._append(self.dpo_path, {"prompt": self.last["user"],
                                         "chosen": self.last["reply"],
                                         "rejected": ""}, "dpo")
            BUS.emit("learn", f"positive signal captured · {self.counts['dpo']} DPO rows", value=self.counts["dpo"])
            return "positive"
        if BAD.search(utterance):
            self._append(self.dpo_path, {"prompt": self.last["user"],
                                         "chosen": "",
                                         "rejected": self.last["reply"],
                                         "correction_hint": utterance}, "dpo")
            BUS.emit("learn", f"correction captured · {self.counts['dpo']} DPO rows", value=self.counts["dpo"])
            return "negative"
        return None

    def ready_to_retrain(self) -> bool:
        return self.counts["dpo"] >= self.min_pairs

    def stats(self):
        return {**self.counts, "ready": self.ready_to_retrain(), "target": self.min_pairs}
