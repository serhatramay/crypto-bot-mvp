from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import ClosedTrade, Position


@dataclass
class PaperWallet:
    cash: float
    fee_rate: float
    position: Position = field(default_factory=Position)
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    total_fees_paid: float = 0.0

    def equity(self, mark_price: float) -> float:
        return self.cash + (self.position.qty * mark_price if self.position.is_open else 0.0)

    def buy(
        self,
        ts: datetime,
        price: float,
        qty: float,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
    ) -> bool:
        if qty <= 0 or price <= 0 or self.position.is_open:
            return False
        notional = qty * price
        fee = notional * self.fee_rate
        total_cost = notional + fee
        if total_cost > self.cash:
            return False
        self.cash -= total_cost
        self.total_fees_paid += fee
        self.position = Position(
            qty=qty,
            entry_price=price,
            entry_ts=ts,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            entry_fee_remaining=fee,
        )
        return True

    def sell_all(self, ts: datetime, price: float, reason: str = "signal") -> bool:
        if not self.position.is_open:
            return False
        return self.sell_qty(ts, price, self.position.qty, reason=reason)

    def sell_qty(self, ts: datetime, price: float, qty: float, reason: str = "signal") -> bool:
        if not self.position.is_open or price <= 0 or self.position.entry_ts is None:
            return False

        qty_before = self.position.qty
        qty = min(qty, qty_before)
        if qty <= 0:
            return False
        notional = qty * price
        exit_fee = notional * self.fee_rate
        gross_pnl = (price - self.position.entry_price) * qty
        # Allocate buy-side fee proportionally for partial fills.
        entry_fee_alloc = (
            (self.position.entry_fee_remaining * (qty / qty_before))
            if qty_before > 0
            else 0.0
        )
        total_trade_fees = entry_fee_alloc + exit_fee
        net_pnl = gross_pnl - total_trade_fees

        self.cash += notional - exit_fee
        self.total_fees_paid += exit_fee
        self.closed_trades.append(
            ClosedTrade(
                entry_ts=self.position.entry_ts,
                exit_ts=ts,
                entry_price=self.position.entry_price,
                exit_price=price,
                qty=qty,
                gross_pnl=gross_pnl,
                fees=total_trade_fees,
                net_pnl=net_pnl,
                entry_fee=entry_fee_alloc,
                exit_fee=exit_fee,
                exit_reason=reason,
            )
        )
        remaining_qty = qty_before - qty
        if remaining_qty <= 1e-12:
            self.position = Position()
        else:
            self.position.qty = remaining_qty
            self.position.entry_fee_remaining = max(0.0, self.position.entry_fee_remaining - entry_fee_alloc)
        return True
