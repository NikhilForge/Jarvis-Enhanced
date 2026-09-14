"""Summarise data/metrics.jsonl: TTFT, RTF, end-to-end percentiles and VRAM peaks."""
import json, os, statistics as st, sys

path = sys.argv[1] if len(sys.argv) > 1 else "data/metrics.jsonl"
if not os.path.exists(path):
    sys.exit(f"no metrics yet at {path} — run a few voice turns first")
rows = [json.loads(l) for l in open(path, encoding="utf-8")]

def p(name, key):
    xs = sorted(r[key] for r in rows if key in r)
    if not xs: return
    print(f"{name:<16} median {st.median(xs):8.1f}   p95 {xs[int(.95*(len(xs)-1))]:8.1f}   max {xs[-1]:8.1f}")

print(f"{len(rows)} turns\n")
p("stt (ms)", "stt_ms"); p("TTFT (ms)", "ttft_ms"); p("TTS first (ms)", "tts_first_ms")
p("end-to-end (ms)", "e2e_ms"); p("RTF", "rtf"); p("VRAM (GB)", "vram_gb"); p("RAM (GB)", "ram_gb")
breach = [r for r in rows if r.get("vram_gb", 0) > 6.0]
print(f"\nVRAM ceiling breaches: {len(breach)}")
