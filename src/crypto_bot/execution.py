from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import hashlib
import hmac
import json
import math
import random
import time
from urllib import error, parse, request

from .models import BotConfig
from .paper_wallet import PaperWallet


class OrderExecutor(ABC):
    @abstractmethod
    def place_market_buy(
        self,
        ts: datetime,
        price: float,
        qty: float,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def place_market_sell_all(self, ts: datetime, price: float, reason: str = "signal") -> bool:
        raise NotImplementedError


class PaperOrderExecutor(OrderExecutor):
    def __init__(self, wallet: PaperWallet, config: BotConfig) -> None:
        self.wallet = wallet
        self.config = config
        self.symbol = config.symbol
        self.rng = random.Random(config.paper_random_seed)

    def _round_price(self, price: float) -> float:
        tick = self.config.paper_tick_size
        if tick <= 0:
            return price
        return round(round(price / tick) * tick, 8)

    def _round_qty(self, qty: float) -> float:
        step = self.config.paper_qty_step
        if step <= 0:
            return qty
        stepped = math.floor(qty / step) * step
        return round(max(0.0, stepped), 12)

    def _apply_fill_price(self, price: float, side: str) -> float:
        spread = self.config.paper_spread_bps / 10000.0
        slippage = self.config.paper_slippage_bps / 10000.0
        if side == "BUY":
            adjusted = price * (1 + (spread / 2) + slippage)
        else:
            adjusted = price * (1 - (spread / 2) - slippage)
        return self._round_price(adjusted)

    def _apply_partial_fill(self, qty: float) -> float:
        if qty <= 0:
            return 0.0
        prob = self.config.paper_partial_fill_probability
        if prob <= 0 or self.rng.random() >= prob:
            return self._round_qty(qty)
        min_ratio = min(max(self.config.paper_partial_fill_min_ratio, 0.05), 1.0)
        ratio = self.rng.uniform(min_ratio, 0.99)
        return self._round_qty(qty * ratio)

    def place_market_buy(
        self,
        ts: datetime,
        price: float,
        qty: float,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
    ) -> bool:
        exec_price = self._apply_fill_price(price, "BUY")
        exec_qty = self._apply_partial_fill(qty)
        if exec_qty <= 0:
            return False
        # Keep SL/TP relative to the actual fill.
        sl_pct = ((price - stop_loss_price) / price) if (price > 0 and stop_loss_price > 0) else 0.0
        tp_pct = ((take_profit_price - price) / price) if (price > 0 and take_profit_price > 0) else 0.0
        adjusted_sl = self._round_price(exec_price * (1 - sl_pct)) if sl_pct > 0 else 0.0
        adjusted_tp = self._round_price(exec_price * (1 + tp_pct)) if tp_pct > 0 else 0.0
        return self.wallet.buy(
            ts,
            exec_price,
            exec_qty,
            stop_loss_price=adjusted_sl,
            take_profit_price=adjusted_tp,
        )

    def place_market_sell_all(self, ts: datetime, price: float, reason: str = "signal") -> bool:
        if not self.wallet.position.is_open:
            return False
        exec_price = self._apply_fill_price(price, "SELL")
        desired_qty = self.wallet.position.qty
        exec_qty = self._apply_partial_fill(desired_qty)
        if exec_qty <= 0:
            return False
        if exec_qty >= desired_qty - 1e-12:
            return self.wallet.sell_all(ts, exec_price, reason=reason)
        return self.wallet.sell_qty(ts, exec_price, exec_qty, reason=f"{reason}_partial")


class BaseHttpExchangeExecutor(OrderExecutor):
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.symbol = config.symbol
        self.dry_run_live = config.dry_run_live
        self._tracked_position_qty = 0.0

    def place_market_buy(
        self,
        ts: datetime,
        price: float,
        qty: float,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
    ) -> bool:
        return self._place_market_order(
            side="BUY",
            ts=ts,
            price=price,
            qty=qty,
            reason="signal",
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
        )

    def place_market_sell_all(self, ts: datetime, price: float, reason: str = "signal") -> bool:
        return self._place_market_order(
            side="SELL",
            ts=ts,
            price=price,
            qty=self._tracked_position_qty,
            reason=reason,
        )

    def _place_market_order(
        self,
        side: str,
        ts: datetime,
        price: float,
        qty: float,
        reason: str,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
    ) -> bool:
        payload = self._build_payload(side=side, qty=qty)
        meta = {
            "ts": ts.isoformat(),
            "approx_price": round(price, 8),
            "reason": reason,
            "stop_loss_price": round(stop_loss_price, 8) if stop_loss_price else 0.0,
            "take_profit_price": round(take_profit_price, 8) if take_profit_price else 0.0,
        }

        if self.dry_run_live:
            print(f"[{self.__class__.__name__}][DRY-RUN] {side} {self.symbol} payload={payload} meta={meta}")
            if side == "BUY" and qty > 0:
                self._tracked_position_qty = qty
            elif side == "SELL":
                self._tracked_position_qty = 0.0
            return True

        if not self.config.exchange_api_key or not self.config.exchange_api_secret:
            print(f"[{self.__class__.__name__}] Missing exchange API credentials. Order skipped.")
            return False

        try:
            response = self._send_signed_order(payload)
            print(f"[{self.__class__.__name__}] order response={response}")
            if side == "BUY" and qty > 0:
                self._tracked_position_qty = qty
            elif side == "SELL":
                self._tracked_position_qty = 0.0
            return True
        except Exception as exc:
            print(f"[{self.__class__.__name__}] order failed: {exc}")
            return False

    @abstractmethod
    def _build_payload(self, side: str, qty: float) -> dict:
        raise NotImplementedError

    @abstractmethod
    def _send_signed_order(self, payload: dict) -> dict:
        raise NotImplementedError


class BinanceSpotTestnetExecutor(BaseHttpExchangeExecutor):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self.base_url = "https://testnet.binance.vision" if config.exchange_testnet else "https://api.binance.com"

    def _build_payload(self, side: str, qty: float) -> dict:
        payload = {
            "symbol": self.symbol,
            "side": side,
            "type": "MARKET",
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
        }
        if qty > 0:
            payload["quantity"] = f"{qty:.6f}"
        return payload

    def _send_signed_order(self, payload: dict) -> dict:
        query = parse.urlencode(payload)
        signature = hmac.new(
            self.config.exchange_api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        full_query = f"{query}&signature={signature}"
        req = request.Request(
            f"{self.base_url}/api/v3/order",
            data=full_query.encode("utf-8"),
            headers={"X-MBX-APIKEY": self.config.exchange_api_key},
            method="POST",
        )
        with request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))


