"""Kiểm thử bộ thu thập: chuẩn hóa dữ liệu SSI, phân loại chứng khoán, xử lý lỗi. Không gọi mạng."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

import src.data.collector as collector
from src.data.database import StockDatabase
from src.ssi_api.client import SSIAPIError


@pytest.fixture
def db(tmp_path):
    return StockDatabase(tmp_path / "test.db")


# ------------------------------------------------------------
# normalize_ohlc
# ------------------------------------------------------------

def ohlc_rows():
    return [
        {"tradingDate": "2026/11/16", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "value": 1050},
        {"tradingDate": "2026/11/17", "open": 10, "high": 11, "low": 9, "close": 11.0, "volume": 200, "value": 2200},
    ]


def test_normalize_ohlc_parses_ssi_style_columns():
    result = collector.normalize_ohlc(ohlc_rows(), "aaa")
    assert list(result.columns) == ["symbol", "trading_date", "open", "high", "low", "close", "volume", "value"]
    assert list(result["trading_date"]) == ["2026-11-16", "2026-11-17"]
    assert result["close"].tolist() == [10.5, 11.0]


def test_normalize_ohlc_accepts_dict_with_data_list():
    assert len(collector.normalize_ohlc({"data": ohlc_rows()}, "AAA")) == 2


def test_normalize_ohlc_drops_invalid_rows():
    rows = ohlc_rows() + [
        {"tradingDate": "2026/11/18", "open": 1, "high": 1, "low": 1, "close": 0, "volume": 1, "value": 1},
        {"tradingDate": "2026/11/19", "open": 1, "high": 1, "low": 1, "close": None, "volume": 1, "value": 1},
        {"tradingDate": "không phải ngày", "open": 1, "high": 1, "low": 1, "close": 5, "volume": 1, "value": 1},
    ]
    assert len(collector.normalize_ohlc(rows, "AAA")) == 2


def test_normalize_ohlc_keeps_last_duplicate_date():
    rows = ohlc_rows() + [dict(ohlc_rows()[0], close=99.0)]
    result = collector.normalize_ohlc(rows, "AAA")
    assert len(result) == 2
    assert result.loc[result["trading_date"] == "2026-11-16", "close"].iloc[0] == 99.0


def test_normalize_ohlc_value_is_nan_when_column_missing():
    rows = [{k: v for k, v in row.items() if k != "value"} for row in ohlc_rows()]
    result = collector.normalize_ohlc(rows, "AAA")
    assert result["value"].isna().all()           # không thay bằng 0


@pytest.mark.parametrize("raw", [None, [], {"code": 204}, [{"tradingDate": "2026/11/16", "close": 5}]])
def test_normalize_ohlc_returns_empty_for_empty_or_incomplete_data(raw):
    assert collector.normalize_ohlc(raw, "AAA").empty


# ------------------------------------------------------------
# Phân loại chứng khoán
# ------------------------------------------------------------

@pytest.mark.parametrize("row, expected", [
    ({"symbol": "VNM", "name": "x", "stock_type": "STOCK"}, (True, "SSI_STOCK")),
    ({"symbol": "VNINDEX", "name": "x", "stock_type": "STOCK"}, (False, "INDEX")),
    ({"symbol": "ABC", "name": "Chỉ số ABC", "stock_type": "STOCK"}, (False, "INDEX")),
    ({"symbol": "CVNM2401", "name": "x", "stock_type": "STOCK", "cw_underlying_symbol": "VNM"}, (False, "WARRANT")),
    ({"symbol": "E1VFVN30", "name": "x", "stock_type": "ETF PRODUCT"}, (False, "EXCLUDED_ETF PRODUCT")),
    ({"symbol": "XYZ", "name": "x", "stock_type": "LẠ"}, (False, "UNKNOWN_TYPE_LẠ")),
    ({"symbol": "41I1FB000", "name": "x"}, (False, "FUTURE_SYMBOL")),
    ({"symbol": "AAA", "name": "Quỹ đầu tư ABC"}, (False, "EXCLUDED_BY_NAME")),
    ({"symbol": "AAA", "name": "Công ty TNHH ABC"}, (False, "EXCLUDED_BY_NAME")),
    ({"symbol": "AAA", "name": "Công ty Cổ phần ABC"}, (True, "INFERRED_COMPANY_NAME")),
    ({"symbol": "AAA", "name": "Tên không rõ"}, (False, "UNRESOLVED")),
    ({"symbol": "", "name": "x", "stock_type": "STOCK"}, (False, "MISSING_SYMBOL")),
])
def test_classify_security(row, expected):
    assert collector.classify_security(row) == expected


@pytest.mark.parametrize("symbol, expected", [("41I1FB000", True), ("41ABC000", True), ("VNM", False), ("HPG", False)])
def test_is_future_symbol(symbol, expected):
    assert collector.is_future_symbol(symbol) is expected


def test_normalize_securities_keeps_only_valid_stocks():
    raw = [
        {"symbol": "vnm", "symbolNameVi": "Vinamilk", "stockType": "stock", "icbName": "Thực phẩm"},
        {"symbol": "VNINDEX", "symbolNameVi": "VN-Index", "stockType": "STOCK"},
        {"symbol": "CWX", "symbolNameVi": "CW", "stockType": "CW PRODUCT"},
        {"symbol": "VNM", "symbolNameVi": "Vinamilk (trùng)", "stockType": "STOCK"},
    ]
    result = collector.normalize_securities(raw, "HOSE")
    assert list(result["symbol"]) == ["VNM"]
    assert result.iloc[0]["board"] == "HOSE"
    assert result.iloc[0]["name"] == "Vinamilk (trùng)"     # giữ dòng cuối khi trùng mã


def test_normalize_securities_without_symbol_column_returns_empty():
    assert collector.normalize_securities([{"ten": "x"}], "HOSE").empty


def test_find_column_is_case_insensitive():
    df = pd.DataFrame(columns=["TradingDate", "Close"])
    assert collector.find_column(df, ["tradingdate"]) == "TradingDate"
    assert collector.find_column(df, ["khong_co"]) is None


@pytest.mark.parametrize("value, expected", [
    (None, ""), (np.nan, ""), ("  none ", ""), ("N/A", ""), (" vnm ", "VNM"),
])
def test_normalize_text(value, expected):
    assert collector.normalize_text(value) == expected


# ------------------------------------------------------------
# Mã bổ sung
# ------------------------------------------------------------

def test_supplemental_symbol_is_added_once(monkeypatch):
    monkeypatch.setattr(collector, "SUPPLEMENTAL_SYMBOLS", ["HPG"])
    base = pd.DataFrame({"symbol": ["VNM"], "name": ["x"], "board": ["HOSE"], "icb_name": [None], "stock_type": ["STOCK"]})
    result = collector.add_supplemental_securities(base)
    assert sorted(result["symbol"]) == ["HPG", "VNM"]
    assert list(collector.add_supplemental_securities(result)["symbol"]).count("HPG") == 1


def test_supplemental_symbol_without_metadata_is_skipped(monkeypatch):
    monkeypatch.setattr(collector, "SUPPLEMENTAL_SYMBOLS", ["KHONGCO"])
    base = pd.DataFrame({"symbol": ["VNM"], "name": ["x"], "board": ["HOSE"], "icb_name": [None], "stock_type": ["STOCK"]})
    assert list(collector.add_supplemental_securities(base)["symbol"]) == ["VNM"]


# ------------------------------------------------------------
# Ngày bắt đầu thu thập
# ------------------------------------------------------------

def test_start_date_defaults_when_no_history(db):
    default = date(2025, 1, 1)
    assert collector.get_symbol_start_date(db, "AAA", default) == default


def test_start_date_overlaps_latest_date(db, monkeypatch):
    monkeypatch.setattr(collector, "OVERLAP_DAYS", 7)
    db.save_prices(pd.DataFrame({"symbol": ["AAA", "AAA"], "trading_date": ["2025-01-02", "2026-01-20"], "close": [1.0, 2.0]}))
    assert collector.get_symbol_start_date(db, "AAA", date(2025, 6, 1)) == date(2026, 1, 13)


def test_start_date_refetches_when_history_is_too_short(db):
    db.save_prices(pd.DataFrame({"symbol": ["AAA"], "trading_date": ["2026-01-20"], "close": [2.0]}))
    default = date(2025, 6, 1)           # dữ liệu hiện có bắt đầu muộn hơn mốc mặc định
    assert collector.get_symbol_start_date(db, "AAA", default) == default


# ------------------------------------------------------------
# Thu thập một mã: thành công, rỗng, lỗi
# ------------------------------------------------------------

class FakeClient:
    def __init__(self, ohlc=None, error=None, boards=None):
        self.ohlc, self.error, self.boards = ohlc, error, boards or {}

    def get_ohlc_all(self, **kwargs):
        if self.error:
            raise self.error
        return self.ohlc

    def get_securities_by_board(self, board):
        value = self.boards[board]
        if isinstance(value, Exception):
            raise value
        return value


def test_collect_symbol_success_saves_rows_and_logs(db):
    rows = collector.collect_symbol_ohlc(FakeClient(ohlc=ohlc_rows()), db, "AAA", date(2026, 11, 1), date(2026, 11, 20))
    assert rows == 2
    assert len(db.get_prices(["AAA"])) == 2
    assert db.get_collection_summary().iloc[0]["status"] == "SUCCESS"


def test_collect_symbol_empty_response_returns_zero(db):
    rows = collector.collect_symbol_ohlc(FakeClient(ohlc=[]), db, "AAA", date(2026, 11, 1), date(2026, 11, 20))
    assert rows == 0
    assert db.get_prices().empty
    assert db.get_collection_summary().iloc[0]["status"] == "EMPTY"


@pytest.mark.parametrize("error", [SSIAPIError("hết hạn", status_code=500), ValueError("dữ liệu lỗi")])
def test_collect_symbol_error_returns_minus_one_and_logs(db, error):
    rows = collector.collect_symbol_ohlc(FakeClient(error=error), db, "AAA", date(2026, 11, 1), date(2026, 11, 20))
    assert rows == -1
    log = db.get_collection_summary().iloc[0]
    assert log["status"] == "ERROR" and str(error) in log["message"]


# ------------------------------------------------------------
# Thu thập danh sách chứng khoán
# ------------------------------------------------------------

def board_rows(symbol):
    return [{"symbol": symbol, "symbolNameVi": f"Công ty {symbol}", "stockType": "STOCK"}]


@pytest.fixture
def quiet_collector(monkeypatch):
    monkeypatch.setattr(collector, "BOARDS", ["HOSE", "HNX"])
    monkeypatch.setattr(collector, "REQUEST_DELAY", 0)
    monkeypatch.setattr(collector, "SUPPLEMENTAL_SYMBOLS", [])


def test_collect_securities_saves_all_boards(db, quiet_collector):
    client = FakeClient(boards={"HOSE": board_rows("AAA"), "HNX": board_rows("BBB")})
    result = collector.collect_securities(client, db)
    assert sorted(result["symbol"]) == ["AAA", "BBB"]
    assert sorted(db.get_securities()["symbol"]) == ["AAA", "BBB"]


def test_collect_securities_keeps_old_list_when_a_board_fails(db, quiet_collector):
    db.save_securities(pd.DataFrame({"symbol": ["OLD"], "name": ["Mã cũ"], "board": ["HOSE"]}))
    client = FakeClient(boards={"HOSE": board_rows("AAA"), "HNX": SSIAPIError("lỗi mạng")})
    with pytest.raises(RuntimeError, match="HNX"):
        collector.collect_securities(client, db)
    assert list(db.get_securities()["symbol"]) == ["OLD"]       # danh sách cũ được giữ nguyên


def test_collect_securities_fails_on_empty_board(db, quiet_collector):
    client = FakeClient(boards={"HOSE": board_rows("AAA"), "HNX": []})
    with pytest.raises(RuntimeError):
        collector.collect_securities(client, db)