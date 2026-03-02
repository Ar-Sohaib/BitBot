"""Tests du module price_feed avec mock HTTP."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.models import Candle
from src.price_feed.rest_provider import BinanceRestProvider, filter_closed_candles


SAMPLE_KLINE = [
    1709337600000,   # open_time
    "91000.00",      # open
    "91500.00",      # high
    "90800.00",      # low
    "91200.00",      # close
    "123.45",        # volume
    1709337659999,   # close_time
    "11266440.00",   # quote asset volume
    500,             # number of trades
    "61.50",         # taker buy base
    "5620000.00",    # taker buy quote
    "0",             # ignore
]


class BinanceRestProviderTest(unittest.TestCase):
    @patch("src.price_feed.rest_provider.requests.get")
    def test_fetch_klines_parses_correctly(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = [SAMPLE_KLINE]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = BinanceRestProvider()
        candles = provider.fetch_klines("BTCUSDT", "1m", limit=1)

        self.assertEqual(len(candles), 1)
        c = candles[0]
        self.assertIsInstance(c, Candle)
        self.assertEqual(c.symbol, "BTCUSDT")
        self.assertEqual(c.timeframe, "1m")
        self.assertEqual(c.open_time, 1709337600000)
        self.assertAlmostEqual(c.open, 91000.0)
        self.assertAlmostEqual(c.high, 91500.0)
        self.assertAlmostEqual(c.low, 90800.0)
        self.assertAlmostEqual(c.close, 91200.0)
        self.assertAlmostEqual(c.volume, 123.45)
        self.assertEqual(c.close_time, 1709337659999)

    @patch("src.price_feed.rest_provider.requests.get")
    def test_fetch_klines_empty(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = BinanceRestProvider()
        candles = provider.fetch_klines("BTCUSDT", "1m")
        self.assertEqual(candles, [])

    @patch("src.price_feed.rest_provider.requests.get")
    def test_fetch_klines_http_error(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 500")
        mock_get.return_value = mock_resp

        provider = BinanceRestProvider()
        with self.assertRaises(Exception):
            provider.fetch_klines("BTCUSDT", "1m")


class FilterClosedCandlesTest(unittest.TestCase):
    def test_filters_future_candles(self) -> None:
        import time
        now_ms = int(time.time() * 1000)
        past = Candle("BTC", "1m", now_ms - 120_000, 1, 1, 1, 1, 1, now_ms - 60_001)
        future = Candle("BTC", "1m", now_ms + 60_000, 1, 1, 1, 1, 1, now_ms + 120_000)
        result = filter_closed_candles([past, future])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open_time, past.open_time)


if __name__ == "__main__":
    unittest.main()
