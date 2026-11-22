
import os
import re
import time
import logging

import pandas as pd

from datetime import date, timedelta
from dotenv import load_dotenv

from src.ssi_api.client import SSIClient, SSIAPIError
from src.data.database import StockDatabase


# ============================================================
# 1. CẤU HÌNH
# ============================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


BOARDS = [
    item.strip().upper()
    for item in os.getenv(
        "BOARDS",
        "HOSE,HNX,UPCOM"
    ).split(",")
    if item.strip()
]

MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "0"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "450"))
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "1000"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.15"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "100"))
OVERLAP_DAYS = int(os.getenv("OVERLAP_DAYS", "7"))
MIN_HISTORY = int(os.getenv("MIN_HISTORY", "127"))

# Các mã SSI không trả về trong danh sách securitiesByBoard
# nhưng đã xác minh có dữ liệu OHLC.
#
# Có thể bổ sung mã khác trong file .env:
# SUPPLEMENTAL_SYMBOLS=HPG,ABC,XYZ
#
# Không tự thêm mã vào đây nếu chưa xác minh được dữ liệu OHLC.

SUPPLEMENTAL_SYMBOLS = [
    item.strip().upper()
    for item in os.getenv(
        "SUPPLEMENTAL_SYMBOLS",
        "HPG"
    ).split(",")
    if item.strip()
]

# Thông tin bổ sung tối thiểu cho HPG.
# SSI không trả metadata HPG qua securitiesByBoard.
#
# Tên và sàn được khai báo riêng để phục vụ việc lưu danh mục.
# Dữ liệu giá vẫn được lấy trực tiếp từ SSI OHLC.

SUPPLEMENTAL_METADATA = {
    "HPG": {
        "name": "Công ty Cổ phần Tập đoàn Hòa Phát",
        "board": "HOSE",
        "icb_name": None,
        "stock_type": "STOCK"
    }
}


if PAGE_SIZE <= 0:
    raise ValueError("PAGE_SIZE phải lớn hơn 0.")

if MAX_PAGES <= 0:
    raise ValueError("MAX_PAGES phải lớn hơn 0.")

if LOOKBACK_DAYS <= 0:
    raise ValueError("LOOKBACK_DAYS phải lớn hơn 0.")

if OVERLAP_DAYS < 0:
    raise ValueError("OVERLAP_DAYS không được âm.")


INDEX_SYMBOLS = {
    "VNINDEX", "VN30", "VN100", "VNALLSHARE",
    "VNXALLSHARE", "VNX50", "HNXINDEX", "HNX30",
    "UPCOMINDEX", "VNFIN", "VNFINLEAD", "VNFINSELECT",
    "VNREAL", "VNCONS", "VNCOND", "VNENE", "VNHEAL",
    "VNIND", "VNIT", "VNMAT", "VNUTI", "VNSI",
    "VNSMALLCAP", "VNMIDCAP", "VNDIAMOND",
    "VNDIVIDEND", "VNSHINE", "VNPRIVGRO", "VNMITECH"
}


EXCLUDED_STOCK_TYPES = {
    "BOND",
    "FUTURE",
    "ETF PRODUCT",
    "INVESTMENT FUND",
    "CW PRODUCT"
}


# ============================================================
# 2. HÀM CHUẨN HÓA CHUNG
# ============================================================

