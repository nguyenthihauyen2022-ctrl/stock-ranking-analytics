# Hệ thống phân tích và xếp hạng cổ phiếu Việt Nam

Đồ án cá nhân cuối kỳ, học phần **Gói phần mềm ứng dụng cho tài chính 1**.

> **Lưu ý:** Đây là công cụ phân tích học thuật, **không phải khuyến nghị đầu tư**.
> Điểm số chỉ là thứ hạng tương đối giữa các cổ phiếu trong tập được phân tích,
> không phải xác suất tăng giá hay lợi nhuận kỳ vọng.

## 1. Mục tiêu và người dùng

Sản phẩm sàng lọc và xếp hạng cổ phiếu trên HOSE, HNX và UPCoM bằng mô hình đa tiêu chí gồm
năm nhóm nhân tố: động lượng giá, hiệu suất trên rủi ro, rủi ro giảm giá, thanh khoản và hiệu
suất tương đối so với VNINDEX. Người dùng mục tiêu là nhà đầu tư cá nhân và chuyên viên phân
tích cần một bước sàng lọc định lượng dựa trên dữ liệu giá và giao dịch.

## 2. Nguồn dữ liệu

- Dữ liệu lấy từ **SSI FastConnect API**.
- Endpoint sử dụng: danh sách chứng khoán theo sàn (`securitiesByBoard`) và dữ liệu OHLC ngày (`ohlc`).
- Các trường lấy về: giá mở cửa, cao nhất, thấp nhất, đóng cửa, khối lượng và giá trị giao dịch.
- Dữ liệu là dữ liệu thật thu thập từ SSI, không có dữ liệu giả hay dữ liệu mô phỏng trong
  bộ dữ liệu đi kèm. Riêng các bài kiểm thử tự động dùng dữ liệu giả lập, xem mục 8.
- Sản phẩm **không** dùng dữ liệu tài khoản cá nhân và **không** gửi lệnh giao dịch.

## 3. Dữ liệu đi kèm

`data/market_data.db` là dữ liệu thu thập từ SSI, gồm toàn bộ 1.556 mã trong danh sách chứng
khoán của HOSE, HNX và UPCoM tại thời điểm thu thập, kèm chỉ số VNINDEX. Dữ liệu giá giữ lại
300 phiên giao dịch gần nhất (từ 10/09/2025 đến 20/11/2026). Dữ liệu này cho phép chạy
dashboard mà không cần API key.

- 1.466 mã có dữ liệu giá; trong đó 954 mã đủ điều kiện xếp hạng (có ít nhất 127 phiên hợp lệ
  và đủ dữ liệu cho cả 5 nhóm nhân tố). Các mã còn lại được đánh dấu không đủ điều kiện.
- Lần mở dashboard đầu tiên mất khoảng 30 giây để tính xếp hạng toàn thị trường.
- Kết quả và ảnh chụp trong báo cáo được tính trên bộ dữ liệu này.

## 4. Cài đặt

Yêu cầu: Python (đã kiểm tra trên Python 3.13).

Windows (PowerShell):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Cấu hình

Sao chép `.env.example` thành `.env` rồi điền giá trị. **Không đưa `.env` lên kho mã nguồn.**
Chỉ cần cấu hình khi muốn thu thập dữ liệu mới; xem dashboard với dữ liệu đi kèm thì không cần.

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `SSI_API_KEY`, `SSI_API_SECRET` | Khóa SSI API của bạn (bắt buộc khi chạy collector) | không có |
| `SSI_BASE_URL` | Địa chỉ SSI API | `https://api.ssi.com.vn` |
| `BOARDS` | Các sàn cần thu thập | `HOSE,HNX,UPCOM` |
| `MAX_SYMBOLS` | Giới hạn số mã khi thử nghiệm (0 là không giới hạn) | `0` |
| `LOOKBACK_DAYS` | Số ngày lịch lấy lùi cho mã mới | `450` |
| `PAGE_SIZE`, `MAX_PAGES` | Phân trang khi gọi OHLC | `1000`, `100` |
| `REQUEST_DELAY` | Giây nghỉ giữa các yêu cầu, để không gọi dày đặc | `0.15` |
| `OVERLAP_DAYS` | Số ngày lấy chồng khi cập nhật thêm, để vá dữ liệu bị sửa | `7` |
| `SUPPLEMENTAL_SYMBOLS` | Mã bổ sung ngoài danh sách SSI trả về | `HPG` |

## 6. Chạy dashboard

Chạy từ **thư mục gốc dự án** (vì cơ sở dữ liệu được mở bằng đường dẫn tương đối
`data/market_data.db`):

```
streamlit run src/app/dashboard.py
```

