"""TTS engine with support for instant SAPI5 (Windows native zero-lag) and Kokoro-82M ONNX."""
import re, threading, time, numpy as np
from core.bus import BUS

SENT_END = re.compile(r"(?<=[.!?])\s+")


def clean_for_speech(text: str) -> str:
    """Prepare text for TTS by removing markdown formatting, links, URLs, and code artifacts."""
    if not text:
        return ""
    # Remove markdown link syntax: [label](url) -> label
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bare URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove markdown symbols: asterisks, underscores, backticks, hashes, tildes
    text = re.sub(r'[*_`~#|]', '', text)
    # Replace newlines with spaces
    text = re.sub(r'[\r\n]+', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class TTS:
    def __init__(self, cfg: dict):
        t = cfg.get("tts", {})
        self.cfg = t
        self.engine_name = t.get("engine", "sapi").lower()
        self._sapi = None
        self._kokoro = None
        self._active_voice = None
        self._stopped = threading.Event()
        self._lock = threading.Lock()

        if self.engine_name in ("sapi", "pyttsx3", "windows", "system"):
            try:
                import pythoncom, win32com.client
                pythoncom.CoInitialize()
                v_test = win32com.client.Dispatch("SAPI.SpVoice")
                self._use_sapi = True
                BUS.emit("tts", "system TTS (SAPI5 via COM) ready · instant zero-lag speech")
                pythoncom.CoUninitialize()
            except Exception as e:
                BUS.emit("tts", f"SAPI5 init error ({e}) · falling back to Kokoro")
                self._use_sapi = False
                self.engine_name = "kokoro"
        else:
            self._use_sapi = False

        if self.engine_name == "kokoro" or not self._use_sapi:
            try:
                from kokoro_onnx import Kokoro
                self._kokoro = Kokoro(t["model_path"], t["voices_path"])
                BUS.emit("tts", f"kokoro-82m ready · voice {t.get('voice', 'af_heart')}")
            except Exception as e:
                BUS.emit("tts", f"kokoro error ({e})")

    def stop(self):
        """Cut playback immediately (barge-in)."""
        self._stopped.set()
        try:
            if self._active_voice:
                # SVSFPurgeBeforeSpeak (2) immediately terminates speech
                self._active_voice.Speak("", 2)
        except Exception:
            pass
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def say(self, text: str):
        clean_text = clean_for_speech(text)
        if not clean_text:
            return
        BUS.emit("tts", f'speaking "{clean_text[:60]}"')
        self._stopped.clear()

        # Fast SAPI path (instant zero lag, thread-safe COM)
        if getattr(self, "_use_sapi", False):
            with self._lock:
                stop_pulsing = threading.Event()
                def _pulse():
                    while not stop_pulsing.is_set():
                        BUS.emit("level", "", value=0.45)
                        time.sleep(0.08)
                        BUS.emit("level", "", value=0.15)
                        time.sleep(0.08)
                t_pulse = threading.Thread(target=_pulse, daemon=True)
                t_pulse.start()
                try:
                    import pythoncom, win32com.client
                    pythoncom.CoInitialize()
                    voice = win32com.client.Dispatch("SAPI.SpVoice")
                    self._active_voice = voice
                    voice.Rate = 1

                    # Voice selection
                    target_voice = self.cfg.get("voice", "").lower()
                    for v in voice.GetVoices():
                        if target_voice and target_voice in v.GetDescription().lower():
                            voice.Voice = v
                            break

                    # Audio output routing (e.g. Speakers, Headphones, or active system default)
                    target_out = self.cfg.get("output_device", "default").lower()
                    if target_out and target_out not in ("null", "none", "default", "auto", "system"):
                        try:
                            outputs = voice.GetAudioOutputs()
                            for i in range(outputs.Count):
                                out_item = outputs.Item(i)
                                if target_out in out_item.GetDescription().lower():
                                    voice.AudioOutput = out_item
                                    break
                        except Exception:
                            pass

                    # SVSFlagsAsync = 1
                    voice.Speak(clean_text, 1)
                    voice.WaitUntilDone(15000)
                except Exception as e:
                    BUS.emit("sys", f"SAPI speak error: {e}")
                finally:
                    self._active_voice = None
                    stop_pulsing.set()
                    BUS.emit("level", "", value=0.01)
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass
            return

        # Kokoro ONNX path
        if self._kokoro:
            import sounddevice as sd
            samples, rate = self._kokoro.create(
                clean_text, voice=self.cfg.get("voice", "af_heart"), speed=self.cfg.get("speed", 1.05), lang="en-us"
            )
            sd.play(samples, rate)
            chunk_size = int(rate * 0.05)
            total_chunks = len(samples) // max(1, chunk_size)
            for idx in range(total_chunks):
                if self._stopped.is_set():
                    sd.stop()
                    break
                chunk = samples[idx * chunk_size : (idx + 1) * chunk_size]
                BUS.emit("level", "", value=float(min(1.0, np.abs(chunk).mean() * 6.0)))
                time.sleep(0.048)
            sd.wait()
            BUS.emit("level", "", value=0.01)

    def stream_sentences(self, token_iter, stop=None):
        """Consume LLM tokens, speak as soon as a complete sentence is ready."""
        buf, full = "", ""
        for tok in token_iter:
            if stop is not None and stop.is_set():
                break
            buf += tok; full += tok
            if SENT_END.search(buf) or len(buf) > 140:
                parts = SENT_END.split(buf)
                for p in parts[:-1]:
                    if p.strip() and not (stop is not None and stop.is_set()):
                        self.say(p.strip())
                buf = parts[-1]
        if buf.strip() and not (stop is not None and stop.is_set()):
            self.say(buf.strip())
        return full
