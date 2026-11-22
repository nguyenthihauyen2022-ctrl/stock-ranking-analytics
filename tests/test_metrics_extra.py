"""Kiểm thử bổ sung cho src/finance/metrics.py: giá trị tính tay và các quy tắc nêu trong README."""

import numpy as np
import pandas as pd
import pytest

from src.finance.metrics import (
    calculate_annualized_volatility,
    calculate_downside_deviation,
    calculate_log_returns,
    calculate_stock_metrics,
)
from tests.helpers import make_price_frame


# ------------------------------------------------------------
# Giá trị tính tay
# ------------------------------------------------------------

def test_annualized_volatility_exact_value():
    # 20 quan sát +-1%, trung bình 0 -> phương sai mẫu = 20 * 0,0001 / 19.
    returns = pd.Series([0.01, -0.01] * 10)
    expected = np.sqrt(20 * 0.01 ** 2 / 19) * np.sqrt(252)
    assert np.isclose(calculate_annualized_volatility(returns), expected)


def test_downside_deviation_exact_value():
    # Chỉ các phiên âm đóng góp: (0,02^2 + 0,04^2) / 4 = 0,0005 mỗi phiên, năm hóa nhân 252.
    returns = pd.Series([0.01, -0.02, 0.03, -0.04] * 10)
    expected = np.sqrt(0.0005 * 252)
    assert np.isclose(calculate_downside_deviation(returns, mar=0), expected)


def test_downside_deviation_uses_mar():
    returns = pd.Series([0.02] * 30)
    # Với MAR = 0,03 mọi phiên đều thấp hơn ngưỡng 0,01.
    assert np.isclose(calculate_downside_deviation(returns, mar=0.03), np.sqrt(0.01 ** 2 * 252))


@pytest.mark.parametrize("function", [calculate_annualized_volatility, calculate_downside_deviation])
def test_not_enough_observations_returns_nan(function):
    assert np.isnan(function(pd.Series([0.01, -0.01] * 9)))  # 18 quan sát < 20


def test_log_returns_are_additive():
    prices = pd.Series([100.0, 110.0, 99.0, 120.0])
    assert np.isclose(calculate_log_returns(prices).sum(), np.log(120.0 / 100.0))


# ------------------------------------------------------------
# Quy tắc 127 phiên
# ------------------------------------------------------------

def test_stock_metrics_needs_127_sessions():
    short = calculate_stock_metrics(make_price_frame("AAA", n=126))
    enough = calculate_stock_metrics(make_price_frame("AAA", n=127))
    assert np.isnan(short["return_6m"])
    assert np.isnan(short["volatility"])
    assert pd.notna(enough["return_6m"])
    assert pd.notna(enough["volatility"])


def test_stock_metrics_empty_input_returns_nan_dict():
    result = calculate_stock_metrics(pd.DataFrame())
    assert np.isnan(result["return_1m"])
    assert result["value_is_estimated"] is False


def test_stock_metrics_ignores_invalid_prices_and_duplicates():
    frame = make_price_frame("AAA", n=130)
    bad = pd.concat([frame, frame.tail(3)], ignore_index=True)  # dòng trùng ngày
    bad.loc[5, "close"] = -1.0                                   # giá không hợp lệ
    clean = calculate_stock_metrics(frame.drop(index=5))
    dirty = calculate_stock_metrics(bad)
    assert np.isclose(clean["return_6m"], dirty["return_6m"])


# ------------------------------------------------------------
# Giá trị giao dịch: ưu tiên SSI, ước tính khi thiếu, không thay bằng 0
# ------------------------------------------------------------

def _flat_frame(n=130, close=100.0, volume=1000.0, value=np.nan):
    return pd.DataFrame({
        "symbol": "AAA",
        "trading_date": pd.bdate_range("2025-01-02", periods=n),
        "close": close,
        "volume": volume,
        "value": value,
    })


def test_value_is_estimated_when_missing():
    result = calculate_stock_metrics(_flat_frame())
    assert result["value_is_estimated"] is True
    assert np.isclose(result["adtv"], 100.0 * 1000.0)


