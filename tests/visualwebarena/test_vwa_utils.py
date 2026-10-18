import io
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

import PIL.Image
import pytest
import requests

from browsergym.visualwebarena import utils


@pytest.fixture
def stalled_server():
    # accepts connections but never sends a response
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    conns = []
    stop = threading.Event()

    def accept():
        sock.settimeout(0.1)
        while not stop.is_set():
            try:
                conns.append(sock.accept()[0])
            except socket.timeout:
                pass

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{sock.getsockname()[1]}/image.png"
    stop.set()
    thread.join()
    for conn in conns:
        conn.close()
    sock.close()


@pytest.fixture
def dripping_server():
    # advertises a large body and keeps sending one byte at a time, never finishing
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(10**9))
            self.end_headers()
            try:
                while not stop.is_set():
                    self.wfile.write(b"\0")
                    self.wfile.flush()
                    time.sleep(0.1)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/image.png"
    stop.set()
    server.shutdown()
    server.server_close()


@pytest.fixture
def image_server():
    buffer = io.BytesIO()
    PIL.Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    payload = buffer.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/image.png":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/image.png"
    server.shutdown()
    server.server_close()


def test_image_download_has_timeout():
    connect_timeout, read_timeout = utils.IMAGE_DOWNLOAD_TIMEOUT
    assert connect_timeout > 0 and read_timeout > 0


def test_image_download_times_out_on_stalled_server(stalled_server, monkeypatch):
    monkeypatch.setattr(utils, "IMAGE_DOWNLOAD_TIMEOUT", (1, 1))
    start = time.monotonic()
    with pytest.raises(requests.exceptions.Timeout):
        utils.image_url_to_pil_image(stalled_server)
    assert time.monotonic() - start < 10


def test_image_download_enforces_deadline_on_dripping_server(dripping_server, monkeypatch):
    monkeypatch.setattr(utils, "IMAGE_DOWNLOAD_TIMEOUT", (1, 1))
    monkeypatch.setattr(utils, "IMAGE_DOWNLOAD_DEADLINE", 2)
    start = time.monotonic()
    with pytest.raises(requests.exceptions.Timeout):
        utils.image_url_to_pil_image(dripping_server)
    assert time.monotonic() - start < 10


def test_image_download_raises_on_http_error(image_server):
    with pytest.raises(ValueError, match="status code 404"):
        utils.image_url_to_pil_image(image_server.replace("/image.png", "/missing.png"))


def test_image_download_succeeds(image_server):
    image = utils.image_url_to_pil_image(image_server)
    assert image.format == "PNG"
    assert image.size == (4, 4)
