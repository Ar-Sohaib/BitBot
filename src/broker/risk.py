from __future__ import annotations


def compute_equity(cash: float, btc_qty: float, btc_price: float) -> float:
    return cash + btc_qty * btc_price


def compute_drawdown(equity: float, peak_equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    dd = (peak_equity - equity) / peak_equity
    return max(0.0, dd)
