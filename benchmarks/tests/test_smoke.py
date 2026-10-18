"""End-to-end smoke run of the real suites (needs playwright + chromium)."""

import json

import pytest

pytest.importorskip("browsergym.core")
pytest.importorskip("browsergym.experiments")

from benchmarks.cli import main  # noqa: E402


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_available(), reason="playwright chromium not installed")
def test_quick_run_small_page(tmp_path):
    out = tmp_path / "out.json"
    code = main(
        [
            "run",
            "--size",
            "small",
            "--rounds",
            "1",
            "-k",
            "env.reset",
            "-k",
            "step.click",
            "-k",
            "obs.*",
            "-k",
            "steps_io.save[",
            "--json",
            str(out),
        ]
    )
    assert code == 0
    data = json.loads(out.read_text())
    ids = {r["id"] for r in data["results"]}
    assert {"env.reset[small]", "step.click[small]", "obs.flatten_axtree[small]"} <= ids
    assert "steps_io.save[small]" in ids and "steps_io.load[small]" not in ids
    assert data["metadata"]["dom_nodes"]["small"] > 50
    assert all(r["stats"]["median"] > 0 for r in data["results"])
