from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crypto_bot.data_utils import generate_sample_ohlcv_csv


if __name__ == "__main__":
    out = generate_sample_ohlcv_csv(ROOT / "data" / "sample_ohlcv.csv")
    print(f"Sample data generated: {out}")
