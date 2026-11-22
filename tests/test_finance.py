
import numpy as np
import pandas as pd

from src.finance.metrics import (
    calculate_return,
    calculate_annualized_volatility,
    calculate_downside_deviation,
    calculate_max_drawdown,
    calculate_annualized_6m_return,
    calculate_adtv,
    calculate_amihud,
    calculate_beta
)


def test_calculate_return():
    prices = pd.Series([100, 105, 110])

    result = calculate_return(
        prices,
        periods=2
    )

    assert np.isclose(result, 0.10)


def test_calculate_return_insufficient_data():
    prices = pd.Series([100, 105])

    result = calculate_return(
        prices,
        periods=2
    )

    assert np.isnan(result)


def test_annualized_volatility():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02] * 10)

    result = calculate_annualized_volatility(returns)

    assert result > 0


def test_annualized_volatility_constant_returns():
    returns = pd.Series([0.01] * 30)

    result = calculate_annualized_volatility(returns)

    assert np.isclose(result, 0)


def test_downside_deviation():
    returns = pd.Series([0.01, -0.02, 0.03, -0.04] * 10)

    result = calculate_downside_deviation(returns)

    assert result > 0


def test_downside_deviation_no_negative_returns():
    returns = pd.Series([0.01, 0.02, 0.03] * 10)

    result = calculate_downside_deviation(returns)

    assert np.isclose(result, 0)


def test_max_drawdown():
    prices = pd.Series([100, 120, 90, 110])

    result = calculate_max_drawdown(prices)

    assert np.isclose(result, 0.25)


def test_max_drawdown_increasing_prices():
    prices = pd.Series([100, 110, 120, 130])

    result = calculate_max_drawdown(prices)

    assert np.isclose(result, 0)


def test_annualized_6m_return():
    result = calculate_annualized_6m_return(0.10)

    assert np.isclose(result, 0.21)


def test_adtv():
    values = pd.Series([100, 200, 300])

    result = calculate_adtv(values)

    assert np.isclose(result, 200)


def test_adtv_all_missing():
    values = pd.Series([np.nan, np.nan])

    result = calculate_adtv(values)

    assert np.isnan(result)


def test_amihud():
    returns = pd.Series([0.01, 0.02, 0.03])
    values = pd.Series([100, 100, 100])

    result = calculate_amihud(
        returns,
        values
    )

    assert np.isclose(result, 0.0002)


def test_amihud_ignores_non_positive_value():
    returns = pd.Series([0.01, 0.02, 0.03])
    values = pd.Series([100, 0, np.nan])

    result = calculate_amihud(
        returns,
        values
    )

    assert np.isclose(result, 0.0001)


def test_beta():
    market = pd.Series(np.linspace(-0.02, 0.02, 40))
    stock = 2 * market

    result = calculate_beta(
        stock,
        market
    )

    assert np.isclose(result, 2.0)


def test_beta_constant_market_returns():
    market = pd.Series([0.01] * 40)
    stock = pd.Series([0.02] * 40)

    result = calculate_beta(
        stock,
        market
    )

    assert np.isnan(result)
