
import numpy as np
import pandas as pd

from src.finance.metrics import calculate_stock_metrics


# ============================================================
# TRỌNG SỐ MÔ HÌNH
# ============================================================

WEIGHTS = {
    "score_momentum": 0.25,
    "score_risk_adjusted": 0.25,
    "score_downside": 0.20,
    "score_liquidity": 0.15,
    "score_relative": 0.15,
}

FACTOR_COMPONENTS = {
    "score_momentum": [
        ("s_1m", 0.20),
        ("s_3m", 0.30),
        ("s_6m", 0.50),
    ],
    "score_risk_adjusted": [
        ("s_reward_volatility", 0.70),
        ("s_volatility", 0.30),
    ],
    "score_downside": [
        ("s_max_drawdown", 0.50),
        ("s_downside_deviation", 0.50),
    ],
    "score_liquidity": [
        ("s_adtv", 0.60),
        ("s_amihud", 0.40),
    ],
    "score_relative": [
        ("s_excess_3m", 0.70),
        ("s_excess_6m", 0.30),
    ],
}

REQUIRED_METRIC_COLUMNS = [
    "return_1m",
    "return_3m",
    "return_6m",
    "reward_volatility",
    "volatility",
    "max_drawdown",
    "downside_deviation",
    "adtv",
    "amihud",
    "excess_3m",
    "excess_6m",
]

SECURITY_COLUMNS = [
    "symbol",
    "name",
    "board",
    "icb_name",
]


# ============================================================
# KIỂM TRA TRỌNG SỐ
# ============================================================

def validate_model_weights():
    total_weight = sum(WEIGHTS.values())

    if not np.isclose(total_weight, 1.0):
        raise ValueError(
            "Tổng trọng số mô hình phải bằng 1."
        )

    if set(WEIGHTS) != set(FACTOR_COMPONENTS):
        raise ValueError(
            "Các nhóm trọng số không đồng nhất."
        )

    for factor, components in FACTOR_COMPONENTS.items():
        component_weight = sum(
            weight for _, weight in components
        )

        if not np.isclose(component_weight, 1.0):
            raise ValueError(
                f"Tổng trọng số thành phần của {factor} phải bằng 1."
            )

        for column, weight in components:
            if not np.isfinite(weight) or weight < 0:
                raise ValueError(
                    f"Trọng số không hợp lệ: {factor} - {column}"
                )


# ============================================================
# CHUẨN HÓA GIÁ TRỊ SỐ
# ============================================================

def _clean_numeric_series(series):
    values = pd.to_numeric(
        series,
        errors="coerce"
    ).astype(float)

    return values.replace(
        [np.inf, -np.inf],
        np.nan
    )


# ============================================================
# CHẤM ĐIỂM PERCENTILE
# ============================================================

def percentile_score(
    series,
    higher_is_better=True
):
    """
    Chuyển chỉ tiêu gốc thành điểm percentile 0-100.

    higher_is_better=True:
        Giá trị cao hơn có điểm cao hơn.

    higher_is_better=False:
        Giá trị thấp hơn có điểm cao hơn.

    Giá trị thiếu được giữ là NaN.
    """

    values = _clean_numeric_series(series)

    result = pd.Series(
        np.nan,
        index=values.index,
        dtype=float,
    )

    valid = values.dropna()

    if valid.empty:
        return result

    if len(valid) == 1:
        result.loc[valid.index] = 50.0
        return result

    ranks = valid.rank(
        method="average",
        ascending=True,
        pct=True,
    )

    if higher_is_better:
        scores = ranks * 100
    else:
        scores = (1 - ranks) * 100

    result.loc[scores.index] = scores

    return result


# ============================================================
# TÍNH ĐIỂM NHÂN TỐ
# ============================================================

def _weighted_score(
    df,
    components,
):
    """
    Chỉ tính điểm nhân tố khi tất cả thành phần
    của nhân tố đều có dữ liệu hợp lệ.
    """

    result = pd.Series(
        np.nan,
        index=df.index,
        dtype=float,
    )

    columns = [
        column for column, _ in components
    ]

    if not all(column in df.columns for column in columns):
        return result

    component_data = df[columns].copy()

    for column in columns:
        component_data[column] = _clean_numeric_series(
            component_data[column]
        )

    available = component_data.notna().all(axis=1)

    if not available.any():
        return result

    weighted_total = pd.Series(
        0.0,
        index=df.index,
        dtype=float,
    )

    for column, weight in components:
        weighted_total += (
            component_data[column].fillna(0) * weight
        )

    result.loc[available] = weighted_total.loc[available]

    return result


# ============================================================
# TÍNH ĐIỂM 5 NHÓM TIÊU CHÍ
# ============================================================

