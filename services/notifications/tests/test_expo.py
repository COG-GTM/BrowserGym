from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from side_notifications.expo import ExpoClient
from tests.conftest import PUSH_URL, RECEIPTS_URL, register, status_event, token


def ok_tickets(request: httpx.Request, prefix: str = "t") -> httpx.Response:
    msgs = json.loads(request.content)
    return httpx.Response(
        200, json={"data": [{"status": "ok", "id": f"{prefix}-{m['to']}"} for m in msgs]}
    )


@pytest.fixture
def live_client(make_client):
    """App with dry run off; Expo is mocked by respx in each test."""
    return make_client(dry_run=False, max_retries=2)


@respx.mock
def test_batches_of_100(live_client):
    route = respx.post(PUSH_URL).mock(side_effect=ok_tickets)
    for i in range(250):
        register(live_client, token(i))
    resp = live_client.post("/internal/run-events", json=status_event("big"))
    assert resp.json()["recipients"] == 250
    sizes = [len(json.loads(c.request.content)) for c in route.calls]
    assert sizes == [100, 100, 50]
    req = route.calls[0].request
    assert req.headers["content-type"] == "application/json"
    assert "authorization" not in req.headers
    deliveries = live_client.app.state.store.deliveries("big", limit=1000)
    assert len(deliveries) == 250
    assert {d.state for d in deliveries} == {"pending"}


@respx.mock
def test_retries_5xx_and_429_then_succeeds(live_client):
    route = respx.post(PUSH_URL).mock(
        side_effect=[
            httpx.Response(503, text="unavailable"),
            httpx.Response(429, headers={"Retry-After": "0"}, text="slow down"),
            ok_tickets,
        ]
    )
    register(live_client, token(1))
    live_client.post("/internal/run-events", json=status_event("r1"))
    assert route.call_count == 3
    [d] = live_client.app.state.store.deliveries("r1")
    assert d.state == "pending" and d.ticket_id == f"t-{token(1)}"


@respx.mock
def test_retries_transport_errors(live_client):
    route = respx.post(PUSH_URL).mock(side_effect=[httpx.ConnectError("boom"), ok_tickets])
    register(live_client, token(1))
    live_client.post("/internal/run-events", json=status_event("r1"))
    assert route.call_count == 2
    assert live_client.app.state.store.deliveries("r1")[0].state == "pending"


@respx.mock
def test_gives_up_after_max_retries(live_client):
    route = respx.post(PUSH_URL).mock(return_value=httpx.Response(500, text="nope"))
    register(live_client, token(1))
    live_client.post("/internal/run-events", json=status_event("r1"))
    assert route.call_count == 3  # 1 + max_retries(2)
    [d] = live_client.app.state.store.deliveries("r1")
    assert (d.state, d.error) == ("error", "RequestFailed")
    # device is kept: a request failure says nothing about the token
    assert live_client.app.state.store.get_device(token(1)) is not None


@respx.mock
def test_4xx_is_not_retried(live_client):
    route = respx.post(PUSH_URL).mock(
        return_value=httpx.Response(400, json={"errors": [{"code": "VALIDATION_ERROR"}]})
    )
    register(live_client, token(1))
    live_client.post("/internal/run-events", json=status_event("r1"))
    assert route.call_count == 1


@respx.mock
def test_ticket_device_not_registered_prunes_device(live_client):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"status": "ok", "id": "good"},
                    {
                        "status": "error",
                        "message": f'"{token("dead")}" is not a registered push notification '
                        "recipient",
                        "details": {"error": "DeviceNotRegistered", "expoPushToken": token("dead")},
                    },
                ]
            },
        )

    respx.post(PUSH_URL).mock(side_effect=respond)
    register(live_client, token("good"))
    register(live_client, token("dead"))
    live_client.post("/internal/run-events", json=status_event("r1"))
    store = live_client.app.state.store
    assert store.get_device(token("good")) is not None
    assert store.get_device(token("dead")) is None
    states = {d.token: (d.state, d.error) for d in store.deliveries("r1")}
    assert states[token("dead")] == ("error", "DeviceNotRegistered")
    assert states[token("good")] == ("pending", None)


