import asyncio
import concurrent.futures
import importlib
import sys
from types import SimpleNamespace

import gymnasium as gym
import playwright.sync_api
import pytest

import browsergym.core.action.functions as fn_context
from browsergym.core.action.highlevel import ACTION_SUBSETS
from browsergym.core.env import BrowserEnv

MCP_SERVER_MODULE = "browsergym.utils.mcp_server"


def run_async(coro):
    # pytest-playwright keeps a sync Playwright event loop alive in the main thread,
    # so coroutines are run on a fresh loop in a worker thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


class FakePage:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def wait_for_timeout(self, timeout):
        self.calls.append(("wait_for_timeout", timeout))
        if self.error is not None:
            raise self.error

    def goto(self, url):
        self.calls.append(("goto", url))

    def go_back(self):
        self.calls.append(("go_back",))


class StubBrowserEnv(BrowserEnv):
    """BrowserEnv that records pre_step/post_step calls instead of driving a browser."""

    def __init__(self, page=None):
        self.page = page if page is not None else FakePage()
        self.last_action = ""
        self.last_action_error = ""
        self.messages = []
        self.infeasible_reasons = []
        self.calls = []

    def pre_step(self):
        self.calls.append(("pre_step", self.last_action))

        def send_message_to_user(text):
            if not isinstance(text, str):
                raise ValueError(f"Forbidden value: {text} is not a string")
            self.messages.append(text)

        def report_infeasible_instructions(reason):
            self.infeasible_reasons.append(reason)

        return {"action_exec_timeout": 0}, send_message_to_user, report_infeasible_instructions

    def post_step(self, info, validate=True):
        self.calls.append(("post_step", dict(info), validate))
        return "post_step_result"


@pytest.fixture
def load_server(monkeypatch):
    """Import mcp_server with a controlled sys.argv (it parses CLI args at import time)."""

    # fn_wrapper overwrites these module globals; restore them after each test
    for name in ("page", "send_message_to_user", "report_infeasible_instructions", "demo_mode"):
        monkeypatch.setattr(fn_context, name, getattr(fn_context, name))

    def _load(*cli_args):
        monkeypatch.setattr(sys, "argv", ["mcp_server.py", *cli_args])
        sys.modules.pop(MCP_SERVER_MODULE, None)
        return importlib.import_module(MCP_SERVER_MODULE)

    yield _load
    sys.modules.pop(MCP_SERVER_MODULE, None)


@pytest.fixture
def server(load_server):
    return load_server()


def attach_env(monkeypatch, server_module, env):
    context = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=SimpleNamespace(gym=env))
    )
    monkeypatch.setattr(server_module.mcp, "get_context", lambda: context)


def post_step_calls(env):
    return [call for call in env.calls if call[0] == "post_step"]


@pytest.mark.parametrize(
    "args,kwargs,expected",
    [
        ((), {}, "noop()"),
        (("a12",), {}, "noop('a12')"),
        (("a12", 3, True), {}, "noop('a12', 3, True)"),
        ((), {"bid": "a12"}, "noop(bid='a12')"),
        ((), {"bid": "a12", "button": "right"}, "noop(bid='a12', button='right')"),
        (("a12",), {"button": "right"}, "noop('a12', button='right')"),
        (('say "hi"',), {}, "noop('say \"hi\"')"),
        (("it's",), {"text": "a'b\"c"}, "noop(\"it's\", text='a\\'b\"c')"),
        (("line1\nline2",), {}, "noop('line1\\nline2')"),
        ((None, 0.5, ["x"]), {"keys": ("a", "b")}, "noop(None, 0.5, ['x'], keys=('a', 'b'))"),
    ],
)
def test_format_func_call(server, args, kwargs, expected):
    assert server.format_func_call(fn_context.noop, args, kwargs) == expected


def test_format_func_call_uses_function_name(server):
    assert server.format_func_call(fn_context.click, ("12",), {}) == "click('12')"


