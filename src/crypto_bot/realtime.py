from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .execution import build_order_executor
from .models import BotConfig, Candle, Signal
from .paper_wallet import PaperWallet
from .risk import RiskManager
from .strategy import SmaCrossStrategy


@dataclass
class RealtimeEvent:
    ts: str
    price: float
    signal: str
    equity: float
    position_open: bool
    note: str = ""


class RealtimePaperRunner:
    def __init__(self, config: BotConfig) -> None:
        if config.mode != "paper":
            raise ValueError("RealtimePaperRunner only supports paper mode")
        self.config = config
        self.wallet = PaperWallet(cash=config.initial_cash, fee_rate=config.fee_rate)
        self.strategy = SmaCrossStrategy(config.short_window, config.long_window)
        self.risk = RiskManager(config.risk_per_trade, config.max_daily_loss_pct, config.min_order_notional)
        self.executor = build_order_executor(config, self.wallet)

    def _check_sl_tp(self, candle: Candle) -> Optional[tuple[float, str]]:
        """Check if SL or TP was hit within the candle range.
        
        Returns the execution price and reason. For more realistic simulation,
        SL/TP executes at the trigger price, not at close.
        """
        pos = self.wallet.position
        if not pos.is_open:
            return None
        
        sl_price = pos.stop_loss_price
        tp_price = pos.take_profit_price
        
        # Check if SL was hit (price went below SL)
        if sl_price and candle.low <= sl_price:
            # Check if TP was also hit in the same candle
            if tp_price and candle.high >= tp_price:
                # Both hit - determine which came first
                # If entry was below SL (long position), price went up then down
                # If entry was above TP, price went down then up
                # Conservative: assume SL hit first (worse outcome)
                entry = pos.entry_price
                if entry <= sl_price:
                    # Price went up then down, TP hit first
                    return tp_price, "take_profit"
                else:
                    # Price went down then up, SL hit first
                    return sl_price, "stop_loss"
            return sl_price, "stop_loss"
        
        # Check if TP was hit (price went above TP)
        if tp_price and candle.high >= tp_price:
            return tp_price, "take_profit"
        
        return None

    def process_candle(self, candle: Candle, on_event: Optional[Callable[[RealtimeEvent], None]] = None) -> RealtimeEvent:
        equity_before = self.wallet.equity(candle.close)
        signal = self.strategy.on_candle(candle, self.wallet.position.is_open)
        note = ""

        exit_trigger = self._check_sl_tp(candle)
        if exit_trigger is not None:
            price, reason = exit_trigger
            before_trades = len(self.wallet.closed_trades)
            self.executor.place_market_sell_all(candle.ts, price, reason=reason)
            if len(self.wallet.closed_trades) > before_trades:
                t = self.wallet.closed_trades[-1]
                note = f"sell qty={t.qty:.6f} @ {t.exit_price:.2f} pnl={t.net_pnl:.2f} ({t.exit_reason})"
                # Notify risk manager of realized PnL
                self.risk.on_trade_closed(t.net_pnl)
            else:
                note = reason
            signal = Signal.SELL
        elif signal == Signal.BUY:
            if self.risk.trading_allowed(candle.ts.date(), equity_before):
                qty = self.risk.position_size_qty(equity_before, candle.close)
                sl = candle.close * (1 - self.config.stop_loss_pct)
                tp = candle.close * (1 + self.config.take_profit_pct)
                ok = self.executor.place_market_buy(candle.ts, candle.close, qty, sl, tp)
                if ok and self.wallet.position.is_open:
                    pos = self.wallet.position
                    note = (
                        f"buy qty={pos.qty:.6f} @ {pos.entry_price:.2f} "
                        f"sl={pos.stop_loss_price:.2f} tp={pos.take_profit_price:.2f}"
                    )
                else:
                    note = "buy_rejected"
            else:
                note = "risk_blocked"
        elif signal == Signal.SELL:
            before_trades = len(self.wallet.closed_trades)
            ok = self.executor.place_market_sell_all(candle.ts, candle.close, reason="signal")
            if ok and len(self.wallet.closed_trades) > before_trades:
                t = self.wallet.closed_trades[-1]
                note = f"sell qty={t.qty:.6f} @ {t.exit_price:.2f} pnl={t.net_pnl:.2f} ({t.exit_reason})"
                # Notify risk manager of realized PnL
                self.risk.on_trade_closed(t.net_pnl)
            else:
                note = "sell_rejected"

        event = RealtimeEvent(
            ts=candle.ts.isoformat(),
            price=candle.close,
            signal=signal.value,
            equity=self.wallet.equity(candle.close),
            position_open=self.wallet.position.is_open,
            note=note,
        )
        if on_event:
            on_event(event)
        return event

    def finish(self, last_candle: Candle | None) -> None:
        if self.config.close_position_at_end and self.wallet.position.is_open and last_candle is not None:
            self.executor.place_market_sell_all(last_candle.ts, last_candle.close, reason="end_of_stream")

    def run(
        self,
        candles: Iterable[Candle],
        speed: float = 0.0,
        on_event: Optional[Callable[[RealtimeEvent], None]] = None,
        max_steps: int | None = None,
    ) -> None:
        last_candle: Candle | None = None
        for i, candle in enumerate(candles):
            last_candle = candle
            if max_steps is not None and i >= max_steps:
                break
            self.process_candle(candle, on_event=on_event)
            if speed > 0:
                time.sleep(speed)
        self.finish(last_candle)
