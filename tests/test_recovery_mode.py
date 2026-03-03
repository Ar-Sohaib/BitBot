"""
Tests for resume mode / recovery functionality.

Tests cover:
1. Restart idempotence - no double trades
2. Crash-safe notifications - notifications sent after restart
3. Complete candle catch-up - all missing candles processed
4. Notification purge - old records removed
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.broker.paper_broker import PaperBroker
from src.config import Settings
from src.main_live import (
    _timeframe_to_ms,
    purge_old_notifications,
    recover_missing_candles,
    send_pending_notifications,
)
from src.models import Candle, Signal
from src.notify.dispatcher import TelegramDispatcher
from src.notify.telegram import TelegramNotifier
from src.storage.db import Database
from src.strategy.ma_cross import MovingAverageCrossStrategy


class RecoveryModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "test.db"
        self.settings = Settings(
            app_env="test",
            log_level="INFO",
            symbol="BTCUSDT",
            timeframe="1m",
            starting_cash=10000,
            fee_rate=0.001,
            slippage_rate=0.0002,
            max_position_pct=0.2,
            min_order_notional=10,
            kill_switch_drawdown_pct=0.5,
            ma_fast=10,
            ma_slow=30,
            db_path=db_path,
            poll_seconds=15,
            price_source="binance",
            telegram_enable=False,
            telegram_bot_token="",
            telegram_chat_id="",
            report_tz="Europe/Paris",
        )
        self.db = Database(db_path)
        self.db.init_schema(Path("src/storage/schema.sql"))
        
        # Run migration
        migration_path = Path("migrations/001_add_notification_tracking.sql")
        if migration_path.exists():
            self.db.run_migration(migration_path)
        
        self.broker = PaperBroker(self.settings, self.db)
        self.strategy = MovingAverageCrossStrategy(fast_period=10, slow_period=30)
        self.notifier = TelegramNotifier(
            enabled=False,
            bot_token="",
            chat_id="",
            tz_name="Europe/Paris"
        )
        self.dispatcher = TelegramDispatcher(db=self.db, tz_name="Europe/Paris")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def _candle(self, open_time: int, close: float) -> Candle:
        return Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=open_time,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
            close_time=open_time + 59999,
        )

    def _signal(self, ts: int, signal: str) -> Signal:
        return Signal(
            ts=ts,
            symbol="BTCUSDT",
            timeframe="1m",
            signal=signal,
            reason="test",
            features_json="",
        )

    def test_timeframe_conversion(self):
        """Test timeframe string to milliseconds conversion."""
        self.assertEqual(_timeframe_to_ms("1m"), 60000)
        self.assertEqual(_timeframe_to_ms("5m"), 300000)
        self.assertEqual(_timeframe_to_ms("1h"), 3600000)
        self.assertEqual(_timeframe_to_ms("1d"), 86400000)

    def test_restart_no_double_trades(self):
        """Test that restarting doesn't cause double trades on same candle."""
        # Insert a candle and execute a trade
        candle = self._candle(1000000, 50000.0)
        self.db.insert_candle(candle)
        
        # Prepare closes for MA calculation
        for i in range(35):
            c = self._candle(1000000 - (34 - i) * 60000, 50000.0 + i * 10)
            self.db.insert_candle(c)
        
        signal = self._signal(candle.close_time, "BUY")
        self.db.insert_signal(signal)
        
        result = self.broker.execute_signal(signal, candle)
        self.assertTrue(result.executed)
        
        # Mark as processed
        self.db.set_bot_state("last_processed_open_time", str(candle.open_time))
        
        # Simulate restart - try to execute again
        broker2 = PaperBroker(self.settings, self.db)
        result2 = broker2.execute_signal(signal, candle)
        
        # Should not execute again (trade already exists for this candle)
        self.assertFalse(result2.executed)
        # Check that idempotence message is present
        self.assertIn("idempotence", result2.reason.lower())
        
        # Verify only one trade in database
        trades = self.db.get_trades_between(0, int(time.time() * 1000))
        self.assertEqual(len(trades), 1)

    def test_crash_safe_notifications(self):
        """Test that notifications are sent after crash if not previously sent."""
        # Create a trade manually without marking notification as sent
        candle = self._candle(1000000, 50000.0)
        self.db.insert_candle(candle)
        
        # Prepare closes
        for i in range(35):
            c = self._candle(1000000 - (34 - i) * 60000, 50000.0 + i * 10)
            self.db.insert_candle(c)
        
        signal = self._signal(candle.close_time, "BUY")
        result = self.broker.execute_signal(signal, candle)
        self.assertTrue(result.executed)
        
        # Verify notification is marked as not sent
        unsent = self.db.get_unsent_trade_notifications()
        self.assertEqual(len(unsent), 1)
        self.assertEqual(unsent[0]["trade_id"], result.trade_id)
        
        # Mock the notifier to track calls
        with patch.object(self.notifier, 'notify_trade') as mock_notify:
            # Send pending notifications
            sent_count = send_pending_notifications(
                self.db,
                self.notifier,
                self.dispatcher,
                self.settings
            )
            
            # Should have sent 1 notification
            self.assertEqual(sent_count, 1)
            self.assertEqual(mock_notify.call_count, 1)
        
        # Verify notification is now marked as sent
        unsent_after = self.db.get_unsent_trade_notifications()
        self.assertEqual(len(unsent_after), 0)

    def test_notification_purge(self):
        """Test that old notification records are purged correctly."""
        now_ms = int(time.time() * 1000)
        
        # Insert old notification (40 days ago)
        old_ts = now_ms - (40 * 86400 * 1000)
        self.db.insert_sent_notification("old_event_1", old_ts, "trade", "{}")
        
        # Insert recent notification (10 days ago)
        recent_ts = now_ms - (10 * 86400 * 1000)
        self.db.insert_sent_notification("recent_event_1", recent_ts, "trade", "{}")
        
        # Purge old notifications (older than 30 days)
        deleted = purge_old_notifications(self.db)
        
        # Should have deleted 1 old record
        self.assertEqual(deleted, 1)

    @patch('src.main_live.BinanceRestProvider')
    def test_candle_recovery_gap_filling(self, mock_provider_class):
        """Test that missing candles are recovered and processed."""
        # Setup mock provider
        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider
        
        # Set last processed time to 5 minutes ago
        now_ms = int(time.time() * 1000)
        last_processed = now_ms - (5 * 60 * 1000)  # 5 minutes ago
        self.db.set_bot_state("last_processed_open_time", str(last_processed))
        
        # Prepare historical candles for MA calculation
        for i in range(35):
            c = self._candle(last_processed - (34 - i) * 60000, 50000.0 + i * 10)
            self.db.insert_candle(c)
        
        # Mock the fetch to return 5 missing candles
        # Note: filter_closed_candles will filter out the current/open candle
        missing_candles = []
        for i in range(1, 6):
            candle_time = last_processed + (i * 60000)
            # Make sure candles are closed (close_time < now)
            candle = self._candle(candle_time, 50000.0 + i * 100)
            missing_candles.append(candle)
        
        mock_provider.fetch_klines.return_value = missing_candles
        
        # Run recovery
        recovered = recover_missing_candles(
            self.db,
            self.broker,
            self.strategy,
            self.notifier,
            self.dispatcher,
            self.settings
        )
        
        # Should have recovered at least 4 candles (last one might be filtered as current)
        self.assertGreaterEqual(recovered, 4)
        
        # Verify candles were inserted (check first 4 which should definitely be there)
        for i, candle in enumerate(missing_candles[:4]):
            db_candle = self.db.get_candles_between(
                "BTCUSDT",
                "1m",
                candle.open_time,
                candle.open_time
            )
            self.assertEqual(len(db_candle), 1, f"Candle {i} should be in database")

    def test_notification_tracking_in_database(self):
        """Test that notification tracking works correctly in database."""
        # Execute a trade
        candle = self._candle(1000000, 50000.0)
        self.db.insert_candle(candle)
        
        # Prepare closes
        for i in range(35):
            c = self._candle(1000000 - (34 - i) * 60000, 50000.0 + i * 10)
            self.db.insert_candle(c)
        
        signal = self._signal(candle.close_time, "BUY")
        result = self.broker.execute_signal(signal, candle)
        self.assertTrue(result.executed)
        
        # Initially should be unsent
        unsent = self.db.get_unsent_trade_notifications()
        self.assertEqual(len(unsent), 1)
        
        # Mark as sent
        self.db.mark_trade_notification_sent(result.trade_id, int(time.time() * 1000))
        
        # Should now be empty
        unsent_after = self.db.get_unsent_trade_notifications()
        self.assertEqual(len(unsent_after), 0)

    def test_idempotent_notification_insert(self):
        """Test that sent_notifications table enforces idempotence."""
        event_id = "trade_123"
        ts = int(time.time() * 1000)
        
        # First insert should succeed
        inserted = self.db.insert_sent_notification(event_id, ts, "trade", "{}")
        self.assertTrue(inserted)
        
        # Second insert with same event_id should be ignored
        inserted2 = self.db.insert_sent_notification(event_id, ts + 1000, "trade", "{}")
        self.assertFalse(inserted2)


if __name__ == "__main__":
    unittest.main()
