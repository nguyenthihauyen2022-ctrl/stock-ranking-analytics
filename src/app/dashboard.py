
# ============================================================
# src/app/dashboard.py
# STOCK RANKING DASHBOARD
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.database import StockDatabase
from src.analytics.ranking import build_ranking
from src.analytics.validation import weight_sensitivity


# ============================================================
# 1. CẤU HÌNH GIAO DIỆN
# ============================================================

st.set_page_config(
    page_title="Vietnam Stock Ranking",
    page_icon="📊",
    layout="wide"
)

st.title("📊 HỆ THỐNG PHÂN TÍCH VÀ XẾP HẠNG CỔ PHIẾU")
st.caption(
    "Phân tích cổ phiếu Việt Nam dựa trên động lượng giá, "
    "hiệu suất điều chỉnh rủi ro và thanh khoản."
)
st.caption(
    "Công cụ phân tích học thuật, không phải khuyến nghị đầu tư. "
    "Điểm số là thứ hạng tương đối giữa các cổ phiếu trong tập được phân tích, "
    "không phải xác suất tăng giá hay lợi nhuận kỳ vọng."
)


# ============================================================
# 2. CÁC HÀM HỖ TRỢ
# ============================================================

def format_number(value, decimals=2):
    if pd.isna(value):
        return "N/A"

    return f"{value:,.{decimals}f}"


def format_percent(value, decimals=2):
    if pd.isna(value):
        return "N/A"

    return f"{value * 100:,.{decimals}f}%"


def format_score(value):
    if pd.isna(value):
        return "N/A"

    return f"{value:.2f}/100"


def clean_dataframe(df):
    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    return df.copy()


def safe_numeric(df, columns):
    result = df.copy()

    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce"
            )

    return result


def get_company_name(row):
    for column in [
        "name",
        "company_name",
        "security_name"
    ]:
        if column in row.index:
            value = row[column]

            if pd.notna(value) and str(value).strip():
                return str(value)

    return str(row.get("symbol", ""))


def get_eligible_ranking(ranking):
    if ranking is None or ranking.empty:
        return pd.DataFrame()

    result = ranking.copy()

    if "eligible" in result.columns:
        result = result[
            result["eligible"] == True
        ]

    if "total_score" not in result.columns:
        return pd.DataFrame()

    result["total_score"] = pd.to_numeric(
        result["total_score"],
        errors="coerce"
    )

    result = result.dropna(
        subset=["total_score"]
    )

    return result.sort_values(
        "total_score",
        ascending=False
    )


def get_stock_price_data(prices, symbol):
    if prices.empty:
        return pd.DataFrame()

    if "symbol" not in prices.columns:
        return pd.DataFrame()

    data = prices[
        prices["symbol"].astype(str).str.upper() == symbol.upper()
    ].copy()

    if data.empty:
        return data

    data["trading_date"] = pd.to_datetime(
        data["trading_date"],
        errors="coerce"
    )

    data["close"] = pd.to_numeric(
        data["close"],
        errors="coerce"
    )

    data = data.dropna(
        subset=["trading_date", "close"]
    )

    data = data[data["close"] > 0]

    return data.sort_values("trading_date")


