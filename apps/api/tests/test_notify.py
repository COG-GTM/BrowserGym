from __future__ import annotations

import json
import time

import httpx


def test_status_events_posted_to_notify_url(make_api, settings, contract):
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(202)

    settings.notify_url = "http://notify.test"
    api = make_api(settings)
    api.client.app.state.manager.notifier.transport = httpx.MockTransport(handler)

    run = api.create_run()
    api.wait_for(run["id"])
    api.get(f"/runs/{run['id']}/events")  # stream closes after terminal status

    deadline = time.monotonic() + 5
    while len(received) < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert {str(r.url) for r in received} == {"http://notify.test/internal/run-events"}
    bodies = [json.loads(r.content) for r in received]
    for body in bodies:
        contract.validate_schema("RunEvent", body)
        assert body["type"] == "status" and body["run_id"] == run["id"]
    assert [b["status"] for b in bodies] == ["queued", "running", "succeeded"]


def test_notify_failures_do_not_break_runs(make_api, settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    settings.notify_url = "http://notify.test"
    api = make_api(settings)
    api.client.app.state.manager.notifier.transport = httpx.MockTransport(handler)
    assert api.wait_for(api.create_run()["id"])["status"] == "succeeded"


def test_devices_without_notify_url_accepted(api):
    body = {"expo_push_token": "ExponentPushToken[x]", "platform": "ios", "run_ids": []}
    assert api.post("/devices", json=body).status_code == 201
    bad = api.post("/devices", json={"expo_push_token": "t", "platform": "web"}, validate=False)
    assert bad.status_code == 422


def test_devices_proxied_to_notifications_service(make_api, settings):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201)

    settings.notify_url = "http://notify.test"
    api = make_api(settings)
    api.client.app.state.manager.notifier.transport = httpx.MockTransport(handler)
    body = {"expo_push_token": "ExponentPushToken[x]", "platform": "android", "run_ids": ["r1"]}
    assert api.post("/devices", json=body).status_code == 201
    assert str(seen[0].url) == "http://notify.test/api/v1/devices"
    assert json.loads(seen[0].content) == body
