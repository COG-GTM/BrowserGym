"""Tiny threaded static file server bound to localhost for offline benchmarks."""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - signature from base class
        pass


class StaticServer:
    """Serve ``directory`` on ``127.0.0.1`` (ephemeral port by default).

    Usable as a context manager; ``url(name)`` returns the URL of a served file.
    """

    def __init__(self, directory: Path, port: int = 0):
        handler = functools.partial(_QuietHandler, directory=str(directory))
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def url(self, name: str = "") -> str:
        return f"http://127.0.0.1:{self.port}/{name}"

    def start(self) -> "StaticServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> "StaticServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
