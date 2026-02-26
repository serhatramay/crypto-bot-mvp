from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.config import apply_env_to_process, build_bot_config, load_env_file, load_json_config
from crypto_bot.dashboard import DashboardServer, DashboardState
from crypto_bot.journal import append_trade_log_jsonl
from crypto_bot.realtime import RealtimePaperRunner
from crypto_bot.ws_market import build_public_kline_stream, fetch_public_klines


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run local dashboard with real public WS market data (paper trading)")
    p.add_argument("--config", default=str(ROOT / "config" / "default.json"))
    p.add_argument("--env-file", default=str(ROOT / ".env"))
    p.add_argument("--provider", default="binance", choices=["binance", "bybit"])
    p.add_argument("--symbol", default=None)
    p.add_argument("--interval", default=None, help="e.g. 1m, 5m")
    p.add_argument("--testnet", action="store_true", default=True)
    p.add_argument("--mainnet", dest="testnet", action="store_false")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--only-actions", action="store_true")
    p.add_argument("--log-file", default=str(ROOT / "logs" / "ws_paper_trades.jsonl"))
    p.add_argument("--warmup-candles", type=int, default=50)
    return p


def main() -> None:
    args = build_parser().parse_args()
    apply_env_to_process(load_env_file(args.env_file))

    overrides = {
        "mode": "paper",
        "exchange_provider": args.provider,
        "exchange_testnet": args.testnet,
        "symbol": args.symbol,
        "timeframe": args.interval,
    }
    config = build_bot_config(load_json_config(args.config), overrides)

    state = DashboardState()
    state.set_status(
        f"connecting_ws provider={config.exchange_provider} symbol={config.symbol} tf={config.timeframe}"
    )
    server = DashboardServer(args.host, args.port, state)
    server.start()

    runner = RealtimePaperRunner(config)
    last_logged_trade_count = 0
    last_seen_ts = None

    print(f"Dashboard running: http://{args.host}:{args.port}")
    print(f"API state: http://{args.host}:{args.port}/api/state")
    print(
        f"WS source: provider={config.exchange_provider} symbol={config.symbol} interval={config.timeframe} testnet={config.exchange_testnet}"
    )
    print("Paper trading only. No real orders are sent.")
    print("Requires websocket-client: pip install websocket-client")
    print("Press Ctrl+C to stop.")

    def handle_candle(candle, source: str = "ws") -> None:
        nonlocal last_logged_trade_count, last_seen_ts
        if last_seen_ts is not None and candle.ts <= last_seen_ts:
            return
        last_seen_ts = candle.ts
        event = runner.process_candle(candle)
        state.set_status(
            f"streaming provider={config.exchange_provider} symbol={config.symbol}"
        )
        state.update_from_runner(runner, event)
        if len(runner.wallet.closed_trades) > last_logged_trade_count:
            new_trades = runner.wallet.closed_trades[last_logged_trade_count:]
            append_trade_log_jsonl(new_trades, args.log_file)
            last_logged_trade_count = len(runner.wallet.closed_trades)
        if args.only_actions and event.signal == "HOLD" and not event.note:
            return
        print(
            f"[{source}:{event.ts}] price={event.price:.2f} signal={event.signal:<4} equity={event.equity:.2f} note={event.note}"
        )

    if args.warmup_candles > 0:
        try:
            state.set_status(
                f"warming_up provider={config.exchange_provider} symbol={config.symbol} candles={args.warmup_candles}"
            )
            warmup = fetch_public_klines(
                provider=config.exchange_provider,
                symbol=config.symbol,
                interval=config.timeframe,
                limit=args.warmup_candles,
                testnet=config.exchange_testnet,
            )
            print(f"Warmup fetched: {len(warmup)} candles")
            for candle in warmup:
                handle_candle(candle, source="warmup")
        except Exception as exc:
            print(f"Warmup failed, continuing without preload: {exc}")

    stream = build_public_kline_stream(
        provider=config.exchange_provider,
        symbol=config.symbol,
        interval=config.timeframe,
        on_candle=lambda candle: handle_candle(candle, source="ws"),
        testnet=config.exchange_testnet,
    )

    try:
        stream.run_forever()
    except KeyboardInterrupt:
        state.set_status("stopped")
        print("Stopping...")
    finally:
        try:
            server.stop()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
