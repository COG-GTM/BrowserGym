"""Offline unit tests for the WebArena-Lite reward logic (browsergym.webarenalite.evaluators)."""

import importlib.resources
import json
import os
import sys
import types
from typing import TypedDict

import pytest

_WEBARENA_SITE_VARS = (
    "SHOPPING",
    "SHOPPING_ADMIN",
    "REDDIT",
    "GITLAB",
    "WIKIPEDIA",
    "MAP",
    "HOMEPAGE",
)


def _install_webarena_stub():
    """Minimal stand-in for libwebarena, only used when it is not installed."""

    class Action(TypedDict, total=False):
        action_type: int
        answer: str

    class StateInfo(TypedDict, total=False):
        observation: dict
        info: dict

    def generate_from_openai_chat_completion(*args, **kwargs):
        raise RuntimeError("LLM calls are not available in offline tests")

    modules = {
        "webarena": {},
        "webarena.browser_env": {"Action": Action, "StateInfo": StateInfo},
        "webarena.browser_env.env_config": {
            "ACCOUNTS": {},
            **{name: os.environ[name] for name in _WEBARENA_SITE_VARS},
        },
        "webarena.llms": {},
        "webarena.llms.providers": {},
        "webarena.llms.providers.openai_utils": {
            "generate_from_openai_chat_completion": generate_from_openai_chat_completion
        },
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        module.__path__ = []
        module.__dict__.update(attrs)
        sys.modules[name] = module


def _import_evaluators():
    # libwebarena asserts at import time that every site URL is configured
    missing = [name for name in _WEBARENA_SITE_VARS if not os.environ.get(name)]
    for name in missing:
        os.environ[name] = f"http://{name.lower()}.invalid"
    try:
        try:
            import webarena.browser_env  # noqa: F401
        except ImportError:
            _install_webarena_stub()
        from browsergym.webarenalite import evaluators
    finally:
        for name in missing:
            del os.environ[name]
        if missing:
            # let later importers re-read the real site URLs
            sys.modules.pop("webarena.browser_env.env_config", None)
    return evaluators


evaluators = _import_evaluators()

from browsergym.webarenalite.helper_functions import PseudoPage  # noqa: E402

StringEvaluator = evaluators.StringEvaluator
URLEvaluator = evaluators.URLEvaluator
HTMLContentEvaluator = evaluators.HTMLContentEvaluator
EvaluatorComb = evaluators.EvaluatorComb
Evaluator = evaluators.Evaluator
evaluator_router = evaluators.evaluator_router


class FakePage(PseudoPage):
    """Page double: `evaluate` answers from a dict keyed by the exact JS expression."""

    def __init__(self, url="http://site.test/start", html="", js_results=None):
        super().__init__(original_page=None, url=url)
        self.html = html
        self.js_results = js_results or {}
        self.evaluated = []
        self.visited = []

    def goto(self, url):
        self.visited.append(url)
        self.url = url

    def content(self):
        return self.html

    def evaluate(self, expression):
        self.evaluated.append(expression)
        result = self.js_results[expression]
        if isinstance(result, Exception):
            raise result
        return result


def answer_trajectory(answer):
    return [{}, {"answer": answer}]


@pytest.fixture
def write_config(tmp_path):
    def _write(eval_config, intent="What is the answer?"):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"intent": intent, "eval": eval_config}))
        return path

    return _write


@pytest.fixture
def llm_calls(monkeypatch):
    """Replace the LLM judges with recorders returning configurable scores."""
    calls = {"fuzzy": [], "ua": [], "fuzzy_score": 1.0, "ua_score": 1.0}

    def fake_fuzzy(pred, reference, question):
        calls["fuzzy"].append((pred, reference, question))
        return calls["fuzzy_score"]

    def fake_ua(pred, reference, question):
        calls["ua"].append((pred, reference, question))
        return calls["ua_score"]

    monkeypatch.setattr(evaluators, "llm_fuzzy_match", fake_fuzzy)
    monkeypatch.setattr(evaluators, "llm_ua_match", fake_ua)
    return calls


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(evaluators.time, "sleep", lambda seconds: None)


# StringEvaluator helpers


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("  Hello  ", "hello"),
        ("'Quoted'", "quoted"),
        ('"Double Quoted"', "double quoted"),
        ("'mismatched\"", "'mismatched\""),
        ("it's", "it's"),
        ("", ""),
    ],
)
def test_clean_answer(answer, expected):
    assert StringEvaluator.clean_answer(answer) == expected


