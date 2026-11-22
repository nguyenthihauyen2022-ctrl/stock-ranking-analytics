
import numpy as np
import pandas as pd

from scipy.stats import spearmanr

from src.analytics.ranking import WEIGHTS


# ============================================================
# CÁC KỊCH BẢN THAY ĐỔI TRỌNG SỐ
# ============================================================

DEFAULT_SCENARIOS = {
    "Base": {
        "score_momentum": 0.25,
        "score_risk_adjusted": 0.25,
        "score_downside": 0.20,
        "score_liquidity": 0.15,
        "score_relative": 0.15,
    },

    "Higher Momentum": {
        "score_momentum": 0.35,
        "score_risk_adjusted": 0.20,
        "score_downside": 0.15,
        "score_liquidity": 0.15,
        "score_relative": 0.15,
    },

    "Higher Risk-adjusted Performance": {
        "score_momentum": 0.20,
        "score_risk_adjusted": 0.35,
        "score_downside": 0.20,
        "score_liquidity": 0.10,
        "score_relative": 0.15,
    },

    "Higher Liquidity": {
        "score_momentum": 0.20,
        "score_risk_adjusted": 0.20,
        "score_downside": 0.15,
        "score_liquidity": 0.30,
        "score_relative": 0.15,
    },
}


# ============================================================
# CHUẨN BỊ DỮ LIỆU KIỂM ĐỊNH
# ============================================================

