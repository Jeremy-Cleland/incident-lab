import asyncio
import json
import os
import platform
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import store
from .agent import investigate, verify
from .models import Approval, CreateRun
from .provider import OllamaProvider
from .simulator import approve, cancel

DB = os.environ.get("INCIDENT_DB", str(store.ROOT / "data/runs.sqlite"))
tasks = {}


def spawn(rid, coroutine):
    task = asyncio.create_task(coroutine)
    tasks[rid] = task
    task.add_done_callback(lambda t: tasks.pop(rid, None) if tasks.get(rid) is t else None)


@asynccontextmanager
async def lifespan(app):
    store.init(DB)
    with store.transaction(DB) as c:
        rows = c.execute(
            "SELECT id FROM runs WHERE state IN ('investigating','executing','verifying')"
        ).fetchall()
        for row in rows:
            c.execute("UPDATE runs SET state='inconclusive' WHERE id=?", (row["id"],))
            store.emit(
                c, row["id"], "inconclusive", {"reason": "Process restarted; no automatic re-execution"}
            )
    yield
    for t in list(tasks.values()):
        t.cancel()
    if tasks:
        await asyncio.gather(*list(tasks.values()), return_exceptions=True)


app = FastAPI(title="Incident Lab local API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)


@app.middleware("http")
async def local_only(request: Request, call_next):
    from starlette.responses import JSONResponse

    if request.client and request.client.host not in ["127.0.0.1", "::1", "testclient"]:
        return JSONResponse({"detail": "Local-only API"}, status_code=403)
    return await call_next(request)


def require_live():
    if os.environ.get("INCIDENT_LIVE") != "1":
        raise HTTPException(
            403,
            "Live inference disabled. Set INCIDENT_LIVE=1 locally; no public inference service is provided.",
        )


def get_run(rid):
    try:
        return store.get(rid, DB)
    except KeyError:
        raise HTTPException(404, "Run not found")


@app.get("/api/health")
def health():
    return {"mode": "local", "live_enabled": os.environ.get("INCIDENT_LIVE") == "1"}


@app.get("/api/scenarios")
def scenarios():
    return [
        {"id": c["id"], "title": c["title"], "brief": c["brief"], "split": c["split"]}
        for c in store.cases()
        if c["split"] == "development"
    ]


@app.post("/api/runs", status_code=201)
async def create_run(body: CreateRun):
    require_live()
    if any(not t.done() for t in tasks.values()):
        raise HTTPException(429, "One local investigation at a time")
    try:
        model = await OllamaProvider().metadata()
    except Exception:
        raise HTTPException(503, "Ollama is unavailable or qwen3:8b is not installed")
    manifest = json.loads((store.ROOT / "cases/manifest.json").read_text())
    try:
        rid = store.create(
            body.case_id,
            model
            | {
                "mode": "local-live",
                "hardware": platform.platform(),
                "scenario_version": manifest["version"],
                "scenario_sha256": manifest["sha256"],
            },
            DB,
        )
    except StopIteration:
        raise HTTPException(404, "Unknown case")
    spawn(rid, investigate(rid, DB))
    return get_run(rid)


@app.get("/api/runs/{rid}")
def run(rid: str):
    return get_run(rid)


@app.post("/api/runs/{rid}/approval")
async def approval(rid: str, body: Approval):
    require_live()
    get_run(rid)
    try:
        approve(rid, body, DB)
    except ValueError as e:
        raise HTTPException(409, str(e))
    if body.decision == "approve":
        spawn(rid, verify(rid, DB))
    return get_run(rid)


@app.post("/api/runs/{rid}/cancel")
async def cancel_run(rid: str):
    require_live()
    get_run(rid)
    cancel(rid, DB)
    if rid in tasks:
        tasks[rid].cancel()
    return get_run(rid)


@app.get("/api/runs/{rid}/export")
def export(rid: str):
    return {"format_version": "1.0", "mode": "recorded-local-agent", "run": get_run(rid)}


@app.get("/api/runs/{rid}/events")
async def events(rid: str, request: Request, after: int = 0):
    get_run(rid)
    try:
        cursor = max(after, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid event cursor")

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            current = get_run(rid)
            for e in current["events"]:
                if e["seq"] > cursor:
                    cursor = e["seq"]
                    yield f"id: {cursor}\nevent: trace\ndata: {json.dumps(e)}\n\n"
            if current["state"] in store.TERMINAL:
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
