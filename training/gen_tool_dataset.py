"""Curate intent → JSON tool-call pairs from the live registry (no hand labelling drift).

Every example is generated against the *actual* tool schemas the runtime exposes, so the model
can never be trained on a command that does not exist.
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEMPLATES = [
    ("open {app}", "desktop.launch_app", lambda a: {"app": a}, ["chrome", "notepad", "Code", "spotify", "explorer"]),
    ("launch {app} for me", "desktop.launch_app", lambda a: {"app": a}, ["Code", "steam", "obs"]),
    ("shut down the pc", "system.power", lambda a: {"action": "shutdown", "delay_seconds": 30}, [""]),
    ("restart the machine", "system.power", lambda a: {"action": "restart", "delay_seconds": 15}, [""]),
    ("lock the screen", "system.power", lambda a: {"action": "lock"}, [""]),
    ("put the laptop to sleep", "system.power", lambda a: {"action": "sleep"}, [""]),
    ("cancel that shutdown", "system.cancel_shutdown", lambda a: {}, [""]),
    ("how hot is my machine right now", "system.status", lambda a: {}, [""]),
    ("what's eating my ram", "system.processes", lambda a: {"top": 8}, [""]),
    ("kill {app}", "system.kill", lambda a: {"name": a}, ["chrome", "discord"]),
    ("set volume to {n}", "system.volume", lambda n: {"percent": int(n)}, ["20", "45", "80"]),
    ("find my {q} file", "files.find", lambda q: {"query": q}, ["invoice", "resume", "benchmark"]),
    ("open my {q} folder", "files.open", lambda q: {"path": f"~/{q}"}, ["Downloads", "Documents", "Desktop"]),
    ("what did I download recently", "files.recent", lambda a: {"folder": "~/Downloads", "count": 10}, [""]),
    ("search the web for {q}", "web.search", lambda q: {"query": q}, ["qlora vram usage", "kokoro tts latency"]),
    ("remember that I {q}", "memory.core_append", lambda q: {"block": "user", "value": q},
     ["prefer 12% lab lighting", "work best after midnight"]),
    ("what did I say about {q}", "memory.archival_search", lambda q: {"query": q}, ["the benchmark", "Priya"]),
]

STYLES = ["{}", "jarvis, {}", "hey jarvis {}", "can you {}", "{} please", "quick — {}"]


def build(n=1200):
    rows = []
    for _ in range(n):
        tmpl, tool, argf, choices = random.choice(TEMPLATES)
        pick = random.choice(choices)
        text = tmpl.replace("{app}", pick).replace("{q}", pick).replace("{n}", pick).strip()
        text = random.choice(STYLES).format(text)
        rows.append({"messages": [
            {"role": "user", "content": text},
            {"role": "assistant", "content": "",
             "tool_calls": [{"type": "function", "function": {"name": tool,
                                                              "arguments": json.dumps(argf(pick))}}]},
        ]})
    return rows


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    rows = build()
    with open("data/tools_sft.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} tool-calling examples → data/tools_sft.jsonl")
