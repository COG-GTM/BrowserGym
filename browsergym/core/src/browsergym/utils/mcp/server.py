"""BrowserGym MCP server built on the official ``mcp`` Python SDK (FastMCP)."""

import asyncio
import base64
import inspect
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Callable, Optional, Sequence

import anyio

try:
    from mcp.server.fastmcp import Context, FastMCP
except ModuleNotFoundError as e:  # mcp not installed, or mcp>=2 where FastMCP was renamed
    raise ModuleNotFoundError(
        "The BrowserGym MCP server needs the FastMCP API of the mcp SDK (mcp>=1.25,<2). "
        'Install it with: pip install "browsergym-core[mcp]"'
    ) from e
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import Field

from browsergym.core.action.highlevel import HighLevelActionSet

from .config import ServerConfig
from .models import BrowserObservation
from .session import (
    BrowserSession,
    SessionScope,
    acquire_browser_worker,
    release_browser_worker,
    run_in_browser_thread,
    shutdown_browser_worker,
)

logger = logging.getLogger(__name__)

ToolResult = Annotated[CallToolResult, BrowserObservation]

INSTRUCTIONS = """\
Controls a Chromium browser through BrowserGym. Every tool returns the resulting observation: the
active page URL/title, the accessibility tree (AXTree) where interactive elements are tagged with
their BrowserGym id in square brackets, e.g. [12] button 'Submit', the last action error (if any),
and a screenshot. Pass those ids as `bid` to element actions (click, fill, select_option, ...).
Call `reset` to start over (optionally on another task / start_url) and `close_browser` when done.
"""

MAX_CHAT_IN_TEXT = 5


def format_action(name: str, arguments: dict[str, Any]) -> str:
    """Render a BrowserGym high-level action string, e.g. ``fill('12', 'hello')``."""
    args = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    return f"{name}({args})"


def render_text(obs: BrowserObservation) -> str:
    lines = [f"Step {obs.step}" + (f" | action: {obs.action}" if obs.action else "")]
    lines.append(f"URL: {obs.url}")
    if obs.title:
        lines.append(f"Title: {obs.title}")
    if len(obs.open_pages) > 1:
        tabs = ", ".join(
            f"{'*' if i == obs.active_page_index else ''}{i}: {p.title or p.url}"
            for i, p in enumerate(obs.open_pages)
        )
        lines.append(f"Tabs: {tabs}")
    if obs.goal:
        lines.append(f"Goal: {obs.goal}")
    if obs.last_action_error:
        lines.append(f"Last action error: {obs.last_action_error}")
    if obs.terminated or obs.truncated or obs.reward:
        lines.append(
            f"Reward: {obs.reward} | terminated: {obs.terminated} | truncated: {obs.truncated}"
        )
    if obs.chat_messages:
        lines.append("Chat (latest):")
        lines.extend(f"  {m.role}: {m.message}" for m in obs.chat_messages[-MAX_CHAT_IN_TEXT:])
    lines.append("")
    lines.append("AXTree:")
    lines.append(obs.axtree)
    return "\n".join(lines)


def to_tool_result(obs: BrowserObservation, png: Optional[bytes]) -> CallToolResult:
    content: list[Any] = [TextContent(type="text", text=render_text(obs))]
    if png:
        content.append(
            ImageContent(type="image", data=base64.b64encode(png).decode(), mimeType="image/png")
        )
    return CallToolResult(
        content=content,
        structuredContent=obs.model_dump(mode="json"),
        isError=bool(obs.last_action_error),
    )


async def _session(ctx: Context) -> BrowserSession:
    scope: SessionScope = ctx.request_context.lifespan_context
    return await scope.get(id(ctx.session))


async def _run(session: BrowserSession, fn: Callable[..., BrowserObservation], *args, **kwargs):
    def _call():
        obs = fn(*args, **kwargs)
        png = session.screenshot_png_sync() if session.config.screenshots else None
        return obs, png

    obs, png = await run_in_browser_thread(_call)
    return to_tool_result(obs, png)