def test_value_from_ssi_is_used_and_not_flagged():
    result = calculate_stock_metrics(_flat_frame(value=555.0))
    assert result["value_is_estimated"] is False
    assert np.isclose(result["adtv"], 555.0)


def test_missing_value_and_volume_stays_nan_not_zero():
    frame = _flat_frame(volume=np.nan)
    result = calculate_stock_metrics(frame)
    assert np.isnan(result["adtv"])
    assert np.isnan(result["amihud"])


def test_zero_value_sessions_count_in_adtv_but_not_in_amihud():
    frame = _flat_frame(n=130)
    frame["close"] = np.linspace(100, 130, 130)
    frame["value"] = [0.0, 1000.0] * 65          # nửa số phiên không có giao dịch
    result = calculate_stock_metrics(frame)
    assert np.isclose(result["adtv"], 500.0)       # phiên bằng 0 vẫn nằm trong ADTV
    assert pd.notna(result["amihud"])              # Amihud chỉ tính phiên có giá trị > 0
    assert result["amihud"] > 0


def test_zero_volume_ratio():
    frame = _flat_frame(n=130)
    frame["volume"] = [0.0, 1000.0] * 65
    assert np.isclose(calculate_stock_metrics(frame)["zero_volume_ratio"], 0.5)


# ------------------------------------------------------------
# Quan hệ giữa các chỉ tiêu
# ------------------------------------------------------------

def test_reward_volatility_equals_annualized_return_over_volatility():
    result = calculate_stock_metrics(make_price_frame("AAA", n=150, seed=3))
    assert np.isclose(result["reward_volatility"], result["annualized_return_6m"] / result["volatility"])
    assert np.isclose(result["annualized_return_6m"], (1 + result["return_6m"]) ** 2 - 1)


def test_max_drawdown_is_positive_magnitude():
    frame = make_price_frame("AAA", n=150, seed=5)
    result = calculate_stock_metrics(frame)
    assert 0 <= result["max_drawdown"] < 1


# ------------------------------------------------------------
# Hiệu suất tương đối so với VNINDEX
# ------------------------------------------------------------

def _geometric(symbol, growth, n=150, start=100.0):
    return pd.DataFrame({
        "symbol": symbol,
        "trading_date": pd.bdate_range("2025-01-02", periods=n),
        "close": start * growth ** np.arange(n),
        "volume": 1000.0,
        "value": 1.0e6,
    })


def test_excess_return_against_market():
    stock = _geometric("AAA", 1.001)
    market = _geometric("VNINDEX", 1.0005, start=1000.0)
    result = calculate_stock_metrics(stock, market)
    assert np.isclose(result["excess_3m"], (1.001 ** 63 - 1) - (1.0005 ** 63 - 1))
    assert np.isclose(result["excess_6m"], (1.001 ** 126 - 1) - (1.0005 ** 126 - 1))


def test_excess_return_nan_without_market_data():
    result = calculate_stock_metrics(_geometric("AAA", 1.001), None)
    assert np.isnan(result["excess_3m"])
    assert np.isnan(result["beta"])


def test_excess_return_nan_when_few_common_dates():
    stock = _geometric("AAA", 1.001, n=150)
    market = _geometric("VNINDEX", 1.0005, n=100)   # chỉ 100 ngày chung < 127
    result = calculate_stock_metrics(stock, market)
    assert np.isnan(result["excess_6m"])


def test_beta_matches_leverage_on_log_returns():
    market = make_price_frame("VNINDEX", n=150, seed=11, drift=0.0, vol=0.01)
    log_market = np.log(market["close"]).diff().fillna(0)
    stock = market.copy()
    stock["symbol"] = "AAA"
    stock["close"] = 100 * np.exp(np.cumsum(2 * log_market))   # biến động gấp đôi thị trường
    result = calculate_stock_metrics(stock, market)
    assert np.isclose(result["beta"], 2.0, rtol=1e-6)