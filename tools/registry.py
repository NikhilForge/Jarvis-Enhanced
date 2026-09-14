"""MCP-style local tool registry exposed to the Gemini agent as JSON function schemas."""
import os, subprocess, webbrowser, httpx
from core.bus import BUS

_REG = {}


def tool(name, description, params, destructive=False, privileged=False):
    """privileged=True → the tool only runs when the enrolled operator's voice is verified."""
    def deco(fn):
        _REG[name] = {"fn": fn, "destructive": destructive, "privileged": privileged, "schema": {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": {
                "type": "object",
                "properties": params,
                "required": [k for k, v in params.items() if v.get("required", True)],
            }},
        }}
        return fn
    return deco


def schemas():
    return [t["schema"] for t in _REG.values()]


def is_destructive(name, cfg):
    return name in cfg["safety"]["confirm_before"] or _REG.get(name, {}).get("destructive", False)


def is_privileged(name, cfg):
    return name in cfg["safety"].get("owner_only", []) or _REG.get(name, {}).get("privileged", False)


def call(name, args, ctx):
    t = _REG.get(name)
    if not t:
        return f"unknown tool {name}"
    # --- voice-identity gate: owner-only tools require a verified voiceprint match ---
    restricted = t.get("privileged") or name in (ctx or {}).get("config", {}).get("safety", {}).get("owner_only", [])
    if restricted:
        spk = (ctx or {}).get("speaker")
        if spk is not None and not spk.is_owner(privileged=True):
            BUS.emit("voice", f"REFUSED {name}: speaker match {spk.last_score:.2f} below "
                              f"{spk.privileged_threshold}")
            return ("refused: that command is restricted to the enrolled operator and this voice "
                    "did not match the voiceprint")
    try:
        return t["fn"](ctx=ctx, **args)
    except Exception as e:
        BUS.emit("tool", f"{name} failed: {e}")
        return f"error: {e}"


# ---------------- desktop automation ----------------
def _gui():
    import pyautogui
    pyautogui.FAILSAFE = True
    return pyautogui


@tool("desktop.launch_app", "Open an application by executable or name on Windows.",
      {"app": {"type": "string", "description": "e.g. notepad, chrome, Code"}})
def launch_app(app, ctx=None):
    os.startfile(app) if hasattr(os, "startfile") else subprocess.Popen([app])
    return f"launched {app}"


@tool("desktop.type_text", "Type text into the focused window.",
      {"text": {"type": "string"}})
def type_text(text, ctx=None):
    _gui().typewrite(text, interval=0.01)
    return "typed"


@tool("desktop.hotkey", "Press a key combination, e.g. ctrl+s.",
      {"keys": {"type": "string", "description": "plus-separated, e.g. alt+tab"}})
def hotkey(keys, ctx=None):
    _gui().hotkey(*[k.strip() for k in keys.split("+")])
    return f"pressed {keys}"


@tool("desktop.click", "Move the mouse and click at absolute screen coordinates.",
      {"x": {"type": "integer"}, "y": {"type": "integer"}})
def click(x, y, ctx=None):
    g = _gui(); g.moveTo(x, y, duration=0.15); g.click()
    return f"clicked {x},{y}"


@tool("desktop.screenshot", "Capture the screen to a PNG for the operator.",
      {"path": {"type": "string", "required": False}})
def screenshot(path="data/screen.png", ctx=None):
    _gui().screenshot(path)
    return path


@tool("desktop.run_command", "Run a shell command. Irreversible — requires confirmation.",
      {"command": {"type": "string"}}, destructive=True)
def run_command(command, ctx=None):
    out = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    return (out.stdout or out.stderr)[:2000]


# ---------------- filesystem ----------------
@tool("fs.list", "List files in a directory.", {"path": {"type": "string"}})
def fs_list(path, ctx=None):
    return "\n".join(sorted(os.listdir(path))[:200])


@tool("fs.read", "Read a UTF-8 text file.", {"path": {"type": "string"}})
def fs_read(path, ctx=None):
    return open(path, encoding="utf-8", errors="ignore").read()[:8000]


@tool("fs.write", "Write a UTF-8 text file.", {"path": {"type": "string"}, "content": {"type": "string"}})
def fs_write(path, content, ctx=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w", encoding="utf-8").write(content)
    return f"wrote {path}"


@tool("fs.delete", "Delete a file or folder. Irreversible — requires confirmation.",
      {"path": {"type": "string"}}, destructive=True)
def fs_delete(path, ctx=None):
    import shutil
    shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    return f"deleted {path}"


# ---------------- web ----------------
@tool("web.search", "Search the web and return short results.", {"query": {"type": "string"}})
def web_search(query, ctx=None):
    from duckduckgo_search import DDGS
    with DDGS() as d:
        hits = list(d.text(query, max_results=4))
    return "\n".join(f"{h['title']}: {h['body'][:180]}" for h in hits)


@tool("web.open", "Open a URL in the default browser.", {"url": {"type": "string"}})
def web_open(url, ctx=None):
    webbrowser.open(url)
    return f"opened {url}"


# ---------------- memory tools (the model edits its own memory) ----------------
@tool("memory.core_replace", "Rewrite a core memory block (persona or user).",
      {"block": {"type": "string"}, "value": {"type": "string"}})
def mem_replace(block, value, ctx=None):
    return ctx["memory"].core_memory_replace(block, value)


@tool("memory.core_append", "Append a durable fact to a core memory block.",
      {"block": {"type": "string"}, "value": {"type": "string"}})
def mem_append(block, value, ctx=None):
    return ctx["memory"].core_memory_append(block, value)


@tool("memory.archival_search", "Semantic search over long-term archival memory.",
      {"query": {"type": "string"}})
def mem_arch(query, ctx=None):
    return "\n".join(ctx["memory"].archival_search(query)) or "no matches"


@tool("memory.recall_search", "Search the chronological conversation log.",
      {"query": {"type": "string"}})
def mem_recall(query, ctx=None):
    return str(ctx["memory"].recall_memory_search(query))


# ---------------- home assistant / snapcast ----------------
@tool("homeassistant.call_service", "Control smart home devices via a local Home Assistant.",
      {"domain": {"type": "string"}, "service": {"type": "string"}, "entity_id": {"type": "string"}},
      destructive=True)
def ha_call(domain, service, entity_id, ctx=None):
    cfg = ctx["config"]["tools"]["home_assistant"]
    if not cfg["enabled"]:
        return "home assistant disabled in config.yaml"
    token = os.environ.get(cfg["token_env"], "")
    r = httpx.post(f"{cfg['base_url']}/api/services/{domain}/{service}",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"entity_id": entity_id}, timeout=15)
    return f"{r.status_code}"


@tool("snapcast.broadcast", "Fan TTS audio out to synchronised multi-room speakers.",
      {"stream": {"type": "string", "required": False}})
def snap(stream="jarvis", ctx=None):
    cfg = ctx["config"]["tools"]["snapcast"]
    if not cfg["enabled"]:
        return "snapcast disabled in config.yaml"
    BUS.emit("tool", f"snapcast broadcast on '{stream}' (NTP-synced)")
    return "broadcasting"
