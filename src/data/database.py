import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

import pandas as pd
from dotenv import load_dotenv


load_dotenv()

DEFAULT_DB_PATH = "data/market_data.db"


class StockDatabase:

    def __init__(self, db_path=None):

        # Thứ tự ưu tiên: tham số truyền vào, biến môi trường
        # DATABASE_PATH (trong .env), rồi mới đến đường dẫn mặc định.
        if db_path is None:
            db_path = (
                os.getenv("DATABASE_PATH", "").strip()
                or DEFAULT_DB_PATH
            )

        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self._create_tables()

    # ========================================================
    # KẾT NỐI DATABASE
    # ========================================================

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30
        )

        conn.row_factory = sqlite3.Row

        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")

            yield conn

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    @staticmethod
    def _get_columns(conn, table_name):

        rows = conn.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()

        return {
            row["name"]
            for row in rows
        }

    @staticmethod
    def _is_missing(value):

        if value is None:
            return True

        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass

        if isinstance(value, str):
            return value.strip().upper() in {
                "",
                "NONE",
                "NAN",
                "NULL",
                "N/A"
            }

        return False

    @classmethod
    def _clean_text(cls, value):

        if cls._is_missing(value):
            return None

        return str(value).strip()

    # ========================================================
    # TẠO BẢNG VÀ MIGRATION
    # ========================================================

    def _create_tables(self):

        with self._connect() as conn:

            conn.execute("PRAGMA journal_mode = WAL")

            # ------------------------------------------------
            # BẢNG DANH SÁCH CHỨNG KHOÁN
            # ------------------------------------------------

            conn.execute("""
                CREATE TABLE IF NOT EXISTS securities (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    board TEXT,
                    icb_name TEXT,
                    stock_type TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ------------------------------------------------
            # BẢNG DỮ LIỆU GIÁ
            # ------------------------------------------------

            conn.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    symbol TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    value REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                    PRIMARY KEY (symbol, trading_date)
                )
            """)

            # ------------------------------------------------
            # BẢNG NHẬT KÝ THU THẬP
            # ------------------------------------------------

            conn.execute("""
                CREATE TABLE IF NOT EXISTS collection_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    status TEXT,
                    message TEXT,
                    rows_collected INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # =================================================
            # MIGRATION SECURITIES
            # =================================================

            security_columns = self._get_columns(
                conn,
                "securities"
            )

            security_migrations = {
                "name": "TEXT",
                "board": "TEXT",
                "icb_name": "TEXT",
                "stock_type": "TEXT",
                "updated_at": "TEXT"
            }

            for column, data_type in security_migrations.items():

                if column not in security_columns:
                    conn.execute(
                        f"""
                        ALTER TABLE securities
                        ADD COLUMN {column} {data_type}
                        """
                    )

            # =================================================
            # MIGRATION PRICES
            # =================================================

            price_columns = self._get_columns(
                conn,
                "prices"
            )

            price_migrations = {
                "open": "REAL",
                "high": "REAL",
                "low": "REAL",
                "close": "REAL",
                "volume": "REAL",
                "value": "REAL",
                "updated_at": "TEXT"
            }

            for column, data_type in price_migrations.items():

                if column not in price_columns:
                    conn.execute(
                        f"""
                        ALTER TABLE prices
                        ADD COLUMN {column} {data_type}
                        """
                    )

            # =================================================
            # MIGRATION COLLECTION_LOG
            # =================================================

            log_columns = self._get_columns(
                conn,
                "collection_log"
            )

            log_migrations = {
                "symbol": "TEXT",
                "status": "TEXT",
                "message": "TEXT",
                "rows_collected": "INTEGER DEFAULT 0",
                "created_at": "TEXT"
            }

            for column, data_type in log_migrations.items():

                if column not in log_columns:
                    conn.execute(
                        f"""
                        ALTER TABLE collection_log
                        ADD COLUMN {column} {data_type}
                        """
                    )

            # Lấy lại cấu trúc sau migration
            log_columns = self._get_columns(
                conn,
                "collection_log"
            )

            # Chuyển row_count cũ sang rows_collected.
            # Không ghi đè dữ liệu đã có giá trị khác 0.
            if "row_count" in log_columns:

                conn.execute("""
                    UPDATE collection_log
                    SET rows_collected = row_count
                    WHERE row_count IS NOT NULL
                      AND (
                          rows_collected IS NULL
                          OR rows_collected = 0
                      )
                """)

            # Chuyển collected_at cũ sang created_at.
            if "collected_at" in log_columns:

                conn.execute("""
                    UPDATE collection_log
                    SET created_at = collected_at
                    WHERE collected_at IS NOT NULL
                      AND (
                          created_at IS NULL
                          OR created_at = ''
                      )
                """)

            conn.execute("""
                UPDATE collection_log
                SET rows_collected = 0
                WHERE rows_collected IS NULL
            """)

            conn.execute("""
                UPDATE collection_log
                SET created_at = CURRENT_TIMESTAMP
                WHERE created_at IS NULL
                   OR created_at = ''
            """)

            # =================================================
            # BỔ SUNG UPDATED_AT CHO DỮ LIỆU CŨ
            # =================================================

            conn.execute("""
                UPDATE securities
                SET updated_at = CURRENT_TIMESTAMP
                WHERE updated_at IS NULL
                   OR updated_at = ''
            """)

            conn.execute("""
                UPDATE prices
                SET updated_at = CURRENT_TIMESTAMP
                WHERE updated_at IS NULL
                   OR updated_at = ''
            """)

            # =================================================
            # INDEX
            # =================================================

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_symbol
                ON prices(symbol)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_date
                ON prices(trading_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_symbol_date
                ON prices(symbol, trading_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_collection_log_symbol
                ON collection_log(symbol)
            """)

    # ========================================================
    # LƯU DANH SÁCH CHỨNG KHOÁN
    # ========================================================

    def save_securities(self, df):

        if df is None or df.empty:
            return 0

        required_columns = [
            "symbol",
            "name",
            "board",
            "icb_name",
            "stock_type"
        ]

        data = df.copy()

        for column in required_columns:

            if column not in data.columns:
                data[column] = None

        data = data[required_columns].copy()

        # Chuẩn hóa mã chứng khoán
        data["symbol"] = (
            data["symbol"]
            .apply(self._clean_text)
            .apply(
                lambda value: (
                    value.upper()
                    if value is not None
                    else None
                )
            )
        )

        data = data[
            data["symbol"].notna()
        ].copy()

        if data.empty:
            return 0

        # Chuẩn hóa các trường văn bản
        for column in [
            "name",
            "board",
            "icb_name",
            "stock_type"
        ]:

            data[column] = data[column].apply(
                self._clean_text
            )

        # Loại bỏ mã trùng
        data = data.drop_duplicates(
            subset=["symbol"],
            keep="last"
        )

        records = []

        for row in data.itertuples(index=False):

            records.append((
                row.symbol,
                row.name,
                row.board,
                row.icb_name,
                row.stock_type
            ))

        if not records:
            return 0

        with self._connect() as conn:

            # Tạo bảng tạm
            conn.execute("""
                CREATE TEMP TABLE IF NOT EXISTS temp_current_securities (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    board TEXT,
                    icb_name TEXT,
                    stock_type TEXT
                )
            """)

            conn.execute("""
                DELETE FROM temp_current_securities
            """)

            conn.executemany("""
                INSERT OR REPLACE INTO temp_current_securities (
                    symbol,
                    name,
                    board,
                    icb_name,
                    stock_type
                )
                VALUES (?, ?, ?, ?, ?)
            """, records)

            # LƯU VÀ CẬP NHẬT DANH SÁCH CHỨNG KHOÁN
            #
            # WHERE 1 rất quan trọng:
            # Giúp SQLite phân biệt WHERE của SELECT
            # với ON CONFLICT của UPSERT.

            conn.execute("""
                INSERT INTO securities (
                    symbol,
                    name,
                    board,
                    icb_name,
                    stock_type,
                    updated_at
                )
                SELECT
                    symbol,
                    name,
                    board,
                    icb_name,
                    stock_type,
                    CURRENT_TIMESTAMP
                FROM temp_current_securities
                WHERE 1
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    board = excluded.board,
                    icb_name = excluded.icb_name,
                    stock_type = excluded.stock_type,
                    updated_at = CURRENT_TIMESTAMP
            """)

            # Chỉ xóa mã khỏi bảng securities nếu mã đó
            # không còn trong danh sách SSI trả về.
            #
            # Không xóa lịch sử giá trong bảng prices.

            conn.execute("""
                DELETE FROM securities
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM temp_current_securities AS current
                    WHERE current.symbol = securities.symbol
                )
            """)

            conn.execute("""
                DROP TABLE IF EXISTS temp_current_securities
            """)

        return len(records)

    # ========================================================
    # LƯU DỮ LIỆU GIÁ
    # ========================================================

    def save_prices(self, df):

        if df is None or df.empty:
            return 0

        required_columns = [
            "symbol",
            "trading_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "value"
        ]

        data = df.copy()

        for column in required_columns:

            if column not in data.columns:
                data[column] = None

        data = data[required_columns].copy()

        # Chuẩn hóa mã
        data["symbol"] = (
            data["symbol"]
            .apply(self._clean_text)
            .apply(
                lambda value: (
                    value.upper()
                    if value is not None
                    else None
                )
            )
        )

        # Chuẩn hóa ngày giao dịch
        data["trading_date"] = pd.to_datetime(
            data["trading_date"],
            errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        # Chuyển các cột số về dạng numeric
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "value"
        ]

        for column in numeric_columns:

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce"
            )

        # Loại dữ liệu không hợp lệ
        data = data.dropna(
            subset=[
                "symbol",
                "trading_date",
                "close"
            ]
        )

        data = data[
            (data["symbol"] != "")
            & (data["close"] > 0)
        ].copy()

        data = data.drop_duplicates(
            subset=[
                "symbol",
                "trading_date"
            ],
            keep="last"
        )

        if data.empty:
            return 0

        records = []

        for row in data.itertuples(index=False):

            values = []

            for value in row:

                if pd.isna(value):
                    values.append(None)

                elif hasattr(value, "item"):
                    values.append(value.item())

                else:
                    values.append(value)

            records.append(tuple(values))

        with self._connect() as conn:

            conn.executemany("""
                INSERT INTO prices (
                    symbol,
                    trading_date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    value,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP
                )

                ON CONFLICT(symbol, trading_date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, records)

        return len(records)

    # ========================================================
    # LẤY DANH SÁCH CHỨNG KHOÁN
    # ========================================================

    def get_securities(self):

        with self._connect() as conn:

            rows = conn.execute("""
                SELECT
                    symbol,
                    name,
                    board,
                    icb_name,
                    stock_type,
                    updated_at
                FROM securities
                ORDER BY board, symbol
            """).fetchall()

        return pd.DataFrame(
            [dict(row) for row in rows]
        )

    # ========================================================
    # LẤY DỮ LIỆU GIÁ
    # ========================================================

    def get_prices(self, symbols=None):

        with self._connect() as conn:

            # Lấy toàn bộ dữ liệu
            if symbols is None:

                rows = conn.execute("""
                    SELECT
                        symbol,
                        trading_date,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        value,
                        updated_at
                    FROM prices
                    ORDER BY symbol, trading_date
                """).fetchall()

                return self._prices_to_dataframe(rows)

            # Chuẩn hóa danh sách mã
            symbols = list(dict.fromkeys(
                str(symbol).strip().upper()
                for symbol in symbols
                if symbol is not None
                and str(symbol).strip() != ""
            ))

            if not symbols:
                return pd.DataFrame()

            result_frames = []

            # Giới hạn biến truy vấn SQLite
            chunk_size = 900

            for start in range(
                0,
                len(symbols),
                chunk_size
            ):

                chunk = symbols[
                    start:start + chunk_size
                ]

                placeholders = ",".join(
                    ["?"] * len(chunk)
                )

                query = f"""
                    SELECT
                        symbol,
                        trading_date,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        value,
                        updated_at
                    FROM prices
                    WHERE symbol IN ({placeholders})
                    ORDER BY symbol, trading_date
                """

                rows = conn.execute(
                    query,
                    chunk
                ).fetchall()

                if rows:

                    result_frames.append(
                        self._prices_to_dataframe(rows)
                    )

            if not result_frames:
                return pd.DataFrame()

            return pd.concat(
                result_frames,
                ignore_index=True
            )

    @staticmethod
    def _prices_to_dataframe(rows):

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(
            [dict(row) for row in rows]
        )

        if "trading_date" in df.columns:

            df["trading_date"] = pd.to_datetime(
                df["trading_date"],
                errors="coerce"
            )

        return df

    # ========================================================
    # TRẠNG THÁI DỮ LIỆU CỦA MỘT MÃ
    # ========================================================

    def get_symbol_price_status(self, symbol):

        symbol = str(symbol).strip().upper()

        with self._connect() as conn:

            row = conn.execute("""
                SELECT
                    COUNT(*) AS row_count,
                    MIN(trading_date) AS first_date,
                    MAX(trading_date) AS latest_date
                FROM prices
                WHERE symbol = ?
            """, (symbol,)).fetchone()

        if row is None:

            return {
                "row_count": 0,
                "first_date": None,
                "latest_date": None
            }

        return {
            "row_count": int(row["row_count"] or 0),
            "first_date": row["first_date"],
            "latest_date": row["latest_date"]
        }

    # ========================================================
    # NHẬT KÝ THU THẬP
    # ========================================================

    def log_collection(
        self,
        symbol,
        status,
        message="",
        rows_collected=0
    ):

        symbol = str(symbol).strip().upper()

        try:
            rows_collected = int(rows_collected or 0)
        except (TypeError, ValueError):
            rows_collected = 0

        values = {
            "symbol": symbol,
            "status": str(status),
            "message": str(message),
            "rows_collected": rows_collected,
            "created_at": None,
            "row_count": rows_collected,
            "collected_at": None
        }

        with self._connect() as conn:

            log_columns = self._get_columns(
                conn,
                "collection_log"
            )

            insert_columns = []
            insert_values = []

            for column, value in values.items():

                if column not in log_columns:
                    continue

                if column in {
                    "created_at",
                    "collected_at"
                }:
                    insert_columns.append(column)
                    insert_values.append(
                        pd.Timestamp.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )

                else:
                    insert_columns.append(column)
                    insert_values.append(value)

            placeholders = ", ".join(
                ["?"] * len(insert_columns)
            )

            column_sql = ", ".join(
                insert_columns
            )

            conn.execute(
                f"""
                INSERT INTO collection_log (
                    {column_sql}
                )
                VALUES ({placeholders})
                """,
                insert_values
            )

    def get_collection_summary(self, limit=100):

        limit = max(1, int(limit))

        with self._connect() as conn:

            rows = conn.execute("""
                SELECT
                    id,
                    symbol,
                    status,
                    message,
                    rows_collected,
                    created_at
                FROM collection_log
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return pd.DataFrame(
            [dict(row) for row in rows]
        )

    # ========================================================
    # THỐNG KÊ DATABASE
    # ========================================================

    def get_database_stats(self):

        with self._connect() as conn:

            securities_count = conn.execute("""
                SELECT COUNT(*) AS total
                FROM securities
            """).fetchone()["total"]

            price_rows = conn.execute("""
                SELECT COUNT(*) AS total
                FROM prices
            """).fetchone()["total"]

            symbols_with_prices = conn.execute("""
                SELECT COUNT(DISTINCT symbol) AS total
                FROM prices
            """).fetchone()["total"]

            benchmark_rows = conn.execute("""
                SELECT COUNT(*) AS total
                FROM prices
                WHERE symbol = 'VNINDEX'
            """).fetchone()["total"]

        return {
            "securities": int(securities_count or 0),
            "price_rows": int(price_rows or 0),
            "symbols_with_prices": int(symbols_with_prices or 0),
            "benchmark_rows": int(benchmark_rows or 0)
        }

    # ========================================================
    # THỜI ĐIỂM CẬP NHẬT GẦN NHẤT
    # ========================================================

    def get_latest_update(self):

        with self._connect() as conn:

            benchmark_date = conn.execute("""
                SELECT MAX(trading_date) AS latest_date
                FROM prices
                WHERE symbol = 'VNINDEX'
            """).fetchone()["latest_date"]

            if benchmark_date:
                return benchmark_date

            latest_date = conn.execute("""
                SELECT MAX(trading_date) AS latest_date
                FROM prices
            """).fetchone()["latest_date"]

        return latest_date