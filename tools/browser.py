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


def _ensure(ctx):
    cfg = (ctx or {}).get("config", {}).get("tools", {}).get("browser", {})
    if not cfg.get("enabled", True):
        raise RuntimeError("browser automation is disabled in config.yaml")
    if _STATE["page"] is not None and not _STATE["page"].is_closed():
        return _STATE["page"]
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
    _STATE["context"] = _STATE["pw"].chromium.launch_persistent_context(profile, **launch)
    _STATE["page"] = _STATE["context"].pages[0] if _STATE["context"].pages else _STATE["context"].new_page()
    BUS.emit("browser", "persistent browser ready")
    return _STATE["page"]


def _page(ctx):
    return _ensure(ctx)


@tool("browser.open", "Open a URL in the visible JARVIS browser. Use https URLs when possible.",
      {"url": {"type": "string"}}, privileged=True)
def browser_open(url, ctx=None):
    page = _page(ctx)
    page.goto(url, wait_until="domcontentloaded", timeout=(ctx or {}).get("config", {}).get("tools", {}).get("browser", {}).get("timeout_ms", 15000))
    return f"opened {page.url} — {page.title()[:160]}"


@tool("browser.search", "Search the web in the visible browser using a search engine.",
      {"query": {"type": "string"}}, privileged=True)
def browser_search(query, ctx=None):
    page = _page(ctx)
    from urllib.parse import quote_plus
    page.goto("https://www.google.com/search?q=" + quote_plus(query), wait_until="domcontentloaded", timeout=15000)
    return f"search results ready for {query}: {page.title()[:120]}"


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
        p.goto(url, wait_until="domcontentloaded", timeout=15000)
    _STATE["page"] = p
    return f"new tab {p.url}"