def _prepare_validation_data(ranking):

    if (
        ranking is None
        or not isinstance(ranking, pd.DataFrame)
        or ranking.empty
    ):
        return pd.DataFrame()

    required_columns = [
        "symbol",
        "score_momentum",
        "score_risk_adjusted",
        "score_downside",
        "score_liquidity",
        "score_relative",
    ]

    if not all(
        column in ranking.columns
        for column in required_columns
    ):
        return pd.DataFrame()

    data = ranking.copy()

    # Chỉ giữ cổ phiếu đủ điều kiện nếu có cột eligible
    if "eligible" in data.columns:

        eligible = data["eligible"]

        if eligible.dtype == bool:
            data = data[eligible].copy()

        else:
            eligible_text = (
                eligible.astype(str)
                .str.strip()
                .str.lower()
            )

            data = data[
                eligible_text.isin(["true", "1", "yes"])
            ].copy()

    # Chuẩn hóa mã cổ phiếu
    data["symbol"] = (
        data["symbol"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    data = data.dropna(
        subset=["symbol"]
    )

    data = data[
        data["symbol"] != ""
    ].copy()

    score_columns = [
        "score_momentum",
        "score_risk_adjusted",
        "score_downside",
        "score_liquidity",
        "score_relative",
    ]

    # Chuyển điểm thành kiểu số
    for column in score_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    # Loại bỏ giá trị vô hạn
    data = data.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    # Chỉ giữ cổ phiếu có đầy đủ 5 nhóm điểm
    data = data.dropna(
        subset=score_columns
    )

    # Loại bỏ mã cổ phiếu trùng lặp
    data = data.drop_duplicates(
        subset=["symbol"],
        keep="last",
    )

    return data.reset_index(drop=True)


# ============================================================
# KIỂM TRA TRỌNG SỐ KỊCH BẢN
# ============================================================

def _validate_scenario_weights(weights):

    if not isinstance(weights, dict):
        return False

    if set(weights.keys()) != set(WEIGHTS.keys()):
        return False

    try:
        values = np.array(
            list(weights.values()),
            dtype=float,
        )
    except (TypeError, ValueError):
        return False

    if not np.isfinite(values).all():
        return False

    if (values < 0).any():
        return False

    return bool(
        np.isclose(values.sum(), 1.0)
    )


# ============================================================
# TÍNH ĐIỂM THEO KỊCH BẢN
# ============================================================

def _calculate_scenario_score(
    data,
    weights,
):

    score = pd.Series(
        0.0,
        index=data.index,
        dtype=float,
    )

    for factor, weight in weights.items():
        score += data[factor] * weight

    return score


# ============================================================
# XẾP HẠNG CỔ PHIẾU
# ============================================================

def _calculate_rank(data, score_column):

    result = data.copy()

    result["rank"] = (
        result[score_column]
        .rank(
            ascending=False,
            method="min",
        )
    )

    return result


# ============================================================
# TÍNH TƯƠNG QUAN THỨ HẠNG SPEARMAN
# ============================================================

def _calculate_spearman(
    baseline_rank,
    scenario_rank,
):

    if (
        baseline_rank is None
        or scenario_rank is None
        or len(baseline_rank) < 2
        or len(scenario_rank) < 2
    ):
        return np.nan

    result = spearmanr(
        baseline_rank,
        scenario_rank,
    )

    correlation = (
        result.statistic
        if hasattr(result, "statistic")
        else result[0]
    )

    if not np.isfinite(correlation):
        return np.nan

    return float(correlation)


# ============================================================
# PHÂN TÍCH ĐỘ NHẠY TRỌNG SỐ
# ============================================================

def weight_sensitivity(
    ranking,
    scenarios=None,
    top_n=10,
):

    """
    Đánh giá độ nhạy của thứ hạng khi thay đổi
    trọng số các nhóm tiêu chí.

    Chỉ số:
    - Spearman correlation.
    - Top-N overlap.
    - Top-N overlap percentage.
    - Mean absolute rank change.
    - Maximum absolute rank change.

    Đây là kiểm tra độ nhạy trọng số,
    không phải kiểm định ngoài mẫu.
    """

    data = _prepare_validation_data(
        ranking
    )

    if data.empty or len(data) < 2:
        return pd.DataFrame()

    if scenarios is None:
        scenarios = DEFAULT_SCENARIOS

    if not isinstance(scenarios, dict):
        raise ValueError(
            "scenarios phải là dictionary."
        )

    if (
        isinstance(top_n, bool)
        or not isinstance(top_n, int)
        or top_n < 1
    ):
        raise ValueError(
            "top_n phải là số nguyên dương."
        )

    # Kiểm tra toàn bộ trọng số kịch bản trước khi tính
    for scenario_name, scenario_weights in scenarios.items():

        if not _validate_scenario_weights(
            scenario_weights
        ):
            raise ValueError(
                f"Trọng số không hợp lệ trong kịch bản: "
                f"{scenario_name}"
            )

    # --------------------------------------------------------
    # XẾP HẠNG CƠ SỞ
    # --------------------------------------------------------

    baseline_weights = WEIGHTS.copy()

    baseline_score = _calculate_scenario_score(
        data,
        baseline_weights,
    )

    baseline = pd.DataFrame({
        "symbol": data["symbol"],
        "score": baseline_score,
    })

    baseline = _calculate_rank(
        baseline,
        "score",
    )

    baseline = baseline.sort_values(
        ["rank", "symbol"],
        ascending=[True, True],
    ).reset_index(drop=True)

    baseline_top = set(
        baseline.head(
            min(top_n, len(baseline))
        )["symbol"]
    )

    effective_top_n = min(
        top_n,
        len(baseline),
    )

    results = []

    # --------------------------------------------------------
    # TÍNH TOÁN TỪNG KỊCH BẢN
    # --------------------------------------------------------

    for scenario_name, scenario_weights in scenarios.items():

        scenario_score = _calculate_scenario_score(
            data,
            scenario_weights,
        )

        scenario = pd.DataFrame({
            "symbol": data["symbol"],
            "score": scenario_score,
        })

        scenario = _calculate_rank(
            scenario,
            "score",
        )

        scenario = scenario.sort_values(
            ["rank", "symbol"],
            ascending=[True, True],
        ).reset_index(drop=True)

        # ----------------------------------------------------
        # SO SÁNH THỨ HẠNG
        # ----------------------------------------------------

        comparison = baseline[
            ["symbol", "rank"]
        ].rename(
            columns={"rank": "rank_base"}
        ).merge(
            scenario[
                ["symbol", "rank"]
            ].rename(
                columns={"rank": "rank_scenario"}
            ),
            on="symbol",
            how="inner",
            validate="one_to_one",
        )

        correlation = _calculate_spearman(
            comparison["rank_base"],
            comparison["rank_scenario"],
        )

        # ----------------------------------------------------
        # TOP-N OVERLAP
        # ----------------------------------------------------

        scenario_top = set(
            scenario.head(effective_top_n)["symbol"]
        )

        overlap = len(
            baseline_top.intersection(scenario_top)
        )

        overlap_pct = (
            overlap / effective_top_n * 100
            if effective_top_n > 0
            else np.nan
        )

        # ----------------------------------------------------
        # THAY ĐỔI THỨ HẠNG
        # ----------------------------------------------------

        rank_change = (
            comparison["rank_scenario"]
            - comparison["rank_base"]
        ).abs()

        results.append({
            "scenario": scenario_name,

            "spearman_correlation": correlation,

            "top_n": effective_top_n,

            "top_n_overlap": overlap,

            "top_n_overlap_pct": overlap_pct,

            "mean_abs_rank_change": (
                float(rank_change.mean())
                if not rank_change.empty
                else np.nan
            ),

            "max_abs_rank_change": (
                float(rank_change.max())
                if not rank_change.empty
                else np.nan
            ),

            "stock_count": len(comparison),
        })

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results)
