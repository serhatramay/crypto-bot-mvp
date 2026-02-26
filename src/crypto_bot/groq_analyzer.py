from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable
from urllib import error, request

from .models import ClosedTrade


@dataclass
class GroqAnalysisResult:
    provider: str
    mode: str
    text: str


class GroqTradeLogAnalyzer:
    api_url = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str = "llama-3.1-8b-instant") -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model

    def _local_fallback(self, trades: list[ClosedTrade]) -> GroqAnalysisResult:
        if not trades:
            return GroqAnalysisResult(provider="local", mode="fallback", text="No trades to analyze.")

        wins = sum(1 for t in trades if t.net_pnl > 0)
        losses = len(trades) - wins
        total_net = sum(t.net_pnl for t in trades)
        avg_net = total_net / len(trades)
        stop_exits = sum(1 for t in trades if t.exit_reason == "stop_loss")
        tp_exits = sum(1 for t in trades if t.exit_reason == "take_profit")
        signal_exits = sum(1 for t in trades if t.exit_reason == "signal")
        text = (
            f"Fallback summary: trades={len(trades)}, wins={wins}, losses={losses}, "
            f"total_net={total_net:.2f}, avg_net={avg_net:.2f}, "
            f"exit_reasons(stop={stop_exits}, take_profit={tp_exits}, signal={signal_exits})."
        )
        return GroqAnalysisResult(provider="local", mode="fallback", text=text)

    def analyze(self, trades: Iterable[ClosedTrade], max_trades: int = 30) -> GroqAnalysisResult:
        trade_list = list(trades)[-max_trades:]
        if not self.api_key:
            return self._local_fallback(trade_list)

        compact_trades = [
            {
                "entry": t.entry_ts.isoformat(),
                "exit": t.exit_ts.isoformat(),
                "entry_price": round(t.entry_price, 4),
                "exit_price": round(t.exit_price, 4),
                "qty": round(t.qty, 8),
                "net_pnl": round(t.net_pnl, 4),
                "exit_reason": t.exit_reason,
            }
            for t in trade_list
        ]

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a trading journal analyst. Give concise risk-focused feedback. "
                        "Do not suggest high leverage. Mention patterns in exits and losses."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Analyze the recent paper trades. Return: 1) summary, 2) risks, 3) next tests.\n"
                        + json.dumps(compact_trades, ensure_ascii=True)
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }

        req = request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = body["choices"][0]["message"]["content"].strip()
            return GroqAnalysisResult(provider="groq", mode="api", text=text)
        except (error.URLError, error.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            fallback = self._local_fallback(trade_list)
            fallback.text += f" Groq request failed: {exc}."
            return fallback
