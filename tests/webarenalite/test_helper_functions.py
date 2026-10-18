import importlib.util
import json
import pathlib
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

HELPERS_PATH = (
    pathlib.Path(__file__).parents[2]
    / "browsergym/webarenalite/src/browsergym/webarenalite/helper_functions.py"
)


class FakeMagento:
    def __init__(self):
        self.token_requests = 0
        self.api_requests = []
        self.valid_tokens = set()
        self.timeouts = []

    def issue_token(self):
        self.token_requests += 1
        token = f"token-{self.token_requests}"
        self.valid_tokens.add(token)
        return token


def _make_handler(magento):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            creds = json.loads(self.rfile.read(length))
            if self.path != "/rest/default/V1/integration/admin/token":
                return self._send(404, {"message": "not found"})
            if creds != {"username": "admin", "password": "admin1234"}:
                return self._send(401, {"message": "invalid credentials"})
            self._send(200, magento.issue_token())

        def do_GET(self):
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            magento.api_requests.append((self.path, token))
            if token not in magento.valid_tokens:
                return self._send(401, {"message": "consumer is not authorized"})
            if self.path.startswith("/rest/V1/orders?"):
                return self._send(200, {"items": [{"increment_id": "000000190"}]})
            if self.path == "/rest/V1/products/B01/reviews":
                reviews = [
                    {"nickname": name, "ratings": [{"rating_name": "Rating", "percent": pct}]}
                    for name, pct in (("first", 40), ("latest", 80))
                ]
                return self._send(200, reviews)
            self._send(404, {"message": "not found"})

    return Handler


@pytest.fixture
def magento():
    fake = FakeMagento()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(fake))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def helpers(magento, monkeypatch):
    """Load helper_functions against the fake Magento with webarena (and playwright) stubbed."""
    env_config = types.ModuleType("webarena.browser_env.env_config")
    env_config.ACCOUNTS = {"shopping_site_admin": {"username": "admin", "password": "admin1234"}}
    for name in ("GITLAB", "MAP", "REDDIT", "SHOPPING_ADMIN", "WIKIPEDIA"):
        setattr(env_config, name, "http://unused")
    env_config.SHOPPING = magento.url
    openai_utils = types.ModuleType("webarena.llms.providers.openai_utils")
    openai_utils.generate_from_openai_chat_completion = lambda *a, **k: ""
    stubs = {
        "webarena": types.ModuleType("webarena"),
        "webarena.browser_env": types.ModuleType("webarena.browser_env"),
        "webarena.browser_env.env_config": env_config,
        "webarena.llms": types.ModuleType("webarena.llms"),
        "webarena.llms.providers": types.ModuleType("webarena.llms.providers"),
        "webarena.llms.providers.openai_utils": openai_utils,
    }
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.CDPSession = sync_api.Page = object
        stubs["playwright"] = types.ModuleType("playwright")
        stubs["playwright.sync_api"] = sync_api
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    # Load the file directly so the package __init__ (nltk, gymnasium, ...) is not required.
    spec = importlib.util.spec_from_file_location("_webarenalite_helper_functions", HELPERS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_token_fetched_once_across_helper_calls(helpers, magento):
    assert helpers.shopping_get_latest_order_url() == (
        f"{magento.url}/sales/order/view/order_id/190/"
    )
    assert helpers.shopping_get_sku_latest_review_author("B01") == "latest"
    assert helpers.shopping_get_sku_latest_review_rating("B01") == "80"
    assert helpers.shopping_get_latest_order_url().endswith("/order_id/190/")

    assert magento.token_requests == 1
    assert len(magento.api_requests) == 4
    assert {token for _, token in magento.api_requests} == {"token-1"}


def test_token_refetched_after_ttl(helpers, magento, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(helpers.time, "monotonic", lambda: now[0])

    helpers.shopping_get_sku_latest_review_author("B01")
    now[0] += helpers.SHOPPING_ADMIN_TOKEN_TTL - 1
    helpers.shopping_get_sku_latest_review_author("B01")
    assert magento.token_requests == 1

    now[0] += 2
    helpers.shopping_get_sku_latest_review_author("B01")
    assert magento.token_requests == 2
    assert magento.api_requests[-1][1] == "token-2"


def test_revoked_token_refetched_on_401(helpers, magento):
    helpers.shopping_get_sku_latest_review_author("B01")
    magento.valid_tokens.clear()

    assert helpers.shopping_get_sku_latest_review_rating("B01") == "80"
    assert magento.token_requests == 2
    assert [token for _, token in magento.api_requests] == ["token-1", "token-1", "token-2"]

    helpers.shopping_get_sku_latest_review_rating("B01")
    assert magento.token_requests == 2


def test_failed_login_not_cached(helpers, magento, monkeypatch):
    monkeypatch.setitem(helpers.ACCOUNTS["shopping_site_admin"], "password", "wrong")
    assert helpers.shopping_get_auth_token() == {"message": "invalid credentials"}
    assert helpers._shopping_token_cache == {}

    monkeypatch.setitem(helpers.ACCOUNTS["shopping_site_admin"], "password", "admin1234")
    assert helpers.shopping_get_auth_token() == "token-1"


def test_requests_have_timeouts(helpers, monkeypatch):
    seen = []
    real_request = helpers.requests.Session.request

    def recording_request(self, method, url, **kwargs):
        seen.append((method.upper(), kwargs.get("timeout")))
        return real_request(self, method, url, **kwargs)

    monkeypatch.setattr(helpers.requests.Session, "request", recording_request)
    helpers.shopping_get_latest_order_url()
    helpers.shopping_get_sku_latest_review_author("B01")

    assert seen == [
        ("POST", helpers.SHOPPING_REQUEST_TIMEOUT),
        ("GET", helpers.SHOPPING_REQUEST_TIMEOUT),
        ("GET", helpers.SHOPPING_REQUEST_TIMEOUT),
    ]
