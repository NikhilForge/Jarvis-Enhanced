"""Always-on loop: "jarvis" → speaker check → STT → LLM(+tools) → sentence-streamed Kokoro.

Design notes
------------
* The wake word runs continuously on the CPU. Saying "jarvis" at any moment — including while
  Jarvis is speaking (barge-in) — reopens the microphone.
* Every utterance is scored against the enrolled voiceprint before the LLM sees it. Owner-only
  tools (power, personal files, shell, smart home) are refused for unrecognised voices.
* Timing marks feed core/metrics.py: wake→final-transcript, TTFT, first-audio, RTF, end-to-end.
"""
import threading, time
from core.bus import BUS
from core.skills import try_fast_path
from tools import registry
import tools.system  # noqa: F401  (registers owner-only OS tools)

SYSTEM = """You are JARVIS, {owner}'s personal assistant. The JARVIS application runs locally on their laptop. The configured Gemini brain is a cloud API, so only the context needed for reasoning is sent to Google.

Voice and behaviour:
- Speak like a competent human colleague: warm, concise, dry wit when it fits. Never robotic.
- One or two spoken sentences. No markdown, no bullet lists, no emoji, no stage directions.
- Contractions, natural rhythm, and back-references to what was said earlier.
- If you are unsure, say so in one clause and offer the next best step. Never bluff.
- Acknowledge before long work ("Give me a second"), then report the result.

Capability rules:
- Understand English, Hindi and Hinglish naturally.
- For multi-step requests, plan internally and execute tools sequentially, checking each result before the next step.
- Use vision.analyze_screen when the answer depends on what is visible on the desktop.
- Use browser.* tools for real website interaction and web.search for research-only questions.
- Never bypass CAPTCHA, MFA, paywalls, security prompts or access controls.
- Never claim an action succeeded unless a tool result confirms it.

- Use a tool whenever the request touches the computer, files, power state, the web, memory or
  the smart home. One tool call at a time; wait for the result before speaking about it.
- Only emit tool names that exist in the provided schema list. Never invent a command.
- Anything irreversible (delete, move, shutdown, shell) is confirmed out loud first.
- When {owner} states a durable preference or fact, call memory.core_append right away.

Speaker context: the current voice matched the enrolled voiceprint with score {score:.2f}
(threshold {threshold:.2f}, verified={verified}). If verified is False, be helpful for general
questions but refuse anything that touches this machine or personal data.

Core memory:
{core}
"""


