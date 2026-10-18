import gzip
import pickle
import tempfile
from pathlib import Path

from browsergym.experiments.loop import STEP_INFO_COMPRESSLEVEL, ExpResult, StepInfo
from browsergym.experiments.utils import count_tokens, count_tokens_batch


def _make_step_info():
    step_info = StepInfo(step=0)
    step_info.obs = {
        "axtree_txt": "[12] button 'Submit'\n" * 50,
        "pruned_html": "<div bid='12'><button>Submit</button></div>\n" * 50,
        "dom_txt": "special token text <|endoftext|> must not raise",
        "goal_object": [{"type": "text", "text": "click submit"}],
        "last_action_error": "",
        "open_pages_urls": ["http://example.com"],
    }
    step_info.agent_info = {"think": "clicking", "stats": {"custom": 1}}
    step_info.profiling.agent_start, step_info.profiling.agent_stop = 1.0, 2.0
    step_info.profiling.env_start, step_info.profiling.env_stop = 0.0, 0.5
    return step_info


def test_count_tokens_batch_matches_count_tokens():
    texts = ["hello world", "", "<|endoftext|> is plain text here", "a" * 1000]
    assert count_tokens_batch(texts) == [count_tokens(t) for t in texts]
    assert count_tokens_batch([]) == []


def test_make_stats_counts_only_string_obs():
    step_info = _make_step_info()
    step_info.make_stats()

    for key in ("axtree_txt", "pruned_html", "dom_txt", "last_action_error"):
        assert step_info.stats[f"n_token_{key}"] == count_tokens(step_info.obs[key])
    assert "n_token_goal_object" not in step_info.stats
    assert "n_token_open_pages_urls" not in step_info.stats
    assert step_info.stats["custom"] == 1
    assert step_info.stats["agent_elapsed"] == 1.0
    assert step_info.stats["step_elapsed"] == 0.5


def test_save_step_info_round_trip():
    assert 1 <= STEP_INFO_COMPRESSLEVEL < 9

    step_info = _make_step_info()
    step_info.make_stats()
    expected_obs = dict(step_info.obs)

    with tempfile.TemporaryDirectory() as tmp_dir:
        exp_dir = Path(tmp_dir)
        step_info.save_step_info(exp_dir, save_screenshot=False)

        with gzip.open(exp_dir / "step_0.pkl.gz", "rb") as f:
            raw = pickle.load(f)
        assert raw.obs["goal_object"] is None

        loaded = ExpResult(exp_dir).get_step_info(0)
        assert loaded.obs == expected_obs
        assert loaded.stats == step_info.stats
        assert loaded.action == step_info.action
