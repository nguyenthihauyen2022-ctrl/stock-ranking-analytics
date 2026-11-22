
import numpy as np
import pandas as pd

from src.analytics.ranking import (
    percentile_score,
    calculate_factor_scores,
    classify_score
)


def test_percentile_score():
    values = pd.Series([10, 20, 30, 40, 50])

    result = percentile_score(
        values,
        higher_is_better=True
    )

    assert result.iloc[-1] > result.iloc[0]
    assert result.between(0, 100).all()


def test_reverse_percentile_score():
    values = pd.Series([10, 20, 30, 40, 50])

    result = percentile_score(
        values,
        higher_is_better=False
    )

    assert result.iloc[0] > result.iloc[-1]
    assert result.between(0, 100).all()


def test_percentile_score_with_missing_values():
    values = pd.Series([10, np.nan, 30, 40])

    result = percentile_score(
        values,
        higher_is_better=True
    )

    assert pd.isna(result.iloc[1])
    assert result.iloc[3] > result.iloc[0]


def test_percentile_score_single_observation():
    values = pd.Series([10])

    result = percentile_score(values)

    assert result.iloc[0] == 50


def test_percentile_score_with_equal_values():
    values = pd.Series([10, 10, 20, 20])

    result = percentile_score(values)

    assert result.iloc[0] == result.iloc[1]
    assert result.iloc[2] == result.iloc[3]


def test_percentile_score_all_missing():
    values = pd.Series([np.nan, np.nan])

    result = percentile_score(values)

    assert result.isna().all()


def test_factor_scores():
    df = pd.DataFrame({
        "return_1m": [0.01, 0.02, 0.03],
        "return_3m": [0.02, 0.03, 0.04],
        "return_6m": [0.03, 0.04, 0.05],
        "reward_volatility": [0.1, 0.2, 0.3],
        "volatility": [0.3, 0.2, 0.1],
        "max_drawdown": [0.3, 0.2, 0.1],
        "downside_deviation": [0.2, 0.1, 0.05],
        "adtv": [100, 200, 300],
        "amihud": [0.3, 0.2, 0.1],
        "excess_3m": [0.01, 0.02, 0.03],
        "excess_6m": [0.01, 0.02, 0.03]
    })

    result = calculate_factor_scores(df)

    expected_columns = [
        "score_momentum",
        "score_risk_adjusted",
        "score_downside",
        "score_liquidity",
        "score_relative"
    ]

    for column in expected_columns:
        assert column in result.columns
        assert result[column].between(0, 100).all()


def test_liquidity_score_requires_both_metrics():
    df = pd.DataFrame({
        "return_1m": [0.01, 0.02],
        "return_3m": [0.02, 0.03],
        "return_6m": [0.03, 0.04],
        "reward_volatility": [0.1, 0.2],
        "volatility": [0.3, 0.2],
        "max_drawdown": [0.3, 0.2],
        "downside_deviation": [0.2, 0.1],
        "adtv": [100, 200],
        "amihud": [np.nan, 0.2],
        "excess_3m": [0.01, 0.02],
        "excess_6m": [0.01, 0.02]
    })

    result = calculate_factor_scores(df)

    assert pd.isna(result.loc[0, "score_liquidity"])
    assert pd.notna(result.loc[1, "score_liquidity"])


def test_missing_column_does_not_crash():
    df = pd.DataFrame({
        "return_1m": [0.01, 0.02],
        "return_3m": [0.02, 0.03]
    })

    result = calculate_factor_scores(df)

    assert "score_momentum" in result.columns
    assert result["score_momentum"].isna().all()


def test_classify_score():
    assert classify_score(85) == "Cao"
    assert classify_score(70) == "Khá cao"
    assert classify_score(55) == "Trung bình"
    assert classify_score(40) == "Thấp"
    assert classify_score(np.nan) == "Chưa đủ dữ liệu"
