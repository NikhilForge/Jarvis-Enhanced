"""Local openWakeWord wake-word detection with automatic model provisioning."""
from pathlib import Path

import numpy as np
from core.bus import BUS


class WakeWord:
    def __init__(self, cfg: dict):
        w = cfg["wakeword"]
        self.enabled = bool(w.get("enabled", True))
        self.threshold = float(w.get("threshold", 0.5))
        self.name = str(w.get("model", "hey_jarvis"))
        self.custom = w.get("custom_model_path")
        self.model = None

        if not self.enabled:
            return

        from openwakeword.model import Model

        if self.custom:
            model_path = Path(self.custom)
            if not model_path.is_absolute():
                model_path = Path.cwd() / model_path
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Custom wake-word model not found: {model_path}"
                )
            models = [str(model_path)]
        else:
            # openWakeWord pip packages do not necessarily ship the pre-trained
            # model files. Provision the requested official model on first run.
            import openwakeword
            from openwakeword import utils as ow_utils

            model_filename = f"{self.name}_v0.1.onnx"
            package_models_dir = (
                Path(openwakeword.__file__).resolve().parent / "resources" / "models"
            )
            model_path = package_models_dir / model_filename

            if not model_path.exists():
                BUS.emit("wake", f"downloading wake-word model '{self.name}' ...")
                ow_utils.download_models(model_names=[self.name])

            # Re-check after download. This gives a clear error instead of an
            # opaque ONNXRuntime NO_SUCHFILE exception.
            if not model_path.exists():
                candidates = list(package_models_dir.glob(f"{self.name}*.onnx"))
                if candidates:
                    model_path = candidates[0]
                else:
                    raise FileNotFoundError(
                        f"openWakeWord model '{self.name}' was not installed at "
                        f"{package_models_dir}. Try: "
                        f"python -c \"from openwakeword import utils; "
                        f"utils.download_models(['{self.name}'])\""
                    )
            models = [str(model_path)]

        self.model = Model(
            wakeword_models=models,
            inference_framework="onnx",
            vad_threshold=w.get("vad_gate", 0.3),
        )
        BUS.emit("wake", f"wake word '{self.name}' armed (onnx int8, cpu)")

    def detect(self, frame: bytes) -> float:
        if not self.enabled or self.model is None:
            return 0.0
        pcm = np.frombuffer(frame, dtype=np.int16)
        scores = self.model.predict(pcm)
        return float(max(scores.values())) if scores else 0.0

    def triggered(self, frame: bytes) -> bool:
        s = self.detect(frame)
        if s >= self.threshold:
            BUS.emit("wake", f"wake word fired · confidence {s:.2f}")
            self.model.reset()
            return True
        return False
