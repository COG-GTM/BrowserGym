"""Side API server. Run with ``uvicorn side_api.main:app --port 8000``."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
import yaml
from fastapi import APIRouter, FastAPI, Header, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import and_, or_
from sqlmodel import col, select

from . import __version__, catalog
from .config import Settings
from .db import RunRecord, make_engine, session
from .monitor import RunManager
from .notify import Notifier
from .schemas import (
    TERMINAL_STATUSES,
    AgentInfo,
    ChatCreate,
    ChatMessage,
    DeviceRegistration,
    ErrorResponse,
    Health,
    Run,
    RunCreate,
    RunList,
    RunStatus,
    Step,
    StepDetail,
    Task,
)
from .sse import event_stream
from .storage import RunPaths, append_jsonl, is_safe_run_id, now_iso, read_json, read_jsonl

log = logging.getLogger("side_api")

API_PREFIX = "/api/v1"
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse}}


def _encode_cursor(rec: RunRecord) -> str:
    raw = json.dumps([rec.created_at, rec.id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, run_id = json.loads(base64.urlsafe_b64decode(padded))
        return str(created_at), str(run_id)
    except (ValueError, TypeError, binascii.Error) as e:
        raise HTTPException(status_code=422, detail="invalid cursor") from e


def _screenshot_url(run_id: str, index: int) -> str:
    return f"{API_PREFIX}/runs/{run_id}/steps/{index}/screenshot"


def _validation_detail(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return "; ".join(parts) or "validation error"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "runs").mkdir(exist_ok=True)
    engine = make_engine(settings.resolved_db_url)
    manager = RunManager(settings, engine, Notifier(settings.notify_url))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await manager.resume()
        yield
        await manager.shutdown()

    app = FastAPI(
        title="Side API",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.manager = manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _validation_detail(exc)})

    contract_path = settings.resolved_contract_path()
    if contract_path is not None:
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))

        def _contract_openapi() -> dict[str, Any]:
            return contract

        app.openapi = _contract_openapi  # type: ignore[method-assign]

    router = APIRouter(prefix=API_PREFIX)

    def get_record(run_id: str) -> RunRecord:
        if not is_safe_run_id(run_id):
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        with session(engine) as s:
            rec = s.get(RunRecord, run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return rec

    def run_paths(run_id: str) -> RunPaths:
        return RunPaths(settings.data_dir, run_id)

    def load_step(paths: RunPaths, index: int) -> StepDetail | None:
        data = read_json(paths.step_json(index))
        if data is None:
            return None
        data.setdefault("index", index)
        data.setdefault("timestamp", now_iso())
        try:
            step = StepDetail.model_validate(data)
        except ValueError:
            log.warning("run %s: invalid step file %s", paths.run_id, index)
            return None
        step.screenshot_url = (
            _screenshot_url(paths.run_id, index) if paths.step_png(index).is_file() else None
        )
        return step

    # -- meta ---------------------------------------------------------------
    @router.get("/health", response_model=Health)
    def get_health() -> Health:
        return Health(status="ok", version=__version__)

    @router.get("/tasks", response_model=list[Task])
    def list_tasks(benchmark: str | None = None, q: str | None = None) -> list[Task]:
        return catalog.list_tasks(benchmark=benchmark, q=q)

    @router.get("/agents", response_model=list[AgentInfo])
    def list_agents() -> list[AgentInfo]:
        return catalog.AGENTS

    # -- runs ---------------------------------------------------------------
    @router.get("/runs", response_model=RunList)
    def list_runs(
        status: RunStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: str | None = None,
    ) -> RunList:
        stmt = select(RunRecord)
        if status:
            stmt = stmt.where(RunRecord.status == status)
        if cursor:
            c_created, c_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    col(RunRecord.created_at) < c_created,
                    and_(col(RunRecord.created_at) == c_created, col(RunRecord.id) < c_id),
                )
            )
        stmt = stmt.order_by(col(RunRecord.created_at).desc(), col(RunRecord.id).desc()).limit(
            limit + 1
        )
        with session(engine) as s:
            rows = list(s.exec(stmt).all())
        next_cursor = _encode_cursor(rows[limit - 1]) if len(rows) > limit else None
        return RunList(items=[r.to_run() for r in rows[:limit]], next_cursor=next_cursor)

    @router.post(
        "/runs",
        response_model=Run,
        status_code=201,
        responses={422: {"model": ErrorResponse}},  # type: ignore[dict-item]
    )
    async def create_run(body: RunCreate) -> Run:
        task = catalog.find_task(body.task_id)
        if task is None:
            raise HTTPException(status_code=422, detail=f"unknown task_id: {body.task_id}")
        if task.benchmark == "openended" and not (body.goal or "").strip():
            raise HTTPException(status_code=422, detail="goal is required for browsergym/openended")
        rec = RunRecord(
            id=uuid.uuid4().hex,
            task_id=body.task_id,
            goal=body.goal,
            start_url=body.start_url,
            agent_json=body.agent.model_dump_json(),
            status="queued",
            n_steps=0,
            max_steps=body.max_steps,
            headless=body.headless,
            created_at=now_iso(),
        )
        with session(engine) as s:
            s.add(rec)
            s.commit()
        run = rec.to_run()
        manager.start(rec)
        return run

    @router.get("/runs/{run_id}", response_model=Run, responses=NOT_FOUND)
    def get_run(run_id: str) -> Run:
        get_record(run_id)
        manager.refresh(run_id)
        return get_record(run_id).to_run()

    @router.delete("/runs/{run_id}", status_code=204, response_class=Response)
    async def delete_run(run_id: str) -> Response:
        if is_safe_run_id(run_id):
            await manager.delete(run_id)
        return Response(status_code=204)

    @router.post("/runs/{run_id}/cancel", response_model=Run, responses=NOT_FOUND)
    async def cancel_run(run_id: str) -> Run:
        get_record(run_id)
        rec = await asyncio.to_thread(manager.cancel, run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return rec.to_run()

    # -- steps --------------------------------------------------------------
    @router.get("/runs/{run_id}/steps", response_model=list[Step], responses=NOT_FOUND)
    def list_steps(run_id: str) -> list[Step]:
        get_record(run_id)
        paths = run_paths(run_id)
        steps = (load_step(paths, i) for i in paths.step_indices())
        return [
            Step.model_validate(s.model_dump(include=set(Step.model_fields))) for s in steps if s
        ]

    @router.get("/runs/{run_id}/steps/{index}", response_model=StepDetail, responses=NOT_FOUND)
    def get_step(run_id: str, index: Annotated[int, Path(ge=0)]) -> StepDetail:
        get_record(run_id)
        step = load_step(run_paths(run_id), index)
        if step is None:
            raise HTTPException(status_code=404, detail=f"step {index} not found")
        return step

    @router.get(
        "/runs/{run_id}/steps/{index}/screenshot",
        response_class=FileResponse,
        responses={200: {"content": {"image/png": {}}}, **NOT_FOUND},
    )
    def get_step_screenshot(run_id: str, index: Annotated[int, Path(ge=0)]) -> FileResponse:
        get_record(run_id)
        png = run_paths(run_id).step_png(index)
        if not png.is_file():
            raise HTTPException(status_code=404, detail=f"no screenshot for step {index}")
        return FileResponse(png, media_type="image/png")

    # -- chat ---------------------------------------------------------------
    @router.get("/runs/{run_id}/chat", response_model=list[ChatMessage], responses=NOT_FOUND)
    def list_chat(run_id: str) -> list[ChatMessage]:
        get_record(run_id)
        out = []
        for raw in read_jsonl(run_paths(run_id).chat):
            try:
                out.append(ChatMessage.model_validate(raw))
            except ValueError:
                continue
        return out

    @router.post(
        "/runs/{run_id}/chat", response_model=ChatMessage, status_code=201, responses=NOT_FOUND
    )
    def send_chat(run_id: str, body: ChatCreate) -> ChatMessage:
        rec = get_record(run_id)
        msg = ChatMessage(role="user", message=body.message, timestamp=now_iso())
        paths = run_paths(run_id)
        append_jsonl(paths.inbox, msg.model_dump(mode="json"))
        if rec.status in TERMINAL_STATUSES:
            # No runner left to echo it into chat.jsonl; record it so GET /chat shows it.
            append_jsonl(paths.chat, msg.model_dump(mode="json"))
        return msg

    # -- events (SSE) -------------------------------------------------------
    @router.get(
        "/runs/{run_id}/events",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {}}}, **NOT_FOUND},
    )
    def stream_run_events(
        run_id: str,
        request: Request,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        get_record(run_id)

        def current_status() -> str | None:
            with session(engine) as s:
                rec = s.get(RunRecord, run_id)
            return rec.status if rec else None

        try:
            start_after = max(0, int(last_event_id)) if last_event_id else 0
        except ValueError:
            start_after = 0
        return StreamingResponse(
            event_stream(
                request,
                run_paths(run_id),
                run_id,
                current_status,
                poll_interval=settings.poll_interval,
                heartbeat=settings.sse_heartbeat,
                last_event_id=start_after,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # -- devices ------------------------------------------------------------
    @router.post("/devices", status_code=201, response_class=Response)
    async def register_device(body: DeviceRegistration) -> Response:
        if not settings.notify_url:
            log.warning("SIDE_NOTIFY_URL not set; device registration accepted but not forwarded")
            return Response(status_code=201)
        url = f"{settings.notify_url}{API_PREFIX}/devices"
        try:
            async with httpx.AsyncClient(
                timeout=5.0, transport=manager.notifier.transport
            ) as client:
                resp = await client.post(url, json=body.model_dump(mode="json"))
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502, detail=f"notifications service unreachable: {e}"
            ) from e
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"notifications service returned {resp.status_code}"
            )
        return Response(status_code=201)

    app.include_router(router)
    return app


def __getattr__(name: str) -> Any:
    # Build the module-level app lazily so importing side_api.main has no side effects.
    if name == "app":
        globals()["app"] = instance = create_app()
        return instance
    raise AttributeError(name)
