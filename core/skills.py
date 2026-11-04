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


@skill(r"^\s*(stop|quiet|shut up|cancel that)\s*$")
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


@skill(r"\b(louder|quieter|mute)\b")
def _volume(m, ctx):
    from tools.registry import call
    word = m.group(1).lower()
    key = {"louder": "volumeup", "quieter": "volumedown", "mute": "volumemute"}.get(word)
    if not key:
        return None
    call("desktop.hotkey", {"keys": key}, ctx)
    return ""


# ---- Fast-path media controls (Spotify, YouTube, VLC, system) ----
@skill(r"^\s*(pause|resume|unpause|play\s*pause|pause\s+(the\s+)?(music|video|song)|resume\s+(the\s+)?(music|video|song))\s*$")
def _media_play_pause(m, ctx):
    from tools.registry import call
    call("media.play_pause", {}, ctx)
    return ""


@skill(r"^\s*(next\s+(song|track)|skip\s+(song|track)?|skip\s+this(\s+song)?)\s*$")
def _media_next(m, ctx):
    from tools.registry import call
    call("media.next", {}, ctx)
    return ""


@skill(r"^\s*(previous\s+(song|track)|prev\s+(song|track)?|last\s+(song|track))\s*$")
def _media_prev(m, ctx):
    from tools.registry import call
    call("media.previous", {}, ctx)
    return ""


@skill(r"^\s*stop\s+(the\s+)?(music|playback|audio|song|video)\s*$")
def _media_stop(m, ctx):
    from tools.registry import call
    call("media.stop", {}, ctx)
    return ""


# ---- Fast-path website & media launchers ----
@skill(
    r"\b(?:open|launch|go to|start)\s+(?:up\s+)?youtube\s+(?:and\s+|to\s+)?(?:search(?:\s+for)?|play|find|look\s+up)\s+(.+)\b"
    r"|\b(?:play|search(?:\s+for)?|find|look\s+up)\s+(.+?)\s+(?:on|in)\s+youtube\b"
    r"|\bsearch\s+youtube\s+for\s+(.+)\b"
    r"|\byoutube\s+search\s+(?:for\s+)?(.+)\b"
)
def _search_youtube(m, ctx):
    query = (m.group(1) or m.group(2) or m.group(3) or m.group(4) or "").strip()
    query = query.rstrip(".!?")
    if not query:
        return None
    from urllib.parse import quote_plus
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    from tools.browser import _launch_desktop_url
    import threading
    threading.Thread(target=_launch_desktop_url, args=(url,), daemon=True).start()
    return f"Searching YouTube for {query}."


@skill(r"\b(?:open|launch|go to|start)\s+(?:up\s+)?youtube\b")
def _open_youtube(m, ctx):
    from tools.browser import _launch_desktop_url
    import threading
    threading.Thread(target=_launch_desktop_url, args=("https://www.youtube.com",), daemon=True).start()
    return "Opening YouTube."


@skill(r"\b(?:open|launch|go to|start)\s+(?:up\s+)?(google|github|reddit|twitter|x|gmail)\b")
def _open_sites(m, ctx):
    site = m.group(1).lower()
    mapping = {
        "google": "https://www.google.com",
        "github": "https://www.github.com",
        "reddit": "https://www.reddit.com",
        "twitter": "https://www.twitter.com",
        "x": "https://www.x.com",
        "gmail": "https://mail.google.com",
    }
    url = mapping.get(site, f"https://www.{site}.com")
    from tools.browser import _launch_desktop_url
    import threading
    threading.Thread(target=_launch_desktop_url, args=(url,), daemon=True).start()
    return f"Opening {site.capitalize()}."


@skill(
    r"\b(?:open|launch|start)\s+(?:up\s+)?"
    r"(notepad|notes|calculator|calc|paint|mspaint|cmd|terminal|explorer|files|file explorer|"
    r"code|vscode|vs code|visual studio code|spotify|whatsapp|telegram|discord|vlc|media player|"
    r"chrome|google chrome|brave|edge|microsoft edge|word|ms word|winword|excel|ms excel|"
    r"powerpoint|ppt|slides|settings|camera|clock|alarms|task manager|taskmgr|"
    r"snipping tool|snip|sticky notes|steam|valorant|riot client)\b"
)
def _open_desktop_apps(m, ctx):
    app_name = m.group(1).lower().strip()
    from tools.registry import call
    import threading
    threading.Thread(target=call, args=("desktop.launch_app", {"app": app_name}, ctx), daemon=True).start()
    return f"Opening {app_name.capitalize()}."


def try_fast_path(text: str, ctx) -> Optional[str]:
    for pat, fn in _SKILLS:
        m = pat.search(text.strip())
        if m:
            out = fn(m, ctx)
            if out is not None:
                BUS.emit("skill", f"fast-path {fn.__name__} · LLM bypassed")
                return out
    return None
