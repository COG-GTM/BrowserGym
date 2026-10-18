"""Offline unit tests for the WebArena-Lite evaluation helpers (no live sites, no OpenAI calls)."""

import os
from types import SimpleNamespace

import pytest

# webarena.browser_env.env_config asserts these are set at import time
for _site in ("REDDIT", "SHOPPING", "SHOPPING_ADMIN", "GITLAB", "WIKIPEDIA", "MAP", "HOMEPAGE"):
    os.environ.setdefault(_site, f"http://{_site.lower()}.invalid")

from browsergym.webarenalite import helper_functions
from browsergym.webarenalite.evaluators import StringEvaluator
from browsergym.webarenalite.helper_functions import (
    PseudoPage,
    _normalize_openai_response_text,
    llm_fuzzy_match,
    llm_ua_match,
    reddit_get_post_url,
)


class _Unknown:
    def __str__(self):
        return "unknown-object"


@pytest.mark.parametrize(
    "response, expected",
    [
        pytest.param((), "", id="empty-tuple"),
        pytest.param(("from tuple", {"usage": 1}), "from tuple", id="tuple-first-item"),
        pytest.param(SimpleNamespace(output_text="aggregated"), "aggregated", id="output_text"),
        pytest.param(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "first"},
                            {"type": "output_text", "text": "second"},
                        ],
                    }
                ]
            },
            "first\nsecond",
            id="responses-dict-nested-content",
        ),
        pytest.param(
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="chat"))]),
            "chat",
            id="choices-obj-message",
        ),
        pytest.param(
            SimpleNamespace(choices=[SimpleNamespace(message=None, text="completion")]),
            "completion",
            id="choices-obj-text",
        ),
        pytest.param(
            SimpleNamespace(choices=[{"message": {"content": "dict choice"}}]),
            "dict choice",
            id="choices-obj-dict-choice",
        ),
        pytest.param({"content": "direct"}, "direct", id="content-dict"),
        pytest.param(
            {"choices": [{"message": {"content": "choices dict"}}]},
            "choices dict",
            id="choices-dict-message",
        ),
        pytest.param(
            {"choices": [{"text": "choices text"}]}, "choices text", id="choices-dict-text"
        ),
        pytest.param("plain", "plain", id="str"),
        pytest.param(_Unknown(), "unknown-object", id="unknown-object-str-fallback"),
    ],
)
def test_normalize_openai_response_text(response, expected):
    assert _normalize_openai_response_text(response) == expected


def test_normalize_skips_blank_output_text():
    response = SimpleNamespace(
        output_text="   ", choices=[SimpleNamespace(message=SimpleNamespace(content="chat"))]
    )
    assert _normalize_openai_response_text(response) == "chat"


def test_normalize_empty_responses_output_falls_through_to_content():
    assert _normalize_openai_response_text({"output": [], "content": "fallback"}) == "fallback"


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []
    state = {"response": None}

    def _fake(**kwargs):
        calls.append(kwargs)
        return state["response"]

    monkeypatch.setattr(helper_functions, "generate_from_openai_chat_completion", _fake)

    def _set(response):
        state["response"] = response
        return calls

    return _set


@pytest.mark.parametrize(
    "response, expected",
    [
        ("Correct", 1.0),
        ("The student answer is correct.", 1.0),
        ("incorrect", 0.0),
        ("Incorrect: the answer is wrong", 0.0),
        ("partially correct", 0.0),
        ("Partially Correct", 0.0),
        (("correct", None), 1.0),
        (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="incorrect"))]
            ),
            0.0,
        ),
    ],
)
def test_llm_fuzzy_match_scoring(fake_llm, response, expected):
    fake_llm(response)
    assert llm_fuzzy_match("pred", "ref", "question") == expected


def test_llm_fuzzy_match_unexpected_response_raises(fake_llm):
    fake_llm("garbage")
    with pytest.raises(AssertionError):
        llm_fuzzy_match("pred", "ref", "question")


def test_llm_fuzzy_match_prompt(fake_llm):
    calls = fake_llm("correct")
    llm_fuzzy_match("my pred", "my ref", "my question")
    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "gpt-4-1106-preview"
    assert call["temperature"] == 0
    user_msg = call["messages"][-1]["content"]
    assert "question: my question\n" in user_msg
    assert "reference answer: my ref\n" in user_msg
    assert "student answer: my pred\n" in user_msg
    assert "correct/incorrect/partially correct" in user_msg


@pytest.mark.parametrize(
    "response, expected",
    [
        ("same", 1.0),
        ("Same", 1.0),
        ("different", 0.0),
        ("Different, not the same reason", 0.0),
        ({"choices": [{"message": {"content": "same"}}]}, 1.0),
    ],
)
def test_llm_ua_match_scoring(fake_llm, response, expected):
    fake_llm(response)
    assert llm_ua_match("pred", "ref", "question") == expected


def test_llm_ua_match_unexpected_response_raises(fake_llm):
    fake_llm("garbage")
    with pytest.raises(AssertionError):
        llm_ua_match("pred", "ref", "question")


def test_llm_ua_match_prompt(fake_llm):
    calls = fake_llm("same")
    llm_ua_match("reported", "actual", "the task")
    user_msg = calls[0]["messages"][-1]["content"]
    assert "task: the task\n" in user_msg
    assert "actual unachievable reason: actual\n" in user_msg
    assert "reported unachievable reason: reported\n" in user_msg


def test_string_evaluator_routes_to_llm_helpers(fake_llm):
    calls = fake_llm("correct")
    assert StringEvaluator.fuzzy_match(ref="r", pred="p", intent="i") == 1.0
    assert "reference answer: r\n" in calls[-1]["messages"][-1]["content"]
    assert "student answer: p\n" in calls[-1]["messages"][-1]["content"]
    fake_llm("different")
    assert StringEvaluator.ua_match(ref="r", pred="p", intent="i") == 0.0


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "http://reddit.example:9999/f/books/123/some-slug",
            "http://reddit.example:9999/f/books/123/",
        ),
        (
            "https://reddit.example/f/books/123/some-slug/comment/456?sort=new",
            "https://reddit.example/f/books/123/",
        ),
        ("http://reddit.example/f/books/123", "http://reddit.example/f/books/123/"),
        ("http://reddit.example/f/books", "http://reddit.example/f/books"),
        ("http://reddit.example/", "http://reddit.example/"),
        ("http://reddit.example/u/someone/posts", "http://reddit.example/u/someone/posts"),
    ],
)
def test_reddit_get_post_url(url, expected):
    assert reddit_get_post_url(url) == expected


def test_pseudo_page_overrides_url_and_delegates():
    original = SimpleNamespace(url="http://original", title=lambda: "page title")
    pseudo = PseudoPage(original, "http://pseudo")
    assert pseudo.url == "http://pseudo"
    assert pseudo.title() == "page title"
    assert pseudo.original_page is original
