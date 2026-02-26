from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.config import apply_env_to_process, build_bot_config, load_env_file, load_json_config
from crypto_bot.dashboard import DashboardServer, DashboardState
from crypto_bot.journal import append_trade_log_jsonl
from crypto_bot.realtime import RealtimePaperRunner
from crypto_bot.ws_market import build_public_kline_stream, fetch_public_klines


# Coin configurations
COINS = {
    "BTC": {"symbol": "BTCUSDT", "config": "btc-volatile.json"},
    "ETH": {"symbol": "ETHUSDT", "config": "eth-volatile.json"},
    "SOL": {"symbol": "SOLUSDT", "config": "sol-volatile.json"},
    "XRP": {"symbol": "XRPUSDT", "config": "xrp-volatile.json"},
}


class MultiCoinDashboardState:
    """Extended dashboard state that tracks multiple coins."""
    
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {
            "status": "idle",
            "context": {"provider": "binance", "timeframe": "1m"},
            "latest_event": None,
            "metrics": {
                "equity": 0.0,
                "cash": 0.0,
                "position_open": False,
                "closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "total_net_pnl": 0.0,
            },
            "recent_events": [],
            "recent_trades": [],
            "open_position": None,
            "coins": {},
        }
        # Initialize coins
        for coin in COINS.keys():
            self._data["coins"][coin] = {
                "price": 0.0,
                "signal": "HOLD",
                "change": 0.0,
                "equity": 5000.0,
                "trades": 0,
                "position_open": False,
                "last_update": None,
            }
    
    def update_coin(self, coin: str, price: float, signal: str, equity: float, 
                    trades: int, position_open: bool, change: float = 0.0) -> None:
        with self._lock:
            self._data["coins"][coin] = {
                "price": price,
                "signal": signal,
                "change": change,
                "equity": equity,
                "trades": trades,
                "position_open": position_open,
                "last_update": datetime.now(timezone.utc).isoformat(),
            }
    
    def set_status(self, status: str) -> None:
        with self._lock:
            self._data["status"] = status
    
    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))


def run_coin_bot(coin: str, coin_config: dict, state: MultiCoinDashboardState, 
                 provider: str, testnet: bool, warmup_candles: int, only_actions: bool):
    """Run a single coin bot in a separate thread."""
    
    config_path = ROOT / "config" / coin_config["config"]
    config = build_bot_config(load_json_config(config_path), {
        "mode": "paper",
        "exchange_provider": provider,
        "exchange_testnet": testnet,
        "symbol": coin_config["symbol"],
        "timeframe": "1m",
    })
    
    runner = RealtimePaperRunner(config)
    last_logged_trade_count = 0
    last_seen_ts = None
    initial_price = None
    
    log_file = ROOT / "logs" / f"{coin.lower()}-trades.jsonl"
    
    def handle_candle(candle, source: str = "ws") -> None:
        nonlocal last_logged_trade_count, last_seen_ts, initial_price
        
        if last_seen_ts is not None and candle.ts <= last_seen_ts:
            return
        last_seen_ts = candle.ts
        
        if initial_price is None:
            initial_price = candle.close
        
        event = runner.process_candle(candle)
        
        # Calculate change %
        change = ((candle.close - initial_price) / initial_price * 100) if initial_price else 0
        
        # Update dashboard state
        state.update_coin(
            coin=coin,
            price=candle.close,
            signal=event.signal,
            equity=event.equity,
            trades=len(runner.wallet.closed_trades),
            position_open=runner.wallet.position.is_open,
            change=change,
        )
        
        # Log trades
        if len(runner.wallet.closed_trades) > last_logged_trade_count:
            new_trades = runner.wallet.closed_trades[last_logged_trade_count:]
            append_trade_log_jsonl(new_trades, str(log_file))
            last_logged_trade_count = len(runner.wallet.closed_trades)
        
        if not (only_actions and event.signal == "HOLD" and not event.note):
            print(f"[{coin}:{event.ts}] price={event.price:.2f} signal={event.signal:<4} equity={event.equity:.2f}")
    
    # Warmup
    if warmup_candles > 0:
        try:
            warmup = fetch_public_klines(
                provider=provider,
                symbol=coin_config["symbol"],
                interval="1m",
                limit=warmup_candles,
                testnet=testnet,
            )
            print(f"[{coin}] Warmup: {len(warmup)} candles")
            for candle in warmup:
                handle_candle(candle, source="warmup")
        except Exception as exc:
            print(f"[{coin}] Warmup failed: {exc}")
    
    # Start WebSocket stream
    stream = build_public_kline_stream(
        provider=provider,
        symbol=coin_config["symbol"],
        interval="1m",
        on_candle=lambda candle: handle_candle(candle, source="ws"),
        testnet=testnet,
    )
    
    try:
        stream.run_forever()
    except Exception as exc:
        print(f"[{coin}] Stream error: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Multi-coin dashboard with 4 bots")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--testnet", action="store_true", default=False)
    parser.add_argument("--mainnet", dest="testnet", action="store_false")
    parser.add_argument("--only-actions", action="store_true")
    parser.add_argument("--warmup-candles", type=int, default=10)
    args = parser.parse_args()
    
    apply_env_to_process(load_env_file(ROOT / ".env"))
    
    # Create multi-coin state
    state = MultiCoinDashboardState()
    state.set_status("starting_4_coins")
    
    # Start dashboard server
    server = DashboardServer(args.host, args.port, state)
    server.start()
    
    print(f"🚀 Multi-Coin Dashboard: http://{args.host}:{args.port}")
    print(f"📊 Tracking: BTC, ETH, SOL, XRP")
    print("Press Ctrl+C to stop\n")
    
    # Start 4 coin bots in separate threads
    threads = []
    for coin, coin_config in COINS.items():
        t = threading.Thread(
            target=run_coin_bot,
            args=(coin, coin_config, state, "binance", args.testnet, 
                  args.warmup_candles, args.only_actions),
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(1)  # Stagger starts
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        state.set_status("stopped")
        server.stop()


if __name__ == "__main__":
    main()
