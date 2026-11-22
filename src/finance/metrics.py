# ============================================================
# src/finance/metrics.py
# TÍNH TOÁN CÁC CHỈ TIÊU TÀI CHÍNH VÀ RỦI RO CỔ PHIẾU
# ============================================================

import numpy as np
import pandas as pd


# ============================================================
# 1. CẤU HÌNH
# ============================================================

TRADING_DAYS = 252

PERIOD_1M = 21
PERIOD_3M = 63
PERIOD_6M = 126

MIN_HISTORY = PERIOD_6M + 1
MIN_RETURN_OBSERVATIONS = 20
MIN_BETA_OBSERVATIONS = 30


# ============================================================
# 2. HÀM CHUẨN HÓA DỮ LIỆU
# ============================================================

def _to_numeric(series):
    """
    Chuyển dữ liệu sang dạng số.
    Các giá trị không hợp lệ được chuyển thành NaN.
    """
    return pd.to_numeric(series, errors="coerce").replace(
        [np.inf, -np.inf],
        np.nan
    )


def _prepare_price_data(df):
    """
    Chuẩn hóa dữ liệu giá của một mã cổ phiếu.

    Yêu cầu:
    - Có trading_date.
    - Có close.
    - Giá đóng cửa phải lớn hơn 0.
    - Sắp xếp theo ngày tăng dần.
    - Mỗi ngày chỉ giữ một bản ghi.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()

    required_columns = ["trading_date", "close"]

    for column in required_columns:
        if column not in data.columns:
            return pd.DataFrame()

    data["trading_date"] = pd.to_datetime(
        data["trading_date"],
        errors="coerce"
    )

    data["close"] = _to_numeric(data["close"])

    data = data.dropna(
        subset=["trading_date", "close"]
    )

    data = data[data["close"] > 0]

    data = data.sort_values("trading_date")

    data = data.drop_duplicates(
        subset=["trading_date"],
        keep="last"
    )

    data = data.reset_index(drop=True)

    return data


# ============================================================
# 3. TÍNH SUẤT SINH LỜI
# ============================================================

def calculate_return(prices, periods):
    """
    Tính suất sinh lời đơn giản:

    R = P_t / P_(t-periods) - 1

    Momentum sử dụng suất sinh lời đơn giản.
    """

    prices = _to_numeric(pd.Series(prices)).dropna()

    if len(prices) <= periods:
        return np.nan

    previous_price = prices.iloc[-periods - 1]
    latest_price = prices.iloc[-1]

    if previous_price <= 0:
        return np.nan

    return latest_price / previous_price - 1


def calculate_log_returns(prices):
    """
    Tính lợi suất log hằng ngày:

    r_t = ln(P_t / P_(t-1))
    """

    prices = _to_numeric(pd.Series(prices))

    log_returns = np.log(
        prices / prices.shift(1)
    )

    log_returns = log_returns.replace(
        [np.inf, -np.inf],
        np.nan
    )

    return log_returns.dropna()


def calculate_annualized_6m_return(return_6m):
    """
    Quy đổi suất sinh lời 6 tháng thành suất sinh lời năm:

    R_annual = (1 + R_6M)^2 - 1
    """

    if pd.isna(return_6m):
        return np.nan

    if return_6m <= -1:
        return np.nan

    return (1 + return_6m) ** 2 - 1


# ============================================================
# 4. RỦI RO BIẾN ĐỘNG GIÁ
# ============================================================

def calculate_annualized_volatility(log_returns):
    """
    Độ biến động năm hóa:

    Volatility = SD(log returns) * sqrt(252)
    """

    returns = _to_numeric(
        pd.Series(log_returns)
    ).dropna()

    if len(returns) < MIN_RETURN_OBSERVATIONS:
        return np.nan

    return returns.std(ddof=1) * np.sqrt(TRADING_DAYS)


def calculate_downside_deviation(log_returns, mar=0):
    """
    Downside Deviation năm hóa.

    Sử dụng lợi suất log và MAR = 0:

    DD = sqrt(mean(min(r - MAR, 0)^2)) * sqrt(252)
    """

    returns = _to_numeric(
        pd.Series(log_returns)
    ).dropna()

    if len(returns) < MIN_RETURN_OBSERVATIONS:
        return np.nan

    downside_returns = np.minimum(
        returns - mar,
        0
    )

    downside_variance = np.mean(
        downside_returns ** 2
    )

    return np.sqrt(
        downside_variance * TRADING_DAYS
    )


def calculate_max_drawdown(prices):
    """
    Tính Maximum Drawdown.

    Kết quả trả về là độ lớn dương.
    Ví dụ: 0.25 tương ứng mức giảm 25% từ đỉnh.

    Khi chấm điểm, chỉ tiêu này cần được đảo chiều:
    MDD càng thấp thì điểm càng cao.
    """

    prices = _to_numeric(
        pd.Series(prices)
    ).dropna()

    if len(prices) < 2:
        return np.nan

    running_max = prices.cummax()

    drawdown = prices / running_max - 1

    if drawdown.empty:
        return np.nan

    return abs(drawdown.min())


# ============================================================
# 5. CHỈ TIÊU THANH KHOẢN
# ============================================================

def _prepare_traded_value(data):
    """
    Chuẩn hóa giá trị giao dịch.

    Ưu tiên sử dụng Value từ SSI.
    Nếu Value bị thiếu hoặc không hợp lệ, ước tính bằng:

        Value = Close * Volume

    Không thay thế giá trị giao dịch bằng 0 khi dữ liệu bị thiếu.
    """

    result = data.copy()

    result["value_is_estimated"] = False

    if "value" in result.columns:
        value = _to_numeric(result["value"])
    else:
        value = pd.Series(
            np.nan,
            index=result.index,
            dtype=float
        )

    invalid_value = value.isna() | (value < 0)

    if "volume" in result.columns:
        volume = _to_numeric(result["volume"])
    else:
        volume = pd.Series(
            np.nan,
            index=result.index,
            dtype=float
        )

    estimated_value = (
        result["close"] * volume
    )

    can_estimate = (
        invalid_value
        & estimated_value.notna()
        & (estimated_value >= 0)
    )

    value.loc[can_estimate] = estimated_value.loc[can_estimate]

    result.loc[
        can_estimate,
        "value_is_estimated"
    ] = True

    result["value"] = value

    return result


def calculate_adtv(values):
    """
    Average Daily Traded Value.

    Tính trung bình giá trị giao dịch trong các phiên
    có dữ liệu hợp lệ. Phiên có giá trị giao dịch bằng 0
    vẫn được giữ lại trong phép tính.
    """

    values = _to_numeric(
        pd.Series(values)
    )

    values = values[values >= 0]

    if values.empty:
        return np.nan

    return values.mean()


def calculate_amihud(log_or_simple_returns, values):
    """
    Amihud Illiquidity:

    Amihud = mean(|R_t| / Value_t)

    Chỉ tính tại những phiên có:
    - Lợi suất hợp lệ.
    - Giá trị giao dịch lớn hơn 0.

    Giá trị Amihud càng thấp thể hiện thanh khoản càng tốt.
    """

    returns = _to_numeric(
        pd.Series(log_or_simple_returns)
    )

    traded_values = _to_numeric(
        pd.Series(values)
    )

    aligned = pd.concat(
        [
            returns.rename("returns"),
            traded_values.rename("value")
        ],
        axis=1
    ).dropna()

    aligned = aligned[
        aligned["value"] > 0
    ]

    if aligned.empty:
        return np.nan

    amihud_values = (
        aligned["returns"].abs()
        / aligned["value"]
    )

    amihud_values = amihud_values.replace(
        [np.inf, -np.inf],
        np.nan
    ).dropna()

    if amihud_values.empty:
        return np.nan

    return amihud_values.mean()


# ============================================================
# 6. HIỆU SUẤT TƯƠNG ĐỐI VỚI VN-INDEX
# ============================================================

def calculate_beta(stock_returns, market_returns):
    """
    Tính hệ số Beta của cổ phiếu so với thị trường.

    Beta = Cov(R_stock, R_market) / Var(R_market)

    Sử dụng tối đa 126 quan sát hợp lệ gần nhất
    và yêu cầu tối thiểu 30 quan sát.
    """

    if stock_returns is None or market_returns is None:
        return np.nan

    stock_returns = pd.Series(
        stock_returns
    ).reset_index(drop=True)

    market_returns = pd.Series(
        market_returns
    ).reset_index(drop=True)

    if len(stock_returns) != len(market_returns):
        return np.nan

    beta_data = pd.DataFrame({
        "stock_return": _to_numeric(stock_returns),
        "market_return": _to_numeric(market_returns)
    })

    beta_data = beta_data.replace(
        [np.inf, -np.inf],
        np.nan
    ).dropna()

    beta_data = beta_data.tail(PERIOD_6M)

    if len(beta_data) < MIN_BETA_OBSERVATIONS:
        return np.nan

    market_variance = beta_data[
        "market_return"
    ].var(ddof=1)

    if (
        pd.isna(market_variance)
        or not np.isfinite(market_variance)
        or market_variance <= 0
    ):
        return np.nan

    covariance = beta_data[
        "stock_return"
    ].cov(
        beta_data["market_return"]
    )

    beta = covariance / market_variance

    if not np.isfinite(beta):
        return np.nan

    return float(beta)


def _calculate_relative_metrics(stock_data, market_data):
    """
    Tính Excess Return và Beta so với VN-Index.

    Hai chuỗi giá được ghép theo ngày giao dịch chung,
    sau đó tính lợi suất trên cùng tập ngày quan sát.
    """

    result = {
        "excess_3m": np.nan,
        "excess_6m": np.nan,
        "beta": np.nan
    }

    if (
        stock_data is None
        or market_data is None
        or stock_data.empty
        or market_data.empty
    ):
        return result

    stock = stock_data[
        ["trading_date", "close"]
    ].copy()

    market = market_data[
        ["trading_date", "close"]
    ].copy()

    stock = stock.rename(
        columns={"close": "stock_close"}
    )

    market = market.rename(
        columns={"close": "market_close"}
    )

    matched = pd.merge(
        stock,
        market,
        on="trading_date",
        how="inner"
    )

    matched = matched.sort_values(
        "trading_date"
    ).reset_index(drop=True)

    matched = matched[
        (matched["stock_close"] > 0)
        & (matched["market_close"] > 0)
    ]

    if len(matched) < MIN_HISTORY:
        return result

    # --------------------------------------------------------
    # Excess Return 3M và 6M
    # --------------------------------------------------------

    stock_3m = calculate_return(
        matched["stock_close"],
        PERIOD_3M
    )

    market_3m = calculate_return(
        matched["market_close"],
        PERIOD_3M
    )

    stock_6m = calculate_return(
        matched["stock_close"],
        PERIOD_6M
    )

    market_6m = calculate_return(
        matched["market_close"],
        PERIOD_6M
    )

    if pd.notna(stock_3m) and pd.notna(market_3m):
        result["excess_3m"] = stock_3m - market_3m

    if pd.notna(stock_6m) and pd.notna(market_6m):
        result["excess_6m"] = stock_6m - market_6m

    # --------------------------------------------------------
    # Beta được tính trên lợi suất log của các ngày ghép chung
    # --------------------------------------------------------

    stock_returns = np.log(
        matched["stock_close"]
        / matched["stock_close"].shift(1)
    )

    market_returns = np.log(
        matched["market_close"]
        / matched["market_close"].shift(1)
    )

    result["beta"] = calculate_beta(
        stock_returns,
        market_returns
    )

    return result


# ============================================================
# 7. HÀM TÍNH TOÁN CHÍNH CHO MỘT CỔ PHIẾU
# ============================================================

def calculate_stock_metrics(stock_df, market_df=None):
    """
    Tính toàn bộ chỉ tiêu của một cổ phiếu.

    Đầu vào:
    - stock_df: dữ liệu giá của một mã cổ phiếu.
    - market_df: dữ liệu VN-Index.

    Đầu ra:
    - Các chỉ tiêu Momentum.
    - Risk-adjusted Performance.
    - Downside Risk.
    - Liquidity.
    - Relative Market Performance.
    """

    result = {
        "return_1m": np.nan,
        "return_3m": np.nan,
        "return_6m": np.nan,
        "annualized_return_6m": np.nan,
        "reward_volatility": np.nan,
        "volatility": np.nan,
        "downside_deviation": np.nan,
        "max_drawdown": np.nan,
        "adtv": np.nan,
        "amihud": np.nan,
        "zero_volume_ratio": np.nan,
        "excess_3m": np.nan,
        "excess_6m": np.nan,
        "beta": np.nan,
        "value_is_estimated": False
    }

    # --------------------------------------------------------
    # Chuẩn hóa dữ liệu giá
    # --------------------------------------------------------

    data = _prepare_price_data(stock_df)

    if len(data) < MIN_HISTORY:
        return result

    # --------------------------------------------------------
    # Momentum: sử dụng simple return
    # --------------------------------------------------------

    result["return_1m"] = calculate_return(
        data["close"],
        PERIOD_1M
    )

    result["return_3m"] = calculate_return(
        data["close"],
        PERIOD_3M
    )

    result["return_6m"] = calculate_return(
        data["close"],
        PERIOD_6M
    )

    # --------------------------------------------------------
    # Annualized 6M Return
    # --------------------------------------------------------

    result["annualized_return_6m"] = (
        calculate_annualized_6m_return(
            result["return_6m"]
        )
    )

    # --------------------------------------------------------
    # Volatility và Downside Deviation
    # Sử dụng log returns
    # --------------------------------------------------------

    log_returns = calculate_log_returns(
        data["close"]
    )

    recent_log_returns = log_returns.tail(
        PERIOD_6M
    )

    result["volatility"] = (
        calculate_annualized_volatility(
            recent_log_returns
        )
    )

    result["downside_deviation"] = (
        calculate_downside_deviation(
            recent_log_returns,
            mar=0
        )
    )

    # --------------------------------------------------------
    # Reward-to-Volatility
    #
    # Đây là chỉ tiêu RV của mô hình,
    # không phải Sharpe Ratio.
    # --------------------------------------------------------

    annualized_volatility = result["volatility"]
    annualized_return = result["annualized_return_6m"]

    if (
        pd.notna(annualized_return)
        and pd.notna(annualized_volatility)
        and annualized_volatility > 0
    ):
        result["reward_volatility"] = (
            annualized_return / annualized_volatility
        )

    # --------------------------------------------------------
    # Maximum Drawdown
    # --------------------------------------------------------

    recent_prices = data["close"].tail(
        MIN_HISTORY
    )

    result["max_drawdown"] = (
        calculate_max_drawdown(recent_prices)
    )

    # --------------------------------------------------------
    # Liquidity
    # --------------------------------------------------------

    data = _prepare_traded_value(data)

    recent_data = data.tail(
        PERIOD_6M
    ).copy()

    result["adtv"] = calculate_adtv(
        recent_data["value"]
    )

    # Lợi suất log được căn chỉnh với phiên giao dịch tương ứng.
    recent_log_returns = np.log(
        recent_data["close"]
        / recent_data["close"].shift(1)
    )

    recent_log_returns = recent_log_returns.replace(
        [np.inf, -np.inf],
        np.nan
    )

    result["amihud"] = calculate_amihud(
        recent_log_returns,
        recent_data["value"]
    )

    # --------------------------------------------------------
    # Tỷ lệ phiên không có khối lượng giao dịch
    # --------------------------------------------------------

    if "volume" in recent_data.columns:
        volume = _to_numeric(
            recent_data["volume"]
        )

        valid_volume = volume.dropna()

        if not valid_volume.empty:
            result["zero_volume_ratio"] = (
                (valid_volume <= 0).mean()
            )

    # --------------------------------------------------------
    # Cho biết có ít nhất một phiên phải ước tính Value hay không
    # --------------------------------------------------------

    result["value_is_estimated"] = bool(
        recent_data["value_is_estimated"].any()
    )

    # --------------------------------------------------------
    # Relative Market Performance và Beta
    # --------------------------------------------------------

    if market_df is not None and not market_df.empty:
        market = _prepare_price_data(
            market_df
        )

        relative_metrics = _calculate_relative_metrics(
            data,
            market
        )

        result.update(relative_metrics)

    # --------------------------------------------------------
    # Làm sạch kết quả
    # --------------------------------------------------------

    for key, value in result.items():
        if key == "value_is_estimated":
            continue

        if isinstance(value, (int, float, np.number)):
            if not np.isfinite(value):
                result[key] = np.nan

    return result