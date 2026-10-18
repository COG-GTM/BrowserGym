"""
Offline unit tests for GenericVisualWebArenaTask.validate() and setup().

No VisualWebArena server, browser or captioning model is needed: the task is built with
object.__new__ and wired with a stub instance, a stub evaluator and a fake page.
"""

import enum
import sys
import types

import numpy as np
import pytest

from browsergym.visualwebarena.task import GenericVisualWebArenaTask

AUTHORIZED_URLS = {
    "reddit": "http://vwa.example:9999",
    "shopping": "http://vwa.example:7770",
    "wikipedia": "http://vwa.example:8888",
    "classifieds": "http://vwa.example:9980",
}
HOME_URL = "http://vwa.example:4399"
UNAUTHORIZED_ERROR = {"error": "Unauthorized url, terminating task"}


class StubInstance:
    def __init__(self):
        self.urls = dict(AUTHORIZED_URLS)
        self.home_url = HOME_URL
        self.classifieds_reset_token = "reset-token"
        self.logins = []

    def ui_login(self, site, page):
        self.logins.append(site)


class StubEvaluator:
    def __init__(self, score=0.0, exc=None):
        self.score = score
        self.exc = exc
        self.calls = []

    def __call__(self, trajectory, config_file, page):
        self.calls.append({"trajectory": trajectory, "config_file": config_file, "page": page})
        if self.exc is not None:
            raise self.exc
        return self.score


class FakePage:
    def __init__(self, url="", context=None):
        self.url = url
        self.context = context
        self.visited = []

    def goto(self, url):
        self.visited.append(url)
        self.url = url


class FakeContext:
    def __init__(self, urls=()):
        self.pages = [FakePage(url, self) for url in urls]
        self.geolocation = None

    def new_page(self):
        page = FakePage("about:blank", self)
        self.pages.append(page)
        return page

    def set_geolocation(self, geolocation):
        self.geolocation = geolocation


def make_page(*urls):
    return FakeContext(urls or ("",)).pages[0]


class StubActionTypes(enum.IntEnum):
    NONE = 0
    STOP = 17


@pytest.fixture
def action_types(monkeypatch):
    try:
        from visualwebarena.browser_env.actions import ActionTypes
    except Exception:
        ActionTypes = StubActionTypes
        module = types.ModuleType("visualwebarena.browser_env.actions")
        module.ActionTypes = ActionTypes
        monkeypatch.setitem(sys.modules, "visualwebarena.browser_env.actions", module)
    return ActionTypes


def make_task(evaluator=None):
    task = object.__new__(GenericVisualWebArenaTask)
    task.webarena_instance = StubInstance()
    task.evaluator = evaluator if evaluator is not None else StubEvaluator()
    task.config_file = "/tmp/vwa-config.json"
    return task


@pytest.mark.parametrize(
    "urls",
    [
        ("https://www.google.com/",),
        (AUTHORIZED_URLS["shopping"], "http://evil.example/"),
        ("http://vwa.example:1234/",),
    ],
)
def test_unauthorized_tab_terminates_without_calling_evaluator(action_types, urls):
    evaluator = StubEvaluator(score=1.0)
    task = make_task(evaluator)

    result = task.validate(make_page(*urls), [{"role": "assistant", "message": "42"}])

    assert result == (0, True, "", UNAUTHORIZED_ERROR)
    assert evaluator.calls == []


def test_authorized_and_blank_tabs_reach_evaluator(action_types):
    evaluator = StubEvaluator(score=0.0)
    task = make_task(evaluator)
    page = make_page(
        "",
        "about:blank",
        "chrome://newtab/",
        HOME_URL + "/",
        *(url + "/some/path?q=1" for url in AUTHORIZED_URLS.values()),
    )

    result = task.validate(page, [])

    assert result == (0.0, False, "", {})
    assert len(evaluator.calls) == 1


@pytest.mark.parametrize("score", [1.0, 0.0])
def test_assistant_message_is_stop_answer_and_done(action_types, score):
    evaluator = StubEvaluator(score=score)
    task = make_task(evaluator)
    page = make_page(AUTHORIZED_URLS["classifieds"])
    chat_messages = [
        {"role": "user", "message": "goal"},
        {"role": "assistant", "message": "first answer"},
        {"role": "assistant", "message": "final answer"},
    ]

    result = task.validate(page, chat_messages)

    assert result == (score, True, "", {})
    (call,) = evaluator.calls
    assert call["trajectory"] == [
        {},
        {"action_type": action_types.STOP, "answer": "final answer"},
    ]
    assert call["config_file"] == "/tmp/vwa-config.json"
    assert call["page"] is page


def test_infeasible_message_is_stop_with_na_answer(action_types):
    evaluator = StubEvaluator(score=0.0)
    task = make_task(evaluator)

    result = task.validate(make_page(), [{"role": "infeasible", "message": "impossible"}])

    assert result == (0.0, True, "", {})
    assert evaluator.calls[0]["trajectory"][1] == {
        "action_type": action_types.STOP,
        "answer": "N/A",
    }


