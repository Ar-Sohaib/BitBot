from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.analytics.daily_report import build_daily_report, previous_day_in_tz
from src.broker.paper_broker import PaperBroker
from src.broker.risk import compute_drawdown, compute_equity
from src.config import load_settings
from src.notify.telegram import TelegramNotifier
from src.price_feed.rest_provider import BinanceRestProvider, filter_closed_candles
from src.storage.db import Database
from src.strategy.ma_cross import MovingAverageCrossStrategy


_log = logging.getLogger("main_live")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/app.log", encoding="utf-8"),
        ],
    )


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "storage" / "schema.sql"


def process_once(
    db: Database,
    broker: PaperBroker,
    strategy: MovingAverageCrossStrategy,
    notifier: TelegramNotifier,
    settings,
) -> int:
    provider = BinanceRestProvider()

    try:
        candles = provider.fetch_klines(settings.symbol, settings.timeframe, limit=max(120, settings.ma_slow + 20))
        notifier.notify_feed_recovered()
    except Exception as exc:
        _log.error("Feed error: %s", exc)
        notifier.notify_feed_down(str(exc))
        return 0

    closed = filter_closed_candles(candles)

    last_processed_raw = db.get_bot_state("last_processed_open_time")
    last_processed = int(last_processed_raw) if last_processed_raw else -1

    processed = 0
    for candle in closed:
        db.insert_candle(candle)
        if candle.open_time <= last_processed:
            continue

        # --- Position AVANT ---
        state_before = broker.get_state()

        closes = db.get_recent_closes(settings.symbol, settings.timeframe, settings.ma_slow + 2)
        signal = strategy.generate_signal(
            ts=candle.close_time,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            closes=closes,
            in_position=state_before.btc_qty > 0,
        )
        db.insert_signal(signal)

        result = broker.execute_signal(signal, candle)

        # --- Position APRÈS ---
        state_after = broker.get_state()

        # --- Logging structuré conforme spec §8 ---
        _log.info(
            "candle_close ts=%d close=%.2f signal=%s reason=%s "
            "before(cash=%.2f btc=%.8f) after(cash=%.2f btc=%.8f)",
            candle.close_time,
            candle.close,
            signal.signal,
            signal.reason,
            state_before.cash,
            state_before.btc_qty,
            state_after.cash,
            state_after.btc_qty,
        )

        if result.executed:
            _log.info(
                "trade_exec trade_id=%s side=%s price_market=%.2f price_exec=%.2f "
                "qty=%.8f fee=%.4f pnl_realized=%.4f",
                result.trade_id,
                result.side,
                result.price_market,
                result.price_exec,
                result.qty_btc,
                result.fee,
                result.pnl_realized,
            )
            notifier.notify_trade(
                result,
                market_price=candle.close,
                cash=state_after.cash,
                btc_qty=state_after.btc_qty,
                slippage_rate=settings.slippage_rate,
            )

        if state_after.is_blocked and not state_before.is_blocked:
            equity = compute_equity(state_after.cash, state_after.btc_qty, candle.close)
            dd = compute_drawdown(equity, state_after.peak_equity)
            notifier.notify_kill_switch(
                drawdown=dd,
                threshold=settings.kill_switch_drawdown_pct,
                equity=equity,
            )

        last_processed = candle.open_time
        processed += 1

    _maybe_send_daily_report(db, broker, notifier, settings, last_price=closed[-1].close if closed else 0.0)
    return processed


def _maybe_send_daily_report(
    db: Database,
    broker: PaperBroker,
    notifier: TelegramNotifier,
    settings,
    last_price: float,
) -> None:
    tz = ZoneInfo(settings.report_tz)
    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    current_local_day = now_utc.astimezone(tz).date().isoformat()

    last_marker = db.get_bot_state("last_report_marker")
    if last_marker is None:
        db.set_bot_state("last_report_marker", current_local_day)
        return

    if last_marker != current_local_day:
        # apply daily top-up for the new day (if enabled)
        added = broker.apply_daily_topup(int(now_utc.timestamp() * 1000), last_price)
        if added > 0:
            notifier.notify_alert(f"Applied daily top-up: {added:.2f}")

        report_day = previous_day_in_tz(now_utc, settings.report_tz)
        report = build_daily_report(
            db=db,
            day=report_day,
            tz_name=settings.report_tz,
            wallet=broker.get_state(),
            btc_price_end=last_price,
        )
        notifier.notify_daily_report(report)
        db.set_bot_state("last_report_marker", current_local_day)


def main() -> None:
    settings = load_settings()
    _configure_logging(settings.log_level)

    db = Database(settings.db_path)
    db.init_schema(_schema_path())

    strategy = MovingAverageCrossStrategy(fast_period=settings.ma_fast, slow_period=settings.ma_slow)
    broker = PaperBroker(settings=settings, db=db)
    notifier = TelegramNotifier(
        enabled=settings.telegram_enable,
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        tz_name=settings.report_tz,
    )

    _log.info("Live paper trading started for %s %s", settings.symbol, settings.timeframe)
    notifier.notify_bot_start(settings.symbol, settings.timeframe)

    try:
        while True:
            try:
                processed = process_once(db, broker, strategy, notifier, settings)
                _log.info("Loop done processed=%s", processed)
            except Exception as exc:
                _log.exception("Unhandled error in loop: %s", exc)
            time.sleep(settings.poll_seconds)
    except KeyboardInterrupt:
        _log.info("Stopped by user")
    finally:
        db.close()


if __name__ == "__main__":
    main()
    finally:
        db.close()


if __name__ == "__main__":
    main()
