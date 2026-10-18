"""Deploy smoke stub of the Side API (NOT the real apps/api)."""

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("SIDE_DATA_DIR", "./.side-data"))
RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
app = FastAPI(title="Side API (deploy stub)")


class RunCreate(BaseModel):
    task_id: str
    agent: dict
    goal: str | None = None
    start_url: str | None = None
    max_steps: int = 15
    headless: bool = True


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "deploy-stub"}


@app.get("/api/v1/tasks")
def tasks():
    return [
        {
            "id": "browsergym/openended",
            "benchmark": "openended",
            "title": "Open-ended",
            "requires_setup": False,
        }
    ]


@app.get("/api/v1/agents")
def agents():
    return [{"type": "mock", "title": "Mock agent", "models": []}]


@app.post("/api/v1/runs", status_code=201)
def create_run(body: RunCreate):
    run_id = uuid.uuid4().hex[:12]
    cmd = [
        sys.executable,
        "-m",
        "side_runner",
        "--run-id",
        run_id,
        "--task",
        body.task_id,
        "--agent-json",
        json.dumps(body.agent),
        "--max-steps",
        str(body.max_steps),
        "--data-dir",
        str(DATA_DIR),
    ]
    if body.goal:
        cmd += ["--goal", body.goal]
    if body.start_url:
        cmd += ["--start-url", body.start_url]
    if not body.headless:
        cmd.append("--no-headless")
    subprocess.run(cmd, check=True, timeout=120)
    return get_run(run_id)


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str):
    if not RUN_ID_RE.fullmatch(run_id):
        raise HTTPException(404, "run not found")
    path = DATA_DIR / "runs" / run_id / "run.json"
    if not path.exists():
        raise HTTPException(404, "run not found")
    return json.loads(path.read_text())


@app.on_event("startup")
def _startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("side-api stub started", datetime.now(timezone.utc).isoformat(), flush=True)
