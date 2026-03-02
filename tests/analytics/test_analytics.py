"""Tests du module analytics: daily_report et metrics."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.analytics.daily_report import (
    build_daily_report,
    day_bounds_epoch_ms,
    render_daily_report_text,
)
from src.analytics.metrics import max_drawdown_from_equity, winrate_from_trades
from src.models import DailyReport, WalletState
from src.storage.db import Database


class MetricsTest(unittest.TestCase):
    def test_winrate_empty(self) -> None:
        self.assertEqual(winrate_from_trades([]), 0.0)

    def test_winrate_all_wins(self) -> None:
        self.assertEqual(winrate_from_trades([10.0, 5.0, 1.0]), 1.0)

    def test_winrate_mixed(self) -> None:
        self.assertAlmostEqual(winrate_from_trades([10.0, -5.0, 3.0, -1.0]), 0.5)

    def test_winrate_all_losses(self) -> None:
        self.assertEqual(winrate_from_trades([-5.0, -10.0]), 0.0)

    def test_max_drawdown_empty(self) -> None:
        self.assertEqual(max_drawdown_from_equity([]), 0.0)

    def test_max_drawdown_values(self) -> None:
        self.assertAlmostEqual(max_drawdown_from_equity([0.01, 0.05, 0.03]), 0.05)


class DayBoundsTest(unittest.TestCase):
    def test_bounds(self) -> None:
        start, end = day_bounds_epoch_ms(date(2026, 3, 2), "Europe/Paris")
        self.assertGreater(end, start)
        self.assertGreater(start, 0)


class RenderDailyReportTest(unittest.TestCase):
    def test_render_contains_required_fields(self) -> None:
        report = DailyReport(
            day="2026-03-02",
            equity_start=10000.0,
            equity_end=10125.4,
            pnl_abs=125.4,
            pnl_pct=0.01254,
            trades_count=4,
            buy_count=2,
            sell_count=2,
            winrate=0.5,
            fees_total=8.2,
            max_drawdown=0.009,
            cash_end=6500.0,
            btc_qty_end=0.0398,
            btc_price_end=91500.0,
            exposure_pct=0.36,
            notes="feed ok, no errors",
        )
        text = render_daily_report_text(report)
        self.assertIn("[DAILY REPORT][PAPER][BTC]", text)
        self.assertIn("2026-03-02", text)
        self.assertIn("Equity:", text)
        self.assertIn("PnL", text)
        self.assertIn("Trades:", text)
        self.assertIn("BUY", text)
        self.assertIn("SELL", text)
        self.assertIn("Winrate:", text)
        self.assertIn("Fees:", text)
        self.assertIn("Max DD:", text)
        self.assertIn("End wallet:", text)
        self.assertIn("exposure=", text)
        self.assertIn("Notes:", text)


class BuildDailyReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "test.db"
        self.db = Database(db_path)
        self.db.init_schema(Path("src/storage/schema.sql"))

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_build_empty_day(self) -> None:
        wallet = WalletState(cash=10000, btc_qty=0, avg_entry_price=0, fees_paid_total=0, is_blocked=False, peak_equity=10000)
        report = build_daily_report(self.db, date(2026, 3, 2), "Europe/Paris", wallet, 90000.0)
        self.assertEqual(report.day, "2026-03-02")
        self.assertEqual(report.trades_count, 0)
        self.assertEqual(report.pnl_abs, 0.0)
        self.assertEqual(report.notes, "feed ok, no errors")


if __name__ == "__main__":
    unittest.main()
