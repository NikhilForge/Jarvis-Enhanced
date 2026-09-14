"""FastAPI host: serves the WebGL HUD and streams pipeline events over a websocket."""
import asyncio, json, threading, yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from core.bus import BUS
from core.audit import Audit

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))
app = FastAPI(title="JARVIS-6")
app.mount("/static", StaticFiles(directory="web"), name="static")
ORCH = {"ref": None}
AUDIT = Audit(CFG)


@app.get("/")
def index():
    return FileResponse("web/index.html")


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


@app.post("/api/confirm/{decision}")
def confirm(decision: str):
    o = ORCH["ref"]
    if o:
        o.confirm(decision == "yes")
    return {"ok": True}


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


def start(orchestrator=None):
    ORCH["ref"] = orchestrator
    if orchestrator:
        threading.Thread(target=orchestrator.run_forever, daemon=True).start()
    uvicorn.run(app, host=CFG["server"]["host"], port=CFG["server"]["port"], log_level="warning")
