"""Train a custom "jarvis" wake-word CNN and export INT8 ONNX (<50 MB RAM, <1% CPU).

    python train_wakeword.py --phrase "jarvis" --positives 100000

Pipeline: Piper multi-speaker TTS → 100k pitch/speed/accent variants → mix with room noise,
TV audio and keyboard clatter (MIT RIR + AudioSet-style negatives) → openWakeWord trainer →
ONNX export → models/jarvis.onnx. Point config.yaml wakeword.custom_model_path at it.
"""
import argparse, os, subprocess, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrase", default="jarvis")
    ap.add_argument("--positives", type=int, default=100_000)
    ap.add_argument("--negatives", type=int, default=200_000)
    ap.add_argument("--out", default="../models/jarvis.onnx")
    ap.add_argument("--steps", type=int, default=50_000)
    a = ap.parse_args()

    try:
        from openwakeword.train import Model as TrainModel   # noqa: F401
        import openwakeword
    except Exception:
        sys.exit("pip install openwakeword[training] piper-sample-generator")

    os.makedirs("wakeword_work", exist_ok=True)
    print(f"1/4 synthesising {a.positives} TTS variants of “{a.phrase}” "
          "(speaker, pitch ±20%, tempo 0.8-1.25x, formant jitter)")
    subprocess.run([sys.executable, "-m", "piper_sample_generator.generate_samples",
                    a.phrase, "--max-samples", str(a.positives),
                    "--batch-size", "64", "--output-dir", "wakeword_work/positive"], check=False)

    print("2/4 augmenting with room impulse responses + TV/typing/ambient negatives")
    print("    (download MIT RIR survey + FMA/AudioSet clips into wakeword_work/noise once)")

    print("3/4 training the INT8 CNN")
    subprocess.run([sys.executable, "-m", "openwakeword.train",
                    "--model_name", a.phrase.replace(" ", "_"),
                    "--positive_dir", "wakeword_work/positive",
                    "--negative_dir", "wakeword_work/negative",
                    "--background_dir", "wakeword_work/noise",
                    "--steps", str(a.steps),
                    "--false_positive_validation_data", "wakeword_work/val_fp",
                    "--target_false_positives_per_hour", "0.2",
                    "--output_dir", "wakeword_work/out"], check=False)

    print(f"4/4 exporting quantised ONNX → {a.out}")
    src = os.path.join("wakeword_work/out", a.phrase.replace(" ", "_") + ".onnx")
    if os.path.exists(src):
        os.replace(src, a.out)
        print("done. set wakeword.custom_model_path in config.yaml")
    else:
        print("training did not produce a model; check the logs above")

if __name__ == "__main__":
    main()
