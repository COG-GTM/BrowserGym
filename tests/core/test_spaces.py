import gymnasium as gym
import numpy as np
import pytest

from browsergym.core.env import BrowserEnv
from browsergym.core.spaces import AnyBox, AnyDict, Anything, Float, Integer, Unicode
from browsergym.core.task import OpenEndedTask


def screenshot_space():
    # mirrors the "screenshot" entry of BrowserEnv.observation_space
    return AnyBox(low=0, high=255, shape=(-1, -1, 3), dtype=np.uint8)


@pytest.mark.parametrize("height,width", [(1, 1), (720, 1280), (1080, 1920), (600, 800)])
def test_anybox_accepts_uint8_screenshots_of_any_viewport(height, width):
    space = screenshot_space()
    assert space.contains(np.zeros((height, width, 3), dtype=np.uint8))
    assert space.contains(np.full((height, width, 3), 255, dtype=np.uint8))


@pytest.mark.parametrize(
    "x",
    [
        np.zeros((10, 10, 4), dtype=np.uint8),  # RGBA, wrong channel count
        np.zeros((10, 10, 1), dtype=np.uint8),
        np.zeros((10, 10), dtype=np.uint8),  # wrong rank
        np.zeros((1, 10, 10, 3), dtype=np.uint8),
        np.zeros((10, 10, 3), dtype=np.float64),  # float screenshots are not castable to uint8
        np.zeros((10, 10, 3), dtype=np.float32),
        np.zeros((10, 10, 3), dtype=np.int64),
        np.zeros((10, 10, 3), dtype=np.uint16),
    ],
    ids=["rgba", "single-channel", "rank-2", "rank-4", "float64", "float32", "int64", "uint16"],
)
def test_anybox_rejects_malformed_arrays(x):
    assert not screenshot_space().contains(x)


def test_anybox_checks_bounds():
    space = AnyBox(low=10, high=20, shape=(-1, 3), dtype=np.uint8)
    assert space.contains(np.full((2, 3), 10, dtype=np.uint8))
    assert space.contains(np.full((2, 3), 20, dtype=np.uint8))
    assert not space.contains(np.full((2, 3), 9, dtype=np.uint8))
    assert not space.contains(np.full((2, 3), 21, dtype=np.uint8))


def test_anybox_fixed_dims_must_match():
    space = AnyBox(low=0, high=255, shape=(-1, 4, 3), dtype=np.uint8)
    assert space.contains(np.zeros((7, 4, 3), dtype=np.uint8))
    assert not space.contains(np.zeros((7, 5, 3), dtype=np.uint8))


def test_anybox_converts_non_array_input():
    space = screenshot_space()
    assert space.contains([[[0, 128, 255]]])
    assert space.contains([[[0, 0, 0], [1, 1, 1]], [[2, 2, 2], [3, 3, 3]]])
    assert not space.contains([[0, 128, 255]])  # wrong rank after conversion


@pytest.mark.parametrize(
    "x",
    ["abc", None, {"a": 1}, [[[0, 0]], [[0, 0, 0]]], [[[300, 0, 0]]], [[[-1, 0, 0]]]],
    ids=["str", "none", "dict", "ragged", "above-high", "below-low"],
)
def test_anybox_rejects_unconvertible_or_out_of_range_input(x):
    assert not screenshot_space().contains(x)


def test_anybox_eq_and_repr():
    space = screenshot_space()
    assert space == screenshot_space()
    assert space != AnyBox(low=0, high=255, shape=(-1, -1, 4), dtype=np.uint8)
    assert space != AnyBox(low=0, high=254, shape=(-1, -1, 3), dtype=np.uint8)
    assert space != AnyBox(low=0, high=255, shape=(-1, -1, 3), dtype=np.uint16)
    assert space != Unicode()
    assert repr(space) == ("AnyBox(low=0, high=255, shape=(-1, -1, 3), dtype=dtype('uint8'))")