def test_cli_args_build_config(load_server):
    server = load_server(
        "--task_id",
        "browsergym/openended",
        "--headless",
        "--timeout_ms",
        "2500",
        "--demo_mode",
        "all_blue",
        "--subset",
        "bid",
        "--validate_actions",
        "click",
        "fill",
        "--some_unknown_flag",
    )
    assert server.task_id == "browsergym/openended"
    assert server.args.subset == "bid"
    assert server.config == server.BgymConfig(
        headless=True,
        timeout_ms=2500,
        record_video_dir=None,
        demo_mode="all_blue",
        validate_actions=["click", "fill"],
    )


def test_cli_args_defaults(server):
    assert server.args.subset == "workarena++"
    assert server.config.headless is False
    assert server.config.timeout_ms == 10000
    assert server.config.demo_mode == "off"
    assert server.config.validate_actions == ["click", "goto"]


@pytest.mark.parametrize("wrapper_layers", [0, 1, 2])
def test_fn_wrapper_success(monkeypatch, server, wrapper_layers):
    env = StubBrowserEnv()
    stack = env
    for _ in range(wrapper_layers):
        stack = gym.Wrapper(stack)
    attach_env(monkeypatch, server, stack)

    tool = server.fn_wrapper(fn_context.noop, validate=False)
    result = run_async(tool(250))

    assert result == "post_step_result"
    assert env.last_action == "noop(250)"
    assert env.last_action_error == ""
    assert env.page.calls == [("wait_for_timeout", 250)]
    # last_action is recorded before pre_step; post_step gets pre_step's info untouched
    assert env.calls == [
        ("pre_step", "noop(250)"),
        ("post_step", {"action_exec_timeout": 0}, False),
    ]


def test_fn_wrapper_injects_gym_state_into_action_module(monkeypatch, load_server):
    server = load_server("--demo_mode", "all_blue")
    env = StubBrowserEnv()
    attach_env(monkeypatch, server, gym.Wrapper(gym.Wrapper(env)))

    run_async(server.fn_wrapper(fn_context.send_msg_to_user)(text="hello"))

    assert env.messages == ["hello"]
    assert env.last_action == "send_msg_to_user(text='hello')"
    assert env.last_action_error == ""
    assert fn_context.page is env.page
    assert fn_context.demo_mode == "all_blue"

    run_async(server.fn_wrapper(fn_context.report_infeasible)("no such field"))
    assert env.infeasible_reasons == ["no such field"]
    assert env.last_action == "report_infeasible('no such field')"

    # a new page on the env must be picked up by the next call, not a stale one
    env.page = FakePage()
    run_async(server.fn_wrapper(fn_context.noop)(10))
    assert fn_context.page is env.page
    assert env.page.calls == [("wait_for_timeout", 10)]


def test_fn_wrapper_resolves_function_from_action_module(monkeypatch, server):
    env = StubBrowserEnv()
    attach_env(monkeypatch, server, env)
    called_with = []

    def noop(wait_ms=1000):
        called_with.append(wait_ms)

    original_noop = fn_context.noop
    # the tool executes the function currently defined in the action module, by name
    monkeypatch.setattr(fn_context, "noop", noop)
    run_async(server.fn_wrapper(original_noop)(5))
    assert called_with == [5]
    assert env.last_action == "noop(5)"


def test_fn_wrapper_captures_errors(monkeypatch, server):
    env = StubBrowserEnv()
    attach_env(monkeypatch, server, env)

    result = run_async(server.fn_wrapper(fn_context.send_msg_to_user)(42))

    assert result == "post_step_result"
    assert env.last_action == "send_msg_to_user(42)"
    assert env.last_action_error == "ValueError: Forbidden value: 42 is not a string"
    assert post_step_calls(env) == [("post_step", {"action_exec_timeout": 0}, True)]


def test_fn_wrapper_clears_previous_error_on_success(monkeypatch, server):
    env = StubBrowserEnv()
    attach_env(monkeypatch, server, env)

    run_async(server.fn_wrapper(fn_context.send_msg_to_user)(42))
    assert env.last_action_error.startswith("ValueError: ")

    run_async(server.fn_wrapper(fn_context.send_msg_to_user)("ok"))
    assert env.last_action_error == ""