Không cần API key để xem dashboard với dữ liệu đi kèm. Lần mở đầu tiên dashboard tính xếp hạng
toàn thị trường nên mất khoảng 30 giây; các lần chuyển trang sau đó diễn ra ngay.

## 7. Thu thập dữ liệu mới (tùy chọn)

Cần SSI API key riêng đã điền trong `.env`. Chạy từ thư mục gốc dự án:

```
python -m src.data.collector
```

Lưu ý:
- Collector lấy toàn bộ thị trường (khoảng 1.500 mã) nên lần đầu mất vài phút.
- Mỗi API key chỉ giữ một phiên đăng nhập, không chạy hai nơi cùng lúc bằng một key.
- Dashboard chỉ đọc dữ liệu đã lưu, không tự gọi API. Sau khi chạy collector cần khởi động lại
  dashboard để thấy dữ liệu mới.

## 8. Kiểm thử

```
python -m pytest
```

Bộ kiểm thử gồm 191 test, phủ: công thức chỉ tiêu tài chính, quy tắc xếp hạng và điều kiện đủ
dữ liệu, phân tích độ nhạy trọng số, tầng SQLite, chuẩn hóa dữ liệu SSI và xử lý lỗi kết nối
(401, 429, lỗi máy chủ, JSON hỏng).

Lưu ý: dữ liệu trong các test là dữ liệu giả lập, chỉ dùng để kiểm tra logic tính toán, không
phải dữ liệu thị trường. Test dùng cơ sở dữ liệu tạm và phản hồi giả lập nên không cần mạng,
không cần API key và không ghi vào `data/market_data.db`. Kết quả xếp hạng trên dashboard được
tính từ dữ liệu thật thu thập từ SSI.

## 9. Cấu trúc thư mục

```
src/ssi_api/    kết nối SSI API (xác thực, gọi OHLC, danh sách mã)
src/data/       thu thập dữ liệu và lưu SQLite
src/finance/    tính các chỉ tiêu tài chính
src/analytics/  chấm điểm, xếp hạng và phân tích độ nhạy
src/app/        dashboard Streamlit
tests/          kiểm thử tự động (công thức, xếp hạng, SQLite, collector, client)
docs/           tài liệu bổ sung (từ điển dữ liệu đầy đủ)
data/           cơ sở dữ liệu SQLite
```

## 10. Luồng xử lý dữ liệu

```
SSI API -> collector (lấy, chuẩn hóa, loại trùng) -> SQLite (securities, prices)
        -> finance/metrics (tính chỉ tiêu) -> analytics/ranking (chuẩn hóa phân vị, chấm điểm)
        -> dashboard Streamlit
```

Quy tắc xử lý dữ liệu:
- Gọi API có thử lại khi lỗi kết nối hoặc lỗi máy chủ, chờ khi bị giới hạn tần suất (429),
  tự đăng nhập lại khi token hết hạn.
- Dữ liệu trùng (cùng mã, cùng ngày) được ghi đè theo khóa chính; dòng thiếu giá đóng cửa hoặc
  giá không dương bị loại.
- Dữ liệu thiếu **không** được thay bằng 0. Mã thiếu dữ liệu hoặc dưới 127 phiên được đánh dấu
  không đủ điều kiện, không bị xếp cuối bảng.
- Giá trị giao dịch ưu tiên lấy từ trường `value` của SSI. Nếu thiếu hoặc không hợp lệ, hệ thống
  ước tính bằng giá đóng cửa × khối lượng và đánh dấu `value_is_estimated`; giá trị này không hoàn
  toàn bằng giá trị giao dịch thực tế. Phiên có giá trị giao dịch bằng 0 vẫn được tính trong ADTV
  nhưng không đưa vào phép chia của chỉ số Amihud.
- Nhật ký thu thập được ghi ở bảng `collection_log` và ở màn hình khi chạy collector.

## 11. Từ điển dữ liệu (SQLite: `data/market_data.db`)

**Bảng `prices`** (khóa chính: `symbol`, `trading_date`)

| Cột | Ý nghĩa |
|---|---|
| `symbol` | Mã chứng khoán (VNINDEX là chỉ số tham chiếu) |
| `trading_date` | Ngày giao dịch (`YYYY-MM-DD`, theo lịch giao dịch Việt Nam) |
| `open`, `high`, `low`, `close` | Giá mở, cao, thấp, đóng, theo đơn vị SSI trả về, chưa điều chỉnh |
| `volume` | Khối lượng giao dịch (cổ phiếu) |
| `value` | Giá trị giao dịch (đồng) do SSI cung cấp |
| `updated_at` | Thời điểm ghi bản ghi (UTC) |

**Bảng `securities`**: `symbol`, `name`, `board` (HOSE/HNX/UPCOM), `icb_name` (ngành, có thể
trống), `stock_type`, `updated_at`.

