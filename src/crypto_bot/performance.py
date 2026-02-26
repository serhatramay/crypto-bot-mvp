from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class PerformanceReport:
    trade_count: int
    wins: int
    losses: int
    win_rate_pct: float
    total_net_pnl: float
    avg_net_pnl: float
    avg_win: float
    avg_loss: float
    expectancy: float
    profit_factor: float
    max_drawdown_on_pnl: float
    longest_win_streak: int
    longest_loss_streak: int


def _max_drawdown_from_pnl_curve(net_pnls: list[float]) -> float:
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in net_pnls:
        cum += pnl
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd


def summarize_trade_rows(rows: Iterable[dict]) -> PerformanceReport:
    items = list(rows)
    pnls = [float(r.get("net_pnl", 0.0)) for r in items]
    wins_list = [p for p in pnls if p > 0]
    losses_list = [p for p in pnls if p <= 0]

    wins = len(wins_list)
    losses = len(losses_list)
    n = len(pnls)
    total = sum(pnls)
    avg = total / n if n else 0.0
    avg_win = sum(wins_list) / wins if wins else 0.0
    avg_loss = sum(losses_list) / losses if losses else 0.0
    win_rate = (wins / n * 100) if n else 0.0

    gross_profit = sum(wins_list)
    gross_loss_abs = abs(sum(losses_list))
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else float("inf") if gross_profit > 0 else 0.0
    expectancy = avg
    max_dd = _max_drawdown_from_pnl_curve(pnls)

    longest_win_streak = 0
    longest_loss_streak = 0
    curr_w = 0
    curr_l = 0
    for p in pnls:
        if p > 0:
            curr_w += 1
            curr_l = 0
        else:
            curr_l += 1
            curr_w = 0
        longest_win_streak = max(longest_win_streak, curr_w)
        longest_loss_streak = max(longest_loss_streak, curr_l)

    return PerformanceReport(
        trade_count=n,
        wins=wins,
        losses=losses,
        win_rate_pct=win_rate,
        total_net_pnl=total,
        avg_net_pnl=avg,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        profit_factor=profit_factor,
        max_drawdown_on_pnl=max_dd,
        longest_win_streak=longest_win_streak,
        longest_loss_streak=longest_loss_streak,
    )
