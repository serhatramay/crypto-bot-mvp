from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class RiskSnapshot:
    day: date | None = None
    day_start_equity: float = 0.0


class RiskManager:
    def __init__(self, risk_per_trade: float, max_daily_loss_pct: float, min_order_notional: float) -> None:
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss_pct = max_daily_loss_pct
        self.min_order_notional = min_order_notional
        self._state = RiskSnapshot()

    def _roll_day(self, current_day: date, equity: float) -> None:
        if self._state.day != current_day:
            self._state.day = current_day
            self._state.day_start_equity = equity

    def trading_allowed(self, current_day: date, equity: float) -> bool:
        self._roll_day(current_day, equity)
        if self._state.day_start_equity <= 0:
            return True
        daily_loss_pct = (self._state.day_start_equity - equity) / self._state.day_start_equity
        return daily_loss_pct < self.max_daily_loss_pct

    def position_size_qty(self, equity: float, price: float) -> float:
        notional = max(self.min_order_notional, equity * self.risk_per_trade)
        notional = min(notional, equity)
        if price <= 0 or notional <= 0:
            return 0.0
        return notional / price
