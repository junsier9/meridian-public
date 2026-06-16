from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_USDM_TESTNET_BASE_URL,
    BinanceUsdmClient,
    BinanceUsdmUnknownExecutionStatus,
)
from enhengclaw.live_trading.config import DEFAULT_LIVE_CONFIG_PATH, load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.order_router import (
    cancel_order_by_client_id,
    query_order_by_client_id,
    recover_unknown_order_status,
)
from enhengclaw.quant_research.contracts import write_json


MANUAL_LIFECYCLE_ACTIONS = ("query", "cancel", "recover")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Testnet-only manual Binance USD-M order lifecycle smoke runner. "
            "It requires an operator-supplied symbol and clientOrderId and never creates strategy orders."
        )
    )
    parser.add_argument("--config", default=str(DEFAULT_LIVE_CONFIG_PATH))
    parser.add_argument("--action", required=True, choices=MANUAL_LIFECYCLE_ACTIONS)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--client-order-id", required=True)
    parser.add_argument(
        "--user-event-jsonl",
        default="",
        help="Optional ORDER_TRADE_UPDATE fixture stream for recover smoke; accepts JSONL or a JSON array.",
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_manual_lifecycle(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_manual_lifecycle(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    action = str(getattr(args, "action", "") or "").strip().lower()
    symbol = str(getattr(args, "symbol", "") or "").strip().upper()
    client_order_id = str(getattr(args, "client_order_id", "") or "").strip()
    live_config = load_live_trading_config(getattr(args, "config", DEFAULT_LIVE_CONFIG_PATH))
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-manual-{action or 'unknown'}"
    run_root = live_config.artifact_root.parent / "manual_lifecycle" / run_id
    request_context = {
        "run_id": run_id,
        "action": action,
        "symbol": symbol,
        "client_order_id": client_order_id,
        "testnet_only": True,
        "base_url": BINANCE_USDM_TESTNET_BASE_URL,
        "strategy_order_generation": "disabled",
        "new_order_submission": "not_called",
    }
    blockers = _validation_blockers(args=args, action=action, symbol=symbol, client_order_id=client_order_id)
    if blockers:
        summary = _summary(
            run_id=run_id,
            action=action,
            symbol=symbol,
            client_order_id=client_order_id,
            status="blocked",
            blockers=blockers,
            started_at=started,
            artifact_root=run_root,
        )
        _persist_manual_artifacts(run_root, request_context=request_context, result={"status": "blocked"}, summary=summary)
        return summary, 2

    user_events = _read_user_events(getattr(args, "user_event_jsonl", ""))
    credentials = _resolve_credentials(live_config.payload, env or os.environ)
    result_payload: dict[str, Any]
    try:
        if action == "query":
            if credentials["blockers"]:
                raise _ManualLifecycleBlocked(credentials["blockers"])
            client = _build_testnet_client(credentials=credentials, client_factory=client_factory)
            result_payload = query_order_by_client_id(
                client,
                symbol=symbol,
                client_order_id=client_order_id,
            ).to_dict()
            status = "manual_query_resolved"
            exit_code = 0
        elif action == "cancel":
            if credentials["blockers"]:
                raise _ManualLifecycleBlocked(credentials["blockers"])
            client = _build_testnet_client(credentials=credentials, client_factory=client_factory)
            result_payload = cancel_order_by_client_id(
                client,
                symbol=symbol,
                client_order_id=client_order_id,
            ).to_dict()
            status = "manual_cancel_resolved"
            exit_code = 0
        else:
            if credentials["blockers"]:
                client = _MissingCredentialOrderClient(credentials["blockers"])
            else:
                client = _build_testnet_client(credentials=credentials, client_factory=client_factory)
            recovery = recover_unknown_order_status(
                client,
                symbol=symbol,
                client_order_id=client_order_id,
                user_events=user_events,
            )
            result_payload = recovery.to_dict()
            if recovery.status == "resolved":
                status = "manual_recovery_resolved"
                exit_code = 0
                blockers = []
            else:
                status = "manual_recovery_reconcile_required"
                blockers = [*credentials["blockers"], *recovery.blockers]
                exit_code = 2
    except _ManualLifecycleBlocked as exc:
        status = "blocked"
        result_payload = {"status": "blocked", "blockers": exc.blockers}
        blockers = exc.blockers
        exit_code = 2
    except BinanceUsdmUnknownExecutionStatus as exc:
        status = "manual_unknown_status_recovery_required"
        result_payload = {
            "status": "unknown_execution_status",
            "next_action": "run_manual_lifecycle_recover",
            "detail": str(exc),
        }
        blockers = [f"binance_unknown_execution_status:{exc}"]
        exit_code = 2
    except Exception as exc:
        status = "blocked"
        result_payload = {
            "status": "failed",
            "exception_type": type(exc).__name__,
            "detail": str(exc),
        }
        blockers = [f"manual_lifecycle_failed:{type(exc).__name__}:{exc}"]
        exit_code = 2

    summary = _summary(
        run_id=run_id,
        action=action,
        symbol=symbol,
        client_order_id=client_order_id,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
        result_source=result_payload.get("source"),
        order_status=result_payload.get("status") if action in {"query", "cancel"} else result_payload.get("order_status"),
    )
    _persist_manual_artifacts(run_root, request_context=request_context, result=result_payload, summary=summary)
    return summary, exit_code


def _validation_blockers(
    *,
    args: argparse.Namespace,
    action: str,
    symbol: str,
    client_order_id: str,
) -> list[str]:
    blockers: list[str] = []
    if action not in MANUAL_LIFECYCLE_ACTIONS:
        blockers.append(f"manual_lifecycle_unsupported_action:{action}")
    if not symbol:
        blockers.append("manual_lifecycle_requires_symbol")
    if not client_order_id:
        blockers.append("manual_lifecycle_requires_client_order_id")
    base_url = str(getattr(args, "base_url", BINANCE_USDM_TESTNET_BASE_URL) or "").strip().rstrip("/")
    if base_url != BINANCE_USDM_TESTNET_BASE_URL:
        blockers.append("manual_lifecycle_testnet_only")
    return blockers


def _resolve_credentials(payload: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_API_KEY").strip()
    api_secret_env = str(binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_API_SECRET").strip()
    api_key = str(getenv_compat(api_key_env, "", env=env) or "").strip()
    api_secret = str(getenv_compat(api_secret_env, "", env=env) or "").strip()
    blockers: list[str] = []
    if not api_key:
        blockers.append(f"missing_api_key_env:{api_key_env}")
    if not api_secret:
        blockers.append(f"missing_api_secret_env:{api_secret_env}")
    return {
        "api_key_env": api_key_env,
        "api_secret_env": api_secret_env,
        "api_key": api_key,
        "api_secret": api_secret,
        "recv_window_ms": int(binance.get("recv_window_ms") or 5000),
        "timeout_seconds": float(binance.get("timeout_seconds") or 10.0),
        "blockers": blockers,
    }


def _build_testnet_client(*, credentials: dict[str, Any], client_factory: Callable[..., Any]) -> Any:
    return client_factory(
        base_url=BINANCE_USDM_TESTNET_BASE_URL,
        api_key=credentials["api_key"],
        api_secret=credentials["api_secret"],
        recv_window_ms=credentials["recv_window_ms"],
        timeout_seconds=credentials["timeout_seconds"],
    )


def _read_user_events(path_ref: str | Path | None) -> list[dict[str, Any]]:
    if not str(path_ref or "").strip():
        return []
    path = resolve_repo_path(str(path_ref))
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("user_event_jsonl JSON array must contain event objects")
        return [dict(item) for item in payload]
    if text.startswith("{") and "\n" not in text:
        return [dict(json.loads(text))]
    events: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"user_event_jsonl line {line_number} is not a JSON object")
        events.append(dict(payload))
    return events


class _ManualLifecycleBlocked(RuntimeError):
    def __init__(self, blockers: list[str]) -> None:
        super().__init__(", ".join(blockers))
        self.blockers = blockers


class _MissingCredentialOrderClient:
    def __init__(self, blockers: list[str]) -> None:
        self.blockers = blockers

    def query_order(self, **_: Any) -> Any:
        raise RuntimeError(";".join(self.blockers))


def _summary(
    *,
    run_id: str,
    action: str,
    symbol: str,
    client_order_id: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    result_source: str | None = None,
    order_status: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "action": action,
        "symbol": symbol,
        "client_order_id": client_order_id,
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "result_source": result_source,
        "order_status": order_status,
        "artifact_root": str(artifact_root),
        "testnet_only": True,
        "base_url": BINANCE_USDM_TESTNET_BASE_URL,
    }


def _persist_manual_artifacts(
    run_root: Path,
    *,
    request_context: dict[str, Any],
    result: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    write_json(run_root / "request_context.json", request_context)
    write_json(run_root / "lifecycle_result.json", result)
    write_json(run_root / "run_summary.json", summary)


if __name__ == "__main__":
    raise SystemExit(main())
