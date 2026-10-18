"""Benchmark suites. Each module exposes ``run(runner, ctx)``."""

from . import env, observation, serialization, step

SUITES = {
    "env": env,
    "step": step,
    "obs": observation,
    "steps_io": serialization,
}
