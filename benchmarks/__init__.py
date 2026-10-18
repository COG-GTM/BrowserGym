"""Offline performance benchmark harness for BrowserGym.

Run ``python -m benchmarks run --json out.json`` and compare against a baseline with
``python -m benchmarks compare benchmarks/baselines/baseline.json out.json``.
"""

__all__ = ["harness", "pages", "server", "compare"]
