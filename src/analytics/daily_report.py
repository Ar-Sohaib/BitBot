from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.analytics.metrics import max_drawdown_from_equity, winrate_from_trades
from src.models import DailyReport, WalletState
from src.storage.db import Database



def day_bounds_epoch_ms(day: date, tz_name: str) -> tuple[int, int]:
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day, time.max, tzinfo=tz)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)



def build_daily_report(
    db: Database,
    day: date,
    tz_name: str,
    wallet: WalletState,
    btc_price_end: float,
    notes: str = "feed ok, no errors",
) -> DailyReport:
    start_ms, end_ms = day_bounds_epoch_ms(day, tz_name)

    equity_rows = db.get_equity_between(start_ms, end_ms)
    trades_rows = db.get_trades_between(start_ms, end_ms)

    if equity_rows:
        equity_start = float(equity_rows[0]["equity"])
        equity_end = float(equity_rows[-1]["equity"])
        max_dd = max_drawdown_from_equity(float(r["drawdown"]) for r in equity_rows)
    else:
        equity_start = wallet.cash + wallet.btc_qty * btc_price_end
        equity_end = equity_start
        max_dd = 0.0

    pnl_abs = equity_end - equity_start
    pnl_pct = 0.0 if equity_start == 0 else pnl_abs / equity_start

    buys = [r for r in trades_rows if str(r["side"]) == "BUY"]
    sells = [r for r in trades_rows if str(r["side"]) == "SELL"]
    fees_total = sum(float(r["fee"]) for r in trades_rows)
    sell_pnls = [float(r["pnl_realized"]) for r in sells]

    equity_now = wallet.cash + wallet.btc_qty * btc_price_end
    exposure = 0.0 if equity_now <= 0 else (wallet.btc_qty * btc_price_end) / equity_now

    return DailyReport(
        day=day.isoformat(),
        equity_start=equity_start,
        equity_end=equity_end,
        pnl_abs=pnl_abs,
        pnl_pct=pnl_pct,
        trades_count=len(trades_rows),
        buy_count=len(buys),
        sell_count=len(sells),
        winrate=winrate_from_trades(sell_pnls),
        fees_total=fees_total,
        max_drawdown=max_dd,
        cash_end=wallet.cash,
        btc_qty_end=wallet.btc_qty,
        btc_price_end=btc_price_end,
        exposure_pct=exposure,
        notes=notes,
    )



def render_daily_report_text(report: DailyReport) -> str:
    return (
        f"[DAILY REPORT][PAPER][BTC] {report.day}\n"
        f"Equity: {report.equity_start:.1f} → {report.equity_end:.1f}  "
        f"(PnL {report.pnl_abs:+.1f} / {report.pnl_pct:+.2%})\n"
        f"Trades: {report.trades_count} (BUY {report.buy_count} / SELL {report.sell_count})\n"
        f"Winrate: {report.winrate:.0%}\n"
        f"Fees: {report.fees_total:.1f} USDT\n"
        f"Max DD: {report.max_drawdown:.1%}\n"
        f"End wallet: cash={report.cash_end:.1f} | btc={report.btc_qty_end:.4f} "
        f"| BTC={report.btc_price_end:.1f} | exposure={report.exposure_pct:.0%}\n"
        f"Notes: {report.notes}"
    )



def previous_day_in_tz(now_utc: datetime, tz_name: str) -> date:
    local_now = now_utc.astimezone(ZoneInfo(tz_name))
    return (local_now - timedelta(days=1)).date()
