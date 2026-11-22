"""Kiểm thử phân tích độ nhạy trọng số (src/analytics/validation.py)."""

import numpy as np
import pandas as pd
import pytest

from src.analytics.ranking import WEIGHTS
from src.analytics.validation import DEFAULT_SCENARIOS, weight_sensitivity

FACTORS = list(WEIGHTS)


def make_scores(n=15, seed=0):
    rng = np.random.default_rng(seed)
    data = {factor: rng.uniform(0, 100, n) for factor in FACTORS}
    data["symbol"] = [f"S{i:02d}" for i in range(n)]
    data["eligible"] = True
    return pd.DataFrame(data)


def test_base_scenario_reproduces_baseline_ranking():
    result = weight_sensitivity(make_scores())
    base = result[result["scenario"] == "Base"].iloc[0]
    assert np.isclose(base["spearman_correlation"], 1.0)
    assert base["top_n_overlap_pct"] == 100
    assert base["mean_abs_rank_change"] == 0
    assert base["max_abs_rank_change"] == 0


def test_result_has_one_row_per_default_scenario():
    result = weight_sensitivity(make_scores())
    assert list(result["scenario"]) == list(DEFAULT_SCENARIOS)
    assert (result["stock_count"] == 15).all()
    assert result["spearman_correlation"].between(-1, 1).all()


def test_opposite_factor_ordering_gives_negative_correlation():
    # Momentum tăng dần, bốn nhân tố còn lại giảm dần: trọng số dồn vào momentum đảo thứ hạng.
    scores = pd.DataFrame({"symbol": list("ABCDEF"), "eligible": True})
    scores["score_momentum"] = [10, 20, 30, 40, 50, 60]
    for factor in FACTORS[1:]:
        scores[factor] = [60, 50, 40, 30, 20, 10]
    only_momentum = {factor: 0.0 for factor in FACTORS}
    only_momentum["score_momentum"] = 1.0

    result = weight_sensitivity(scores, scenarios={"Chỉ momentum": only_momentum})
    assert np.isclose(result.iloc[0]["spearman_correlation"], -1.0)


def test_top_n_is_capped_by_number_of_stocks():
    result = weight_sensitivity(make_scores(n=5), top_n=10)
    assert (result["top_n"] == 5).all()


@pytest.mark.parametrize("bad_weights", [
    {factor: 0.3 for factor in FACTORS},                                   # tổng khác 1
    {**{factor: 0.25 for factor in FACTORS[:4]}},                          # thiếu nhân tố
    {**{factor: 0.2 for factor in FACTORS}, "score_momentum": -0.2},       # trọng số âm
    {**{factor: 0.2 for factor in FACTORS}, "score_momentum": np.nan},     # không hữu hạn
])
def test_invalid_scenario_weights_raise(bad_weights):
    with pytest.raises(ValueError):
        weight_sensitivity(make_scores(), scenarios={"Sai": bad_weights})


@pytest.mark.parametrize("top_n", [0, -1, 2.5, True])
def test_invalid_top_n_raises(top_n):
    with pytest.raises(ValueError):
        weight_sensitivity(make_scores(), top_n=top_n)


def test_scenarios_must_be_a_dictionary():
    with pytest.raises(ValueError):
        weight_sensitivity(make_scores(), scenarios=[1, 2])


@pytest.mark.parametrize("ranking", [
    None,
    pd.DataFrame(),
    make_scores(n=1),                                   # chưa đủ 2 cổ phiếu
    make_scores().drop(columns=["score_downside"]),     # thiếu cột điểm
])
def test_returns_empty_when_data_is_insufficient(ranking):
    assert weight_sensitivity(ranking).empty


def test_only_eligible_stocks_with_full_scores_are_used():
    scores = make_scores(n=10)
    scores.loc[0:2, "eligible"] = False
    scores.loc[3, "score_liquidity"] = np.nan
    result = weight_sensitivity(scores)
    assert (result["stock_count"] == 6).all()


def test_eligible_column_may_be_text():
    scores = make_scores(n=10)
    scores["eligible"] = ["True", "False"] * 5
    assert (weight_sensitivity(scores)["stock_count"] == 5).all()