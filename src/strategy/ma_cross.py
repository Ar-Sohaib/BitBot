from __future__ import annotations

import json

from src.models import Signal
from src.strategy.base import Strategy


class MovingAverageCrossStrategy(Strategy):
    def __init__(self, fast_period: int = 10, slow_period: int = 30):
        if fast_period <= 1 or slow_period <= 1:
            raise ValueError("MA periods must be > 1")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be < slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period

    @staticmethod
    def _sma(values: list[float], period: int) -> float:
        return sum(values[-period:]) / period

    def generate_signal(
        self,
        ts: int,
        symbol: str,
        timeframe: str,
        closes: list[float],
        in_position: bool,
    ) -> Signal:
        needed = self.slow_period + 1
        if len(closes) < needed:
            return Signal(
                ts=ts,
                symbol=symbol,
                timeframe=timeframe,
                signal="HOLD",
                reason=f"Not enough data: {len(closes)}/{needed}",
            )

        prev = closes[:-1]
        curr = closes

        prev_fast = self._sma(prev, self.fast_period)
        prev_slow = self._sma(prev, self.slow_period)
        curr_fast = self._sma(curr, self.fast_period)
        curr_slow = self._sma(curr, self.slow_period)

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        signal = "HOLD"
        reason = "No crossover"
        if crossed_up and not in_position:
            signal = "BUY"
            reason = f"MA{self.fast_period} crossed above MA{self.slow_period}"
        elif crossed_down and in_position:
            signal = "SELL"
            reason = f"MA{self.fast_period} crossed below MA{self.slow_period}"

        features = {
            "prev_fast": prev_fast,
            "prev_slow": prev_slow,
            "curr_fast": curr_fast,
            "curr_slow": curr_slow,
            "in_position": in_position,
        }

        return Signal(
            ts=ts,
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            reason=reason,
            features_json=json.dumps(features),
        )
