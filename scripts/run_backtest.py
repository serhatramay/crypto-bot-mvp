from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.engine import TradingEngine
from crypto_bot.exchange import CsvMarketDataFeed
from crypto_bot.models import BotConfig


def main() -> None:
    csv_path = ROOT / "data" / "sample_ohlcv.csv"
    if not csv_path.exists():
        print("Sample data not found. Run: python3 scripts/generate_sample_data.py")
        return

    config = BotConfig(
        symbol="BTCUSDT",
        mode="paper",
        initial_cash=5000.0,
        fee_rate=0.001,
        short_window=7,
        long_window=25,
        risk_per_trade=0.25,  # MVP: pozisyon boyutu buyuk olsun ki islemler gorulsun
        max_daily_loss_pct=0.05,
        min_order_notional=250.0,
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
    )

    feed = CsvMarketDataFeed(csv_path)
    candles = list(feed.candles())
    engine = TradingEngine(config)
    result = engine.run(candles)

    print("=== Backtest Result ===")
    print(f"Symbol: {config.symbol}")
    print(f"Initial Cash: {result.initial_cash:.2f} TL")
    print(f"Final Equity: {result.final_equity:.2f} TL")
    print(f"Return: {result.total_return_pct:.2f}%")
    print(f"Max Drawdown: {result.max_drawdown_pct:.2f}%")
    print(f"Trades: {result.trade_count}")
    print(f"Win Rate: {result.win_rate_pct:.2f}%")
    print(f"Fees Paid: {result.total_fees_paid:.2f} TL")
    print(f"Mode: {config.mode}")
    print(f"SL/TP: {config.stop_loss_pct*100:.2f}% / {config.take_profit_pct*100:.2f}%")

    if engine.wallet.closed_trades:
        print("\nLast 3 trades:")
        for trade in engine.wallet.closed_trades[-3:]:
            print(
                f"- {trade.entry_ts.isoformat()} -> {trade.exit_ts.isoformat()} | "
                f"entry={trade.entry_price:.2f} exit={trade.exit_price:.2f} "
                f"qty={trade.qty:.6f} net_pnl={trade.net_pnl:.2f} reason={trade.exit_reason}"
            )


if __name__ == "__main__":
    main()
