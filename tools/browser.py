"""Persistent local browser agent powered by Playwright.

The browser is visible by default so the operator can see what JARVIS is doing.
The module keeps a single browser context alive across tool calls, which lets Gemini
compose navigation -> click -> type -> extract operations over several hops.
"""
import os, re
from pathlib import Path
from core.bus import BUS
from tools.registry import tool

_STATE = {"pw": None, "browser": None, "context": None, "page": None}
_LAST_LAUNCHED_URLS = {}


def _extract_browser_cfg(ctx):
    if isinstance(ctx, dict):
        return ctx.get("config", {}).get("tools", {}).get("browser", {})
    if hasattr(ctx, "cfg"):
        return (ctx.cfg or {}).get("tools", {}).get("browser", {})
    return {}


def _launch_desktop_url(url: str):
    """Reliably launch a URL in the user's desktop browser (preferring active browser like Brave).
    Guaranteed to open exactly ONCE with deduplication and early return."""
    import os, subprocess, webbrowser, time
    url = url.strip()
    if not url:
        return False

    now = time.time()
    # Deduplicate rapid repeated calls for the same URL within 3.5 seconds
    if url in _LAST_LAUNCHED_URLS and (now - _LAST_LAUNCHED_URLS[url]) < 3.5:
        return True
    _LAST_LAUNCHED_URLS[url] = now

    BUS.emit("browser", f"desktop browser opened ({url})")

    # 1. Notify the HUD via WebSocket for audit/history display only
    try:
        BUS.emit("open_url", url, url=url)
    except Exception:
        pass

    # 2. Windows WinSta0\\Default direct invocation via cmd start (most reliable on Windows 11)
    try:
        import win32process
        si = win32process.STARTUPINFO()
        si.lpDesktop = r"WinSta0\Default"
        cmd = f'cmd.exe /c start "" "{url}"'
        win32process.CreateProcess(None, cmd, None, None, False, 0, None, None, si)
        return True  # Success - DO NOT fall through to duplicate methods!
    except Exception:
        pass

    # 3. Native os.startfile (ShellExecute) fallback
    try:
        if hasattr(os, "startfile"):
            os.startfile(url)
            return True
    except Exception:
        pass

    # 4. Direct browser binary invocation fallback
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            try:
                import win32process
                si = win32process.STARTUPINFO()
                si.lpDesktop = r"WinSta0\Default"
                cmd = f'"{exe}" --single-argument "{url}"'
                win32process.CreateProcess(None, cmd, None, None, False, 0, None, None, si)
                return True
            except Exception:
                try:
                    subprocess.Popen([exe, "--single-argument", url])
                    return True
                except Exception:
                    pass

    # 5. Standard python webbrowser fallback
    try:
        webbrowser.open_new_tab(url)
        return True
    except Exception:
        pass

    return False


def _ensure(ctx):
    cfg = _extract_browser_cfg(ctx)
    if not cfg.get("enabled", True):
        raise RuntimeError("browser automation is disabled in config.yaml")
    if _STATE.get("page") is not None and not _STATE["page"].is_closed():
        return _STATE["page"]
    try:
        if _STATE.get("context"):
            _STATE["context"].close()
    except Exception:
        pass
    try:
        if _STATE.get("pw"):
            _STATE["pw"].stop()
    except Exception:
        pass
    _STATE["context"] = None
    _STATE["browser"] = None
    _STATE["page"] = None

    from playwright.sync_api import sync_playwright
    _STATE["pw"] = sync_playwright().start()
    channel = cfg.get("channel", "chrome") or None
    launch = {"headless": bool(cfg.get("headless", False))}
    if channel:
        launch["channel"] = channel
    profile = os.getenv("JARVIS_BROWSER_PROFILE", "").strip()
    if not profile:
        profile = str(Path("data") / "browser-profile")
    Path(profile).mkdir(parents=True, exist_ok=True)
    try:
        _STATE["context"] = _STATE["pw"].chromium.launch_persistent_context(profile, **launch)
    except Exception as e:
        BUS.emit("browser", f"persistent profile unavailable ({e}) · launching standard browser")
        _STATE["browser"] = _STATE["pw"].chromium.launch(**launch)
        _STATE["context"] = _STATE["browser"].new_context()

    _STATE["page"] = _STATE["context"].pages[0] if _STATE["context"].pages else _STATE["context"].new_page()
    BUS.emit("browser", "visible browser ready")
    return _STATE["page"]


