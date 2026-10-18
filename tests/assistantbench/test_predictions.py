import json
import sys
from unittest import mock

import pytest


def _import_assistantbench_modules():
    """
    Import the AssistantBench task/utils modules without network access.

    `browsergym.assistantbench.task` loads the AssistantBench HF dataset at import time.
    If the package has not been imported yet, import it with a stubbed (empty) dataset
    and drop it from `sys.modules` afterwards, so that other tests importing it later
    still get the real dataset. The "imp.0" task used here does not depend on the dataset.
    """
    package_modules = [
        "browsergym.assistantbench",
        "browsergym.assistantbench.task",
        "browsergym.assistantbench.utils",
    ]
    if "browsergym.assistantbench.task" in sys.modules:
        return (
            sys.modules["browsergym.assistantbench.task"],
            sys.modules["browsergym.assistantbench.utils"],
        )

    with mock.patch("datasets.load_dataset", return_value={"validation": [], "test": []}):
        import browsergym.assistantbench.task as task_module
        import browsergym.assistantbench.utils as utils_module

    for name in package_modules:
        sys.modules.pop(name, None)

    return task_module, utils_module


task_module, utils_module = _import_assistantbench_modules()
AssistantBenchTask = task_module.AssistantBenchTask
add_prediction_to_jsonl = utils_module.add_prediction_to_jsonl

IMP_TASK_ID = "imp.0"
IMP_AB_TASK_ID = "test_imp_id_0"
IMP_GOLD_ANSWER = "20"


def read_jsonl(path):
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture(autouse=True)
def reset_output_file_defaults(monkeypatch):
    monkeypatch.delenv("ASSISTANTBENCH_OUTPUT_FILE", raising=False)
    task_module.set_default_output_file(None)
    yield
    task_module.set_default_output_file(None)


@pytest.fixture
def output_file(tmp_path):
    return tmp_path / "predictions.jsonl"


@pytest.fixture
def lock_file(output_file):
    return output_file.with_suffix(".lock")


# add_prediction_to_jsonl


def test_add_prediction_creates_file(output_file, lock_file):
    assert not output_file.exists()

    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    assert read_jsonl(output_file) == [{"id": "task_a", "answer": "answer_a"}]
    assert not lock_file.exists()


def test_add_prediction_appends_new_ids_in_order(output_file, lock_file):
    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)
    add_prediction_to_jsonl(str(output_file), "task_b", "answer_b", override_if_exists=False)
    add_prediction_to_jsonl(str(output_file), "task_c", "", override_if_exists=True)

    assert read_jsonl(output_file) == [
        {"id": "task_a", "answer": "answer_a"},
        {"id": "task_b", "answer": "answer_b"},
        {"id": "task_c", "answer": ""},
    ]
    assert not lock_file.exists()


def test_add_prediction_override_updates_existing_entry(output_file, lock_file):
    add_prediction_to_jsonl(str(output_file), "task_a", "", override_if_exists=False)
    add_prediction_to_jsonl(str(output_file), "task_b", "answer_b", override_if_exists=False)

    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=True)

    assert read_jsonl(output_file) == [
        {"id": "task_a", "answer": "answer_a"},
        {"id": "task_b", "answer": "answer_b"},
    ]
    assert not lock_file.exists()


def test_add_prediction_no_override_raises_and_releases_lock(output_file, lock_file):
    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    with pytest.raises(ValueError, match="task_a"):
        add_prediction_to_jsonl(str(output_file), "task_a", "other", override_if_exists=False)

    # file is untouched, and the lock does not block subsequent writes
    assert read_jsonl(output_file) == [{"id": "task_a", "answer": "answer_a"}]
    assert not lock_file.exists()
    add_prediction_to_jsonl(str(output_file), "task_b", "answer_b", override_if_exists=False)
    assert [entry["id"] for entry in read_jsonl(output_file)] == ["task_a", "task_b"]


def test_add_prediction_serializes_non_string_predictions(output_file):
    prediction = {"city": "Paris", "temperature": 20, "values": [1.5, None]}

    add_prediction_to_jsonl(str(output_file), "task_a", prediction, override_if_exists=False)

    assert read_jsonl(output_file) == [{"id": "task_a", "answer": prediction}]


def test_add_prediction_skips_blank_lines(output_file):
    output_file.write_text(
        '{"id": "task_a", "answer": "a"}\n\n   \n{"id": "task_b", "answer": "b"}\n'
    )

    add_prediction_to_jsonl(str(output_file), "task_b", "b2", override_if_exists=True)

    assert output_file.read_text() == (
        '{"id": "task_a", "answer": "a"}\n' '{"id": "task_b", "answer": "b2"}\n'
    )