@pytest.mark.parametrize(
    "ref, pred, expected",
    [
        ("Pittsburgh", "pittsburgh", 1.0),
        ("Pittsburgh", " 'PITTSBURGH' ", 1.0),
        ("Pittsburgh", "Pittsburgh, PA", 0.0),
        ("N/A", "n/a", 1.0),
    ],
)
def test_exact_match(ref, pred, expected):
    assert StringEvaluator.exact_match(ref=ref, pred=pred) == expected


def test_must_include_substring():
    assert StringEvaluator.must_include(ref="Blue", pred="the blue shirt") == 1.0
    assert StringEvaluator.must_include(ref="red", pred="the blue shirt") == 0.0


def test_must_include_tokenize_prevents_single_char_false_positive():
    assert StringEvaluator.must_include(ref="0", pred="I have 10 items", tokenize=True) == 0.0
    assert StringEvaluator.must_include(ref="0", pred="I have 0 items", tokenize=True) == 1.0
    # without tokenization a single character matches anywhere
    assert StringEvaluator.must_include(ref="0", pred="I have 10 items") == 1.0


def test_must_include_tokenize_ignored_for_multi_char_ref():
    assert StringEvaluator.must_include(ref="10", pred="item-100", tokenize=True) == 1.0


# StringEvaluator.__call__


def test_string_evaluator_exact_match(write_config):
    config = write_config({"reference_answers": {"exact_match": "Yes"}})
    evaluator = StringEvaluator()
    assert evaluator(answer_trajectory('"YES"'), config) == 1.0
    assert evaluator(answer_trajectory("no"), config) == 0.0


def test_string_evaluator_must_include_all_values(write_config):
    config = write_config({"reference_answers": {"must_include": ["alice", "bob"]}})
    evaluator = StringEvaluator()
    assert evaluator(answer_trajectory("Alice and Bob"), config) == 1.0
    assert evaluator(answer_trajectory("Alice only"), config) == 0.0


def test_string_evaluator_must_include_tokenizes_single_reference(write_config):
    config = write_config({"reference_answers": {"must_include": ["0"]}})
    evaluator = StringEvaluator()
    assert evaluator(answer_trajectory("There are 0 reviews"), config) == 1.0
    assert evaluator(answer_trajectory("There are 10 reviews"), config) == 0.0


def test_string_evaluator_must_include_no_tokenize_with_several_references(write_config):
    config = write_config({"reference_answers": {"must_include": ["0", "reviews"]}})
    assert StringEvaluator()(answer_trajectory("There are 10 reviews"), config) == 1.0


def test_string_evaluator_combines_approaches(write_config):
    config = write_config(
        {"reference_answers": {"exact_match": "blue shirt", "must_include": ["blue"]}}
    )
    evaluator = StringEvaluator()
    assert evaluator(answer_trajectory("Blue Shirt"), config) == 1.0
    assert evaluator(answer_trajectory("blue shirts"), config) == 0.0


def test_string_evaluator_fuzzy_match_calls_llm_per_reference(write_config, llm_calls):
    config = write_config(
        {"reference_answers": {"fuzzy_match": ["ref one", "ref two"]}}, intent="Find it"
    )
    llm_calls["fuzzy_score"] = 1.0
    assert StringEvaluator()(answer_trajectory("My Answer"), config) == 1.0
    assert llm_calls["fuzzy"] == [
        ("my answer", "ref one", "Find it"),
        ("my answer", "ref two", "Find it"),
    ]

    llm_calls["fuzzy_score"] = 0.0
    assert StringEvaluator()(answer_trajectory("My Answer"), config) == 0.0


def test_string_evaluator_na_exact_skips_llm(write_config, llm_calls):
    config = write_config({"reference_answers": {"fuzzy_match": "N/A"}, "string_note": "why"})
    assert StringEvaluator()(answer_trajectory("N/A"), config) == 1.0
    assert llm_calls["ua"] == []


@pytest.mark.parametrize("ua_score", [0.0, 1.0])
def test_string_evaluator_na_falls_back_to_ua_match(write_config, llm_calls, ua_score):
    config = write_config(
        {"reference_answers": {"fuzzy_match": "N/A"}, "string_note": "no such order"},
        intent="Cancel order 42",
    )
    llm_calls["ua_score"] = ua_score
    score = StringEvaluator()(answer_trajectory("N/A: the order does not exist"), config)
    assert score == ua_score
    assert llm_calls["ua"] == [
        ("n/a: the order does not exist", "no such order", "Cancel order 42")
    ]


