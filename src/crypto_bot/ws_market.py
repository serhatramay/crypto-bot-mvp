from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable
from urllib import parse, request

from .models import Candle

try:
    import websocket  # type: ignore
except ImportError:  # pragma: no cover
    websocket = None


def _require_ws_client() -> None:
    if websocket is None:
        raise RuntimeError(
            "Missing dependency 'websocket-client'. Install with: pip install websocket-client"
        )


class BinanceKlineStream:
    def __init__(self, symbol: str, interval: str, on_candle: Callable[[Candle], None]) -> None:
        self.symbol = symbol.lower()
        self.interval = interval
        self.on_candle = on_candle
        self.ws_app = None

    def _url(self) -> str:
        return f"wss://stream.binance.com:9443/ws/{self.symbol}@kline_{self.interval}"

    def _on_message(self, _ws, message: str) -> None:
        data = json.loads(message)
        k = data.get("k", {})
        if not k.get("x"):
            return  # only closed candles
        ts_ms = int(k["t"])
        self.on_candle(
            Candle(
                ts=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
                open=float(k["o"]),
                high=float(k["h"]),
                low=float(k["l"]),
                close=float(k["c"]),
                volume=float(k.get("v", 0.0)),
            )
        )

    def run_forever(self) -> None:
        _require_ws_client()
        self.ws_app = websocket.WebSocketApp(self._url(), on_message=self._on_message)  # type: ignore[attr-defined]
        self.ws_app.run_forever()


class BybitKlineStream:
    def __init__(self, symbol: str, interval: str, on_candle: Callable[[Candle], None], testnet: bool = True) -> None:
        self.symbol = symbol.upper()
        self.interval = interval
        self.on_candle = on_candle
        self.base = "wss://stream-testnet.bybit.com/v5/public/spot" if testnet else "wss://stream.bybit.com/v5/public/spot"
        self.ws_app = None

    def _topic(self) -> str:
        bybit_interval = self.interval.replace("m", "") if self.interval.endswith("m") else self.interval
        return f"kline.{bybit_interval}.{self.symbol}"

    def _on_open(self, ws) -> None:
        ws.send(json.dumps({"op": "subscribe", "args": [self._topic()]}))

    def _on_message(self, _ws, message: str) -> None:
        data = json.loads(message)
        items = data.get("data") or []
        for item in items:
            if not item.get("confirm"):
                continue
            ts_ms = int(item["start"])
            self.on_candle(
                Candle(
                    ts=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item.get("volume", 0.0)),
                )
            )

    def run_forever(self) -> None:
        _require_ws_client()
        self.ws_app = websocket.WebSocketApp(  # type: ignore[attr-defined]
            self.base,
            on_open=self._on_open,
            on_message=self._on_message,
        )
        self.ws_app.run_forever()


def build_public_kline_stream(
    provider: str,
    symbol: str,
    interval: str,
    on_candle: Callable[[Candle], None],
    testnet: bool = True,
):
    normalized = provider.lower()
    if normalized == "binance":
        return BinanceKlineStream(symbol=symbol, interval=interval, on_candle=on_candle)
    if normalized == "bybit":
        return BybitKlineStream(symbol=symbol, interval=interval, on_candle=on_candle, testnet=testnet)
    raise ValueError(f"Unsupported WS provider: {provider}")


def _binance_rest_base(testnet: bool) -> str:
    return "https://testnet.binance.vision" if testnet else "https://api.binance.com"


def _bybit_interval(interval: str) -> str:
    x = interval.lower()
    if x.endswith("m"):
        return x[:-1]
    if x.endswith("h"):
        return str(int(x[:-1]) * 60)
    if x == "1d":
        return "D"
    if x == "1w":
        return "W"
    return interval


def fetch_public_klines(
    provider: str,
    symbol: str,
    interval: str,
    limit: int = 50,
    testnet: bool = True,
    timeout: int = 10,
) -> list[Candle]:
    normalized = provider.lower()
    if normalized == "binance":
        qs = parse.urlencode({"symbol": symbol.upper(), "interval": interval, "limit": max(1, min(limit, 1000))})
        url = f"{_binance_rest_base(testnet)}/api/v3/klines?{qs}"
        with request.urlopen(url, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        candles: list[Candle] = []
        for r in rows:
            candles.append(
                Candle(
                    ts=datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc).replace(tzinfo=None),
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]),
                )
            )
        return candles

    if normalized == "bybit":
        qs = parse.urlencode(
            {
                "category": "spot",
                "symbol": symbol.upper(),
                "interval": _bybit_interval(interval),
                "limit": max(1, min(limit, 1000)),
            }
        )
        base = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
        url = f"{base}/v5/market/kline?{qs}"
        with request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        rows = (payload.get("result") or {}).get("list") or []
        candles = []
        for r in rows:
            # Bybit often returns reverse-chronological strings
            candles.append(
                Candle(
                    ts=datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc).replace(tzinfo=None),
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]),
                )
            )
        candles.sort(key=lambda c: c.ts)
        return candles

    raise ValueError(f"Unsupported provider for REST klines: {provider}")
