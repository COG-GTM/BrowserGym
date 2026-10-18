from __future__ import annotations

import json
import logging

import pytest

from tests.conftest import register, status_event, token


def test_non_status_and_non_terminal_events_are_ignored(client):
    register(client, token(1))
    events = [
        {"type": "step", "run_id": "r1", "timestamp": "2026-10-18T00:00:00Z", "step": {}},
        {"type": "log", "run_id": "r1", "timestamp": "2026-10-18T00:00:00Z", "log": "hi"},
        status_event("r1", "queued"),
        status_event("r1", "running"),
    ]
    for ev in events:
        resp = client.post("/internal/run-events", json=ev)
        assert resp.status_code == 202
        assert resp.json()["action"] == "ignored"
    assert client.app.state.store.deliveries() == []


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_terminal_status_dry_run_logs_payload(client, caplog, status):
    register(client, token(1), "ios")
    with caplog.at_level(logging.INFO, logger="side_notifications.push"):
        resp = client.post("/internal/run-events", json=status_event("run-42", status))
    assert resp.status_code == 202
    assert resp.json() == {"accepted": True, "action": "queued", "recipients": 1, "reason": None}

    dry = [r for r in caplog.records if "DRY RUN" in r.getMessage()]
    assert len(dry) == 1
    payload = json.loads(dry[0].getMessage().split("\n", 1)[1])
    assert payload == [
        {
            "to": token(1),
            "title": f"Run {status}",
            "body": f"Run run-42 {status}. Tap to replay the trace.",
            "sound": "default",
            "priority": "high",
            "data": {
                "type": "run_status",
                "run_id": "run-42",
                "status": status,
                "url": "side://runs/run-42",
            },
        }
    ]
    [d] = client.app.state.store.deliveries("run-42")
    assert (d.token, d.state, d.status) == (token(1), "dry_run", status)


def test_subscription_filtering(client):
    register(client, token("all"))  # no run_ids = all runs
    register(client, token("x"), run_ids=["run-x"])
    register(client, token("y"), run_ids=["run-y"])
    resp = client.post("/internal/run-events", json=status_event("run-x"))
    assert resp.json()["recipients"] == 2
    tokens = sorted(d.token for d in client.app.state.store.deliveries("run-x"))
    assert tokens == sorted([token("all"), token("x")])


def test_duplicate_terminal_event_notifies_once(client):
    register(client, token(1))
    first = client.post("/internal/run-events", json=status_event("r1"))
    second = client.post("/internal/run-events", json=status_event("r1"))
    assert first.json()["action"] == "queued"
    assert second.json()["action"] == "duplicate"
    assert len(client.app.state.store.deliveries("r1")) == 1


def test_no_subscribers(client):
    resp = client.post("/internal/run-events", json=status_event("lonely"))
    assert resp.json()["recipients"] == 0


def test_invalid_event_422(client):
    assert client.post("/internal/run-events", json={"type": "status"}).status_code == 422
    bad_status = status_event("r1", "exploded")
    assert client.post("/internal/run-events", json=bad_status).status_code == 422


def test_internal_secret(make_client):
    client = make_client(internal_secret="s3cret")
    ev = status_event("r1")
    assert client.post("/internal/run-events", json=ev).status_code == 401
    wrong = {"X-Side-Notify-Secret": "nope"}
    assert client.post("/internal/run-events", json=ev, headers=wrong).status_code == 401
    ok = {"X-Side-Notify-Secret": "s3cret"}
    assert client.post("/internal/run-events", json=ev, headers=ok).status_code == 202
    assert client.get("/internal/deliveries").status_code == 401
    assert client.get("/internal/deliveries", headers=ok).status_code == 200
    # public device endpoints don't need the secret
    register(client, token(1))
