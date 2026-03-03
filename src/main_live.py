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
                # Mark notification as sent in the database
                db.mark_trade_notification_sent(result.trade_id, int(time.time() * 1000))
            else:
                # Already sent via dispatcher, just mark in DB if not already
                db.mark_trade_notification_sent(result.trade_id, int(time.time() * 1000))

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


def _timeframe_to_ms(timeframe: str) -> int:
    """Convert timeframe string to milliseconds."""
    unit = timeframe[-1].lower()
    amount = int(timeframe[:-1])
    
    if unit == "m":
        return amount * 60 * 1000
    elif unit == "h":
        return amount * 3600 * 1000
    elif unit == "d":
        return amount * 86400 * 1000
    elif unit == "w":
        return amount * 7 * 86400 * 1000
    else:
        raise ValueError(f"Unsupported timeframe: {timeframe}")


def recover_missing_candles(
    db: Database,
    broker: PaperBroker,
    strategy: MovingAverageCrossStrategy,
    notifier: TelegramNotifier,
    dispatcher: TelegramDispatcher,
    settings,
) -> int:
    """Recover missing candles since last processed time.
    
    This function fetches all missing candles since last_processed_open_time
    and processes them chronologically to fill the gap.
    
    Returns:
        Number of candles recovered and processed
    """
    provider = BinanceRestProvider()
    
    last_processed_raw = db.get_bot_state("last_processed_open_time")
    if not last_processed_raw:
        _log.info("No last_processed_open_time found, skipping recovery")
        return 0
    
    last_processed = int(last_processed_raw)
    timeframe_ms = _timeframe_to_ms(settings.timeframe)
    
    # Start from the next candle after last processed
    start_time = last_processed + timeframe_ms
    now_ms = int(time.time() * 1000)
    
    # Calculate expected candles to recover
    expected_count = (now_ms - start_time) // timeframe_ms
    
    if expected_count <= 0:
        _log.info("No missing candles to recover")
        return 0
    
    _log.info(
        "Starting recovery: last_processed=%d start_time=%d now=%d expected_candles=%d",
        last_processed, start_time, now_ms, expected_count
    )
    
    recovered_count = 0
    batch_size = 1000  # Max Binance allows
    current_start = start_time
    
    while current_start < now_ms:
        try:
            # Fetch batch of candles
            candles = provider.fetch_klines(
                settings.symbol,
                settings.timeframe,
                limit=batch_size,
                start_time=current_start
            )
            
            if not candles:
                break
            
            # Filter to only closed candles
            closed = filter_closed_candles(candles)
            
            if not closed:
                break
            
            # Process each candle
            for candle in closed:
                # Skip if already processed (safety check)
                if candle.open_time <= last_processed:
                    continue
                
                # Insert candle
                db.insert_candle(candle)
                
                # Get position before
                state_before = broker.get_state()
                
                # Generate signal
                closes = db.get_recent_closes(settings.symbol, settings.timeframe, settings.ma_slow + 2)
                signal = strategy.generate_signal(
                    ts=candle.close_time,
                    symbol=settings.symbol,
                    timeframe=settings.timeframe,
                    closes=closes,
                    in_position=state_before.btc_qty > 0,
                )
                db.insert_signal(signal)
                
                # Execute signal
                result = broker.execute_signal(signal, candle)
                
                # Get position after
                state_after = broker.get_state()
                
                # Log recovery progress
                _log.info(
                    "recovery_candle ts=%d close=%.2f signal=%s executed=%s",
                    candle.close_time,
                    candle.close,
                    signal.signal,
                    result.executed
                )
                
                # Note: Don't send notifications during recovery
                # They will be sent by send_pending_notifications() later
                
                last_processed = candle.open_time
                recovered_count += 1
            
            # Move to next batch
            if len(closed) < batch_size:
                break
            
            current_start = closed[-1].open_time + timeframe_ms
            
        except Exception as exc:
            _log.error("Error during recovery: %s", exc)
            break
    
    _log.info(
        "Recovery complete: recovered=%d candles from last_processed=%d to now=%d",
        recovered_count, int(last_processed_raw), now_ms
    )
    
    return recovered_count


def send_pending_notifications(
    db: Database,
    notifier: TelegramNotifier,
    dispatcher: TelegramDispatcher,
    settings,
) -> int:
    """Send any pending trade notifications that weren't sent due to crashes.
    
    Returns:
        Number of notifications sent
    """
    unsent = db.get_unsent_trade_notifications()
    
    if not unsent:
        return 0
    
    _log.info("Found %d unsent trade notifications, sending now", len(unsent))
    
    sent_count = 0
    for trade in unsent:
        try:
            # Convert Row to dict for easier access
            if not isinstance(trade, dict):
                trade = dict(trade)
            
            # Check if already sent via dispatcher (legacy check)
            if dispatcher.should_send_trade(trade["trade_id"]):
                # Send notification
                from src.models import TradeResult
                
                result = TradeResult(
                    executed=True,
                    trade_id=trade["trade_id"],
                    side=trade["side"],
                    qty_btc=float(trade["qty_btc"]),
                    price_market=float(trade["price_market"]),
                    price_exec=float(trade["price_exec"]),
                    fee=float(trade["fee"]),
                    pnl_realized=float(trade["pnl_realized"]),
                    reason=trade.get("reason", ""),
                )
                
                notifier.notify_trade(
                    result,
                    market_price=float(trade["price_market"]),
                    cash=float(trade["cash_after"]),
                    btc_qty=float(trade["btc_after"]),
                    slippage_rate=settings.slippage_rate,
                )
                
                dispatcher.mark_trade_sent(trade["trade_id"])
            
            # Mark as sent in database
            db.mark_trade_notification_sent(trade["trade_id"], int(time.time() * 1000))
            sent_count += 1
            
            _log.info("Sent pending notification for trade_id=%s", trade["trade_id"])
            
        except Exception as exc:
            _log.error("Failed to send pending notification for trade %s: %s", trade.get("trade_id", "unknown"), exc)
    
    return sent_count
    
    return sent_count


def purge_old_notifications(db: Database) -> int:
    """Purge notification records older than 30 days.
    
    Returns:
        Number of records deleted
    """
    # 30 days in milliseconds
    cutoff_ts = int((time.time() - 30 * 86400) * 1000)
    deleted = db.purge_old_sent_notifications(cutoff_ts)
    
    if deleted > 0:
        _log.info("Purged %d old notification records (older than 30 days)", deleted)
    
    return deleted


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
    
    # Run migrations
    migration_dir = Path(__file__).resolve().parent.parent / "migrations"
    if migration_dir.exists():
        for migration_file in sorted(migration_dir.glob("*.sql")):
            _log.info("Running migration: %s", migration_file.name)
            try:
                db.run_migration(migration_file)
            except Exception as exc:
                _log.warning("Migration %s failed or already applied: %s", migration_file.name, exc)

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
    
    # Purge old notification records (older than 30 days)
    purge_old_notifications(db)
    
    # Send any pending notifications from previous crashes
    sent = send_pending_notifications(db, notifier, dispatcher, settings)
    if sent > 0:
        _log.info("Sent %d pending notifications from previous session", sent)
    
    # Recover missing candles if there's a gap
    recovered = recover_missing_candles(db, broker, strategy, notifier, dispatcher, settings)
    if recovered > 0:
        _log.info("Recovered %d missing candles", recovered)
    
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
