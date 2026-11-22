"""Hàm dựng dữ liệu giả lập dùng chung cho các file test (dữ liệu tổng hợp, không phải dữ liệu thật)."""

import numpy as np
import pandas as pd


def make_price_frame(symbol, n=150, seed=0, drift=0.0005, vol=0.02,
                     start="2025-01-02", with_value=True):
    """Chuỗi giá bước ngẫu nhiên có seed cố định, kèm khối lượng và giá trị giao dịch."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    volume = rng.integers(100_000, 1_000_000, n).astype(float)
    frame = pd.DataFrame({
        "symbol": symbol,
        "trading_date": pd.bdate_range(start, periods=n),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
        "value": close * volume if with_value else np.nan,
    })
    return frame


def make_market_and_stocks(symbols, n=150):
    """VNINDEX và danh sách cổ phiếu (mỗi mã một seed khác nhau)."""
    frames = [make_price_frame("VNINDEX", n=n, seed=999, drift=0.0003, vol=0.01)]
    for index, symbol in enumerate(symbols):
        frames.append(make_price_frame(symbol, n=n, seed=index + 1,
                                       drift=0.0002 * (index % 5), vol=0.015 + 0.002 * (index % 4)))
    prices = pd.concat(frames, ignore_index=True)
    securities = pd.DataFrame({
        "symbol": symbols,
        "name": [f"Công ty {s}" for s in symbols],
        "board": "HOSE",
        "icb_name": "Ngành thử",
    })
    return prices, securities
