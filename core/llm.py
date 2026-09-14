"""Gemini API brain for JARVIS.

The microphone, wake word, TTS, memory and tool execution stay local.
Only the reasoning request and the text/context sent to Gemini leave the laptop.
"""
import json, os, httpx
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from core.bus import BUS


def _clean_schema(props):
    out = {}
    for name, spec in (props or {}).items():
        s = dict(spec)
        s.pop("required", None)
        out[name] = s
    return out


def _gemini_tools(tools):
    declarations = []
    for t in tools or []:
        fn = t.get("function", {})
        params = fn.get("parameters", {"type": "object", "properties": {}})
        declarations.append({
            "name": fn.get("name"),
            "description": fn.get("description", ""),
            "parameters": {
                "type": "object",
                "properties": _clean_schema(params.get("properties", {})),
                "required": params.get("required", []),
            },
        })
    return [{"functionDeclarations": declarations}] if declarations else []


class LLM:
    def __init__(self, cfg: dict):
        self.c = cfg["llm"]
        self.backend = self.c.get("backend", "gemini").lower()
        self.client = httpx.Client(timeout=self.c.get("timeout_seconds", 90))
        self.api_key = os.getenv(self.c.get("api_key_env", "GEMINI_API_KEY"), "").strip()
        if self.backend == "gemini" and not self.api_key:
            raise RuntimeError(
                f"Missing {self.c.get('api_key_env', 'GEMINI_API_KEY')}. "
                "Set it in your Windows environment before starting JARVIS."
            )

    def _ollama_stream(self, messages, tools=None):
        payload = {
            "model": self.c["model"], "messages": messages,
            "stream": True,
            "options": {
                "num_ctx": self.c.get("num_ctx", 4096),
                "num_gpu": self.c.get("num_gpu_layers", 999),
                "temperature": self.c.get("temperature", 0.4),
            },
        }
        if tools:
            payload["tools"] = tools
        with self.client.stream("POST", "/api/chat", json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                msg = data.get("message") or {}
                for call in msg.get("tool_calls") or []:
                    fn = call.get("function", {})
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try: args = json.loads(args)
                        except json.JSONDecodeError: args = {}
                    yield ("tool", {"name": fn.get("name"), "args": args or {}})
                if msg.get("content"):
                    yield ("token", msg["content"])
                if data.get("done"):
                    break

    @staticmethod
    def _gemini_contents(messages):
        contents = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": str(m.get("content", ""))}]})
            elif role == "assistant":
                parts = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    parts.append({"functionCall": {
                        "name": fn.get("name"),
                        "args": fn.get("arguments") or {},
                    }})
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                # The orchestrator sends one tool result immediately after one call.
                name = "unknown"
                if contents and contents[-1]["role"] == "model":
                    for p in reversed(contents[-1]["parts"]):
                        if "functionCall" in p:
                            name = p["functionCall"]["name"]
                            break
                contents.append({"role": "user", "parts": [{
                    "functionResponse": {"name": name, "response": {"result": str(m.get("content", ""))[:4000]}}
                }]})
        return contents

    def _gemini_once(self, messages, tools=None):
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
        body = {
            "systemInstruction": {"parts": [{"text": system}]} if system else None,
            "contents": self._gemini_contents(messages),
            "generationConfig": {
                "temperature": self.c.get("temperature", 0.4),
                "maxOutputTokens": self.c.get("max_output_tokens", 1024),
            },
        }
        if body["systemInstruction"] is None:
            del body["systemInstruction"]
        gt = _gemini_tools(tools)
        if gt:
            body["tools"] = gt
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.c['model']}:generateContent"
        r = self.client.post(url, headers={
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini API {r.status_code}: {r.text[:1000]}")
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {json.dumps(data)[:1000]}")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            fc = part.get("functionCall")
            if fc:
                BUS.emit("tool", f"Gemini tool_call {fc.get('name')}({json.dumps(fc.get('args', {}))})")
                return ("tool", {"name": fc.get("name"), "args": fc.get("args") or {}})
        text = "".join(p.get("text", "") for p in parts if p.get("text"))
        return ("text", text.strip())

    def chat_stream(self, messages, tools=None):
        """Compatibility generator used by the existing orchestrator."""
        if self.backend == "ollama":
            yield from self._ollama_stream(messages, tools)
            return
        kind, payload = self._gemini_once(messages, tools)
        if kind == "tool":
            yield ("tool", payload)
        else:
            yield ("token", payload)


    def analyze_image(self, path: str, prompt: str) -> str:
        """Send one local image to Gemini for visual understanding. The image stays on disk locally;
        its bytes are included only in this Gemini request. This is intentionally separate from
        the normal text/tool loop so vision can be used as a local tool.
        """
        if self.backend != "gemini":
            return "vision requires the Gemini backend"
        from pathlib import Path
        import mimetypes, base64
        data = Path(path).read_bytes()
        mime = mimetypes.guess_type(path)[0] or "image/png"
        body = {
            "contents": [{"role": "user", "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}},
            ]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": min(2048, self.c.get("max_output_tokens", 1024) * 2),
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.c['model']}:generateContent"
        r = self.client.post(url, headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini vision API {r.status_code}: {r.text[:1000]}")
        data = r.json()
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if p.get("text"))
        return text.strip() or "Gemini returned no visual description."

    def prefetch(self, partial: str):
        # Gemini calls are intentionally not made on every partial transcript:
        # doing so adds latency/cost and can race the final request.
        BUS.emit("llm", f'partial received → "{partial}"')
