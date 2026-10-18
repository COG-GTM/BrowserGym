import logging
import types

import pytest
import playwright.sync_api
import requests

import browsergym.webarena.instance as instance_module
from browsergym.webarena.instance import WebArenaInstance


def test_is_reachable():
    # default URLs
    instance = WebArenaInstance()
    instance.check_status()

    # unreacheable URL
    with pytest.raises(RuntimeError):
        instance = WebArenaInstance()
        instance.urls["reddit"] = "https://invalid.url"
        instance.check_status()


@pytest.mark.parametrize(
    "site", ["reddit", "shopping", "shopping_admin", "gitlab", "wikipedia", "map"]
)
def test_credentials(page: playwright.sync_api.Page, site: str):
    # default URLs and credentials
    instance = WebArenaInstance()
    instance.ui_login(site=site, page=page)

    # TODO: test this more thoroughly


# ---------------------------------------------------------------------------
# Offline tests for WebArenaInstance.full_reset (no live WebArena servers).
# requests.get and the instance module's clock are faked.
# ---------------------------------------------------------------------------

RESET_BASE_URL = "http://reset.invalid:7565"
DUMMY_URLS = {
    "reddit": "http://reddit.invalid",
    "gitlab": "http://gitlab.invalid",
    "shopping": "http://shopping.invalid",
    "shopping_admin": "http://shopping-admin.invalid",
    "wikipedia": "http://wikipedia.invalid",
    "map": "http://map.invalid",
}


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class FakeRequests:
    """Replaces requests.get: serves scripted /reset and /status responses, records every call."""

    def __init__(self, reset=None, statuses=(), site_errors=()):
        self.reset = reset
        self.statuses = list(statuses)
        # one entry per _check_is_reachable() pass: None (all sites up) or an exception to raise
        self.site_errors = list(site_errors)
        self.calls = []

    def get(self, url, timeout=None, **kwargs):
        self.calls.append((url, timeout))
        if url == f"{RESET_BASE_URL}/reset":
            assert self.reset is not None, "unexpected reset request"
            return self.reset
        if url == f"{RESET_BASE_URL}/status":
            if len(self.statuses) > 1:
                return self.statuses.pop(0)
            return self.statuses[0]
        assert url in DUMMY_URLS.values(), f"unexpected URL {url}"
        if url == DUMMY_URLS["reddit"] and self.site_errors:
            error = self.site_errors.pop(0)
            if error is not None:
                raise error
        return FakeResponse(200)

    def urls_called(self):
        return [url for url, _ in self.calls]