def _make_action_tool(action_name: str, signature: inspect.Signature):
    async def tool(ctx: Context, **kwargs) -> ToolResult:
        session = await _session(ctx)
        action = format_action(action_name, kwargs)
        return await _run(session, session.step_sync, action)

    ctx_param = inspect.Parameter("ctx", inspect.Parameter.KEYWORD_ONLY, annotation=Context)
    params = [p.replace(kind=inspect.Parameter.KEYWORD_ONLY) for p in signature.parameters.values()]
    tool.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=[*params, ctx_param], return_annotation=ToolResult
    )
    tool.__annotations__ = {
        **{p.name: p.annotation for p in params if p.annotation is not inspect.Parameter.empty},
        "ctx": Context,
        "return": ToolResult,
    }
    tool.__name__ = action_name
    tool.__qualname__ = action_name
    return tool


# actions that read arbitrary files from the server host
UPLOAD_ACTIONS = frozenset({"upload_file", "mouse_upload_file"})


def action_tools(
    subsets: Sequence[str], allow_upload_file: bool = False
) -> list[tuple[str, Callable, str]]:
    """(name, tool fn, description) for every action of the configured BrowserGym action set."""
    import browsergym.core.action.functions as functions

    action_set = HighLevelActionSet(subsets=list(subsets))
    tools = []
    for name, action in action_set.action_set.items():
        if name in UPLOAD_ACTIONS and not allow_upload_file:
            # reads arbitrary files from the server host: opt-in only
            continue
        fn = getattr(functions, name)
        description = inspect.cleandoc(fn.__doc__ or action.description)
        tools.append((name, _make_action_tool(name, inspect.signature(fn)), description))
    return tools


def create_server(config: Optional[ServerConfig] = None) -> FastMCP:
    config = config or ServerConfig()

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[SessionScope]:
        scope = SessionScope(config)
        acquire_browser_worker()
        try:
            yield scope
        finally:
            # shielded: this also runs while the transport is being cancelled (Ctrl-C, client gone)
            with anyio.CancelScope(shield=True):
                try:
                    await scope.close_all()
                finally:
                    await anyio.to_thread.run_sync(release_browser_worker)

    mcp = FastMCP(
        "BrowserGym",
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
        host=config.host,
        port=config.port,
        streamable_http_path=config.path,
        log_level=config.log_level,
    )

    for name, fn, description in action_tools(config.subsets, config.allow_upload_file):
        mcp.add_tool(
            fn,
            name=name,
            description=description,
            annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True),
            structured_output=True,
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    async def get_observation(ctx: Context) -> ToolResult:
        """Return the current browser observation (URL, AXTree, screenshot) without acting.
        Starts the browser on the configured task if it is not running yet."""
        session = await _session(ctx)
        return await _run(session, session.observe_sync)

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    async def reset(
        ctx: Context,
        task_id: Annotated[
            Optional[str],
            Field(
                description="BrowserGym task id, e.g. browsergym/openended (server default if omitted)"
            ),
        ] = None,
        start_url: Annotated[
            Optional[str], Field(description="Start URL (open-ended task only)")
        ] = None,
        goal: Annotated[
            Optional[str], Field(description="Goal text (open-ended task only)")
        ] = None,
        seed: Annotated[Optional[int], Field(description="Random seed for the task")] = None,
    ) -> ToolResult:
        """(Re)start this session's browser on a task and return the first observation."""
        session = await _session(ctx)
        return await _run(
            session, session.reset_sync, task_id=task_id, start_url=start_url, goal=goal, seed=seed
        )

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
    async def close_browser(ctx: Context) -> str:
        """Close this session's browser and free its resources. Any later tool call starts a new one."""
        scope: SessionScope = ctx.request_context.lifespan_context
        closed = await scope.close(id(ctx.session))
        return "Browser closed." if closed else "No browser was running."

    return mcp


def main(argv: Optional[Sequence[str]] = None) -> None:
    config = ServerConfig.from_args(argv)
    logging.basicConfig(level=config.log_level)
    if config.transport == "streamable-http" and config.host not in (
        "127.0.0.1",
        "localhost",
        "::1",
    ):
        logger.warning(
            "Streamable HTTP is bound to %s without authentication: any client that can reach it "
            "controls the browser. Only expose it on trusted networks.",
            config.host,
        )
    server = create_server(config)
    try:
        server.run(transport=config.transport)
    except (KeyboardInterrupt, asyncio.CancelledError):
        # uvicorn re-raises SIGINT/SIGTERM after its graceful shutdown; sessions are closed by then
        logger.info("BrowserGym MCP server stopped")
    finally:
        shutdown_browser_worker()