@respx.mock
def test_receipt_check_resolves_and_prunes(live_client):
    respx.post(PUSH_URL).mock(side_effect=ok_tickets)
    for name in ("ok", "dead", "later", "big"):
        register(live_client, token(name))
    live_client.post("/internal/run-events", json=status_event("r1"))

    receipts_route = respx.post(RECEIPTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    f"t-{token('ok')}": {"status": "ok"},
                    f"t-{token('dead')}": {
                        "status": "error",
                        "message": "not registered",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                    f"t-{token('big')}": {
                        "status": "error",
                        "message": "too big",
                        "details": {"error": "MessageTooBig"},
                    },
                }
            },
        )
    )
    resp = live_client.post("/internal/receipts/check", params={"min_age_s": 0})
    assert resp.status_code == 200
    assert resp.json() == {
        "checked": 4,
        "ok": 1,
        "errors": 2,
        "pruned": 1,
        "pending": 1,
        "expired": 0,
    }
    sent_ids = sorted(json.loads(receipts_route.calls[0].request.content)["ids"])
    assert sent_ids == sorted(f"t-{token(n)}" for n in ("ok", "dead", "later", "big"))

    store = live_client.app.state.store
    assert store.get_device(token("dead")) is None
    assert store.get_device(token("big")) is not None
    states = {d.token: d.state for d in store.deliveries("r1")}
    assert states == {
        token("ok"): "ok",
        token("dead"): "error",
        token("big"): "error",
        token("later"): "pending",
    }
    # only the still-pending ticket is re-checked
    live_client.post("/internal/receipts/check", params={"min_age_s": 0})
    assert json.loads(receipts_route.calls[1].request.content)["ids"] == [f"t-{token('later')}"]


@respx.mock
def test_receipt_min_age_is_respected(live_client):
    respx.post(PUSH_URL).mock(side_effect=ok_tickets)
    receipts_route = respx.post(RECEIPTS_URL).mock(return_value=httpx.Response(200, json={}))
    register(live_client, token(1))
    live_client.post("/internal/run-events", json=status_event("r1"))
    resp = live_client.post("/internal/receipts/check", params={"min_age_s": 3600})
    assert resp.json()["checked"] == 0
    assert receipts_route.call_count == 0


@respx.mock
def test_access_token_header(make_client):
    route = respx.post(PUSH_URL).mock(side_effect=ok_tickets)
    client = make_client(dry_run=False, expo_access_token="expo-test-token")
    register(client, token(1))
    client.post("/internal/run-events", json=status_event("r1"))
    assert route.calls[0].request.headers["authorization"] == "Bearer expo-test-token"


@respx.mock
def test_dry_run_never_calls_expo(make_client):
    route = respx.post(PUSH_URL).mock(side_effect=ok_tickets)
    client = make_client(dry_run=True)
    register(client, token(1))
    client.post("/internal/run-events", json=status_event("r1"))
    assert route.call_count == 0


def test_expo_client_receipts_batched_by_1000():
    async def run():
        async with respx.mock() as mock:
            empty = httpx.Response(200, json={"data": {}})
            route = mock.post(RECEIPTS_URL).mock(return_value=empty)
            async with httpx.AsyncClient() as http:
                await ExpoClient(http).get_receipts([f"id-{i}" for i in range(2500)])
            return [len(json.loads(c.request.content)["ids"]) for c in route.calls]

    assert asyncio.run(run()) == [1000, 1000, 500]


def test_backoff_exponential_and_capped():
    client = ExpoClient(httpx.AsyncClient(), backoff_base_s=0.5, backoff_max_s=3)
    assert [client._backoff(i, None) for i in range(4)] == [0.5, 1.0, 2.0, 3]
    assert client._backoff(0, "2") == 2.0
    assert client._backoff(0, "60") == 3
