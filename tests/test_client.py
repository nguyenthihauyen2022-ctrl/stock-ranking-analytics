"""Kiểm thử SSIClient bằng phiên giả lập: xác thực, làm mới token, giới hạn tần suất, lỗi máy chủ.
Không gọi mạng, không cần khóa API thật."""

import time
from datetime import date, datetime

import pytest
import requests

import src.ssi_api.client as client_module
from src.ssi_api.client import SSIAPIError, SSIClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", json_error=False):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)
        self.url = "https://fake.test/endpoint"
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("không phải JSON")
        return self._payload


class FakeSession:
    """Trả lần lượt các phản hồi (hoặc ném lỗi) đã xếp sẵn."""

    def __init__(self, responses=None, auth_responses=None):
        self.headers = {}
        self.responses = list(responses or [])
        self.auth_responses = list(auth_responses or [])
        self.calls = 0
        self.auth_calls = 0

    def post(self, url, json=None, timeout=None):
        self.auth_calls += 1
        item = self.auth_responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def request(self, method, url, params=None, timeout=None):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def token_response(token="tok-1", **extra):
    return FakeResponse(200, {"data": {"accessToken": token, **extra}})


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr(time, "sleep", lambda seconds: recorded.append(seconds))
    return recorded


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SSI_API_KEY", "key-gia")
    monkeypatch.setenv("SSI_API_SECRET", "secret-gia")
    monkeypatch.setenv("SSI_BASE_URL", "https://fake.test/")
    instance = SSIClient()
    instance.access_token = "tok-0"                   # coi như đã đăng nhập, token còn hạn
    instance.token_expiry = time.time() + 3600
    return instance


# ------------------------------------------------------------
# Khởi tạo và xác thực
# ------------------------------------------------------------

@pytest.mark.parametrize("key, secret", [("", "s"), ("k", ""), (" ", " ")])
def test_missing_credentials_raise(monkeypatch, key, secret):
    monkeypatch.setenv("SSI_API_KEY", key)
    monkeypatch.setenv("SSI_API_SECRET", secret)
    with pytest.raises(SSIAPIError, match="SSI_API_KEY"):
        SSIClient()


def test_base_url_trailing_slash_is_removed(client):
    assert client._url("/api/x") == "https://fake.test/api/x"


def test_authenticate_reads_nested_token_and_sets_header(client):
    client.session = FakeSession(auth_responses=[token_response("tok-9", expiresIn=600)])
    before = time.time()
    client.authenticate()
    assert client.access_token == "tok-9"
    assert client.session.headers["Authorization"] == "Bearer tok-9"
    assert before + 590 <= client.token_expiry <= time.time() + 610


def test_authenticate_converts_millisecond_expiry(client):
    expires_ms = (time.time() + 1000) * 1000
    client.session = FakeSession(auth_responses=[token_response(expiresAt=expires_ms)])
    client.authenticate()
    assert abs(client.token_expiry - (time.time() + 1000)) < 5


@pytest.mark.parametrize("response, status", [
    (FakeResponse(401, {"message": "sai khóa"}), 401),
    (FakeResponse(200, json_error=True), None),
    (FakeResponse(200, ["không", "phải", "dict"]), None),
    (FakeResponse(200, {"data": {}}), None),                  # thiếu accessToken
])
def test_authenticate_failures_raise(client, response, status):
    client.session = FakeSession(auth_responses=[response])
    with pytest.raises(SSIAPIError) as info:
        client.authenticate()
    assert info.value.status_code == status


def test_authenticate_network_error_raises(client):
    client.session = FakeSession(auth_responses=[requests.ConnectionError("mất mạng")])
    with pytest.raises(SSIAPIError, match="Không kết nối được"):
        client.authenticate()


def test_expired_token_triggers_new_login(client):
    client.token_expiry = time.time() - 10
    client.session = FakeSession(responses=[FakeResponse(200, {"ok": 1})],
                                 auth_responses=[token_response("tok-new")])
    assert client._request("GET", "/x") == {"ok": 1}
    assert client.session.auth_calls == 1 and client.access_token == "tok-new"


# ------------------------------------------------------------
# _request: 401, 429, 5xx, lỗi khác, kết nối
# ------------------------------------------------------------

def test_request_success_does_not_login_again(client):
    client.session = FakeSession(responses=[FakeResponse(200, {"data": [1]})])
    assert client._request("GET", "/x") == {"data": [1]}
    assert client.session.auth_calls == 0


def test_401_triggers_one_relogin_then_succeeds(client):
    client.session = FakeSession(responses=[FakeResponse(401), FakeResponse(200, {"ok": True})],
                                 auth_responses=[token_response("tok-2")])
    assert client._request("GET", "/x") == {"ok": True}
    assert client.session.auth_calls == 1


def test_repeated_401_raises(client):
    client.session = FakeSession(responses=[FakeResponse(401), FakeResponse(401)],
                                 auth_responses=[token_response("tok-2")])
    with pytest.raises(SSIAPIError) as info:
        client._request("GET", "/x")
    assert info.value.status_code == 401


def test_429_waits_then_retries(client, sleeps):
    client.session = FakeSession(responses=[FakeResponse(429), FakeResponse(429), FakeResponse(200, {"ok": 1})])
    assert client._request("GET", "/x") == {"ok": 1}
    assert sleeps == [1, 2]                        # chờ lũy thừa 2**lần thử


def test_429_on_every_attempt_gives_up_after_three_tries(client, sleeps):
    client.session = FakeSession(responses=[FakeResponse(429)] * 3)
    with pytest.raises(SSIAPIError, match="3 lần thử"):
        client._request("GET", "/x")
    assert client.session.calls == 3


