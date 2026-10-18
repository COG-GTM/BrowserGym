import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pytest
import requests

from browsergym.webarenalite import helper_functions


class _ShoppingHandler(BaseHTTPRequestHandler):
    # path -> (status, json body, delay in seconds)
    routes: dict = {}

    def _respond(self):
        status, body, delay = self.routes.get(self.path.split("?")[0], (404, {}, 0))
        time.sleep(delay)
        payload = json.dumps(body).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = _respond
    do_POST = _respond

    def log_message(self, *args):
        pass


@pytest.fixture
def shopping_server():
    _ShoppingHandler.routes = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ShoppingHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    with mock.patch.object(helper_functions, "SHOPPING", url):
        yield _ShoppingHandler.routes
    server.shutdown()
    server.server_close()


TOKEN_PATH = "/rest/default/V1/integration/admin/token"
REVIEWS_PATH = "/rest/V1/products/SKU1/reviews"
ORDERS_PATH = "/rest/V1/orders"


def test_shopping_helpers_return_values(shopping_server):
    shopping_server[TOKEN_PATH] = (200, "tok", 0)
    shopping_server[REVIEWS_PATH] = (
        200,
        [{"nickname": "alice", "ratings": [{"rating_name": "Rating", "percent": 80}]}],
        0,
    )
    shopping_server[ORDERS_PATH] = (200, {"items": [{"increment_id": "000000042"}]}, 0)

    assert helper_functions.shopping_get_auth_token() == "tok"
    assert helper_functions.shopping_get_sku_latest_review_author("SKU1") == "alice"
    assert helper_functions.shopping_get_sku_latest_review_rating("SKU1") == "80"
    order_url = helper_functions.shopping_get_latest_order_url()
    assert order_url.endswith("/sales/order/view/order_id/42/")


def test_shopping_helpers_no_reviews_is_empty(shopping_server):
    shopping_server[TOKEN_PATH] = (200, "tok", 0)
    shopping_server[REVIEWS_PATH] = (200, [], 0)

    assert helper_functions.shopping_get_sku_latest_review_author("SKU1") == ""
    assert helper_functions.shopping_get_sku_latest_review_rating("SKU1") == ""


@pytest.mark.parametrize(
    "helper,args",
    [
        (helper_functions.shopping_get_latest_order_url, ()),
        (helper_functions.shopping_get_sku_latest_review_author, ("SKU1",)),
        (helper_functions.shopping_get_sku_latest_review_rating, ("SKU1",)),
    ],
)
def test_shopping_helpers_raise_on_http_error(shopping_server, helper, args):
    shopping_server[TOKEN_PATH] = (200, "tok", 0)
    shopping_server[REVIEWS_PATH] = (500, {"message": "boom"}, 0)
    shopping_server[ORDERS_PATH] = (500, {"message": "boom"}, 0)

    with pytest.raises(requests.HTTPError):
        helper(*args)


def test_shopping_auth_token_raises_on_http_error(shopping_server):
    shopping_server[TOKEN_PATH] = (401, {"message": "bad credentials"}, 0)

    with pytest.raises(requests.HTTPError):
        helper_functions.shopping_get_auth_token()


def test_shopping_helpers_time_out(shopping_server):
    shopping_server[TOKEN_PATH] = (200, "tok", 0)
    shopping_server[REVIEWS_PATH] = (200, [], 5)

    with mock.patch.object(helper_functions, "REQUEST_TIMEOUT", (1, 0.5)):
        start = time.monotonic()
        with pytest.raises(requests.Timeout):
            helper_functions.shopping_get_sku_latest_review_author("SKU1")
        assert time.monotonic() - start < 4


def test_shopping_rating_unexpected_name_raises(shopping_server):
    shopping_server[TOKEN_PATH] = (200, "tok", 0)
    shopping_server[REVIEWS_PATH] = (
        200,
        [{"nickname": "alice", "ratings": [{"rating_name": "Quality", "percent": 80}]}],
        0,
    )

    with pytest.raises(ValueError):
        helper_functions.shopping_get_sku_latest_review_rating("SKU1")


class _FakePage:
    """Mimics page.evaluate() for the GitLab project members table."""

    def __init__(self, accounts, roles, error=None):
        self.accounts = accounts
        self.roles = roles
        self.error = error
        self.calls = []

    def evaluate(self, expression, arg=None):
        self.calls.append((expression, arg))
        if self.error is not None:
            raise self.error
        if "gl-avatar-labeled-sublabel" in expression:
            return self.accounts.index(arg) if arg in self.accounts else -1
        if "col-max-role" in expression:
            return self.roles[arg] if arg < len(self.roles) else None
        raise AssertionError(f"unexpected expression: {expression}")


def test_gitlab_role_found():
    page = _FakePage(["@alice", "@bob"], ["Owner", "Developer"])
    assert helper_functions.gitlab_get_project_memeber_role(page, "bob") == "Developer"


def test_gitlab_role_not_a_member_is_empty():
    page = _FakePage(["@alice"], ["Owner"])
    assert helper_functions.gitlab_get_project_memeber_role(page, "carol") == ""
    assert len(page.calls) == 1


def test_gitlab_role_account_name_passed_as_argument():
    name = "o'brien\"); alert(1); //"
    page = _FakePage([f"@{name}"], ["Maintainer"])
    assert helper_functions.gitlab_get_project_memeber_role(page, name) == "Maintainer"
    assert all(name not in expression for expression, _ in page.calls)


def test_gitlab_role_page_error_propagates():
    page = _FakePage([], [], error=RuntimeError("Target page, context or browser has been closed"))
    with pytest.raises(RuntimeError, match="has been closed"):
        helper_functions.gitlab_get_project_memeber_role(page, "alice")


def test_gitlab_role_missing_role_cell_raises():
    page = _FakePage(["@alice", "@bob"], ["Owner"])
    with pytest.raises(RuntimeError, match="no role cell"):
        helper_functions.gitlab_get_project_memeber_role(page, "bob")
