"""Owner-only OS control: power, sessions, processes, personal folders.

Every tool here is marked privileged=True, so registry.call() refuses to run it unless the
speaker verification score for the *current utterance* clears speaker_id.privileged_threshold.
A stranger can ask Jarvis the weather; only the enrolled operator can shut the machine down.
"""
import os, shutil, subprocess, glob
from tools.registry import tool
from core.bus import BUS

IS_WIN = os.name == "nt"


@tool("system.power", "Shut down, restart, sleep, lock or sign out of the PC. Owner only.",
      {"action": {"type": "string", "description": "shutdown | restart | sleep | lock | logoff"},
       "delay_seconds": {"type": "integer", "required": False}},
      destructive=True, privileged=True)
def power(action, delay_seconds=15, ctx=None):
    action = action.lower().strip()
    if not IS_WIN:
        return f"simulated {action} (non-Windows host)"
    cmds = {
        "shutdown": ["shutdown", "/s", "/t", str(delay_seconds)],
        "restart": ["shutdown", "/r", "/t", str(delay_seconds)],
        "logoff": ["shutdown", "/l"],
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "cancel": ["shutdown", "/a"],
    }
    if action not in cmds:
        return f"unknown power action {action}"
    subprocess.Popen(cmds[action])
    BUS.emit("tool", f"system.power({action}) issued")
    return f"{action} scheduled in {delay_seconds}s — say 'cancel shutdown' to abort" \
        if action in ("shutdown", "restart") else f"{action} done"


@tool("system.cancel_shutdown", "Abort a pending shutdown or restart. Owner only.", {}, privileged=True)
def cancel_shutdown(ctx=None):
    if IS_WIN:
        subprocess.Popen(["shutdown", "/a"])
    return "pending power action aborted"


@tool("system.status", "Report CPU, RAM, VRAM, battery and disk usage.", {})
def status(ctx=None):
    import psutil
    v = ctx["metrics"].vram_gb() if ctx and ctx.get("metrics") else 0.0
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    d = psutil.disk_usage(os.path.abspath(os.sep))
    return (f"cpu {psutil.cpu_percent()}%, ram {psutil.virtual_memory().percent}%, "
            f"vram {v:.2f} GB, disk {d.percent}% used"
            + (f", battery {b.percent}%" if b else ""))


@tool("system.processes", "List the heaviest running processes.", {"top": {"type": "integer", "required": False}})
def processes(top=8, ctx=None):
    import psutil
    procs = sorted(psutil.process_iter(["name", "memory_info"]),
                   key=lambda p: (p.info["memory_info"].rss if p.info.get("memory_info") else 0),
                   reverse=True)[:top]
    return ", ".join(f"{p.info['name']} {p.info['memory_info'].rss/1e6:.0f} MB" for p in procs)


@tool("system.kill", "Terminate a process by name. Owner only.", {"name": {"type": "string"}},
      destructive=True, privileged=True)
def kill(name, ctx=None):
    import psutil
    n = 0
    for p in psutil.process_iter(["name"]):
        if p.info["name"] and p.info["name"].lower().startswith(name.lower()):
            try:
                p.terminate(); n += 1
            except Exception:
                pass
    return f"terminated {n} process(es) matching {name}"


@tool("system.volume", "Set the master output volume 0-100.", {"percent": {"type": "integer"}})
def volume(percent, ctx=None):
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        cast(iface, POINTER(IAudioEndpointVolume)).SetMasterVolumeLevelScalar(
            max(0, min(100, int(percent))) / 100.0, None)
        return f"volume {percent}%"
    except Exception as e:
        return f"volume control unavailable: {e}"


# ---------------- personal files (owner only) ----------------
@tool("files.find", "Search the operator's personal folders for files by name. Owner only.",
      {"query": {"type": "string"}, "root": {"type": "string", "required": False}},
      privileged=True)
def find(query, root=None, ctx=None):
    roots = [root] if root else [
        os.path.expanduser("~/Desktop"), os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"), os.path.expanduser("~/Pictures"),
    ]
    hits = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        for p in glob.iglob(os.path.join(r, "**", f"*{query}*"), recursive=True):
            hits.append(p)
            if len(hits) >= 20:
                break
    return "\n".join(hits) or f"nothing matching '{query}' in your personal folders"


@tool("files.open", "Open a file or folder in its default application. Owner only.",
      {"path": {"type": "string"}}, privileged=True)
def open_path(path, ctx=None):
    path = os.path.expanduser(path)
    if IS_WIN:
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
    return f"opened {path}"


@tool("files.move", "Move or rename a file. Owner only, irreversible.",
      {"src": {"type": "string"}, "dst": {"type": "string"}}, destructive=True, privileged=True)
def move(src, dst, ctx=None):
    shutil.move(os.path.expanduser(src), os.path.expanduser(dst))
    return f"moved {src} → {dst}"


@tool("files.recent", "List recently modified files in a folder. Owner only.",
      {"folder": {"type": "string", "required": False}, "count": {"type": "integer", "required": False}},
      privileged=True)
def recent(folder=None, count=10, ctx=None):
    folder = os.path.expanduser(folder or "~/Downloads")
    items = [(os.path.getmtime(os.path.join(folder, f)), f) for f in os.listdir(folder)]
    items.sort(reverse=True)
    return "\n".join(f for _, f in items[:count])
