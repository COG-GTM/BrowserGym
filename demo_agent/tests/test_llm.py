import types

import openai

try:  # openai>=3 ships its HTTP client as httpx2
    import httpx2 as httpx
except ImportError:
    import httpx
import llm
import pytest
from llm import (
    LLMError,
    LLMResponse,
    MockLLMClient,
    OpenAIClient,
    Usage,
    UsageTracker,
    _to_anthropic_blocks,
    estimate_cost,
    make_llm,
    retry_with_backoff,
)

PROMPT = [
    {
        "type": "text",
        "text": (
            "Tab 0 (active tab)\n  Title: Hello\n  URL: file:///x.html\n\n"
            "[6] heading 'Hi'\n[7] link 'A'\n"
        ),
    }
]


def test_mock_is_deterministic_and_follows_script():
    replies = []
    for _ in range(2):
        client = MockLLMClient()
        replies.append([client.complete([], PROMPT).text for _ in range(3)])
    assert replies[0] == replies[1]
    assert "```scroll(0, 200)```" in replies[0][0]
    assert "```noop()```" in replies[0][1]
    assert "send_msg_to_user(" in replies[0][2]
    assert "'Hello' (file:///x.html), 2 elements" in replies[0][2]


def test_mock_counts_bids_in_html_observation():
    client = MockLLMClient()
    html = [
        {"type": "text", "text": '<button bid="4">Submit</button><a bid="5">x</a> [4]'},
        {"type": "text", "text": '<iframe bid="a"><button bid="a0">'},
    ]
    reply = [client.complete([], html).text for _ in range(3)][-1]
    assert "4 elements with a bid" in reply


def test_mock_reports_usage():
    response = MockLLMClient().complete([], PROMPT)
    assert response.usage.input_tokens > 0 and response.usage.output_tokens > 0
    assert estimate_cost(response.model, response.usage) == 0.0


def test_make_llm_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        make_llm("openai")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        make_llm("anthropic")
    with pytest.raises(LLMError):
        make_llm("nope")
    assert isinstance(make_llm("mock"), MockLLMClient)


def test_retry_with_backoff_retries_then_succeeds():
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("flaky")
        return "ok"

    result, attempts = retry_with_backoff(
        fn, lambda e: isinstance(e, TimeoutError), max_retries=4, base_delay=1, sleep=sleeps.append
    )
    assert (result, attempts) == ("ok", 3)
    assert len(sleeps) == 2 and sleeps[0] <= 1 and sleeps[1] <= 2


def test_retry_with_backoff_gives_up():
    def fn():
        raise TimeoutError("down")

    with pytest.raises(TimeoutError):
        retry_with_backoff(fn, lambda e: True, max_retries=2, sleep=lambda s: None)

    calls = []

    def fatal():
        calls.append(1)
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        retry_with_backoff(fatal, lambda e: False, max_retries=5, sleep=lambda s: None)
    assert len(calls) == 1


def _status_error(cls, status):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return cls("err", response=httpx.Response(status, request=request), body=None)


def test_openai_client_retries_rate_limits(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    client = OpenAIClient("gpt-5-mini", base_delay=0)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise _status_error(openai.RateLimitError, 429)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="```noop()```"))],
            usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=10),
        )

    client.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    response = client.complete([{"type": "text", "text": "sys"}], PROMPT)
    assert response.text == "```noop()```"
    assert response.attempts == 2
    assert response.usage.input_tokens == 100
    assert calls[0]["model"] == "gpt-5-mini"
    assert not client._is_retryable(_status_error(openai.BadRequestError, 400))
    assert client._is_retryable(_status_error(openai.InternalServerError, 503))


def test_cost_estimation(monkeypatch):
    monkeypatch.delenv("DEMO_AGENT_PRICE_IN", raising=False)
    monkeypatch.delenv("DEMO_AGENT_PRICE_OUT", raising=False)
    usage = Usage(1_000_000, 1_000_000)
    assert estimate_cost("gpt-4o-mini", usage) == pytest.approx(0.75)
    assert estimate_cost("gpt-4.1-mini-2025-04-14", usage) == pytest.approx(2.0)
    assert estimate_cost("claude-haiku-4-5-20251001", usage) == pytest.approx(6.0)
    assert estimate_cost("some-future-model", usage) is None
    monkeypatch.setenv("DEMO_AGENT_PRICE_IN", "1")
    monkeypatch.setenv("DEMO_AGENT_PRICE_OUT", "2")
    assert estimate_cost("some-future-model", usage) == pytest.approx(3.0)


def test_usage_tracker_accumulates(monkeypatch):
    monkeypatch.delenv("DEMO_AGENT_PRICE_IN", raising=False)
    tracker = UsageTracker(model="gpt-4o-mini")
    stats = tracker.record(LLMResponse("x", "gpt-4o-mini", Usage(1000, 100)))
    tracker.record(LLMResponse("x", "gpt-4o-mini", Usage(1000, 100)))
    assert stats["input_tokens"] == 1000 and stats["cost_usd"] == pytest.approx(0.00021)
    assert (tracker.calls, tracker.input_tokens, tracker.output_tokens) == (2, 2000, 200)
    assert tracker.cost_usd == pytest.approx(0.00042)
    tracker.record(LLMResponse("x", "unknown-model", Usage(1, 1)))
    assert tracker.cost_usd is None and "n/a" in tracker.summary()


def test_anthropic_block_conversion():
    blocks = _to_anthropic_blocks(
        [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
            {"type": "image_url", "image_url": "https://example.com/a.png"},
        ]
    )
    assert blocks[0] == {"type": "text", "text": "hi"}
    assert blocks[1]["source"] == {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}
    assert blocks[2]["source"] == {"type": "url", "url": "https://example.com/a.png"}


def test_anthropic_client_uses_messages_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    client = make_llm("anthropic", "claude-haiku-4-5")
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="ok\n```noop()```")],
            usage=types.SimpleNamespace(input_tokens=50, output_tokens=5),
        )

    client.client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    response = client.complete([{"type": "text", "text": "be helpful"}], PROMPT)
    assert response.text == "ok\n```noop()```" and response.usage.output_tokens == 5
    assert seen["system"] == "be helpful" and seen["model"] == "claude-haiku-4-5"
    assert seen["messages"][0]["content"][0]["type"] == "text"
