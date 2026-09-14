"""Speaker verification — 'is this actually the operator?'

A 256-d d-vector (Resemblyzer / GE2E encoder, CPU-only, ~25 MB RAM) is compared by cosine
similarity against the enrolled voiceprint. Privileged tools (shutdown, filesystem, shell,
smart home) are refused unless the voice on the microphone matches.
"""
import json, os
import numpy as np
from core.bus import BUS


class SpeakerID:
    def __init__(self, cfg: dict):
        s = cfg.get("speaker_id", {})
        self.enabled = s.get("enabled", True)
        self.threshold = s.get("threshold", 0.75)
        self.privileged_threshold = s.get("privileged_threshold", 0.82)
        self.print_path = s.get("voiceprint_path", "data/voiceprint.json")
        self.owner = s.get("owner_name", "operator")
        self.encoder = None
        self.reference = None
        self.last_score = 0.0
        if not self.enabled:
            return
        try:
            from resemblyzer import VoiceEncoder
            self.encoder = VoiceEncoder("cpu")
            BUS.emit("sys", "speaker encoder loaded (GE2E d-vector, CPU)")
        except Exception as e:
            BUS.emit("sys", f"speaker verification disabled: {e}")
            self.enabled = False
            return
        if os.path.exists(self.print_path):
            d = json.load(open(self.print_path))
            self.reference = np.array(d["embedding"], dtype=np.float32)
            self.owner = d.get("owner", self.owner)
            BUS.emit("sys", f"voiceprint loaded for {self.owner} ({d.get('clips', '?')} clips)")
        else:
            BUS.emit("sys", "no voiceprint yet — run: python scripts/enroll_voice.py")

    # ---- enrollment -----------------------------------------------------
    def embed(self, audio: np.ndarray) -> np.ndarray:
        from resemblyzer import preprocess_wav
        wav = preprocess_wav(audio.astype(np.float32), source_sr=16000)
        return self.encoder.embed_utterance(wav)

    def enroll(self, clips, owner: str):
        vecs = [self.embed(c) for c in clips]
        ref = np.mean(vecs, axis=0)
        ref = ref / (np.linalg.norm(ref) + 1e-9)
        os.makedirs(os.path.dirname(self.print_path) or ".", exist_ok=True)
        json.dump({"owner": owner, "clips": len(clips), "embedding": ref.tolist()},
                  open(self.print_path, "w"))
        self.reference = ref
        self.owner = owner
        return ref

    # ---- verification ---------------------------------------------------
    def score(self, audio: np.ndarray) -> float:
        if not self.enabled or self.reference is None:
            return 1.0
        try:
            v = self.embed(audio)
            v = v / (np.linalg.norm(v) + 1e-9)
            self.last_score = float(np.dot(v, self.reference))
        except Exception as e:
            BUS.emit("sys", f"speaker scoring failed: {e}")
            self.last_score = 0.0
        BUS.emit("voice", f"speaker match {self.last_score:.2f} vs {self.owner}",
                 value=self.last_score)
        return self.last_score

    def is_owner(self, privileged: bool = False) -> bool:
        if not self.enabled or self.reference is None:
            return True
        need = self.privileged_threshold if privileged else self.threshold
        return self.last_score >= need
