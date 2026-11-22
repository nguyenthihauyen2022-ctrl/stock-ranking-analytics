import os
import time

from datetime import date, datetime

import requests
from dotenv import load_dotenv


load_dotenv()


class SSIAPIError(Exception):

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class SSIClient:

    def __init__(self):

        self.base_url = os.getenv(
            "SSI_BASE_URL",
            "https://api.ssi.com.vn"
        ).rstrip("/")

        self.api_key = os.getenv(
            "SSI_API_KEY",
            ""
        ).strip()

        self.api_secret = os.getenv(
            "SSI_API_SECRET",
            ""
        ).strip()

        if not self.api_key or not self.api_secret:
            raise SSIAPIError(
                "Thiếu SSI_API_KEY hoặc SSI_API_SECRET trong file .env"
            )

        self.session = requests.Session()

        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SSI-Stock-Analytics/1.0"
        })

        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0

    # ========================================================
    # URL
    # ========================================================

    def _url(self, endpoint):
        return f"{self.base_url}{endpoint}"

    # ========================================================
    # XÁC THỰC
    # ========================================================

    def authenticate(self):

        url = self._url("/api/v3/auth/token")

        payload = {
            "apiKey": self.api_key,
            "apiSecret": self.api_secret
        }

        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=30
            )

        except requests.RequestException as exc:
            raise SSIAPIError(
                f"Không kết nối được SSI khi xác thực: {exc}"
            ) from exc

        if response.status_code != 200:
            raise SSIAPIError(
                "SSI authentication thất bại: "
                f"{response.status_code} - {response.text[:500]}",
                status_code=response.status_code
            )

        try:
            result = response.json()

        except ValueError as exc:
            raise SSIAPIError(
                "SSI trả về dữ liệu xác thực không phải JSON."
            ) from exc

        if not isinstance(result, dict):
            raise SSIAPIError(
                "Cấu trúc dữ liệu xác thực SSI không hợp lệ."
            )

        token_data = result

        if isinstance(result.get("data"), dict):
            token_data = result["data"]

        token = (
            token_data.get("accessToken")
            or token_data.get("access_token")
        )

        if not token:
            raise SSIAPIError(
                f"SSI không trả accessToken: {result}"
            )

        self.access_token = token

        self.refresh_token = (
            token_data.get("refreshToken")
            or token_data.get("refresh_token")
        )

        expires_at = token_data.get("expiresAt")
        expires_in = token_data.get("expiresIn", 1800)

        try:

            if expires_at is not None:

                expiry = float(expires_at)

                # Hỗ trợ timestamp mili giây.
                if expiry > 10_000_000_000:
                    expiry /= 1000

                self.token_expiry = expiry

            else:
                self.token_expiry = (
                    time.time() + float(expires_in)
                )

        except (TypeError, ValueError):
            self.token_expiry = time.time() + 1800

        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })

        print("SSI authentication successful")

    def _ensure_token(self):

        if not self.access_token:
            self.authenticate()
            return

        if time.time() >= self.token_expiry - 60:
            self.authenticate()

    # ========================================================
    # CHUẨN HÓA NGÀY
    # ========================================================

    @staticmethod
    def _format_daily_date(value, field_name):

        accepted_formats = [
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y-%m-%d"
        ]

        is_date_only = False

        if isinstance(value, datetime):
            parsed_date = value

        elif isinstance(value, date):
            parsed_date = datetime.combine(
                value,
                datetime.min.time()
            )
            is_date_only = True

        elif isinstance(value, str):

            value = value.strip()

            if len(value) == 10:
                is_date_only = True

            parsed_date = None

            for date_format in accepted_formats:

                try:
                    parsed_date = datetime.strptime(
                        value,
                        date_format
                    )
                    break

                except ValueError:
                    continue

            if parsed_date is None:
                raise SSIAPIError(
                    f"{field_name} không hợp lệ: {value}. "
                    "Định dạng hỗ trợ: YYYY/MM/DD hoặc "
                    "YYYY/MM/DD HH:mm:ss."
                )

        else:
            raise SSIAPIError(
                f"{field_name} phải là chuỗi ngày hoặc đối tượng date hợp lệ."
            )

        if is_date_only:

            if field_name == "from":
                parsed_date = parsed_date.replace(
                    hour=0,
                    minute=0,
                    second=0
                )

            elif field_name == "to":
                parsed_date = parsed_date.replace(
                    hour=23,
                    minute=59,
                    second=59
                )

        return parsed_date.strftime(
            "%Y/%m/%d %H:%M:%S"
        )

    # ========================================================
    # GỌI API
    # ========================================================

    def _request(
        self,
        method,
        endpoint,
        params=None
    ):

        self._ensure_token()

        url = self._url(endpoint)
        refreshed_token = False

        for attempt in range(3):

            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=45
                )

            except requests.RequestException as exc:

                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue

                raise SSIAPIError(
                    f"Lỗi kết nối SSI: {exc}"
                ) from exc

            # Token hết hạn hoặc không còn hợp lệ.
            if response.status_code == 401:

                if refreshed_token:
                    raise SSIAPIError(
                        "SSI tiếp tục trả lỗi 401 sau khi xác thực lại.",
                        status_code=401
                    )

                self.authenticate()
                refreshed_token = True
                continue

            # Rate limit.
            if response.status_code == 429:

                wait_time = 2 ** attempt

                print(
                    f"SSI rate limit. Chờ {wait_time} giây..."
                )

                time.sleep(wait_time)
                continue

            # Lỗi server.
            if response.status_code >= 500:

                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue

                raise SSIAPIError(
                    f"SSI server lỗi {response.status_code}: "
                    f"{response.text[:500]}\n"
                    f"URL thực tế: {response.url}",
                    status_code=response.status_code
                )

            if response.status_code != 200:
                raise SSIAPIError(
                    f"API lỗi {response.status_code}: "
                    f"{response.text[:500]}\n"
                    f"URL thực tế: {response.url}",
                    status_code=response.status_code
                )

            try:
                return response.json()

            except ValueError as exc:
                raise SSIAPIError(
                    "SSI trả về dữ liệu không phải JSON."
                ) from exc

        raise SSIAPIError(
            f"Không thể gọi SSI API sau 3 lần thử: {endpoint}"
        )

    # ========================================================
    # DANH SÁCH CHỨNG KHOÁN THEO SÀN
    # ========================================================

    def get_securities_by_board(self, board):

        result = self._request(
            "GET",
            "/api/v3/data/securitiesByBoard",
            params={
                "board": board
            }
        )

        if isinstance(result, list):
            return result

        if isinstance(result, dict):

            data = result.get("data", [])

            if isinstance(data, list):
                return data

        return []

    # ========================================================
    # LẤY OHLC THEO TRANG
    # ========================================================

    def get_ohlc_page(
        self,
        symbol,
        from_date,
        to_date,
        page_index=1,
        page_size=1000
    ):

        from_date = self._format_daily_date(
            from_date,
            "from"
        )

        to_date = self._format_daily_date(
            to_date,
            "to"
        )

        start = datetime.strptime(
            from_date,
            "%Y/%m/%d %H:%M:%S"
        )

        end = datetime.strptime(
            to_date,
            "%Y/%m/%d %H:%M:%S"
        )

        if start > end:
            raise SSIAPIError(
                "Ngày bắt đầu không được lớn hơn ngày kết thúc."
            )

        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "timeFrame": "1d",
            "pageIndex": page_index,
            "pageSize": page_size
        }

        result = self._request(
            "GET",
            "/api/v3/data/ohlc",
            params=params
        )

        if isinstance(result, list):
            return {
                "data": result,
                "pageCount": 1
            }

        if not isinstance(result, dict):
            return {
                "data": [],
                "pageCount": 0
            }

        return result

    # ========================================================
    # LẤY TOÀN BỘ OHLC
    # ========================================================

    def get_ohlc_all(
        self,
        symbol,
        from_date,
        to_date,
        page_size=1000,
        max_pages=100
    ):

        all_rows = []

        for page in range(1, max_pages + 1):

            result = self.get_ohlc_page(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
                page_index=page,
                page_size=page_size
            )

            rows = result.get("data", [])

            if not isinstance(rows, list) or not rows:
                break

            all_rows.extend(rows)

            page_count = result.get("pageCount")

            try:
                page_count = int(page_count)

            except (TypeError, ValueError):
                page_count = 0

            if page_count > 0 and page >= page_count:
                break

            if len(rows) < page_size:
                break

        return all_rows