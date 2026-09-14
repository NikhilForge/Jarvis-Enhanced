"""Proactive layer: reminders, timers, routines and the morning briefing.

Runs on a CPU thread. Anything due is pushed straight into the TTS queue, so
Jarvis can speak first instead of only reacting.
"""
import json, os, threading, time
from dataclasses import dataclass, asdict
from typing import Callable, List

from core.bus import BUS


@dataclass
class Job:
    at: float
    text: str
    repeat_daily: bool = False
    tool: str | None = None
    args: dict | None = None


class Proactive:
    def __init__(self, cfg: dict, speak: Callable[[str], None], run_tool: Callable | None = None):
        self.cfg = cfg.get("proactive", {})
        self.path = self.cfg.get("jobs_path", "data/jobs.json")
        self.speak = speak
        self.run_tool = run_tool
        self.jobs: List[Job] = self._load()
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    # --- persistence ---
    def _load(self) -> List[Job]:
        if os.path.exists(self.path):
            return [Job(**j) for j in json.load(open(self.path))]
        return []

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        json.dump([asdict(j) for j in self.jobs], open(self.path, "w"), indent=2)

    # --- api ---
    def schedule_in(self, seconds: float, text: str, tool=None, args=None):
        self.jobs.append(Job(time.time() + seconds, text, False, tool, args))
        self._save()
        BUS.emit("proactive", f"scheduled +{int(seconds)}s · {text[:48]}")

    def schedule_daily(self, hhmm: str, text: str, tool=None, args=None):
        h, m = (int(x) for x in hhmm.split(":"))
        t = time.localtime()
        at = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, 0, 0, 0, -1))
        if at < time.time():
            at += 86400
        self.jobs.append(Job(at, text, True, tool, args))
        self._save()
        BUS.emit("proactive", f"daily routine at {hhmm} · {text[:48]}")

    def pending(self):
        return sorted(self.jobs, key=lambda j: j.at)

    def cancel_all(self):
        self.jobs.clear(); self._save()

    # --- loop ---
    def _loop(self):
        while not self._stop.is_set():
            now = time.time()
            for job in list(self.jobs):
                if job.at <= now:
                    BUS.emit("proactive", f"firing · {job.text[:60]}")
                    if job.tool and self.run_tool:
                        try:
                            self.run_tool(job.tool, job.args or {})
                        except Exception as e:
                            BUS.emit("proactive", f"tool failed: {e}")
                    if job.text:
                        self.speak(job.text)
                    if job.repeat_daily:
                        job.at += 86400
                    else:
                        self.jobs.remove(job)
                    self._save()
            time.sleep(1.0)
