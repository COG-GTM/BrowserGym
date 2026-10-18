from types import SimpleNamespace

import playwright.sync_api
import pytest

from browsergym.core.action import functions
from browsergym.core.action.utils import call_fun, get_elem_by_bid, map_coordinates


@pytest.mark.parametrize(
    "page, x, y, expected",
    [
        (SimpleNamespace(_bgym_scale_factor=1.5), 300, 450, (200.0, 300.0)),
        (SimpleNamespace(_bgym_scale_factor=1.5), -150, 75, (-100.0, 50.0)),
        (SimpleNamespace(_bgym_scale_factor=2.0), 10.5, 0, (5.25, 0.0)),
        (SimpleNamespace(_bgym_scale_factor=1.0), 300, 450, (300, 450)),
        (object(), 300, 450, (300, 450)),
        (object(), 12.3, -4.5, (12.3, -4.5)),
    ],
)
def test_map_coordinates(page, x, y, expected):
    assert map_coordinates(page, x, y) == pytest.approx(expected)


class _Recorder:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls = []

    def __call__(self, force):
        self.calls.append(force)
        if self.exc is not None and not force:
            raise self.exc


def test_call_fun_success_is_not_retried():
    fun = _Recorder()
    call_fun(fun, retry_with_force=True)
    assert fun.calls == [False]


def test_call_fun_timeout_retries_with_force():
    fun = _Recorder(exc=playwright.sync_api.TimeoutError("timeout"))
    call_fun(fun, retry_with_force=True)
    assert fun.calls == [False, True]


def test_call_fun_timeout_reraised_without_retry():
    fun = _Recorder(exc=playwright.sync_api.TimeoutError("timeout"))
    with pytest.raises(playwright.sync_api.TimeoutError):
        call_fun(fun, retry_with_force=False)
    assert fun.calls == [False]


def test_call_fun_other_errors_are_not_retried():
    fun = _Recorder(exc=playwright.sync_api.Error("boom"))
    with pytest.raises(playwright.sync_api.Error):
        call_fun(fun, retry_with_force=True)
    assert fun.calls == [False]


class _FakeLocator:
    def __init__(self, frame, test_id):
        self.frame = frame
        self.test_id = test_id

    def count(self):
        return int(self.test_id in self.frame.bids)

    def scroll_into_view_if_needed(self, timeout):
        self.frame.log.append(("scroll", self.test_id, timeout))

    def frame_locator(self, selector):
        assert selector == ":scope"
        return self.frame.children[self.test_id]


class _FakeFrame:
    """Mimics the get_by_test_id / frame_locator API of a playwright page or frame."""

    def __init__(self, name, bids=(), children=None, log=None):
        self.name = name
        self.children = children or {}
        self.bids = set(bids) | set(self.children)
        self.log = log

    def get_by_test_id(self, test_id):
        self.log.append(("query", self.name, test_id))
        return _FakeLocator(self, test_id)


@pytest.fixture
def fake_page():
    # bids follow frame_mark_elements.js: frames get letter ids ("a", ..., "z", "aA", "aB", ...),
    # nested frame / element bids are prefixed with their parent frame bid.
    log = []
    abc = _FakeFrame("aBc", bids=["aBc7"], log=log)
    ab = _FakeFrame("aB", bids=["aB3"], children={"aBc": abc}, log=log)
    a = _FakeFrame("a", bids=["a5"], log=log)
    page = _FakeFrame("page", bids=["12"], children={"a": a, "aB": ab}, log=log)
    return page


@pytest.mark.parametrize(
    "bid, expected_queries",
    [
        ("12", [("page", "12")]),
        ("a5", [("page", "a"), ("a", "a5")]),
        ("aB3", [("page", "aB"), ("aB", "aB3")]),
        ("aBc7", [("page", "aB"), ("aB", "aBc"), ("aBc", "aBc7")]),
    ],
)
def test_get_elem_by_bid_walks_frames(fake_page, bid, expected_queries):
    elem = get_elem_by_bid(fake_page, bid)
    assert elem.test_id == bid
    assert [entry[1:] for entry in fake_page.log if entry[0] == "query"] == expected_queries
    assert not [entry for entry in fake_page.log if entry[0] == "scroll"]


def test_get_elem_by_bid_scroll_into_view(fake_page):
    get_elem_by_bid(fake_page, "aBc7", scroll_into_view=True)
    scrolls = [entry[1:] for entry in fake_page.log if entry[0] == "scroll"]
    assert scrolls == [("aB", 500), ("aBc", 500), ("aBc7", 500)]


@pytest.mark.parametrize(
    "bid",
    [
        "999",  # missing element in the main frame
        "zz999",  # missing frame "z"
        "a999",  # existing frame "a", missing element
        "aBd7",  # existing frame "aB", missing nested frame "aBd"
        "aC1",  # missing multi-letter frame "aC"
    ],
)
def test_get_elem_by_bid_missing(fake_page, bid):
    with pytest.raises(ValueError, match=f'Could not find element with bid "{bid}"'):
        get_elem_by_bid(fake_page, bid)


@pytest.mark.parametrize("bid", [None, 42, 42.7, ["a5"]])
def test_get_elem_by_bid_rejects_non_string(fake_page, bid):
    with pytest.raises(ValueError, match="expected a string"):
        get_elem_by_bid(fake_page, bid)


class _FakeMouse:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


@pytest.fixture
def scaled_page(monkeypatch):
    page = SimpleNamespace(_bgym_scale_factor=1.5, mouse=_FakeMouse())
    monkeypatch.setattr(functions, "page", page)
    monkeypatch.setattr(functions, "demo_mode", "off")
    return page


@pytest.mark.parametrize(
    "action, args, expected_calls",
    [
        ("mouse_click", (300, 450), [("click", (200.0, 300.0), {"button": "left"})]),
        (
            "mouse_dblclick",
            (300, 450, "right"),
            [("dblclick", (200.0, 300.0), {"button": "right"})],
        ),
        ("mouse_move", (300, 450), [("move", (200.0, 300.0), {})]),
        (
            "mouse_down",
            (300, 450),
            [("move", (200.0, 300.0), {}), ("down", (), {"button": "left"})],
        ),
        (
            "mouse_up",
            (300, 450),
            [("move", (200.0, 300.0), {}), ("up", (), {"button": "left"})],
        ),
        ("scroll", (0, -150), [("wheel", (0.0, -100.0), {})]),
        (
            "scroll_at",
            (300, 450, 0, 150),
            [("move", (200.0, 300.0), {}), ("wheel", (0.0, 100.0), {})],
        ),
        (
            "mouse_drag_and_drop",
            (30, 45, 300, 450),
            [
                ("move", (20.0, 30.0), {}),
                ("down", (), {}),
                ("move", (200.0, 300.0), {}),
                ("up", (), {}),
            ],
        ),
    ],
)
def test_coordinate_actions_apply_scale_factor(scaled_page, action, args, expected_calls):
    getattr(functions, action)(*args)
    assert scaled_page.mouse.calls == [
        (name, pytest.approx(call_args), kwargs) for name, call_args, kwargs in expected_calls
    ]
