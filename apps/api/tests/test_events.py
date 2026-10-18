from __future__ import annotations

import socket
import sys
import threading
import time

import httpx
import pytest
import uvicorn

from side_api.main import create_app

from .conftest import parse_sse


def _stream(api, run_id: str, headers: dict | None = None) -> list[dict]:
    resp = api.get(f"/runs/{run_id}/events", headers=headers or {})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    return parse_sse(resp.text)


def test_sse_streams_full_run_and_closes(api, contract):
    run = api.create_run()
    events = _stream(api, run["id"])  # returns only once the stream closes

    for ev in events:
        contract.validate_schema("RunEvent", ev["data"])
        assert ev["event"] == ev["data"]["type"]
        assert ev["data"]["run_id"] == run["id"]

    statuses = [e["data"]["status"] for e in events if e["event"] == "status"]
    assert statuses == ["queued", "running", "succeeded"]
    assert events[-1]["event"] == "status" and events[-1]["data"]["status"] == "succeeded"

    steps = [e["data"]["step"] for e in events if e["event"] == "step"]
    assert [s["index"] for s in steps] == [0, 1, 2, 3, 4]
    assert all(s["screenshot_url"].endswith(f"/steps/{s['index']}/screenshot") for s in steps)
    assert any(e["event"] == "chat" for e in events)
    assert any(e["event"] == "log" for e in events)
    assert [int(e["id"]) for e in events] == list(range(1, len(events) + 1))


def test_sse_replays_finished_run_and_resumes_from_last_event_id(api):
    run = api.create_run()
    api.wait_for(run["id"])
    full = _stream(api, run["id"])
    resumed = _stream(api, run["id"], headers={"Last-Event-ID": full[-4]["id"]})
    assert [e["id"] for e in resumed] == [e["id"] for e in full[-3:]]
    assert resumed[-1]["data"]["status"] == "succeeded"


def test_sse_closes_with_synthesized_status_if_runner_never_wrote_one(make_api, settings):
    # runner exits immediately without writing anything -> API marks the run failed
    settings.runner_cmd = f"{sys.executable} -c \"import sys; print('boom'); sys.exit(3)\""
    api = make_api(settings)
    run = api.create_run()
    events = _stream(api, run["id"])
    assert [e["data"].get("status") for e in events] == ["queued", "failed"]
    done = api.get(f"/runs/{run['id']}").json()
    assert done["status"] == "failed"
    assert "code 3" in done["error"] and "boom" in done["error"]


def test_sse_unknown_run_404(api):
    assert api.get("/runs/nope/events", validate=False).status_code == 404


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(settings):
    settings.fake_step_delay = 0.3
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}/api/v1"
    server.should_exit = True
    thread.join(timeout=10)


def test_sse_is_incremental_over_real_http(live_server):
    """Over a real socket, events arrive while the run is still in progress."""
    with httpx.Client(base_url=live_server, timeout=20) as client:
        run = client.post(
            "/runs",
            json={"task_id": "browsergym/openended", "agent": {"type": "mock"}, "goal": "g"},
        ).json()
        received: list[tuple[float, str]] = []
        t0 = time.monotonic()
        with client.stream("GET", f"/runs/{run['id']}/events") as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    received.append((time.monotonic() - t0, line.removeprefix("event: ")))
        assert received[0][1] == "status"
        # first event well before the run (4 steps x 0.3s) finished
        assert received[0][0] < 0.5 < received[-1][0]
        assert client.get(f"/runs/{run['id']}").json()["status"] == "succeeded"


def test_get_run_is_terminal_as_soon_as_sse_closes(make_api, settings):
    settings.poll_interval = 5.0  # monitor lags; reads must still reflect artifacts
    api = make_api(settings)
    run = api.create_run()
    _stream(api, run["id"])
    done = api.get(f"/runs/{run['id']}").json()
    assert done["status"] == "succeeded" and done["n_steps"] == 4 and done["reward"] == 1.0


def test_sse_reconnect_after_terminal_event_closes_without_duplicate(api):
    run = api.create_run()
    full = _stream(api, run["id"])
    resumed = _stream(api, run["id"], headers={"Last-Event-ID": full[-1]["id"]})
    assert resumed == []