def test_anybox_eq_with_array_bounds():
    low, high = np.zeros(3), np.array([1.0, 2.0, 3.0])
    space = AnyBox(low=low, high=high, shape=(-1, 3), dtype=np.float64)
    assert space == AnyBox(low=low.copy(), high=high.copy(), shape=(-1, 3), dtype=np.float64)
    assert space != AnyBox(low=low, high=high + 1, shape=(-1, 3), dtype=np.float64)
    assert space.contains(np.array([[0.5, 1.5, 2.5]]))
    assert not space.contains(np.array([[0.5, 2.5, 2.5]]))
    # malformed input must be rejected, not raise a broadcasting error against the bounds
    assert not space.contains([[0, 0], [0, 0]])
    assert not space.contains(np.zeros((2, 2)))
    assert not space.contains([0.5, 1.5, 2.5])


def test_unicode():
    space = Unicode()
    for x in ["", "abc", "héllo 你好", np.str_("abc")]:
        assert space.contains(x)
    for x in [None, 1, 1.0, b"abc", ["abc"]]:
        assert not space.contains(x)
    assert space == Unicode()
    assert space != Float()
    assert repr(space) == "Unicode()"


def test_float():
    space = Float()
    for x in [0.0, -1.5, float("inf"), np.float64(1.0)]:
        assert space.contains(x)
    # strict isinstance(x, float): ints and non-float64 numpy scalars are rejected
    for x in [1, True, np.float32(1.0), "1.0", None]:
        assert not space.contains(x)
    assert space == Float()
    assert space != Integer()
    assert repr(space) == "Float()"


def test_integer():
    space = Integer()
    # strict isinstance(x, int): bool is a subclass of int and is accepted
    for x in [0, -3, 2**70, True]:
        assert space.contains(x)
    for x in [1.0, np.int64(1), "1", None]:
        assert not space.contains(x)
    assert space == Integer()
    assert space != Float()
    assert repr(space) == "Integer()"


def test_anydict():
    space = AnyDict()
    for x in [{}, {"a": 1}, {"nested": {"b": [1, 2]}}]:
        assert space.contains(x)
    for x in [None, [], [("a", 1)], "{}"]:
        assert not space.contains(x)
    assert space == AnyDict()
    assert space != Anything()
    assert repr(space) == "AnyDict()"


def test_anything():
    space = Anything()
    for x in [None, 0, "abc", {}, [], object(), np.zeros(3)]:
        assert space.contains(x)
    assert space == Anything()
    assert space != AnyDict()
    assert repr(space) == "Anything()"


def make_env(**kwargs):
    return BrowserEnv(
        task_entrypoint=OpenEndedTask, task_kwargs={"start_url": "about:blank"}, **kwargs
    )


def test_browser_env_declares_expected_custom_spaces():
    env = make_env()
    obs_space = env.observation_space
    assert isinstance(obs_space, gym.spaces.Dict)
    assert obs_space["screenshot"] == screenshot_space()
    for key in ["goal", "url", "focused_element_bid", "last_action", "last_action_error"]:
        assert obs_space[key] == Unicode(), key
    for key in ["dom_object", "axtree_object", "extra_element_properties"]:
        assert obs_space[key] == AnyDict(), key
    assert obs_space["goal_object"].feature_space == AnyDict()
    assert obs_space["open_pages_urls"].feature_space == Unicode()
    assert obs_space["open_pages_titles"].feature_space == Unicode()
    message_space = obs_space["chat_messages"].feature_space
    assert message_space["role"] == Unicode()
    assert message_space["message"] == Unicode()
    assert message_space["timestamp"] == Float()
    assert env.action_space == Unicode()

    assert obs_space["screenshot"].contains(np.zeros((720, 1280, 3), dtype=np.uint8))
    assert message_space["timestamp"].contains(1.7e9)


def test_browser_env_raw_page_output_declares_anything_page():
    env = make_env(use_raw_page_output=True)
    obs_space = env.observation_space
    assert obs_space["page"] == Anything()
    assert "screenshot" not in obs_space.spaces
    assert env.action_space == Unicode()
