"""Word Error Rate for the STT stage. Record 50 commands, measure transcription quality.

    python eval/eval_wer.py --record 50     # guided recording session
    python eval/eval_wer.py                 # score data/wer_set/*.wav against transcripts.json
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml

def wer(ref, hyp):
    r, h = ref.lower().split(), hyp.lower().split()
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1): d[i][0] = i
    for j in range(len(h) + 1): d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1, d[i-1][j-1] + (r[i-1] != h[j-1]))
    return d[len(r)][len(h)] / max(1, len(r))

PROMPTS = ["jarvis open visual studio code", "shut down the pc in one minute",
           "what is eating my memory", "find the benchmark report in documents",
           "set the volume to twenty percent", "cancel the shutdown",
           "remember that I prefer dark mode", "search the web for qlora vram usage"]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--record", type=int, default=0)
    a = ap.parse_args()
    os.makedirs("data/wer_set", exist_ok=True)
    tpath = "data/wer_set/transcripts.json"
    refs = json.load(open(tpath)) if os.path.exists(tpath) else {}

    if a.record:
        import sounddevice as sd, soundfile as sf
        for i in range(a.record):
            p = PROMPTS[i % len(PROMPTS)]
            input(f"[{i+1}/{a.record}] Enter, then say: “{p}”  ")
            x = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="float32"); sd.wait()
            f = f"data/wer_set/{i:03d}.wav"; sf.write(f, x, 16000); refs[f] = p
        json.dump(refs, open(tpath, "w"), indent=2)

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    from core.stt import STT
    import soundfile as sf
    stt = STT(cfg)
    scores = []
    for f, ref in refs.items():
        x, _ = sf.read(f, dtype="float32")
        scores.append(wer(ref, stt.transcribe(x)))
    print(f"n={len(scores)}  WER={sum(scores)/max(1,len(scores)):.3f}")

if __name__ == "__main__":
    main()
