"""Minimal async client for the Expo Push API with batching and retries.

Docs: https://docs.expo.dev/push-notifications/sending-notifications/
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from .config import EXPO_PUSH_URL, EXPO_RECEIPTS_URL

logger = logging.getLogger("side_notifications.expo")

PUSH_BATCH_SIZE = 100
RECEIPT_BATCH_SIZE = 1000


class ExpoError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass
class PushTicket:
    token: str
    status: str  # "ok" | "error"
    id: str | None = None
    error: str | None = None  # e.g. DeviceNotRegistered, MessageTooBig, RequestFailed
    message: str | None = None


def chunked(items: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class ExpoClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        access_token: str | None = None,
        push_url: str = EXPO_PUSH_URL,
        receipts_url: str = EXPO_RECEIPTS_URL,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 8.0,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ):
        self.http = http
        self.access_token = access_token
        self.push_url = push_url
        self.receipts_url = receipts_url
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_max_s)
            except ValueError:
                pass
        return min(self.backoff_base_s * (2**attempt), self.backoff_max_s)

    async def _post(self, url: str, payload: Any) -> dict[str, Any]:
        last_error: ExpoError | None = None
        for attempt in range(self.max_retries + 1):
            retry_after = None
            try:
                resp = await self.http.post(url, json=payload, headers=self._headers())
            except httpx.TransportError as exc:
                last_error = ExpoError(f"transport error: {exc!r}", retryable=True)
            else:
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    retry_after = resp.headers.get("Retry-After")
                    last_error = ExpoError(
                        f"Expo HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                        retryable=True,
                    )
                elif resp.status_code >= 400:
                    raise ExpoError(
                        f"Expo HTTP {resp.status_code}: {resp.text[:500]}",
                        status_code=resp.status_code,
                    )
                else:
                    body = resp.json()
                    if "data" not in body and body.get("errors"):
                        raise ExpoError(f"Expo request error: {body['errors']}")
                    return body
            if attempt < self.max_retries:
                delay = self._backoff(attempt, retry_after)
                logger.warning(
                    "Expo request failed (%s), retry %d/%d in %.2fs",
                    last_error,
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                await self._sleep(delay)
        assert last_error is not None
        raise last_error

    async def send(self, messages: Sequence[dict[str, Any]]) -> list[PushTicket]:
        """Send messages in batches of 100. Returns one ticket per message, in order."""
        tickets: list[PushTicket] = []
        for batch in chunked(messages, PUSH_BATCH_SIZE):
            try:
                body = await self._post(self.push_url, list(batch))
            except ExpoError as exc:
                logger.error("Expo push batch of %d failed: %s", len(batch), exc)
                failed = [
                    PushTicket(m["to"], "error", error="RequestFailed", message=str(exc))
                    for m in batch
                ]
                tickets.extend(failed)
                continue
            data = body.get("data") or []
            if isinstance(data, dict):  # single-message responses are an object
                data = [data]
            for i, msg in enumerate(batch):
                item = data[i] if i < len(data) else {"status": "error", "message": "missing"}
                details = item.get("details") or {}
                tickets.append(
                    PushTicket(
                        token=msg["to"],
                        status=item.get("status", "error"),
                        id=item.get("id"),
                        error=details.get("error")
                        or (None if item.get("status") == "ok" else "Unknown"),
                        message=item.get("message"),
                    )
                )
        return tickets

    async def get_receipts(
        self, ticket_ids: Sequence[str]
    ) -> tuple[dict[str, dict[str, Any]], set[str]]:
        """Fetch receipts (1000 ids/request).

        Returns (receipts, queried_ids). Ids in `queried_ids` but not in `receipts` were looked
        up successfully but have no receipt (yet); ids outside `queried_ids` were in a failed
        request and should simply be retried later.
        """
        receipts: dict[str, dict[str, Any]] = {}
        queried: set[str] = set()
        for batch in chunked(list(ticket_ids), RECEIPT_BATCH_SIZE):
            try:
                body = await self._post(self.receipts_url, {"ids": list(batch)})
            except ExpoError as exc:
                logger.error("Expo receipts request for %d ids failed: %s", len(batch), exc)
                continue
            queried.update(batch)
            receipts.update(body.get("data") or {})
        return receipts, queried
