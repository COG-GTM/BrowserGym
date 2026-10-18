from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_core import OpenAPI
from openapi_core.testing import MockRequest, MockResponse
from openapi_schema_validator import OAS31Validator

from side_api.config import Settings
from side_api.main import create_app

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
TERMINAL = {"succeeded", "failed", "cancelled"}


class Contract:
    """Validates live responses against contracts/openapi.yaml."""

    def __init__(self, path: Path):
        self.spec_dict = yaml.safe_load(path.read_text())
        self.openapi = OpenAPI.from_file_path(str(path))

    def operation(self, method: str, path: str) -> dict:
        rel = path.removeprefix("/api/v1")
        for template, item in self.spec_dict["paths"].items():
            pattern = "^" + re.sub(r"\\{[^/]+\\}", "[^/]+", re.escape(template)) + "$"
            if re.match(pattern, rel) and method.lower() in item:
                return item[method.lower()]
        raise AssertionError(f"{method} {path} is not in the contract")

    def validate(self, resp: httpx.Response) -> httpx.Response:
        req = resp.request
        content_type = resp.headers.get("content-type", "application/json").split(";")[0]
        if content_type not in ("application/json", ""):
            # Binary / streaming bodies: check status + media type against the contract
            # (SSE payloads are validated per event with validate_schema("RunEvent", ...)).
            op = self.operation(req.method, req.url.path)
            declared = op["responses"].get(str(resp.status_code))
            assert declared is not None, f"undeclared status {resp.status_code}"
            assert content_type in declared.get("content", {}), f"undeclared {content_type}"
            return resp
        mock_req = MockRequest(
            "http://localhost:8000",
            req.method.lower(),
            req.url.path,
            args=dict(req.url.params),
            data=req.content or None,
            content_type="application/json",
        )
        mock_resp = MockResponse(
            resp.content, status_code=resp.status_code, content_type=content_type
        )
        self.openapi.validate_response(mock_req, mock_resp)
        return resp

    def validate_schema(self, name: str, instance: Any) -> None:
        schema = {
            "$ref": f"#/components/schemas/{name}",
            "components": self.spec_dict["components"],
        }
        OAS31Validator(schema).validate(instance)


@pytest.fixture(scope="session")
def contract() -> Contract:
    return Contract(CONTRACT_PATH)


class Api:
    def __init__(self, client: TestClient, contract: Contract):
        self.client = client
        self.contract = contract

    def __getattr__(self, method: str) -> Callable[..., httpx.Response]:
        fn = getattr(self.client, method)

        def call(path: str, *args, validate: bool = True, **kwargs) -> httpx.Response:
            resp = fn(f"/api/v1{path}", *args, **kwargs)
            if validate:
                self.contract.validate(resp)
            return resp

        return call

    def create_run(self, **overrides) -> dict:
        body = {
            "task_id": "browsergym/openended",
            "agent": {"type": "mock"},
            "goal": "Find the pricing page",
            "start_url": "https://example.com",
            "max_steps": 10,
        } | overrides
        resp = self.post("/runs", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def wait_for(self, run_id: str, statuses=TERMINAL, timeout: float = 15.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.get(f"/runs/{run_id}").json()
            if run["status"] in statuses:
                return run
            time.sleep(0.05)
        raise AssertionError(f"run {run_id} did not reach {statuses}: {run}")


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if not line or line.startswith(":"):
                continue
            key, _, value = line.partition(": ")
            fields[key] = value
        if "data" in fields:
            events.append(
                {
                    "id": fields.get("id"),
                    "event": fields["event"],
                    "data": json.loads(fields["data"]),
                }
            )
    return events


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "side-data",
        fake_runner=True,
        fake_step_delay=0.05,
        poll_interval=0.02,
        contract_path=CONTRACT_PATH,
    )


@pytest.fixture
def make_api(contract: Contract) -> Iterator[Callable[[Settings], Api]]:
    clients: list[TestClient] = []

    def _make(settings: Settings) -> Api:
        client = TestClient(create_app(settings))
        client.__enter__()
        clients.append(client)
        return Api(client, contract)

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def api(make_api, settings: Settings) -> Api:
    return make_api(settings)
