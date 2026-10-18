import base64
import os
import re
import signal
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from browsergym.utils.mcp import ServerConfig, create_server
from browsergym.utils.mcp.server import format_action
from browsergym.utils.mcp.session import BrowserSession, browser_worker

from .conftest import free_port

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "goto",
    "click",
    "fill",
    "select_option",
    "scroll",
    "hover",
    "press",
    "send_msg_to_user",
    "go_back",
    "noop",
    "get_observation",
    "reset",
    "close_browser",
}


def bid_of(axtree: str, role: str, name: str) -> str:
    match = re.search(rf"\[([^\]]+)\] {role} '{re.escape(name)}'", axtree)
    assert match, f"no {role} {name!r} in AXTree:\n{axtree}"
    return match.group(1)


def text_of(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


@asynccontextmanager
async def client(**config_kwargs):
    server = create_server(ServerConfig(**config_kwargs))
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        yield session


async def call(session: ClientSession, name: str, **arguments):
    result = await session.call_tool(name, arguments)
    assert result.structuredContent is not None, text_of(result)
    return result, result.structuredContent


def test_format_action():
    assert format_action("fill", {"bid": "12", "value": 'it\'s "quoted"'}) == (
        "fill(bid='12', value='it\\'s \"quoted\"')"
    )


async def test_tool_listing_has_typed_schemas():
    async with client() as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    assert EXPECTED_TOOLS <= set(tools)
    fill = tools["fill"]
    assert fill.inputSchema["required"] == ["bid", "value"]
    assert fill.inputSchema["properties"]["enable_autocomplete_menu"]["type"] == "boolean"
    assert "bid" in tools["click"].inputSchema["required"]
    assert set(tools["scroll"].inputSchema["required"]) == {"delta_x", "delta_y"}
    for name in ("fill", "click", "get_observation", "reset"):
        props = tools[name].outputSchema["properties"]
        assert {"url", "axtree", "last_action_error"} <= set(props)
    assert tools["get_observation"].annotations.readOnlyHint is True


async def test_form_flow(static_site):
    async with client() as session:
        result, obs = await call(session, "reset", start_url=f"{static_site}/form.html")
        assert obs["url"] == f"{static_site}/form.html"
        assert obs["title"] == "MCP Test Form"
        images = [c for c in result.content if c.type == "image"]
        assert len(images) == 1 and images[0].mimeType == "image/png"
        assert base64.b64decode(images[0].data)[:8] == b"\x89PNG\r\n\x1a\n"
        axtree = obs["axtree"]

        _, obs = await call(session, "fill", bid=bid_of(axtree, "textbox", "Name"), value="Alice")
        assert obs["last_action_error"] == ""
        assert obs["action"].startswith("fill(")

        _, obs = await call(
            session, "select_option", bid=bid_of(axtree, "combobox", "Size"), options="Large"
        )
        assert obs["last_action_error"] == ""

        _, obs = await call(session, "click", bid=bid_of(axtree, "button", "Submit"))
        assert "Ordered l for Alice" in obs["axtree"]

        _, obs = await call(session, "hover", bid=bid_of(axtree, "button", "Hover me"))
        assert "Hovered!" in obs["axtree"]

        _, obs = await call(
            session, "press", bid=bid_of(axtree, "textbox", "Keys"), key_comb="Enter"
        )
        assert "Enter pressed" in obs["axtree"]

        _, obs = await call(session, "scroll", delta_x=0, delta_y=1500)
        assert obs["last_action_error"] == ""

        _, obs = await call(session, "send_msg_to_user", text="Order placed")
        assert {"role": "assistant", "message": "Order placed"}.items() <= obs["chat_messages"][
            -1
        ].items()

        _, obs = await call(session, "goto", url=f"{static_site}/second.html")
        assert obs["title"] == "Second Page"
        assert "Welcome to the second page" in obs["axtree"]
        assert obs["step"] == 8

        _, obs = await call(session, "go_back")
        assert obs["title"] == "MCP Test Form"

        result, obs = await call(session, "get_observation")
        assert obs["action"] is None and obs["url"].endswith("/form.html")
        assert "URL: " in text_of(result) and "AXTree:" in text_of(result)


async def test_action_error_is_reported(static_site):
    async with client(screenshots=False) as session:
        await call(session, "reset", start_url=f"{static_site}/form.html")
        result, obs = await call(session, "click", bid="does-not-exist")
        assert result.isError is True
        assert obs["last_action_error"]
        assert "Last action error:" in text_of(result)
        assert not [c for c in result.content if c.type == "image"]


async def test_lazy_start_and_close(static_site):
    async with client(start_url=f"{static_site}/second.html", screenshots=False) as session:
        _, obs = await call(session, "get_observation")
        assert obs["title"] == "Second Page"
        result = await session.call_tool("close_browser", {})
        assert text_of(result) == "Browser closed."
        result = await session.call_tool("close_browser", {})
        assert text_of(result) == "No browser was running."
        _, obs = await call(session, "get_observation")  # relaunches
        assert obs["title"] == "Second Page" and obs["step"] == 0


async def test_sessions_are_isolated(static_site):
    async with client(screenshots=False) as a, client(screenshots=False) as b:
        await call(a, "reset", start_url=f"{static_site}/form.html")
        await call(b, "reset", start_url=f"{static_site}/second.html")
        _, obs_a = await call(a, "get_observation")
        _, obs_b = await call(b, "get_observation")
    assert obs_a["title"] == "MCP Test Form"
    assert obs_b["title"] == "Second Page"


async def test_upload_file_is_opt_in():
    async with client() as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert "upload_file" not in names
    async with client(subsets=["bid", "coord"]) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert "mouse_click" in names
        assert not names & {"upload_file", "mouse_upload_file"}
    async with client(subsets=["bid", "coord"], allow_upload_file=True) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert {"upload_file", "mouse_upload_file"} <= names


async def test_failed_reset_recovers(static_site):
    async with client(start_url=f"{static_site}/second.html", timeout_ms=5000) as session:
        bad = await session.call_tool("reset", {"start_url": f"http://127.0.0.1:{free_port()}/"})
        assert bad.isError
        # the broken env is discarded, so the next call starts the configured task again
        _, obs = await call(session, "get_observation")
        assert obs["title"] == "Second Page"


def test_observe_after_active_tab_closed(static_site):
    session = BrowserSession(ServerConfig(start_url=f"{static_site}/form.html"))

    def scenario():
        session.reset_sync()
        session.step_sync("new_tab()")
        session.step_sync(f"goto('{static_site}/second.html')")
        session.browser_env.page.close()  # e.g. the page called window.close()
        return session.observe_sync()

    try:
        obs = browser_worker().submit(scenario).result(timeout=60)
        assert obs.title == "MCP Test Form"
    finally:
        browser_worker().submit(session.dispose_sync).result(timeout=60)


def test_disposed_session_does_not_relaunch(static_site):
    session = BrowserSession(ServerConfig(start_url=f"{static_site}/form.html"))
    browser_worker().submit(session.dispose_sync).result(timeout=60)
    with pytest.raises(RuntimeError, match="was closed"):
        browser_worker().submit(session.step_sync, "noop()").result(timeout=60)
    assert session.env is None


def _wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        assert proc.poll() is None, proc.stderr.read().decode()
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"server did not listen on {port}")


