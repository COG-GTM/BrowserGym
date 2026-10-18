# BrowserGym MCP server

`browsergym.utils.mcp` exposes a BrowserGym browser environment as a
[Model Context Protocol](https://modelcontextprotocol.io) server, so any MCP client
(Claude Desktop, Devin, the Side runner, custom agents) can drive a real Chromium page with
the BrowserGym action set and read back BrowserGym observations.

It is built on the official `mcp` Python SDK (`FastMCP`, `mcp>=1.25,<2`) and supports the
**stdio** and **Streamable HTTP** transports. Everything runs locally and offline; no API keys
are needed.

## Install

```bash
pip install "browsergym-core[mcp]"     # or, from a checkout: pip install -e "browsergym/core[mcp]"
playwright install chromium
```

> The server uses the `FastMCP` API of the 1.x SDK. `mcp` 2.x removed `mcp.server.fastmcp`,
> which is why the extra pins `mcp[cli]>=1.25,<2`.

## Run

```bash
# stdio (default) - what desktop MCP clients launch
python -m browsergym.utils.mcp --start-url https://example.com

# Streamable HTTP on http://127.0.0.1:8931/mcp
python -m browsergym.utils.mcp --transport streamable-http --port 8931

# The legacy entry point still works and accepts the same flags
python -m browsergym.utils.mcp_server --task_id browsergym/openended --start-url https://example.com
```

Useful flags (`python -m browsergym.utils.mcp --help` for all):

| Flag | Default | Meaning |
| --- | --- | --- |
| `-t/--task-id` | `browsergym/openended` | Any registered BrowserGym gym id (e.g. `browsergym/miniwob.click-test`). |
| `--start-url`, `--goal` | `about:blank`, empty | Start page and goal for the open-ended task. |
| `--subset` | `chat,infeas,bid,nav,tab` | Action subsets to expose as tools (repeatable or comma-separated; e.g. `coord`, `webarena`). |
| `--headless/--no-headless` | headless | Show the browser window. |
| `--screenshots/--no-screenshots` | on | Attach a PNG screenshot to every tool result. |
| `--allow-upload-file` | off | Expose `upload_file` / `mouse_upload_file` (reads files from the server host; keep off for remote clients). |
| `--max-axtree-chars` | unlimited | Truncate the AXTree text in results. |
| `--demo-mode` | `off` | BrowserGym demo mode (visual cursor/highlights). |
| `-r/--record-video-dir` | none | Record a Playwright video per session. |
| `--transport` | `stdio` | `stdio` or `streamable-http`. |
| `--host/--port/--path` | `127.0.0.1`/`8931`/`/mcp` | Streamable HTTP bind address and endpoint path. |

## Tools

Action tools are generated from BrowserGym's `HighLevelActionSet` for the selected subsets, with
typed JSON schemas derived from the action function signatures. With the default subsets:

| Tool | BrowserGym action |
| --- | --- |
| `goto(url)`, `go_back()`, `go_forward()` | navigation (`nav`) |
| `click(bid, button?, modifiers?)`, `dblclick`, `hover(bid)`, `fill(bid, value)`, `select_option(bid, options)`, `press(bid, key_comb)`, `focus`, `clear`, `drag_and_drop`, `scroll(delta_x, delta_y)`, `upload_file` (only with `--allow-upload-file`) | element actions (`bid`) |
| `new_tab()`, `tab_focus(index)`, `tab_close()` | tabs (`tab`) |
| `send_msg_to_user(text)` | chat (`chat`) |
| `report_infeasible(reason)` | infeasible (`infeas`) |
| `noop(wait_ms?)` | wait |

Plus lifecycle tools:

| Tool | Purpose |
| --- | --- |
| `reset(task_id?, start_url?, goal?, seed?)` | (Re)start this session's environment; returns the first observation. |
| `get_observation()` | Current observation without acting (read-only). |
| `close_browser()` | Close this session's browser. The next call lazily relaunches it. |

`bid`s are the `[N]` ids shown in the AXTree text.

### Tool results

Every action tool, `reset` and `get_observation` return:

* `structuredContent` - a `BrowserObservation` object (schema advertised as the tool's
  `outputSchema`): `action`, `url`, `title`, `open_pages[]`, `active_page_index`, `axtree`,
  `focused_element_bid`, `last_action_error`, `goal`, `chat_messages[]`, `reward`, `terminated`,
  `truncated`, `step`, `task_id`.
* `content[0]` - a text block with URL, title, error, chat and the AXTree text.
* `content[1]` - the page screenshot as MCP image content (`image/png`), unless
  `--no-screenshots`.
* `isError: true` when the action failed (`last_action_error` is non-empty). The observation
  is still returned so the agent can recover.

## Lifecycle

* **Per-session environments.** Each MCP session (one stdio connection, or one
  `Mcp-Session-Id` over Streamable HTTP) gets its own `BrowserEnv`, created lazily on the first
  tool call. Sessions never share pages.
* **Graceful shutdown.** `close_browser` closes the session's env; when the server stops
  (stdin closed, SIGINT/SIGTERM) the FastMCP lifespan closes every remaining env and, once the
  last server run ends, stops the shared Playwright instance (also when served via `mcp run`).
  A failed `reset` discards the half-started env, so the next call starts cleanly. Playwright's sync API is driven from a single dedicated worker
  thread, so the asyncio event loop is never blocked by the browser.

## Client configuration

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "browsergym": {
      "command": "python",
      "args": [
        "-m", "browsergym.utils.mcp",
        "--start-url", "https://example.com",
        "--no-headless"
      ]
    }
  }
}
```

Use the absolute path of the virtualenv's `python` if it is not on Claude Desktop's `PATH`.
To connect Claude Desktop to an already-running Streamable HTTP server instead, use a
remote-server bridge such as `"command": "npx", "args": ["-y", "mcp-remote", "http://127.0.0.1:8931/mcp"]`.

### Devin

In Devin: **Settings -> MCP Marketplace -> Add your own** (custom MCP server).

STDIO (runs inside Devin's machine, which needs `browsergym-core[mcp]` and
`playwright install chromium` in its environment):

```json
{
  "command": "python",
  "args": ["-m", "browsergym.utils.mcp", "--start-url", "https://example.com"],
  "env": {}
}
```

Streamable HTTP (server reachable from Devin):

```json
{
  "transport": "streamable-http",
  "url": "http://<host>:8931/mcp",
  "headers": {}
}
```

Start the HTTP server with `--host 0.0.0.0` when it must be reachable from another machine; it
has no authentication, so only expose it on trusted networks or behind an authenticating proxy.

### Python MCP client

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("http://127.0.0.1:8931/mcp") as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        obs = await session.call_tool("reset", {"start_url": "https://example.com"})
        print(obs.structuredContent["url"], obs.structuredContent["axtree"][:200])
        await session.call_tool("click", {"bid": "12"})
```

