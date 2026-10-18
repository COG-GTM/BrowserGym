"""Environment construction and reset latency."""

from __future__ import annotations

from ..context import Context
from ..harness import Runner

GROUP = "env"


def run(runner: Runner, ctx: Context) -> None:
    first = next(iter(ctx.pages.values()))

    # gym.make only builds the wrapper stack; the browser is launched lazily in reset().
    runner.bench(
        GROUP,
        "make",
        "-",
        lambda holder: holder.append(ctx.make_env(first.url)),
        rounds=20,
        setup=list,
        teardown=lambda holder: [e.close() for e in holder],
    )

    for size, info in ctx.pages.items():
        # cold reset: launches chromium, opens the page, extracts the first observation
        runner.bench(
            GROUP,
            "reset",
            size,
            lambda env: env.reset(seed=0),
            rounds=8,
            setup=lambda url=info.url: ctx.make_env(url),
            teardown=lambda env: env.close(),
            params=ctx.page_params(size),
        )

        # make + reset + close: full episode boot/teardown cost as seen by a runner
        runner.bench(
            GROUP,
            "make_reset_close",
            size,
            lambda _, url=info.url: _make_reset_close(ctx, url),
            rounds=5,
            params=ctx.page_params(size),
        )


def _make_reset_close(ctx: Context, url: str) -> None:
    env = ctx.make_env(url)
    try:
        env.reset(seed=0)
    finally:
        env.close()
