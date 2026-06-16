from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib import parse

import websockets
from websockets.exceptions import ConnectionClosed

from enhengclaw.core.execution_control import (
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    DEFAULT_SHADOW_INGEST_SCOPE,
    INGESTION_WORKER_ENTRYPOINT,
    require_active_worker_lease,
)
from enhengclaw.health.data_health_monitor import DataHealthMonitor
from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
from enhengclaw.ingress.shadow_schema import (
    BinanceTradeSchemaValidator,
    CrossSubjectViolationError,
    SHADOW_SCHEMA_VERSION,
    ShadowSchemaError,
)
from enhengclaw.providers.shadow_common import (
    ExponentialBackoffConfig,
    require_env,
    sleep_or_stop,
)
from enhengclaw.utils.binance_http import BinanceHttpError, binance_get_json
from enhengclaw.utils.subject_keys import SubjectKey


WebSocketConnectCallable = Callable[..., Any]


@dataclass(slots=True)
class BinanceTradeShadowConfig:
    api_key_env_var: str = "BINANCE_API_KEY"
    websocket_url: str = "wss://stream.binance.com:9443/ws"
    rest_api_base_url: str = "https://api.binance.com"
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    socket_label: str | None = None
    ping_interval_seconds: float | None = None
    ping_timeout_seconds: float | None = None
    receive_timeout_seconds: float = 20.0
    historical_trade_limit: int = 1000
    historical_trade_max_pages: int = 200
    symbol_live_gap_threshold_seconds: float = 120.0
    symbol_live_gap_check_interval_seconds: float = 5.0
    post_ack_symbol_grace_seconds: float = 30.0
    reconnect_backoff: ExponentialBackoffConfig = field(
        default_factory=lambda: ExponentialBackoffConfig(
            initial_delay_seconds=1.0,
            max_delay_seconds=5.0,
            multiplier=2.0,
            max_attempts=None,
        )
    )


