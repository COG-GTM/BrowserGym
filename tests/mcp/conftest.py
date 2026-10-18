import functools
import http.server
import pathlib
import socket
import threading

import pytest

pytest.importorskip(
    "mcp.server.fastmcp", reason="needs the mcp extra: pip install browsergym-core[mcp]"
)

DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def static_site():
    """Serve tests/mcp/data on a local HTTP port; yields the base URL."""
    handler = functools.partial(
        type(
            "QuietHandler",
            (http.server.SimpleHTTPRequestHandler,),
            {"log_message": lambda *a: None},
        ),
        directory=str(DATA_DIR),
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
