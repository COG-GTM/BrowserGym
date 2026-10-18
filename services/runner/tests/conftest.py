import functools
import http.server
import json
import threading
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"
SITE_DIR = Path(__file__).parent / "site"


@functools.lru_cache(maxsize=None)
def _openapi() -> dict:
    return yaml.safe_load(CONTRACT.read_text())


@functools.lru_cache(maxsize=None)
def contract_validator(schema_name: str) -> Draft202012Validator:
    """Validator for components/schemas/<schema_name>, with $refs resolved inside the contract."""
    root = dict(_openapi())
    root["$ref"] = f"#/components/schemas/{schema_name}"
    return Draft202012Validator(root, format_checker=Draft202012Validator.FORMAT_CHECKER)


def assert_valid(schema_name: str, instance) -> None:
    errors = sorted(contract_validator(schema_name).iter_errors(instance), key=str)
    assert not errors, f"{schema_name} invalid: {[e.message for e in errors]}\n{instance}"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate_run_dir(run_dir: Path) -> dict:
    """Validate every artifact of a run dir against the contract; returns parsed artifacts."""
    run = json.loads((run_dir / "run.json").read_text())
    assert_valid("Run", run)
    steps = []
    step_files = sorted(p.name for p in (run_dir / "steps").glob("*.json"))
    if not step_files:  # cancelled/failed before env.reset() completed
        assert run["n_steps"] == 0 and run["status"] in ("failed", "cancelled")
    expected = range(run["n_steps"] + 1) if step_files else range(0)
    assert step_files == sorted(f"{i}.json" for i in expected)
    for i in expected:
        step = json.loads((run_dir / "steps" / f"{i}.json").read_text())
        assert_valid("StepDetail", step)
        assert step["index"] == i
        steps.append(step)
    chat = read_jsonl(run_dir / "chat.jsonl")
    for msg in chat:
        assert_valid("ChatMessage", msg)
    events = read_jsonl(run_dir / "events.jsonl")
    for ev in events:
        assert_valid("RunEvent", ev)
        assert ev["run_id"] == run["id"]
    return {"run": run, "steps": steps, "chat": chat, "events": events}


@pytest.fixture(scope="session")
def site_url():
    """Serve tests/site over HTTP on an ephemeral port."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE_DIR))

    class QuietHandler(handler.func):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(SITE_DIR))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    server.shutdown()