def test_string_evaluator_na_fallback_keeps_earlier_failures(write_config, llm_calls):
    # regression: the N/A fallback used to overwrite (not multiply) the running score
    config = write_config(
        {
            "reference_answers": {"must_include": ["refund"], "fuzzy_match": "N/A"},
            "string_note": "not possible",
        }
    )
    llm_calls["ua_score"] = 1.0
    assert StringEvaluator()(answer_trajectory("it is not possible"), config) == 0.0


# URLEvaluator


def url_score(write_config, page_url, reference_url, url_note=None):
    eval_config = {"reference_url": reference_url}
    if url_note is not None:
        eval_config["url_note"] = url_note
    config = write_config(eval_config)
    return URLEvaluator()([{}], config, FakePage(url=page_url))


@pytest.mark.parametrize(
    "page_url, reference_url, expected",
    [
        ("http://shop.test/orders", "http://shop.test/orders", 1.0),
        ("http://shop.test/orders/", "http://shop.test/orders", 1.0),
        ("http://shop.test/orders", "http://shop.test/orders/", 1.0),
        ("http://shop.test/orders/view/12", "http://shop.test/orders", 1.0),
        ("http://shop.test/cart", "http://shop.test/orders", 0.0),
        ("http://other.test/orders", "http://shop.test/orders", 0.0),
    ],
)
def test_url_evaluator_base_path(write_config, page_url, reference_url, expected):
    assert url_score(write_config, page_url, reference_url) == expected


@pytest.mark.parametrize(
    "page_url, expected",
    [
        ("http://shop.test/a", 1.0),
        ("http://shop.test/b/", 1.0),
        ("http://shop.test/c", 0.0),
    ],
)
def test_url_evaluator_or_alternatives(write_config, page_url, expected):
    reference_url = "http://shop.test/a |OR| http://shop.test/b/"
    assert url_score(write_config, page_url, reference_url) == expected


@pytest.mark.parametrize(
    "page_url, expected",
    [
        ("http://shop.test/search?q=shoe", 1.0),
        ("http://shop.test/search?page=2&q=shoe", 1.0),
        ("http://shop.test/search", 0.0),
        ("http://shop.test/search?q=boot", 0.0),
    ],
)
def test_url_evaluator_query_params(write_config, page_url, expected):
    assert url_score(write_config, page_url, "http://shop.test/search?q=shoe") == expected


def test_url_evaluator_query_values_across_alternatives(write_config):
    reference_url = "http://shop.test/search?q=shoe |OR| http://shop.test/search?q=boot"
    assert url_score(write_config, "http://shop.test/search?q=boot", reference_url) == 1.0
    assert url_score(write_config, "http://shop.test/search?q=hat", reference_url) == 0.0


def test_url_evaluator_explicit_gold_in_pred(write_config):
    assert url_score(write_config, "http://a.test/x", "http://a.test/x", "GOLD in PRED") == 1.0


def test_url_evaluator_unknown_rule(write_config):
    with pytest.raises(ValueError, match="Unknown matching rule"):
        url_score(write_config, "http://a.test/x", "http://a.test/x", "EXACT")


# HTMLContentEvaluator


def html_config(write_config, *targets, intent="Check the page"):
    return write_config({"program_html": list(targets)}, intent=intent)


def test_html_empty_locator_uses_page_content(write_config):
    page = FakePage(html="<p>Order Placed</p>")
    config = html_config(
        write_config,
        {"url": "last", "locator": "", "required_contents": {"must_include": ["order placed"]}},
    )
    assert HTMLContentEvaluator()([{}], config, page) == 1.0
    assert page.visited == []


def test_html_must_include_or_alternatives(write_config):
    page = FakePage(html="status: Shipped")
    target = {
        "url": "last",
        "locator": "",
        "required_contents": {"must_include": ["Pending |OR| Shipped", "status"]},
    }
    assert HTMLContentEvaluator()([{}], html_config(write_config, target), page) == 1.0

    target["required_contents"] = {"must_include": ["Pending |OR| Cancelled"]}
    assert HTMLContentEvaluator()([{}], html_config(write_config, target), page) == 0.0


def test_html_document_locator_with_prep_actions(write_config):
    locator = "document.querySelector('#name').value"
    page = FakePage(
        js_results={
            "() => document.querySelector('#tab').click()": None,
            f"() => {locator}": "Alice",
        }
    )
    config = html_config(
        write_config,
        {
            "url": "http://site.test/profile",
            "locator": locator,
            "prep_actions": ["document.querySelector('#tab').click()"],
            "required_contents": {"exact_match": "alice"},
        },
    )
    assert HTMLContentEvaluator()([{}], config, page) == 1.0
    assert page.visited == ["http://site.test/profile"]
    assert page.evaluated == ["() => document.querySelector('#tab').click()", f"() => {locator}"]


