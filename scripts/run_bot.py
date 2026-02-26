from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.config import apply_env_to_process, build_bot_config, load_env_file, load_json_config
from crypto_bot.engine import TradingEngine
from crypto_bot.exchange import CsvMarketDataFeed
from crypto_bot.execution import build_order_executor
from crypto_bot.groq_analyzer import GroqTradeLogAnalyzer
from crypto_bot.journal import write_trade_log_jsonl
from crypto_bot.models import BotConfig
from crypto_bot.paper_wallet import PaperWallet
from crypto_bot.realtime import RealtimePaperRunner


def _common_overrides_from_args(args: argparse.Namespace) -> dict:
    return {
        "symbol": args.symbol,
        "mode": args.mode,
        "exchange_provider": args.exchange_provider,
        "exchange_testnet": args.exchange_testnet,
        "dry_run_live": args.dry_run_live,
        "risk_per_trade": args.risk_per_trade,
        "stop_loss_pct": args.stop_loss_pct,
        "take_profit_pct": args.take_profit_pct,
        "initial_cash": args.initial_cash,
        "enable_llm_log_analysis": args.enable_llm_log_analysis,
    }


def _load_config(args: argparse.Namespace) -> BotConfig:
    env_path = Path(args.env_file)
    apply_env_to_process(load_env_file(env_path))

    base = load_json_config(args.config)
    return build_bot_config(base, _common_overrides_from_args(args))


def cmd_backtest(args: argparse.Namespace) -> None:
    config = _load_config(args)
    config.mode = "paper"
    candles = list(CsvMarketDataFeed(args.csv).candles())
    engine = TradingEngine(config)
    result = engine.run(candles)

    print("=== CLI Backtest ===")
    print(f"Mode: {config.mode} | Provider: {config.exchange_provider} | Testnet: {config.exchange_testnet}")
    print(f"Symbol: {config.symbol} | Trades: {result.trade_count} | WinRate: {result.win_rate_pct:.2f}%")
    print(f"Final Equity: {result.final_equity:.2f} | Return: {result.total_return_pct:.2f}%")
    print(f"MaxDD: {result.max_drawdown_pct:.2f}% | Fees: {result.total_fees_paid:.2f}")


def cmd_realtime(args: argparse.Namespace) -> None:
    config = _load_config(args)
    config.mode = "paper"
    runner = RealtimePaperRunner(config)
    candles = CsvMarketDataFeed(args.csv).candles()

    print("=== Realtime Paper Replay (WS-ready runner) ===")
    print(f"Symbol: {config.symbol} | Speed: {args.speed}s | Max steps: {args.max_steps or 'all'}")

    def on_event(event) -> None:
        if args.only_actions and event.signal == "HOLD" and not event.note:
            return
        print(
            f"[{event.ts}] price={event.price:.2f} signal={event.signal:<4} "
            f"equity={event.equity:.2f} pos_open={event.position_open} note={event.note}"
        )

    runner.run(candles, speed=args.speed, on_event=on_event, max_steps=args.max_steps)
    print("--- Replay Finished ---")
    print(f"Closed trades: {len(runner.wallet.closed_trades)} | Cash: {runner.wallet.cash:.2f}")


def cmd_live_demo(args: argparse.Namespace) -> None:
    config = _load_config(args)
    config.mode = "live"
    if config.dry_run_live is False and not args.allow_send_orders:
        print("Refusing to send test/live orders without --allow-send-orders")
        return
    if config.dry_run_live is False and config.exchange_testnet is False and not args.allow_mainnet_live:
        print("Refusing mainnet live order send without --allow-mainnet-live")
        return
    wallet = PaperWallet(cash=config.initial_cash, fee_rate=config.fee_rate)
    executor = build_order_executor(config, wallet)

    print("=== Live Executor Demo (Dry-run recommended) ===")
    print(
        f"Provider={config.exchange_provider} testnet={config.exchange_testnet} dry_run_live={config.dry_run_live}"
    )
    from datetime import datetime

    now = datetime.utcnow()
    demo_price = float(args.demo_price)
    demo_qty = float(args.demo_qty)
    demo_notional = demo_price * demo_qty
    if demo_notional > args.max_demo_notional:
        print(
            f"Refusing demo order: notional {demo_notional:.2f} exceeds cap {args.max_demo_notional:.2f}. "
            "Use --max-demo-notional to raise intentionally."
        )
        return
    executor.place_market_buy(
        now,
        price=demo_price,
        qty=demo_qty,
        stop_loss_price=demo_price * 0.985,
        take_profit_price=demo_price * 1.03,
    )
    executor.place_market_sell_all(now, price=demo_price * 1.01, reason="demo")


