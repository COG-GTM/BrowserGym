from __future__ import annotations

import sys
from pathlib import Path

import pytest

from side_api.storage import RunPaths


def test_create_run_returns_queued_and_completes(api, settings):
    run = api.create_run()
    assert run["status"] == "queued"
    assert run["agent"] == {
        "type": "mock",
        "model": None,
        "use_screenshot": False,
        "use_axtree": True,
    }
    assert run["n_steps"] == 0 and run["max_steps"] == 10
    assert run["created_at"].endswith("Z")

    done = api.wait_for(run["id"])
    assert done["status"] == "succeeded"
    assert done["reward"] == 1.0
    assert done["n_steps"] == 4
    assert done["started_at"] and done["finished_at"]

    paths = RunPaths(settings.data_dir, run["id"])
    assert paths.run_json.is_file() and paths.events.is_file() and paths.chat.is_file()
    assert paths.step_indices() == [0, 1, 2, 3, 4]


@pytest.mark.parametrize(
    "body, fragment",
    [
        ({"agent": {"type": "mock"}}, "task_id"),
        ({"task_id": "browsergym/openended", "goal": "x"}, "agent"),
        ({"task_id": "browsergym/openended", "goal": "x", "agent": {"type": "gpt"}}, "agent.type"),
        (
            {
                "task_id": "browsergym/openended",
                "goal": "x",
                "agent": {"type": "mock"},
                "max_steps": 0,
            },
            "max_steps",
        ),
        (
            {
                "task_id": "browsergym/openended",
                "goal": "x",
                "agent": {"type": "mock"},
                "max_steps": 101,
            },
            "max_steps",
        ),
        ({"task_id": "browsergym/nope", "agent": {"type": "mock"}}, "unknown task_id"),
        ({"task_id": "browsergym/openended", "agent": {"type": "mock"}}, "goal is required"),
    ],
)
def test_create_run_validation(api, body, fragment):
    resp = api.post("/runs", json=body)
    assert resp.status_code == 422
    assert isinstance(resp.json()["detail"], str)
    assert fragment in resp.json()["detail"]


def test_non_openended_task_needs_no_goal(api):
    run = api.create_run(task_id="browsergym/miniwob.click-test", goal=None, max_steps=2)
    done = api.wait_for(run["id"])
    assert done["status"] == "succeeded"
    assert done["n_steps"] == 2


def test_list_runs_pagination_and_filter(api):
    ids = [api.create_run(max_steps=1)["id"] for _ in range(5)]
    for run_id in ids:
        api.wait_for(run_id)

    page = api.get("/runs", params={"limit": 2}).json()
    assert [r["id"] for r in page["items"]] == ids[::-1][:2]
    assert page["next_cursor"]
    seen = [r["id"] for r in page["items"]]
    while page["next_cursor"]:
        page = api.get("/runs", params={"limit": 2, "cursor": page["next_cursor"]}).json()
        seen += [r["id"] for r in page["items"]]
    assert seen == ids[::-1]

    assert len(api.get("/runs", params={"status": "succeeded"}).json()["items"]) == 5
    assert api.get("/runs", params={"status": "running"}).json() == {
        "items": [],
        "next_cursor": None,
    }
    assert api.get("/runs", params={"limit": 201}, validate=False).status_code == 422
    assert api.get("/runs", params={"cursor": "garbage"}, validate=False).status_code == 422


def test_get_run_404(api):
    resp = api.get("/runs/doesnotexist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_steps_detail_and_screenshot(api):
    run = api.create_run()
    api.wait_for(run["id"])

    steps = api.get(f"/runs/{run['id']}/steps").json()
    assert [s["index"] for s in steps] == [0, 1, 2, 3, 4]
    assert steps[0]["action"] is None
    assert steps[1]["action"] == "noop(500)"
    assert steps[-1]["action"].startswith("send_msg_to_user(")
    assert steps[-1]["terminated"] is True and steps[-1]["reward"] == 1.0
    assert "axtree_txt" not in steps[0]
    for s in steps:
        assert s["screenshot_url"] == f"/api/v1/runs/{run['id']}/steps/{s['index']}/screenshot"

    detail = api.get(f"/runs/{run['id']}/steps/3").json()
    assert detail["index"] == 3
    assert "[a42] button 'Submit'" in detail["axtree_txt"]
    assert detail["pruned_html"].startswith("<body>")
    assert detail["focused_element_bid"] == "a42"

    png = api.get(f"/runs/{run['id']}/steps/3/screenshot")
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"\x89PNG\r\n\x1a\n") and len(png.content) > 1000

    # screenshot_url follows the API, not whatever the runner wrote
    assert api.client.get(steps[0]["screenshot_url"]).status_code == 200

    assert api.get(f"/runs/{run['id']}/steps/99", validate=False).status_code == 404
    assert api.get(f"/runs/{run['id']}/steps/99/screenshot", validate=False).status_code == 404
    assert api.get(f"/runs/{run['id']}/steps/-1", validate=False).status_code == 422
    assert api.get("/runs/nope/steps", validate=False).status_code == 404


