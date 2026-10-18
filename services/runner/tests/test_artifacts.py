import json

import pytest
import numpy as np
from PIL import Image

from side_runner.artifacts import RunStore
from side_runner.obs import build_step, step_summary
from side_runner.timeutil import iso

from conftest import assert_valid


def test_inbox_reads_only_complete_new_lines(tmp_path):
    store = RunStore(tmp_path, "r1")
    store.ensure_dirs()
    assert store.read_new_inbox() == []
    with open(store.inbox_jsonl, "w") as f:
        f.write(json.dumps({"role": "user", "message": "a"}) + "\n" + '{"role": "user", "mess')
    assert [m["message"] for m in store.read_new_inbox()] == ["a"]
    with open(store.inbox_jsonl, "a") as f:
        f.write('age": "b"}\nnot json\n')
    msgs = store.read_new_inbox()
    assert msgs[0]["message"] == "b" and "_invalid" in msgs[1]
    assert store.read_new_inbox() == []


def test_events_and_screenshot(tmp_path):
    store = RunStore(tmp_path, "r1")
    store.ensure_dirs()
    ev = store.append_event("status", status="running")
    assert_valid("RunEvent", ev)
    assert json.loads(store.events_jsonl.read_text()) == ev
    path = store.write_screenshot(0, np.full((20, 30, 3), 200, dtype=np.uint8))
    assert Image.open(path).size == (30, 20)
    assert not list(store.steps_dir.glob(".*"))  # no temp files left behind


def test_build_step_maps_empty_strings_to_null():
    obs = {
        "url": "http://x/",
        "last_action_error": "",
        "focused_element_bid": "",
        "axtree_txt": "t",
    }
    step = build_step(
        run_id="r1",
        index=2,
        obs=obs,
        action="noop()",
        thought=None,
        reward=np.float64(1),
        terminated=False,
        truncated=False,
        elapsed_ms=12.345,
        timestamp=iso(),
        has_screenshot=True,
    )
    assert_valid("StepDetail", step)
    assert step["last_action_error"] is None and step["focused_element_bid"] is None
    assert step["screenshot_url"] == "/runs/r1/steps/2/screenshot" and step["elapsed_ms"] == 12.3
    assert_valid("Step", step_summary(step))
    assert "axtree_txt" not in step_summary(step)


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", "", ".hidden", "a\\b", "x" * 200])
def test_run_store_rejects_path_like_run_ids(tmp_path, bad):
    with pytest.raises(ValueError):
        RunStore(tmp_path, bad)