## Verified transcript (Streamable HTTP)

Server: `python -m browsergym.utils.mcp --transport streamable-http --port 8931`; page: the
static fixture `tests/mcp/data/form.html` served with `python -m http.server 8765`; client:
`mcp.client.streamable_http.streamable_http_client` + `ClientSession` (mcp 1.30.0).

```text
>>> initialize -> server=BrowserGym protocol=2025-11-25 session=9a7e4113a1a142c78569a215babc3a91
>>> tools/list -> 22 tools: noop, send_msg_to_user, report_infeasible, scroll, fill, select_option, click, dblclick, hover, press, focus, clear, drag_and_drop, go_back, go_forward, goto, tab_close, tab_focus, new_tab, get_observation, reset, close_browser

>>> tools/call reset {"start_url": "http://127.0.0.1:8765/form.html", "goal": "Order a large for Alice"}
    isError=False content=['text', 'image']
    structured: {"action": null, "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 0}
    axtree (first lines):
      RootWebArea 'MCP Test Form', focused
      	[4] heading 'Order form'
      	[5] LabelText ''
      		StaticText 'Name'
      	[6] textbox 'Name'
      	[7] LabelText ''
      		StaticText 'Size'
      	[8] combobox 'Size' value='Small', hasPopup='menu', expanded=False
      		[9] option 'Small', selected=True
      		[10] option 'Medium', selected=False
      		[11] option 'Large', selected=False
      	[12] button 'Submit'

>>> tools/call fill {"bid": "6", "value": "Alice"}
    isError=False content=['text', 'image']
    structured: {"action": "fill(bid='6', value='Alice', enable_autocomplete_menu=False)", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 1}

>>> tools/call select_option {"bid": "8", "options": "Large"}
    isError=False content=['text', 'image']
    structured: {"action": "select_option(bid='8', options='Large')", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 2}

>>> tools/call click {"bid": "12"}
    isError=False content=['text', 'image']
    structured: {"action": "click(bid='12', button='left', modifiers=[])", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 3}
    axtree contains 'Ordered l for Alice': True

>>> tools/call hover {"bid": "13"}
    isError=False content=['text', 'image']
    structured: {"action": "hover(bid='13')", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 4}

>>> tools/call press {"bid": "16", "key_comb": "Enter"}
    isError=False content=['text', 'image']
    structured: {"action": "press(bid='16', key_comb='Enter')", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 5}

>>> tools/call scroll {"delta_x": 0, "delta_y": 800}
    isError=False content=['text', 'image']
    structured: {"action": "scroll(delta_x=0.0, delta_y=800.0)", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 6}

>>> tools/call click {"bid": "does-not-exist"}
    isError=True content=['text', 'image']
    structured: {"action": "click(bid='does-not-exist', button='left', modifiers=[])", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "ValueError: Could not find element with bid \"does-not-exist\"", "step": 7}

>>> tools/call send_msg_to_user {"text": "Order placed for Alice (Large)."}
    isError=False content=['text', 'image']
    structured: {"action": "send_msg_to_user(text='Order placed for Alice (Large).')", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 8}

>>> tools/call goto {"url": "http://127.0.0.1:8765/second.html"}
    isError=False content=['text', 'image']
    structured: {"action": "goto(url='http://127.0.0.1:8765/second.html')", "url": "http://127.0.0.1:8765/second.html", "title": "Second Page", "last_action_error": "", "step": 9}

>>> tools/call go_back {}
    isError=False content=['text', 'image']
    structured: {"action": "go_back()", "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 10}

>>> tools/call get_observation {}
    isError=False content=['text', 'image']
    structured: {"action": null, "url": "http://127.0.0.1:8765/form.html", "title": "MCP Test Form", "last_action_error": "", "step": 10}
    chat: {"role": "assistant", "message": "Order placed for Alice (Large).", "timestamp": 1792291722.5307686}

>>> tools/call close_browser {}
    isError=False content=['text']
    text: Browser closed.
```

Server shutdown after SIGINT:

```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:mcp.server.streamable_http_manager:StreamableHTTP session manager shutting down
INFO:     Application shutdown complete.
INFO:     Finished server process
```

## Tests

```bash
pip install -e "browsergym/core[mcp]" pytest anyio && playwright install chromium
pytest tests/mcp -v
```

The tests serve `tests/mcp/data` from a local HTTP server and drive the server through the MCP
client: in-process (tool schemas, form flow, error reporting, lazy start/close, session
isolation) and as subprocesses over Streamable HTTP and stdio.
