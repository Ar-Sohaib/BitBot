from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SignalType = Literal["BUY", "SELL", "HOLD"]
Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


@dataclass(frozen=True)
class Signal:
    ts: int
    symbol: str
    timeframe: str
    signal: SignalType
    reason: str
    features_json: str = ""


@dataclass
class WalletState:
    cash: float
    btc_qty: float
    avg_entry_price: float
    fees_paid_total: float
    is_blocked: bool
    peak_equity: float


@dataclass(frozen=True)
class TradeResult:
    executed: bool
    side: Side | None
    reason: str
    trade_id: str | None = None
    qty_btc: float = 0.0
    price_market: float = 0.0
    price_exec: float = 0.0
    fee: float = 0.0
    pnl_realized: float = 0.0


@dataclass(frozen=True)
class DailyReport:
    day: str
    equity_start: float
    equity_end: float
    pnl_abs: float
    pnl_pct: float
    trades_count: int
    buy_count: int
    sell_count: int
    winrate: float
    fees_total: float
    max_drawdown: float
    cash_end: float
    btc_qty_end: float
    btc_price_end: float
    exposure_pct: float
    notes: str = "feed ok, no errors"
