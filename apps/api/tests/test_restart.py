"""Behaviour across an API restart while a subprocess runner is still alive."""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

from side_api.runners import pid_alive


def _restart_with_live_runner(make_api, settings):
    # The sleeper receives the runner-contract args (incl. --run-id) on its command line.
    settings.runner_cmd = f'{sys.executable} -c "import time; time.sleep(60)"'
    api = make_api(settings)
    run = api.create_run()
    pid = api.client.app.state.manager.handles[run["id"]].pid
    api.client.__exit__(None, None, None)  # API "crashes"; runner keeps going
    assert pid_alive(pid)
    settings.runner_cmd = None
    return run, pid


def _wait_dead(pid: int, timeout: float = 10) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


def test_delete_after_restart_stops_recovered_runner(make_api, settings):
    run, pid = _restart_with_live_runner(make_api, settings)
    api2 = make_api(settings)
    assert api2.get(f"/runs/{run['id']}").json()["status"] == "queued"
    assert api2.delete(f"/runs/{run['id']}").status_code == 204
    assert _wait_dead(pid)
    assert not (settings.data_dir / "runs" / run["id"]).exists()


def test_resume_does_not_renotify_old_statuses(make_api, settings):
    received: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(202)

    run, pid = _restart_with_live_runner(make_api, settings)
    settings.notify_url = "http://notify.test"
    api2 = make_api(settings)
    api2.client.app.state.manager.notifier.transport = httpx.MockTransport(handler)
    time.sleep(0.3)  # resumed monitor has replayed the existing log
    assert received == []
    assert api2.post(f"/runs/{run['id']}/cancel").json()["status"] == "cancelled"
    assert _wait_dead(pid)
    deadline = time.monotonic() + 5
    while not received and time.monotonic() < deadline:
        time.sleep(0.05)
    assert [e["status"] for e in received] == ["cancelled"]


def test_recovered_runner_ignoring_cancel_is_killed_after_grace(make_api, settings, monkeypatch):
    import side_api.monitor as monitor

    monkeypatch.setattr(monitor, "CANCEL_GRACE_SECONDS", 0.3)
    run, pid = _restart_with_live_runner(make_api, settings)
    api2 = make_api(settings)
    # Mark the run as running so cancel goes through the cooperative CANCEL path.
    from side_api.db import RunRecord, session

    engine = api2.client.app.state.manager.engine
    with session(engine) as s:
        rec = s.get(RunRecord, run["id"])
        rec.status = "running"
        s.add(rec)
        s.commit()
    assert api2.post(f"/runs/{run['id']}/cancel").json()["status"] == "running"
    assert (settings.data_dir / "runs" / run["id"] / "CANCEL").exists()
    assert api2.wait_for(run["id"])["status"] == "cancelled"
    assert _wait_dead(pid)


def test_sse_resume_tolerates_malformed_status(api, settings):
    run = api.create_run()
    api.wait_for(run["id"])
    events = settings.data_dir / "runs" / run["id"] / "events.jsonl"
    lines = events.read_text().splitlines()
    lines.insert(1, json.dumps({"type": "status", "run_id": run["id"], "status": ["x"]}))
    events.write_text("\n".join(lines) + "\n")
    resp = api.get(f"/runs/{run['id']}/events", headers={"Last-Event-ID": "3"})
    assert resp.status_code == 200 and "succeeded" in resp.text
