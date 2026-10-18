import json
import multiprocessing
import os
import socket
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ProcessPoolExecutor

import pytest

from browsergym.assistantbench import utils
from browsergym.assistantbench.utils import add_prediction_to_jsonl


def _read(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _lock_path(output_file):
    return output_file.with_suffix(".lock")


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


@pytest.fixture
def output_file(tmp_path):
    return tmp_path / "predictions.jsonl"


def test_add_and_override(output_file):
    add_prediction_to_jsonl(str(output_file), "t1", "", override_if_exists=False)
    add_prediction_to_jsonl(str(output_file), "t1", "answer", override_if_exists=True)
    add_prediction_to_jsonl(str(output_file), "t2", "", override_if_exists=False)
    assert _read(output_file) == [{"id": "t1", "answer": "answer"}, {"id": "t2", "answer": ""}]
    assert not _lock_path(output_file).exists()


def test_duplicate_entry_releases_lock(output_file):
    add_prediction_to_jsonl(str(output_file), "t1", "", override_if_exists=False)
    with pytest.raises(ValueError, match="already exists"):
        add_prediction_to_jsonl(str(output_file), "t1", "", override_if_exists=False)
    assert not _lock_path(output_file).exists()

    start = time.time()
    add_prediction_to_jsonl(str(output_file), "t2", "x", override_if_exists=False)
    assert time.time() - start < 1
    assert [e["id"] for e in _read(output_file)] == ["t1", "t2"]


def test_corrupt_file_releases_lock_and_is_left_untouched(output_file):
    output_file.write_text('{"id": "t1", "answer": ""}\nnot json\n')
    with pytest.raises(ValueError, match="line 2"):
        add_prediction_to_jsonl(str(output_file), "t2", "", override_if_exists=False)
    assert not _lock_path(output_file).exists()
    assert output_file.read_text() == '{"id": "t1", "answer": ""}\nnot json\n'


def test_entry_without_id_does_not_crash(output_file):
    output_file.write_text('{"answer": "orphan"}\n')
    add_prediction_to_jsonl(str(output_file), "t1", "x", override_if_exists=False)
    assert _read(output_file) == [{"answer": "orphan"}, {"id": "t1", "answer": "x"}]
    assert not _lock_path(output_file).exists()


def test_lock_from_dead_process_is_reclaimed(output_file):
    lock = _lock_path(output_file)
    lock.write_text(
        json.dumps({"pid": _dead_pid(), "host": socket.gethostname(), "created": time.time()})
    )
    start = time.time()
    add_prediction_to_jsonl(str(output_file), "t1", "x", override_if_exists=False)
    assert time.time() - start < 1
    assert _read(output_file) == [{"id": "t1", "answer": "x"}]
    assert not lock.exists()


def test_old_legacy_lock_is_reclaimed(output_file):
    lock = _lock_path(output_file)
    lock.write_text("lock")
    old = time.time() - utils.LOCK_STALE_AFTER - 5
    os.utime(lock, (old, old))
    add_prediction_to_jsonl(str(output_file), "t1", "x", override_if_exists=False)
    assert _read(output_file) == [{"id": "t1", "answer": "x"}]
    assert not lock.exists()


def test_live_lock_is_respected(output_file, monkeypatch):
    monkeypatch.setattr(utils, "LOCK_MAX_WAIT", 0.5)
    lock = _lock_path(output_file)
    content = json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created": 0})
    lock.write_text(content)
    with pytest.raises(RuntimeError, match="could not be acquired"):
        add_prediction_to_jsonl(str(output_file), "t1", "x", override_if_exists=False)
    assert lock.read_text() == content
    assert not output_file.exists()


def test_release_does_not_remove_foreign_lock(output_file):
    lock = _lock_path(output_file)
    token = utils._acquire_lock(lock)
    lock.write_text("someone else")
    utils._release_lock(lock, token)
    assert lock.read_text() == "someone else"


def test_process_killed_while_holding_lock(output_file):
    add_prediction_to_jsonl(str(output_file), "t1", "first", override_if_exists=False)
    script = textwrap.dedent(
        f"""
        import os
        from browsergym.assistantbench import utils

        def crash(*args, **kwargs):
            os._exit(1)

        utils.os.replace = crash
        utils.add_prediction_to_jsonl({str(output_file)!r}, "t2", "lost", override_if_exists=False)
        """
    )
    result = subprocess.run([sys.executable, "-c", script], env=os.environ.copy())
    assert result.returncode == 1
    assert _lock_path(output_file).exists()
    assert _read(output_file) == [{"id": "t1", "answer": "first"}]

    start = time.time()
    add_prediction_to_jsonl(str(output_file), "t3", "x", override_if_exists=False)
    assert time.time() - start < 1
    assert _read(output_file) == [{"id": "t1", "answer": "first"}, {"id": "t3", "answer": "x"}]
    assert not _lock_path(output_file).exists()


def _write_one(args):
    file_path, task_id = args
    add_prediction_to_jsonl(file_path, task_id, task_id, override_if_exists=False)


def test_concurrent_writers(output_file):
    task_ids = [f"t{i}" for i in range(40)]
    with ProcessPoolExecutor(
        max_workers=8, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        list(pool.map(_write_one, [(str(output_file), t) for t in task_ids]))
    assert sorted(e["id"] for e in _read(output_file)) == sorted(task_ids)
    assert not _lock_path(output_file).exists()
