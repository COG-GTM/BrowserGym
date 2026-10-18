"""Experiment-loop step serialization: ``StepInfo.save_step_info`` and reload."""

from __future__ import annotations

import shutil

from browsergym.experiments.loop import ExpResult, StepInfo

from ..context import Context
from ..harness import Runner

GROUP = "steps_io"
NAMES = ["save", "save_json", "load"]


def run(runner: Runner, ctx: Context) -> None:
    for size, info in ctx.pages.items():
        if not runner.any_selected(GROUP, NAMES, size):
            continue
        env = ctx.make_env(info.url)
        try:
            obs, _ = env.reset(seed=0)
        finally:
            env.close()
        _run_size(runner, ctx, size, obs)


def _fresh_dir(ctx: Context, name: str):
    path = ctx.workdir / "steps_io" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def _step_info(obs: dict) -> StepInfo:
    info = StepInfo(step=0, obs=dict(obs), action="noop()", terminated=False, truncated=False)
    info.agent_info = {"think": "benchmark", "chat_messages": []}
    info.stats = {"step_elapsed": 0.0, "agent_elapsed": 0.0}
    return info


def _dir_bytes(path) -> int:
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file())


def _run_size(runner: Runner, ctx: Context, size: str, obs: dict) -> None:
    params = ctx.page_params(size)
    rounds = {"small": 15, "medium": 10, "large": 5}.get(size, 5)
    step_info = _step_info(obs)

    # default experiment-loop path: gzip pickle + screenshot PNG
    out = _fresh_dir(ctx, f"{size}-save")
    step_info.save_step_info(out)
    save_params = dict(params, artifact_bytes=_dir_bytes(out))
    runner.bench(
        GROUP,
        "save",
        size,
        lambda d: step_info.save_step_info(d),
        rounds=rounds,
        setup=lambda: _fresh_dir(ctx, f"{size}-save"),
        params=save_params,
    )

    # save_json=True additionally dumps the whole StepInfo (incl. DOM/AXTree) as JSON
    out_json = _fresh_dir(ctx, f"{size}-json")
    step_info.save_step_info(out_json, save_json=True)
    runner.bench(
        GROUP,
        "save_json",
        size,
        lambda d: step_info.save_step_info(d, save_json=True),
        rounds=max(3, rounds // 2),
        setup=lambda: _fresh_dir(ctx, f"{size}-json"),
        params=dict(params, artifact_bytes=_dir_bytes(out_json)),
    )

    # replay path: ExpResult.get_step_info (unpickle + screenshot PNG decode)
    def load(_):
        loaded = ExpResult(out).get_step_info(0)
        assert loaded.obs["screenshot"].shape == obs["screenshot"].shape

    runner.bench(GROUP, "load", size, load, rounds=rounds, params=save_params)