class Orchestrator:
    def __init__(self, cfg, audio, wake, stt, llm, tts, memory, speaker=None, metrics=None,
                 rag=None, learning=None, proactive=None, audit=None):
        self.cfg, self.audio, self.wake = cfg, audio, wake
        self.stt, self.llm, self.tts, self.memory = stt, llm, tts, memory
        self.speaker, self.metrics = speaker, metrics
        self.rag, self.learning, self.proactive, self.audit = rag, learning, proactive, audit
        self.history = []
        self.state = "idle"
        self.pending = None
        self._confirm = threading.Event()
        self._approved = False
        self._stop_speaking = threading.Event()
        self.follow_up_until = 0.0     # short window where no wake word is needed
        self._manual_wake = threading.Event()

    def wake_now(self):
        """Wake the assistant from the local HUD button."""
        self._manual_wake.set()
        BUS.emit("wake", "manual wake button pressed")

    def consume_manual_wake(self):
        if self._manual_wake.is_set():
            self._manual_wake.clear()
            return True
        return False

    def set_state(self, s):
        self.state = s
        BUS.emit("state", s, state=s)

    # ---- HITL ---------------------------------------------------------
    def confirm(self, approved: bool):
        self._approved = approved
        self._confirm.set()

    def _await_confirmation(self, name, args) -> bool:
        self.pending = {"name": name, "args": args}
        self._approved = False
        if self.audit:
            self.audit.record("confirmation_requested", tool=name, args=args)
        self._confirm.clear()
        self.set_state("confirm")
        BUS.emit("sys", f"HITL: {name} needs a spoken 'yes'", pending=self.pending)
        self.tts.say("That one can't be undone. Want me to go ahead?")
        threading.Thread(target=self._listen_for_yes, daemon=True).start()
        self._confirm.wait(timeout=25)
        self.pending = None
        BUS.emit("sys", "approved" if self._approved else "vetoed", pending=None)
        if self.audit:
            self.audit.record("confirmation_result", tool=name, approved=self._approved)
        return self._approved

    def _listen_for_yes(self):
        try:
            audio = self.audio.record_utterance(max_seconds=6)
            if self.speaker:
                self.speaker.score(audio)               # confirmation must come from the owner too
                if not self.speaker.is_owner(privileged=True):
                    BUS.emit("voice", "confirmation rejected: voice did not match")
                    if self.audit: self.audit.record("confirmation_rejected", tool=self.pending["name"] if self.pending else "unknown", reason="voice_not_verified")
                    self.confirm(False)
                    return
            said = self.stt.transcribe(audio).lower()
            self.confirm(any(w in said for w in ("yes", "yeah", "yep", "confirm", "do it", "go ahead", "affirmative")))
        except Exception:
            self.confirm(False)

    # ---- one turn -----------------------------------------------------
    def handle(self, text: str, t_wake: float):
        self.memory.log("user", text)
        if self.audit:
            self.audit.record("user_turn", text=text[:1000])

        # 0. turn praise / corrections in this utterance into training signal
        if self.learning:
            self.learning.feedback(text)

        # 1. deterministic fast path — answers trivia without waking the 3B model
        fast = try_fast_path(text, self)
        if fast is not None:
            if fast:
                self.set_state("speaking")
                self.tts.say(fast)
                self.memory.log("assistant", fast)
            self.set_state("idle")
            self.follow_up_until = time.time() + self.cfg["wakeword"].get("follow_up_seconds", 8)
            return fast

        self.history = self.history[-8:] + [{"role": "user", "content": text}]
        score = self.speaker.last_score if self.speaker else 1.0
        verified = self.speaker.is_owner() if self.speaker else True
        sysmsg = SYSTEM.format(
            owner=(self.speaker.owner if self.speaker else "the operator"),
            score=score, threshold=(self.speaker.threshold if self.speaker else 0.0),
            verified=verified, core=self.memory.block_text())
        # 2. ground the answer in the operator's own documents when relevant
        if self.rag and self.rag.available():
            hits = self.rag.search(text)
            if hits:
                ctx = "\n\n".join(f"[{h['path']}]\n{h['text'][:600]}" for h in hits[:3])
                sysmsg += f"\n\nRelevant excerpts from the operator's files:\n{ctx}\n"
        msgs = [{"role": "system", "content": sysmsg}] + self.history
        ttft = first_audio = 0.0
        spoken_total = ""

        for _hop in range(6):
            self.set_state("thinking")
            tool_call = None
            t_llm = time.perf_counter()
            marks = {"ttft": None, "audio": None}

            def tokens():
                nonlocal tool_call
                for kind, payload in self.llm.chat_stream(msgs, tools=registry.schemas()):
                    if kind == "tool":
                        tool_call = payload
                        return
                    if marks["ttft"] is None:
                        marks["ttft"] = (time.perf_counter() - t_llm) * 1000
                    yield payload

            self.set_state("speaking")
            self._stop_speaking.clear()
            t_speak = time.perf_counter()
            spoken = self.tts.stream_sentences(tokens(), stop=self._stop_speaking)
            marks["audio"] = (time.perf_counter() - t_speak) * 1000
            ttft = ttft or (marks["ttft"] or 0.0)
            first_audio = first_audio or marks["audio"]
            spoken_total += spoken

            if not tool_call:
                self.history.append({"role": "assistant", "content": spoken})
                self.memory.log("assistant", spoken)
                self.memory.archival_insert(f"user: {text}\nassistant: {spoken}")
                if self.metrics:
                    words = max(1, len(spoken.split()))
                    self.metrics.record({
                        "utterance": text[:120], "speaker_score": round(score, 3),
                        "verified": verified,
                        "stt_ms": self._stt_ms, "ttft_ms": ttft,
                        "tts_first_ms": first_audio,
                        "e2e_ms": (time.perf_counter() - t_wake) * 1000,
                        "rtf": round(first_audio / max(1.0, words * 300.0), 3),
                    })
                if self.learning:
                    self.learning.record_turn(text, spoken)
                self.set_state("idle")
                self.follow_up_until = time.time() + self.cfg["wakeword"].get("follow_up_seconds", 8)
                return spoken

            name, args = tool_call["name"], tool_call["args"]
            if self.audit:
                self.audit.record("tool_requested", tool=name, args=args,
                                  destructive=registry.is_destructive(name, self.cfg),
                                  privileged=registry.is_privileged(name, self.cfg))
            if registry.is_privileged(name, self.cfg) and self.speaker and not self.speaker.is_owner(privileged=True):
                result = "refused: voice not verified as the enrolled operator"
                BUS.emit("voice", f"blocked {name} (score {score:.2f})")
                if self.audit: self.audit.record("tool_blocked", tool=name, reason="voice_not_verified", score=round(score, 3))
            elif registry.is_destructive(name, self.cfg) and not self._await_confirmation(name, args):
                result = "operator declined the action"
                if self.audit: self.audit.record("tool_blocked", tool=name, reason="confirmation_denied")
            else:
                result = registry.call(name, args, {"config": self.cfg, "memory": self.memory,
                                                    "speaker": self.speaker, "metrics": self.metrics,
                                                    "rag": self.rag, "learning": self.learning,
                                                    "proactive": self.proactive, "tts": self.tts,
                                                    "llm": self.llm, "orchestrator": self})
                BUS.emit("tool", f"{name} → {str(result)[:120]}")
                if self.audit: self.audit.record("tool_executed", tool=name, result=str(result)[:2000])
            msgs.append({"role": "assistant", "content": "",
                         "tool_calls": [{"function": {"name": name, "arguments": args}}]})
            msgs.append({"role": "tool", "content": str(result)[:4000]})
        self.set_state("idle")
        return spoken_total

    # ---- main loop ----------------------------------------------------
    def run_forever(self):
        self.audio.start()
        self.set_state("idle")
        self._stt_ms = 0.0
        last_res = 0.0
        for frame in self.audio.frames():
            BUS.emit("level", "", value=self.audio.level(frame))
            if self.metrics and time.time() - last_res > 5:
                self.metrics.sample(); last_res = time.time()

            hot = (self.wake.enabled and self.wake.triggered(frame))
            clap = self.audio.clap_triggered(frame)
            hot = hot or clap or self.consume_manual_wake()
            if hot and self.state == "speaking":
                BUS.emit("wake", "barge-in: 'jarvis' heard mid-reply, stopping playback")
                self._stop_speaking.set()
                self.tts.stop()
            if self.state not in ("idle", "speaking"):
                continue
            follow_up = time.time() < self.follow_up_until and self.audio.level(frame) > 0.12
            if not hot and not follow_up:
                continue

            t_wake = time.perf_counter()
            self.set_state("listening")
            audio = self.audio.record_utterance()
            if self.speaker:
                self.speaker.score(audio)
            t0 = time.perf_counter()
            text = self.stt.transcribe(audio, on_partial=self.llm.prefetch)
            self._stt_ms = (time.perf_counter() - t0) * 1000
            if not text:
                self.set_state("idle"); continue
            BUS.emit("user", text)
            try:
                self.handle(text, t_wake)
            except Exception as e:
                if self.audit: self.audit.record("turn_error", error=str(e))
                BUS.emit("sys", f"turn failed: {e}")
                self.set_state("idle")
