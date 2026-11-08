"""FastAPI app: serves the UI and runs the benchmark.

Start it with::

    uvicorn backend.main:app --reload

The OpenRouter key is read from the backend environment (``.env``) only.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import random
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, load_settings, ollama_models
from .ledger import APILedger
from .cube import GEOMETRY, SOLVED
from .runner import RESULTS_DIR, Run, execute

FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Rubik's Cube Race", version="1.0")
RUNS: dict[str, Run] = {}


class RunRequest(BaseModel):
    suite: Literal["warmup", "primary", "extension", "custom"] = "primary"
    n_puzzles: int = Field(1, ge=1, le=50)
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    scramble_len: int | None = Field(None, ge=3, le=3)
    models: list[str] | None = None
    parallel: bool = False
    ollama_guided: bool = False  # opt-in SOLVER-ASSISTED demo, not a fair model benchmark
    mock: bool | None = None
    provider: Literal["mock", "ollama", "openrouter"] | None = None


def _active_run() -> Run | None:
    return next((r for r in RUNS.values() if not r.finished), None)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    s = load_settings()
    out = s.public_dict()
    out["local_models"] = [{"key": m.key, "name": m.name, "model_id": m.model_id,
                            "category": m.category, "api": m.api, "badge": m.badge,
                            "color": m.color} for m in ollama_models()]
    return out


@app.get("/api/usage")
def get_usage():
    """Persistent real OpenRouter budget; never returns the key or raw prompts."""
    return APILedger(load_settings().ledger_path).snapshot()


@app.get("/api/geometry")
def get_geometry():
    """Facelet index -> (cubie position, outward normal); lets the UI draw the cube
    with exactly the same layout the engine uses."""
    return {
        "solved": SOLVED,
        "facelets": [{"pos": list(p), "normal": list(n)} for p, n in GEOMETRY],
    }


@app.post("/api/run")
async def start_run(req: RunRequest):
    if (active := _active_run()) is not None:
        raise HTTPException(409, f"A benchmark is already running (run {active.id}). Stop it first.")
    settings = load_settings()
    # The browser must explicitly select a provider. Old API clients using
    # {"mock":false} still work only if the separate live-API gate is enabled.
    provider = req.provider or ("mock" if req.mock is True else
                                "openrouter" if req.mock is False else settings.provider)
    if req.ollama_guided and provider != "ollama":
        raise HTTPException(400, "Solver-guided mode is available only for local Ollama demonstrations.")
    settings.provider = provider
    settings.mock = provider == "mock"
    if provider == "ollama":
        settings.models = ollama_models()
        # A laptop cannot reliably load/infer with four different models at once.
        # Enforce serial local trials even if an old UI/client requested parallel.
        # Hosted API benchmark behavior remains unchanged.
        req.parallel = False
        # Local inference can be much slower than cloud inference, especially on CPU.
        # Never change the dedicated hosted OpenRouter timeout or request policy.
        settings.time_limit_s = settings.ollama_time_limit_s
    if provider == "openrouter":
        if not settings.allow_live_api:
            raise HTTPException(400, "Live OpenRouter disabled. Set ALLOW_LIVE_API=1 in .env ONLY after offline testing.")
        if not settings.api_key:
            raise HTTPException(400, "OPENROUTER_API_KEY missing: add your key in the private .env file.")
        # Fail closed when the ledger is unwritable; never bypass it.
        try:
            APILedger(settings.ledger_path).snapshot()
        except Exception as exc:
            raise HTTPException(500, "Cannot open persistent API counter; live run blocked.") from exc
    if provider == "ollama" and not settings.ollama_base_url.startswith(("https://", "http://")):
        raise HTTPException(400, "OLLAMA_BASE_URL must be an HTTP URL")
    known = settings.model_map()
    keys = req.models or [m.key for m in settings.models]
    keys = list(dict.fromkeys(keys))  # never schedule the same model twice for a puzzle
    unknown = [k for k in keys if k not in known]
    if unknown or not keys:
        raise HTTPException(400, f"Unknown model keys: {unknown}")
    seed = req.seed if req.seed is not None else random.randrange(1, 10**6)
    request = req.model_dump()
    request["seed"] = seed
    request["provider"] = provider
    run = Run(request, settings, keys)
    RUNS[run.id] = run
    run.task = asyncio.create_task(execute(run))
    return {"run_id": run.id, "seed": seed, "mock": settings.mock, "provider": provider}


def _get_run(run_id: str) -> Run:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run id")
    return run


@app.get("/api/run/{run_id}/events")
async def run_events(run_id: str, request: Request):
    """Server-Sent Events stream.  Reconnects resume via the Last-Event-ID header."""
    run = _get_run(run_id)
    last = request.headers.get("last-event-id")
    start = int(last) + 1 if last and last.isdigit() else 0

    async def gen():
        i = start
        while True:
            while i < len(run.events):
                ev = run.events[i]
                yield f"id: {i}\ndata: {json.dumps(ev)}\n\n"
                i += 1
            if run.finished and i >= len(run.events):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.04)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/run/{run_id}/stop")
async def stop_run(run_id: str):
    run = _get_run(run_id)
    if run.task and not run.finished:
        run.task.cancel()
        for _ in range(100):
            if run.finished:
                break
            await asyncio.sleep(0.02)
    return {"status": run.status}


@app.get("/api/run/{run_id}")
def get_run(run_id: str):
    return _get_run(run_id).to_dict()


@app.get("/api/runs/latest")
def latest_saved_run():
    files = sorted(RESULTS_DIR.glob("run-*.json"))
    if not files:
        raise HTTPException(404, "No saved runs yet")
    return JSONResponse(json.loads(files[-1].read_text()))


def _csv(rows: list[dict], fields: list[str]) -> PlainTextResponse:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


@app.get("/api/run/{run_id}/trials.csv")
def export_trials(run_id: str):
    run = _get_run(run_id)
    fields = ["puzzle_id", "model_name", "model_id", "status", "solved", "moves_used", "turns", "optimal",
              "optimal_exact", "reference_len", "gap", "scramble_len", "total_time_s", "avg_move_latency_ms",
              "invalid_outputs", "retries", "failed_turns", "assisted_mode", "guide_overrides", "guide_accepted", "sticker_scorecard", "final_correct_facelets", "final_exact_distance", "distance_horizon", "cost_usd", "api_calls", "cache_hits", "local_requests", "live_latency_ms", "cache_latency_ms", "error"]
    return _csv(run.results, fields)


@app.get("/api/run/{run_id}/moves.csv")
def export_moves(run_id: str):
    run = _get_run(run_id)
    rows = [{"puzzle_id": t["puzzle_id"], "model_name": t["model_name"], **turn}
            for t in run.results for turn in t["turn_log"]]
    fields = ["puzzle_id", "model_name", "turn", "move", "ok", "latency_ms", "last_attempt_ms", "attempts",
              "retries", "invalid_outputs", "confidence", "probability", "correct_facelets", "elapsed_s",
              "distance_before", "distance_after", "distance_delta", "distance_change", "distance_after_label", "distance_exact", "distance_horizon",
              "model_proposed_move", "guide_overrode", "model_response_ok", "move_source", "distance_reducing_choices",
              "http_status", "cost_usd", "api_calls", "cache_hits", "local_requests", "live_latency_ms", "cache_latency_ms", "error"]
    return _csv(rows, fields)


# The UI.  Registered last so /api/* routes win.
class NoStoreStaticFiles(StaticFiles):
    """Avoid mixing old JavaScript with a newer HTML interface during local development."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


app.mount("/static", NoStoreStaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    """Always serve HTML with matching, content-versioned JS and CSS URLs.

    A stale app.js from the browser cache can access a checkbox that no longer
    exists in the current HTML, producing errors such as setting 'checked' on null.
    Hashing the actual on-disk assets also works with --reload and manual edits.
    """
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    for name, placeholder in (("app.js", "__APP_HASH__"),
                              ("style.css", "__STYLE_HASH__")):
        digest = hashlib.sha256((FRONTEND_DIR / name).read_bytes()).hexdigest()[:16]
        html = html.replace(placeholder, digest)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})
