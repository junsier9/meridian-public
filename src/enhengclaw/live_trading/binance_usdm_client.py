from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BINANCE_USDM_MAINNET_BASE_URL = "https://fapi.binance.com"
BINANCE_USDM_TESTNET_BASE_URL = "https://demo-fapi.binance.com"
BINANCE_SPOT_MAINNET_BASE_URL = "https://api.binance.com"
UNKNOWN_EXECUTION_STATUS_MARKER = "Unknown error, please check your request or try again later."


class LiveOrderSubmissionDisabled(RuntimeError):
    pass


class TestnetOrderSubmissionGuard(RuntimeError):
    __test__ = False

    pass


class MainnetStrategyOrderGuard(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BinanceUsdmResponse:
    status_code: int
    headers: dict[str, str]
    payload: Any


@dataclass(frozen=True, slots=True)
class BinanceUsdmUnknownExecutionStatus(RuntimeError):
    method: str
    path: str
    detail: str

    def __str__(self) -> str:
        return f"Binance execution status unknown for {self.method} {self.path}: {self.detail}"


@dataclass(frozen=True, slots=True)
class BinanceUsdmRequestError(RuntimeError):
    method: str
    path: str
    status_code: int
    detail: str

    def __str__(self) -> str:
        return f"Binance request failed for {self.method} {self.path} with HTTP {self.status_code}: {self.detail}"


@dataclass(slots=True)
class BinanceUsdmClient:
    base_url: str = BINANCE_USDM_TESTNET_BASE_URL
    api_key: str | None = None
    api_secret: str | None = None
    recv_window_ms: int = 5000
    timeout_seconds: float = 10.0
    urlopen_fn: Callable[..., Any] | None = None
    time_ms_fn: Callable[[], int] | None = None

    def server_time(self) -> BinanceUsdmResponse:
        return self._request("GET", "/fapi/v1/time")

    def exchange_info(self) -> BinanceUsdmResponse:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> BinanceUsdmResponse:
        return self._request(
            "GET",
            "/fapi/v1/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "startTime": start_time,
                "endTime": end_time,
            },
        )

    def spot_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> BinanceUsdmResponse:
        """Binance SPOT klines (/api/v3/klines). The instance must be constructed with
        base_url=BINANCE_SPOT_MAINNET_BASE_URL; the response array layout matches the USDM
        klines payload, so klines_payload_to_frame parses it unchanged. Public, no key."""
        return self._request(
            "GET",
            "/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "startTime": start_time,
                "endTime": end_time,
            },
        )

    def premium_index(self, *, symbol: str) -> BinanceUsdmResponse:
        return self._request("GET", "/fapi/v1/premiumIndex", params={"symbol": symbol})

    def funding_rate_history(
        self,
        *,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> BinanceUsdmResponse:
        return self._request(
            "GET",
            "/fapi/v1/fundingRate",
            params={
                "symbol": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
        )

    def income_history(
        self,
        *,
        symbol: str | None = None,
        income_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> BinanceUsdmResponse:
        return self._request(
            "GET",
            "/fapi/v1/income",
            params={
                "symbol": symbol,
                "incomeType": income_type,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            },
            signed=True,
        )

    def account_information_v3(self) -> BinanceUsdmResponse:
        return self._request("GET", "/fapi/v3/account", signed=True)

    def account_config(self) -> BinanceUsdmResponse:
        return self._request("GET", "/fapi/v1/accountConfig", signed=True)

    def position_mode(self) -> BinanceUsdmResponse:
        return self._request("GET", "/fapi/v1/positionSide/dual", signed=True)

    def position_information_v2(self, *, symbol: str | None = None) -> BinanceUsdmResponse:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v2/positionRisk", params=params, signed=True)

    def current_all_open_orders(self, *, symbol: str | None = None) -> BinanceUsdmResponse:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def api_key_restrictions(self) -> BinanceUsdmResponse:
        return self._request("GET", "/sapi/v1/account/apiRestrictions", signed=True)

    def new_order_test(self, **params: Any) -> BinanceUsdmResponse:
        return self._request("POST", "/fapi/v1/order/test", params=params, signed=True)

    def new_order(self, **_: Any) -> BinanceUsdmResponse:
        raise LiveOrderSubmissionDisabled(
            "real Binance order submission is intentionally disabled in the Phase 1 scaffold"
        )

    def submit_manual_live_order_smoke(self, **params: Any) -> BinanceUsdmResponse:
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def submit_testnet_strategy_order(self, **params: Any) -> BinanceUsdmResponse:
        if self.base_url.rstrip("/") != BINANCE_USDM_TESTNET_BASE_URL:
            raise TestnetOrderSubmissionGuard(
                "strategy auto-order submission is only allowed against Binance USD-M testnet"
            )
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def submit_mainnet_strategy_single_run_order(self, **params: Any) -> BinanceUsdmResponse:
        if self.base_url.rstrip("/") != BINANCE_USDM_MAINNET_BASE_URL:
            raise MainnetStrategyOrderGuard(
                "mainnet strategy single-run order submission is only allowed against Binance USD-M mainnet"
            )
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def submit_mainnet_strategy_delta_order(self, **params: Any) -> BinanceUsdmResponse:
        if self.base_url.rstrip("/") != BINANCE_USDM_MAINNET_BASE_URL:
            raise MainnetStrategyOrderGuard(
                "mainnet strategy delta order submission is only allowed against Binance USD-M mainnet"
            )
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def submit_mainnet_reduce_only_order(self, **params: Any) -> BinanceUsdmResponse:
        if self.base_url.rstrip("/") != BINANCE_USDM_MAINNET_BASE_URL:
            raise MainnetStrategyOrderGuard(
                "mainnet reduce-only order submission is only allowed against Binance USD-M mainnet"
            )
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def change_margin_type(self, *, symbol: str, margin_type: str) -> BinanceUsdmResponse:
        return self._request(
            "POST",
            "/fapi/v1/marginType",
            params={"symbol": symbol, "marginType": margin_type},
            signed=True,
        )

    def change_initial_leverage(self, *, symbol: str, leverage: int) -> BinanceUsdmResponse:
        return self._request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol, "leverage": int(leverage)},
            signed=True,
        )

    def query_order(
        self,
        *,
        symbol: str,
        order_id: int | str | None = None,
        orig_client_order_id: str | None = None,
    ) -> BinanceUsdmResponse:
        params = _order_lookup_params(
            symbol=symbol,
            order_id=order_id,
            orig_client_order_id=orig_client_order_id,
        )
        return self._request("GET", "/fapi/v1/order", params=params, signed=True)

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | str | None = None,
        orig_client_order_id: str | None = None,
    ) -> BinanceUsdmResponse:
        params = _order_lookup_params(
            symbol=symbol,
            order_id=order_id,
            orig_client_order_id=orig_client_order_id,
        )
        return self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

    def sign_params(self, params: dict[str, Any]) -> dict[str, str]:
        if not self.api_secret:
            raise ValueError("api_secret is required for signed Binance USD-M requests")
        signed = {key: _stringify(value) for key, value in params.items() if value is not None}
        signed.setdefault("recvWindow", str(int(self.recv_window_ms)))
        signed.setdefault("timestamp", str(self._time_ms()))
        query = urlencode(signed)
        signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        signed["signature"] = signature
        return signed

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> BinanceUsdmResponse:
        normalized_method = method.upper()
        request_params = {key: _stringify(value) for key, value in dict(params or {}).items() if value is not None}
        if signed:
            request_params = self.sign_params(request_params)
        query = urlencode(request_params)
        url = f"{self.base_url.rstrip('/')}{path}"
        data: bytes | None = None
        if normalized_method == "GET" and query:
            url = f"{url}?{query}"
        elif query:
            data = query.encode("utf-8")
        headers = {"User-Agent": "EnhengClaw/0.1"}
        if signed:
            if not self.api_key:
                raise ValueError("api_key is required for signed Binance USD-M requests")
            headers["X-MBX-APIKEY"] = self.api_key
        request = Request(url, data=data, headers=headers, method=normalized_method)
        opener = self.urlopen_fn or urlopen
        try:
            with opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                return BinanceUsdmResponse(
                    status_code=int(getattr(response, "status", 200)),
                    headers=dict(getattr(response, "headers", {}) or {}),
                    payload=payload,
                )
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 503 and UNKNOWN_EXECUTION_STATUS_MARKER in detail:
                raise BinanceUsdmUnknownExecutionStatus(normalized_method, path, detail) from exc
            raise BinanceUsdmRequestError(normalized_method, path, int(exc.code), detail) from exc

    def _time_ms(self) -> int:
        if self.time_ms_fn is not None:
            return int(self.time_ms_fn())
        return int(time.time() * 1000)


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _order_lookup_params(
    *,
    symbol: str,
    order_id: int | str | None = None,
    orig_client_order_id: str | None = None,
) -> dict[str, Any]:
    if order_id is None and not orig_client_order_id:
        raise ValueError("either order_id or orig_client_order_id is required")
    return {
        "symbol": symbol,
        "orderId": order_id,
        "origClientOrderId": orig_client_order_id,
    }
