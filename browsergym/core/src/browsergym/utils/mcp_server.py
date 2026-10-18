"""BrowserGym MCP server entry point (kept for backwards compatibility).

    python -m browsergym.utils.mcp_server [--transport streamable-http] [options]
    mcp dev browsergym/core/src/browsergym/utils/mcp_server.py

The implementation lives in :mod:`browsergym.utils.mcp`.
"""

from browsergym.utils.mcp.config import ServerConfig
from browsergym.utils.mcp.server import create_server, main

__all__ = ["ServerConfig", "create_server", "main", "mcp"]


def __getattr__(name: str):
    # `mcp dev` / `mcp run` look up a module-level server object called `mcp`
    if name == "mcp":
        global mcp
        mcp = create_server(ServerConfig.from_args(known_only=True))
        return mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    main()