async def test_streamable_http_transport(static_site):
    port = free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "browsergym.utils.mcp",
            "--transport",
            "streamable-http",
            "--port",
            str(port),
            "--start-url",
            f"{static_site}/form.html",
        ],
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_port(port, proc)
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {t.name for t in (await session.list_tools()).tools}
                assert EXPECTED_TOOLS <= tools
                _, obs = await call(session, "get_observation")
                assert obs["title"] == "MCP Test Form"
                bid = bid_of(obs["axtree"], "textbox", "Name")
                _, obs = await call(session, "fill", bid=bid, value="Bob")
                assert obs["last_action_error"] == ""
                _, obs = await call(session, "click", bid=bid_of(obs["axtree"], "button", "Submit"))
                assert "Ordered s for Bob" in obs["axtree"]
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise
    stderr = proc.stderr.read().decode()
    assert proc.returncode == 0, stderr
    assert "Closed BrowserGym env browsergym/openended" in stderr, stderr


async def test_stdio_transport(static_site):
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "browsergym.utils.mcp_server",
            "--no-screenshots",
            "--start-url",
            f"{static_site}/second.html",
        ],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result, obs = await call(session, "get_observation")
            assert obs["title"] == "Second Page"
            assert not [c for c in result.content if c.type == "image"]
