"""Kiểm thử cách StockDatabase chọn file dữ liệu: tham số, biến DATABASE_PATH, đường dẫn mặc định."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.database import DEFAULT_DB_PATH, StockDatabase


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Chạy trong thư mục tạm để mọi đường dẫn tương đối không chạm vào data/ thật."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    return tmp_path


def test_default_path_is_used_when_variable_is_not_set(isolated):
    db = StockDatabase()
    assert db.db_path == Path(DEFAULT_DB_PATH)
    assert (isolated / "data" / "market_data.db").exists()


def test_environment_variable_selects_another_file(isolated, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "data/market_data_latest.db")
    db = StockDatabase()
    assert db.db_path == Path("data/market_data_latest.db")
    assert (isolated / "data" / "market_data_latest.db").exists()
    assert not (isolated / "data" / "market_data.db").exists()      # không tạo file mặc định


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_variable_falls_back_to_default(isolated, monkeypatch, value):
    monkeypatch.setenv("DATABASE_PATH", value)
    assert StockDatabase().db_path == Path(DEFAULT_DB_PATH)


def test_explicit_argument_beats_environment_variable(isolated, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "data/market_data_latest.db")
    db = StockDatabase(isolated / "rieng.db")
    assert db.db_path == isolated / "rieng.db"


def test_sample_database_is_untouched_when_writing_to_another_file(isolated, monkeypatch):
    prices = pd.DataFrame({"symbol": ["AAA"], "trading_date": ["2026-01-05"], "close": [10.0]})

    sample = StockDatabase()                                   # dữ liệu mẫu
    sample.save_prices(prices)

    monkeypatch.setenv("DATABASE_PATH", "data/market_data_latest.db")
    latest = StockDatabase()                                   # dữ liệu thu thập mới
    latest.save_prices(prices.assign(symbol="BBB", close=99.0))

    assert list(sample.get_prices()["symbol"]) == ["AAA"]      # bản mẫu không bị đổi
    assert list(latest.get_prices()["symbol"]) == ["BBB"]