def test_server_error_is_retried_then_succeeds(client, sleeps):
    client.session = FakeSession(responses=[FakeResponse(503), FakeResponse(200, {"ok": 1})])
    assert client._request("GET", "/x") == {"ok": 1}
    assert sleeps == [1]


def test_persistent_server_error_raises_with_status(client, sleeps):
    client.session = FakeSession(responses=[FakeResponse(500, text="lỗi")] * 3)
    with pytest.raises(SSIAPIError) as info:
        client._request("GET", "/x")
    assert info.value.status_code == 500
    assert sleeps == [1, 2]


def test_client_error_is_not_retried(client, sleeps):
    client.session = FakeSession(responses=[FakeResponse(404, text="không thấy")])
    with pytest.raises(SSIAPIError) as info:
        client._request("GET", "/x")
    assert info.value.status_code == 404
    assert client.session.calls == 1 and sleeps == []


def test_non_json_success_response_raises(client):
    client.session = FakeSession(responses=[FakeResponse(200, json_error=True)])
    with pytest.raises(SSIAPIError, match="không phải JSON"):
        client._request("GET", "/x")


def test_network_error_is_retried_then_raises(client, sleeps):
    client.session = FakeSession(responses=[requests.Timeout("quá hạn")] * 3)
    with pytest.raises(SSIAPIError, match="Lỗi kết nối"):
        client._request("GET", "/x")
    assert sleeps == [1, 2]


def test_network_error_then_success(client, sleeps):
    client.session = FakeSession(responses=[requests.ConnectionError("rớt mạng"), FakeResponse(200, {"ok": 1})])
    assert client._request("GET", "/x") == {"ok": 1}


# ------------------------------------------------------------
# Chuẩn hóa ngày
# ------------------------------------------------------------

@pytest.mark.parametrize("value, field, expected", [
    ("2026-11-20", "from", "2026/11/20 00:00:00"),
    ("2026/11/20", "to", "2026/11/20 23:59:59"),
    (date(2026, 11, 20), "to", "2026/11/20 23:59:59"),
    (datetime(2026, 11, 20, 9, 30, 5), "from", "2026/11/20 09:30:05"),
    ("2026-11-20 10:00:00", "to", "2026/11/20 10:00:00"),
])
def test_format_daily_date(value, field, expected):
    assert SSIClient._format_daily_date(value, field) == expected


@pytest.mark.parametrize("value", ["20-11-2026", "hôm qua", 20261120, None])
def test_format_daily_date_rejects_invalid_values(value):
    with pytest.raises(SSIAPIError):
        SSIClient._format_daily_date(value, "from")


# ------------------------------------------------------------
# Lấy OHLC và danh sách chứng khoán
# ------------------------------------------------------------

def test_ohlc_page_rejects_reversed_date_range_before_calling_api(client):
    client.session = FakeSession()
    with pytest.raises(SSIAPIError, match="Ngày bắt đầu"):
        client.get_ohlc_page("AAA", "2026-11-20", "2026-11-01")
    assert client.session.calls == 0


def test_ohlc_page_wraps_list_response(client):
    client.session = FakeSession(responses=[FakeResponse(200, [{"close": 1}])])
    page = client.get_ohlc_page("AAA", "2026-11-01", "2026-11-20")
    assert page == {"data": [{"close": 1}], "pageCount": 1}


def test_ohlc_all_collects_every_page(client, monkeypatch):
    pages = iter([{"data": [{"i": 1}, {"i": 2}], "pageCount": 2}, {"data": [{"i": 3}, {"i": 4}], "pageCount": 2}])
    monkeypatch.setattr(client, "get_ohlc_page", lambda **kwargs: next(pages))
    rows = client.get_ohlc_all("AAA", "2026-11-01", "2026-11-20", page_size=2)
    assert [row["i"] for row in rows] == [1, 2, 3, 4]


def test_ohlc_all_stops_on_short_or_empty_page(client, monkeypatch):
    calls = []

    def fake_page(**kwargs):
        calls.append(kwargs["page_index"])
        return {"data": [{"i": 1}], "pageCount": None}       # ít hơn page_size nên dừng

    monkeypatch.setattr(client, "get_ohlc_page", fake_page)
    assert len(client.get_ohlc_all("AAA", "2026-11-01", "2026-11-20", page_size=1000)) == 1
    assert calls == [1]

    monkeypatch.setattr(client, "get_ohlc_page", lambda **kwargs: {"data": []})
    assert client.get_ohlc_all("AAA", "2026-11-01", "2026-11-20") == []


def test_ohlc_all_respects_max_pages(client, monkeypatch):
    monkeypatch.setattr(client, "get_ohlc_page", lambda **kwargs: {"data": [{"i": 1}, {"i": 2}], "pageCount": 99})
    rows = client.get_ohlc_all("AAA", "2026-11-01", "2026-11-20", page_size=2, max_pages=3)
    assert len(rows) == 6


@pytest.mark.parametrize("payload, expected", [
    ([{"symbol": "AAA"}], [{"symbol": "AAA"}]),
    ({"data": [{"symbol": "BBB"}]}, [{"symbol": "BBB"}]),
    ({"data": "khác"}, []),
    ("không hợp lệ", []),
])
def test_securities_by_board_accepts_list_or_dict(client, payload, expected):
    client.session = FakeSession(responses=[FakeResponse(200, payload)])
    assert client.get_securities_by_board("HOSE") == expected