"""Deterministic fast-path skills.

Anything matched here answers in ~15 ms without waking Gemini, which keeps
the GPU free and makes trivial commands feel instant. Unmatched text falls
through to the LLM.
"""
import datetime as _dt
import re
from typing import Callable, Optional

from core.bus import BUS

_SKILLS: list[tuple[re.Pattern, Callable]] = []


def skill(pattern: str):
    def deco(fn):
        _SKILLS.append((re.compile(pattern, re.I), fn))
        return fn
    return deco


@skill(r"\b(what'?s|what is|tell me) the time\b|\bwhat time is it\b")
def _time(m, ctx):
    return _dt.datetime.now().strftime("It's %I:%M %p.").lstrip("0")


@skill(r"\bwhat'?s (today'?s )?date\b|\bwhat day is it\b")
def _date(m, ctx):
    return _dt.datetime.now().strftime("Today is %A, %B %d.")


@skill(r"\b(stop|quiet|shut up|cancel that)\b")
def _stop(m, ctx):
    tts = ctx.get("tts") if isinstance(ctx, dict) else getattr(ctx, "tts", None)
    if tts and hasattr(tts, "stop"):
        tts.stop()
    return ""


@skill(r"\b(set|start) a timer for (\d+) (second|minute|hour)s?\b")
def _timer(m, ctx):
    n, unit = int(m.group(2)), m.group(3)
    secs = n * {"second": 1, "minute": 60, "hour": 3600}[unit]
    pro = ctx.get("proactive") if isinstance(ctx, dict) else getattr(ctx, "proactive", None)
    if pro:
        pro.schedule_in(secs, f"Your {n} {unit} timer is up.")
    return f"Timer set for {n} {unit}{'s' if n != 1 else ''}."


@skill(r"\b(volume|louder|quieter|mute)\b")
def _volume(m, ctx):
    from tools.registry import call
    word = m.group(1).lower()
    key = {"louder": "volumeup", "quieter": "volumedown", "mute": "volumemute"}.get(word)
    if not key:
        return None
    call("desktop.hotkey", {"keys": key}, ctx)
    return ""


def try_fast_path(text: str, ctx) -> Optional[str]:
    for pat, fn in _SKILLS:
        m = pat.search(text)
        if m:
            out = fn(m, ctx)
            if out is not None:
                BUS.emit("skill", f"fast-path {fn.__name__} · LLM bypassed")
                return out
    return None
