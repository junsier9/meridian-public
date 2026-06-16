from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import socket
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib import error, request as urllib_request

from enhengclaw.core.execution_control import (
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    DEFAULT_SHADOW_INGEST_SCOPE,
    INGESTION_WORKER_ENTRYPOINT,
    require_active_worker_lease,
)
from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
from enhengclaw.ingress.shadow_schema import (
    AlchemyRpcSchemaValidator,
    SHADOW_SCHEMA_VERSION,
    ShadowSchemaError,
)
from enhengclaw.infra.shared.redaction import redact_secret_url
from enhengclaw.providers.shadow_common import (
    ExponentialBackoffConfig,
    FatalTransportError,
    RetryableTransportError,
    require_env,
    sleep_or_stop,
)
from enhengclaw.utils.subject_keys import SubjectKey


RpcCaller = Callable[[dict[str, object]], Any]


@dataclass(slots=True)
class AlchemyEthShadowConfig:
    api_key_env_var: str = "ALCHEMY_API_KEY"
    provider_id: str = "alchemy.eth.rpc"
    symbol: str = "ETH"
    subject_key: str = "ETH.alchemy.onchain"
    network: str = "eth-mainnet"
    endpoint_url: str | None = None
    poll_interval_seconds: float = 5.0
    request_timeout_seconds: float = 10.0
    include_block_details: bool = True
    legacy_checkpoint_path: str | Path | None = None
    retry_backoff: ExponentialBackoffConfig = field(
        default_factory=lambda: ExponentialBackoffConfig(
            initial_delay_seconds=1.0,
            max_delay_seconds=20.0,
            multiplier=2.0,
            max_attempts=5,
        )
    )
    degraded_after_failures: int = 3


