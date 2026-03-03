from __future__ import annotations

import time
from typing import Any

import requests

from src.models import Candle


class BinanceRestProvider:
    BASE_URL = "https://api.binance.com"

    def __init__(self, timeout_seconds: int = 10):
        self.timeout_seconds = timeout_seconds

    def fetch_klines(self, symbol: str, timeframe: str, limit: int = 200, start_time: int | None = None) -> list[Candle]:
        """Fetch klines from Binance REST API.
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            timeframe: Interval (e.g., 1m, 5m, 1h)
            limit: Number of candles to fetch (max 1000)
            start_time: Optional start time in milliseconds (for recovery)
        
        Returns:
            List of Candle objects
        """
        url = f"{self.BASE_URL}/api/v3/klines"
        params = {"symbol": symbol.upper(), "interval": timeframe, "limit": max(2, min(limit, 1000))}
        
        if start_time is not None:
            params["startTime"] = start_time
        
        response = requests.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        raw: list[list[Any]] = response.json()

        out: list[Candle] = []
        for row in raw:
            out.append(
                Candle(
                    symbol=symbol.upper(),
                    timeframe=timeframe,
                    open_time=int(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    close_time=int(row[6]),
                )
            )
        return out


def filter_closed_candles(candles: list[Candle]) -> list[Candle]:
    now_ms = int(time.time() * 1000)
    return [c for c in candles if c.close_time <= now_ms]
