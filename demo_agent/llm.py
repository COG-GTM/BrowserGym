"""LLM providers for the demo agent: OpenAI, Anthropic and a deterministic offline mock.

Every provider takes OpenAI-style content blocks (``{"type": "text"}`` / ``{"type": "image_url"}``)
for the system and user messages and returns an :class:`LLMResponse` with token usage, so the agent
code stays provider-agnostic. Retries with exponential backoff and token/cost accounting live here.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

PROVIDERS = ("openai", "anthropic", "mock")

DEFAULT_MODELS = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-sonnet-4-5",
    "mock": "mock-deterministic",
}

API_KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

# USD per 1M tokens (input, output). Used only for cost logging; unknown models log tokens without
# a cost unless DEMO_AGENT_PRICE_IN / DEMO_AGENT_PRICE_OUT (USD per 1M tokens) are set.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "mock-deterministic": (0.0, 0.0),
}


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    latency_s: float = 0.0
    attempts: int = 1


def price_for(model: str) -> Optional[tuple[float, float]]:
    env_in, env_out = os.getenv("DEMO_AGENT_PRICE_IN"), os.getenv("DEMO_AGENT_PRICE_OUT")
    if env_in is not None and env_out is not None:
        return float(env_in), float(env_out)
    if model in PRICING_PER_MTOK:
        return PRICING_PER_MTOK[model]
    # dated snapshots, e.g. "gpt-4.1-mini-2025-04-14" or "claude-haiku-4-5-20251001"
    base = re.sub(r"-\d{4}-?\d{2}-?\d{2}$", "", model)
    return PRICING_PER_MTOK.get(base)


def estimate_cost(model: str, usage: Usage) -> Optional[float]:
    price = price_for(model)
    if price is None:
        return None
    return (usage.input_tokens * price[0] + usage.output_tokens * price[1]) / 1_000_000


@dataclass
class UsageTracker:
    """Accumulates token usage and cost over an episode."""

    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Optional[float] = 0.0

    def record(self, response: LLMResponse) -> dict:
        cost = estimate_cost(response.model, response.usage)
        self.calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        if cost is None or self.cost_usd is None:
            self.cost_usd = None
        else:
            self.cost_usd += cost
        cost_str = "n/a" if cost is None else f"${cost:.6f}"
        total_str = "n/a" if self.cost_usd is None else f"${self.cost_usd:.6f}"
        logger.info(
            "llm call #%d model=%s in=%d out=%d cost=%s latency=%.2fs attempts=%d"
            " | total in=%d out=%d cost=%s",
            self.calls,
            response.model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            cost_str,
            response.latency_s,
            response.attempts,
            self.input_tokens,
            self.output_tokens,
            total_str,
        )
        stats = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "llm_latency": response.latency_s,
            "llm_attempts": response.attempts,
        }
        if cost is not None:
            stats["cost_usd"] = cost
        return stats

    def summary(self) -> str:
        cost = "n/a (unknown model pricing)" if self.cost_usd is None else f"${self.cost_usd:.6f}"
        return (
            f"model={self.model} calls={self.calls} input_tokens={self.input_tokens} "
            f"output_tokens={self.output_tokens} cost={cost}"
        )


def retry_with_backoff(
    fn: Callable[[], T],
    is_retryable: Callable[[BaseException], bool],
    max_retries: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Call ``fn`` and retry retryable errors with exponential backoff and full jitter.

    Returns ``(result, attempts)``.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn(), attempt
        except Exception as e:
            if attempt > max_retries or not is_retryable(e):
                raise
            delay = random.uniform(0, min(max_delay, base_delay * 2 ** (attempt - 1)))
            logger.warning(
                "LLM call failed (%s: %s), retry %d/%d in %.2fs",
                type(e).__name__,
                e,
                attempt,
                max_retries,
                delay,
            )
            sleep(delay)


class LLMClient:
    provider: str = ""

    def __init__(self, model: str, max_retries: int = 4, base_delay: float = 1.0):
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay

    def complete(self, system: list[dict], user: list[dict]) -> LLMResponse:
        start = time.monotonic()
        (text, usage), attempts = retry_with_backoff(
            lambda: self._complete(system, user),
            self._is_retryable,
            max_retries=self.max_retries,
            base_delay=self.base_delay,
        )
        return LLMResponse(
            text=text,
            model=self.model,
            usage=usage,
            latency_s=time.monotonic() - start,
            attempts=attempts,
        )

    def _complete(self, system: list[dict], user: list[dict]) -> tuple[str, Usage]:
        raise NotImplementedError

    def _is_retryable(self, e: BaseException) -> bool:
        return False


def _status_retryable(status: Optional[int]) -> bool:
    return status is not None and (status in (408, 409, 429) or status >= 500)


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self, model: str, **kwargs):
        super().__init__(model, **kwargs)
        import openai

        self._openai = openai
        # retries are handled by retry_with_backoff so they are logged and counted
        self.client = openai.OpenAI(max_retries=0)

    def _complete(self, system, user):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = Usage()
        if response.usage is not None:
            usage = Usage(response.usage.prompt_tokens, response.usage.completion_tokens)
        return response.choices[0].message.content or "", usage

    def _is_retryable(self, e):
        o = self._openai
        if isinstance(e, (o.APIConnectionError, o.APITimeoutError, o.RateLimitError)):
            return True
        return isinstance(e, o.APIStatusError) and _status_retryable(e.status_code)


def _to_anthropic_blocks(blocks: list[dict]) -> list[dict]:
    out = []
    for block in blocks:
        if block["type"] == "text":
            out.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image_url":
            url = block["image_url"]
            url = url["url"] if isinstance(url, dict) else url
            m = re.match(r"data:(image/[\w.+-]+);base64,(.*)", url, re.DOTALL)
            if m:
                source = {"type": "base64", "media_type": m.group(1), "data": m.group(2)}
            else:
                source = {"type": "url", "url": url}
            out.append({"type": "image", "source": source})
        else:
            raise ValueError(f"Unknown message type {block['type']!r}")
    return out


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: str, max_tokens: int = 2048, **kwargs):
        super().__init__(model, **kwargs)
        import anthropic

        self._anthropic = anthropic
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic(max_retries=0)

    def _complete(self, system, user):
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system="\n".join(b["text"] for b in system if b["type"] == "text"),
            messages=[{"role": "user", "content": _to_anthropic_blocks(user)}],
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        return text, Usage(response.usage.input_tokens, response.usage.output_tokens)

    def _is_retryable(self, e):
        a = self._anthropic
        if isinstance(e, (a.APIConnectionError, a.APITimeoutError, a.RateLimitError)):
            return True
        return isinstance(e, a.APIStatusError) and _status_retryable(e.status_code)


def _approx_tokens(blocks: list[dict]) -> int:
    chars = sum(len(b.get("text", "")) for b in blocks if b.get("type") == "text")
    images = sum(1 for b in blocks if b.get("type") == "image_url")
    return chars // 4 + 85 * images


class MockLLMClient(LLMClient):
    """Deterministic offline LLM used by ``--dry-run`` and the tests.

    Follows the Side ``mock`` agent script: scroll, noop, then ``send_msg_to_user`` with a summary
    of the active tab. The reply only depends on the call index and the prompt, never on randomness
    or the network. Token usage is approximated as characters / 4.
    """

    provider = "mock"

    def __init__(self, model: str = DEFAULT_MODELS["mock"], **kwargs):
        super().__init__(model, **kwargs)
        self.calls = 0

    def _complete(self, system, user):
        prompt = "\n".join(b.get("text", "") for b in system + user if b.get("type") == "text")
        step = self.calls
        self.calls += 1
        if step == 0:
            text = (
                "I am running in dry-run mode with a deterministic mock LLM. "
                "First I scroll down to look at the rest of the page.\n"
                "```scroll(0, 200)```"
            )
        elif step == 1:
            text = "Nothing else to inspect, I wait one step.\n```noop()```"
        else:
            title = _active_tab_field(prompt, "Title") or "unknown"
            url = _active_tab_field(prompt, "URL") or "unknown"
            n_bids = len(set(re.findall(r"\[(\d+)\]", prompt)))
            summary = (
                f"Dry run complete. Active tab: {title!r} ({url}), "
                f"{n_bids} elements with a bid in the accessibility tree."
            )
            text = f"I report what I saw to the user.\n```send_msg_to_user({summary!r})```"
        return text, Usage(_approx_tokens(system) + _approx_tokens(user), len(text) // 4)


def _active_tab_field(prompt: str, name: str) -> Optional[str]:
    m = re.search(r"\(active tab\)\n\s+Title: (.*)\n\s+URL: (.*)\n", prompt)
    if not m:
        return None
    return (m.group(1) if name == "Title" else m.group(2)).strip()


def make_llm(provider: str, model: Optional[str] = None, **kwargs) -> LLMClient:
    if provider not in PROVIDERS:
        raise LLMError(f"Unknown provider {provider!r}, expected one of {PROVIDERS}")
    model = model or DEFAULT_MODELS[provider]
    if provider == "mock":
        return MockLLMClient(model, **kwargs)
    key_env = API_KEY_ENV[provider]
    if not os.getenv(key_env):
        raise LLMError(
            f"{key_env} is not set. Export it, or use --dry-run to run offline with the mock LLM."
        )
    if provider == "openai":
        return OpenAIClient(model, **kwargs)
    return AnthropicClient(model, **kwargs)
