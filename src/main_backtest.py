from __future__ import annotations

import logging
from pathlib import Path

from src.broker.paper_broker import PaperBroker
from src.config import load_settings
from src.models import Signal
from src.storage.db import Database
from src.strategy.ma_cross import MovingAverageCrossStrategy
from zoneinfo import ZoneInfo
from datetime import datetime



def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )



def main() -> None:
    settings = load_settings()
    _configure_logging(settings.log_level)

    db = Database()
    db.init_schema(Path("src/storage/schema.sql"))

    strategy = MovingAverageCrossStrategy(fast_period=settings.ma_fast, slow_period=settings.ma_slow)
    broker = PaperBroker(settings=settings, db=db)

    candles = db.get_candles_between(settings.symbol, settings.timeframe, 0, 9999999999999)
    if not candles:
        logging.getLogger("main_backtest").warning("No candles in DB for %s %s", settings.symbol, settings.timeframe)
        db.close()
        return

    closes: list[float] = []
    last_local_day: str | None = None
    tz = ZoneInfo(settings.report_tz)
    for candle in candles:
        # detect day boundary in report tz and apply daily top-up once per day
        local_day = datetime.fromtimestamp(candle.close_time / 1000, tz=ZoneInfo("UTC")).astimezone(tz).date().isoformat()
        if last_local_day != local_day:
            # apply top-up at start of this local day
            added = broker.apply_daily_topup(candle.close_time, candle.close)
            if added > 0:
                logging.getLogger("main_backtest").info("Applied daily top-up=%.2f at day=%s", added, local_day)
            last_local_day = local_day
        closes.append(candle.close)
        signal: Signal = strategy.generate_signal(
            ts=candle.close_time,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            closes=closes,
            in_position=broker.get_state().btc_qty > 0,
        )
        db.insert_signal(signal)
        broker.execute_signal(signal, candle)

    state = broker.get_state()
    logging.getLogger("main_backtest").info(
        "Backtest done. cash=%.2f btc=%.8f avg_entry=%.2f fees_total=%.4f blocked=%s",
        state.cash,
        state.btc_qty,
        state.avg_entry_price,
        state.fees_paid_total,
        state.is_blocked,
    )
    db.close()


if __name__ == "__main__":
    main()
