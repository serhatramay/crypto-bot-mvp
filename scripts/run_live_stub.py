from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.execution import build_order_executor
from crypto_bot.models import BotConfig
from crypto_bot.paper_wallet import PaperWallet


def main() -> None:
    config = BotConfig(symbol="BTCUSDT", mode="live")
    wallet = PaperWallet(cash=config.initial_cash, fee_rate=config.fee_rate)
    executor = build_order_executor(config, wallet)

    now = datetime.utcnow()
    print("=== Live Stub Demo (No Real Orders) ===")
    executor.place_market_buy(
        now,
        price=100000.0,
        qty=0.01,
        stop_loss_price=98500.0,
        take_profit_price=103000.0,
    )
    executor.place_market_sell_all(now, price=101200.0, reason="signal")
    print("Stub complete. Gercek borsa entegrasyonu icin LiveExchangeExecutor icini dolduracagiz.")


if __name__ == "__main__":
    main()
