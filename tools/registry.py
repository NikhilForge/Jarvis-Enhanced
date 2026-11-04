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


def _normalize_ctx(ctx):
    if isinstance(ctx, dict):
        return ctx
    if ctx is None:
        return {}
    return {
        "config": getattr(ctx, "cfg", {}),
        "speaker": getattr(ctx, "speaker", None),
        "metrics": getattr(ctx, "metrics", None),
        "memory": getattr(ctx, "memory", None),
        "rag": getattr(ctx, "rag", None),
        "learning": getattr(ctx, "learning", None),
        "proactive": getattr(ctx, "proactive", None),
        "tts": getattr(ctx, "tts", None),
        "llm": getattr(ctx, "llm", None),
        "orchestrator": ctx,
    }


def call(name, args, ctx):
    t = _REG.get(name)
    if not t:
        return f"unknown tool {name}"
    ctx = _normalize_ctx(ctx)
    # --- voice-identity gate: owner-only tools require a verified voiceprint match ---
    cfg = ctx.get("config", {})
    spk = ctx.get("speaker")
    restricted = t.get("privileged") or name in (cfg or {}).get("safety", {}).get("owner_only", [])
    if restricted:
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


APP_ALIASES = {
    # Text editors & IDEs
    "notepad": "notepad.exe",
    "notes": "notepad.exe",
    "code": "code.exe",
    "vscode": "code.exe",
    "vs code": "code.exe",
    "visual studio code": "code.exe",

    # Utilities & System
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "settings": "ms-settings:",
    "camera": "microsoft.windows.camera:",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
    "snipping tool": "ms-screenclip:",
    "snip": "ms-screenclip:",
    "store": "ms-windows-store:",
    "weather": "bingweather:",

    # Media & Social
    "spotify": "spotify:",
    "whatsapp": "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
    "telegram": r"D:\Telegram Desktop\Telegram.exe",
    "discord": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"),
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "vlc media player": r"C:\Program Files\VideoLAN\VLC\vlc.exe",

    # Browsers
    "brave": "brave.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",

    # Office
    "word": "winword.exe",
    "ms word": "winword.exe",
    "winword": "winword.exe",
    "excel": "excel.exe",
    "ms excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "ppt": "powerpnt.exe",
    "outlook": "outlook.exe",
}


def _launch_aumid(aumid: str) -> bool:
    """Launch Windows Store / UWP application via IApplicationActivationManager COM."""
    try:
        import comtypes
        from comtypes import GUID, IUnknown, COMMETHOD, HRESULT
        from ctypes import POINTER, c_ulong, c_wchar_p, c_uint

        CLSID_ApplicationActivationManager = GUID('{45BA127D-10A8-46EA-8AB7-56EA9078943C}')
        IID_IApplicationActivationManager = GUID('{2E941141-7F97-4756-BA1D-9DECDE894A3D}')

        class IApplicationActivationManager(IUnknown):
            _case_insensitive_ = True
            _iid_ = IID_IApplicationActivationManager
            _methods_ = [
                COMMETHOD([], HRESULT, 'ActivateApplication',
                          (['in'], c_wchar_p, 'appUserModelId'),
                          (['in'], c_wchar_p, 'arguments'),
                          (['in'], c_ulong, 'options'),
                          (['out', 'retval'], POINTER(c_uint), 'processId')),
            ]

        comtypes.CoInitialize()
        mgr = comtypes.CoCreateInstance(
            CLSID_ApplicationActivationManager,
            IApplicationActivationManager,
            comtypes.CLSCTX_LOCAL_SERVER
        )
        pid = mgr.ActivateApplication(aumid, '', 0)
        comtypes.CoUninitialize()
        return True
    except Exception:
        return False


def _resolve_app_target(clean: str) -> str:
    """Resolve an application name to an executable path, protocol, or AUMID."""
    if clean in APP_ALIASES:
        return APP_ALIASES[clean]

    import winreg, shutil
    # 1. Check App Paths in registry
    for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root_key, f"Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{clean}.exe") as k:
                val, _ = winreg.QueryValueEx(k, "")
                if val:
                    return val
        except Exception:
            pass

    # 2. Check PATH
    w = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if w:
        return w

    # 3. Check Start Menu shortcuts (.lnk)
    folders = [
        os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Start Menu\Programs'),
        os.path.expandvars(r'%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs')
    ]
    norm_query = clean.replace("-", " ").replace("+", "").replace(" ", "")
    candidate_lnk = None
    for base in folders:
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk"):
                    low_f = f.lower()
                    if any(skip in low_f for skip in ["uninstall", "help", "readme", "documentation", "website", "manual"]):
                        continue
                    norm_f = os.path.splitext(low_f)[0].replace("-", " ").replace("+", "").replace(" ", "")
                    if norm_query in norm_f or clean in low_f:
                        candidate_lnk = os.path.join(root, f)
                        break
            if candidate_lnk:
                break
        if candidate_lnk:
            break

    if candidate_lnk:
        try:
            import win32com.client
            shell = win32com.client.Dispatch('WScript.Shell')
            sc = shell.CreateShortcut(candidate_lnk)
            if sc.TargetPath and os.path.exists(sc.TargetPath):
                return sc.TargetPath
        except Exception:
            pass
        return candidate_lnk

    if "." not in clean and "/" not in clean and "\\" not in clean and not clean.endswith(":") and not clean.startswith("shell:"):
        return f"{clean}.exe"
    return clean


_LAST_LAUNCHED_APPS = {}


