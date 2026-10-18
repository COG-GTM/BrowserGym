"""``env.step`` latency for common high-level actions (includes observation extraction)."""

from __future__ import annotations

import itertools

from browsergym.core.constants import BROWSERGYM_ID_ATTRIBUTE as BID_ATTR

from ..context import Context, collect_garbage, watch_crashes
from ..harness import Runner

GROUP = "step"
NAMES = ["noop", "click", "fill", "scroll", "goto"]


def _bid(env, selector: str) -> str:
    bid = env.unwrapped.page.get_attribute(selector, BID_ATTR)
    if bid is None:
        raise RuntimeError(f"element {selector!r} has no {BID_ATTR} attribute")
    return bid


def _step(env, action: str) -> None:
    _, _, _, _, info = env.step(action)
    error = env.unwrapped.last_action_error
    if error:
        raise RuntimeError(f"action {action!r} failed: {error}")


def run(runner: Runner, ctx: Context) -> None:
    for size, info in ctx.pages.items():
        if not runner.any_selected(GROUP, NAMES, size):
            continue
        env = ctx.make_env(info.url)
        try:
            env.reset(seed=0)
            button = _bid(env, "#bench-button")
            field = _bid(env, "#bench-input")
            params = ctx.page_params(size)
            watch_crashes(env.unwrapped.page, f"step[{size}]")

            def gc_setup():
                collect_garbage(env.unwrapped.page)

            # noop(0): step overhead = action dispatch + page-load wait + observation extraction
            runner.bench(
                GROUP,
                "noop",
                size,
                lambda _: _step(env, "noop(0)"),
                rounds=15,
                setup=gc_setup,
                params=params,
            )
            runner.bench(
                GROUP,
                "click",
                size,
                lambda _: _step(env, f'click("{button}")'),
                rounds=15,
                setup=gc_setup,
                params=params,
            )
            texts = itertools.cycle(["hello world", "browsergym benchmark"])
            runner.bench(
                GROUP,
                "fill",
                size,
                lambda _: _step(env, f'fill("{field}", "{next(texts)}")'),
                rounds=15,
                setup=gc_setup,
                params=params,
            )
            # alternate down/up so every round scrolls the same distance
            deltas = itertools.cycle([300, -300])
            runner.bench(
                GROUP,
                "scroll",
                size,
                lambda _: _step(env, f"scroll(0, {next(deltas)})"),
                rounds=16,
                setup=gc_setup,
                params=params,
            )
            # full navigation (reload of the same page) + observation
            runner.bench(
                GROUP,
                "goto",
                size,
                lambda _: _step(env, f'goto("{info.url}")'),
                rounds=10,
                setup=gc_setup,
                params=params,
            )
        finally:
            env.close()