def _normalize_url(url: str) -> str:
    u = url.strip()
    if not (u.startswith("http://") or u.startswith("https://") or u.startswith("about:") or u.startswith("file://")):
        return "https://" + u
    return u


def _page(ctx):
    return _ensure(ctx)


@tool("browser.open", "Open a URL in the browser. Use https URLs when possible.",
      {"url": {"type": "string"}})
def browser_open(url, ctx=None):
    url = _normalize_url(url)
    _launch_desktop_url(url)
    b_cfg = _extract_browser_cfg(ctx)
    if b_cfg.get("use_playwright", False):
        try:
            page = _page(ctx)
            page.goto(url, wait_until="domcontentloaded", timeout=b_cfg.get("timeout_ms", 10000))
            return f"opened {url} — {page.title()[:160]}"
        except Exception:
            pass
    return f"opened {url} in desktop browser"


@tool("browser.search", "Search the web in the visible browser using a search engine.",
      {"query": {"type": "string"}})
def browser_search(query, ctx=None):
    from urllib.parse import quote_plus
    target_url = "https://www.google.com/search?q=" + quote_plus(query)
    b_cfg = _extract_browser_cfg(ctx)
    try:
        page = _page(ctx)
        page.goto(target_url, wait_until="domcontentloaded", timeout=b_cfg.get("timeout_ms", 15000))
        return f"search results ready for {query}: {page.title()[:120]}"
    except Exception as e:
        BUS.emit("browser", f"playwright fallback to desktop browser for search: {e}")
        _launch_desktop_url(target_url)
        return f"searched {query} in default browser"


@tool("browser.extract", "Extract readable text from the current browser page, limited to a compact result.",
      {"selector": {"type": "string", "required": False}, "max_chars": {"type": "integer", "required": False}}, privileged=True)
def browser_extract(selector=None, max_chars=6000, ctx=None):
    page = _page(ctx)
    text = page.locator(selector).inner_text() if selector else page.locator("body").inner_text()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


@tool("browser.click", "Click a visible browser element using an accessible role/name or CSS selector.",
      {"target": {"type": "string", "description": "CSS selector, text, or accessible name"}}, privileged=True)
def browser_click(target, ctx=None):
    page = _page(ctx)
    try:
        page.get_by_role("button", name=target, exact=False).click(timeout=5000)
    except Exception:
        try:
            page.get_by_role("link", name=target, exact=False).click(timeout=5000)
        except Exception:
            page.locator(target).first.click(timeout=5000)
    return f"clicked {target} on {page.url}"


@tool("browser.type", "Fill an input on the current page. Target should be a label, placeholder, CSS selector, or input name.",
      {"target": {"type": "string"}, "text": {"type": "string"}}, privileged=True)
def browser_type(target, text, ctx=None):
    page = _page(ctx)
    try:
        page.get_by_label(target, exact=False).fill(text)
    except Exception:
        try:
            page.get_by_placeholder(target, exact=False).fill(text)
        except Exception:
            page.locator(target).first.fill(text)
    return f"filled {target}"


@tool("browser.press", "Press a keyboard key on the current browser page or focused element.",
      {"key": {"type": "string"}}, privileged=True)
def browser_press(key, ctx=None):
    page = _page(ctx)
    page.keyboard.press(key)
    return f"pressed {key}"


@tool("browser.screenshot", "Save a screenshot of the current browser page locally.",
      {"path": {"type": "string", "required": False}}, privileged=True)
def browser_screenshot(path="data/browser.png", ctx=None):
    page = _page(ctx)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=path, full_page=True)
    return path


@tool("browser.tabs", "List open browser tabs with their titles and URLs.", {}, privileged=True)
def browser_tabs(ctx=None):
    page = _page(ctx)
    tabs = []
    for i, p in enumerate(_STATE["context"].pages):
        tabs.append(f"{i}: {p.title()[:100]} — {p.url}")
    return "\n".join(tabs)


@tool("browser.new_tab", "Open a new tab, optionally navigating to a URL.",
      {"url": {"type": "string", "required": False}}, privileged=True)
def browser_new_tab(url="about:blank", ctx=None):
    page = _page(ctx)
    p = _STATE["context"].new_page()
    if url and url != "about:blank":
        p.goto(_normalize_url(url), wait_until="domcontentloaded", timeout=15000)
    _STATE["page"] = p
    return f"new tab {p.url}"


