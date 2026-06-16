from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from enhengclaw.domain.identity.subject_key import SubjectKey
from enhengclaw.providers.shadow_common import isoformat_utc, stable_hash


SHADOW_SCHEMA_VERSION = "shadow.v1"


class ShadowSchemaError(ValueError):
    pass


class CrossSubjectViolationError(ShadowSchemaError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedShadowEvent:
    subject_key: SubjectKey
    provider_id: str
    event_type: str
    source_timestamp: str | None
    raw_payload: Any
    schema_version: str
    event_id: str


class BinanceTradeSchemaValidator:
    provider_id = "binance.spot.ws"
    event_type = "trade"

    def __init__(self, symbols: Iterable[str]) -> None:
        normalized_symbols = tuple(self._normalize_symbol(symbol) for symbol in symbols)
        if not normalized_symbols:
            raise ValueError("BinanceTradeSchemaValidator requires at least one symbol")
        self.subject_keys = {
            symbol: SubjectKey.build(symbol=symbol, venue="binance", instrument_type="spot")
            for symbol in normalized_symbols
        }

    def validate(self, payload: Any) -> ValidatedShadowEvent:
        if not isinstance(payload, Mapping):
            raise ShadowSchemaError("binance trade payload must be a JSON object")

        data = payload.get("data", payload)
        if not isinstance(data, Mapping):
            raise ShadowSchemaError("binance trade payload must include an object at field 'data'")

        event_type = self._require_non_empty_string(data.get("e"), field="data.e")
        if event_type != self.event_type:
            raise ShadowSchemaError(
                f"binance trade payload field 'data.e' must equal '{self.event_type}', observed '{event_type}'"
            )

        symbol = self._normalize_symbol(self._require_non_empty_string(data.get("s"), field="data.s"))
        if symbol not in self.subject_keys:
            raise CrossSubjectViolationError(
                f"unexpected Binance symbol '{symbol}' observed outside configured subject set"
            )

        stream_name = payload.get("stream")
        if stream_name is not None:
            stream = self._require_non_empty_string(stream_name, field="stream").lower()
            expected_stream = f"{symbol.lower()}@trade"
            if stream != expected_stream:
                raise CrossSubjectViolationError(
                    f"binance stream mismatch: expected '{expected_stream}', observed '{stream}'"
                )

        trade_id = self._require_int_like(data.get("t"), field="data.t")
        event_time_ms = self._require_int_like(data.get("E"), field="data.E")
        self._require_numeric_like(data.get("p"), field="data.p")
        self._require_numeric_like(data.get("q"), field="data.q")

        source_time_ms = data.get("T")
        if source_time_ms is None:
            source_timestamp = self._ms_to_iso(event_time_ms)
        else:
            source_timestamp = self._ms_to_iso(self._require_int_like(source_time_ms, field="data.T"))

        event_hash = stable_hash(
            {
                "provider_id": self.provider_id,
                "event_type": self.event_type,
                "symbol": symbol,
                "trade_id": trade_id,
                "event_time": event_time_ms,
                "price": str(data.get("p")),
                "quantity": str(data.get("q")),
            }
        )
        return ValidatedShadowEvent(
            subject_key=self.subject_keys[symbol],
            provider_id=self.provider_id,
            event_type=self.event_type,
            source_timestamp=source_timestamp,
            raw_payload=payload,
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"sha256:{event_hash}",
        )

    def infer_subject_key(self, payload: Any) -> SubjectKey:
        symbol = self._extract_symbol(payload)
        if symbol in self.subject_keys:
            return self.subject_keys[symbol]
        return SubjectKey.build(symbol=symbol or "UNKNOWN", venue="binance", instrument_type="spot")

    def _extract_symbol(self, payload: Any) -> str | None:
        if isinstance(payload, Mapping):
            data = payload.get("data")
            if isinstance(data, Mapping):
                symbol = data.get("s")
                if isinstance(symbol, str) and symbol.strip():
                    return self._normalize_symbol(symbol)
            stream_name = payload.get("stream")
            if isinstance(stream_name, str) and "@" in stream_name:
                return self._normalize_symbol(stream_name.split("@", maxsplit=1)[0])
        return None

    def _normalize_symbol(self, symbol: object) -> str:
        return self._require_non_empty_string(symbol, field="symbol").upper()

    def _require_non_empty_string(self, value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ShadowSchemaError(f"binance trade payload field '{field}' must be a non-empty string")
        return value.strip()

    def _require_int_like(self, value: object, *, field: str) -> int:
        if isinstance(value, bool):
            raise ShadowSchemaError(f"binance trade payload field '{field}' must be an integer")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ShadowSchemaError(f"binance trade payload field '{field}' must be an integer") from exc

    def _require_numeric_like(self, value: object, *, field: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ShadowSchemaError(f"binance trade payload field '{field}' must be numeric") from exc

    def _ms_to_iso(self, value: int) -> str:
        return isoformat_utc(datetime.fromtimestamp(value / 1000, tz=timezone.utc))


class AlchemyRpcSchemaValidator:
    def __init__(
        self,
        *,
        provider_id: str = "alchemy.eth.rpc",
        subject_key: SubjectKey | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.subject_key = subject_key or SubjectKey.build(
            symbol="ETH",
            venue="alchemy",
            instrument_type="onchain",
        )

    def validate(
        self,
        *,
        method: str,
        payload: Any,
        expected_id: int | str | None = None,
    ) -> ValidatedShadowEvent:
        if not isinstance(payload, Mapping):
            raise ShadowSchemaError("alchemy RPC response must be a JSON object")

        jsonrpc = self._require_non_empty_string(payload.get("jsonrpc"), field="jsonrpc")
        if jsonrpc != "2.0":
            raise ShadowSchemaError(f"alchemy RPC response field 'jsonrpc' must equal '2.0', observed '{jsonrpc}'")

        response_id = payload.get("id")
        if response_id is None:
            raise ShadowSchemaError("alchemy RPC response field 'id' is required")
        if expected_id is not None and response_id != expected_id:
            raise ShadowSchemaError(
                f"alchemy RPC response id mismatch: expected '{expected_id}', observed '{response_id}'"
            )
        if "result" not in payload:
            raise ShadowSchemaError("alchemy RPC response field 'result' is required")

        result = payload["result"]
        source_timestamp: str | None = None
        if method == "eth_blockNumber":
            self._require_hex_quantity(result, field="result")
        elif method == "eth_getBlockByNumber":
            if not isinstance(result, Mapping):
                raise ShadowSchemaError("alchemy RPC response field 'result' must be an object for eth_getBlockByNumber")
            self._require_hex_quantity(result.get("number"), field="result.number")
            timestamp_hex = self._require_hex_quantity(result.get("timestamp"), field="result.timestamp")
            source_timestamp = self._hex_timestamp_to_iso(timestamp_hex)
        else:
            raise ShadowSchemaError(f"unsupported Alchemy RPC method '{method}'")

        event_hash = stable_hash(
            {
                "provider_id": self.provider_id,
                "event_type": method,
                "id": response_id,
                "result": result,
            }
        )
        return ValidatedShadowEvent(
            subject_key=self.subject_key,
            provider_id=self.provider_id,
            event_type=method,
            source_timestamp=source_timestamp,
            raw_payload={
                "method": method,
                "response": payload,
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"sha256:{event_hash}",
        )

    def infer_subject_key(self, payload: Any | None = None) -> SubjectKey:
        return self.subject_key

    def _require_non_empty_string(self, value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ShadowSchemaError(f"alchemy RPC response field '{field}' must be a non-empty string")
        return value.strip()

    def _require_hex_quantity(self, value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value.startswith("0x") or len(value) < 3:
            raise ShadowSchemaError(f"alchemy RPC response field '{field}' must be a hex quantity string")
        try:
            int(value, 16)
        except ValueError as exc:
            raise ShadowSchemaError(f"alchemy RPC response field '{field}' must be a valid hex quantity string") from exc
        return value

    def _hex_timestamp_to_iso(self, value: str) -> str:
        seconds = int(value, 16)
        return isoformat_utc(datetime.fromtimestamp(seconds, tz=timezone.utc))


class AlchemySolanaRpcSchemaValidator:
    def __init__(
        self,
        *,
        provider_id: str = "alchemy.sol.rpc",
        subject_key: SubjectKey | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.subject_key = subject_key or SubjectKey.build(
            symbol="SOL",
            venue="alchemy",
            instrument_type="onchain",
        )

    def validate(
        self,
        *,
        method: str,
        payload: Any,
        expected_id: int | str | None = None,
    ) -> ValidatedShadowEvent:
        if not isinstance(payload, Mapping):
            raise ShadowSchemaError("alchemy Solana RPC response must be a JSON object")

        jsonrpc = self._require_non_empty_string(payload.get("jsonrpc"), field="jsonrpc")
        if jsonrpc != "2.0":
            raise ShadowSchemaError(
                f"alchemy Solana RPC response field 'jsonrpc' must equal '2.0', observed '{jsonrpc}'"
            )

        response_id = payload.get("id")
        if response_id is None:
            raise ShadowSchemaError("alchemy Solana RPC response field 'id' is required")
        if expected_id is not None and response_id != expected_id:
            raise ShadowSchemaError(
                f"alchemy Solana RPC response id mismatch: expected '{expected_id}', observed '{response_id}'"
            )
        if "result" not in payload:
            raise ShadowSchemaError("alchemy Solana RPC response field 'result' is required")

        result = payload["result"]
        source_timestamp: str | None = None
        if method == "getSlot":
            self._require_non_negative_int(result, field="result")
        elif method == "getBlock":
            if result is None:
                pass
            elif not isinstance(result, Mapping):
                raise ShadowSchemaError("alchemy Solana RPC response field 'result' must be an object for getBlock")
            else:
                self._require_non_negative_int(result.get("parentSlot"), field="result.parentSlot")
                block_time = result.get("blockTime")
                if block_time is not None:
                    source_timestamp = self._unix_timestamp_to_iso(
                        self._require_non_negative_int(block_time, field="result.blockTime")
                    )
        else:
            raise ShadowSchemaError(f"unsupported Alchemy Solana RPC method '{method}'")

        event_hash = stable_hash(
            {
                "provider_id": self.provider_id,
                "event_type": method,
                "id": response_id,
                "result": result,
            }
        )
        return ValidatedShadowEvent(
            subject_key=self.subject_key,
            provider_id=self.provider_id,
            event_type=method,
            source_timestamp=source_timestamp,
            raw_payload={
                "method": method,
                "response": payload,
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"sha256:{event_hash}",
        )

    def infer_subject_key(self, payload: Any | None = None) -> SubjectKey:
        return self.subject_key

    def _require_non_empty_string(self, value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ShadowSchemaError(f"alchemy Solana RPC response field '{field}' must be a non-empty string")
        return value.strip()

    def _require_non_negative_int(self, value: object, *, field: str) -> int:
        if isinstance(value, bool):
            raise ShadowSchemaError(f"alchemy Solana RPC response field '{field}' must be an integer")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ShadowSchemaError(f"alchemy Solana RPC response field '{field}' must be an integer") from exc
        if normalized < 0:
            raise ShadowSchemaError(f"alchemy Solana RPC response field '{field}' must be non-negative")
        return normalized

    def _unix_timestamp_to_iso(self, value: int) -> str:
        return isoformat_utc(datetime.fromtimestamp(value, tz=timezone.utc))


class AlchemyBitcoinRpcSchemaValidator:
    def __init__(
        self,
        *,
        provider_id: str = "alchemy.btc.rpc",
        subject_key: SubjectKey | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.subject_key = subject_key or SubjectKey.build(
            symbol="BTC",
            venue="alchemy",
            instrument_type="onchain",
        )

    def validate(
        self,
        *,
        method: str,
        payload: Any,
        expected_id: int | str | None = None,
    ) -> ValidatedShadowEvent:
        if not isinstance(payload, Mapping):
            raise ShadowSchemaError("alchemy Bitcoin RPC response must be a JSON object")

        jsonrpc = self._require_non_empty_string(payload.get("jsonrpc"), field="jsonrpc")
        if jsonrpc != "2.0":
            raise ShadowSchemaError(
                f"alchemy Bitcoin RPC response field 'jsonrpc' must equal '2.0', observed '{jsonrpc}'"
            )

        response_id = payload.get("id")
        if response_id is None:
            raise ShadowSchemaError("alchemy Bitcoin RPC response field 'id' is required")
        if expected_id is not None and response_id != expected_id:
            raise ShadowSchemaError(
                f"alchemy Bitcoin RPC response id mismatch: expected '{expected_id}', observed '{response_id}'"
            )
        if "result" not in payload:
            raise ShadowSchemaError("alchemy Bitcoin RPC response field 'result' is required")

        result = payload["result"]
        source_timestamp: str | None = None
        if method == "getblockcount":
            self._require_non_negative_int(result, field="result")
        elif method == "getblock":
            if not isinstance(result, Mapping):
                raise ShadowSchemaError("alchemy Bitcoin RPC response field 'result' must be an object for getblock")
            self._require_non_negative_int(result.get("height"), field="result.height")
            self._require_non_empty_string(result.get("hash"), field="result.hash")
            source_timestamp = self._unix_timestamp_to_iso(
                self._require_non_negative_int(result.get("time"), field="result.time")
            )
        else:
            raise ShadowSchemaError(f"unsupported Alchemy Bitcoin RPC method '{method}'")

        event_hash = stable_hash(
            {
                "provider_id": self.provider_id,
                "event_type": method,
                "id": response_id,
                "result": result,
            }
        )
        return ValidatedShadowEvent(
            subject_key=self.subject_key,
            provider_id=self.provider_id,
            event_type=method,
            source_timestamp=source_timestamp,
            raw_payload={
                "method": method,
                "response": payload,
            },
            schema_version=SHADOW_SCHEMA_VERSION,
            event_id=f"sha256:{event_hash}",
        )

    def infer_subject_key(self, payload: Any | None = None) -> SubjectKey:
        return self.subject_key

    def _require_non_empty_string(self, value: object, *, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ShadowSchemaError(f"alchemy Bitcoin RPC response field '{field}' must be a non-empty string")
        return value.strip()

    def _require_non_negative_int(self, value: object, *, field: str) -> int:
        if isinstance(value, bool):
            raise ShadowSchemaError(f"alchemy Bitcoin RPC response field '{field}' must be an integer")
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ShadowSchemaError(f"alchemy Bitcoin RPC response field '{field}' must be an integer") from exc
        if normalized < 0:
            raise ShadowSchemaError(f"alchemy Bitcoin RPC response field '{field}' must be non-negative")
        return normalized

    def _unix_timestamp_to_iso(self, value: int) -> str:
        return isoformat_utc(datetime.fromtimestamp(value, tz=timezone.utc))
