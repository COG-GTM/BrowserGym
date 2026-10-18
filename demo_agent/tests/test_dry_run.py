import gzip
import pickle

import pytest
import run_demo


@pytest.mark.slow
def test_dry_run_end_to_end(tmp_path, capsys):
    assert run_demo.main(["--dry-run", "--results-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "err_msg: None" in out
    assert "n_steps: 3" in out

    (exp_dir,) = list(tmp_path.iterdir())
    assert (exp_dir / "screenshot_step_3.png").exists()
    with gzip.open(exp_dir / "step_2.pkl.gz") as f:
        step = pickle.load(f)
    assert step.action.startswith("send_msg_to_user(")
    assert "Dry run complete" in step.action
    assert step.stats["input_tokens"] > 0


@pytest.mark.slow
def test_dry_run_html_only_debug_logging(tmp_path, capsys):
    argv = ["--dry-run", "--no-use-axtree", "--use-html", "--log-level", "DEBUG"]
    assert run_demo.main(argv + ["--results-dir", str(tmp_path)]) == 0
    (exp_dir,) = list(tmp_path.iterdir())
    log = (exp_dir / "experiment.log").read_text()
    assert "# Current page DOM" in log  # full prompt is logged at DEBUG
    with gzip.open(exp_dir / "step_2.pkl.gz") as f:
        step = pickle.load(f)
    assert "Dry run complete" in step.action
    assert " 0 elements" not in step.action
