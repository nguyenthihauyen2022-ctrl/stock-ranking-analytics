"""Kiểm thử build_ranking trên dữ liệu giả lập: điều kiện xếp hạng, tổng điểm, thứ hạng."""

import numpy as np
import pandas as pd
import pytest

from src.analytics import ranking as ranking_module
from src.analytics.ranking import WEIGHTS, build_ranking, classify_score, validate_model_weights
from tests.helpers import make_market_and_stocks, make_price_frame

SYMBOLS = [f"S{index:02d}" for index in range(12)]


@pytest.fixture(scope="module")
def full_ranking():
    prices, securities = make_market_and_stocks(SYMBOLS, n=150)
    return build_ranking(prices, securities)


def test_weights_sum_to_one():
    validate_model_weights()
    assert np.isclose(sum(WEIGHTS.values()), 1.0)


def test_validate_model_weights_rejects_bad_total(monkeypatch):
    monkeypatch.setitem(WEIGHTS, "score_momentum", 0.50)
    with pytest.raises(ValueError):
        validate_model_weights()


def test_all_stocks_with_enough_data_are_eligible(full_ranking):
    assert len(full_ranking) == len(SYMBOLS)
    assert full_ranking["eligible"].all()


def test_vnindex_is_not_ranked(full_ranking):
    assert "VNINDEX" not in set(full_ranking["symbol"])


def test_total_score_is_weighted_sum_of_factor_scores(full_ranking):
    expected = sum(full_ranking[column] * weight for column, weight in WEIGHTS.items())
    assert np.allclose(full_ranking["total_score"], expected)


def test_scores_are_within_0_and_100(full_ranking):
    for column in list(WEIGHTS) + ["total_score"]:
        assert full_ranking[column].between(0, 100).all()


def test_rank_follows_total_score(full_ranking):
    ordered = full_ranking.sort_values("total_score", ascending=False)
    assert list(ordered["rank"]) == sorted(ordered["rank"])
    assert full_ranking["rank"].min() == 1
    best = full_ranking.loc[full_ranking["total_score"].idxmax(), "rank"]
    assert best == 1


def test_result_is_sorted_by_score_descending(full_ranking):
    assert full_ranking["total_score"].is_monotonic_decreasing


def test_rating_matches_classify_score(full_ranking):
    assert all(full_ranking["rating"] == full_ranking["total_score"].apply(classify_score))


def test_short_history_is_not_eligible_and_not_zero_scored():
    prices, securities = make_market_and_stocks(SYMBOLS[:6], n=150)
    short = make_price_frame("SHORT", n=100, seed=77)
    prices = pd.concat([prices, short], ignore_index=True)
    securities = pd.concat([securities, pd.DataFrame({
        "symbol": ["SHORT"], "name": ["Mã ngắn"], "board": ["HNX"], "icb_name": [None]})],
        ignore_index=True)

    result = build_ranking(prices, securities)
    row = result[result["symbol"] == "SHORT"].iloc[0]

    assert bool(row["eligible"]) is False
    assert np.isnan(row["total_score"])           # không bị gán điểm 0
    assert np.isnan(row["rank"])
    assert row["rating"] == "Chưa đủ dữ liệu"
    assert result.index[result["symbol"] == "SHORT"][0] == len(result) - 1   # nằm sau các mã đủ điều kiện
    assert result["eligible"].sum() == 6


def test_missing_value_and_volume_makes_stock_not_eligible():
    prices, securities = make_market_and_stocks(SYMBOLS[:6], n=150)
    mask = prices["symbol"] == "S00"
    prices.loc[mask, ["value", "volume"]] = np.nan   # không có dữ liệu để tính thanh khoản
    result = build_ranking(prices, securities)
    row = result[result["symbol"] == "S00"].iloc[0]
    assert bool(row["eligible"]) is False
    assert np.isnan(row["score_liquidity"])
    assert result["eligible"].sum() == 5


def test_symbols_not_in_securities_are_excluded():
    prices, securities = make_market_and_stocks(SYMBOLS[:6], n=150)
    extra = make_price_frame("GHOST", n=150, seed=55)     # có giá nhưng không có trong danh sách
    result = build_ranking(pd.concat([prices, extra], ignore_index=True), securities)
    assert "GHOST" not in set(result["symbol"])


def test_duplicate_price_rows_do_not_change_result(full_ranking):
    prices, securities = make_market_and_stocks(SYMBOLS, n=150)
    duplicated = pd.concat([prices, prices.tail(40)], ignore_index=True)
    result = build_ranking(duplicated, securities)
    merged = full_ranking.merge(result, on="symbol", suffixes=("_a", "_b"))
    assert np.allclose(merged["total_score_a"], merged["total_score_b"])


@pytest.mark.parametrize("prices, securities", [
    (None, None),
    (pd.DataFrame(), pd.DataFrame()),
    (pd.DataFrame({"symbol": ["A"]}), pd.DataFrame({"symbol": ["A"]})),   # thiếu cột giá
])
def test_build_ranking_handles_empty_or_invalid_input(prices, securities):
    assert build_ranking(prices, securities).empty


def test_ranking_module_exposes_expected_columns(full_ranking):
    expected = {"symbol", "name", "board", "eligible", "total_score", "rating", "rank", *WEIGHTS}
    assert expected.issubset(full_ranking.columns)
    assert ranking_module.FACTOR_COMPONENTS.keys() == WEIGHTS.keys()


@pytest.mark.parametrize("score, expected", [
    (100, "Cao"), (80, "Cao"), (79.99, "Khá cao"),
    (65, "Khá cao"), (64.99, "Trung bình"),
    (50, "Trung bình"), (49.99, "Thấp"), (0, "Thấp"),
])
def test_classify_score_boundaries(score, expected):
    assert classify_score(score) == expected