def test_add_prediction_releases_lock_on_corrupted_file(output_file, lock_file):
    output_file.write_text("not json\n")

    with pytest.raises(json.JSONDecodeError):
        add_prediction_to_jsonl(str(output_file), "task_a", "a", override_if_exists=False)

    assert output_file.read_text() == "not json\n"
    assert not lock_file.exists()


def test_add_prediction_keeps_file_intact_if_write_fails(output_file, lock_file, monkeypatch):
    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    def failing_dumps(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(utils_module.json, "dumps", failing_dumps)
    with pytest.raises(OSError, match="disk full"):
        add_prediction_to_jsonl(str(output_file), "task_b", "answer_b", override_if_exists=False)
    monkeypatch.undo()

    assert read_jsonl(output_file) == [{"id": "task_a", "answer": "answer_a"}]
    assert not lock_file.exists()
    assert sorted(p.name for p in output_file.parent.iterdir()) == [output_file.name]


def test_add_prediction_tmp_suffixed_output_kept_intact_if_write_fails(tmp_path, monkeypatch):
    output_file = tmp_path / "predictions.tmp"
    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    def failing_dumps(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(utils_module.json, "dumps", failing_dumps)
    with pytest.raises(OSError, match="disk full"):
        add_prediction_to_jsonl(str(output_file), "task_b", "answer_b", override_if_exists=False)
    monkeypatch.undo()

    assert read_jsonl(output_file) == [{"id": "task_a", "answer": "answer_a"}]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["predictions.tmp"]


def test_add_prediction_leaves_no_temporary_files(output_file, tmp_path):
    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)
    add_prediction_to_jsonl(str(output_file), "task_a", "answer_b", override_if_exists=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == [output_file.name]


def test_add_prediction_preserves_file_mode(output_file):
    output_file.write_text("")
    output_file.chmod(0o640)

    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    assert output_file.stat().st_mode & 0o777 == 0o640


def test_add_prediction_through_symlink_updates_target(tmp_path):
    target = tmp_path / "runs" / "october.jsonl"
    target.parent.mkdir()
    target.write_text('{"id": "task_a", "answer": ""}\n')
    link = tmp_path / "current.jsonl"
    link.symlink_to(target)

    add_prediction_to_jsonl(str(link), "task_a", "answer_a", override_if_exists=True)

    assert link.is_symlink()
    assert read_jsonl(target) == [{"id": "task_a", "answer": "answer_a"}]
    assert read_jsonl(link) == [{"id": "task_a", "answer": "answer_a"}]
    assert not target.with_suffix(".lock").exists()
    assert not link.with_suffix(".lock").exists()


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_add_prediction_times_out_on_held_lock(output_file, lock_file, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(utils_module.time, "time", clock.time)
    monkeypatch.setattr(utils_module.time, "sleep", clock.sleep)
    lock_file.write_text("lock")

    with pytest.raises(RuntimeError, match="Lock file could not be acquired"):
        add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    assert sum(clock.sleeps) == 10
    # the lock held by someone else is left alone, and nothing was written
    assert lock_file.exists()
    assert not output_file.exists()


def test_add_prediction_waits_for_lock_release(output_file, lock_file, monkeypatch):
    clock = FakeClock()

    def sleep_then_release(seconds):
        clock.sleep(seconds)
        if len(clock.sleeps) == 3:
            lock_file.unlink()

    monkeypatch.setattr(utils_module.time, "time", clock.time)
    monkeypatch.setattr(utils_module.time, "sleep", sleep_then_release)
    lock_file.write_text("lock")

    add_prediction_to_jsonl(str(output_file), "task_a", "answer_a", override_if_exists=False)

    assert len(clock.sleeps) == 3
    assert read_jsonl(output_file) == [{"id": "task_a", "answer": "answer_a"}]
    assert not lock_file.exists()


# AssistantBenchTask output file resolution


def test_output_file_unset_by_default():
    task = AssistantBenchTask(seed=0, task_id=IMP_TASK_ID, save_predictions=True)

    assert task.output_file is None
    assert task.ab_task_id == IMP_AB_TASK_ID
    assert task.gold == IMP_GOLD_ANSWER


def test_output_file_from_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANTBENCH_OUTPUT_FILE", str(tmp_path / "env.jsonl"))

    task = AssistantBenchTask(seed=0, task_id=IMP_TASK_ID, save_predictions=True)

    assert task.output_file == str(tmp_path / "env.jsonl")


def test_output_file_global_default_takes_precedence_over_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANTBENCH_OUTPUT_FILE", str(tmp_path / "env.jsonl"))
    task_module.set_default_output_file(str(tmp_path / "default.jsonl"))

    task = AssistantBenchTask(seed=0, task_id=IMP_TASK_ID, save_predictions=True)

    assert task_module.get_default_output_file() == str(tmp_path / "default.jsonl")
    assert task.output_file == str(tmp_path / "default.jsonl")


def test_output_file_constructor_arg_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("ASSISTANTBENCH_OUTPUT_FILE", str(tmp_path / "env.jsonl"))
    task_module.set_default_output_file(str(tmp_path / "default.jsonl"))

    task = AssistantBenchTask(
        seed=0,
        task_id=IMP_TASK_ID,
        output_file=str(tmp_path / "arg.jsonl"),
        save_predictions=True,
    )

    assert task.output_file == str(tmp_path / "arg.jsonl")


# AssistantBenchTask setup / validate prediction writes


def make_task(output_file, save_predictions=True):
    return AssistantBenchTask(
        seed=0,
        task_id=IMP_TASK_ID,
        output_file=str(output_file) if output_file else None,
        save_predictions=save_predictions,
    )


def test_setup_writes_empty_entry(output_file, lock_file):
    task = make_task(output_file)
    page = mock.MagicMock()

    goal, info = task.setup(page)

    page.goto.assert_called_once_with(task.start_url, timeout=10000)
    assert goal == task.goal
    assert info == {}
    assert read_jsonl(output_file) == [{"id": IMP_AB_TASK_ID, "answer": ""}]
    assert not lock_file.exists()


def test_setup_twice_raises_without_corrupting_file(output_file, lock_file):
    make_task(output_file).setup(mock.MagicMock())

    with pytest.raises(ValueError, match=IMP_AB_TASK_ID):
        make_task(output_file).setup(mock.MagicMock())

    assert read_jsonl(output_file) == [{"id": IMP_AB_TASK_ID, "answer": ""}]
    assert not lock_file.exists()


def test_setup_then_validate_writes_prediction(output_file, lock_file):
    task = make_task(output_file)
    page = mock.MagicMock()
    task.setup(page)

    result = task.validate(
        page,
        chat_messages=[
            {"role": "user", "message": task.goal},
            {"role": "assistant", "message": IMP_GOLD_ANSWER},
        ],
    )

    assert result == (1.0, True, "", {})
    assert read_jsonl(output_file) == [{"id": IMP_AB_TASK_ID, "answer": IMP_GOLD_ANSWER}]
    assert not lock_file.exists()


def test_validate_overwrites_previous_prediction(output_file):
    task = make_task(output_file)
    page = mock.MagicMock()
    task.setup(page)

    accuracy, done, _, _ = task.validate(page, [{"role": "assistant", "message": "35"}])
    assert accuracy < 1.0
    assert done is True
    assert read_jsonl(output_file) == [{"id": IMP_AB_TASK_ID, "answer": "35"}]

    accuracy, done, _, _ = task.validate(page, [{"role": "assistant", "message": IMP_GOLD_ANSWER}])
    assert accuracy == 1.0
    assert done is True
    assert read_jsonl(output_file) == [{"id": IMP_AB_TASK_ID, "answer": IMP_GOLD_ANSWER}]


def test_setup_preserves_other_tasks_predictions(output_file):
    output_file.write_text('{"id": "other_task", "answer": "42"}\n')
    task = make_task(output_file)
    page = mock.MagicMock()

    task.setup(page)
    task.validate(page, [{"role": "assistant", "message": IMP_GOLD_ANSWER}])

    assert read_jsonl(output_file) == [
        {"id": "other_task", "answer": "42"},
        {"id": IMP_AB_TASK_ID, "answer": IMP_GOLD_ANSWER},
    ]


@pytest.mark.parametrize(
    "chat_messages",
    [
        [],
        [{"role": "user", "message": "What is the weather in Paris?"}],
        [
            {"role": "assistant", "message": IMP_GOLD_ANSWER},
            {"role": "user", "message": "Are you sure?"},
        ],
    ],
)
def test_validate_without_assistant_answer_is_not_done(output_file, chat_messages):
    task = make_task(output_file)
    page = mock.MagicMock()
    task.setup(page)

    result = task.validate(page, chat_messages)

    assert result == (0.0, False, "", {})
    assert read_jsonl(output_file) == [{"id": IMP_AB_TASK_ID, "answer": ""}]


def test_no_writes_when_save_predictions_disabled(output_file):
    task = make_task(output_file, save_predictions=False)
    page = mock.MagicMock()

    task.setup(page)
    result = task.validate(page, [{"role": "assistant", "message": IMP_GOLD_ANSWER}])

    assert result == (1.0, True, "", {})
    assert not output_file.exists()


def test_no_writes_when_output_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task = make_task(None, save_predictions=True)
    page = mock.MagicMock()

    task.setup(page)
    result = task.validate(page, [{"role": "assistant", "message": IMP_GOLD_ANSWER}])

    assert result == (1.0, True, "", {})
    assert list(tmp_path.iterdir()) == []
