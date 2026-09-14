"""Live check: how well does the current mic input match the enrolled voiceprint?"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml, sounddevice as sd

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
from core.speaker_id import SpeakerID
spk = SpeakerID(cfg)
print("Speak for 4 seconds…")
a = sd.rec(int(4 * 16000), samplerate=16000, channels=1, dtype="float32"); sd.wait()
s = spk.score(a.flatten())
print(f"match {s:.3f} | recognised={s >= spk.threshold} | privileged={s >= spk.privileged_threshold}")