def get_company_universe(securities):
    if securities.empty or "symbol" not in securities.columns:
        return pd.DataFrame()

    result = securities.copy()

    result["symbol"] = (
        result["symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # Loại mã chỉ số khỏi danh sách cổ phiếu.
    excluded_symbols = {
        "VNINDEX",
        "HNXINDEX",
        "UPCOMINDEX"
    }

    result = result[
        ~result["symbol"].isin(excluded_symbols)
    ]

    return result


# ------------------------------------------------------------
# Tên cột hiển thị bằng tiếng Việt
# ------------------------------------------------------------

COLUMN_LABELS = {
    "rank": "Thứ hạng",
    "symbol": "Mã cổ phiếu",
    "name": "Tên doanh nghiệp",
    "icb_name": "Ngành",
    "total_score": "Tổng điểm",
    "score_momentum": "Điểm động lượng",
    "score_risk_adjusted": "Điểm hiệu suất điều chỉnh rủi ro",
    "score_downside": "Điểm rủi ro giảm giá",
    "score_liquidity": "Điểm thanh khoản",
    "score_relative": "Điểm hiệu suất tương đối",

    "return_1m": "Lợi suất 1 tháng",
    "return_3m": "Lợi suất 3 tháng",
    "return_6m": "Lợi suất 6 tháng",
    "annualized_return_6m": "Lợi suất 6 tháng quy đổi năm",

    "reward_volatility": "Lợi suất / Biến động (RV)",
    "volatility": "Độ lệch chuẩn lợi suất năm hóa",
    "max_drawdown": "Mức sụt giảm tối đa (MDD)",
    "downside_deviation": "Độ lệch giảm",
    "adtv": "Giá trị giao dịch bình quân ngày (ADTV)",
    "amihud": "Chỉ số Amihud",
    "excess_3m": "Lợi suất vượt VN-Index 3 tháng",
    "excess_6m": "Lợi suất vượt VN-Index 6 tháng",
    "beta": "Hệ số Beta",
    "zero_volume_ratio": "Tỷ lệ phiên không giao dịch",

    "scenario": "Kịch bản trọng số",
    "spearman_correlation": "Tương quan thứ hạng Spearman",
    "top_n": "Số mã trong Top N",
    "top_n_overlap": "Số mã trùng lặp Top N",
    "top_n_overlap_pct": "Tỷ lệ trùng lặp Top N (%)",
    "mean_abs_rank_change": "Mức thay đổi thứ hạng bình quân",
    "max_abs_rank_change": "Mức thay đổi thứ hạng lớn nhất",
    "stock_count": "Số lượng cổ phiếu",
    "mean_score": "Điểm trung bình",

    "average_score": "Điểm xếp hạng trung bình",
    "average_return_6m": "Lợi suất 6 tháng bình quân",
    "average_volatility": "Độ lệch chuẩn lợi suất năm hóa bình quân",
    "average_adtv": "Giá trị giao dịch bình quân ngày",
    "average_max_drawdown": "Mức sụt giảm tối đa bình quân",

    "first_date": "Ngày có dữ liệu đầu tiên",
    "latest_date": "Ngày dữ liệu gần nhất",
    "observation_count": "Số phiên có dữ liệu",

    "eligible": "Đủ điều kiện xếp hạng"
}


def show_styled_table(
    df,
    column_labels=None,
    use_container_width=True
):
    """
    Hiển thị bảng với:
    - Tên cột dễ hiểu hơn.
    - Màu tiêu đề xanh navy.
    - Nền các dòng nhẹ nhàng.
    - Giữ nguyên dữ liệu gốc.
    """

    if df is None or df.empty:
        st.info("Không có dữ liệu để hiển thị.")
        return

    display_df = df.copy()

    # Chuyển thứ hạng thành số nguyên để tránh hiển thị
    # dạng 1.00000, 2.00000, 3.00000.
    if "rank" in display_df.columns:
        rank_values = pd.to_numeric(
            display_df["rank"],
            errors="coerce"
        )

        display_df["rank"] = rank_values.round().astype("Int64")

    labels = COLUMN_LABELS.copy()

    if column_labels:
        labels.update(column_labels)

    display_df = display_df.rename(
        columns=labels
    )

    styled_df = (
        display_df.style
        .set_table_styles([
            {
                "selector": "th",
                "props": [
                    ("background-color", "#17365D"),
                    ("color", "#FFFFFF"),
                    ("font-weight", "bold"),
                    ("text-align", "center"),
                    ("border", "1px solid #D5DEE9"),
                    ("padding", "8px")
                ]
            },
            {
                "selector": "td",
                "props": [
                    ("border", "1px solid #E5EAF0"),
                    ("padding", "7px")
                ]
            },
            {
                "selector": "tbody tr:nth-child(even)",
                "props": [
                    ("background-color", "#F3F6FA")
                ]
            }
        ])
    )

    st.dataframe(
        styled_df,
        use_container_width=use_container_width,
        hide_index=True
    )


# ============================================================
# 3. ĐỌC DỮ LIỆU TỪ SQLITE
# ============================================================

@st.cache_data(show_spinner="Đang tính xếp hạng toàn thị trường, vui lòng chờ khoảng 30 giây...")
def load_dashboard_data():
    """
    Dashboard chỉ đọc dữ liệu đã có trong SQLite.
    Không gọi SSI API.
    Không chạy collector.
    """

    db = StockDatabase()

    prices = clean_dataframe(
        db.get_prices()
    )

    securities = clean_dataframe(
        db.get_securities()
    )

    if prices.empty:
        return {
            "prices": pd.DataFrame(),
            "securities": securities,
            "ranking": pd.DataFrame(),
            "market_data": pd.DataFrame(),
            "data_error": "Database chưa có dữ liệu giá."
        }

    if "symbol" in prices.columns:
        prices["symbol"] = (
            prices["symbol"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

    if "trading_date" in prices.columns:
        prices["trading_date"] = pd.to_datetime(
            prices["trading_date"],
            errors="coerce"
        )

    if "close" in prices.columns:
        prices["close"] = pd.to_numeric(
            prices["close"],
            errors="coerce"
        )

    prices = prices.dropna(
        subset=["symbol", "trading_date", "close"]
    )

    prices = prices[
        prices["close"] > 0
    ]

    if "symbol" in prices.columns:
        market_data = prices[
            prices["symbol"] == "VNINDEX"
        ].copy()
    else:
        market_data = pd.DataFrame()

    ranking = build_ranking(
        prices=prices,
        securities=securities
    )

    return {
        "prices": prices,
        "securities": securities,
        "ranking": clean_dataframe(ranking),
        "market_data": market_data,
        "data_error": None
    }


# ============================================================
# 4. TỔNG QUAN THỊ TRƯỜNG
# ============================================================

def render_overview(data):
    st.header("1. Tổng quan thị trường")

    prices = data["prices"]
    securities = data["securities"]
    ranking = data["ranking"]
    market_data = data["market_data"]

    eligible = get_eligible_ranking(ranking)

    stock_universe = get_company_universe(
        securities
    )

    latest_date = None

    if not prices.empty:
        latest_date = prices["trading_date"].max()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Số mã trong danh sách",
        f"{len(stock_universe):,}"
    )

    col2.metric(
        "Số mã đủ điều kiện xếp hạng",
        f"{len(eligible):,}"
    )

    col3.metric(
        "Số bản ghi giá",
        f"{len(prices):,}"
    )

    col4.metric(
        "Ngày dữ liệu mới nhất",
        latest_date.strftime("%d/%m/%Y")
        if pd.notna(latest_date)
        else "N/A"
    )

    st.divider()

    # --------------------------------------------------------
    # Diễn biến VN-Index
    # --------------------------------------------------------

    st.subheader("Diễn biến VN-Index")

    if market_data.empty:
        st.info("Chưa có dữ liệu VN-Index.")
    else:
        market_data = market_data.sort_values(
            "trading_date"
        )

        fig = px.line(
            market_data,
            x="trading_date",
            y="close",
            title="VN-Index theo thời gian"
        )

        fig.update_layout(
            xaxis_title="Ngày giao dịch",
            yaxis_title="Điểm số",
            hovermode="x unified"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        if len(market_data) >= 2:
            first_price = market_data["close"].iloc[0]
            last_price = market_data["close"].iloc[-1]

            market_return = (
                last_price / first_price - 1
                if first_price > 0
                else np.nan
            )

            st.metric(
                "Biến động VN-Index trong giai đoạn dữ liệu",
                format_percent(market_return)
            )

    st.divider()

    # --------------------------------------------------------
    # Phân phối điểm xếp hạng
    # --------------------------------------------------------

    st.subheader("Phân phối điểm xếp hạng")

    if eligible.empty:
        st.info("Chưa có mã cổ phiếu đủ điều kiện xếp hạng.")
    else:
        fig = px.histogram(
            eligible,
            x="total_score",
            nbins=20,
            title="Phân phối tổng điểm"
        )

        fig.update_layout(
            xaxis_title="Tổng điểm",
            yaxis_title="Số lượng cổ phiếu"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    st.divider()

    # --------------------------------------------------------
    # Top cổ phiếu
    # --------------------------------------------------------

    st.subheader("Top 10 cổ phiếu")

    if not eligible.empty:
        display_columns = [
            column
            for column in [
                "rank",
                "symbol",
                "name",
                "icb_name",
                "total_score",
                "score_momentum",
                "score_risk_adjusted",
                "score_downside",
                "score_liquidity",
                "score_relative"
            ]
            if column in eligible.columns
        ]

        top_stocks = eligible.head(10)[
            display_columns
        ].copy()

        show_styled_table(top_stocks)


# ============================================================
# 5. BẢNG XẾP HẠNG CỔ PHIẾU
# ============================================================

def render_ranking(data):
    st.header("2. Xếp hạng cổ phiếu")

    ranking = get_eligible_ranking(
        data["ranking"]
    )

    if ranking.empty:
        st.warning(
            "Chưa có cổ phiếu đủ dữ liệu để xếp hạng."
        )
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        search_symbol = st.text_input(
            "Tìm mã cổ phiếu",
            placeholder="Ví dụ: FPT"
        ).strip().upper()

    with col2:
        industries = []

        if "icb_name" in ranking.columns:
            industries = sorted(
                ranking["icb_name"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        selected_industry = st.selectbox(
            "Ngành",
            ["Tất cả"] + industries
        )

    with col3:
        sort_options = {
            "Tổng điểm": "total_score",
            "Momentum 6 tháng": "return_6m",
            "Lợi suất 3 tháng": "return_3m",
            "Lợi suất 1 tháng": "return_1m",
            "RV": "reward_volatility",
            "Độ lệch chuẩn lợi suất năm hóa": "volatility",
            "Thanh khoản ADTV": "adtv",
            "Maximum Drawdown": "max_drawdown"
        }

        selected_sort = st.selectbox(
            "Sắp xếp theo",
            list(sort_options.keys())
        )

    filtered = ranking.copy()

    if search_symbol:
        filtered = filtered[
            filtered["symbol"]
            .astype(str)
            .str.contains(
                search_symbol,
                case=False,
                na=False
            )
        ]

    if (
        selected_industry != "Tất cả"
        and "icb_name" in filtered.columns
    ):
        filtered = filtered[
            filtered["icb_name"] == selected_industry
        ]

    sort_column = sort_options[selected_sort]

    if sort_column in filtered.columns:
        filtered = filtered.sort_values(
            sort_column,
            ascending=False,
            na_position="last"
        )

    display_columns = [
        "rank",
        "symbol",
        "name",
        "icb_name",
        "total_score",
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
        "excess_6m"
    ]

    display_columns = [
        column
        for column in display_columns
        if column in filtered.columns
    ]

    show_styled_table(
        filtered[display_columns]
    )


# ============================================================
# 6. PHÂN TÍCH CHI TIẾT CỔ PHIẾU
# ============================================================

def render_stock_analysis(data):
    st.header("3. Phân tích chi tiết cổ phiếu")

    ranking = get_eligible_ranking(
        data["ranking"]
    )

    prices = data["prices"]

    if ranking.empty:
        st.warning("Chưa có dữ liệu xếp hạng.")
        return

    symbols = sorted(
        ranking["symbol"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_symbol = st.selectbox(
        "Chọn cổ phiếu",
        symbols
    )

    stock_row = ranking[
        ranking["symbol"] == selected_symbol
    ]

    if stock_row.empty:
        st.warning("Không tìm thấy thông tin cổ phiếu.")
        return

    stock_row = stock_row.iloc[0]

    st.subheader(
        f"{selected_symbol} - {get_company_name(stock_row)}"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Tổng điểm",
        format_score(stock_row.get("total_score"))
    )

    col2.metric(
        "Xếp hạng",
        format_number(stock_row.get("rank"), 0)
    )

    col3.metric(
        "Lợi suất 6 tháng",
        format_percent(stock_row.get("return_6m"))
    )

    col4.metric(
        "RV",
        format_number(stock_row.get("reward_volatility"))
    )

    # --------------------------------------------------------
    # Biểu đồ giá
    # --------------------------------------------------------

    stock_prices = get_stock_price_data(
        prices,
        selected_symbol
    )

    if stock_prices.empty:
        st.info("Không có dữ liệu giá cho cổ phiếu này.")
        return

    st.subheader("Diễn biến giá")

    fig = px.line(
        stock_prices,
        x="trading_date",
        y="close",
        title=f"Giá đóng cửa {selected_symbol}"
    )

    fig.update_layout(
        xaxis_title="Ngày giao dịch",
        yaxis_title="Giá đóng cửa",
        hovermode="x unified"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # --------------------------------------------------------
    # Khối lượng giao dịch
    # --------------------------------------------------------

    if "volume" in stock_prices.columns:
        st.subheader("Khối lượng giao dịch")

        stock_prices["volume"] = pd.to_numeric(
            stock_prices["volume"],
            errors="coerce"
        )

        fig = px.bar(
            stock_prices,
            x="trading_date",
            y="volume",
            title=f"Khối lượng giao dịch {selected_symbol}"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    st.divider()

    # --------------------------------------------------------
    # Điểm thành phần
    # --------------------------------------------------------

    st.subheader("Điểm số theo năm nhóm tiêu chí")

    factor_columns = {
        "Momentum": "score_momentum",
        "Risk-adjusted Performance": "score_risk_adjusted",
        "Downside Risk": "score_downside",
        "Liquidity": "score_liquidity",
        "Relative Market Performance": "score_relative"
    }

    factor_data = []

    for factor_name, column in factor_columns.items():
        if column in stock_row.index:
            factor_data.append(
                {
                    "Factor": factor_name,
                    "Score": stock_row[column]
                }
            )

    factor_df = pd.DataFrame(factor_data)

    if not factor_df.empty:
        fig = px.bar(
            factor_df,
            x="Factor",
            y="Score",
            range_y=[0, 100],
            title="Điểm thành phần"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # --------------------------------------------------------
    # Các chỉ tiêu gốc
    # --------------------------------------------------------

    st.subheader("Các chỉ tiêu tài chính và rủi ro")

    metric_columns = {
        "Lợi suất 1 tháng": "return_1m",
        "Lợi suất 3 tháng": "return_3m",
        "Lợi suất 6 tháng": "return_6m",
        "Lợi suất 6 tháng quy đổi năm": "annualized_return_6m",
        "Lợi suất / Biến động (RV)": "reward_volatility",
        "Độ lệch chuẩn lợi suất năm hóa": "volatility",
        "Độ lệch giảm": "downside_deviation",
        "Mức sụt giảm tối đa (MDD)": "max_drawdown",
        "Giá trị giao dịch bình quân ngày (ADTV)": "adtv",
        "Chỉ số Amihud": "amihud",
        "Lợi suất vượt VN-Index 3 tháng": "excess_3m",
        "Lợi suất vượt VN-Index 6 tháng": "excess_6m",
        "Hệ số Beta": "beta",
        "Tỷ lệ phiên không giao dịch": "zero_volume_ratio"
    }

    metric_rows = []

    for label, column in metric_columns.items():
        if column in stock_row.index:
            value = stock_row[column]

            metric_rows.append(
                {
                    "Chỉ tiêu": label,
                    "Giá trị": value
                }
            )

    metric_df = pd.DataFrame(metric_rows)

    show_styled_table(metric_df)

    if bool(stock_row.get("value_is_estimated", False)):
        st.warning(
            "Một phần giá trị giao dịch được ước tính bằng "
            "Giá đóng cửa × Khối lượng do dữ liệu Value không đầy đủ."
        )


# ============================================================
# 7. SO SÁNH CỔ PHIẾU
# ============================================================

def render_comparison(data):
    st.header("4. So sánh cổ phiếu")

    ranking = get_eligible_ranking(
        data["ranking"]
    )

    prices = data["prices"]

    if ranking.empty:
        st.warning("Chưa có dữ liệu để so sánh.")
        return

    symbols = sorted(
        ranking["symbol"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_symbols = st.multiselect(
        "Chọn cổ phiếu cần so sánh",
        symbols,
        default=symbols[:3]
    )

    if len(selected_symbols) < 2:
        st.info("Vui lòng chọn ít nhất hai cổ phiếu.")
        return

    # --------------------------------------------------------
    # So sánh điểm số và chỉ tiêu
    # --------------------------------------------------------

    selected_ranking = ranking[
        ranking["symbol"].isin(selected_symbols)
    ].copy()

    comparison_columns = [
        "symbol",
        "total_score",
        "score_momentum",
        "score_risk_adjusted",
        "score_downside",
        "score_liquidity",
        "score_relative",
        "return_3m",
        "return_6m",
        "reward_volatility",
        "volatility",
        "max_drawdown",
        "adtv",
        "amihud"
    ]

    comparison_columns = [
        column
        for column in comparison_columns
        if column in selected_ranking.columns
    ]

    st.subheader("Bảng so sánh chỉ tiêu")

    show_styled_table(
        selected_ranking[comparison_columns]
    )

    # --------------------------------------------------------
    # So sánh diễn biến giá chuẩn hóa
    # --------------------------------------------------------

    st.subheader("Diễn biến giá chuẩn hóa")

    normalized_data = []

    for symbol in selected_symbols:
        stock_prices = get_stock_price_data(
            prices,
            symbol
        )

        if stock_prices.empty:
            continue

        stock_prices = stock_prices.sort_values(
            "trading_date"
        ).copy()

        first_price = stock_prices["close"].iloc[0]

        if first_price <= 0:
            continue

        stock_prices["normalized_price"] = (
            stock_prices["close"] / first_price * 100
        )

        stock_prices["symbol"] = symbol

        normalized_data.append(
            stock_prices[
                [
                    "trading_date",
                    "symbol",
                    "normalized_price"
                ]
            ]
        )

    if normalized_data:
        chart_data = pd.concat(
            normalized_data,
            ignore_index=True
        )

        fig = px.line(
            chart_data,
            x="trading_date",
            y="normalized_price",
            color="symbol",
            title="So sánh giá chuẩn hóa (mốc 100 tại phiên đầu tiên)"
        )

        fig.update_layout(
            xaxis_title="Ngày giao dịch",
            yaxis_title="Giá chuẩn hóa",
            hovermode="x unified"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )
    else:
        st.info("Không đủ dữ liệu giá để tạo biểu đồ.")


# ============================================================
# 8. PHÂN TÍCH NGÀNH
# ============================================================

def render_industry_analysis(data):
    st.header("5. Phân tích ngành")

    ranking = get_eligible_ranking(
        data["ranking"]
    )

    if ranking.empty:
        st.warning("Chưa có dữ liệu xếp hạng.")
        return

    if "icb_name" not in ranking.columns:
        st.info(
            "Dữ liệu hiện tại chưa có thông tin phân ngành ICB."
        )
        return

    industry_data = ranking.dropna(
        subset=["icb_name"]
    ).copy()

    if industry_data.empty:
        st.info("Không có dữ liệu ngành hợp lệ.")
        return

    aggregation = {
        "symbol": "count",
        "total_score": "mean"
    }

    if "return_6m" in industry_data.columns:
        aggregation["return_6m"] = "mean"

    if "volatility" in industry_data.columns:
        aggregation["volatility"] = "mean"

    if "adtv" in industry_data.columns:
        aggregation["adtv"] = "mean"

    if "max_drawdown" in industry_data.columns:
        aggregation["max_drawdown"] = "mean"

    industry_summary = (
        industry_data
        .groupby("icb_name")
        .agg(aggregation)
        .reset_index()
    )

    industry_summary = industry_summary.rename(
        columns={
            "symbol": "stock_count",
            "total_score": "average_score",
            "return_6m": "average_return_6m",
            "volatility": "average_volatility",
            "adtv": "average_adtv",
            "max_drawdown": "average_max_drawdown"
        }
    )

    industry_summary = industry_summary.sort_values(
        "average_score",
        ascending=False
    )

    st.subheader("Bảng tổng hợp theo ngành")

    show_styled_table(industry_summary)

    st.subheader("Điểm xếp hạng trung bình theo ngành")

    fig = px.bar(
        industry_summary,
        x="icb_name",
        y="average_score",
        title="Điểm trung bình theo ngành"
    )

    fig.update_layout(
        xaxis_title="Ngành",
        yaxis_title="Điểm trung bình",
        xaxis_tickangle=-45
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# ============================================================
# 9. KIỂM ĐỊNH MÔ HÌNH
# ============================================================

def render_validation(data):
    st.header("6. Kiểm định mô hình")

    ranking = get_eligible_ranking(
        data["ranking"]
    )

    if ranking.empty:
        st.warning(
            "Chưa có đủ dữ liệu để kiểm định mô hình."
        )
        return

    st.subheader("Phân tích độ nhạy trọng số")

    st.write(
        """
        Phân tích độ nhạy được sử dụng để đánh giá mức độ thay đổi
        thứ hạng cổ phiếu khi điều chỉnh trọng số của năm nhóm tiêu chí.
        """
    )

    try:
        sensitivity = weight_sensitivity(
            ranking
        )
    except Exception as error:
        st.error(
            f"Không thể thực hiện phân tích độ nhạy: {error}"
        )
        return

    if sensitivity is None or sensitivity.empty:
        st.info(
            "Không đủ dữ liệu hợp lệ để thực hiện phân tích độ nhạy."
        )
        return

    show_styled_table(sensitivity)

    if "spearman_correlation" in sensitivity.columns:
        st.subheader("Tương quan thứ hạng Spearman")

        chart_data = sensitivity.dropna(
            subset=["spearman_correlation"]
        )

        if not chart_data.empty:
            fig = px.bar(
                chart_data,
                x="scenario",
                y="spearman_correlation",
                title="Tương quan thứ hạng so với kịch bản cơ sở"
            )

            fig.update_layout(
                xaxis_title="Kịch bản",
                yaxis_title="Spearman Correlation",
                xaxis_tickangle=-20
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

    if "top_n_overlap_pct" in sensitivity.columns:
        st.subheader("Mức độ trùng lặp Top N")

        chart_data = sensitivity.dropna(
            subset=["top_n_overlap_pct"]
        )

        if not chart_data.empty:
            fig = px.bar(
                chart_data,
                x="scenario",
                y="top_n_overlap_pct",
                title="Tỷ lệ cổ phiếu trùng lặp trong Top N"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

    st.info(
        "Kết quả trên phản ánh độ nhạy của thứ hạng trước thay đổi trọng số. "
        "Đây chưa phải kiểm định ngoài mẫu hoặc kiểm định khả năng dự báo "
        "lợi suất tương lai."
    )


# ============================================================
# 10. TRẠNG THÁI DỮ LIỆU
# ============================================================

def render_data_status(data):
    st.header("7. Trạng thái dữ liệu")

    prices = data["prices"]
    securities = data["securities"]
    ranking = data["ranking"]

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Số mã chứng khoán",
        f"{len(securities):,}"
    )

    col2.metric(
        "Số bản ghi giá",
        f"{len(prices):,}"
    )

    col3.metric(
        "Số mã đủ điều kiện",
        f"{len(get_eligible_ranking(ranking)):,}"
    )

    st.subheader("Thống kê dữ liệu theo mã")

    if prices.empty:
        st.info("Database chưa có dữ liệu giá.")
        return

    summary = (
        prices
        .groupby("symbol")
        .agg(
            first_date=("trading_date", "min"),
            latest_date=("trading_date", "max"),
            observation_count=("close", "count")
        )
        .reset_index()
    )

    summary = summary.sort_values(
        "latest_date",
        ascending=False
    )

    show_styled_table(summary)

    st.subheader("Danh sách mã chưa đủ điều kiện xếp hạng")

    if ranking.empty:
        st.info("Chưa có kết quả xếp hạng.")

    elif "eligible" in ranking.columns:
        ineligible = ranking[
            ranking["eligible"] != True
        ].copy()

        if ineligible.empty:
            st.success(
                "Không có mã nào bị đánh dấu không đủ điều kiện "
                "trong kết quả xếp hạng hiện tại."
            )
        else:
            # Không hiển thị eligible và total_score vì đây là
            # các cột kỹ thuật, không hữu ích khi xem danh sách này.
            display_columns = [
                column
                for column in [
                    "symbol",
                    "name",
                    "icb_name"
                ]
                if column in ineligible.columns
            ]

            display_data = ineligible[
                display_columns
            ].copy()

            display_data["status_text"] = (
                "Chưa đủ điều kiện xếp hạng"
            )

            display_data = display_data.rename(
                columns={
                    "status_text": "Trạng thái"
                }
            )

            show_styled_table(display_data)

    else:
        st.info(
            "Kết quả ranking hiện tại chưa có thông tin điều kiện xếp hạng."
        )


# ============================================================
# 11. GIẢI THÍCH CÁC CHỈ TIÊU
# ============================================================

def render_metric_guide():
    st.header("8. Giải thích các chỉ tiêu")

    st.subheader("1. Nhóm động lượng giá (Momentum)")

    momentum_data = pd.DataFrame([
        {
            "Chỉ tiêu": "Lợi suất 1 tháng",
            "Ý nghĩa": "Đo mức thay đổi giá cổ phiếu trong khoảng 1 tháng giao dịch.",
            "Công thức": "P hiện tại / P cách 21 phiên - 1"
        },
        {
            "Chỉ tiêu": "Lợi suất 3 tháng",
            "Ý nghĩa": "Đo mức thay đổi giá cổ phiếu trong khoảng 3 tháng giao dịch.",
            "Công thức": "P hiện tại / P cách 63 phiên - 1"
        },
        {
            "Chỉ tiêu": "Lợi suất 6 tháng",
            "Ý nghĩa": "Đo mức thay đổi giá cổ phiếu trong khoảng 6 tháng giao dịch.",
            "Công thức": "P hiện tại / P cách 126 phiên - 1"
        }
    ])

    show_styled_table(momentum_data)

    st.caption(
        "Trọng số nội bộ của Momentum: lợi suất 1 tháng 20%, "
        "3 tháng 30% và 6 tháng 50%. Trọng số nhóm: 25%."
    )

    st.divider()

    st.subheader("2. Nhóm hiệu suất điều chỉnh rủi ro")

    risk_adjusted_data = pd.DataFrame([
        {
            "Chỉ tiêu": "Lợi suất 6 tháng quy đổi năm",
            "Ý nghĩa": "Quy đổi lợi suất 6 tháng thành mức lợi suất tương đương một năm.",
            "Công thức": "(1 + R6M)^2 - 1"
        },
        {
            "Chỉ tiêu": "RV (Reward-to-Volatility)",
            "Ý nghĩa": "Đo lợi suất năm hóa trên một đơn vị biến động năm hóa.",
            "Công thức": "Lợi suất 6 tháng quy đổi năm / Độ lệch chuẩn lợi suất năm hóa"
        },
        {
            "Chỉ tiêu": "Độ lệch chuẩn lợi suất năm hóa",
            "Ý nghĩa": "Đo mức độ phân tán của lợi suất cổ phiếu quanh mức trung bình, được quy đổi theo năm.",
            "Công thức": "Độ lệch chuẩn lợi suất log ngày × √252"
        }
    ])

    show_styled_table(risk_adjusted_data)

    st.caption(
        "RV không phải Sharpe Ratio vì công thức không sử dụng lãi suất phi rủi ro. "
        "Trọng số nội bộ: RV 70%, độ lệch chuẩn lợi suất năm hóa 30%. "
        "Trọng số nhóm: 25%."
    )

    st.divider()

    st.subheader("3. Nhóm rủi ro giảm giá (Downside Risk)")

    downside_data = pd.DataFrame([
        {
            "Chỉ tiêu": "Maximum Drawdown (MDD)",
            "Ý nghĩa": "Đo mức giảm lớn nhất của giá so với đỉnh trước đó trong giai đoạn quan sát.",
            "Công thức": "Giá / Đỉnh giá tích lũy - 1; lấy mức giảm lớn nhất"
        },
        {
            "Chỉ tiêu": "Downside Deviation",
            "Ý nghĩa": "Đo mức độ biến động của các phiên có lợi suất thấp hơn mức chuẩn MAR = 0.",
            "Công thức": "√Mean[min(r - MAR, 0)^2] × √252"
        }
    ])

    show_styled_table(downside_data)

    st.caption(
        "Các chỉ tiêu rủi ro giảm giá càng thấp thường được đánh giá tốt hơn. "
        "Trọng số nội bộ: MDD 50%, Downside Deviation 50%. "
        "Trọng số nhóm: 20%."
    )

    st.divider()

    st.subheader("4. Nhóm thanh khoản (Liquidity)")

    liquidity_data = pd.DataFrame([
        {
            "Chỉ tiêu": "ADTV",
            "Ý nghĩa": "Đo giá trị giao dịch bình quân mỗi phiên, phản ánh quy mô giao dịch.",
            "Công thức": "Giá trị giao dịch bình quân ngày"
        },
        {
            "Chỉ tiêu": "Amihud Illiquidity",
            "Ý nghĩa": "Đo mức thay đổi giá tương ứng với một đơn vị giá trị giao dịch.",
            "Công thức": "Mean(|Lợi suất ngày| / Giá trị giao dịch ngày)"
        }
    ])

    show_styled_table(liquidity_data)

    st.caption(
        "ADTV càng cao thường phản ánh thanh khoản tốt hơn; "
        "Amihud càng thấp thường phản ánh mức độ kém thanh khoản thấp hơn. "
        "Trọng số nội bộ: ADTV 60%, Amihud 40%. Trọng số nhóm: 15%."
    )

    st.divider()

    st.subheader("5. Nhóm hiệu suất tương đối (Relative Market Performance)")

    relative_data = pd.DataFrame([
        {
            "Chỉ tiêu": "Excess Return 3 tháng",
            "Ý nghĩa": "Đo phần lợi suất cổ phiếu vượt hoặc thấp hơn VN-Index trong 3 tháng.",
            "Công thức": "Lợi suất cổ phiếu 3 tháng - Lợi suất VN-Index 3 tháng"
        },
        {
            "Chỉ tiêu": "Excess Return 6 tháng",
            "Ý nghĩa": "Đo phần lợi suất cổ phiếu vượt hoặc thấp hơn VN-Index trong 6 tháng.",
            "Công thức": "Lợi suất cổ phiếu 6 tháng - Lợi suất VN-Index 6 tháng"
        }
    ])

    show_styled_table(relative_data)

    st.caption(
        "Trọng số nội bộ: Excess Return 3 tháng 70%, "
        "6 tháng 30%. Trọng số nhóm: 15%."
    )

    st.divider()

    st.subheader("6. Một số chỉ tiêu bổ sung")

    additional_data = pd.DataFrame([
        {
            "Chỉ tiêu": "Beta",
            "Ý nghĩa": "Đo mức độ biến động của lợi suất cổ phiếu so với VN-Index.",
            "Công thức": "Cov(R cổ phiếu, R thị trường) / Var(R thị trường)"
        },
        {
            "Chỉ tiêu": "Tỷ lệ phiên không giao dịch",
            "Ý nghĩa": "Phản ánh tỷ lệ phiên có khối lượng giao dịch bằng hoặc thấp hơn 0 trong dữ liệu.",
            "Công thức": "Số phiên không giao dịch / Tổng số phiên quan sát"
        }
    ])

    show_styled_table(additional_data)

    st.caption(
        "Beta và tỷ lệ phiên không giao dịch được dùng để bổ sung thông tin "
        "phân tích, không phải thành phần tính tổng điểm xếp hạng."
    )

    st.divider()

    st.subheader("7. Cách tính điểm và xếp hạng")

    st.write(
        """
        Các chỉ tiêu được chuyển đổi thành điểm percentile trong khoảng 0–100
        để có thể so sánh giữa các cổ phiếu trong tập dữ liệu.

        Với chỉ tiêu mà giá trị cao hơn được đánh giá tốt hơn,
        cổ phiếu có giá trị tương đối cao sẽ nhận điểm cao hơn.

        Với chỉ tiêu rủi ro hoặc kém thanh khoản mà giá trị thấp hơn được đánh giá tốt hơn,
        thứ tự điểm được đảo chiều.
        """
    )

    weight_data = pd.DataFrame([
        {
            "Nhóm tiêu chí": "Momentum",
            "Trọng số": "25%"
        },
        {
            "Nhóm tiêu chí": "Risk-adjusted Performance",
            "Trọng số": "25%"
        },
        {
            "Nhóm tiêu chí": "Downside Risk",
            "Trọng số": "20%"
        },
        {
            "Nhóm tiêu chí": "Liquidity",
            "Trọng số": "15%"
        },
        {
            "Nhóm tiêu chí": "Relative Market Performance",
            "Trọng số": "15%"
        }
    ])

    show_styled_table(weight_data)

    st.caption(
        "Tổng điểm được tính bằng tổng điểm của năm nhóm tiêu chí "
        "nhân với trọng số tương ứng. Tổng trọng số bằng 100%."
    )

    st.divider()

    st.subheader("8. Giới hạn của sản phẩm")

    st.markdown(
        """
        - Đây là công cụ phân tích học thuật, **không phải khuyến nghị đầu tư**.
          Điểm số chỉ có ý nghĩa tương đối giữa các cổ phiếu trong tập được phân tích.
        - Mô hình chỉ dùng dữ liệu giá và giao dịch trong quá khứ; không đánh giá
          cơ bản doanh nghiệp (ROE, EPS, P/E...).
        - Giá chưa được điều chỉnh cho sự kiện doanh nghiệp (chia tách, thưởng cổ phiếu).
        - Trọng số là lựa chọn thiết kế, chưa được tối ưu; thứ hạng nhóm đầu có thể
          thay đổi khi đổi trọng số (xem trang Kiểm định mô hình).
        - Chưa có kiểm định ngoài mẫu hoặc backtest.
        - Phân tích ngành phụ thuộc vào dữ liệu ngành SSI trả về; một số mã có thể thiếu ngành.
        - Giá trị giao dịch có thể là giá trị ước tính (Giá đóng cửa × Khối lượng)
          khi dữ liệu không đầy đủ.
        - Mã không còn trong danh sách hiện tại của SSI (ví dụ đã hủy niêm yết) không
          được đưa vào phân tích, nên kết quả có thể chịu sai lệch sống sót.
        - Dữ liệu phụ thuộc vào lần thu thập gần nhất. Dashboard chỉ đọc dữ liệu đã lưu,
          không tự gọi API; xem ngày dữ liệu mới nhất ở trang Tổng quan và Trạng thái dữ liệu.
        """
    )


# ============================================================
# 12. CHƯƠNG TRÌNH CHÍNH
# ============================================================

def main():
    try:
        data = load_dashboard_data()

    except Exception as error:
        st.error(
            f"Không thể tải dữ liệu từ SQLite: {error}"
        )

        st.info(
            "Kiểm tra đường dẫn database và các hàm đọc dữ liệu "
            "trong src/data/database.py."
        )
        return

    if data.get("data_error"):
        st.warning(
            data["data_error"]
        )
        return

    if data["prices"].empty:
        st.warning(
            "Database hiện chưa có dữ liệu giá."
        )
        return

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        [
            "Tổng quan",
            "Xếp hạng",
            "Phân tích cổ phiếu",
            "So sánh",
            "Phân tích ngành",
            "Kiểm định mô hình",
            "Trạng thái dữ liệu",
            "Giải thích các chỉ tiêu"
        ]
    )

    with tab1:
        render_overview(data)

    with tab2:
        render_ranking(data)

    with tab3:
        render_stock_analysis(data)

    with tab4:
        render_comparison(data)

    with tab5:
        render_industry_analysis(data)

    with tab6:
        render_validation(data)

    with tab7:
        render_data_status(data)

    with tab8:
        render_metric_guide()


if __name__ == "__main__":
    main()