from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any

from .config import Settings
from .expo import ExpoClient
from .store import Store

logger = logging.getLogger("side_notifications.push")

RECEIPT_TTL_S = 24 * 3600  # Expo keeps receipts for ~24h

TITLES = {
    "succeeded": "Run succeeded",
    "failed": "Run failed",
    "cancelled": "Run cancelled",
}


def build_message(token: str, run_id: str, status: str, deep_link_base: str) -> dict[str, Any]:
    return {
        "to": token,
        "title": TITLES.get(status, f"Run {status}"),
        "body": f"Run {run_id} {status}. Tap to replay the trace.",
        "sound": "default",
        "priority": "high",
        "data": {
            "type": "run_status",
            "run_id": run_id,
            "status": status,
            "url": f"{deep_link_base}{run_id}",
        },
    }


class Notifier:
    def __init__(self, store: Store, settings: Settings, expo: ExpoClient | None):
        self.store = store
        self.settings = settings
        self.expo = expo

    async def deliver(self, run_id: str, status: str, tokens: Sequence[str]) -> dict[str, int]:
        """Push a terminal-status notification to `tokens`. Returns a small summary.

        The caller holds the (run_id, status) claim from `Store.mark_notified`. If any message
        could not be handed to Expo (request failure or crash), the claim is released so a
        re-sent event retries; tokens that already got a ticket are skipped on retry.
        """
        summary = {"sent": 0, "errors": 0, "pruned": 0, "dry_run": 0, "failed": 0}
        try:
            await self._deliver(run_id, status, tokens, summary)
        except Exception:
            logger.exception("run %s %s: delivery crashed", run_id, status)
            summary["failed"] = max(summary["failed"], 1)
        if summary["failed"]:
            self.store.unmark_notified(run_id, status)
            logger.warning(
                "run %s %s: %d message(s) not accepted by Expo; event can be retried",
                run_id,
                status,
                summary["failed"],
            )
        return summary

    async def _deliver(
        self, run_id: str, status: str, tokens: Sequence[str], summary: dict[str, int]
    ) -> None:
        if not tokens:
            logger.info("run %s %s: no subscribed devices", run_id, status)
            return
        messages = [build_message(t, run_id, status, self.settings.deep_link_base) for t in tokens]

        if self.settings.dry_run or self.expo is None:
            logger.info(
                "DRY RUN (SIDE_PUSH_DRY_RUN=1): would POST %d message(s) to %s\n%s",
                len(messages),
                self.settings.expo_push_url,
                json.dumps(messages, indent=2),
            )
            for t in tokens:
                self.store.add_delivery(run_id, status, t, state="dry_run")
            summary["dry_run"] = len(tokens)
            return

        tickets = await self.expo.send(messages)
        dead: list[str] = []
        for ticket in tickets:
            if ticket.status == "ok" and ticket.id:
                self.store.add_delivery(
                    run_id, status, ticket.token, state="pending", ticket_id=ticket.id
                )
                summary["sent"] += 1
            else:
                self.store.add_delivery(
                    run_id,
                    status,
                    ticket.token,
                    state="error",
                    error=ticket.error,
                    message=ticket.message,
                )
                summary["errors"] += 1
                if ticket.error == "RequestFailed":
                    summary["failed"] += 1
                if ticket.error == "DeviceNotRegistered":
                    dead.append(ticket.token)
        if dead:
            summary["pruned"] = self.store.delete_devices(dead)
            logger.info("pruned %d unregistered device(s)", summary["pruned"])
        logger.info("run %s %s: push summary %s", run_id, status, summary)

    async def check_receipts(self, min_age_s: float | None = None) -> dict[str, int]:
        """Resolve pending tickets via the Expo receipts API and prune dead tokens."""
        summary = {"checked": 0, "ok": 0, "errors": 0, "pruned": 0, "pending": 0, "expired": 0}
        if self.expo is None:
            return summary
        if min_age_s is None:
            min_age_s = self.settings.receipt_min_age_s
        pending = self.store.pending_tickets(min_age_s)
        if not pending:
            return summary
        receipts, queried = await self.expo.get_receipts([tid for tid, _, _ in pending])
        now = time.time()
        dead: list[str] = []
        for ticket_id, token, created_at in pending:
            summary["checked"] += 1
            receipt = receipts.get(ticket_id)
            if receipt is None:
                if ticket_id in queried and now - created_at > RECEIPT_TTL_S:
                    self.store.resolve_ticket(ticket_id, "expired")
                    summary["expired"] += 1
                else:
                    summary["pending"] += 1
                continue
            if receipt.get("status") == "ok":
                self.store.resolve_ticket(ticket_id, "ok")
                summary["ok"] += 1
                continue
            error = (receipt.get("details") or {}).get("error") or "Unknown"
            message = receipt.get("message")
            self.store.resolve_ticket(ticket_id, "error", error=error, message=message)
            summary["errors"] += 1
            logger.warning("receipt %s error %s: %s", ticket_id, error, message)
            if error == "DeviceNotRegistered":
                dead.append(token)
        if dead:
            summary["pruned"] = self.store.delete_devices(dead)
        logger.info("receipt check summary %s", summary)
        return summary