@pytest.mark.parametrize(
    "error,expected_timeout",
    [
        (playwright.sync_api.TimeoutError("Timeout 500ms exceeded."), 0.5),
        (
            playwright.sync_api.TimeoutError(
                "Timeout 30000ms exceeded.\n=========================== logs ==========="
            ),
            30.0,
        ),
        (TimeoutError("Timeout 1500ms exceeded."), 1.5),
    ],
)
def test_fn_wrapper_timeout_sets_action_exec_timeout(monkeypatch, server, error, expected_timeout):
    env = StubBrowserEnv(page=FakePage(error=error))
    attach_env(monkeypatch, server, gym.Wrapper(env))

    run_async(server.fn_wrapper(fn_context.noop)(100))

    assert env.last_action_error == f"TimeoutError: {error}"
    [(_, info, _)] = post_step_calls(env)
    assert info["action_exec_timeout"] == expected_timeout


@pytest.mark.parametrize(
    "error",
    [
        playwright.sync_api.Error("Timeout 500ms exceeded."),
        playwright.sync_api.TimeoutError("Navigation timed out"),
        ValueError("TimeoutError: Timeout 500ms exceeded."),
    ],
)
def test_fn_wrapper_non_timeout_errors_leave_timeout_untouched(monkeypatch, server, error):
    env = StubBrowserEnv(page=FakePage(error=error))
    attach_env(monkeypatch, server, env)

    run_async(server.fn_wrapper(fn_context.noop)(100))

    assert env.last_action_error == f"{type(error).__name__}: {error}"
    [(_, info, _)] = post_step_calls(env)
    assert info["action_exec_timeout"] == 0


def test_fn_wrapper_preserves_metadata(server):
    tool = server.fn_wrapper(fn_context.click)
    assert tool.__name__ == "click"
    assert tool.__doc__ == fn_context.click.__doc__
    assert tool.__wrapped__ is fn_context.click


def registered_tools(server):
    return {tool.name: tool for tool in run_async(server.mcp.list_tools())}


@pytest.mark.parametrize("subset", ["workarena++", "bid", "chat"])
def test_registered_tools_match_action_subset(load_server, subset):
    server = load_server("--subset", subset)
    tools = registered_tools(server)

    expected = {fn.__name__: fn for fn in ACTION_SUBSETS[subset]}
    assert set(tools) == set(expected)
    for name, fn in expected.items():
        assert tools[name].description == fn.__doc__
        # the tool schema comes from the wrapped action's signature, not *args/**kwargs
        params = set(tools[name].inputSchema.get("properties", {}))
        assert params == set(fn.__code__.co_varnames[: fn.__code__.co_argcount])


def call_tool_validate_flag(monkeypatch, server, name, arguments):
    env = StubBrowserEnv()
    attach_env(monkeypatch, server, gym.Wrapper(gym.Wrapper(env)))
    run_async(server.mcp.call_tool(name, arguments))
    [(_, _, validate)] = post_step_calls(env)
    return env, validate


def test_registered_tools_use_default_validate_actions(monkeypatch, server):
    env, validate = call_tool_validate_flag(monkeypatch, server, "goto", {"url": "about:blank"})
    assert validate is True
    assert env.last_action == "goto(url='about:blank')"
    assert env.page.calls == [("goto", "about:blank")]

    env, validate = call_tool_validate_flag(monkeypatch, server, "go_back", {})
    assert validate is False
    assert env.last_action == "go_back()"
    assert env.page.calls == [("go_back",)]

    # click is validated even when it fails on the (fake) page
    env, validate = call_tool_validate_flag(monkeypatch, server, "click", {"bid": "12"})
    assert validate is True
    # FastMCP may pass defaulted parameters explicitly
    assert env.last_action.startswith("click(bid='12'")
    assert env.last_action_error != ""


def test_registered_tools_use_cli_validate_actions(monkeypatch, load_server):
    server = load_server("--validate_actions", "go_back", "send_msg_to_user")

    _, validate = call_tool_validate_flag(monkeypatch, server, "go_back", {})
    assert validate is True
    _, validate = call_tool_validate_flag(monkeypatch, server, "goto", {"url": "about:blank"})
    assert validate is False
    env, validate = call_tool_validate_flag(
        monkeypatch, server, "send_msg_to_user", {"text": "done"}
    )
    assert validate is True
    assert env.messages == ["done"]
