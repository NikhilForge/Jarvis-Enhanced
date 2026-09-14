"""Enrol the operator's voiceprint.

    python scripts/enroll_voice.py            # record 8 phrases from the mic
    python scripts/enroll_voice.py --wav a.wav b.wav

Averages GE2E d-vectors into data/voiceprint.json. Re-run any time your setup changes
(new mic, new room) — 20 seconds of speech is plenty.
"""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, yaml

PHRASES = [
    "Jarvis, wake up.",
    "Jarvis, shut down the PC in one minute.",
    "Open my downloads folder and find the benchmark report.",
    "What's on my calendar for tomorrow morning?",
    "Set the lab lights to twelve percent.",
    "Delete the old model checkpoints from the D drive.",
    "Summarise my unread mail and draft a reply.",
    "Never do that without asking me first.",
]


def record(seconds=4, rate=16000):
    import sounddevice as sd
    a = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="float32")
    sd.wait()
    return a.flatten()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", nargs="*", default=[])
    ap.add_argument("--seconds", type=float, default=4)
    a = ap.parse_args()
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    from core.speaker_id import SpeakerID
    spk = SpeakerID(cfg)
    if not spk.encoder:
        print("resemblyzer missing — pip install resemblyzer"); return

    clips = []
    if a.wav:
        import soundfile as sf
        for w in a.wav:
            x, sr = sf.read(w, dtype="float32")
            clips.append(x if x.ndim == 1 else x.mean(axis=1))
    else:
        n = cfg["speaker_id"].get("enroll_clips", 8)
        print(f"Recording {n} clips of {a.seconds:.0f}s each. Speak normally.\n")
        for i in range(n):
            input(f"[{i+1}/{n}] press Enter, then say: “{PHRASES[i % len(PHRASES)]}”  ")
            clips.append(record(a.seconds))
            print("   captured.")

    ref = spk.enroll(clips, cfg["speaker_id"]["owner_name"])
    sims = [float(np.dot(spk.embed(c) / np.linalg.norm(spk.embed(c)), ref)) for c in clips]
    print(f"\nvoiceprint saved → {spk.print_path}")
    print(f"self-similarity min {min(sims):.2f} / mean {sum(sims)/len(sims):.2f}")
    print("Set speaker_id.privileged_threshold just under the min if owner commands get refused.")


if __name__ == "__main__":
    main()
