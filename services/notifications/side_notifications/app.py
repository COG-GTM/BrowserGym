import asyncio
import contextlib
import hmac
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import __version__
from .config import Settings
from .expo import ExpoClient
from .models import TERMINAL_STATUSES, DeviceRegistration, RunEvent, RunEventAck
from .notifier import Notifier
from .store import Store

logger = logging.getLogger("side_notifications")

SECRET_HEADER = "X-Side-Notify-Secret"


async def _receipt_loop(notifier: Notifier, interval_s: float) -> None:
    while True:
        await asyncio.sleep(interval_s)
        try:
            await notifier.check_receipts()
        except Exception:  # keep the loop alive
            logger.exception("receipt check failed")


def create_app(
    settings: Settings | None = None, http_client: httpx.AsyncClient | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(settings.db_path)
        owns_client = http_client is None
        client = http_client or httpx.AsyncClient(timeout=settings.http_timeout_s)
        expo = ExpoClient(
            client,
            access_token=settings.expo_access_token,
            push_url=settings.expo_push_url,
            receipts_url=settings.expo_receipts_url,
            max_retries=settings.max_retries,
            backoff_base_s=settings.backoff_base_s,
            backoff_max_s=settings.backoff_max_s,
        )
        notifier = Notifier(store, settings, None if settings.dry_run else expo)
        app.state.store = store
        app.state.notifier = notifier
        receipt_task = None
        if not settings.dry_run and settings.receipt_interval_s > 0:
            receipt_task = asyncio.create_task(_receipt_loop(notifier, settings.receipt_interval_s))
        logger.info(
            "side-notifications ready (db=%s, dry_run=%s, internal_secret=%s)",
            settings.db_path,
            settings.dry_run,
            "set" if settings.internal_secret else "unset",
        )
        try:
            yield
        finally:
            if receipt_task:
                receipt_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await receipt_task
            if owns_client:
                await client.aclose()

    app = FastAPI(title="Side notifications", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    def get_store(request: Request) -> Store:
        return request.app.state.store

    def get_notifier(request: Request) -> Notifier:
        return request.app.state.notifier

    def require_secret(
        x_side_notify_secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
    ) -> None:
        expected = settings.internal_secret
        if not expected:
            return
        if not x_side_notify_secret or not hmac.compare_digest(
            x_side_notify_secret.encode(), expected.encode()
        ):
            raise HTTPException(status_code=401, detail=f"missing or invalid {SECRET_HEADER}")

    StoreDep = Annotated[Store, Depends(get_store)]
    NotifierDep = Annotated[Notifier, Depends(get_notifier)]

    @app.get("/health")
    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "dry_run": settings.dry_run}

    @app.post("/api/v1/devices", status_code=201)
    def register_device(reg: DeviceRegistration, store: StoreDep) -> dict[str, Any]:
        created = store.upsert_device(reg.expo_push_token, reg.platform, reg.run_ids)
        return {**reg.model_dump(), "created": created}

    @app.delete("/api/v1/devices/{token}", status_code=204)
    def unregister_device(token: str, store: StoreDep) -> Response:
        store.delete_device(token)
        return Response(status_code=204)

    @app.post(
        "/internal/run-events",
        status_code=202,
        response_model=RunEventAck,
        dependencies=[Depends(require_secret)],
    )
    def run_event(
        event: RunEvent, background: BackgroundTasks, store: StoreDep, notifier: NotifierDep
    ) -> RunEventAck:
        if event.type != "status" or event.status is None:
            return RunEventAck(action="ignored", reason="not a status event")
        if event.status not in TERMINAL_STATUSES:
            return RunEventAck(action="ignored", reason=f"non-terminal status {event.status}")
        if not store.mark_notified(event.run_id, event.status):
            return RunEventAck(action="duplicate", reason="already notified")
        tokens = store.subscribers(event.run_id)
        background.add_task(notifier.deliver, event.run_id, event.status, tokens)
        return RunEventAck(action="queued", recipients=len(tokens))

    @app.post("/internal/receipts/check", dependencies=[Depends(require_secret)])
    async def check_receipts(
        notifier: NotifierDep, min_age_s: Annotated[float | None, Query(ge=0)] = None
    ) -> dict[str, int]:
        return await notifier.check_receipts(min_age_s)

    @app.get("/internal/deliveries", dependencies=[Depends(require_secret)])
    def list_deliveries(
        store: StoreDep,
        run_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    ) -> list[dict[str, Any]]:
        return [asdict(d) for d in store.deliveries(run_id, limit)]

    return app
