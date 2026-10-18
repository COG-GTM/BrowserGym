import http.server
import threading
import time

import pytest

from browsergym.webarena.instance import WebArenaInstance


class _ResetServer:
    """Local stand-in for the WebArena reset server, with configurable hangs."""

    def __init__(self, reset_hang=0.0, status_hangs=0, hang_seconds=5.0):
        self.reset_hang = reset_hang
        self.status_hangs = status_hangs
        self.hang_seconds = hang_seconds
        self.status_calls = 0
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, body):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/reset":
                    time.sleep(server.reset_hang)
                    self._reply(b"Reset started")
                elif self.path == "/status":
                    server.status_calls += 1
                    if server.status_hangs < 0 or server.status_calls <= server.status_hangs:
                        time.sleep(server.hang_seconds)
                        return
                    self._reply(b"Ready for duty!")

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def instance(monkeypatch):
    monkeypatch.setattr(WebArenaInstance, "RESET_REQUEST_TIMEOUT", 0.5)
    monkeypatch.setattr(WebArenaInstance, "RESET_STATUS_INTERVAL", 0.2)
    monkeypatch.setattr(WebArenaInstance, "RESET_MAX_DURATION", 1.0)
    # bypass __init__, which requires a live WebArena deployment
    instance = WebArenaInstance.__new__(WebArenaInstance)
    instance.urls = {}
    return instance


@pytest.fixture
def make_server(monkeypatch):
    servers = []

    def _make(**kwargs):
        server = _ResetServer(**kwargs)
        servers.append(server)
        monkeypatch.setenv(WebArenaInstance.RESET_URL_VAR, server.url)
        return server

    yield _make
    for server in servers:
        server.close()


def test_full_reset_completes(instance, make_server):
    server = make_server()
    instance.full_reset()
    assert server.status_calls == 1


def test_full_reset_hanging_reset_request_times_out(instance, make_server):
    make_server(reset_hang=5.0)
    start = time.time()
    with pytest.raises(RuntimeError, match="reset request"):
        instance.full_reset()
    assert time.time() - start < 3.0


def test_full_reset_hanging_status_request_is_retried(instance, make_server):
    server = make_server(status_hangs=2, hang_seconds=1.0)
    instance.full_reset()
    assert server.status_calls == 3


def test_full_reset_hanging_status_honors_max_duration(instance, make_server):
    make_server(status_hangs=-1, hang_seconds=5.0)
    start = time.time()
    with pytest.raises(Exception, match="Reset still running"):
        instance.full_reset()
    assert time.time() - start < 3.0