def normalize_text(value):
    """Chuẩn hóa văn bản và xử lý giá trị thiếu."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    result = str(value).strip().upper()

    if result in {
        "",
        "NONE",
        "NAN",
        "NULL",
        "N/A",
        "NA"
    }:
        return ""

    return result


def convert_to_dataframe(raw_data):
    """Chuyển dữ liệu SSI API thành DataFrame."""

    if raw_data is None:
        return pd.DataFrame()

    if isinstance(raw_data, pd.DataFrame):
        return raw_data.copy()

    if isinstance(raw_data, list):
        return pd.DataFrame(raw_data)

    if isinstance(raw_data, dict):

        data = raw_data.get("data")

        if isinstance(data, list):
            return pd.DataFrame(data)

        if isinstance(data, dict):
            return pd.DataFrame([data])

        # SSI có thể trả code 204 và không có data.
        if raw_data.get("code") == 204:
            return pd.DataFrame()

        return pd.DataFrame([raw_data])

    logger.warning(
        "Không hỗ trợ kiểu dữ liệu: %s",
        type(raw_data).__name__
    )

    return pd.DataFrame()


def find_column(df, candidates):
    """Tìm tên cột không phân biệt chữ hoa, chữ thường."""

    columns = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:

        key = candidate.strip().lower()

        if key in columns:
            return columns[key]

    return None


# ============================================================
# 3. PHÂN LOẠI CHỨNG KHOÁN
# ============================================================

def is_index_security(symbol, name):

    symbol = normalize_text(symbol)
    name = normalize_text(name)

    if symbol in INDEX_SYMBOLS:
        return True

    if symbol.endswith("INDEX"):
        return True

    if "CHỈ SỐ" in name or "INDEX" in name:
        return True

    if name.startswith("VN") and any(
        keyword in name
        for keyword in [
            "GROWTH",
            "DIVIDEND",
            "SHARE",
            "CAP"
        ]
    ):
        return True

    return False


def is_future_symbol(symbol):

    symbol = normalize_text(symbol)

    patterns = [
        r"\d{2}[A-Z]\d[A-Z]{2}\d{3}",
        r"\d{2}[A-Z]{2}[A-Z]\d{3}"
    ]

    return any(
        re.fullmatch(pattern, symbol)
        for pattern in patterns
    )


def has_company_evidence(name):

    name = normalize_text(name)

    company_patterns = [
        "CÔNG TY CỔ PHẦN",
        "CÔNG TY CP",
        "CTCP",
        "TỔNG CÔNG TY CỔ PHẦN",
        "TẬP ĐOÀN CỔ PHẦN"
    ]

    return any(
        pattern in name
        for pattern in company_patterns
    )


def classify_security(row):
    """Phân loại từng mã chứng khoán."""

    symbol = normalize_text(row.get("symbol"))
    name = normalize_text(row.get("name"))
    stock_type = normalize_text(row.get("stock_type"))
    cw_underlying = normalize_text(
        row.get("cw_underlying_symbol")
    )

    if not symbol:
        return False, "MISSING_SYMBOL"

    if is_index_security(symbol, name):
        return False, "INDEX"

    if cw_underlying:
        return False, "WARRANT"

    if stock_type == "STOCK":
        return True, "SSI_STOCK"

    if stock_type in EXCLUDED_STOCK_TYPES:
        return False, f"EXCLUDED_{stock_type}"

    if stock_type:
        return False, f"UNKNOWN_TYPE_{stock_type}"

    if is_future_symbol(symbol):
        return False, "FUTURE_SYMBOL"

    excluded_name_patterns = [
        "ETF",
        "QUỸ ĐẦU TƯ",
        "QUỸ MỞ",
        "QUỸ ĐÓNG",
        "QUỸ",
        "INVESTMENT FUND",
        "TRUST",
        "CHỨNG QUYỀN",
        "TRÁI PHIẾU",
        "HỢP ĐỒNG TƯƠNG LAI",
        "CÔNG TY TNHH",
        "CÔNG TY TRÁCH NHIỆM HỮU HẠN"
    ]

    if any(
        pattern in name
        for pattern in excluded_name_patterns
    ):
        return False, "EXCLUDED_BY_NAME"

    if has_company_evidence(name):
        return True, "INFERRED_COMPANY_NAME"

    return False, "UNRESOLVED"


# ============================================================
# 4. CHUẨN HÓA DANH SÁCH CHỨNG KHOÁN
# ============================================================

def normalize_securities(raw_data, board):

    df = convert_to_dataframe(raw_data)

    if df.empty:
        return pd.DataFrame()

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    # SSI sử dụng symbolNameVi thay vì stockName.
    symbol_col = find_column(
        df,
        ["symbol", "stockSymbol", "code"]
    )

    name_col = find_column(
        df,
        [
            "symbolNameVi",
            "stockName",
            "name",
            "securityName",
            "companyName",
            "organName"
        ]
    )

    stock_type_col = find_column(
        df,
        [
            "stockType",
            "stock_type",
            "securityType"
        ]
    )

    cw_col = find_column(
        df,
        [
            "cwUnderlyingSymbol",
            "cw_underlying_symbol"
        ]
    )

    icb_col = find_column(
        df,
        [
            "icbName",
            "icb_name",
            "industryName",
            "industry"
        ]
    )

    if symbol_col is None:

        logger.error(
            "%s: Không tìm thấy cột mã chứng khoán. "
            "Các cột hiện có: %s",
            board,
            list(df.columns)
        )

        return pd.DataFrame()

    result = pd.DataFrame(index=df.index)

    result["symbol"] = (
        df[symbol_col]
        .apply(normalize_text)
    )

    if name_col is not None:
        result["name"] = (
            df[name_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        result["name"] = ""

    result["board"] = board

    if icb_col is not None:
        result["icb_name"] = df[icb_col]
    else:
        result["icb_name"] = None

    if stock_type_col is not None:
        result["stock_type"] = df[stock_type_col]
    else:
        result["stock_type"] = None

    if cw_col is not None:
        result["cw_underlying_symbol"] = df[cw_col]
    else:
        result["cw_underlying_symbol"] = None

    result["stock_type"] = (
        result["stock_type"]
        .apply(normalize_text)
        .replace("", None)
    )

    result["cw_underlying_symbol"] = (
        result["cw_underlying_symbol"]
        .apply(normalize_text)
    )

    result = result[
        result["symbol"].notna()
        & (result["symbol"] != "")
    ].copy()

    result = result.drop_duplicates(
        subset=["symbol"],
        keep="last"
    ).reset_index(drop=True)

    if result.empty:
        return pd.DataFrame()

    classifications = result.apply(
        classify_security,
        axis=1
    )

    result["is_valid_stock"] = [
        item[0] for item in classifications
    ]

    result["classification_reason"] = [
        item[1] for item in classifications
    ]

    reason_counts = (
        result["classification_reason"]
        .value_counts()
        .to_dict()
    )

    valid_count = int(
        result["is_valid_stock"].sum()
    )

    logger.info(
        "%s: Tổng %s mã | Hợp lệ %s | Bị loại %s",
        board,
        len(result),
        valid_count,
        len(result) - valid_count
    )

    logger.info(
        "%s: Chi tiết phân loại: %s",
        board,
        reason_counts
    )

    valid = result[
        result["is_valid_stock"]
    ].copy()

    return valid[
        [
            "symbol",
            "name",
            "board",
            "icb_name",
            "stock_type"
        ]
    ].reset_index(drop=True)


# ============================================================
# 5. BỔ SUNG MÃ ĐÃ XÁC MINH CÓ DỮ LIỆU OHLC
# ============================================================

def add_supplemental_securities(securities):
    """
    Bổ sung mã không xuất hiện trong securitiesByBoard.

    Chỉ sử dụng cho các mã đã được xác minh có dữ liệu OHLC.
    Metadata bổ sung được khai báo riêng, không giả định
    SSI đã trả về thông tin đó.
    """

    if not SUPPLEMENTAL_SYMBOLS:
        return securities

    frames = [securities.copy()]

    existing_symbols = set(
        securities["symbol"]
        .astype(str)
        .str.upper()
        .tolist()
    )

    added_symbols = []

    for symbol in SUPPLEMENTAL_SYMBOLS:

        if symbol in existing_symbols:
            continue

        metadata = SUPPLEMENTAL_METADATA.get(symbol)

        if metadata is None:

            logger.warning(
                "%s: Chưa có metadata bổ sung. "
                "Bỏ qua mã này.",
                symbol
            )

            continue

        row = {
            "symbol": symbol,
            "name": metadata["name"],
            "board": metadata["board"],
            "icb_name": metadata.get("icb_name"),
            "stock_type": metadata.get("stock_type", "STOCK")
        }

        frames.append(
            pd.DataFrame([row])
        )

        added_symbols.append(symbol)
        existing_symbols.add(symbol)

    if added_symbols:

        logger.info(
            "Bổ sung mã ngoài danh sách SSI: %s",
            added_symbols
        )

    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(
            subset=["symbol"],
            keep="last"
        )
        .reset_index(drop=True)
    )


# ============================================================
# 6. CHUẨN HÓA DỮ LIỆU OHLC
# ============================================================

def normalize_ohlc(raw_data, symbol):

    df = convert_to_dataframe(raw_data)

    if df.empty:
        return pd.DataFrame()

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    date_col = find_column(
        df,
        [
            "tradingdate",
            "trading_date",
            "date"
        ]
    )

    open_col = find_column(df, ["open"])
    high_col = find_column(df, ["high"])
    low_col = find_column(df, ["low"])
    close_col = find_column(df, ["close"])

    volume_col = find_column(
        df,
        ["volume", "totalvolume"]
    )

    value_col = find_column(
        df,
        [
            "value",
            "tradingvalue",
            "totalvalue",
            "totaltradingvalue"
        ]
    )

    required = [
        date_col,
        open_col,
        high_col,
        low_col,
        close_col,
        volume_col
    ]

    if any(column is None for column in required):

        logger.warning(
            "%s: Dữ liệu OHLC thiếu cột bắt buộc. "
            "Các cột hiện có: %s",
            symbol,
            list(df.columns)
        )

        return pd.DataFrame()

    result = pd.DataFrame(index=df.index)

    result["symbol"] = symbol

    result["trading_date"] = pd.to_datetime(
        df[date_col],
        errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    for target, source in [
        ("open", open_col),
        ("high", high_col),
        ("low", low_col),
        ("close", close_col),
        ("volume", volume_col)
    ]:

        result[target] = pd.to_numeric(
            df[source],
            errors="coerce"
        )

    if value_col is not None:

        result["value"] = pd.to_numeric(
            df[value_col],
            errors="coerce"
        )

    else:
        result["value"] = float("nan")

    result = result.dropna(
        subset=[
            "trading_date",
            "close"
        ]
    )

    result = result[
        result["close"] > 0
    ].copy()

    result = result.drop_duplicates(
        subset=[
            "symbol",
            "trading_date"
        ],
        keep="last"
    )

    return result[
        [
            "symbol",
            "trading_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "value"
        ]
    ].reset_index(drop=True)


# ============================================================
# 7. THU THẬP DANH SÁCH CHỨNG KHOÁN
# ============================================================

def collect_securities(client, db):

    logger.info(
        "BẮT ĐẦU THU THẬP DANH SÁCH CHỨNG KHOÁN"
    )

    if not BOARDS:
        raise RuntimeError(
            "Không có sàn nào được cấu hình trong BOARDS."
        )

    frames = []
    failed_boards = []

    for board in BOARDS:

        try:

            raw = client.get_securities_by_board(board)

            raw_df = convert_to_dataframe(raw)

            if raw_df.empty:
                raise RuntimeError(
                    "SSI trả về danh sách rỗng."
                )

            normalized = normalize_securities(
                raw_df,
                board
            )

            logger.info(
                "%s: %s mã cổ phiếu hợp lệ.",
                board,
                len(normalized)
            )

            if normalized.empty:
                raise RuntimeError(
                    "Không nhận diện được cổ phiếu hợp lệ."
                )

            frames.append(normalized)

        except Exception as exc:

            failed_boards.append(board)

            logger.exception(
                "%s: Lỗi thu thập danh sách: %s",
                board,
                exc
            )

        if REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)

    if failed_boards:

        raise RuntimeError(
            "Không thể cập nhật danh sách chứng khoán vì "
            "các sàn sau bị lỗi: "
            + ", ".join(failed_boards)
            + ". Danh sách cũ trong database được giữ nguyên."
        )

    if not frames:
        raise RuntimeError(
            "Không thu thập được danh sách cổ phiếu hợp lệ."
        )

    securities = pd.concat(
        frames,
        ignore_index=True
    )

    securities = securities.drop_duplicates(
        subset=["symbol"],
        keep="last"
    ).reset_index(drop=True)

    if securities.empty:
        raise RuntimeError(
            "Danh sách cổ phiếu sau khi tổng hợp bị rỗng."
        )

    # Bổ sung mã đã xác minh có dữ liệu OHLC.
    securities = add_supplemental_securities(
        securities
    )

    # Chỉ cập nhật sau khi đã thu thập đủ các sàn.
    db.save_securities(securities)

    logger.info(
        "HOÀN TẤT: %s mã cổ phiếu được lưu.",
        len(securities)
    )

    logger.info(
        "Phân bổ theo sàn: %s",
        securities["board"].value_counts().to_dict()
    )

    return securities


# ============================================================
# 8. XÁC ĐỊNH NGÀY BẮT ĐẦU THU THẬP
# ============================================================

def get_symbol_start_date(
    db,
    symbol,
    default_start
):

    status = db.get_symbol_price_status(symbol)

    if not status or status["row_count"] == 0:
        return default_start

    first_date = pd.to_datetime(
        status["first_date"],
        errors="coerce"
    )

    latest_date = pd.to_datetime(
        status["latest_date"],
        errors="coerce"
    )

    if pd.isna(first_date) or pd.isna(latest_date):
        return default_start

    first_date = first_date.date()
    latest_date = latest_date.date()

    if first_date > default_start:
        return default_start

    return latest_date - timedelta(
        days=OVERLAP_DAYS
    )


# ============================================================
# 9. GHI NHẬT KÝ AN TOÀN
# ============================================================

def safe_log_collection(
    db,
    symbol,
    status,
    message,
    rows_collected=0
):

    try:

        db.log_collection(
            symbol,
            status,
            message,
            rows_collected
        )

    except Exception:

        logger.exception(
            "%s: Không thể ghi nhật ký thu thập.",
            symbol
        )


# ============================================================
# 10. THU THẬP DỮ LIỆU GIÁ TỪNG MÃ
# ============================================================

def collect_symbol_ohlc(
    client,
    db,
    symbol,
    start_date,
    end_date
):

    try:

        raw = client.get_ohlc_all(
            symbol=symbol,
            from_date=start_date.strftime("%Y-%m-%d"),
            to_date=end_date.strftime("%Y-%m-%d"),
            page_size=PAGE_SIZE,
            max_pages=MAX_PAGES
        )

        normalized = normalize_ohlc(
            raw,
            symbol
        )

        if normalized.empty:

            safe_log_collection(
                db,
                symbol,
                "EMPTY",
                "Không có dữ liệu OHLC hợp lệ.",
                0
            )

            logger.warning(
                "%s: Không có dữ liệu OHLC hợp lệ.",
                symbol
            )

            return 0

        rows = db.save_prices(normalized)

        safe_log_collection(
            db,
            symbol,
            "SUCCESS",
            "Thu thập dữ liệu thành công.",
            rows
        )

        logger.info(
            "%s: Đã ghi/cập nhật %s dòng giá.",
            symbol,
            rows
        )

        return rows

    except SSIAPIError as exc:

        safe_log_collection(
            db,
            symbol,
            "ERROR",
            str(exc),
            0
        )

        logger.error(
            "%s: Lỗi SSI API: %s",
            symbol,
            exc
        )

        return -1

    except Exception as exc:

        safe_log_collection(
            db,
            symbol,
            "ERROR",
            str(exc),
            0
        )

        logger.exception(
            "%s: Lỗi thu thập dữ liệu.",
            symbol
        )

        return -1


# ============================================================
# 11. CHƯƠNG TRÌNH CHÍNH
# ============================================================

def main():

    logger.info("=" * 65)
    logger.info("BẮT ĐẦU THU THẬP DỮ LIỆU SSI")
    logger.info("=" * 65)

    db = StockDatabase()
    client = SSIClient()

    # --------------------------------------------------------
    # 11.1. Xác thực SSI API
    # --------------------------------------------------------

    try:

        client.authenticate()

    except Exception as exc:

        logger.exception(
            "Không thể xác thực SSI API: %s",
            exc
        )

        return

    # --------------------------------------------------------
    # 11.2. Thu thập danh sách cổ phiếu
    # --------------------------------------------------------

    try:

        securities = collect_securities(
            client,
            db
        )

    except Exception as exc:

        logger.exception(
            "Không thể thu thập danh sách chứng khoán: %s",
            exc
        )

        return

    # --------------------------------------------------------
    # 11.3. Giới hạn số mã nếu MAX_SYMBOLS > 0
    # --------------------------------------------------------

    if MAX_SYMBOLS > 0:

        supplemental_rows = securities[
            securities["symbol"].isin(
                SUPPLEMENTAL_SYMBOLS
            )
        ].copy()

        securities = securities.head(
            MAX_SYMBOLS
        ).copy()

        # Không để MAX_SYMBOLS vô tình loại HPG.
        securities = pd.concat(
            [
                securities,
                supplemental_rows
            ],
            ignore_index=True
        ).drop_duplicates(
            subset=["symbol"],
            keep="last"
        )

        logger.info(
            "Chế độ giới hạn: %s mã thông thường "
            "và %s mã bổ sung.",
            min(MAX_SYMBOLS, len(securities)),
            len(supplemental_rows)
        )

    symbols = securities[
        "symbol"
    ].tolist()

    # VNINDEX chỉ dùng làm chỉ số tham chiếu.
    symbols.append("VNINDEX")

    symbols = list(dict.fromkeys(symbols))

    # --------------------------------------------------------
    # 11.4. Xác định khoảng thời gian
    # --------------------------------------------------------

    today = date.today()

    default_start = today - timedelta(
        days=LOOKBACK_DAYS
    )

    total = len(symbols)

    total_rows = 0
    successful_symbols = 0
    empty_symbols = 0
    failed_symbols = 0

    interrupted = False

    logger.info(
        "Tổng số mã cần thu thập: %s",
        total
    )

    logger.info(
        "Khoảng thời gian mặc định: %s đến %s",
        default_start,
        today
    )

    logger.info(
        "Số phiên lịch sử tối thiểu dự kiến: %s",
        MIN_HISTORY
    )

    # --------------------------------------------------------
    # 11.5. Thu thập dữ liệu từng mã
    # --------------------------------------------------------

    try:

        for index, symbol in enumerate(
            symbols,
            start=1
        ):

            logger.info(
                "[%s/%s] Đang thu thập %s",
                index,
                total,
                symbol
            )

            start_date = get_symbol_start_date(
                db,
                symbol,
                default_start
            )

            rows = collect_symbol_ohlc(
                client,
                db,
                symbol,
                start_date,
                today
            )

            if rows > 0:

                total_rows += rows
                successful_symbols += 1

            elif rows == 0:

                empty_symbols += 1

            else:

                failed_symbols += 1

            if REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)

    except KeyboardInterrupt:

        interrupted = True

        logger.warning(
            "Người dùng đã dừng quá trình thu thập."
        )

    # --------------------------------------------------------
    # 11.6. Tổng kết
    # --------------------------------------------------------

    stats = db.get_database_stats()

    logger.info("=" * 65)

    if interrupted:
        logger.info("ĐÃ DỪNG THU THẬP THEO YÊU CẦU")
    else:
        logger.info("HOÀN TẤT THU THẬP DỮ LIỆU")

    logger.info(
        "Số mã trong danh sách: %s",
        total
    )

    logger.info(
        "Số mã thu thập thành công: %s",
        successful_symbols
    )

    logger.info(
        "Số mã không có dữ liệu OHLC hợp lệ: %s",
        empty_symbols
    )

    logger.info(
        "Số mã gặp lỗi: %s",
        failed_symbols
    )

    logger.info(
        "Số dòng giá được ghi/cập nhật: %s",
        total_rows
    )

    logger.info(
        "Tổng số mã trong database: %s",
        stats["securities"]
    )

    logger.info(
        "Tổng số dòng giá trong database: %s",
        stats["price_rows"]
    )

    logger.info(
        "Số mã có dữ liệu giá: %s",
        stats["symbols_with_prices"]
    )

    logger.info(
        "Số dòng dữ liệu VNINDEX: %s",
        stats["benchmark_rows"]
    )

    logger.info(
        "Cập nhật gần nhất: %s",
        db.get_latest_update()
    )

    logger.info("=" * 65)


if __name__ == "__main__":
    main()
