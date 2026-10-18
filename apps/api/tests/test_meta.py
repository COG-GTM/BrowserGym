from __future__ import annotations

import yaml
from fastapi.openapi.utils import get_openapi

from side_api.catalog import title_of

from .conftest import CONTRACT_PATH


def test_health(api):
    resp = api.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["version"]


def test_tasks_lists_openended_and_filters(api):
    tasks = api.get("/tasks").json()
    ids = {t["id"] for t in tasks}
    assert "browsergym/openended" in ids
    assert tasks[0]["id"] == "browsergym/openended"

    miniwob = api.get("/tasks", params={"benchmark": "miniwob"}).json()
    assert miniwob and all(t["benchmark"] == "miniwob" for t in miniwob)

    webarena = api.get("/tasks", params={"benchmark": "webarena"}).json()
    assert webarena and all(t["requires_setup"] for t in webarena)

    found = api.get("/tasks", params={"q": "CLICK-TEST"}).json()
    assert [t["id"] for t in found] == ["browsergym/miniwob.click-test"]
    assert api.get("/tasks", params={"q": "zzz-no-such-task"}).json() == []


def test_miniwob_requires_setup_follows_env(api, monkeypatch):
    monkeypatch.delenv("MINIWOB_URL", raising=False)
    assert all(t["requires_setup"] for t in api.get("/tasks?benchmark=miniwob").json())
    monkeypatch.setenv("MINIWOB_URL", "file:///tmp/miniwob/")
    assert not any(t["requires_setup"] for t in api.get("/tasks?benchmark=miniwob").json())


def test_task_titles():
    assert title_of("browsergym/openended") == "Open-ended"
    assert title_of("browsergym/miniwob.click-test") == "MiniWoB++: Click Test"
    assert title_of("browsergym/webarena.12") == "WebArena #12"
    assert (
        title_of("browsergym/workarena.servicenow.order-standard-laptop")
        == "WorkArena: Order Standard Laptop"
    )


def test_agents(api):
    agents = api.get("/agents").json()
    assert [a["type"] for a in agents] == ["mock", "scripted", "openai", "anthropic"]
    assert any(a["models"] for a in agents if a["type"] == "openai")


def test_openapi_json_serves_contract(api):
    resp = api.get("/openapi.json", validate=False)
    assert resp.status_code == 200
    assert resp.json() == yaml.safe_load(CONTRACT_PATH.read_text())


def test_every_contract_operation_is_routed(api):
    spec = yaml.safe_load(CONTRACT_PATH.read_text())
    app = api.client.app
    generated = get_openapi(title=app.title, version=app.version, routes=app.routes)
    routed = {(m.upper(), path) for path, ops in generated["paths"].items() for m in ops}
    for path, item in spec["paths"].items():
        for method in item:
            if method == "parameters":
                continue
            assert (method.upper(), f"/api/v1{path}") in routed, f"{method.upper()} {path} missing"


def test_cors_preflight_allows_web_and_expo(api):
    for origin in ("http://localhost:3000", "http://localhost:8081", "http://localhost:19006"):
        resp = api.client.options(
            "/api/v1/runs",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == origin
    resp = api.client.options(
        "/api/v1/runs",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in resp.headers
