"""BrowserGym MCP server (Model Context Protocol).

Exposes the BrowserGym high-level action set as typed MCP tools over stdio or Streamable HTTP.
Requires the ``mcp`` extra: ``pip install "browsergym-core[mcp]"``.
"""

from .config import ServerConfig
from .models import BrowserObservation, ChatMessage, PageInfo

__all__ = [
    "BrowserObservation",
    "ChatMessage",
    "PageInfo",
    "ServerConfig",
    "create_server",
    "main",
]


def __getattr__(name: str):
    # lazy: keeps `import browsergym.utils.mcp` cheap and mcp-SDK-free until a server is needed
    if name in ("create_server", "main"):
        from . import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
