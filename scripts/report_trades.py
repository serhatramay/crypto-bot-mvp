from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.journal import read_trade_log_jsonl
from crypto_bot.performance import summarize_trade_rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Report performance from JSONL trade logs")
    p.add_argument("--log-file", default=str(ROOT / "logs" / "ws_paper_trades.jsonl"))
    p.add_argument("--min-trades", type=int, default=100)
    return p


def main() -> None:
    args = build_parser().parse_args()
    rows = read_trade_log_jsonl(args.log_file)
    if not rows:
        print(f"No trades found in {args.log_file}")
        return

    report = summarize_trade_rows(rows)
    print("=== Performance Report ===")
    print(f"Log file: {args.log_file}")
    print(f"Trades: {report.trade_count} (target: {args.min_trades}+) {'OK' if report.trade_count >= args.min_trades else 'NOT ENOUGH'}")
    print(f"Wins / Losses: {report.wins} / {report.losses} | Win Rate: {report.win_rate_pct:.2f}%")
    print(f"Total Net PnL: {report.total_net_pnl:.2f}")
    print(f"Avg Net PnL (Expectancy): {report.expectancy:.4f}")
    print(f"Avg Win: {report.avg_win:.4f} | Avg Loss: {report.avg_loss:.4f}")
    pf = "inf" if report.profit_factor == float('inf') else f"{report.profit_factor:.3f}"
    print(f"Profit Factor: {pf}")
    print(f"Max Drawdown (cum pnl): {report.max_drawdown_on_pnl:.2f}")
    print(f"Longest Win/Loss Streak: {report.longest_win_streak}/{report.longest_loss_streak}")

    print("\nReadiness (heuristic):")
    if report.trade_count < args.min_trades:
        print("- Veri yetersiz: 100+ islem birikmeden canli karar verme.")
    elif report.expectancy <= 0:
        print("- Beklenen deger <= 0: stratejiyi canliya alma.")
    elif report.profit_factor < 1.1:
        print("- Profit factor zayif: maliyet/sippage ile bozulabilir.")
    else:
        print("- Paper sonuçları umut verici. Sonraki adım: testnet gerçek emir akışı.")


if __name__ == "__main__":
    main()