def calculate_factor_scores(df):
    result = df.copy()

    for column in REQUIRED_METRIC_COLUMNS:
        if column not in result.columns:
            result[column] = np.nan

        result[column] = _clean_numeric_series(
            result[column]
        )

    # --------------------------------------------------------
    # 1. MOMENTUM
    # --------------------------------------------------------

    result["s_1m"] = percentile_score(
        result["return_1m"],
        higher_is_better=True,
    )

    result["s_3m"] = percentile_score(
        result["return_3m"],
        higher_is_better=True,
    )

    result["s_6m"] = percentile_score(
        result["return_6m"],
        higher_is_better=True,
    )

    result["score_momentum"] = _weighted_score(
        result,
        FACTOR_COMPONENTS["score_momentum"],
    )

    # --------------------------------------------------------
    # 2. RISK-ADJUSTED PERFORMANCE
    # --------------------------------------------------------

    result["s_reward_volatility"] = percentile_score(
        result["reward_volatility"],
        higher_is_better=True,
    )

    result["s_volatility"] = percentile_score(
        result["volatility"],
        higher_is_better=False,
    )

    result["score_risk_adjusted"] = _weighted_score(
        result,
        FACTOR_COMPONENTS["score_risk_adjusted"],
    )

    # --------------------------------------------------------
    # 3. DOWNSIDE RISK
    # --------------------------------------------------------

    result["s_max_drawdown"] = percentile_score(
        result["max_drawdown"],
        higher_is_better=False,
    )

    result["s_downside_deviation"] = percentile_score(
        result["downside_deviation"],
        higher_is_better=False,
    )

    result["score_downside"] = _weighted_score(
        result,
        FACTOR_COMPONENTS["score_downside"],
    )

    # --------------------------------------------------------
    # 4. LIQUIDITY
    # --------------------------------------------------------

    result["s_adtv"] = percentile_score(
        result["adtv"],
        higher_is_better=True,
    )

    result["s_amihud"] = percentile_score(
        result["amihud"],
        higher_is_better=False,
    )

    result["score_liquidity"] = _weighted_score(
        result,
        FACTOR_COMPONENTS["score_liquidity"],
    )

    # --------------------------------------------------------
    # 5. RELATIVE MARKET PERFORMANCE
    # --------------------------------------------------------

    result["s_excess_3m"] = percentile_score(
        result["excess_3m"],
        higher_is_better=True,
    )

    result["s_excess_6m"] = percentile_score(
        result["excess_6m"],
        higher_is_better=True,
    )

    result["score_relative"] = _weighted_score(
        result,
        FACTOR_COMPONENTS["score_relative"],
    )

    return result


# ============================================================
# PHÂN LOẠI ĐIỂM
# ============================================================

def classify_score(score):
    if pd.isna(score):
        return "Chưa đủ dữ liệu"

    if score >= 80:
        return "Cao"

    if score >= 65:
        return "Khá cao"

    if score >= 50:
        return "Trung bình"

    return "Thấp"


# ============================================================
# CHUẨN HÓA DỮ LIỆU CHỨNG KHOÁN
# ============================================================

