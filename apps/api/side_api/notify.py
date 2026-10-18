from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)


class Notifier:
    """POSTs status RunEvents to ``${SIDE_NOTIFY_URL}/internal/run-events`` (fire-and-forget)."""

    def __init__(self, base_url: str | None, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url
        self.transport = transport
        self._pending: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def submit(self, event: dict) -> None:
        if not self.enabled:
            return
        task = asyncio.create_task(self._post(event))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _post(self, event: dict) -> None:
        url = f"{self.base_url}/internal/run-events"
        try:
            async with httpx.AsyncClient(timeout=5.0, transport=self.transport) as client:
                resp = await client.post(url, json=event)
                if resp.status_code >= 400:
                    log.warning("notify %s -> HTTP %s", url, resp.status_code)
        except httpx.HTTPError as e:
            log.warning("notify %s failed: %s", url, e)

    async def drain(self) -> None:
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
