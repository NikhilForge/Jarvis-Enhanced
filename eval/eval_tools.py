"""LLM-as-a-judge: tool-calling accuracy + persona adherence on a held-out set."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml

CASES = [
    ("jarvis shut down the pc", "system.power"),
    ("what's using all my ram", "system.processes"),
    ("open my downloads folder", "files.open"),
    ("find the invoice pdf", "files.find"),
    ("turn it down to twenty", "system.volume"),
    ("cancel that", "system.cancel_shutdown"),
    ("look up kokoro tts latency", "web.search"),
    ("remember I hate morning meetings", "memory.core_append"),
    ("how are you", None),
    ("format my c drive", None),
]

def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    from core.llm import LLM
    from tools import registry
    import tools.system  # noqa
    llm = LLM(cfg)
    ok = 0
    rows = []
    for text, expect in CASES:
        got, reply = None, ""
        for kind, payload in llm.chat_stream(
                [{"role": "system", "content": "You are JARVIS. Use tools when appropriate."},
                 {"role": "user", "content": text}], tools=registry.schemas()):
            if kind == "tool":
                got = payload["name"]; break
            reply += payload
        hit = (got == expect)
        ok += hit
        rows.append({"input": text, "expected": expect, "got": got, "reply": reply.strip()[:120], "pass": hit})
        print(("PASS " if hit else "FAIL ") + f"{text!r} → {got}")
    print(f"\ntool-call accuracy: {ok}/{len(CASES)} = {ok/len(CASES):.0%}")
    json.dump(rows, open("data/eval_tools.json", "w"), indent=2)
    print("persona adherence: score data/eval_tools.json with a judge model "
          "(criteria: ≤2 sentences, no markdown, no emoji, dry tone)")

if __name__ == "__main__":
    main()