class BybitV5TestnetExecutor(BaseHttpExchangeExecutor):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(config)
        self.base_url = "https://api-testnet.bybit.com" if config.exchange_testnet else "https://api.bybit.com"

    def _build_payload(self, side: str, qty: float) -> dict:
        return {
            "category": "spot",
            "symbol": self.symbol,
            "side": side.title(),
            "orderType": "Market",
            "qty": f"{qty:.6f}" if qty > 0 else "0",
        }

    def _send_signed_order(self, payload: dict) -> dict:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        body = json.dumps(payload, separators=(",", ":"))
        prehash = timestamp + self.config.exchange_api_key + recv_window + body
        signature = hmac.new(
            self.config.exchange_api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        req = request.Request(
            f"{self.base_url}/v5/order/create",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-BAPI-API-KEY": self.config.exchange_api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": signature,
            },
            method="POST",
        )
        with request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))


class LiveExchangeExecutor(OrderExecutor):
    """Delegates to a provider-specific executor (Binance/Bybit)."""

    def __init__(self, delegate: BaseHttpExchangeExecutor) -> None:
        self.delegate = delegate

    def place_market_buy(
        self,
        ts: datetime,
        price: float,
        qty: float,
        stop_loss_price: float = 0.0,
        take_profit_price: float = 0.0,
    ) -> bool:
        return self.delegate.place_market_buy(ts, price, qty, stop_loss_price, take_profit_price)

    def place_market_sell_all(self, ts: datetime, price: float, reason: str = "signal") -> bool:
        return self.delegate.place_market_sell_all(ts, price, reason)


def build_order_executor(config: BotConfig, wallet: PaperWallet) -> OrderExecutor:
    normalized_mode = (config.mode or "paper").lower()
    if normalized_mode == "paper":
        return PaperOrderExecutor(wallet, config)

    if normalized_mode != "live":
        raise ValueError(f"Unsupported mode: {config.mode}")

    provider = (config.exchange_provider or "binance").lower()
    if provider == "binance":
        return LiveExchangeExecutor(BinanceSpotTestnetExecutor(config))
    if provider == "bybit":
        return LiveExchangeExecutor(BybitV5TestnetExecutor(config))
    raise ValueError(f"Unsupported exchange provider: {config.exchange_provider}")