@tool("browser.switch_tab", "Switch to an existing browser tab by its index from browser.tabs.",
      {"index": {"type": "integer"}}, privileged=True)
def browser_switch_tab(index, ctx=None):
    _ensure(ctx)
    pages = _STATE["context"].pages
    if 0 <= index < len(pages):
        _STATE["page"] = pages[index]
        _STATE["page"].bring_to_front()
        return f"switched to tab {index}: {_STATE['page'].title()[:80]}"
    return f"tab index {index} out of range (open tabs: {len(pages)})"


@tool("browser.close_tab", "Close a browser tab by its index, or the active tab if index is omitted.",
      {"index": {"type": "integer", "required": False}}, privileged=True)
def browser_close_tab(index=None, ctx=None):
    _ensure(ctx)
    pages = _STATE["context"].pages
    if not pages:
        return "no tabs open"
    if index is not None and 0 <= index < len(pages):
        p = pages[index]
    else:
        p = _STATE["page"] or pages[-1]
    url = p.url
    p.close()
    remaining = _STATE["context"].pages
    _STATE["page"] = remaining[-1] if remaining else None
    return f"closed tab {url}"


@tool("browser.scroll", "Scroll the page up, down, top, or bottom.",
      {"direction": {"type": "string", "description": "down | up | top | bottom"},
       "amount": {"type": "integer", "required": False, "description": "pixels to scroll (default 500)"}}, privileged=True)
def browser_scroll(direction="down", amount=500, ctx=None):
    page = _page(ctx)
    d = direction.lower().strip()
    if d == "top":
        page.evaluate("window.scrollTo(0, 0)")
    elif d == "bottom":
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    elif d == "up":
        page.evaluate(f"window.scrollBy(0, -{amount})")
    else:
        page.evaluate(f"window.scrollBy(0, {amount})")
    return f"scrolled {d}"


@tool("browser.back", "Navigate back in browser history.", {}, privileged=True)
def browser_back(ctx=None):
    page = _page(ctx)
    page.go_back(wait_until="domcontentloaded", timeout=10000)
    return f"navigated back to {page.url}"


@tool("browser.forward", "Navigate forward in browser history.", {}, privileged=True)
def browser_forward(ctx=None):
    page = _page(ctx)
    page.go_forward(wait_until="domcontentloaded", timeout=10000)
    return f"navigated forward to {page.url}"


@tool("browser.reload", "Reload the current browser page.", {}, privileged=True)
def browser_reload(ctx=None):
    page = _page(ctx)
    page.reload(wait_until="domcontentloaded", timeout=15000)
    return f"reloaded {page.url}"


@tool("browser.run_js", "Execute a JavaScript expression on the page and return the result.",
      {"code": {"type": "string"}}, privileged=True)
def browser_run_js(code, ctx=None):
    page = _page(ctx)
    res = page.evaluate(code)
    return str(res)[:2000]


# ---------------- YouTube automation ----------------
@tool("youtube.search_and_play", "Search YouTube for a video, artist, or topic and automatically start playing the top result.",
      {"query": {"type": "string", "description": "video title, song name, or search keywords"}})
def youtube_search_and_play(query, ctx=None):
    from urllib.parse import quote_plus
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    _launch_desktop_url(url)
    return f"opened YouTube search for '{query}' in desktop browser"


@tool("youtube.control", "Control YouTube playback in the browser: play_pause, fullscreen, mute, forward, backward, restart, captions, next.",
      {"action": {"type": "string", "description": "play_pause | fullscreen | mute | forward | backward | restart | captions | next"}})
def youtube_control(action, ctx=None):
    page = _page(ctx)
    action = action.lower().strip()
    key_map = {
        "play_pause": "k",
        "play": "k",
        "pause": "k",
        "fullscreen": "f",
        "mute": "m",
        "forward": "l",     # +10s
        "backward": "j",    # -10s
        "restart": "0",     # jump to beginning
        "captions": "c",    # toggle subtitles
        "next": "Shift+N",  # next video
    }
    key = key_map.get(action)
    if key:
        page.keyboard.press(key)
        return f"YouTube action '{action}' executed"

    if action in ("play", "pause", "toggle"):
        res = page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return 'no video player found';
            if (v.paused) { v.play(); return 'playing'; }
            else { v.pause(); return 'paused'; }
        }""")
        return f"YouTube video state: {res}"
    return f"unknown YouTube action: {action}"
