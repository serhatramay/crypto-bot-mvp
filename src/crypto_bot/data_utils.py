from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate_sample_ohlcv_csv(path: str | Path, rows: int = 500, start_price: float = 100000.0) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime(2026, 1, 1, 9, 0, 0)
    price = start_price
    rng = random.Random(42)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])

        for i in range(rows):
            drift = math.sin(i / 18) * 120
            shock = rng.uniform(-180, 180)
            delta = drift + shock
            open_p = price
            close_p = max(1.0, price + delta)
            high_p = max(open_p, close_p) + abs(rng.uniform(10, 80))
            low_p = min(open_p, close_p) - abs(rng.uniform(10, 80))
            volume = rng.uniform(0.1, 5.0)

            writer.writerow([
                ts.isoformat(),
                f"{open_p:.2f}",
                f"{high_p:.2f}",
                f"{low_p:.2f}",
                f"{close_p:.2f}",
                f"{volume:.4f}",
            ])
            ts += timedelta(minutes=5)
            price = close_p

    return path
