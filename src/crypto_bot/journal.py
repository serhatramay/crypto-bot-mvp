from __future__ import annotations

import json
from pathlib import Path

from .models import ClosedTrade


def trade_to_dict(trade: ClosedTrade) -> dict:
    return {
        "entry_ts": trade.entry_ts.isoformat(),
        "exit_ts": trade.exit_ts.isoformat(),
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "qty": trade.qty,
        "gross_pnl": trade.gross_pnl,
        "fees": trade.fees,
        "entry_fee": trade.entry_fee,
        "exit_fee": trade.exit_fee,
        "net_pnl": trade.net_pnl,
        "exit_reason": trade.exit_reason,
    }


def write_trade_log_jsonl(trades: list[ClosedTrade], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for trade in trades:
            f.write(json.dumps(trade_to_dict(trade), ensure_ascii=True) + "\n")
    return path


def append_trade_log_jsonl(trades: list[ClosedTrade], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for trade in trades:
            f.write(json.dumps(trade_to_dict(trade), ensure_ascii=True) + "\n")
    return path


def read_trade_log_jsonl(input_path: str | Path) -> list[dict]:
    path = Path(input_path)
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows
