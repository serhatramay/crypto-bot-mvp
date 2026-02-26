from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Position:
    qty: float = 0.0
    entry_price: float = 0.0
    entry_ts: Optional[datetime] = None
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    entry_fee_remaining: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.qty > 0


@dataclass
class ClosedTrade:
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    qty: float
    gross_pnl: float
    fees: float
    net_pnl: float
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    exit_reason: str = "signal"


@dataclass
class BotConfig:
    symbol: str = "BTCUSDT"
    timeframe: str = "5m"
    initial_cash: float = 5000.0
    fee_rate: float = 0.001  # 0.1%
    short_window: int = 5
    long_window: int = 20
    risk_per_trade: float = 0.01  # equity'nin %1'i
    max_daily_loss_pct: float = 0.03
    min_order_notional: float = 100.0
    close_position_at_end: bool = True
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    mode: str = "paper"  # paper | live
    exchange_provider: str = "binance"  # binance | bybit
    exchange_testnet: bool = True
    exchange_api_key: Optional[str] = None
    exchange_api_secret: Optional[str] = None
    dry_run_live: bool = True
    paper_spread_bps: float = 2.0
    paper_slippage_bps: float = 3.0
    paper_tick_size: float = 0.01
    paper_qty_step: float = 0.000001
    paper_partial_fill_probability: float = 0.05
    paper_partial_fill_min_ratio: float = 0.4
    paper_random_seed: int = 42
    enable_llm_log_analysis: bool = False
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-8b-instant"
