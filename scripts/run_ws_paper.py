from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.config import apply_env_to_process, build_bot_config, load_env_file, load_json_config
from crypto_bot.realtime import RealtimePaperRunner
from crypto_bot.ws_market import build_public_kline_stream, fetch_public_klines


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run paper bot on real public WebSocket kline stream")
    p.add_argument("--config", default=str(ROOT / "config" / "default.json"))
    p.add_argument("--env-file", default=str(ROOT / ".env"))
    p.add_argument("--provider", default="binance", choices=["binance", "bybit"])
    p.add_argument("--symbol", default=None)
    p.add_argument("--interval", default=None, help="e.g. 1m, 5m")
    p.add_argument("--testnet", action="store_true", default=True)
    p.add_argument("--mainnet", dest="testnet", action="store_false")
    p.add_argument("--only-actions", action="store_true")
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
    runner = RealtimePaperRunner(config)

    print("=== WS Paper Bot ===")
    print(
        f"provider={config.exchange_provider} symbol={config.symbol} interval={config.timeframe} testnet={config.exchange_testnet}"
    )
    print("Press Ctrl+C to stop. Requires: pip install websocket-client")
    last_seen_ts = None

    def on_candle(candle, source: str = "ws") -> None:
        nonlocal last_seen_ts
        if last_seen_ts is not None and candle.ts <= last_seen_ts:
            return
        last_seen_ts = candle.ts
        event = runner.process_candle(candle)
        if args.only_actions and event.signal == "HOLD" and not event.note:
            return
        print(
            f"[{source}:{event.ts}] price={event.price:.2f} signal={event.signal} equity={event.equity:.2f} note={event.note}"
        )

    if args.warmup_candles > 0:
        try:
            warmup = fetch_public_klines(
                provider=config.exchange_provider,
                symbol=config.symbol,
                interval=config.timeframe,
                limit=args.warmup_candles,
                testnet=config.exchange_testnet,
            )
            print(f"Warmup fetched: {len(warmup)} candles")
            for candle in warmup:
                on_candle(candle, source="warmup")
        except Exception as exc:
            print(f"Warmup failed, continuing without preload: {exc}")

    stream = build_public_kline_stream(
        provider=config.exchange_provider,
        symbol=config.symbol,
        interval=config.timeframe,
        on_candle=lambda candle: on_candle(candle, source="ws"),
        testnet=config.exchange_testnet,
    )
    stream.run_forever()


if __name__ == "__main__":
    main()