class FakeClock:
    """Replaces the `time` module used by instance.py: sleep() advances time() without waiting."""

    def __init__(self, start: float = 1000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def offline_instance(monkeypatch):
    # bypass __init__, which imports webarena and requires the WA_* environment variables
    instance = WebArenaInstance.__new__(WebArenaInstance)
    instance.urls = dict(DUMMY_URLS)
    instance.home_url = "http://homepage.invalid"
    instance.credentials = {}
    monkeypatch.setenv(WebArenaInstance.RESET_URL_VAR, RESET_BASE_URL)
    return instance


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(
        instance_module, "time", types.SimpleNamespace(time=fake.time, sleep=fake.sleep)
    )
    return fake


def install_requests(monkeypatch, fake: FakeRequests):
    monkeypatch.setattr(instance_module.requests, "get", fake.get)
    return fake


def reachability_calls(fake: FakeRequests):
    return [(url, timeout) for url, timeout in fake.calls if url in DUMMY_URLS.values()]


@pytest.mark.parametrize("env_value", [None, ""])
def test_full_reset_missing_url_skips_and_warms_up(
    offline_instance, clock, monkeypatch, caplog, env_value
):
    if env_value is None:
        monkeypatch.delenv(WebArenaInstance.RESET_URL_VAR, raising=False)
    else:
        monkeypatch.setenv(WebArenaInstance.RESET_URL_VAR, env_value)
    fake = install_requests(monkeypatch, FakeRequests())

    with caplog.at_level(logging.INFO, logger=instance_module.__name__):
        offline_instance.full_reset(skip_if_not_set=True)

    # no reset/status request, but the instance is still warmed up once with the 60s timeout
    assert fake.calls == [(url, 60) for url in DUMMY_URLS.values()]
    assert clock.sleeps == []
    assert any(
        r.levelno == logging.ERROR and WebArenaInstance.RESET_URL_VAR in r.getMessage()
        for r in caplog.records
    )
    assert any(
        r.levelno == logging.WARNING and "Skipping automated reset" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.parametrize("env_value", [None, ""])
def test_full_reset_missing_url_raises_when_not_skipping(
    offline_instance, clock, monkeypatch, env_value
):
    if env_value is None:
        monkeypatch.delenv(WebArenaInstance.RESET_URL_VAR, raising=False)
    else:
        monkeypatch.setenv(WebArenaInstance.RESET_URL_VAR, env_value)
    fake = install_requests(monkeypatch, FakeRequests())

    with pytest.raises(RuntimeError, match="Could not reset instance"):
        offline_instance.full_reset(skip_if_not_set=False)

    # aborts before any network request, including the warm-up
    assert fake.calls == []


def test_full_reset_started_then_ready(offline_instance, clock, monkeypatch, caplog):
    fake = install_requests(
        monkeypatch,
        FakeRequests(
            reset=FakeResponse(200),
            statuses=[FakeResponse(200, "Resetting..."), FakeResponse(200, "Ready for duty!")],
        ),
    )

    with caplog.at_level(logging.INFO, logger=instance_module.__name__):
        offline_instance.full_reset()

    assert fake.urls_called() == [
        f"{RESET_BASE_URL}/reset",
        f"{RESET_BASE_URL}/status",
        f"{RESET_BASE_URL}/status",
        *DUMMY_URLS.values(),
    ]
    assert reachability_calls(fake) == [(url, 60) for url in DUMMY_URLS.values()]
    assert clock.sleeps == [20]
    assert any("Reset started." in r.getMessage() for r in caplog.records)


def test_full_reset_already_running_418_waits_for_ready(
    offline_instance, clock, monkeypatch, caplog
):
    fake = install_requests(
        monkeypatch,
        FakeRequests(
            reset=FakeResponse(418, "I'm a teapot"),
            statuses=[FakeResponse(200, "Ready for duty!")],
        ),
    )

    with caplog.at_level(logging.INFO, logger=instance_module.__name__):
        offline_instance.full_reset()

    # 418 is not an error: the job keeps going, polls status and warms up
    assert fake.urls_called() == [
        f"{RESET_BASE_URL}/reset",
        f"{RESET_BASE_URL}/status",
        *DUMMY_URLS.values(),
    ]
    assert clock.sleeps == []
    assert any(
        r.levelno == logging.WARNING and "already running" in r.getMessage() for r in caplog.records
    )


@pytest.mark.parametrize("status_code", [500, 404, 503])
def test_full_reset_reset_request_failure_raises(offline_instance, clock, monkeypatch, status_code):
    fake = install_requests(monkeypatch, FakeRequests(reset=FakeResponse(status_code, "boom")))

    with pytest.raises(Exception, match=rf"reset request .*/reset failed \({status_code}\): boom"):
        offline_instance.full_reset()

    # no status poll and no warm-up after a failed reset request
    assert fake.urls_called() == [f"{RESET_BASE_URL}/reset"]
    assert clock.sleeps == []


@pytest.mark.parametrize("reset_status", [200, 418])
@pytest.mark.parametrize("status_code,status_text", [(404, "Not Found"), (502, "Bad Gateway")])
def test_full_reset_status_request_failure_raises(
    offline_instance, clock, monkeypatch, reset_status, status_code, status_text
):
    fake = install_requests(
        monkeypatch,
        FakeRequests(
            reset=FakeResponse(reset_status),
            statuses=[FakeResponse(200, "Resetting..."), FakeResponse(status_code, status_text)],
        ),
    )

    with pytest.raises(
        Exception, match=rf"status request .*/status failed \({status_code}\): {status_text}"
    ):
        offline_instance.full_reset()

    assert fake.urls_called() == [
        f"{RESET_BASE_URL}/reset",
        f"{RESET_BASE_URL}/status",
        f"{RESET_BASE_URL}/status",
    ]
    assert clock.sleeps == [20]


def test_full_reset_status_never_ready_times_out(offline_instance, clock, monkeypatch):
    fake = install_requests(
        monkeypatch,
        FakeRequests(reset=FakeResponse(200), statuses=[FakeResponse(200, "Resetting...")]),
    )

    with pytest.raises(Exception, match=r"Reset still running after .* \(> 600\), aborting"):
        offline_instance.full_reset()

    # polls every 20s; 600s elapsed is still allowed, the first poll past 600s (620s) aborts
    assert clock.sleeps == [20] * 31
    assert clock.now - 1000.0 == 620
    status_calls = [u for u in fake.urls_called() if u == f"{RESET_BASE_URL}/status"]
    assert len(status_calls) == 32
    # no warm-up after a timeout
    assert reachability_calls(fake) == []


def test_full_reset_ready_at_timeout_boundary(offline_instance, clock, monkeypatch):
    # still "Resetting..." at exactly 600s elapsed (not > timeout), ready on the next poll
    fake = install_requests(
        monkeypatch,
        FakeRequests(
            reset=FakeResponse(200),
            statuses=[FakeResponse(200, "Resetting...")] * 31
            + [FakeResponse(200, "Ready for duty!")],
        ),
    )

    offline_instance.full_reset()

    assert clock.sleeps == [20] * 31
    assert reachability_calls(fake) == [(url, 60) for url in DUMMY_URLS.values()]


def test_full_reset_warm_up_retries_until_reachable(offline_instance, clock, monkeypatch, caplog):
    fake = install_requests(
        monkeypatch,
        FakeRequests(
            reset=FakeResponse(200),
            statuses=[FakeResponse(200, "Ready for duty!")],
            site_errors=[
                requests.exceptions.ConnectionError("refused"),
                requests.exceptions.Timeout("slow"),
                None,
            ],
        ),
    )

    with caplog.at_level(logging.INFO, logger=instance_module.__name__):
        offline_instance.full_reset()

    calls = reachability_calls(fake)
    # two failed passes stop at the first site, the third pass visits every site
    assert calls == [(DUMMY_URLS["reddit"], 60)] * 2 + [(url, 60) for url in DUMMY_URLS.values()]
    retry_logs = [r.getMessage() for r in caplog.records if "retrying" in r.getMessage()]
    assert len(retry_logs) == 2
    assert "2 retries left" in retry_logs[0]
    assert "1 retries left" in retry_logs[1]


def test_full_reset_warm_up_gives_up_after_three_attempts(offline_instance, clock, monkeypatch):
    fake = install_requests(
        monkeypatch,
        FakeRequests(
            reset=FakeResponse(200),
            statuses=[FakeResponse(200, "Ready for duty!")],
            site_errors=[requests.exceptions.ConnectionError("refused")] * 4,
        ),
    )

    with pytest.raises(RuntimeError, match=r'WebArena site "reddit" .* is not reacheable'):
        offline_instance.full_reset()

    assert reachability_calls(fake) == [(DUMMY_URLS["reddit"], 60)] * 3


def test_full_reset_warm_up_retries_when_reset_skipped(offline_instance, clock, monkeypatch):
    monkeypatch.delenv(WebArenaInstance.RESET_URL_VAR, raising=False)
    calls = []

    def flaky_check(timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise RuntimeError("not ready")

    monkeypatch.setattr(offline_instance, "_check_is_reachable", flaky_check)

    offline_instance.full_reset(skip_if_not_set=True)

    assert calls == [60, 60, 60]
