import http.server
import threading
import time

import playwright.sync_api
import pytest

from browsergym.webarena.instance import WebArenaInstance

LOGIN_FORM = b"""
<html><body>
<form method="post" action="/login">
  <label for="u">Username</label><input id="u" name="username">
  <label for="p">Password</label><input id="p" name="password" type="password">
  <button type="submit">Sign in</button>
</form>
</body></html>
"""


class FakeAdminSite(http.server.BaseHTTPRequestHandler):
    login_form = LOGIN_FORM
    login_delay = 0.5  # seconds, simulates a slow site after a reset

    def do_GET(self):
        body = b"<html><body>Dashboard</body></html>" if self.path == "/dashboard" else None
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body or self.login_form)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        time.sleep(self.login_delay)
        self.send_response(302)
        self.send_header("Location", "/dashboard")
        self.send_header("Set-Cookie", "session=ok; Path=/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def site_url(request):
    handler = type("Handler", (FakeAdminSite,), getattr(request, "param", {}))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def make_instance(url):
    # bypass __init__, which requires a live WebArena deployment
    instance = WebArenaInstance.__new__(WebArenaInstance)
    instance.urls = {"shopping_admin": url}
    instance.credentials = {"shopping_admin": {"username": "admin", "password": "secret"}}
    return instance


def test_ui_login_waits_for_login_and_closes_tab(page: playwright.sync_api.Page, site_url):
    make_instance(site_url).ui_login(site="shopping_admin", page=page)

    assert page.context.pages == [page]
    cookies = {c["name"]: c["value"] for c in page.context.cookies(site_url)}
    assert cookies.get("session") == "ok"


@pytest.mark.parametrize(
    "site_url", [{"login_form": b"<html><body>Unexpected markup</body></html>"}], indirect=True
)
def test_ui_login_closes_tab_on_failure(page: playwright.sync_api.Page, site_url):
    page.context.set_default_timeout(1000)

    with pytest.raises(playwright.sync_api.TimeoutError):
        make_instance(site_url).ui_login(site="shopping_admin", page=page)

    assert page.context.pages == [page]