class BinanceTradeShadowProvider:
    provider_id = "binance.spot.ws"

    def __init__(
        self,
        config: BinanceTradeShadowConfig | None = None,
        *,
        replay_writer: LiveReplayWriter | None = None,
        quarantine_writer: LiveQuarantineWriter | None = None,
        health_monitor: DataHealthMonitor | None = None,
        logger: logging.Logger | None = None,
        websocket_connect: WebSocketConnectCallable | None = None,
        state_root: str | Path | None = None,
    ) -> None:
        self.config = config or BinanceTradeShadowConfig()
        self.socket_label = self._resolve_socket_label()
        base_logger = logger or logging.getLogger(self.__class__.__name__)
        self.logger = (
            base_logger.getChild(self.socket_label)
            if self.socket_label is not None
            else base_logger
        )
        self.replay_writer = replay_writer or LiveReplayWriter()
        self.quarantine_writer = quarantine_writer or LiveQuarantineWriter()
        self.health_monitor = health_monitor
        self.websocket_connect = websocket_connect or websockets.connect
        self.validator = BinanceTradeSchemaValidator(self.config.symbols)
        self.streams = tuple(f"{symbol.lower()}@trade" for symbol in self.config.symbols)
        self.unknown_subject_key = SubjectKey.build(
            symbol="UNKNOWN",
            venue="binance",
            instrument_type="spot",
        )
        self.api_key = require_env(self.config.api_key_env_var)
        replay_root = Path(self.replay_writer.root).resolve()
        default_state_root = (
            replay_root.parent / "provider_state"
            if replay_root.name == "live_replay"
            else replay_root / "provider_state"
        )
        base_state_root = (
            Path(state_root).resolve()
            if state_root is not None
            else default_state_root
        )
        self.state_root = (
            base_state_root / "binance" / self.socket_label
            if self.socket_label is not None
            else base_state_root
        )
        self.checkpoint_path = self.state_root / "binance_trade_checkpoint.json"
        self._last_trade_ids = self._load_checkpoint()
        self._last_live_receive_monotonic: dict[str, float] = {}
        self._last_live_source_timestamp_utc: dict[str, datetime] = {}
        self._subscription_ack_monotonic: float | None = None

    def _resolve_socket_label(self) -> str | None:
        if self.config.socket_label is not None and self.config.socket_label.strip():
            return self.config.socket_label.strip().upper()
        if len(self.config.symbols) == 1:
            return self.config.symbols[0].strip().upper()
        return None

    async def run(self, stop_event: asyncio.Event) -> None:
        require_active_worker_lease(
            operation="provider.binance_shadow.run",
            required_capabilities={CAP_PROVIDER_STREAM},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        attempt = 0
        while not stop_event.is_set():
            try:
                await self._run_session(stop_event, reconnecting=attempt > 0)
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                max_attempts = self.config.reconnect_backoff.max_attempts
                if max_attempts is not None and attempt > max_attempts:
                    raise RuntimeError(
                        f"Binance reconnect attempts exhausted after {max_attempts} failures"
                    ) from exc
                delay_seconds = self.config.reconnect_backoff.delay_for_attempt(attempt)
                self.logger.warning(
                    "Binance WebSocket disconnected; reconnect attempt %s/%s in %.1fs: %s",
                    attempt,
                    self.config.reconnect_backoff.describe_attempts(),
                    delay_seconds,
                    exc,
                )
                await sleep_or_stop(stop_event, delay_seconds)

    def process_message(self, payload: Any, *, origin: str = "live") -> bool:
        require_active_worker_lease(
            operation="provider.binance_shadow.process_message",
            required_capabilities={CAP_PROVIDER_STREAM},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        if origin not in {"live", "historical"}:
            raise ValueError(f"unsupported Binance message origin '{origin}'")
        if self._is_subscription_ack(payload):
            return True

        try:
            event = self.validator.validate(payload)
        except CrossSubjectViolationError as exc:
            subject_key = self.validator.infer_subject_key(payload)
            self.quarantine_writer.write(
                subject_key=subject_key,
                provider_id=self.provider_id,
                event_type="trade",
                raw_payload=payload,
                reason=str(exc),
                schema_version=SHADOW_SCHEMA_VERSION,
            )
            if self.health_monitor is not None:
                self.health_monitor.note_contamination(subject_key, str(exc))
            raise
        except ShadowSchemaError as exc:
            subject_key = self.validator.infer_subject_key(payload)
            self.quarantine_writer.write(
                subject_key=subject_key,
                provider_id=self.provider_id,
                event_type="trade",
                raw_payload=payload,
                reason=str(exc),
                schema_version=SHADOW_SCHEMA_VERSION,
            )
            self.logger.error(
                "Rejected Binance trade payload for %s: %s",
                subject_key.as_stable_string(),
                exc,
            )
            return False

        symbol, trade_id = self._extract_trade_identity(payload)
        if origin == "live" and symbol is not None:
            self._note_live_message(symbol, event.source_timestamp)
        if symbol is not None and trade_id is not None:
            last_seen = self._last_trade_ids.get(symbol)
            if last_seen is not None and trade_id <= last_seen:
                self.logger.debug(
                    "Skipping duplicate Binance trade for %s trade_id=%s last_seen=%s",
                    symbol,
                    trade_id,
                    last_seen,
                )
                return False
        self.replay_writer.write(event=event)
        if symbol is not None and trade_id is not None:
            self._remember_trade(symbol, trade_id)
        return False

    async def _run_session(
        self,
        stop_event: asyncio.Event,
        *,
        reconnecting: bool = False,
    ) -> None:
        require_active_worker_lease(
            operation="provider.binance_shadow.transport",
            required_capabilities={CAP_PROVIDER_TRANSPORT},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        self.logger.info(
            "Connecting Binance WebSocket for streams: %s",
            ", ".join(self.streams),
        )
        self._reset_live_watchdog_state()
        async with self.websocket_connect(
            self.config.websocket_url,
            ping_interval=self.config.ping_interval_seconds,
            ping_timeout=self.config.ping_timeout_seconds,
            open_timeout=self.config.receive_timeout_seconds,
            close_timeout=min(self.config.receive_timeout_seconds, 5.0),
        ) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "method": "SUBSCRIBE",
                        "params": list(self.streams),
                        "id": 1,
                    },
                    separators=(",", ":"),
                )
            )
            await self._await_subscription_ack(
                websocket,
                stop_event=stop_event,
                reconnecting=reconnecting,
            )
            self._subscription_ack_monotonic = time.monotonic()
            reconnect_signal: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            watchdog_task = asyncio.create_task(
                self._watch_live_symbol_gaps(
                    stop_event=stop_event,
                    reconnect_signal=reconnect_signal,
                )
            )
            catch_up_task = asyncio.create_task(self._recover_gap_best_effort(stop_event))
            receive_task: asyncio.Task[Any] | None = None
            try:
                while not stop_event.is_set():
                    receive_task = asyncio.create_task(self._receive_payload(websocket))
                    done, _ = await asyncio.wait(
                        {receive_task, reconnect_signal},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if reconnect_signal in done:
                        if not receive_task.done():
                            receive_task.cancel()
                            try:
                                await receive_task
                            except asyncio.CancelledError:
                                pass
                        raise RuntimeError(reconnect_signal.result())
                    payload = receive_task.result()
                    self.process_message(payload, origin="live")
            finally:
                if receive_task is not None and not receive_task.done():
                    receive_task.cancel()
                    try:
                        await receive_task
                    except asyncio.CancelledError:
                        pass
                for task, task_name in (
                    (catch_up_task, "Background Binance catch-up task"),
                    (watchdog_task, "Per-symbol Binance live-gap watchdog"),
                ):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        self.logger.warning(
                            "%s ended with error during session shutdown: %s",
                            task_name,
                            exc,
                        )
                self._reset_live_watchdog_state()

    def _is_subscription_ack(self, payload: Any) -> bool:
        return (
            isinstance(payload, dict)
            and payload.get("result") is None
            and "id" in payload
            and "stream" not in payload
        )

    async def _recover_gap_best_effort(self, stop_event: asyncio.Event) -> None:
        symbols_with_checkpoint = [
            symbol
            for symbol in self.config.symbols
            if self._last_trade_ids.get(symbol) is not None
        ]
        if not symbols_with_checkpoint:
            return
        for symbol in symbols_with_checkpoint:
            if stop_event.is_set():
                return
            try:
                await self._recover_symbol_gap(symbol, stop_event=stop_event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning(
                    "Binance catch-up failed for %s; continuing with live stream: %s",
                    symbol,
                    exc,
                )
            await asyncio.sleep(0)

    async def _recover_symbol_gap(self, symbol: str, *, stop_event: asyncio.Event) -> None:
        last_trade_id = self._last_trade_ids.get(symbol)
        if last_trade_id is None:
            return
        next_trade_id = last_trade_id + 1
        recovered = 0
        hit_page_cap = False
        self.logger.info(
            "Starting background catch-up for %s from trade_id=%s",
            symbol,
            next_trade_id,
        )
        self.logger.info(
            "Ignoring historical catch-up payload for live-gap watchdog on %s",
            symbol,
        )
        for page in range(1, self.config.historical_trade_max_pages + 1):
            if stop_event.is_set():
                return
            current_last_trade_id = self._last_trade_ids.get(symbol)
            if current_last_trade_id is not None and current_last_trade_id >= next_trade_id:
                self.logger.info(
                    "Binance catch-up aborted for %s because live stream overtook checkpoint at trade_id=%s",
                    symbol,
                    current_last_trade_id,
                )
                return
            rows = await asyncio.to_thread(self._fetch_historical_trades, symbol, next_trade_id)
            current_last_trade_id = self._last_trade_ids.get(symbol)
            if current_last_trade_id is not None and current_last_trade_id >= next_trade_id:
                self.logger.info(
                    "Binance catch-up aborted for %s because live stream overtook checkpoint at trade_id=%s",
                    symbol,
                    current_last_trade_id,
                )
                return
            if not rows:
                break
            max_trade_id = next_trade_id - 1
            for row in rows:
                payload = self._historical_trade_to_stream_payload(symbol, row)
                _, trade_id = self._extract_trade_identity(payload)
                if trade_id is None or trade_id < next_trade_id:
                    continue
                self.process_message(payload, origin="historical")
                recovered += 1
                max_trade_id = max(max_trade_id, trade_id)
            if max_trade_id < next_trade_id:
                break
            next_trade_id = max_trade_id + 1
            if len(rows) < self.config.historical_trade_limit:
                break
            if page == self.config.historical_trade_max_pages:
                hit_page_cap = True
            await asyncio.sleep(0)
        self.logger.info(
            "Binance catch-up completed for %s recovered=%s",
            symbol,
            recovered,
        )
        if hit_page_cap:
            self.logger.warning(
                "Binance catch-up for %s hit the configured page cap after recovering %s trades; "
                "source freshness may remain degraded until live traffic catches up",
                symbol,
                recovered,
            )

    async def _watch_live_symbol_gaps(
        self,
        *,
        stop_event: asyncio.Event,
        reconnect_signal: asyncio.Future[str],
    ) -> None:
        self.logger.info("Starting per-symbol live-gap watchdog")
        while not stop_event.is_set() and not reconnect_signal.done():
            ack_monotonic = self._subscription_ack_monotonic
            if ack_monotonic is None:
                await asyncio.sleep(self.config.symbol_live_gap_check_interval_seconds)
                continue
            now_monotonic = time.monotonic()
            now_utc = datetime.now(timezone.utc)
            for symbol in self.config.symbols:
                last_live_receive = self._last_live_receive_monotonic.get(symbol)
                if last_live_receive is None:
                    if now_monotonic - ack_monotonic <= self.config.post_ack_symbol_grace_seconds:
                        continue
                    live_receive_gap = now_monotonic - ack_monotonic
                else:
                    live_receive_gap = now_monotonic - last_live_receive
                if live_receive_gap > self.config.symbol_live_gap_threshold_seconds:
                    reason = (
                        "forcing Binance reconnect because "
                        f"{symbol} live receive gap exceeded "
                        f"{self.config.symbol_live_gap_threshold_seconds:.0f}s"
                    )
                    self.logger.warning(reason)
                    reconnect_signal.set_result(reason)
                    return
                last_live_source = self._last_live_source_timestamp_utc.get(symbol)
                if last_live_source is None:
                    continue
                live_source_age = (now_utc - last_live_source).total_seconds()
                if live_source_age > self.config.symbol_live_gap_threshold_seconds:
                    reason = (
                        "forcing Binance reconnect because "
                        f"{symbol} live source age exceeded "
                        f"{self.config.symbol_live_gap_threshold_seconds:.0f}s"
                    )
                    self.logger.warning(reason)
                    reconnect_signal.set_result(reason)
                    return
            await asyncio.sleep(self.config.symbol_live_gap_check_interval_seconds)

    async def _await_subscription_ack(
        self,
        websocket: Any,
        *,
        stop_event: asyncio.Event,
        reconnecting: bool,
    ) -> None:
        while not stop_event.is_set():
            payload = await self._receive_payload(websocket)
            if self.process_message(payload):
                if reconnecting:
                    self.logger.info(
                        "Binance subscription ack received after reconnect for streams: %s",
                        ", ".join(self.streams),
                    )
                else:
                    self.logger.info(
                        "Binance subscription acknowledged for streams: %s",
                        ", ".join(self.streams),
                    )
                return
        raise RuntimeError("stop requested before Binance subscription ack was received")

    async def _receive_payload(self, websocket: Any) -> Any:
        try:
            raw_message = await asyncio.wait_for(
                websocket.recv(),
                timeout=self.config.receive_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"no Binance messages received within {self.config.receive_timeout_seconds:.1f}s"
            ) from exc
        except ConnectionClosed as exc:
            raise RuntimeError(f"Binance WebSocket closed: {exc}") from exc

        try:
            return json.loads(raw_message)
        except json.JSONDecodeError as exc:
            self.quarantine_writer.write(
                subject_key=self.unknown_subject_key,
                provider_id=self.provider_id,
                event_type="trade",
                raw_payload={"raw_text": raw_message},
                reason=f"invalid JSON from Binance WebSocket: {exc.msg}",
                schema_version=SHADOW_SCHEMA_VERSION,
            )
            raise RuntimeError("received invalid JSON from Binance WebSocket") from exc

    def _fetch_historical_trades(self, symbol: str, from_trade_id: int) -> list[dict[str, Any]]:
        require_active_worker_lease(
            operation="provider.binance_shadow.transport_historical_trades",
            required_capabilities={CAP_PROVIDER_TRANSPORT},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        query = parse.urlencode(
            {
                "symbol": symbol,
                "limit": self.config.historical_trade_limit,
                "fromId": from_trade_id,
            }
        )
        url = f"{self.config.rest_api_base_url.rstrip('/')}/api/v3/historicalTrades?{query}"
        try:
            payload = binance_get_json(
                url,
                headers={
                    "Accept": "application/json",
                    "X-MBX-APIKEY": self.api_key,
                },
                timeout_seconds=self.config.receive_timeout_seconds,
            )
        except BinanceHttpError as exc:
            if exc.reason == "timeout":
                raise TimeoutError(f"timeout fetching Binance historical trades for {symbol}") from exc
            raise RuntimeError(f"network error fetching Binance historical trades for {symbol}: {exc}") from exc
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected Binance historical trades payload for {symbol}: expected list")
        return [row for row in payload if isinstance(row, dict)]

    def _historical_trade_to_stream_payload(self, symbol: str, row: dict[str, Any]) -> dict[str, Any]:
        trade_id = int(row["id"])
        timestamp_ms = int(row["time"])
        return {
            "stream": f"{symbol.lower()}@trade",
            "data": {
                "e": "trade",
                "E": timestamp_ms,
                "s": symbol,
                "t": trade_id,
                "p": str(row["price"]),
                "q": str(row["qty"]),
                "T": timestamp_ms,
                "m": bool(row.get("isBuyerMaker", False)),
                "M": bool(row.get("isBestMatch", True)),
            },
        }

    def _extract_trade_identity(self, payload: Any) -> tuple[str | None, int | None]:
        if not isinstance(payload, dict):
            return None, None
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return None, None
        symbol = data.get("s")
        trade_id = data.get("t")
        if not isinstance(symbol, str):
            return None, None
        try:
            return symbol.upper(), int(trade_id)
        except (TypeError, ValueError):
            return symbol.upper(), None

    def _remember_trade(self, symbol: str, trade_id: int) -> None:
        current = self._last_trade_ids.get(symbol)
        if current is not None and trade_id <= current:
            return
        self._last_trade_ids[symbol] = trade_id
        self._write_checkpoint()

    def _note_live_message(self, symbol: str, source_timestamp: str | None) -> None:
        self._last_live_receive_monotonic[symbol] = time.monotonic()
        parsed_source_timestamp = self._coerce_utc_datetime(source_timestamp)
        if parsed_source_timestamp is None:
            return
        current = self._last_live_source_timestamp_utc.get(symbol)
        if current is None or parsed_source_timestamp > current:
            self._last_live_source_timestamp_utc[symbol] = parsed_source_timestamp

    def _reset_live_watchdog_state(self) -> None:
        self._last_live_receive_monotonic.clear()
        self._last_live_source_timestamp_utc.clear()
        self._subscription_ack_monotonic = None

    def _coerce_utc_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _load_checkpoint(self) -> dict[str, int]:
        if not self.checkpoint_path.exists():
            return {}
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        checkpoints = payload.get("last_trade_ids")
        if not isinstance(checkpoints, dict):
            return {}
        loaded: dict[str, int] = {}
        for symbol, trade_id in checkpoints.items():
            try:
                loaded[str(symbol).upper()] = int(trade_id)
            except (TypeError, ValueError):
                continue
        return loaded

    def _write_checkpoint(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider_id": self.provider_id,
            "last_trade_ids": dict(sorted(self._last_trade_ids.items())),
        }
        self.checkpoint_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2),
            encoding="utf-8",
        )
