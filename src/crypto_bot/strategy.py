from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import Candle, Signal


@dataclass
class StrategyState:
    prev_short_ma: float | None = None
    prev_long_ma: float | None = None


class SmaCrossStrategy:
    def __init__(self, short_window: int, long_window: int) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")
        self.short_window = short_window
        self.long_window = long_window
        self._short = deque(maxlen=short_window)
        self._long = deque(maxlen=long_window)
        self.state = StrategyState()

    def on_candle(self, candle: Candle, has_position: bool) -> Signal:
        self._short.append(candle.close)
        self._long.append(candle.close)

        if len(self._long) < self.long_window:
            return Signal.HOLD

        short_ma = sum(self._short) / len(self._short)
        long_ma = sum(self._long) / len(self._long)
        signal = Signal.HOLD

        if self.state.prev_short_ma is not None and self.state.prev_long_ma is not None:
            crossed_up = self.state.prev_short_ma <= self.state.prev_long_ma and short_ma > long_ma
            crossed_down = self.state.prev_short_ma >= self.state.prev_long_ma and short_ma < long_ma

            if crossed_up and not has_position:
                signal = Signal.BUY
            elif crossed_down and has_position:
                signal = Signal.SELL

        self.state.prev_short_ma = short_ma
        self.state.prev_long_ma = long_ma
        return signal
