from __future__ import annotations

import csv
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request as urllib_request

from enhengclaw.providers.offline_providers import OfflineReplayOnchainProvider
from enhengclaw.providers.providers import (
    OnchainProvider,
    OnchainProviderPayload,
    ProviderMetadata,
    ProviderNetworkError,
    ProviderReplayError,
    ProviderRequest,
    ProviderSchemaError,
    ProviderTimeoutError,
    validate_onchain_provider_payload,
)
from enhengclaw.utils.subject_keys import SubjectKey, subject_key_path


HttpGetter = Callable[..., Any]


@dataclass(slots=True)
class RealOnchainProviderConfig:
    api_base_url: str = "https://api.dexscreener.com"
    timeout_seconds: float = 5.0
    api_key_env_var: str | None = None
    mode: str = "live"
    raw_payload_dir: str | Path | None = None
    query_quote_symbol: str = "USDT"
    max_pairs: int = 1


class RealOnchainProvider(OnchainProvider):
    file_name = "onchain_snapshot.csv"
    provider_name = "dexscreener-public-onchain"
    subject_instrument_type = "onchain"

    def __init__(
        self,
        config: RealOnchainProviderConfig | None = None,
        *,
        http_getter: HttpGetter | None = None,
    ) -> None:
        self.config = config or RealOnchainProviderConfig()
        self.http_getter = http_getter or urllib_request.urlopen
        self.raw_payload_dir = (
            Path(self.config.raw_payload_dir)
            if self.config.raw_payload_dir is not None
            else Path(__file__).resolve().parents[3] / "fixtures" / "replays"
        )

    def fetch(self, request: ProviderRequest) -> OnchainProviderPayload:
        self._require_fetch_execution(request, operation="provider.real_onchain.fetch")
        if self.config.mode == "replay":
            return self._fetch_replay(request)
        if self.config.mode not in {"live", "record"}:
            raise ProviderSchemaError(f"unsupported RealOnchainProvider mode: {self.config.mode}")

        payload = self._fetch_live(request)
        if self.config.mode == "record":
            self._record_payload(request, payload.raw_payload)
        return payload

    def preview(self, request: ProviderRequest) -> dict[str, object]:
        try:
            payload = self.fetch(request)
            sample_keys = sorted(str(key) for key in payload.raw_payload[0].keys()) if payload.raw_payload else []
            return {
                "provider_name": payload.metadata.provider_name,
                "scenario": payload.metadata.scenario,
                "retrieved_at": payload.metadata.retrieved_at.isoformat(),
                "raw_record_count": payload.metadata.raw_record_count,
                "mode": self.config.mode,
                "replay_path": str(self._replay_path_for(request)),
                "sample_keys": sample_keys,
            }
        except Exception as exc:  # pragma: no cover - preview fallback
            return {
                "provider_name": self.provider_name,
                "scenario": request.scenario,
                "mode": self.config.mode,
                "replay_path": str(self._replay_path_for(request)),
                "error": str(exc),
            }

    def _fetch_replay(self, request: ProviderRequest) -> OnchainProviderPayload:
        try:
            payload = OfflineReplayOnchainProvider(
                self.raw_payload_dir,
                default_venue=self.provider_name,
                default_instrument_type=self.subject_instrument_type,
            ).fetch(request)
            validate_onchain_provider_payload(payload)
        except Exception as exc:
            raise ProviderReplayError(f"failed to load onchain replay payload for scenario '{request.scenario}': {exc}") from exc
        return payload

    def _fetch_live(self, request: ProviderRequest) -> OnchainProviderPayload:
        query = request.subject.upper()
        if self.config.query_quote_symbol and not query.endswith(self.config.query_quote_symbol.upper()):
            query = f"{query}"
        retrieved_at = datetime.now(timezone.utc)
        search_result = self._request_json(
            "/latest/dex/search",
            {"q": query},
            context="dex search",
        )
        rows = self._build_rows(request=request, retrieved_at=retrieved_at, search_result=search_result)
        payload = OnchainProviderPayload(
            metadata=ProviderMetadata(
                provider_name=self.provider_name,
                retrieved_at=retrieved_at,
                scenario=request.scenario,
                raw_record_count=len(rows),
            ),
            raw_payload=rows,
        )
        validate_onchain_provider_payload(payload)
        return payload

    def _request_json(self, path: str, query: dict[str, object], *, context: str) -> Any:
        self._require_transport_execution(operation="provider.real_onchain.transport")
        encoded = parse.urlencode({key: value for key, value in query.items() if value is not None})
        url = f"{self.config.api_base_url.rstrip('/')}{path}"
        if encoded:
            url = f"{url}?{encoded}"
        headers = {"Accept": "application/json"}
        if self.config.api_key_env_var:
            api_key = os.getenv(self.config.api_key_env_var)
            if api_key:
                headers["Authorization"] = api_key
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
        return data

    def _build_rows(
        self,
        *,
        request: ProviderRequest,
        retrieved_at: datetime,
        search_result: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(search_result, dict):
            raise ProviderSchemaError("dex search payload must be an object")
        pairs = search_result.get("pairs")
        if not isinstance(pairs, list):
            raise ProviderSchemaError("dex search payload must include a pairs list")

        subject = request.subject.upper()
        filtered = [pair for pair in pairs if self._matches_subject(pair, subject)]
        selected = filtered[: self.config.max_pairs]
        rows: list[dict[str, Any]] = []
        for index, pair in enumerate(selected, start=1):
            rows.append(self._pair_to_row(request, retrieved_at, pair, index))
        return rows

    def _matches_subject(self, pair: Any, subject: str) -> bool:
        if not isinstance(pair, dict):
            return False
        base = pair.get("baseToken")
        quote = pair.get("quoteToken")
        base_symbol = base.get("symbol") if isinstance(base, dict) else None
        quote_symbol = quote.get("symbol") if isinstance(quote, dict) else None
        return str(base_symbol or "").upper() == subject or str(quote_symbol or "").upper() == subject

    def _pair_to_row(
        self,
        request: ProviderRequest,
        retrieved_at: datetime,
        pair: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        base = pair.get("baseToken")
        if not isinstance(base, dict):
            raise ProviderSchemaError("dex pair is missing baseToken")
        txns = pair.get("txns")
        if not isinstance(txns, dict):
            raise ProviderSchemaError("dex pair is missing txns")
        h1 = txns.get("h1")
        if not isinstance(h1, dict):
            raise ProviderSchemaError("dex pair is missing txns.h1")
        buys = self._as_int(h1, "buys", context="txns.h1")
        sells = self._as_int(h1, "sells", context="txns.h1")
        liquidity = pair.get("liquidity")
        if not isinstance(liquidity, dict):
            raise ProviderSchemaError("dex pair is missing liquidity")
        liquidity_usd = self._as_float(liquidity, "usd", context="liquidity")
        volume = pair.get("volume")
        if not isinstance(volume, dict):
            raise ProviderSchemaError("dex pair is missing volume")
        volume_h24 = self._as_float(volume, "h24", context="volume")
        chain_id = str(pair.get("chainId", "unknown"))
        dex_id = str(pair.get("dexId", "unknown"))
        pair_address = str(pair.get("pairAddress", f"pair-{index}"))
        url = str(pair.get("url", ""))
        created_at_ms = pair.get("pairCreatedAt")

        direction = "bullish" if buys >= sells else "bearish"
        confidence = max(45, min(88, int(50 + min(abs(buys - sells) * 2, 20) + min(liquidity_usd / 100000, 18))))
        interpretation = (
            f"dex pair flow on {chain_id}/{dex_id} shows {buys} buys vs {sells} sells in h1 "
            f"with liquidity ${liquidity_usd:,.0f} and 24h volume ${volume_h24:,.0f}"
        )

        return {
            "record_id": f"{pair_address}:{index}",
            "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
            "provider": self.provider_name,
            "asset_symbol": request.subject.upper(),
            "event_type": "wallet_buy" if direction == "bullish" else "wallet_sell",
            "interpretation": interpretation,
            "claim_kind": "flow",
            "signal_side": direction,
            "evidence_grade": "E4",
            "confidence_score": str(confidence),
            "horizon_label": "intraday",
            "scope_name": request.scope,
            "wallet_cluster": "dex_pair_flow",
            "extra_note": f"pair={pair_address};dex={dex_id}",
            "raw_http_pair_address": pair_address,
            "raw_http_chain_id": chain_id,
            "raw_http_dex_id": dex_id,
            "raw_http_url": url,
            "raw_http_pair_created_at": "" if created_at_ms is None else str(created_at_ms),
        }

    def _record_payload(self, request: ProviderRequest, rows: list[dict[str, Any]]) -> None:
        path = self._replay_path_for(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            fieldnames = [
                "record_id",
                "retrieved_at",
                "provider",
                "asset_symbol",
                "event_type",
                "interpretation",
                "claim_kind",
                "signal_side",
                "evidence_grade",
                "confidence_score",
                "horizon_label",
                "scope_name",
                "wallet_cluster",
                "extra_note",
                "raw_http_pair_address",
                "raw_http_chain_id",
                "raw_http_dex_id",
                "raw_http_url",
                "raw_http_pair_created_at",
            ]
        else:
            fieldnames = []
            for row in rows:
                for key in row.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _replay_path_for(self, request: ProviderRequest) -> Path:
        subject_key = SubjectKey.from_request(
            request,
            default_venue=self.provider_name,
            default_instrument_type=self.subject_instrument_type,
        )
        return subject_key_path(self.raw_payload_dir, request.scenario, subject_key, self.file_name)

    def _as_int(self, source: Any, key: str, *, context: str) -> int:
        try:
            value = source[key]
        except (KeyError, TypeError) as exc:
            raise ProviderSchemaError(f"{context} is missing field '{key}'") from exc
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ProviderSchemaError(f"{context} field '{key}' must be int-like") from exc

    def _as_float(self, source: Any, key: str, *, context: str) -> float:
        try:
            value = source[key]
        except (KeyError, TypeError) as exc:
            raise ProviderSchemaError(f"{context} is missing field '{key}'") from exc
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ProviderSchemaError(f"{context} field '{key}' must be numeric") from exc

    def _error_body(self, exc: error.HTTPError) -> str:
        try:
            body = exc.read()
        except Exception:  # pragma: no cover
            return exc.reason if isinstance(exc.reason, str) else "http error"
        if not body:
            return exc.reason if isinstance(exc.reason, str) else "http error"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body.decode("utf-8", errors="replace")
        return json.dumps(data) if isinstance(data, dict) else str(data)
