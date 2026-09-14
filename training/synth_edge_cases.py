"""Synthetic data generation with a large teacher model (Lovable AI Gateway / OpenAI-compatible).

    set LOVABLE_API_KEY=...            (or OPENAI_API_KEY + --base-url)
    python synth_edge_cases.py --n 2000

Produces hard, realistic user queries plus the correct JSON tool call, including the tricky ones:
ambiguous references, multi-step chains, refusals, and unsafe requests that must be declined.
"""
import argparse, json, os, re, sys, time
import requests

TOOLS = ["desktop.launch_app", "desktop.type_text", "desktop.hotkey", "desktop.screenshot",
         "desktop.run_command", "system.power", "system.cancel_shutdown", "system.status",
         "system.processes", "system.kill", "system.volume", "files.find", "files.open",
         "files.move", "files.recent", "fs.list", "fs.read", "fs.write", "fs.delete",
         "web.search", "web.open", "memory.core_append", "memory.archival_search",
         "memory.recall_search", "homeassistant.call_service", "snapcast.broadcast"]

PROMPT = """Generate {k} diverse training examples for a local Windows voice assistant named Jarvis.
Only these tools exist: {tools}
Return a JSON array. Each item: {{"user": "...", "tool": "<name or null>", "args": {{...}}, "reply": "..."}}
Rules:
- 20% should need NO tool (chit-chat, questions) → "tool": null.
- 10% should be unsafe or impossible requests the assistant must refuse politely → "tool": null.
- Vary phrasing: slang, half sentences, background-noise fragments, accents in spelling.
- Replies: one or two spoken sentences, dry and concise, no markdown."""


def call(base, key, model, prompt):
    r = requests.post(f"{base}/chat/completions",
                      headers={"Lovable-API-Key": key, "Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"},
                      json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                      timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--model", default="google/gemini-2.5-flash")
    ap.add_argument("--base-url", default="https://ai.gateway.lovable.dev/v1")
    a = ap.parse_args()
    key = os.environ.get("LOVABLE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("set LOVABLE_API_KEY (or OPENAI_API_KEY) first")

    os.makedirs("data", exist_ok=True)
    out, seen = [], set()
    while len(out) < a.n:
        try:
            txt = call(a.base_url, key, a.model, PROMPT.format(k=a.batch, tools=", ".join(TOOLS)))
            block = re.search(r"\[.*\]", txt, re.S)
            items = json.loads(block.group(0)) if block else []
        except Exception as e:
            print("retry:", e); time.sleep(4); continue
        for it in items:
            u = (it.get("user") or "").strip()
            if not u or u in seen or (it.get("tool") and it["tool"] not in TOOLS):
                continue           # hard filter: never train on a hallucinated tool name
            seen.add(u)
            msg = {"role": "assistant", "content": it.get("reply", "")}
            if it.get("tool"):
                msg["tool_calls"] = [{"type": "function",
                                      "function": {"name": it["tool"],
                                                   "arguments": json.dumps(it.get("args", {}))}}]
            out.append({"messages": [{"role": "user", "content": u}, msg]})
        print(f"{len(out)}/{a.n}")
    with open("data/synthetic_sft.jsonl", "w", encoding="utf-8") as f:
        for r in out[: a.n]:
            f.write(json.dumps(r) + "\n")
    print("wrote data/synthetic_sft.jsonl")
