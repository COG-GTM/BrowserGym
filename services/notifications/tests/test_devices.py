from __future__ import annotations

from urllib.parse import quote

from tests.conftest import register, token


def test_health(client):
    for path in ("/health", "/api/v1/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_register_device_201(client):
    resp = register(client, token(1), "ios", ["run-a", "run-b", "run-a"])
    body = resp.json()
    assert body["created"] is True
    assert body["run_ids"] == ["run-a", "run-b"]
    device = client.app.state.store.get_device(token(1))
    assert device.platform == "ios"
    assert device.run_ids == ["run-a", "run-b"]


def test_reregister_replaces_registration(client):
    register(client, token(1), "ios", ["run-a"])
    resp = register(client, token(1), "android", [])
    assert resp.json()["created"] is False
    device = client.app.state.store.get_device(token(1))
    assert device.platform == "android"
    assert device.run_ids == []


def test_accepts_expo_push_token_prefix(client):
    register(client, "ExpoPushToken[abc]", "android")


def test_rejects_invalid_token_and_platform(client):
    bad = [
        {"expo_push_token": "not-a-token", "platform": "ios"},
        {"expo_push_token": token(1), "platform": "windows"},
        {"platform": "ios"},
    ]
    for body in bad:
        assert client.post("/api/v1/devices", json=body).status_code == 422


def test_delete_device(client):
    register(client, token(1))
    resp = client.delete(f"/api/v1/devices/{quote(token(1))}")
    assert resp.status_code == 204
    assert client.app.state.store.get_device(token(1)) is None
    # idempotent
    assert client.delete(f"/api/v1/devices/{quote(token(1))}").status_code == 204


def test_registration_persists_across_restarts(make_client):
    register(make_client(), token(1), run_ids=["r1"])
    second = make_client()
    assert second.app.state.store.get_device(token(1)).run_ids == ["r1"]