def test_html_spread_document_locator(write_config):
    locator = "[...document.querySelectorAll('li')].map(e => e.innerText).join(',')"
    page = FakePage(js_results={f"() => {locator}": "a,b"})
    config = html_config(
        write_config,
        {"url": "last", "locator": locator, "required_contents": {"must_include": ["b"]}},
    )
    assert HTMLContentEvaluator()([{}], config, page) == 1.0


def test_html_document_locator_error_scores_as_empty(write_config):
    locator = "document.querySelector('#missing').innerText"
    page = FakePage(js_results={f"() => {locator}": RuntimeError("null")})
    config = html_config(
        write_config,
        {"url": "last", "locator": locator, "required_contents": {"must_include": ["x"]}},
    )
    assert HTMLContentEvaluator()([{}], config, page) == 0.0


@pytest.mark.parametrize(
    "body",
    [
        "document.querySelector('#total').innerText",
        "() => document.title",
        "async () => 'x'",
    ],
)
def test_html_lambda_locator_strips_prefix_only(write_config, body):
    # regression: lstrip("lambda:") stripped leading l/a/m/b/d/: characters from the body too
    page = FakePage(js_results={body: "$42.00"})
    config = html_config(
        write_config,
        {
            "url": "last",
            "locator": f"lambda:{body}",
            "required_contents": {"exact_match": "$42.00"},
        },
    )
    assert HTMLContentEvaluator()([{}], config, page) == 1.0
    assert page.evaluated == [body]


@pytest.mark.parametrize("result", ["", None, RuntimeError("boom")])
def test_html_lambda_locator_empty_or_error_scores_zero(write_config, result):
    body = "() => document.title"
    page = FakePage(js_results={body: result})
    config = html_config(
        write_config,
        {"url": "last", "locator": f"lambda:{body}", "required_contents": {"must_include": ["x"]}},
    )
    assert HTMLContentEvaluator()([{}], config, page) == 0.0


def test_html_func_locator_calls_helper(write_config, monkeypatch):
    monkeypatch.setattr(
        evaluators, "shopping_get_sku_latest_review_rating", lambda sku: f"rating-{sku}"
    )
    config = html_config(
        write_config,
        {
            "url": "last",
            "locator": "func:shopping_get_sku_latest_review_rating('B01')",
            "required_contents": {"exact_match": "rating-b01"},
        },
    )
    assert HTMLContentEvaluator()([{}], config, FakePage()) == 1.0


def test_html_func_locator_substitutes_page(write_config, monkeypatch):
    seen = []

    def fake_role(page, account_name):
        seen.append(page)
        return "Developer"

    monkeypatch.setattr(evaluators, "gitlab_get_project_memeber_role", fake_role)
    page = FakePage()
    config = html_config(
        write_config,
        {
            "url": "last",
            "locator": "func:gitlab_get_project_memeber_role(__page__, 'byteblaze')",
            "required_contents": {"must_include": ["developer"]},
        },
    )
    assert HTMLContentEvaluator()([{}], config, page) == 1.0
    assert seen == [page]


def test_html_func_target_url_substitutes_last_url(write_config, monkeypatch):
    monkeypatch.setattr(evaluators, "reddit_get_post_url", lambda url: url + "/comments/1")
    page = FakePage(url="http://reddit.test/f/books", html="great post")
    config = html_config(
        write_config,
        {
            "url": "func:reddit_get_post_url('__last_url__')",
            "locator": "",
            "required_contents": {"must_include": ["great"]},
        },
    )
    assert HTMLContentEvaluator()([{}], config, page) == 1.0
    assert page.visited == ["http://reddit.test/f/books/comments/1"]


def test_html_fuzzy_match_joins_references(write_config, llm_calls):
    page = FakePage(html="Shipped to Pittsburgh")
    config = html_config(
        write_config,
        {"url": "last", "locator": "", "required_contents": {"fuzzy_match": ["a", "b"]}},
        intent="Where?",
    )
    llm_calls["fuzzy_score"] = 1.0
    assert HTMLContentEvaluator()([{}], config, page) == 1.0
    assert llm_calls["fuzzy"] == [("Shipped to Pittsburgh", "a, b", "Where?")]


