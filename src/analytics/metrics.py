from __future__ import annotations

from typing import Iterable


def winrate_from_trades(pnls: Iterable[float]) -> float:
    values = list(pnls)
    if not values:
        return 0.0
    wins = sum(1 for x in values if x > 0)
    return wins / len(values)


def max_drawdown_from_equity(drawdowns: Iterable[float]) -> float:
    values = list(drawdowns)
    if not values:
        return 0.0
    return max(values)
