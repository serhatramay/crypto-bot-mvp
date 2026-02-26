from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable


@dataclass
class RiskSnapshot:
    day: date | None = None
    day_start_equity: float = 0.0
    realized_daily_pnl: float = 0.0  # Track realized PnL separately


class RiskManager:
    def __init__(self, risk_per_trade: float, max_daily_loss_pct: float, min_order_notional: float) -> None:
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss_pct = max_daily_loss_pct
        self.min_order_notional = min_order_notional
        self._state = RiskSnapshot()
        self._on_trade_close_callbacks: list[Callable[[float], None]] = []

    def _roll_day(self, current_day: date, equity: float) -> None:
        if self._state.day != current_day:
            self._state.day = current_day
            self._state.day_start_equity = equity
            self._state.realized_daily_pnl = 0.0  # Reset realized PnL on new day

    def on_trade_closed(self, net_pnl: float) -> None:
        """Call this when a trade is closed to track realized PnL."""
        self._state.realized_daily_pnl += net_pnl

    def trading_allowed(self, current_day: date, equity: float, unrealized_pnl: float = 0.0) -> bool:
        """Check if trading is allowed based on daily loss limit.
        
        Args:
            current_day: Current trading day
            equity: Current total equity (cash + position value)
            unrealized_pnl: Unrealized profit/loss from open position (default 0)
                             This is excluded from daily loss calculation.
        """
        self._roll_day(current_day, equity)
        if self._state.day_start_equity <= 0:
            return True
        
        # Only count realized PnL against daily loss limit
        # Unrealized PnL (open position fluctuations) doesn't count
        effective_equity = equity - unrealized_pnl
        daily_loss_pct = (self._state.day_start_equity - effective_equity + self._state.realized_daily_pnl) / self._state.day_start_equity
        
        # Alternative simpler calculation: use realized PnL directly
        realized_loss_pct = -self._state.realized_daily_pnl / self._state.day_start_equity if self._state.day_start_equity > 0 else 0
        
        return realized_loss_pct < self.max_daily_loss_pct

    def get_daily_stats(self) -> dict:
        """Get current daily risk statistics."""
        return {
            "day": self._state.day.isoformat() if self._state.day else None,
            "day_start_equity": self._state.day_start_equity,
            "realized_daily_pnl": self._state.realized_daily_pnl,
            "max_daily_loss_pct": self.max_daily_loss_pct,
        }

    def position_size_qty(self, equity: float, price: float) -> float:
        notional = max(self.min_order_notional, equity * self.risk_per_trade)
        notional = min(notional, equity)
        if price <= 0 or notional <= 0:
            return 0.0
        return notional / price