def cmd_analyze(args: argparse.Namespace) -> None:
    config = _load_config(args)
    config.mode = "paper"
    candles = list(CsvMarketDataFeed(args.csv).candles())
    engine = TradingEngine(config)
    result = engine.run(candles)
    log_path = write_trade_log_jsonl(engine.wallet.closed_trades, ROOT / "logs" / "trades.jsonl")

    analyzer = GroqTradeLogAnalyzer(api_key=config.groq_api_key, model=config.groq_model)
    analysis = analyzer.analyze(engine.wallet.closed_trades)
    print("=== CLI Analyze ===")
    print(f"Final Equity: {result.final_equity:.2f} | Return: {result.total_return_pct:.2f}%")
    print(f"Log file: {log_path}")
    print(f"Provider: {analysis.provider} ({analysis.mode})")
    print(analysis.text)


def cmd_preflight(args: argparse.Namespace) -> None:
    config = _load_config(args)
    print("=== Exchange Preflight ===")
    print(f"Mode: {config.mode} | Provider: {config.exchange_provider} | Testnet: {config.exchange_testnet}")
    print(f"Dry Run Live: {config.dry_run_live}")
    print(f"Symbol/TF: {config.symbol} / {config.timeframe}")
    print(f"Risk per trade: {config.risk_per_trade} | SL/TP: {config.stop_loss_pct}/{config.take_profit_pct}")
    print(f"Exchange key present: {'yes' if bool(config.exchange_api_key) else 'no'}")
    print(f"Exchange secret present: {'yes' if bool(config.exchange_api_secret) else 'no'}")
    if config.mode == "live" and not config.dry_run_live and config.exchange_testnet and not (
        config.exchange_api_key and config.exchange_api_secret
    ):
        print("WARNING: Testnet live send selected but API credentials are missing.")
    if config.mode == "live" and not config.dry_run_live and not config.exchange_testnet:
        print("WARNING: Mainnet live sending selected. Use very small size and double-check keys.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crypto Bot MVP CLI")
    parser.add_argument("--config", default=str(ROOT / "config" / "default.json"))
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--csv", default=str(ROOT / "data" / "sample_ohlcv.csv"))
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--mode", default=None, choices=["paper", "live"])
    parser.add_argument("--exchange-provider", default=None, choices=["binance", "bybit"])
    parser.add_argument("--exchange-testnet", dest="exchange_testnet", action="store_true")
    parser.add_argument("--no-exchange-testnet", dest="exchange_testnet", action="store_false")
    parser.set_defaults(exchange_testnet=None)
    parser.add_argument("--dry-run-live", dest="dry_run_live", action="store_true")
    parser.add_argument("--no-dry-run-live", dest="dry_run_live", action="store_false")
    parser.set_defaults(dry_run_live=None)
    parser.add_argument("--risk-per-trade", type=float, default=None)
    parser.add_argument("--stop-loss-pct", type=float, default=None)
    parser.add_argument("--take-profit-pct", type=float, default=None)
    parser.add_argument("--initial-cash", type=float, default=None)
    parser.add_argument("--enable-llm-log-analysis", action="store_true", default=None)

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backtest = sub.add_parser("backtest", help="Run batch backtest from CSV")
    p_backtest.set_defaults(func=cmd_backtest)

    p_realtime = sub.add_parser("realtime", help="Replay CSV as realtime paper stream")
    p_realtime.add_argument("--speed", type=float, default=0.0, help="Seconds between candles")
    p_realtime.add_argument("--max-steps", type=int, default=50)
    p_realtime.add_argument("--only-actions", action="store_true")
    p_realtime.set_defaults(func=cmd_realtime)

    p_live = sub.add_parser("live-demo", help="Exercise Binance/Bybit live executors in dry-run")
    p_live.add_argument("--allow-send-orders", action="store_true", help="Required when --no-dry-run-live is set")
    p_live.add_argument(
        "--allow-mainnet-live",
        action="store_true",
        help="Required when --no-dry-run-live and --no-exchange-testnet are both set",
    )
    p_live.add_argument("--demo-price", type=float, default=100000.0)
    p_live.add_argument("--demo-qty", type=float, default=0.01)
    p_live.add_argument("--max-demo-notional", type=float, default=2000.0)
    p_live.set_defaults(func=cmd_live_demo)

    p_analyze = sub.add_parser("analyze", help="Run backtest and analyze trade logs (Groq optional)")
    p_analyze.set_defaults(func=cmd_analyze)

    p_preflight = sub.add_parser("preflight", help="Validate config/env before testnet or live actions")
    p_preflight.set_defaults(func=cmd_preflight)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
