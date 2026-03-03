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
from src.notify.dispatcher import TelegramDispatcher
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
    dispatcher: TelegramDispatcher,
    settings,
) -> int:
    provider = BinanceRestProvider()

    try:
        candles = provider.fetch_klines(settings.symbol, settings.timeframe, limit=max(120, settings.ma_slow + 20))
        
        # Check if feed was down and is now recovered
        if dispatcher.should_send_feed_ok():
            downtime = dispatcher.get_feed_downtime_seconds()
            text = notifier.format_feed_ok("Binance REST", downtime)
            notifier.send_message(text)
            dispatcher.mark_feed_ok()
            
    except Exception as exc:
        _log.error("Feed error: %s", exc)
        
        # Check if we should send feed down alert
        if dispatcher.should_send_feed_down():
            text = notifier.format_feed_down("Binance REST", str(exc), 1, 1.5, False)
            notifier.send_message(text)
            dispatcher.mark_feed_down()
        
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
            # Check if we should send trade notification
            if dispatcher.should_send_trade(result.trade_id):
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
                dispatcher.mark_trade_sent(result.trade_id)

        if state_after.is_blocked and not state_before.is_blocked:
            equity = compute_equity(state_after.cash, state_after.btc_qty, candle.close)
            dd = compute_drawdown(equity, state_after.peak_equity)
            text = notifier.format_kill_switch(
                drawdown=dd,
                threshold=settings.kill_switch_drawdown_pct,
                equity=equity,
                position_btc=state_after.btc_qty,
            )
            notifier.send_message(text)

        last_processed = candle.open_time
        processed += 1

    _maybe_send_daily_report(db, broker, notifier, dispatcher, settings, last_price=closed[-1].close if closed else 0.0)
    return processed


def _maybe_send_daily_report(
    db: Database,
    broker: PaperBroker,
    notifier: TelegramNotifier,
    dispatcher: TelegramDispatcher,
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
        # Check if we should send daily report (rate limit 1/day)
        if dispatcher.should_send_daily_report(current_local_day):
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
            dispatcher.mark_daily_report_sent(current_local_day)
        
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
    dispatcher = TelegramDispatcher(db=db, tz_name=settings.report_tz)

    _log.info("Live paper trading started for %s %s", settings.symbol, settings.timeframe)
    
    # Check if we should send startup notification
    if dispatcher.should_send_startup():
        text = notifier.format_startup(settings.symbol, settings.timeframe, "Binance REST")
        notifier.send_message(text)
        dispatcher.mark_startup_sent()

    try:
        while True:
            try:
                processed = process_once(db, broker, strategy, notifier, dispatcher, settings)
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