@pytest.mark.parametrize(
    "chat_messages",
    [
        [],
        [{"role": "user", "message": "goal"}],
        [{"role": "assistant", "message": "hi"}, {"role": "user", "message": "go on"}],
    ],
)
def test_no_final_answer_is_not_done(action_types, chat_messages):
    evaluator = StubEvaluator(score=0.0)
    task = make_task(evaluator)

    result = task.validate(make_page(), chat_messages)

    assert result == (0.0, False, "", {})
    assert evaluator.calls[0]["trajectory"][1] == {
        "action_type": action_types.NONE,
        "answer": "whatever",
    }


def test_positive_score_without_answer_is_done(action_types):
    task = make_task(StubEvaluator(score=1.0))

    assert task.validate(make_page(), []) == (1.0, True, "", {})


@pytest.mark.parametrize(
    "chat_messages, done",
    [
        ([{"role": "assistant", "message": "answer"}], True),
        ([{"role": "infeasible", "message": ""}], True),
        ([], False),
    ],
)
def test_evaluator_assertion_error_scores_zero(action_types, chat_messages, done):
    evaluator = StubEvaluator(exc=AssertionError("'correct' not in response"))
    task = make_task(evaluator)

    result = task.validate(make_page(), chat_messages)

    assert result == (0.0, done, "", {})
    assert len(evaluator.calls) == 1


def test_evaluator_other_errors_propagate(action_types):
    task = make_task(StubEvaluator(exc=RuntimeError("evaluator bug")))

    with pytest.raises(RuntimeError, match="evaluator bug"):
        task.validate(make_page(), [{"role": "assistant", "message": "answer"}])


class StubResponse:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture
def setup_stubs(monkeypatch):
    """Stub the evaluator router, captioning model and transformers logging used by setup()."""
    built = {}

    def evaluator_router(config_file, captioning_fn):
        built["config_file"] = config_file
        built["captioning_fn"] = captioning_fn
        return StubEvaluator()

    def get_captioning_fn(device, dtype, model_name):
        built["captioning_args"] = (device, dtype, model_name)
        return "captioning_fn"

    evaluators = types.ModuleType("visualwebarena.evaluation_harness.evaluators")
    evaluators.evaluator_router = evaluator_router
    image_utils = types.ModuleType("visualwebarena.evaluation_harness.image_utils")
    image_utils.get_captioning_fn = get_captioning_fn
    hf_logging = types.ModuleType("transformers.utils.logging")
    hf_logging.disable_progress_bar = lambda: None
    hf_logging.enable_progress_bar = lambda: None
    hf_logging.is_progress_bar_enabled = lambda: False

    monkeypatch.setitem(sys.modules, "visualwebarena.evaluation_harness.evaluators", evaluators)
    monkeypatch.setitem(sys.modules, "visualwebarena.evaluation_harness.image_utils", image_utils)
    monkeypatch.setitem(sys.modules, "transformers.utils.logging", hf_logging)
    return built


def make_setup_task(config):
    task = make_task()
    task.random = np.random.RandomState(0)
    task.task_configs = [config]
    task.with_na_hint = False
    task.eval_captioning_model_device = "cpu"
    return task


def classifieds_config(require_reset=True, start_url=None):
    return {
        "task_id": 0,
        "intent": "Find the cheapest bike.",
        "image": None,
        "sites": ["classifieds"],
        "require_reset": require_reset,
        "geolocation": None,
        "start_url": start_url or AUTHORIZED_URLS["classifieds"],
    }


def record_posts(monkeypatch, status_code):
    import browsergym.visualwebarena.task as task_module

    posts = []

    def fake_post(url, data):
        posts.append((url, data))
        return StubResponse(status_code)

    monkeypatch.setattr(task_module.requests, "post", fake_post)
    return posts


@pytest.mark.parametrize("status_code", [500, 403])
def test_setup_classifieds_reset_failure_raises(monkeypatch, setup_stubs, status_code):
    posts = record_posts(monkeypatch, status_code)
    task = make_setup_task(classifieds_config())
    page = make_page()

    with pytest.raises(Exception, match=f"Failed to reset Classifieds site: {status_code}"):
        task.setup(page)

    reset_url = AUTHORIZED_URLS["classifieds"] + "/index.php?page=reset"
    assert posts == [(reset_url, {"token": "reset-token"})]
    assert task.webarena_instance.logins == []
    assert page.visited == []


def test_setup_classifieds_reset_success_logs_in_and_navigates(monkeypatch, setup_stubs):
    posts = record_posts(monkeypatch, 200)
    start_urls = [AUTHORIZED_URLS["classifieds"] + "/a", AUTHORIZED_URLS["classifieds"] + "/b"]
    task = make_setup_task(classifieds_config(start_url=" |AND| ".join(start_urls)))
    page = make_page()

    goal, info = task.setup(page)

    assert len(posts) == 1
    assert task.webarena_instance.logins == ["classifieds"]
    assert page.visited == [start_urls[0]]
    assert page.context.pages[-1].visited == [start_urls[1]]
    assert task.config_file == setup_stubs["config_file"]
    assert setup_stubs["captioning_fn"] == "captioning_fn"
    assert goal == [{"type": "text", "text": "Find the cheapest bike."}]
    assert info == {}


def test_setup_without_reset_does_not_post(monkeypatch, setup_stubs):
    posts = record_posts(monkeypatch, 500)
    task = make_setup_task(classifieds_config(require_reset=False))

    task.setup(make_page())

    assert posts == []
    assert task.webarena_instance.logins == ["classifieds"]