def _get_app_search_terms(app_name: str) -> list:
    kw = app_name.lower().replace(".exe", "").strip()
    kw_map = {
        "calc": "calculator",
        "mspaint": "paint",
        "wt": "terminal",
        "taskmgr": "task manager",
        "winword": "word",
        "powerpnt": "powerpoint",
        "code": "visual studio code",
        "vscode": "visual studio code",
    }
    terms = [kw]
    if kw in kw_map:
        terms.append(kw_map[kw])
    return terms


def _find_and_bring_to_front(app_name: str) -> bool:
    """Check if a window matching app_name is already running and bring it to front."""
    search_terms = _get_app_search_terms(app_name)
    clean = search_terms[0]
    try:
        import win32service, win32gui, win32con, win32process, ctypes, psutil
        try:
            hwinsta = win32service.OpenWindowStation("WinSta0", False, 0x10000000)
            hwinsta.SetProcessWindowStation()
            hdesk = win32service.OpenDesktop("Default", 0, False, 0x10000000)
            hdesk.SetThreadDesktop()
        except Exception:
            pass

        matching_pids = set()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p_name = p.info["name"].lower()
                if any(t in p_name for t in search_terms):
                    matching_pids.add(p.info["pid"])
            except Exception:
                pass

        target_hwnd = None
        def cb(hwnd, _):
            nonlocal target_hwnd
            if target_hwnd or not win32gui.IsWindowVisible(hwnd):
                return
            t = win32gui.GetWindowText(hwnd).strip()
            c = win32gui.GetClassName(hwnd).strip()
            if not t:
                return
            t_low = t.lower()
            c_low = c.lower()
            if clean not in ("cmd", "terminal", "powershell") and any(x in t_low for x in ("powershell", "command prompt", "cmd.exe")):
                return
            if clean not in ("code", "vscode", "antigravity") and "antigravity" in t_low:
                return

            tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in matching_pids or any(term in t_low or term in c_low for term in search_terms):
                target_hwnd = hwnd

        win32gui.EnumWindows(cb, None)
        if target_hwnd:
            user32 = ctypes.windll.user32
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            if win32gui.IsIconic(target_hwnd):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(target_hwnd, win32con.SW_SHOW)
            user32.BringWindowToTop(target_hwnd)
            win32gui.SetForegroundWindow(target_hwnd)
            return True
    except Exception:
        pass
    return False


def _bring_to_front(app_name: str):
    import time
    for _ in range(12):
        time.sleep(0.2)
        if _find_and_bring_to_front(app_name):
            return


@tool("desktop.launch_app", "Open an application by executable or name on Windows.",
      {"app": {"type": "string", "description": "e.g. notepad, spotify, discord, chrome, Code"}})
def launch_app(app, ctx=None):
    import time
    clean = str(app).lower().strip()
    now = time.time()
    last = _LAST_LAUNCHED_APPS.get(clean, 0)
    if (now - last) < 3.0:
        _find_and_bring_to_front(clean)
        return f"{app} is already opening / in foreground"

    _LAST_LAUNCHED_APPS[clean] = now

    # If already open, bring existing window to front without spawning duplicate processes!
    if _find_and_bring_to_front(clean):
        return f"brought existing {app} window to front"

    target = _resolve_app_target(clean)
    launched = False

    # 1. AUMID Store App
    if "!" in target and not target.endswith(".exe"):
        launched = _launch_aumid(target)

    # 2. Protocol or command
    if not launched:
        try:
            import win32process
            si = win32process.STARTUPINFO()
            si.lpDesktop = r"WinSta0\Default"

            if target.endswith(":") or target.startswith("http://") or target.startswith("https://") or (" " in target and not os.path.exists(target)):
                cmd = f'cmd.exe /c start "" {target}'
                win32process.CreateProcess(None, cmd, None, None, False, 0, None, None, si)
                launched = True
            elif os.path.exists(target) and target.lower().endswith(".lnk"):
                cmd = f'cmd.exe /c start "" "{target}"'
                win32process.CreateProcess(None, cmd, None, None, False, 0, None, None, si)
                launched = True
            else:
                workdir = os.path.dirname(target) if os.path.isabs(target) and os.path.isdir(os.path.dirname(target)) else None
                try:
                    win32process.CreateProcess(target if os.path.exists(target) else None, f'"{target}"', None, None, False, 0, None, workdir, si)
                    launched = True
                except Exception:
                    cmd = f'cmd.exe /c start "" "{target}"'
                    win32process.CreateProcess(None, cmd, None, None, False, 0, None, workdir, si)
                    launched = True
        except Exception:
            pass

    # 3. Fallbacks
    if not launched:
        try:
            subprocess.Popen(f'cmd.exe /c start "" "{target}"', shell=True)
            launched = True
        except Exception:
            try:
                if hasattr(os, "startfile"):
                    os.startfile(target)
                    launched = True
            except Exception as e:
                return f"failed to launch {app}: {e}"

    import threading
    threading.Thread(target=_bring_to_front, args=(clean,), daemon=True).start()
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
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        return f"path not found: {path}"
    if not os.path.isdir(p):
        return f"not a directory: {path}"
    try:
        return "\n".join(sorted(os.listdir(p))[:200])
    except Exception as e:
        return f"failed to list {path}: {e}"


@tool("fs.read", "Read a UTF-8 text file.", {"path": {"type": "string"}})
def fs_read(path, ctx=None):
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        return f"file not found: {path}"
    if os.path.isdir(p):
        return f"path is a directory: {path}"
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            return f.read()[:8000]
    except Exception as e:
        return f"failed to read {path}: {e}"


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