def test_chat_roundtrip(make_api, settings):
    settings.fake_step_delay = 0.3
    api = make_api(settings)
    run = api.create_run()
    api.wait_for(run["id"], statuses={"running"})

    resp = api.post(f"/runs/{run['id']}/chat", json={"message": "Use the top nav"})
    assert resp.status_code == 201
    msg = resp.json()
    assert msg["role"] == "user" and msg["message"] == "Use the top nav"

    inbox = RunPaths(settings.data_dir, run["id"]).inbox.read_text()
    assert '"message": "Use the top nav"' in inbox

    api.wait_for(run["id"])
    chat = api.get(f"/runs/{run['id']}/chat").json()
    roles = [(m["role"], m["message"]) for m in chat]
    assert roles[0][0] == "assistant"
    assert ("user", "Find the pricing page") in roles
    assert ("user", "Use the top nav") in roles  # echoed by the runner
    assert ("assistant", "Noted: Use the top nav") in roles
    assert roles[-1] == ("assistant", "Done: Find the pricing page")

    assert (
        api.post(f"/runs/{run['id']}/chat", json={"message": ""}, validate=False).status_code == 422
    )
    assert api.post("/runs/nope/chat", json={"message": "hi"}, validate=False).status_code == 404


def test_infeasible_and_failure_goals(api):
    run = api.create_run(goal="Do the impossible [infeasible]")
    done = api.wait_for(run["id"])
    assert done["status"] == "succeeded" and done["reward"] == 0.0
    assert api.get(f"/runs/{run['id']}/chat").json()[-1]["role"] == "infeasible"

    run = api.create_run(goal="Break please [fail]")
    done = api.wait_for(run["id"])
    assert done["status"] == "failed"
    assert "simulated failure" in done["error"]


def test_cancel_running_run(make_api, settings):
    settings.fake_step_delay = 0.5
    api = make_api(settings)
    run = api.create_run()
    api.wait_for(run["id"], statuses={"running"})

    resp = api.post(f"/runs/{run['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"running", "cancelled"}
    assert RunPaths(settings.data_dir, run["id"]).cancel.is_file()

    done = api.wait_for(run["id"])
    assert done["status"] == "cancelled"
    assert done["n_steps"] < 4
    # cancelling again is a no-op
    assert api.post(f"/runs/{run['id']}/cancel").json()["status"] == "cancelled"


def test_cancel_queued_run_is_immediate(make_api, settings, tmp_path):
    # A runner that never reports anything keeps the run queued.
    settings.runner_cmd = f'{sys.executable} -c "import time; time.sleep(30)"'
    api = make_api(settings)
    run = api.create_run()
    assert api.get(f"/runs/{run['id']}").json()["status"] == "queued"
    resp = api.post(f"/runs/{run['id']}/cancel")
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["finished_at"]
    assert api.post("/runs/nope/cancel", validate=False).status_code == 404


def test_delete_run(api, settings):
    run = api.create_run()
    api.wait_for(run["id"])
    root = RunPaths(settings.data_dir, run["id"]).root
    assert root.is_dir()

    resp = api.delete(f"/runs/{run['id']}")
    assert resp.status_code == 204
    assert not root.exists()
    assert api.get(f"/runs/{run['id']}").status_code == 404
    assert api.delete(f"/runs/{run['id']}").status_code == 204  # idempotent


def test_delete_running_run_stops_it(make_api, settings):
    settings.fake_step_delay = 0.5
    api = make_api(settings)
    run = api.create_run()
    api.wait_for(run["id"], statuses={"running"})
    assert api.delete(f"/runs/{run['id']}").status_code == 204
    assert api.get(f"/runs/{run['id']}").status_code == 404
    assert not RunPaths(settings.data_dir, run["id"]).root.exists()


def test_path_traversal_ids_rejected(api):
    assert api.get("/runs/..%2F..%2Fetc", validate=False).status_code == 404


def test_index_survives_restart(make_api, settings):
    api = make_api(settings)
    run = api.create_run()
    api.wait_for(run["id"])
    api2 = make_api(settings)
    assert api2.get(f"/runs/{run['id']}").json()["status"] == "succeeded"
    assert len(api2.get(f"/runs/{run['id']}/steps").json()) == 5


def test_orphaned_run_marked_failed_on_restart(make_api, settings):
    settings.runner_cmd = f'{sys.executable} -c "import time; time.sleep(30)"'
    api = make_api(settings)
    run = api.create_run()
    # simulate an API restart where the runner process is gone
    api.client.__exit__(None, None, None)
    from side_api.db import RunRecord, make_engine, session

    engine = make_engine(settings.resolved_db_url)
    with session(engine) as s:
        rec = s.get(RunRecord, run["id"])
        rec.pid = 999999999
        s.add(rec)
        s.commit()
    settings.runner_cmd = None
    api2 = make_api(settings)
    done = api2.wait_for(run["id"])
    assert done["status"] == "failed"
    assert "no longer running" in done["error"]


def test_data_dir_layout(api, settings):
    run = api.create_run(max_steps=2)
    api.wait_for(run["id"])
    files = sorted(
        str(p.relative_to(settings.data_dir)) for p in Path(settings.data_dir, "runs").rglob("*")
    )
    rid = run["id"]
    for expected in [
        f"runs/{rid}/run.json",
        f"runs/{rid}/events.jsonl",
        f"runs/{rid}/chat.jsonl",
        f"runs/{rid}/steps/0.json",
        f"runs/{rid}/steps/0.png",
        f"runs/{rid}/steps/2.json",
    ]:
        assert expected in files


def test_chat_on_finished_run_is_kept(api):
    run = api.create_run()
    api.wait_for(run["id"])
    assert api.post(f"/runs/{run['id']}/chat", json={"message": "thanks!"}).status_code == 201
    assert api.get(f"/runs/{run['id']}/chat").json()[-1]["message"] == "thanks!"