def test_html_multiple_targets_multiply(write_config):
    page = FakePage(html="alpha beta")
    ok = {"url": "last", "locator": "", "required_contents": {"must_include": ["alpha"]}}
    bad = {"url": "last", "locator": "", "required_contents": {"must_include": ["gamma"]}}
    evaluator = HTMLContentEvaluator()
    assert evaluator([{}], html_config(write_config, ok, ok), page) == 1.0
    assert evaluator([{}], html_config(write_config, ok, bad), page) == 0.0


def test_html_none_element_stops_evaluation(write_config):
    body = "() => null"
    page = FakePage(js_results={body: None})
    config = html_config(
        write_config,
        {"url": "last", "locator": f"lambda:{body}", "required_contents": {"must_include": ["x"]}},
        {"url": "http://site.test/never", "locator": "", "required_contents": {"must_include": []}},
    )
    assert HTMLContentEvaluator()([{}], config, page) == 0.0
    assert page.visited == []


def test_html_unknown_locator(write_config):
    config = html_config(
        write_config,
        {"url": "last", "locator": "xpath://div", "required_contents": {"must_include": ["x"]}},
    )
    with pytest.raises(ValueError, match="Unknown locator"):
        HTMLContentEvaluator()([{}], config, FakePage())


def test_html_unknown_required_contents(write_config):
    config = html_config(
        write_config, {"url": "last", "locator": "", "required_contents": {"regex": "x"}}
    )
    with pytest.raises(ValueError, match="Unknown required_contents"):
        HTMLContentEvaluator()([{}], config, FakePage(html="x"))


# EvaluatorComb and evaluator_router


class FixedEvaluator(Evaluator):
    def __init__(self, score):
        super().__init__()
        self.score = score
        self.calls = 0

    def __call__(self, trajectory, config_file, page, client=None):
        self.calls += 1
        return self.score


@pytest.mark.parametrize(
    "scores, expected",
    [([], 1.0), ([1.0, 1.0], 1.0), ([1.0, 0.5], 0.5), ([1.0, 0.0, 1.0], 0.0)],
)
def test_evaluator_comb_multiplies(write_config, scores, expected):
    parts = [FixedEvaluator(score) for score in scores]
    config = write_config({})
    assert EvaluatorComb(parts)([{}], config, FakePage()) == expected
    assert all(part.calls == 1 for part in parts)


@pytest.mark.parametrize(
    "eval_types, expected",
    [
        (["string_match"], [StringEvaluator]),
        (["url_match"], [URLEvaluator]),
        (["program_html"], [HTMLContentEvaluator]),
        (["url_match", "program_html"], [URLEvaluator, HTMLContentEvaluator]),
    ],
)
def test_evaluator_router_types(write_config, eval_types, expected):
    comb = evaluator_router(write_config({"eval_types": eval_types}))
    assert isinstance(comb, EvaluatorComb)
    assert [type(e) for e in comb.evaluators] == expected


def test_evaluator_router_accepts_str_path(write_config):
    comb = evaluator_router(str(write_config({"eval_types": ["string_match"]})))
    assert [type(e) for e in comb.evaluators] == [StringEvaluator]


def test_evaluator_router_unsupported_type(write_config):
    with pytest.raises(ValueError, match="eval_type page_image_query is not supported"):
        evaluator_router(write_config({"eval_types": ["page_image_query"]}))


def test_evaluator_router_handles_every_shipped_task(tmp_path):
    raw = importlib.resources.files("browsergym.webarenalite").joinpath(
        "test_webarena_lite.raw.json"
    )
    configs = json.loads(raw.read_text())
    assert configs
    path = tmp_path / "task.json"
    for task_config in configs:
        path.write_text(json.dumps(task_config))
        comb = evaluator_router(path)
        assert len(comb.evaluators) == len(task_config["eval"]["eval_types"])


def test_router_comb_end_to_end(write_config):
    config = write_config(
        {
            "eval_types": ["string_match", "url_match"],
            "reference_answers": {"exact_match": "42"},
            "reference_url": "http://shop.test/orders/42",
        }
    )
    comb = evaluator_router(config)
    trajectory = answer_trajectory("42")
    assert comb(trajectory, config, FakePage(url="http://shop.test/orders/42/")) == 1.0
    assert comb(trajectory, config, FakePage(url="http://shop.test/orders/41")) == 0.0
    assert comb(answer_trajectory("41"), config, FakePage(url="http://shop.test/orders/42")) == 0.0
