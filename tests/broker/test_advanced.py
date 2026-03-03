"""Tests avancés du broker: kill-switch, erreurs DB, edge cases."""
from __future__ import annotations

import os
import tempfile
import unittest

from src.broker.paper_broker import PaperBroker
from src.config import Settings
from src.models import Candle, Signal
from src.storage.db import Database


def _make_settings(**overrides) -> Settings:
    defaults = dict(
        app_env="test",
        log_level="WARNING",
        symbol="BTCUSDT",
        timeframe="1m",
        starting_cash=10000,
        fee_rate=0.001,
        slippage_rate=0.0002,
        max_position_pct=0.2,
        min_order_notional=10,
        kill_switch_drawdown_pct=0.10,
        ma_fast=10,
        ma_slow=30,
        poll_seconds=15,
        price_source="binance",
        telegram_enable=False,
        telegram_bot_token="",
        telegram_chat_id="",
        report_tz="Europe/Paris",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _candle(open_time: int, close: float) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=open_time,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        close_time=open_time + 60_000,
    )


class KillSwitchTest(unittest.TestCase):
    def setUp(self) -> None:
        dsn = os.getenv("TEST_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
        if not dsn:
            self.skipTest("TEST_POSTGRES_DSN or POSTGRES_DSN is required for PostgreSQL tests")
        os.environ["POSTGRES_DSN"] = dsn

        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings(
            kill_switch_drawdown_pct=0.10,
            max_position_pct=0.95,
        )
        self.db = Database()
        self.db.init_schema(Path("src/storage/schema.sql"))
        self.broker = PaperBroker(self.settings, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_kill_switch_triggers_on_drawdown(self) -> None:
        # Buy at 100k
        c1 = _candle(1_000_000, 100_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="test")
        self.broker.execute_signal(s_buy, c1)
        self.assertFalse(self.broker.get_state().is_blocked)

        # Price drops 12% → equity drops, should trigger kill switch (threshold 10%)
        c2 = _candle(1_060_000, 88_000.0)
        s_hold = Signal(ts=c2.close_time, symbol="BTCUSDT", timeframe="1m", signal="HOLD", reason="drop")
        self.broker.execute_signal(s_hold, c2)

        self.assertTrue(self.broker.get_state().is_blocked)

    def test_blocked_broker_refuses_trades(self) -> None:
        self.broker.wallet.is_blocked = True
        self.db.save_wallet_state(self.broker.wallet)

        c1 = _candle(3_000_000, 95_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="blocked")
        result = self.broker.execute_signal(s_buy, c1)

        self.assertFalse(result.executed)
        self.assertIn("blocked", result.reason.lower())


class EdgeCasesTest(unittest.TestCase):
    def setUp(self) -> None:
        dsn = os.getenv("TEST_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
        if not dsn:
            self.skipTest("TEST_POSTGRES_DSN or POSTGRES_DSN is required for PostgreSQL tests")
        os.environ["POSTGRES_DSN"] = dsn

        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _make_settings()
        self.db = Database()
        self.db.init_schema(Path("src/storage/schema.sql"))
        self.broker = PaperBroker(self.settings, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_sell_with_no_position(self) -> None:
        c1 = _candle(4_000_000, 90_000.0)
        s_sell = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="SELL", reason="no pos")
        result = self.broker.execute_signal(s_sell, c1)
        self.assertFalse(result.executed)
        self.assertIn("No BTC", result.reason)

    def test_hold_does_not_trade(self) -> None:
        c1 = _candle(5_000_000, 92_000.0)
        s_hold = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="HOLD", reason="waiting")
        result = self.broker.execute_signal(s_hold, c1)
        self.assertFalse(result.executed)
        self.assertEqual(self.broker.get_state().cash, self.settings.starting_cash)

    def test_buy_notional_too_low(self) -> None:
        # Set cash très bas pour que budget < min_order_notional
        self.broker.wallet.cash = 5.0
        self.db.save_wallet_state(self.broker.wallet)

        c1 = _candle(6_000_000, 90_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="low cash")
        result = self.broker.execute_signal(s_buy, c1)
        self.assertFalse(result.executed)
        self.assertIn("Notional too low", result.reason)

    def test_wallet_state_persists_and_reloads(self) -> None:
        c1 = _candle(7_000_000, 100_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="persist test")
        self.broker.execute_signal(s_buy, c1)

        state_before = self.broker.get_state()

        # Recrée un broker pour simuler restart
        broker2 = PaperBroker(self.settings, self.db)
        state_after = broker2.get_state()

        self.assertAlmostEqual(state_before.cash, state_after.cash, places=4)
        self.assertAlmostEqual(state_before.btc_qty, state_after.btc_qty, places=10)
        self.assertAlmostEqual(state_before.fees_paid_total, state_after.fees_paid_total, places=6)

    def test_fees_and_slippage_applied(self) -> None:
        c1 = _candle(8_000_000, 100_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="fee check")
        result = self.broker.execute_signal(s_buy, c1)

        self.assertTrue(result.executed)
        # price_exec should be > market price for BUY (slippage)
        self.assertGreater(result.price_exec, result.price_market)
        # fee should be > 0
        self.assertGreater(result.fee, 0)
        # fees_paid_total should be updated
        self.assertGreater(self.broker.get_state().fees_paid_total, 0)


if __name__ == "__main__":
    unittest.main()