def _prepare_securities(securities):
    if (
        securities is None
        or not isinstance(securities, pd.DataFrame)
        or securities.empty
        or "symbol" not in securities.columns
    ):
        return pd.DataFrame()

    data = securities.copy()

    for column in SECURITY_COLUMNS:
        if column not in data.columns:
            data[column] = None

    data["symbol"] = (
        data["symbol"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    data = data.dropna(subset=["symbol"])

    data = data[
        data["symbol"] != ""
    ].copy()

    data = data.drop_duplicates(
        subset=["symbol"],
        keep="last",
    )

    return data[SECURITY_COLUMNS].reset_index(drop=True)


# ============================================================
# CHUẨN HÓA DỮ LIỆU GIÁ
# ============================================================

def _prepare_prices(prices):
    if (
        prices is None
        or not isinstance(prices, pd.DataFrame)
        or prices.empty
    ):
        return pd.DataFrame()

    required = {"symbol", "trading_date", "close"}

    if not required.issubset(prices.columns):
        return pd.DataFrame()

    data = prices.copy()

    data["symbol"] = (
        data["symbol"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    data["trading_date"] = pd.to_datetime(
        data["trading_date"],
        errors="coerce",
    )

    data["close"] = pd.to_numeric(
        data["close"],
        errors="coerce",
    )

    data = data.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    data = data.dropna(
        subset=["symbol", "trading_date", "close"]
    )

    data = data[
        (data["symbol"] != "")
        & (data["close"] > 0)
    ].copy()

    data = data.sort_values(
        ["symbol", "trading_date"]
    )

    data = data.drop_duplicates(
        subset=["symbol", "trading_date"],
        keep="last",
    )

    return data.reset_index(drop=True)


# ============================================================
# XÂY DỰNG BẢNG XẾP HẠNG
# ============================================================

def build_ranking(
    prices,
    securities=None,
):
    """
    Xây dựng bảng xếp hạng cổ phiếu.

    Đầu vào:
        prices: dữ liệu giá của cổ phiếu và VNINDEX.
        securities: danh sách chứng khoán hiện tại.

    Đầu ra:
        Bảng chỉ tiêu, điểm 5 nhân tố, điểm tổng hợp,
        trạng thái đủ điều kiện và thứ hạng.
    """

    validate_model_weights()

    securities_data = _prepare_securities(securities)
    prices_data = _prepare_prices(prices)

    if securities_data.empty or prices_data.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # TÁCH VNINDEX
    # --------------------------------------------------------

    market_df = prices_data[
        prices_data["symbol"] == "VNINDEX"
    ].copy()

    # --------------------------------------------------------
    # CHỈ LẤY CỔ PHIẾU THUỘC DANH SÁCH HIỆN TẠI
    # --------------------------------------------------------

    valid_symbols = set(
        securities_data["symbol"]
    )

    stock_prices = prices_data[
        prices_data["symbol"].isin(valid_symbols)
    ].copy()

    if stock_prices.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # TÍNH CHỈ TIÊU TỪNG CỔ PHIẾU
    # --------------------------------------------------------

    metric_rows = []

    for symbol, group in stock_prices.groupby(
        "symbol",
        sort=True,
    ):
        group = group.sort_values(
            "trading_date"
        ).reset_index(drop=True)

        try:
            metrics = calculate_stock_metrics(
                group,
                market_df,
            )
        except Exception as exc:
            # Không làm dừng toàn bộ bảng xếp hạng
            # chỉ vì một mã có dữ liệu lỗi.
            print(
                f"[RANKING] Không tính được {symbol}: {exc}"
            )
            continue

        if not isinstance(metrics, dict):
            continue

        row = metrics.copy()
        row["symbol"] = symbol

        metric_rows.append(row)

    if not metric_rows:
        return pd.DataFrame()

    metrics_df = pd.DataFrame(metric_rows)

    # --------------------------------------------------------
    # ĐẢM BẢO CÓ ĐỦ CỘT CHỈ TIÊU
    # --------------------------------------------------------

    for column in REQUIRED_METRIC_COLUMNS:
        if column not in metrics_df.columns:
            metrics_df[column] = np.nan

    # --------------------------------------------------------
    # GHÉP THÔNG TIN DOANH NGHIỆP
    # --------------------------------------------------------

    ranking = metrics_df.merge(
        securities_data,
        on="symbol",
        how="inner",
        validate="one_to_one",
    )

    if ranking.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # TÍNH ĐIỂM 5 NHÂN TỐ
    # --------------------------------------------------------

    ranking = calculate_factor_scores(ranking)

    score_columns = list(WEIGHTS.keys())

    # --------------------------------------------------------
    # XÁC ĐỊNH CỔ PHIẾU ĐỦ ĐIỀU KIỆN
    # --------------------------------------------------------

    ranking["eligible"] = (
        ranking[score_columns]
        .notna()
        .all(axis=1)
    )

    ranking["total_score"] = np.nan

    eligible_mask = ranking["eligible"]

    # --------------------------------------------------------
    # TÍNH ĐIỂM TỔNG HỢP
    # --------------------------------------------------------

    if eligible_mask.any():
        total_score = pd.Series(
            0.0,
            index=ranking.index,
        )

        for column, weight in WEIGHTS.items():
            total_score.loc[eligible_mask] += (
                ranking.loc[eligible_mask, column] * weight
            )

        ranking.loc[
            eligible_mask,
            "total_score",
        ] = total_score.loc[eligible_mask]

    # --------------------------------------------------------
    # PHÂN LOẠI
    # --------------------------------------------------------

    ranking["rating"] = ranking[
        "total_score"
    ].apply(classify_score)

    # --------------------------------------------------------
    # XẾP HẠNG
    # --------------------------------------------------------

    ranking["rank"] = np.nan

    if eligible_mask.any():
        ranking.loc[
            eligible_mask,
            "rank",
        ] = (
            ranking.loc[
                eligible_mask,
                "total_score",
            ]
            .rank(
                ascending=False,
                method="min",
            )
        )

    # --------------------------------------------------------
    # SẮP XẾP
    # --------------------------------------------------------

    ranking = ranking.sort_values(
        ["eligible", "total_score", "symbol"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)

    return ranking