class AlchemyEthShadowProvider:
    provider_id = "alchemy.eth.rpc"

    def __init__(
        self,
        config: AlchemyEthShadowConfig | None = None,
        *,
        replay_writer: LiveReplayWriter | None = None,
        quarantine_writer: LiveQuarantineWriter | None = None,
        logger: logging.Logger | None = None,
        rpc_caller: RpcCaller | None = None,
        state_root: str | Path | None = None,
    ) -> None:
        self.config = config or AlchemyEthShadowConfig()
        base_logger = logger or logging.getLogger(self.__class__.__name__)
        log_label = self.config.symbol.strip().upper()
        self.logger = base_logger.getChild(log_label) if log_label else base_logger
        self.replay_writer = replay_writer or LiveReplayWriter()
        self.quarantine_writer = quarantine_writer or LiveQuarantineWriter()
        self.subject_key = SubjectKey.build(
            symbol=self.config.symbol,
            venue="alchemy",
            instrument_type="onchain",
        )
        if self.subject_key.as_stable_string() != self.config.subject_key:
            raise ValueError(
                "Alchemy EVM subject_key does not match the canonical stable string for the configured symbol: "
                f"expected '{self.subject_key.as_stable_string()}', observed '{self.config.subject_key}'"
            )
        self.provider_id = self.config.provider_id
        self.validator = AlchemyRpcSchemaValidator(
            provider_id=self.provider_id,
            subject_key=self.subject_key,
        )
        self.api_key = require_env(self.config.api_key_env_var)
        self.endpoint = self.config.endpoint_url or f"https://{self.config.network}.g.alchemy.com/v2/{self.api_key}"
        self.redacted_endpoint = redact_secret_url(self.endpoint)
        self.rpc_caller = rpc_caller or self._rpc_call_once
        self._request_id = 0
        replay_root = Path(self.replay_writer.root).resolve()
        default_state_root = (
            replay_root.parent / "provider_state"
            if replay_root.name == "live_replay"
            else replay_root / "provider_state"
        )
        self.state_root = (
            Path(state_root).resolve()
            if state_root is not None
            else default_state_root
        )
        self.checkpoint_path = self.state_root / "alchemy_block_checkpoint.json"
        self.legacy_checkpoint_path = (
            None
            if self.config.legacy_checkpoint_path is None
            else Path(self.config.legacy_checkpoint_path).resolve()
        )
        self._last_block_number = self._load_checkpoint()
        self._consecutive_failures = 0
        self._degraded = False

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    async def run(self, stop_event: asyncio.Event) -> None:
        require_active_worker_lease(
            operation="provider.alchemy_shadow.run",
            required_capabilities={CAP_PROVIDER_STREAM},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        while not stop_event.is_set():
            try:
                await self.poll_once()
                self._note_success()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._note_failure(exc)
            await sleep_or_stop(stop_event, self.config.poll_interval_seconds)

    async def poll_once(self) -> None:
        require_active_worker_lease(
            operation="provider.alchemy_shadow.poll_once",
            required_capabilities={CAP_PROVIDER_STREAM},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        block_request = self._build_request("eth_blockNumber", [])
        block_response = await self._call_with_retry(block_request)
        self._write_validated_response(
            method="eth_blockNumber",
            request_id=block_request["id"],
            response=block_response,
        )

        block_number = str(block_response["result"])
        detail_written = False
        if self.config.include_block_details:
            detail_written = await self._recover_and_write_block_range(block_number)
        else:
            self._remember_block_number(block_number)

        self.logger.info(
            "Alchemy poll succeeded against %s block=%s detail_written=%s",
            self.redacted_endpoint,
            block_number,
            detail_written,
        )

    def _write_validated_response(
        self,
        *,
        method: str,
        request_id: int,
        response: Any,
    ) -> None:
        require_active_worker_lease(
            operation="provider.alchemy_shadow.write_validated_response",
            required_capabilities={CAP_PROVIDER_STREAM},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        try:
            event = self.validator.validate(
                method=method,
                payload=response,
                expected_id=request_id,
            )
        except ShadowSchemaError as exc:
            self.quarantine_writer.write(
                subject_key=self.validator.infer_subject_key(),
                provider_id=self.provider_id,
                event_type=method,
                raw_payload={
                    "method": method,
                    "response": response,
                },
                reason=str(exc),
                schema_version=SHADOW_SCHEMA_VERSION,
            )
            raise
        self.replay_writer.write(event=event)

    async def _call_with_retry(self, request_payload: dict[str, object]) -> Any:
        require_active_worker_lease(
            operation="provider.alchemy_shadow.transport_retry",
            required_capabilities={CAP_PROVIDER_TRANSPORT},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        attempt = 0
        while True:
            try:
                return await asyncio.to_thread(self.rpc_caller, request_payload)
            except RetryableTransportError as exc:
                attempt += 1
                max_attempts = self.config.retry_backoff.max_attempts
                if max_attempts is not None and attempt > max_attempts:
                    raise RuntimeError(
                        f"Alchemy RPC retries exhausted for {request_payload['method']}"
                    ) from exc
                delay_seconds = self.config.retry_backoff.delay_for_attempt(attempt)
                self.logger.warning(
                    "Alchemy RPC transient failure for %s against %s; retry %s/%s in %.1fs: %s",
                    request_payload["method"],
                    self.redacted_endpoint,
                    attempt,
                    self.config.retry_backoff.describe_attempts(),
                    delay_seconds,
                    exc,
                )
                await asyncio.sleep(delay_seconds)
            except FatalTransportError:
                raise

    def _build_request(self, method: str, params: list[object]) -> dict[str, object]:
        self._request_id += 1
        return {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

    def _rpc_call_once(self, request_payload: dict[str, object]) -> Any:
        require_active_worker_lease(
            operation="provider.alchemy_shadow.transport_rpc",
            required_capabilities={CAP_PROVIDER_TRANSPORT},
            requested_scope=DEFAULT_SHADOW_INGEST_SCOPE,
            allowed_entrypoints={INGESTION_WORKER_ENTRYPOINT},
        )
        body = json.dumps(request_payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        req = urllib_request.Request(
            self.endpoint,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
                raw_body = response.read()
        except error.HTTPError as exc:
            raw_body = exc.read()
            detail = self._safe_error_detail(raw_body)
            if exc.code == 429 or 500 <= exc.code <= 599:
                raise RetryableTransportError(
                    f"HTTP {exc.code} for {request_payload['method']}: {detail}"
                ) from exc
            raise FatalTransportError(
                f"HTTP {exc.code} for {request_payload['method']}: {detail}"
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise RetryableTransportError(
                    f"timeout for {request_payload['method']} after {self.config.request_timeout_seconds:.1f}s"
                ) from exc
            raise RetryableTransportError(
                f"network error for {request_payload['method']}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise RetryableTransportError(
                f"timeout for {request_payload['method']} after {self.config.request_timeout_seconds:.1f}s"
            ) from exc
        except OSError as exc:
            raise RetryableTransportError(
                f"network error for {request_payload['method']}: {exc}"
            ) from exc

        if not raw_body or not raw_body.strip():
            raise FatalTransportError(f"empty response body for {request_payload['method']}")
        try:
            response_payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise FatalTransportError(
                f"invalid JSON response for {request_payload['method']}: {exc.msg}"
            ) from exc

        if isinstance(response_payload, dict) and "error" in response_payload:
            error_payload = response_payload["error"]
            error_code = error_payload.get("code") if isinstance(error_payload, dict) else None
            error_message = (
                error_payload.get("message")
                if isinstance(error_payload, dict)
                else str(error_payload)
            )
            if error_code in {-32000, -32005}:
                raise RetryableTransportError(
                    f"JSON-RPC retryable error for {request_payload['method']}: {error_message}"
                )
            raise FatalTransportError(
                f"JSON-RPC error for {request_payload['method']}: {error_message}"
            )
        return response_payload

    def _safe_error_detail(self, body: bytes) -> str:
        if not body:
            return "empty body"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body.decode("utf-8", errors="replace")
        if isinstance(payload, dict):
            if "error" in payload and isinstance(payload["error"], dict):
                return str(payload["error"].get("message", "unknown error"))
            if "message" in payload:
                return str(payload["message"])
        return json.dumps(payload, ensure_ascii=True)

    def _note_success(self) -> None:
        if self._degraded:
            self.logger.info(
                "Alchemy provider recovered after %s consecutive failures against %s",
                self._consecutive_failures,
                self.redacted_endpoint,
            )
        self._consecutive_failures = 0
        self._degraded = False

    def _note_failure(self, exc: Exception) -> None:
        self._consecutive_failures += 1
        self.logger.error(
            "Alchemy poll failed against %s (%s consecutive failures): %s",
            self.redacted_endpoint,
            self._consecutive_failures,
            exc,
        )
        if (
            not self._degraded
            and self._consecutive_failures >= self.config.degraded_after_failures
        ):
            self._degraded = True
            self.logger.error(
                "Alchemy provider entered degraded state after %s consecutive failures",
                self._consecutive_failures,
            )

    async def _recover_and_write_block_range(self, latest_block_number: str) -> bool:
        latest_int = int(latest_block_number, 16)
        previous_int = (latest_int - 1) if self._last_block_number is None else int(self._last_block_number, 16)
        if previous_int > latest_int:
            previous_int = latest_int - 1
        detail_written = False
        for block_int in range(previous_int + 1, latest_int + 1):
            block_hex = hex(block_int)
            detail_request = self._build_request("eth_getBlockByNumber", [block_hex, False])
            detail_response = await self._call_with_retry(detail_request)
            self._write_validated_response(
                method="eth_getBlockByNumber",
                request_id=detail_request["id"],
                response=detail_response,
            )
            self._remember_block_number(block_hex)
            detail_written = True
        if not detail_written:
            self._remember_block_number(latest_block_number)
        return detail_written

    def _remember_block_number(self, block_number: str) -> None:
        self._last_block_number = block_number
        self._write_checkpoint()

    def _load_checkpoint(self) -> str | None:
        for candidate in self._checkpoint_candidates():
            if not candidate.exists():
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            block_number = payload.get("last_block_number")
            if isinstance(block_number, str) and block_number.startswith("0x"):
                return block_number
        return None

    def _checkpoint_candidates(self) -> tuple[Path, ...]:
        candidates = [self.checkpoint_path]
        if self.legacy_checkpoint_path is not None and self.legacy_checkpoint_path != self.checkpoint_path:
            candidates.append(self.legacy_checkpoint_path)
        return tuple(candidates)

    def _write_checkpoint(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(
            json.dumps(
                {
                    "provider_id": self.provider_id,
                    "last_block_number": self._last_block_number,
                },
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )


AlchemyEvmShadowConfig = AlchemyEthShadowConfig
AlchemyEvmShadowProvider = AlchemyEthShadowProvider