**Bảng `collection_log`**: nhật ký thu thập (để trống trong dữ liệu đi kèm).

Cơ sở dữ liệu dùng chế độ WAL của SQLite, nên khi mở sẽ sinh thêm hai file tạm
`market_data.db-wal` và `market_data.db-shm` (đã được `.gitignore` loại). Mỗi lần khởi tạo,
chương trình cũng kiểm tra và tạo bảng nếu thiếu.

Từ điển đầy đủ gồm cả các chỉ tiêu và điểm số xem tại `docs/data_dictionary.md`.

## 12. Mô hình xếp hạng

Điểm tổng hợp 0-100, chuẩn hóa theo phân vị trong tập cổ phiếu được xếp hạng:

| Nhân tố | Trọng số | Chỉ tiêu bên trong |
|---|---|---|
| Động lượng giá | 25% | Lợi suất 1 tháng, 3 tháng, 6 tháng (20/30/50) |
| Hiệu suất trên rủi ro | 25% | Lợi suất năm hóa 6 tháng chia độ biến động năm (70), độ biến động đảo chiều (30) |
| Rủi ro giảm giá | 20% | Mức sụt giảm tối đa (50), độ lệch chuẩn bán phần (50) |
| Thanh khoản | 15% | Giá trị giao dịch bình quân ngày (60), chỉ số Amihud đảo chiều (40) |
| Hiệu suất tương đối | 15% | Lợi suất vượt trội so với VNINDEX 3 tháng, 6 tháng (70/30) |

Ghi chú công thức: lợi suất 1/3/6 tháng là lợi suất đơn. Độ biến động và độ lệch chuẩn bán phần
(MAR = 0) tính trên lợi suất log của 126 phiên gần nhất và được năm hóa (nhân √252). Chỉ số
Amihud dùng trị tuyệt đối lợi suất log chia giá trị giao dịch. Mức sụt giảm tối đa là số dương
(ví dụ 0,25 là giảm 25% từ đỉnh) và được đảo chiều khi chấm điểm.

Cổ phiếu có dưới 127 phiên hợp lệ hoặc thiếu dữ liệu cần thiết không được xếp hạng.
Hệ số Beta và Sharpe Ratio không nằm trong điểm tổng hợp. Chi tiết công thức xem trong báo cáo.

## 13. Giới hạn đã biết

- Mô hình chỉ dùng dữ liệu giá và giao dịch; không đánh giá cơ bản doanh nghiệp (ROE, EPS, P/E...).
- Giá chưa được điều chỉnh cho sự kiện doanh nghiệp (chia tách, thưởng cổ phiếu).
- Trọng số là cấu hình thiết kế ban đầu, chưa được tối ưu; hệ thống có phân tích độ nhạy trọng số.
- Chưa có kiểm định ngoài mẫu theo từng kỳ.
- Điểm xếp hạng chỉ có ý nghĩa tương đối trong tập cổ phiếu được phân tích.
- Phân tích ngành phụ thuộc vào dữ liệu ngành SSI trả về; một số mã có thể thiếu ngành.
- Chỉ tiêu thanh khoản có thể dùng giá trị giao dịch ước tính (giá đóng cửa × khối lượng) khi SSI
  không cung cấp `value`.
- Chưa áp dụng Winsorization cho giá trị cực đoan. Điểm percentile ít bị ảnh hưởng bởi giá trị
  cực đoan nhưng không loại bỏ hoàn toàn.
- Lợi suất vượt trội so với VNINDEX tính trên các ngày giao dịch chung với chỉ số, nên có thể
  lệch nhẹ so với lợi suất 3 tháng, 6 tháng của riêng mã khi mã có phiên không giao dịch.
- Khi cập nhật danh sách chứng khoán, mã không còn nằm trong danh sách hiện tại của SSI (ví dụ
  đã hủy niêm yết) bị xóa khỏi bảng `securities` nên không còn được đưa vào phân tích. Kết quả
  vì vậy có thể chịu sai lệch sống sót (survivorship bias).
- Múi giờ: `trading_date` theo ngày giao dịch Việt Nam, còn `updated_at` dùng giờ UTC mặc định
  của SQLite và nhật ký thu thập dùng giờ máy của người chạy, nên các mốc thời gian ghi nhận
  chưa thống nhất theo UTC+7.
- Chưa kiểm thử giao diện dashboard và chưa kiểm thử gọi SSI thật; các test dùng dữ liệu giả
  lập (xem mục 8).
- Hàm lưu dữ liệu vào SQLite chưa xử lý dòng có mã chứng khoán trống. Trường hợp này được loại
  ở bước chuẩn hóa của collector nên không xảy ra trong luồng xử lý thực tế.