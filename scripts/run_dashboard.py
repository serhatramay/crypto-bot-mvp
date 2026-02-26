from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.config import apply_env_to_process, build_bot_config, load_env_file, load_json_config
from crypto_bot.dashboard import DashboardServer, DashboardState
from crypto_bot.exchange import CsvMarketDataFeed
from crypto_bot.realtime import RealtimePaperRunner


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run local dashboard with replayed paper bot")
    p.add_argument("--config", default=str(ROOT / "config" / "default.json"))
    p.add_argument("--env-file", default=str(ROOT / ".env"))
    p.add_argument("--csv", default=str(ROOT / "data" / "sample_ohlcv.csv"))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--speed", type=float, default=0.05)
    p.add_argument("--max-steps", type=int, default=200)
    p.add_argument("--hold-seconds", type=int, default=20, help="Keep server alive after replay finishes")
    return p


def main() -> None:
    args = build_parser().parse_args()
    apply_env_to_process(load_env_file(args.env_file))
    config = build_bot_config(load_json_config(args.config), {"mode": "paper"})

    state = DashboardState()
    server = DashboardServer(args.host, args.port, state)
    server.start()
    state.set_status("running")

    runner = RealtimePaperRunner(config)
    candles = CsvMarketDataFeed(args.csv).candles()

    def replay() -> None:
        try:
            runner.run(candles, speed=args.speed, max_steps=args.max_steps, on_event=lambda e: state.update_from_runner(runner, e))
            state.set_status("replay_finished")
        except Exception as exc:
            state.set_status(f"error: {exc}")

    t = threading.Thread(target=replay, daemon=True)
    t.start()

    print(f"Dashboard running: http://{args.host}:{args.port}")
    print(f"API state: http://{args.host}:{args.port}/api/state")
    print(f"Replay settings: speed={args.speed}s max_steps={args.max_steps}")

    try:
        if args.hold_seconds > 0:
            end = time.time() + args.hold_seconds
            while time.time() < end:
                time.sleep(0.5)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        try:
            server.stop()
        except KeyboardInterrupt:
            pass
        print("Dashboard stopped.")


if __name__ == "__main__":
    main()
