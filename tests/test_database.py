"""Kiểm thử tầng SQLite. Mọi test dùng cơ sở dữ liệu tạm (tmp_path), không đụng data/market_data.db."""

import numpy as np
import pandas as pd
import pytest

from src.data.database import StockDatabase


@pytest.fixture
def db(tmp_path):
    return StockDatabase(tmp_path / "test.db")


def price_rows(**overrides):
    base = {
        "symbol": ["AAA", "AAA"],
        "trading_date": ["2026-01-05", "2026-01-06"],
        "open": [10.0, 11.0], "high": [11.0, 12.0], "low": [9.0, 10.0],
        "close": [10.5, 11.5], "volume": [1000.0, 2000.0], "value": [10500.0, 23000.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_new_database_has_expected_tables(db):
    with db._connect() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"securities", "prices", "collection_log"}.issubset(tables)


def test_save_prices_returns_count_and_stores_rows(db):
    assert db.save_prices(price_rows()) == 2
    stored = db.get_prices()
    assert len(stored) == 2
    assert pd.api.types.is_datetime64_any_dtype(stored["trading_date"])


def test_duplicate_symbol_date_is_overwritten(db):
    db.save_prices(price_rows())
    db.save_prices(price_rows(close=[99.0, 98.0]))
    stored = db.get_prices()
    assert len(stored) == 2
    assert sorted(stored["close"]) == [98.0, 99.0]


def test_duplicates_inside_one_batch_keep_last(db):
    frame = price_rows(symbol=["AAA", "AAA"], trading_date=["2026-01-05", "2026-01-05"], close=[1.0, 2.0])
    assert db.save_prices(frame) == 1
    assert db.get_prices().iloc[0]["close"] == 2.0


def test_invalid_rows_are_dropped(db):
    frame = pd.DataFrame({
        "symbol": ["AAA", "AAA", "AAA", "AAA", "BBB"],
        "trading_date": ["2026-01-05", "2026-01-06", "2026-01-07", None, "2026-01-05"],
        "close": [10.0, 0.0, -5.0, 10.0, np.nan],
    })
    assert db.save_prices(frame) == 1               # chỉ dòng AAA ngày 05/01 hợp lệ
    assert list(db.get_prices()["symbol"]) == ["AAA"]


def test_symbol_and_date_are_normalized(db):
    frame = pd.DataFrame({"symbol": [" vnm "], "trading_date": ["2026/01/05"], "close": [70.0]})
    db.save_prices(frame)
    row = db.get_prices().iloc[0]
    assert row["symbol"] == "VNM"
    assert row["trading_date"] == pd.Timestamp("2026-01-05")


def test_missing_optional_columns_are_stored_as_null(db):
    db.save_prices(pd.DataFrame({"symbol": ["AAA"], "trading_date": ["2026-01-05"], "close": [10.0]}))
    row = db.get_prices().iloc[0]
    assert pd.isna(row["value"]) and pd.isna(row["volume"])


def test_save_prices_with_empty_input_returns_zero(db):
    assert db.save_prices(None) == 0
    assert db.save_prices(pd.DataFrame()) == 0


def test_get_prices_filters_by_symbol(db):
    db.save_prices(price_rows())
    db.save_prices(price_rows(symbol=["BBB", "BBB"]))
    only_b = db.get_prices(["bbb"])
    assert set(only_b["symbol"]) == {"BBB"}
    assert db.get_prices([]).empty
    assert db.get_prices(["ZZZ"]).empty


def test_symbol_price_status(db):
    empty = db.get_symbol_price_status("AAA")
    assert empty["row_count"] == 0 and empty["first_date"] is None
    db.save_prices(price_rows())
    status = db.get_symbol_price_status("aaa")
    assert status == {"row_count": 2, "first_date": "2026-01-05", "latest_date": "2026-01-06"}


def test_save_securities_cleans_text_and_uppercases_symbol(db):
    frame = pd.DataFrame({
        "symbol": ["aaa", "BBB"],
        "name": ["Công ty A", "None"],
        "board": ["HOSE", "nan"],
        "icb_name": [None, ""],
        "stock_type": ["STOCK", "STOCK"],
    })
    assert db.save_securities(frame) == 2
    stored = db.get_securities().set_index("symbol")
    assert set(stored.index) == {"AAA", "BBB"}
    assert pd.isna(stored.loc["BBB", "name"]) and pd.isna(stored.loc["BBB", "board"])


def test_save_securities_removes_delisted_but_keeps_price_history(db):
    both = pd.DataFrame({"symbol": ["AAA", "BBB"], "name": ["A", "B"], "board": ["HOSE", "HNX"]})
    db.save_securities(both)
    db.save_prices(price_rows(symbol=["AAA", "AAA"]))
    db.save_prices(price_rows(symbol=["BBB", "BBB"]))

    db.save_securities(both[both["symbol"] == "AAA"])     # BBB không còn trong danh sách SSI

    assert list(db.get_securities()["symbol"]) == ["AAA"]
    assert set(db.get_prices()["symbol"]) == {"AAA", "BBB"}   # lịch sử giá vẫn còn


def test_save_securities_updates_existing_rows(db):
    db.save_securities(pd.DataFrame({"symbol": ["AAA"], "name": ["Tên cũ"], "board": ["HOSE"]}))
    db.save_securities(pd.DataFrame({"symbol": ["AAA"], "name": ["Tên mới"], "board": ["HNX"]}))
    stored = db.get_securities()
    assert len(stored) == 1
    assert stored.iloc[0]["name"] == "Tên mới" and stored.iloc[0]["board"] == "HNX"


def test_collection_log_is_returned_newest_first(db):
    db.log_collection("AAA", "SUCCESS", "xong", 5)
    db.log_collection("BBB", "ERROR", "lỗi mạng")
    log = db.get_collection_summary(limit=10)
    assert list(log["symbol"]) == ["BBB", "AAA"]
    assert list(log["status"]) == ["ERROR", "SUCCESS"]
    assert log.iloc[1]["rows_collected"] == 5
    assert len(db.get_collection_summary(limit=1)) == 1


def test_database_stats_and_latest_update_use_vnindex(db):
    db.save_prices(price_rows(symbol=["AAA", "AAA"]))
    db.save_prices(price_rows(symbol=["VNINDEX", "VNINDEX"], trading_date=["2026-01-05", "2026-01-09"]))
    stats = db.get_database_stats()
    assert stats["price_rows"] == 4
    assert stats["symbols_with_prices"] == 2
    assert stats["benchmark_rows"] == 2
    assert db.get_latest_update() == "2026-01-09"       # lấy theo VNINDEX


def test_latest_update_falls_back_to_any_symbol(db):
    assert db.get_latest_update() is None
    db.save_prices(price_rows())
    assert db.get_latest_update() == "2026-01-06"