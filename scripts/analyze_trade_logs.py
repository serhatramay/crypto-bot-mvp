from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.engine import TradingEngine
from crypto_bot.exchange import CsvMarketDataFeed
from crypto_bot.groq_analyzer import GroqTradeLogAnalyzer
from crypto_bot.journal import write_trade_log_jsonl
from crypto_bot.models import BotConfig


def main() -> None:
    csv_path = ROOT / "data" / "sample_ohlcv.csv"
    if not csv_path.exists():
        print("Sample data not found. Run: python3 scripts/generate_sample_data.py")
        return

    config = BotConfig(
        symbol="BTCUSDT",
        initial_cash=5000.0,
        short_window=7,
        long_window=25,
        risk_per_trade=0.25,
        min_order_notional=250.0,
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
        enable_llm_log_analysis=True,
        groq_api_key=os.getenv("GROQ_API_KEY"),
    )

    candles = list(CsvMarketDataFeed(csv_path).candles())
    engine = TradingEngine(config)
    result = engine.run(candles)

    log_path = write_trade_log_jsonl(engine.wallet.closed_trades, ROOT / "logs" / "trades.jsonl")
    analysis = GroqTradeLogAnalyzer(api_key=config.groq_api_key, model=config.groq_model).analyze(
        engine.wallet.closed_trades
    )

    print("=== Trade Journal Analysis ===")
    print(f"Final Equity: {result.final_equity:.2f} TL | Return: {result.total_return_pct:.2f}%")
    print(f"Trade log: {log_path}")
    print(f"Analyzer provider: {analysis.provider} ({analysis.mode})")
    print("\n" + analysis.text)


if __name__ == "__main__":
    main()
