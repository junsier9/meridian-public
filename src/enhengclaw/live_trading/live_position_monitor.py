from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.live_trading.binance_usdm_client import (
    BINANCE_SPOT_MAINNET_BASE_URL,
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmClient,
)
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path
from enhengclaw.live_trading.live_risk_controls import classify_exception_strategy
from enhengclaw.quant_research.contracts import read_json, write_json


READ_ONLY_ENDPOINTS = {
    "account_information_v3": "/fapi/v3/account",
    "account_config": "/fapi/v1/accountConfig",
    "position_mode": "/fapi/v1/positionSide/dual",
    "open_orders": "/fapi/v1/openOrders",
    "position_information_v2": "/fapi/v2/positionRisk",
    "api_key_permissions": "/sapi/v1/account/apiRestrictions",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Binance USD-M mainnet live position monitor for the hv_balanced first pilot. "
            "It never submits, tests, or cancels orders."
        )
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml")
    parser.add_argument(
        "--reference-run",
        default="",
        help=(
            "Reference artifact directory. Supports a reconciled mainnet delta execution, a genesis snapshot, "
            "or a mainnet single-run. Defaults to the latest valid reference for the config."
        ),
    )
    parser.add_argument("--api-key-env", default="", help="Override API key environment variable name.")
    parser.add_argument("--api-secret-env", default="", help="Override API secret environment variable name.")
    parser.add_argument("--max-abs-position-drift-qty", type=float, default=1e-9)
    args = parser.parse_args(argv)
    summary, exit_code = run_live_position_monitor(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_live_position_monitor(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
    mainnet_client_factory: Callable[..., Any] = BinanceUsdmClient,
    permission_client_factory: Callable[..., Any] = BinanceUsdmClient,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    started = (now_fn or (lambda: datetime.now(UTC)))()
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    live_config = load_live_trading_config(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm_live_pilot_executable_candidate.yaml"))
    payload = live_config.payload
    run_id = f"{started.strftime('%Y%m%dT%H%M%S%fZ')}-mainnet-position-monitor"
    run_root = live_config.artifact_root.parent / "position_monitor" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = _config_blockers(payload)
    reference_run, reference_blockers = _resolve_reference_run(live_config.artifact_root, str(getattr(args, "reference_run", "") or ""))
    blockers.extend(reference_blockers)
    reference_context: dict[str, Any] = {
        "reference_run": str(reference_run) if reference_run else None,
        "reference_type": _reference_type(reference_run) if reference_run else None,
    }
    expected_positions, target_context, expected_blockers = _load_reference_expected_positions(reference_run) if reference_run else ({}, [], [])
    blockers.extend(expected_blockers)

    credentials = _credential_context(payload=payload, args=args, env=env or os.environ)
    blockers.extend(credentials["blockers"])
    request_context = {
        "run_id": run_id,
        "environment": "mainnet",
        "base_url": BINANCE_USDM_MAINNET_BASE_URL,
        "read_only": True,
        "reference": reference_context,
        "api_key_env": credentials["api_key_env"],
        "api_secret_env": credentials["api_secret_env"],
        "api_key_present": credentials["api_key_present"],
        "api_secret_present": credentials["api_secret_present"],
        "api_key_length": credentials["api_key_length"],
        "api_secret_length": credentials["api_secret_length"],
        "endpoint_paths": READ_ONLY_ENDPOINTS,
        "forbidden_methods": [
            "new_order",
            "new_order_test",
            "submit_manual_live_order_smoke",
            "submit_mainnet_strategy_single_run_order",
            "cancel_order",
        ],
    }

    endpoint_results: dict[str, dict[str, Any]] = {}
    account_payload: dict[str, Any] | None = None
    account_config_payload: dict[str, Any] | None = None
    position_mode_payload: dict[str, Any] | None = None
    open_orders_payload: list[dict[str, Any]] | None = None
    position_risk_payload: list[dict[str, Any]] | None = None
    api_permissions_payload: dict[str, Any] | None = None
    if not credentials["blockers"]:
        mainnet_client = mainnet_client_factory(
            base_url=BINANCE_USDM_MAINNET_BASE_URL,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
            recv_window_ms=credentials["recv_window_ms"],
            timeout_seconds=credentials["timeout_seconds"],
        )
        permission_client = permission_client_factory(
            base_url=BINANCE_SPOT_MAINNET_BASE_URL,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
            recv_window_ms=credentials["recv_window_ms"],
            timeout_seconds=credentials["timeout_seconds"],
        )
        account_payload = _safe_endpoint_call(endpoint_results, "account_information_v3", mainnet_client.account_information_v3)
        account_config_payload = _safe_endpoint_call(endpoint_results, "account_config", mainnet_client.account_config)
        position_mode_payload = _safe_endpoint_call(endpoint_results, "position_mode", mainnet_client.position_mode)
        open_orders_payload = _safe_endpoint_list(endpoint_results, "open_orders", mainnet_client.current_all_open_orders)
        position_risk_payload = _safe_endpoint_list(endpoint_results, "position_information_v2", mainnet_client.position_information_v2)
        api_permissions_payload = _safe_endpoint_call(
            endpoint_results,
            "api_key_permissions",
            permission_client.api_key_restrictions,
            base_url=BINANCE_SPOT_MAINNET_BASE_URL,
        )
    else:
        for name in READ_ONLY_ENDPOINTS:
            endpoint_results[name] = {"path": READ_ONLY_ENDPOINTS[name], "status": "not_called_missing_credentials"}

    blockers.extend(_endpoint_blockers(endpoint_results))
    account_summary = _account_summary(account_payload, account_config_payload)
    position_mode = _position_mode(position_mode_payload, account_config_payload)
    open_orders = _redacted_open_orders(open_orders_payload or [])
    position_rows = _position_rows(position_risk_payload or [], account_payload or {})
    api_permissions = _redacted_api_key_permissions(api_permissions_payload or {})

    expected_position_rows = _expected_position_rows(expected_positions, target_context=target_context)
    blockers.extend(
        _semantic_blockers(
            payload,
            account_summary=account_summary,
            position_mode=position_mode,
            open_orders=open_orders,
            position_rows=position_rows,
            expected_positions=expected_positions,
            api_permissions=api_permissions,
            max_abs_drift_qty=float(getattr(args, "max_abs_position_drift_qty", 1e-9) or 1e-9),
        )
    )
    current_rows = _current_position_rows_for_report(position_rows, expected_positions=expected_positions)
    comparison_rows = _position_comparison_rows(
        expected_positions=expected_positions,
        current_positions={row["symbol"]: float(row["position_amt"]) for row in position_rows},
        max_abs_drift_qty=float(getattr(args, "max_abs_position_drift_qty", 1e-9) or 1e-9),
    )
    decision = _operator_decision(
        blockers=blockers,
        open_order_count=len(open_orders),
        open_position_count=sum(1 for row in position_rows if abs(float(row["position_amt"])) > 0.0),
        expected_position_count=len(expected_positions),
        total_unrealized_pnl_usdt=sum(float(row.get("unrealized_pnl_usdt") or 0.0) for row in position_rows),
        total_abs_notional_usdt=sum(abs(float(row.get("notional_usdt") or 0.0)) for row in position_rows),
    )
    status = "passed_live_position_monitor" if not blockers else "blocked_live_position_monitor"
    monitor_report = {
        "status": status,
        "blockers": sorted(set(blockers)),
        "environment": "mainnet",
        "read_only": True,
        "reference_run": str(reference_run) if reference_run else None,
        "account": account_summary,
        "position_mode": position_mode,
        "api_key_permissions": api_permissions,
        "open_orders": {
            "open_order_count": len(open_orders),
            "open_orders_redacted": open_orders,
        },
        "expected_position_count": len(expected_positions),
        "current_position_count": sum(1 for row in position_rows if abs(float(row["position_amt"])) > 0.0),
        "total_abs_notional_usdt": decision["current_state"]["total_abs_notional_usdt"],
        "total_unrealized_pnl_usdt": decision["current_state"]["total_unrealized_pnl_usdt"],
        "position_comparison": comparison_rows,
        "operator_decision": decision,
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "account_settings_changed": 0,
            "only_http_get_endpoints": True,
        },
    }
    summary = _summary(
        run_id=run_id,
        status=status,
        blockers=blockers,
        started_at=started,
        artifact_root=run_root,
        reference_run=reference_run,
        account_summary=account_summary,
        position_mode=position_mode,
        decision=decision,
        open_order_count=len(open_orders),
        open_position_count=sum(1 for row in position_rows if abs(float(row["position_amt"])) > 0.0),
    )
    _write_artifacts(
        run_root,
        request_context=request_context,
        monitor_report=monitor_report,
        summary=summary,
        endpoint_results=endpoint_results,
        current_rows=current_rows,
        expected_rows=expected_position_rows,
        comparison_rows=comparison_rows,
        open_orders=open_orders,
        decision=decision,
    )
    return summary, 0 if status == "passed_live_position_monitor" else 2


def _resolve_reference_run(artifact_root: Path, raw_reference: str) -> tuple[Path | None, list[str]]:
    if raw_reference.strip():
        path = resolve_repo_path(raw_reference.strip())
        if not path.exists():
            return path, [f"reference_run_missing:{path}"]
        return path, []
    candidates: list[tuple[tuple[datetime, int, str], Path]] = []
    parent = artifact_root.parent
    if artifact_root.exists():
        for child in artifact_root.iterdir():
            if not child.is_dir() or not child.name.endswith("-mainnet-single-run"):
                continue
            summary_path = child / "run_summary.json"
            if not summary_path.exists():
                continue
            try:
                summary = dict(read_json(summary_path))
            except Exception:
                continue
            if summary.get("status") == "mainnet_single_run_orders_submitted":
                candidates.append((_reference_candidate_sort_key(child, summary=summary, priority=1), child))
    delta_root = parent / "mainnet_delta_execution"
    if delta_root.exists():
        for child in delta_root.iterdir():
            if not child.is_dir() or not child.name.endswith("-mainnet-delta-execution"):
                continue
            summary_path = child / "run_summary.json"
            reconciliation_path = child / "reconciliation.json"
            if not summary_path.exists() or not reconciliation_path.exists():
                continue
            try:
                summary = dict(read_json(summary_path))
                reconciliation = dict(read_json(reconciliation_path))
            except Exception:
                continue
            if (
                summary.get("status") == "mainnet_delta_orders_submitted"
                and summary.get("reconciliation_status") == "reconciled"
                and reconciliation.get("status") == "reconciled"
            ):
                candidates.append((_reference_candidate_sort_key(child, summary=summary, priority=2), child))
    reference_root = parent / "position_reference"
    if reference_root.exists():
        for child in reference_root.iterdir():
            if not child.is_dir() or not child.name.endswith("-genesis-snapshot"):
                continue
            summary_path = child / "run_summary.json"
            if not summary_path.exists():
                continue
            try:
                summary = dict(read_json(summary_path))
            except Exception:
                continue
            if summary.get("status") in {"mainnet_position_genesis_snapshot", "position_genesis_snapshot"}:
                candidates.append((_reference_candidate_sort_key(child, summary=summary, priority=0), child))
    if not candidates:
        return None, [f"no_valid_position_reference_under:{parent}"]
    return sorted(candidates, key=lambda item: item[0])[-1][1], []


def _reference_candidate_sort_key(child: Path, *, summary: dict[str, Any], priority: int) -> tuple[datetime, int, str]:
    return (_reference_candidate_time(child, summary=summary), int(priority), child.name)


def _reference_candidate_time(child: Path, *, summary: dict[str, Any]) -> datetime:
    for key in ("finished_at_utc", "created_at_utc", "started_at_utc", "updated_at_utc"):
        parsed = _parse_reference_time(summary.get(key))
        if parsed is not None:
            return parsed
    parsed_from_name = _parse_reference_time(child.name)
    if parsed_from_name is not None:
        return parsed_from_name
    return datetime.fromtimestamp(child.stat().st_mtime, tz=UTC)


def _parse_reference_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    match = re.search(r"(\d{8}T\d{6}(?:\d{1,6})?Z)", text)
    if match is None:
        return None
    compact = match.group(1)
    for fmt in ("%Y%m%dT%H%M%S%fZ", "%Y%m%dT%H%M%SZ"):
        try:
            return datetime.strptime(compact, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _load_reference_expected_positions(reference_run: Path) -> tuple[dict[str, float], list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    kind = _reference_type(reference_run)
    if kind == "mainnet_delta_execution":
        return _load_delta_reference_expected_positions(reference_run)
    if kind == "genesis_snapshot":
        return _load_genesis_reference_expected_positions(reference_run)
    fills_path = reference_run / "fills.csv"
    target_path = reference_run / "target_positions.csv"
    expected: dict[str, float] = {}
    target_rows: list[dict[str, Any]] = []
    if not fills_path.exists():
        blockers.append(f"reference_fills_missing:{fills_path}")
    else:
        fills = pd.read_csv(fills_path)
        for _, row in fills.iterrows():
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            quantity = _float(row.get("quantity"))
            signed = quantity if str(row.get("side") or "").upper() == "BUY" else -quantity
            expected[symbol] = expected.get(symbol, 0.0) + signed
    if not expected:
        blockers.append("reference_expected_positions_empty")
    if target_path.exists():
        target_frame = pd.read_csv(target_path)
        target_rows = [dict(row) for _, row in target_frame.iterrows()]
    else:
        blockers.append(f"reference_target_positions_missing:{target_path}")
    return expected, target_rows, blockers


def _reference_type(reference_run: Path | None) -> str:
    if reference_run is None:
        return "missing"
    name = reference_run.name
    if name.endswith("-mainnet-delta-execution"):
        return "mainnet_delta_execution"
    if name.endswith("-genesis-snapshot"):
        return "genesis_snapshot"
    if name.endswith("-mainnet-single-run"):
        return "mainnet_single_run"
    summary_path = reference_run / "run_summary.json"
    if summary_path.exists():
        try:
            status = str(dict(read_json(summary_path)).get("status") or "")
        except Exception:
            status = ""
        if status == "mainnet_delta_orders_submitted":
            return "mainnet_delta_execution"
        if status in {"mainnet_position_genesis_snapshot", "position_genesis_snapshot"}:
            return "genesis_snapshot"
    return "mainnet_single_run"


def _load_delta_reference_expected_positions(reference_run: Path) -> tuple[dict[str, float], list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    reconciliation_path = reference_run / "reconciliation.json"
    account_after_path = reference_run / "account_after.json"
    expected: dict[str, float] = {}
    target_rows: list[dict[str, Any]] = []
    if reconciliation_path.exists():
        reconciliation = dict(read_json(reconciliation_path))
        for symbol, amount in dict(reconciliation.get("expected_positions") or {}).items():
            expected[str(symbol).upper()] = float(amount)
        for row in list(reconciliation.get("open_positions_redacted") or []):
            if isinstance(row, dict):
                target_rows.append(dict(row))
    if not expected and account_after_path.exists():
        account_after = dict(read_json(account_after_path))
        for row in list(account_after.get("open_positions_redacted") or []):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if symbol:
                expected[symbol] = _float(row.get("positionAmt"))
                target_rows.append(dict(row))
    if not expected:
        blockers.append(f"delta_reference_expected_positions_empty:{reference_run}")
    return expected, target_rows, blockers


def _load_genesis_reference_expected_positions(reference_run: Path) -> tuple[dict[str, float], list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    expected: dict[str, float] = {}
    target_rows: list[dict[str, Any]] = []
    csv_path = reference_run / "reference_positions.csv"
    json_path = reference_run / "genesis_snapshot.json"
    if csv_path.exists():
        frame = pd.read_csv(csv_path)
        for _, row in frame.iterrows():
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            amount = row.get("expected_position_amt")
            if amount is None:
                amount = row.get("positionAmt")
            if amount is None:
                amount = row.get("position_amt")
            expected[symbol] = _float(amount)
            target_rows.append(dict(row))
    elif json_path.exists():
        payload = dict(read_json(json_path))
        for row in list(payload.get("positions") or []):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            amount = row.get("expected_position_amt")
            if amount is None:
                amount = row.get("positionAmt")
            if amount is None:
                amount = row.get("position_amt")
            expected[symbol] = _float(amount)
            target_rows.append(dict(row))
    else:
        blockers.append(f"genesis_reference_positions_missing:{reference_run}")
    if not expected:
        blockers.append("genesis_reference_expected_positions_empty")
    return expected, target_rows, blockers


def _safe_endpoint_call(
    endpoint_results: dict[str, dict[str, Any]],
    name: str,
    fn: Callable[[], Any],
    *,
    base_url: str | None = None,
) -> dict[str, Any] | None:
    try:
        response = fn()
    except Exception as exc:
        endpoint_results[name] = {
            "path": READ_ONLY_ENDPOINTS[name],
            "base_url": base_url,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        return None
    payload = response.payload
    endpoint_results[name] = {
        "path": READ_ONLY_ENDPOINTS[name],
        "base_url": base_url,
        "status": "ok",
        "status_code": int(getattr(response, "status_code", 200)),
    }
    return dict(payload) if isinstance(payload, dict) else None


def _safe_endpoint_list(
    endpoint_results: dict[str, dict[str, Any]],
    name: str,
    fn: Callable[[], Any],
) -> list[dict[str, Any]] | None:
    try:
        response = fn()
    except Exception as exc:
        endpoint_results[name] = {
            "path": READ_ONLY_ENDPOINTS[name],
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        return None
    payload = response.payload
    endpoint_results[name] = {
        "path": READ_ONLY_ENDPOINTS[name],
        "status": "ok",
        "status_code": int(getattr(response, "status_code", 200)),
    }
    return [dict(item) for item in list(payload or []) if isinstance(item, dict)]


def _endpoint_blockers(endpoint_results: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for name in sorted(READ_ONLY_ENDPOINTS):
        result = dict(endpoint_results.get(name) or {})
        if result.get("status") == "ok":
            continue
        if result.get("status") == "not_called_missing_credentials":
            blockers.append(f"read_only_endpoint_not_called:{name}:missing_credentials")
            continue
        blockers.append(f"read_only_endpoint_failed:{name}:{result.get('error_type')}:{result.get('error')}")
    return blockers


def _semantic_blockers(
    payload: dict[str, Any],
    *,
    account_summary: dict[str, Any],
    position_mode: dict[str, Any],
    open_orders: list[dict[str, Any]],
    position_rows: list[dict[str, Any]],
    expected_positions: dict[str, float],
    api_permissions: dict[str, Any],
    max_abs_drift_qty: float,
) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    expected_mode = _normalize_position_mode(binance.get("position_mode") or "one_way")
    expected_margin_type = str(binance.get("margin_type") or "").strip().lower()
    max_leverage = _max_allowed_leverage(binance)
    if account_summary.get("can_trade") is not True:
        blockers.append(f"mainnet_account_canTrade_not_true:{account_summary.get('can_trade')}")
    actual_mode = _normalize_position_mode(position_mode.get("mode"))
    if expected_mode and actual_mode != expected_mode:
        blockers.append(f"position_mode_mismatch:expected={expected_mode}:actual={actual_mode or 'unknown'}")
    if open_orders:
        blockers.append(f"mainnet_open_orders_exist:{len(open_orders)}")
    blockers.extend(_api_permission_blockers(api_permissions))
    actual_by_symbol = {str(row["symbol"]): row for row in position_rows}
    expected_symbols = set(expected_positions)
    for row in position_rows:
        symbol = str(row["symbol"])
        amount = float(row["position_amt"])
        if abs(amount) <= max_abs_drift_qty:
            continue
        if symbol not in expected_symbols:
            blockers.append(f"unexpected_live_position:{symbol}:{amount}")
    for symbol, expected_amount in sorted(expected_positions.items()):
        actual = float((actual_by_symbol.get(symbol) or {}).get("position_amt") or 0.0)
        drift = actual - float(expected_amount)
        if abs(drift) > max_abs_drift_qty:
            blockers.append(f"position_mismatch:{symbol}:expected={expected_amount}:actual={actual}:drift={drift}")
        row = actual_by_symbol.get(symbol)
        if row is None:
            if abs(float(expected_amount)) > max_abs_drift_qty or abs(actual) > max_abs_drift_qty:
                blockers.append(f"position_risk_missing:{symbol}")
            continue
        margin_type = str(row.get("margin_type") or "").strip().lower()
        if expected_margin_type and margin_type != expected_margin_type:
            blockers.append(f"margin_type_mismatch:{symbol}:expected={expected_margin_type}:actual={margin_type or 'missing'}")
        leverage = int(_float(row.get("leverage")))
        if max_leverage > 0 and leverage > max_leverage:
            blockers.append(f"leverage_above_max:{symbol}:max={max_leverage}:actual={leverage}")
        if _normalize_position_mode(row.get("position_side") or "BOTH") != "one_way":
            blockers.append(f"position_side_not_one_way:{symbol}:{row.get('position_side')}")
    return blockers


def _operator_decision(
    *,
    blockers: list[str],
    open_order_count: int,
    open_position_count: int,
    expected_position_count: int,
    total_unrealized_pnl_usdt: float,
    total_abs_notional_usdt: float,
) -> dict[str, Any]:
    current_state = {
        "open_order_count": int(open_order_count),
        "open_position_count": int(open_position_count),
        "expected_position_count": int(expected_position_count),
        "total_unrealized_pnl_usdt": float(total_unrealized_pnl_usdt),
        "total_abs_notional_usdt": float(total_abs_notional_usdt),
    }
    exception_policy = classify_exception_strategy(blockers, context=current_state)
    if blockers:
        recommendation = "STOP_NEW_ENTRIES_FORCED_RECONCILE_REVIEW"
        rationale = exception_policy["rationale"]
        allowed = list(exception_policy["allowed_next_actions"])
    else:
        recommendation = "HOLD_MANUAL_MONITOR"
        rationale = (
            "Live positions match the explicitly submitted first single-run fills, no open orders were observed, "
            "and account settings remain within one-way cross max-2x bounds."
        )
        allowed = [
            "hold_and_monitor",
            "reduce_only_manual_plan_after_explicit_confirmation",
            "flatten_after_explicit_reduce_only_confirmation",
            "next_rebalance_only_after_current_position_aware_plan_gate",
        ]
    return {
        "recommendation": recommendation,
        "rationale": rationale,
        "current_state": current_state,
        "allowed_next_actions": allowed,
        "disallowed_next_actions": [
            "recurring_mainnet_loop",
            "new_mainnet_entry_without_fresh_monitor",
            "blind_rebalance_from_flat_assumption",
            "non_reduce_only_risk_reduction",
        ],
        "next_rebalance_gate": {
            "requires_current_position_aware_execution_plan": True,
            "requires_fresh_read_only_monitor": True,
            "requires_explicit_single_run_confirmation": True,
            "recurring_mainnet_authorized": False,
        },
        "exception_policy": exception_policy,
    }


def _write_artifacts(
    run_root: Path,
    *,
    request_context: dict[str, Any],
    monitor_report: dict[str, Any],
    summary: dict[str, Any],
    endpoint_results: dict[str, dict[str, Any]],
    current_rows: list[dict[str, Any]],
    expected_rows: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
    decision: dict[str, Any],
) -> None:
    write_json(run_root / "request_context.json", request_context)
    write_json(run_root / "endpoint_results.json", endpoint_results)
    write_json(run_root / "monitor_report.json", monitor_report)
    write_json(run_root / "operator_decision_matrix.json", decision)
    write_json(run_root / "run_summary.json", summary)
    pd.DataFrame(current_rows).to_csv(run_root / "current_positions.csv", index=False)
    pd.DataFrame(expected_rows).to_csv(run_root / "expected_positions.csv", index=False)
    pd.DataFrame(comparison_rows).to_csv(run_root / "position_comparison.csv", index=False)
    pd.DataFrame(open_orders).to_csv(run_root / "open_orders.csv", index=False)


def _summary(
    *,
    run_id: str,
    status: str,
    blockers: list[str],
    started_at: datetime,
    artifact_root: Path,
    reference_run: Path | None,
    account_summary: dict[str, Any],
    position_mode: dict[str, Any],
    decision: dict[str, Any],
    open_order_count: int,
    open_position_count: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "environment": "mainnet",
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "artifact_root": str(artifact_root),
        "reference_run": str(reference_run) if reference_run else None,
        "read_only": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "account_settings_changed": 0,
        "can_trade": account_summary.get("can_trade"),
        "position_mode": position_mode.get("mode"),
        "open_order_count": int(open_order_count),
        "open_position_count": int(open_position_count),
        "operator_recommendation": decision["recommendation"],
        "recurring_mainnet_enabled": False,
    }


def _config_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    binance = dict(payload.get("binance") or {})
    venue = str(binance.get("venue") or "").strip().lower()
    if venue != "usdm_futures":
        blockers.append(f"live_position_monitor_requires_mainnet_usdm_venue:actual={venue or 'missing'}")
    max_leverage = _max_allowed_leverage(binance)
    if max_leverage <= 0:
        blockers.append("live_position_monitor_requires_positive_max_leverage")
    if max_leverage > 2:
        blockers.append(f"live_position_monitor_max_leverage_above_pilot_cap:{max_leverage}>2")
    return blockers


def _credential_context(
    *,
    payload: dict[str, Any],
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    api_key_env = str(getattr(args, "api_key_env", "") or binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_API_KEY").strip()
    api_secret_env = str(
        getattr(args, "api_secret_env", "") or binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_API_SECRET"
    ).strip()
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
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "api_key_length": len(api_key),
        "api_secret_length": len(api_secret),
        "recv_window_ms": int(binance.get("recv_window_ms") or 5000),
        "timeout_seconds": float(binance.get("timeout_seconds") or 10.0),
        "blockers": blockers,
    }


def _account_summary(account_payload: dict[str, Any] | None, config_payload: dict[str, Any] | None) -> dict[str, Any]:
    account = dict(account_payload or {})
    config = dict(config_payload or {})
    can_trade = _optional_bool(account.get("canTrade"))
    if can_trade is None:
        can_trade = _optional_bool(config.get("canTrade"))
    return {
        "account_readable": bool(account),
        "account_config_readable": bool(config),
        "can_trade": can_trade,
        "available_balance_usdt": _float(account.get("availableBalance")),
        "total_wallet_balance_usdt": _float(account.get("totalWalletBalance")),
        "total_margin_balance_usdt": _float(account.get("totalMarginBalance")),
    }


def _position_mode(position_payload: dict[str, Any] | None, config_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(position_payload or {})
    fallback = dict(config_payload or {})
    dual = _optional_bool(payload.get("dualSidePosition"))
    if dual is None:
        dual = _optional_bool(fallback.get("dualSidePosition"))
    mode = None
    if dual is not None:
        mode = "hedge" if dual else "one_way"
    return {
        "position_mode_readable": bool(position_payload),
        "dual_side_position": dual,
        "mode": mode,
    }


def _position_rows(position_risk_payload: list[dict[str, Any]], account_payload: dict[str, Any]) -> list[dict[str, Any]]:
    account_positions = {
        str(item.get("symbol") or "").upper(): dict(item)
        for item in list(account_payload.get("positions") or [])
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in position_risk_payload:
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        seen.add(symbol)
        amount = _float(item.get("positionAmt"))
        if abs(amount) <= 1e-12:
            continue
        rows.append(_normalized_position_row(symbol, item, fallback=account_positions.get(symbol, {})))
    for symbol, item in sorted(account_positions.items()):
        if symbol in seen:
            continue
        amount = _float(item.get("positionAmt"))
        if abs(amount) <= 1e-12:
            continue
        rows.append(_normalized_position_row(symbol, item, fallback={}))
    return sorted(rows, key=lambda row: row["symbol"])


def _normalized_position_row(symbol: str, item: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    amount = _float(item.get("positionAmt"))
    unrealized = item.get("unRealizedProfit")
    if unrealized is None:
        unrealized = item.get("unrealizedProfit")
    if unrealized is None:
        unrealized = fallback.get("unrealizedProfit")
    return {
        "symbol": symbol,
        "position_side": str(item.get("positionSide") or fallback.get("positionSide") or "BOTH"),
        "position_amt": float(amount),
        "notional_usdt": float(_float(item.get("notional") if item.get("notional") is not None else fallback.get("notional"))),
        "entry_price": float(_float(item.get("entryPrice") if item.get("entryPrice") is not None else fallback.get("entryPrice"))),
        "mark_price": float(_float(item.get("markPrice"))),
        "unrealized_pnl_usdt": float(_float(unrealized)),
        "margin_type": str(item.get("marginType") or ""),
        "leverage": int(_float(item.get("leverage"))),
        "isolated": _optional_bool(item.get("isolated")),
    }


def _expected_position_rows(expected_positions: dict[str, float], *, target_context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_by_symbol = {str(row.get("usdm_symbol") or "").upper(): row for row in target_context}
    rows: list[dict[str, Any]] = []
    for symbol, amount in sorted(expected_positions.items()):
        target = target_by_symbol.get(symbol, {})
        rows.append(
            {
                "symbol": symbol,
                "expected_position_amt": float(amount),
                "target_side": str(target.get("side") or ""),
                "target_notional_usdt": _float(target.get("target_notional_usdt")),
                "target_weight": _float(target.get("target_weight")),
                "selection_reason": str(target.get("selection_reason") or ""),
            }
        )
    return rows


def _current_position_rows_for_report(
    position_rows: list[dict[str, Any]],
    *,
    expected_positions: dict[str, float],
) -> list[dict[str, Any]]:
    expected_symbols = set(expected_positions)
    rows: list[dict[str, Any]] = []
    for row in position_rows:
        item = dict(row)
        item["expected_by_reference_run"] = str(row.get("symbol") or "") in expected_symbols
        rows.append(item)
    return rows


def _position_comparison_rows(
    *,
    expected_positions: dict[str, float],
    current_positions: dict[str, float],
    max_abs_drift_qty: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(expected_positions) | set(current_positions)):
        expected = float(expected_positions.get(symbol, 0.0))
        actual = float(current_positions.get(symbol, 0.0))
        drift = actual - expected
        rows.append(
            {
                "symbol": symbol,
                "expected_position_amt": expected,
                "actual_position_amt": actual,
                "drift_position_amt": drift,
                "within_tolerance": abs(drift) <= max_abs_drift_qty,
            }
        )
    return rows


def _redacted_open_orders(open_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": str(item.get("symbol") or ""),
            "orderId": item.get("orderId"),
            "clientOrderId": str(item.get("clientOrderId") or ""),
            "side": str(item.get("side") or ""),
            "positionSide": str(item.get("positionSide") or ""),
            "status": str(item.get("status") or ""),
            "type": str(item.get("type") or ""),
            "origQty": str(item.get("origQty") or ""),
            "executedQty": str(item.get("executedQty") or ""),
            "reduceOnly": bool(item.get("reduceOnly", False)),
        }
        for item in open_orders
    ]


def _redacted_api_key_permissions(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "api_key_permissions_readable": bool(payload),
        "ip_restrict": _optional_bool(payload.get("ipRestrict")),
        "enable_reading": _optional_bool(payload.get("enableReading")),
        "enable_futures": _optional_bool(payload.get("enableFutures")),
        "enable_withdrawals": _optional_bool(payload.get("enableWithdrawals")),
        "enable_margin": _optional_bool(payload.get("enableMargin")),
        "enable_spot_and_margin_trading": _optional_bool(payload.get("enableSpotAndMarginTrading")),
        "permits_universal_transfer": _optional_bool(payload.get("permitsUniversalTransfer")),
        "trading_authority_expiration_time": payload.get("tradingAuthorityExpirationTime"),
    }


def _api_permission_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not payload.get("api_key_permissions_readable"):
        return ["api_key_permissions_unreadable"]
    if payload.get("enable_reading") is not True:
        blockers.append(f"api_key_enableReading_not_true:{payload.get('enable_reading')}")
    if payload.get("enable_futures") is not True:
        blockers.append(f"api_key_enableFutures_not_true:{payload.get('enable_futures')}")
    if payload.get("enable_withdrawals") is not False:
        blockers.append(f"api_key_enableWithdrawals_not_false:{payload.get('enable_withdrawals')}")
    if payload.get("ip_restrict") is not True:
        blockers.append(f"api_key_ipRestrict_not_true:{payload.get('ip_restrict')}")
    return blockers


def _max_allowed_leverage(binance: dict[str, Any]) -> int:
    raw = binance.get("max_leverage")
    if raw is None:
        raw = binance.get("leverage")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_position_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"oneway", "one_way", "single", "both"}:
        return "one_way"
    if normalized in {"hedge", "hedge_mode", "dual"}:
        return "hedge"
    return normalized


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    if value in {0, 1}:
        return bool(value)
    return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
