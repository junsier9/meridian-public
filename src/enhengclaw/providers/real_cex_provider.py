from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request as urllib_request

from enhengclaw.providers.offline_providers import OfflineReplayCEXProvider
from enhengclaw.providers.providers import (
    CEXProvider,
    CEXProviderPayload,
    ProviderMetadata,
    ProviderNetworkError,
    ProviderReplayError,
    ProviderRequest,
    ProviderSchemaError,
    ProviderTimeoutError,
    validate_cex_provider_payload,
)
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_path


HttpGetter = Callable[..., Any]


@dataclass(slots=True)
class RealCEXProviderConfig:
    api_base_url: str = "https://api.binance.com"
    timeout_seconds: float = 5.0
    api_key_env_var: str | None = None
    mode: str = "live"
    raw_payload_dir: str | Path | None = None
    quote_asset: str = "USDT"
    kline_interval: str = "5m"
    kline_limit: int = 2


class RealCEXProvider(CEXProvider):
    file_name = "cex_snapshot.json"
    provider_name = "binance-public-cex"
    subject_instrument_type = "cex"

    def __init__(
        self,
        config: RealCEXProviderConfig | None = None,
        *,
        http_getter: HttpGetter | None = None,
    ) -> None:
        self.config = config or RealCEXProviderConfig()
        self.http_getter = http_getter or urllib_request.urlopen
        self.raw_payload_dir = (
            Path(self.config.raw_payload_dir)
            if self.config.raw_payload_dir is not None
            else Path(__file__).resolve().parents[3] / "fixtures" / "replays"
        )

    def fetch(self, request: ProviderRequest) -> CEXProviderPayload:
        self._require_fetch_execution(request, operation="provider.real_cex.fetch")
        if self.config.mode == "replay":
            return self._fetch_replay(request)
        if self.config.mode not in {"live", "record"}:
            raise ProviderSchemaError(f"unsupported RealCEXProvider mode: {self.config.mode}")

        payload = self._fetch_live(request)
        if self.config.mode == "record":
            self._record_payload(request, payload.raw_payload)
        return payload

    def preview(self, request: ProviderRequest) -> dict[str, object]:
        try:
            payload = self.fetch(request)
            return {
                "provider_name": payload.metadata.provider_name,
                "scenario": payload.metadata.scenario,
                "retrieved_at": payload.metadata.retrieved_at.isoformat(),
                "raw_record_count": payload.metadata.raw_record_count,
                "mode": self.config.mode,
                "replay_path": str(self._replay_path_for(request)),
                "sample_keys": sorted(str(key) for key in payload.raw_payload.keys()),
            }
        except Exception as exc:  # pragma: no cover - defensive preview path
            return {
                "provider_name": self.provider_name,
                "scenario": request.scenario,
                "mode": self.config.mode,
                "replay_path": str(self._replay_path_for(request)),
                "error": str(exc),
            }

    def _fetch_replay(self, request: ProviderRequest) -> CEXProviderPayload:
        try:
            payload = OfflineReplayCEXProvider(
                self.raw_payload_dir,
                default_venue=self.provider_name,
                default_instrument_type=self.subject_instrument_type,
            ).fetch(request)
            validate_cex_provider_payload(payload)
        except Exception as exc:
            raise ProviderReplayError(f"failed to load replay payload for scenario '{request.scenario}': {exc}") from exc
        return payload

    def _fetch_live(self, request: ProviderRequest) -> CEXProviderPayload:
        instrument = self._instrument_for(request.subject)
        retrieved_at = datetime.now(timezone.utc)
        ticker = self._request_json(
            "/api/v3/ticker/24hr",
            {"symbol": instrument},
            context="spot 24hr ticker",
        )
        klines = self._request_json(
            "/api/v3/klines",
            {"symbol": instrument, "interval": self.config.kline_interval, "limit": self.config.kline_limit},
            context="spot klines",
        )
        raw_payload = self._build_raw_payload(
            request=request,
            instrument=instrument,
            retrieved_at=retrieved_at,
            ticker=ticker,
            klines=klines,
        )
        payload = CEXProviderPayload(
            metadata=ProviderMetadata(
                provider_name=self.provider_name,
                retrieved_at=retrieved_at,
                scenario=request.scenario,
                raw_record_count=len(raw_payload["events"]),
            ),
            raw_payload=raw_payload,
        )
        validate_cex_provider_payload(payload)
        return payload

    def _request_json(self, path: str, query: dict[str, object], *, context: str) -> Any:
        self._require_transport_execution(operation="provider.real_cex.transport")
        encoded = parse.urlencode({key: value for key, value in query.items() if value is not None})
        url = f"{self.config.api_base_url.rstrip('/')}{path}"
        if encoded:
            url = f"{url}?{encoded}"
        headers = {"Accept": "application/json"}
        if self.config.api_key_env_var:
            api_key = os.getenv(self.config.api_key_env_var)
            if api_key:
                headers["X-MBX-APIKEY"] = api_key
        req = urllib_request.Request(url, headers=headers, method="GET")
        try:
            with self.http_getter(req, timeout=self.config.timeout_seconds) as response:
                body = response.read()
        except error.HTTPError as exc:
            detail = self._error_body(exc)
            raise ProviderNetworkError(f"{context} request failed with HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise ProviderTimeoutError(f"{context} request timed out after {self.config.timeout_seconds}s") from exc
            raise ProviderNetworkError(f"{context} request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError(f"{context} request timed out after {self.config.timeout_seconds}s") from exc
        except OSError as exc:
            raise ProviderNetworkError(f"{context} request failed: {exc}") from exc

        if not body or not body.strip():
            raise ProviderSchemaError(f"{context} returned an empty response body")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError(f"{context} returned invalid JSON: {exc.msg}") from exc
        if isinstance(data, dict) and "code" in data and "msg" in data:
            raise ProviderSchemaError(f"{context} returned exchange error payload: {data.get('msg')}")
        return data

    def _build_raw_payload(
        self,
        *,
        request: ProviderRequest,
        instrument: str,
        retrieved_at: datetime,
        ticker: Any,
        klines: Any,
    ) -> dict[str, Any]:
        if not isinstance(ticker, dict):
            raise ProviderSchemaError("spot 24hr ticker payload must be an object")
        if not isinstance(klines, list) or len(klines) < 2:
            raise ProviderSchemaError("spot klines payload must contain at least two candles")

        price_change_pct = self._as_float(ticker, "priceChangePercent", context="spot 24hr ticker")
        quote_volume = self._as_float(ticker, "quoteVolume", context="spot 24hr ticker")
        last_price = self._as_float(ticker, "lastPrice", context="spot 24hr ticker")
        open_price = self._as_float(ticker, "openPrice", context="spot 24hr ticker")

        previous_candle = klines[-2]
        latest_candle = klines[-1]
        if not isinstance(previous_candle, list) or not isinstance(latest_candle, list):
            raise ProviderSchemaError("spot klines rows must be arrays")

        previous_close = self._as_float(previous_candle, 4, context="previous kline close")
        latest_close = self._as_float(latest_candle, 4, context="latest kline close")
        latest_quote_volume = max(self._as_float(latest_candle, 7, context="latest kline quote volume"), 1.0)
        latest_taker_quote_volume = self._as_float(latest_candle, 10, context="latest kline taker buy quote volume")
        taker_buy_ratio = latest_taker_quote_volume / latest_quote_volume

        events = [
            {
                "event_id": f"{instrument.lower()}-spot-24h",
                "event_name": "spot_24h_momentum",
                "payload": {
                    "asset": request.subject.upper(),
                    "summary": self._ticker_summary(price_change_pct, quote_volume, last_price, open_price),
                    "metrics": {
                        "price_change_pct": round(price_change_pct, 4),
                        "quote_volume": round(quote_volume, 4),
                        "last_price": round(last_price, 8),
                    },
                },
                "mapping": {
                    "claimKind": "measurement",
                    "bias": self._momentum_bias(price_change_pct),
                    "evidence": "E4",
                    "confidenceScore": self._momentum_confidence(price_change_pct),
                    "horizon": "intraday",
                },
                "extra": {
                    "venue": "Binance",
                    "market_type": "spot",
                    "endpoint": "/api/v3/ticker/24hr",
                },
            },
            {
                "event_id": f"{instrument.lower()}-spot-structure",
                "event_name": "market_structure_support",
                "payload": {
                    "asset": request.subject.upper(),
                    "summary": self._structure_summary(previous_close, latest_close, taker_buy_ratio),
                    "metrics": {
                        "previous_close": round(previous_close, 8),
                        "latest_close": round(latest_close, 8),
                        "taker_buy_ratio": round(taker_buy_ratio, 4),
                    },
                },
                "mapping": {
                    "claimKind": "market_structure",
                    "bias": self._structure_bias(previous_close, latest_close, taker_buy_ratio),
                    "evidence": "E4",
                    "confidenceScore": self._structure_confidence(previous_close, latest_close, taker_buy_ratio),
                    "horizon": "intraday",
                },
                "extra": {
                    "venue": "Binance",
                    "market_type": "spot",
                    "endpoint": "/api/v3/klines",
                },
            },
        ]

        return {
            "provider": self.provider_name,
            "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
            "scenario_tag": request.scenario,
            "instrument": instrument,
            "events": events,
            "raw_http": {
                "ticker_24hr": ticker,
                "klines": klines,
            },
        }

    def _record_payload(self, request: ProviderRequest, raw_payload: dict[str, Any]) -> None:
        path = self._replay_path_for(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw_payload, indent=2), encoding="utf-8")

    def _replay_path_for(self, request: ProviderRequest) -> Path:
        subject_key = SubjectKey.from_request(
            request,
            default_venue=self.provider_name,
            default_instrument_type=self.subject_instrument_type,
        )
        return subject_key_path(self.raw_payload_dir, request.scenario, subject_key, self.file_name)

    def _instrument_for(self, subject: str) -> str:
        normalized = subject.upper()
        if normalized.endswith(self.config.quote_asset.upper()):
            return normalized
        return f"{normalized}{self.config.quote_asset.upper()}"

    def _as_float(self, source: Any, key: int | str, *, context: str) -> float:
        try:
            value = source[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderSchemaError(f"{context} is missing field '{key}'") from exc
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ProviderSchemaError(f"{context} field '{key}' must be numeric") from exc

    def _momentum_bias(self, price_change_pct: float) -> str:
        if price_change_pct > 0.25:
            return "bullish"
        if price_change_pct < -0.25:
            return "bearish"
        return "neutral"

    def _momentum_confidence(self, price_change_pct: float) -> int:
        return max(45, min(90, int(55 + min(abs(price_change_pct) * 2.0, 35))))

    def _structure_bias(self, previous_close: float, latest_close: float, taker_buy_ratio: float) -> str:
        if latest_close >= previous_close and taker_buy_ratio >= 0.5:
            return "bullish"
        if latest_close < previous_close and taker_buy_ratio <= 0.5:
            return "bearish"
        return "neutral"

    def _structure_confidence(self, previous_close: float, latest_close: float, taker_buy_ratio: float) -> int:
        move_score = min(abs(((latest_close - previous_close) / max(previous_close, 1e-9)) * 100.0) * 30.0, 18.0)
        ratio_score = min(abs(taker_buy_ratio - 0.5) * 80.0, 17.0)
        return max(45, min(88, int(50 + move_score + ratio_score)))

    def _ticker_summary(self, price_change_pct: float, quote_volume: float, last_price: float, open_price: float) -> str:
        return (
            f"24h price change is {price_change_pct:.2f}% with quote volume {quote_volume:.0f}; "
            f"last price {last_price:.6f} vs open {open_price:.6f}"
        )

    def _structure_summary(self, previous_close: float, latest_close: float, taker_buy_ratio: float) -> str:
        direction = "holding above" if latest_close >= previous_close else "slipping below"
        return (
            f"latest 5m candle is {direction} the prior close with taker buy ratio {taker_buy_ratio:.2f}"
        )

    def _error_body(self, exc: error.HTTPError) -> str:
        try:
            body = exc.read()
        except Exception:  # pragma: no cover - defensive
            return exc.reason if isinstance(exc.reason, str) else "http error"
        if not body:
            return exc.reason if isinstance(exc.reason, str) else "http error"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body.decode("utf-8", errors="replace")
        if isinstance(data, dict):
            if "msg" in data:
                return str(data["msg"])
            return json.dumps(data)
        return str(data)
