# Từ điển dữ liệu

Tài liệu mô tả dữ liệu lưu trong `data/market_data.db` và các chỉ tiêu, điểm số do hệ thống tính ra.
Nguồn dữ liệu gốc: SSI FastConnect API. Công cụ phân tích học thuật, không phải khuyến nghị đầu tư.

## 1. Bảng SQLite

### 1.1. Bảng `prices` (khóa chính: `symbol`, `trading_date`)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `symbol` | TEXT | Mã chứng khoán (VNINDEX là chỉ số tham chiếu) |
| `trading_date` | TEXT | Ngày giao dịch, định dạng `YYYY-MM-DD`, theo lịch giao dịch Việt Nam |
| `open`, `high`, `low`, `close` | REAL | Giá mở cửa, cao nhất, thấp nhất, đóng cửa; đơn vị theo SSI trả về, chưa điều chỉnh |
| `volume` | REAL | Khối lượng giao dịch (cổ phiếu) |
| `value` | REAL | Giá trị giao dịch (đồng) do SSI cung cấp; có thể trống |
| `updated_at` | TEXT | Thời điểm ghi bản ghi, giờ UTC (mặc định của SQLite) |

Quy tắc khi ghi: bỏ dòng thiếu mã, thiếu ngày hoặc giá đóng cửa không dương; trùng (mã, ngày) thì ghi đè.

### 1.2. Bảng `securities` (khóa chính: `symbol`)

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `symbol` | TEXT | Mã cổ phiếu |
| `name` | TEXT | Tên doanh nghiệp |
| `board` | TEXT | Sàn: HOSE, HNX hoặc UPCOM |
| `icb_name` | TEXT | Ngành ICB, có thể trống |
| `stock_type` | TEXT | Loại chứng khoán do SSI trả về |
| `updated_at` | TEXT | Thời điểm cập nhật, giờ UTC |

### 1.3. Bảng `collection_log`

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | INTEGER | Khóa tự tăng |
| `symbol` | TEXT | Mã được thu thập |
| `status` | TEXT | `SUCCESS`, `EMPTY` (không có dữ liệu hợp lệ) hoặc `ERROR` |
| `message` | TEXT | Thông báo kèm theo |
| `rows_collected` | INTEGER | Số dòng giá ghi được |
| `created_at` | TEXT | Thời điểm ghi theo giờ máy người chạy |

Bảng này để trống trong dữ liệu đi kèm. `sqlite_sequence` là bảng nội bộ của SQLite.

## 2. Chỉ tiêu tính từ dữ liệu giá (`src/finance/metrics.py`)

Chỉ tính khi mã có ít nhất 127 phiên giá hợp lệ.

| Chỉ tiêu | Cách tính |
|---|---|
| `return_1m`, `return_3m`, `return_6m` | Lợi suất đơn P(t) / P(t-n) - 1 với n = 21, 63, 126 phiên |
| `annualized_return_6m` | (1 + return_6m)^2 - 1 |
| `volatility` | Độ lệch chuẩn lợi suất log 126 phiên gần nhất, nhân √252 |
| `reward_volatility` | annualized_return_6m chia volatility (không phải Sharpe Ratio) |
| `downside_deviation` | Độ lệch chuẩn bán phần của lợi suất log với MAR = 0, năm hóa (nhân √252) |
| `max_drawdown` | Mức sụt giảm tối đa từ đỉnh lũy kế trên 127 phiên cuối, số dương (0,25 là giảm 25%) |
| `adtv` | Giá trị giao dịch bình quân ngày (đồng) trên 126 phiên cuối, gồm cả phiên bằng 0 |
| `amihud` | Trung bình |lợi suất log| / giá trị giao dịch (đồng); chỉ tính phiên có giá trị giao dịch lớn hơn 0 |
| `zero_volume_ratio` | Tỷ lệ phiên có khối lượng bằng 0 trong 126 phiên cuối |
| `excess_3m`, `excess_6m` | Lợi suất mã trừ lợi suất VNINDEX, tính trên các ngày giao dịch chung |
| `beta` | Cov(mã, VNINDEX) / Var(VNINDEX) trên tối đa 126 quan sát chung; chỉ để tham khảo, không vào điểm |
| `value_is_estimated` | Có ít nhất một phiên phải ước tính giá trị giao dịch bằng giá đóng cửa × khối lượng |

## 3. Điểm và kết quả xếp hạng (`src/analytics/ranking.py`)

Điểm thành phần `s_*` là điểm phân vị trong tập cổ phiếu được xếp hạng; chỉ tiêu rủi ro và kém
thanh khoản được đảo chiều (giá trị thấp hơn thì điểm cao hơn). Điểm thấp nhất là 1/n nhân 100,
không phải đúng 0.

| Cột | Ý nghĩa |
|---|---|
| `s_1m`, `s_3m`, `s_6m` | Điểm phân vị của lợi suất 1, 3, 6 tháng |
| `s_reward_volatility`, `s_volatility` | Điểm của reward_volatility; điểm đảo chiều của volatility |
| `s_max_drawdown`, `s_downside_deviation` | Điểm đảo chiều của max_drawdown và downside_deviation |
| `s_adtv`, `s_amihud` | Điểm của adtv; điểm đảo chiều của amihud |
| `s_excess_3m`, `s_excess_6m` | Điểm của excess_3m và excess_6m |
| `score_momentum` | 0,20 × s_1m + 0,30 × s_3m + 0,50 × s_6m |
| `score_risk_adjusted` | 0,70 × s_reward_volatility + 0,30 × s_volatility |
| `score_downside` | 0,50 × s_max_drawdown + 0,50 × s_downside_deviation |
| `score_liquidity` | 0,60 × s_adtv + 0,40 × s_amihud |
| `score_relative` | 0,70 × s_excess_3m + 0,30 × s_excess_6m |
| `eligible` | Đúng khi cả 5 điểm nhân tố đều có giá trị; mã không đủ điều kiện không có điểm tổng hợp |
| `total_score` | 0,25 momentum + 0,25 risk_adjusted + 0,20 downside + 0,15 liquidity + 0,15 relative |
| `rating` | Cao (từ 80), Khá cao (từ 65), Trung bình (từ 50), Thấp (dưới 50), Chưa đủ dữ liệu |
| `rank` | Thứ hạng theo total_score giảm dần (cùng điểm thì cùng hạng) |

Một nhân tố chỉ có điểm khi mọi chỉ tiêu thành phần của nó đều có dữ liệu. Dữ liệu thiếu không bị
thay bằng 0.