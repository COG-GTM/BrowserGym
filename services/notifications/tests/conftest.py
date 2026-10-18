from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from side_notifications.app import create_app
from side_notifications.config import Settings

os.environ.setdefault("SIDE_PUSH_DRY_RUN", "1")

PUSH_URL = "https://exp.host/--/api/v2/push/send"
RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"


def token(n: int | str) -> str:
    return f"ExponentPushToken[tok-{n}]"


@pytest.fixture
def make_settings(tmp_path):
    def _make(**overrides) -> Settings:
        base = dict(
            db_path=str(tmp_path / "notifications.db"),
            dry_run=True,
            backoff_base_s=0.0,
            backoff_max_s=0.0,
            receipt_interval_s=0,  # no background loop in tests
            receipt_min_age_s=0,
        )
        base.update(overrides)
        return Settings(**base)

    return _make


@pytest.fixture
def make_client(make_settings):
    clients: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        client = TestClient(create_app(make_settings(**overrides)))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def register(client: TestClient, tok: str, platform: str = "ios", run_ids=None):
    body = {"expo_push_token": tok, "platform": platform}
    if run_ids is not None:
        body["run_ids"] = run_ids
    resp = client.post("/api/v1/devices", json=body)
    assert resp.status_code == 201, resp.text
    return resp


def status_event(run_id: str, status: str = "succeeded") -> dict:
    return {
        "type": "status",
        "run_id": run_id,
        "status": status,
        "timestamp": "2026-10-18T02:40:00Z",
    }
