"""Tests du module TelegramNotifier avec mock HTTP."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.models import DailyReport, TradeResult
from src.notify.telegram import TelegramNotifier


class TelegramNotifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.notifier = TelegramNotifier(
            enabled=True,
            bot_token="FAKE:TOKEN",
            chat_id="12345",
            tz_name="Europe/Paris",
        )

    @patch("src.notify.telegram.requests.post")
    def test_send_message_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        self.notifier.send_message("Hello test")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        self.assertIn("Hello test", str(call_kwargs))

    @patch("src.notify.telegram.requests.post")
    def test_send_message_disabled(self, mock_post: MagicMock) -> None:
        disabled = TelegramNotifier(enabled=False, bot_token="", chat_id="")
        disabled.send_message("Should not send")
        mock_post.assert_not_called()

    @patch("src.notify.telegram.requests.post")
    def test_send_message_retry_on_failure(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = [Exception("Network error"), MagicMock(status_code=200)]
        mock_post.return_value = MagicMock()
        self.notifier.send_message("Retry test")
        self.assertEqual(mock_post.call_count, 2)

    @patch("src.notify.telegram.requests.post")
    def test_notify_trade_format(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        trade = TradeResult(
            executed=True,
            side="BUY",
            reason="MA10 crossed above MA30",
            trade_id="abc-123",
            qty_btc=0.01092,
            price_market=91500.0,
            price_exec=91518.3,
            fee=1.0,
        )
        self.notifier.notify_trade(trade, market_price=91500.0, cash=8999.0, btc_qty=0.01092, slippage_rate=0.0002)

        call_args = mock_post.call_args
        text = call_args[1]["json"]["text"] if "json" in (call_args[1] or {}) else call_args[0][0]
        self.assertIn("[PAPER][BTC] BUY", text)
        self.assertIn("Time:", text)
        self.assertIn("Market:", text)
        self.assertIn("slip", text)
        self.assertIn("Reason:", text)

    @patch("src.notify.telegram.requests.post")
    def test_notify_kill_switch_format(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        self.notifier.notify_kill_switch(drawdown=0.153, threshold=0.15, equity=8420.5)

        call_args = mock_post.call_args
        text = call_args[1]["json"]["text"] if "json" in (call_args[1] or {}) else ""
        self.assertIn("[ALERT][PAPER][BTC] Kill switch", text)
        self.assertIn("Drawdown:", text)
        self.assertIn("seuil", text)
        self.assertIn("Equity:", text)

    @patch("src.notify.telegram.requests.post")
    def test_notify_feed_down_anti_spam(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        self.notifier.notify_feed_down("Connection timeout")
        self.notifier.notify_feed_down("Connection timeout again")
        self.assertEqual(mock_post.call_count, 1)

    @patch("src.notify.telegram.requests.post")
    def test_notify_feed_recovered(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        self.notifier._feed_error_notified = True
        self.notifier.notify_feed_recovered()
        self.assertFalse(self.notifier._feed_error_notified)
        mock_post.assert_called_once()

    @patch("src.notify.telegram.requests.post")
    def test_notify_bot_start(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        self.notifier.notify_bot_start("BTCUSDT", "1m")
        call_args = mock_post.call_args
        text = call_args[1]["json"]["text"] if "json" in (call_args[1] or {}) else ""
        self.assertIn("[INFO][PAPER][BTC] Bot démarré", text)
        self.assertIn("BTCUSDT", text)

    @patch("src.notify.telegram.requests.post")
    def test_notify_daily_report(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

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
        self.notifier.notify_daily_report(report)
        call_args = mock_post.call_args
        text = call_args[1]["json"]["text"] if "json" in (call_args[1] or {}) else ""
        self.assertIn("[DAILY REPORT][PAPER][BTC]", text)
        self.assertIn("Notes:", text)


if __name__ == "__main__":
    unittest.main()
