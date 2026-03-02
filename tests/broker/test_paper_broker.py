from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.broker.paper_broker import PaperBroker
from src.config import Settings
from src.models import Candle, Signal
from src.storage.db import Database


class PaperBrokerTest(unittest.TestCase):
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
        self.broker = PaperBroker(self.settings, self.db)

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
            volume=1.0,
            close_time=open_time + 60_000,
        )

    def test_buy_then_sell(self) -> None:
        c1 = self._candle(1_000_000, 100_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="test")
        r_buy = self.broker.execute_signal(s_buy, c1)
        self.assertTrue(r_buy.executed)
        self.assertEqual(r_buy.side, "BUY")

        state_after_buy = self.broker.get_state()
        self.assertGreater(state_after_buy.btc_qty, 0)
        self.assertLess(state_after_buy.cash, self.settings.starting_cash)

        c2 = self._candle(1_060_000, 105_000.0)
        s_sell = Signal(ts=c2.close_time, symbol="BTCUSDT", timeframe="1m", signal="SELL", reason="test")
        r_sell = self.broker.execute_signal(s_sell, c2)
        self.assertTrue(r_sell.executed)
        self.assertEqual(r_sell.side, "SELL")

        state_after_sell = self.broker.get_state()
        self.assertAlmostEqual(state_after_sell.btc_qty, 0.0, places=10)
        self.assertGreater(state_after_sell.cash, 0.0)

    def test_idempotence_same_candle(self) -> None:
        c1 = self._candle(2_000_000, 90_000.0)
        s_buy = Signal(ts=c1.close_time, symbol="BTCUSDT", timeframe="1m", signal="BUY", reason="idempotence")

        first = self.broker.execute_signal(s_buy, c1)
        second = self.broker.execute_signal(s_buy, c1)

        self.assertTrue(first.executed)
        self.assertFalse(second.executed)

        rows = self.db.get_trades_between(0, 9_999_999_999)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
