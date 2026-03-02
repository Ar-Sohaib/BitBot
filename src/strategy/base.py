from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import Signal


class Strategy(ABC):
    @abstractmethod
    def generate_signal(
        self,
        ts: int,
        symbol: str,
        timeframe: str,
        closes: list[float],
        in_position: bool,
    ) -> Signal:
        raise NotImplementedError
