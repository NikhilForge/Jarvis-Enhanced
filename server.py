"""FastAPI host: serves the WebGL HUD and streams pipeline events over a websocket."""
import asyncio, json, os, subprocess, threading, time, yaml
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from core.bus import BUS
from core.audit import Audit

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.yaml")
WEB_DIR = os.path.join(HERE, "web")
INDEX_PATH = os.path.join(WEB_DIR, "index.html")

CFG = yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))
app = FastAPI(title="JARVIS-6")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
ORCH = {"ref": None}
AUDIT = Audit(CFG)


@app.get("/")
def index():
    return FileResponse(INDEX_PATH)


@app.get("/api/config")
def config():
    return {"llm": CFG["llm"]["model"], "stt": CFG["stt"]["model"], "tts": CFG["tts"]["engine"]}

@app.get("/api/audit")
def audit():
    return {"enabled": AUDIT.enabled, "records": AUDIT.read(CFG.get("audit", {}).get("max_api_records", 500))}

@app.get("/api/audit/export")
def audit_export():
    import csv, io
    records = AUDIT.read(5000)
    fields = sorted({k for r in records for k in r.keys()})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jarvis-audit.csv"'},
    )


@app.post("/api/wake")
def wake():
    o = ORCH["ref"]
    if o:
        o.wake_now()
        return {"ok": True}
    return {"ok": False, "error": "assistant not running"}


class PromptRequest(BaseModel):
    text: str


@app.post("/api/prompt")
def prompt(req: PromptRequest):
    o = ORCH["ref"]
    if not o:
        return {"ok": False, "error": "assistant not running"}
    text = (req.text or "").strip()
    if not text:
        return {"ok": False, "error": "empty text"}

    def _run():
        if hasattr(o, "handle_text"):
            o.handle_text(text)
        else:
            BUS.emit("user", text)
            o.handle(text, time.perf_counter())

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


@app.post("/api/confirm/{decision}")
def confirm(decision: str):
    o = ORCH["ref"]
    if o:
        o.confirm(decision == "yes")
    return {"ok": True}


@app.get("/api/devices")
def get_devices():
    import sounddevice as sd
    devices = []
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    
    cur_dev = None
    o = ORCH.get("ref")
    if o and hasattr(o, "audio"):
        cur_dev = o.audio.device

    for idx, d in enumerate(sd.query_devices()):
        # Filter to MME (hostapi == 0) to avoid duplicates across DirectSound/WASAPI/WDM
        if d.get("max_input_channels", 0) > 0 and d.get("hostapi") == 0:
            is_active = (idx == cur_dev)
            devices.append({
                "index": idx,
                "name": d.get("name"),
                "channels": d.get("max_input_channels"),
                "is_default": (idx == default_in),
                "is_active": is_active,
            })
    return {"devices": devices, "current": cur_dev}


class DeviceRequest(BaseModel):
    device: int | str


@app.post("/api/device")
def set_device(req: DeviceRequest):
    o = ORCH.get("ref")
    if not o or not hasattr(o, "audio"):
        return {"ok": False, "error": "audio engine not running"}
    dev = req.device
    ok = o.audio.switch_device(dev)
    if ok:
        try:
            import sounddevice as sd
            dinfo = sd.query_devices(o.audio.device)
            dev_name = dinfo.get("name", str(dev))
            save_name = dev_name
            for kw in ("Realtek", "Airdopes", "Headset", "Microphone"):
                if kw.lower() in dev_name.lower():
                    save_name = kw
                    break
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = yaml.safe_load(f)
            c["audio"]["input_device"] = save_name
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(c, f, sort_keys=False)
        except Exception:
            pass
        return {"ok": True, "device": o.audio.device}
    return {"ok": False, "error": "failed to switch device"}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    q = BUS.subscribe()
    try:
        while True:
            evt = await q.get()
            await sock.send_text(json.dumps(evt))
    except WebSocketDisconnect:
        pass
    finally:
        BUS.unsubscribe(q)


def _free_port(port: int):
    """If a previous zombie process is holding the port, terminate it."""
    try:
        out = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True)
        for line in out.stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pid = parts[-1]
                if pid and pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
    except Exception:
        pass


def start(orchestrator=None):
    ORCH["ref"] = orchestrator
    if orchestrator:
        threading.Thread(target=orchestrator.run_forever, daemon=True).start()

    port = int(CFG["server"]["port"])
    host = CFG["server"]["host"]

    _free_port(port)

    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except OSError as e:
        if getattr(e, "winerror", None) == 10048 or "10048" in str(e):
            fallback_port = port + 1
            print(f"· Port {port} still locked, launching HUD on fallback http://localhost:{fallback_port}")
            uvicorn.run(app, host=host, port=fallback_port, log_level="warning")
        else:
            raise
