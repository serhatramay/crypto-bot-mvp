from __future__ import annotations

from dataclasses import dataclass
from math import inf

from .models import BotConfig, Candle, Signal
from .execution import build_order_executor
from .paper_wallet import PaperWallet
from .risk import RiskManager
from .strategy import SmaCrossStrategy


@dataclass
class BacktestResult:
    initial_cash: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_rate_pct: float
    total_fees_paid: float


class TradingEngine:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.strategy = SmaCrossStrategy(config.short_window, config.long_window)
        self.risk = RiskManager(config.risk_per_trade, config.max_daily_loss_pct, config.min_order_notional)
        self.wallet = PaperWallet(cash=config.initial_cash, fee_rate=config.fee_rate)
        self.executor = build_order_executor(config, self.wallet)

    def _exit_price_and_reason(self, candle: Candle) -> tuple[float, str] | None:
        pos = self.wallet.position
        if not pos.is_open:
            return None

        if pos.stop_loss_price and candle.low <= pos.stop_loss_price:
            return pos.stop_loss_price, "stop_loss"
        if pos.take_profit_price and candle.high >= pos.take_profit_price:
            return pos.take_profit_price, "take_profit"
        return None

    def run(self, candles: list[Candle]) -> BacktestResult:
        if not candles:
            raise ValueError("No candles provided")

        peak_equity = -inf
        max_drawdown = 0.0

        for candle in candles:
            equity_before = self.wallet.equity(candle.close)
            peak_equity = max(peak_equity, equity_before)
            if peak_equity > 0:
                dd = (peak_equity - equity_before) / peak_equity
                max_drawdown = max(max_drawdown, dd)

            signal = self.strategy.on_candle(candle, self.wallet.position.is_open)

            exit_trigger = self._exit_price_and_reason(candle)
            if exit_trigger is not None:
                exit_price, reason = exit_trigger
                self.executor.place_market_sell_all(candle.ts, exit_price, reason=reason)
                continue

            if signal == Signal.BUY:
                if self.risk.trading_allowed(candle.ts.date(), equity_before):
                    qty = self.risk.position_size_qty(equity_before, candle.close)
                    stop_price = candle.close * (1 - self.config.stop_loss_pct)
                    take_price = candle.close * (1 + self.config.take_profit_pct)
                    self.executor.place_market_buy(
                        candle.ts,
                        candle.close,
                        qty,
                        stop_loss_price=stop_price,
                        take_profit_price=take_price,
                    )
            elif signal == Signal.SELL:
                self.executor.place_market_sell_all(candle.ts, candle.close, reason="signal")

        if self.config.close_position_at_end and self.wallet.position.is_open:
            last = candles[-1]
            self.executor.place_market_sell_all(last.ts, last.close, reason="end_of_data")

        final_equity = self.wallet.equity(candles[-1].close)
        wins = sum(1 for t in self.wallet.closed_trades if t.net_pnl > 0)
        trade_count = len(self.wallet.closed_trades)
        win_rate = (wins / trade_count * 100) if trade_count else 0.0
        total_return_pct = ((final_equity - self.config.initial_cash) / self.config.initial_cash) * 100

        return BacktestResult(
            initial_cash=self.config.initial_cash,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_drawdown * 100,
            trade_count=trade_count,
            win_rate_pct=win_rate,
            total_fees_paid=self.wallet.total_fees_paid,
        )
