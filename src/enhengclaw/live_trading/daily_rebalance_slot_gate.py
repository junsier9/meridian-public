from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from enhengclaw.live_trading.models import ExecutionPlan, TargetPortfolio
from enhengclaw.live_trading.models import TargetPosition


FROZEN_TARGET_SNAPSHOT_ARTIFACT = "frozen_target_snapshot.json"
FROZEN_TARGET_SNAPSHOT_VERSION = "daily_rebalance_slot_target.v1"
REBALANCE_SLOT_REEXECUTION_ACTION = "authorize-rebalance-slot-reexecution"
REBALANCE_SLOT_POST_FILL_CLEANUP_ACTION = "authorize-rebalance-slot-post-fill-cleanup"
REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_ACTION = "authorize-rebalance-slot-risk-only-reduce-cleanup"
REBALANCE_SLOT_RISK_ONLY_REDUCE_CLEANUP_CONSUMED_ACTION = "consume-rebalance-slot-risk-only-reduce-cleanup"


def build_frozen_target_snapshot(
    *,
    target_engine: str,
    portfolio: TargetPortfolio,
    order_sizing_report: pd.DataFrame,
    capital_allocation_context: dict[str, Any],
    decision_metadata: dict[str, Any],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    created = created_at or datetime.now(UTC)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    slot_id = rebalance_slot_id(target_engine=target_engine, portfolio=portfolio, decision_metadata=decision_metadata)
    rows = _sizing_rows_by_symbol(order_sizing_report)
    positions: list[dict[str, Any]] = []
    for position in sorted(portfolio.positions, key=lambda item: item.usdm_symbol):
        row = rows.get(position.usdm_symbol, {})
        reference_price = _float(row.get("target_reference_price", row.get("mark_price")))
        target_amt = _float(row.get("target_position_amt"))
        positions.append(
            {
                "symbol": position.usdm_symbol,
                "subject": position.subject,
                "side": position.side,
                "selection_reason": position.selection_reason,
                "target_weight": float(position.target_weight),
                "target_notional_usdt": float(position.target_notional_usdt),
                "resolved_capital_usdt": float(portfolio.allocated_capital_usdt),
                "reference_price": float(reference_price),
                "target_position_amt": float(target_amt),
            }
        )
    hash_payload = _target_hash_payload(
        slot_id=slot_id,
        target_engine=target_engine,
        portfolio=portfolio,
        capital_allocation_context=capital_allocation_context,
        decision_metadata=decision_metadata,
        positions=positions,
    )
    target_hash = _sha256_json(hash_payload)
    return {
        "schema_version": FROZEN_TARGET_SNAPSHOT_VERSION,
        "status": "open",
        "slot_id": slot_id,
        "target_hash": target_hash,
        "target_engine": str(target_engine),
        "strategy_label": str(portfolio.strategy_label),
        "decision_id": str(portfolio.decision_id),
        "portfolio_id": str(portfolio.portfolio_id),
        "decision_time_ms": decision_metadata.get("decision_time_ms"),
        "decision_date_utc": decision_metadata.get("decision_date_utc"),
        "input_bar_end_ms": decision_metadata.get("input_bar_end_ms"),
        "phase_decision_time_ms": list(decision_metadata.get("phase_decision_time_ms") or []),
        "phase_decision_dates_utc": list(decision_metadata.get("phase_decision_dates_utc") or []),
        "capital_sizing_basis": str(capital_allocation_context.get("sizing_basis") or ""),
        "baseline_allocated_capital_usdt": _float(capital_allocation_context.get("baseline_allocated_capital_usdt")),
        "resolved_capital_usdt": float(portfolio.allocated_capital_usdt),
        "positions": positions,
        "position_count": int(len(positions)),
        "created_at_utc": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "hash_payload": hash_payload,
    }


def rebalance_slot_id(
    *,
    target_engine: str,
    portfolio: TargetPortfolio,
    decision_metadata: dict[str, Any],
) -> str:
    decision_time = decision_metadata.get("decision_time_ms")
    if decision_time is None:
        decision_time = decision_metadata.get("input_bar_end_ms", "unknown")
    return f"{str(target_engine)}:{str(portfolio.strategy_label)}:{decision_time}"


def target_position_overrides(snapshot: dict[str, Any] | None) -> dict[str, float]:
    return {
        str(row.get("symbol")): _float(row.get("target_position_amt"))
        for row in list(dict(snapshot or {}).get("positions") or [])
        if str(row.get("symbol") or "").strip()
    }


def target_reference_prices(snapshot: dict[str, Any] | None) -> dict[str, float]:
    return {
        str(row.get("symbol")): _float(row.get("reference_price"))
        for row in list(dict(snapshot or {}).get("positions") or [])
        if str(row.get("symbol") or "").strip()
    }


def apply_frozen_snapshot_to_portfolio(portfolio: TargetPortfolio, snapshot: dict[str, Any]) -> TargetPortfolio:
    frozen_positions = list(dict(snapshot or {}).get("positions") or [])
    existing_by_symbol = {position.usdm_symbol: position for position in portfolio.positions}
    positions: list[TargetPosition] = []
    for row in frozen_positions:
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        existing = existing_by_symbol.get(symbol)
        target_weight = _float(row.get("target_weight"))
        positions.append(
            TargetPosition(
                subject=str(row.get("subject") or (existing.subject if existing else symbol.removesuffix("USDT"))),
                usdm_symbol=symbol,
                side=str(row.get("side") or ("long" if target_weight > 0.0 else "short")),
                score=float(existing.score) if existing else 0.0,
                target_weight=target_weight,
                target_notional_usdt=_float(row.get("target_notional_usdt")),
                previous_target_weight=float(existing.previous_target_weight) if existing else 0.0,
                delta_target_weight=float(existing.delta_target_weight) if existing else target_weight,
                raw_short_multiplier=float(existing.raw_short_multiplier) if existing else 1.0,
                portfolio_drawdown_multiplier=float(existing.portfolio_drawdown_multiplier) if existing else 1.0,
                selection_reason=str(row.get("selection_reason") or (existing.selection_reason if existing else "frozen_slot")),
            )
        )
    gross = sum(abs(position.target_weight) for position in positions)
    net = sum(position.target_weight for position in positions)
    return TargetPortfolio(
        portfolio_id=str(snapshot.get("portfolio_id") or portfolio.portfolio_id),
        decision_id=str(snapshot.get("decision_id") or portfolio.decision_id),
        strategy_label=str(snapshot.get("strategy_label") or portfolio.strategy_label),
        allocated_capital_usdt=_float(snapshot.get("resolved_capital_usdt", portfolio.allocated_capital_usdt)),
        portfolio_drawdown=float(portfolio.portfolio_drawdown),
        portfolio_drawdown_multiplier=float(portfolio.portfolio_drawdown_multiplier),
        target_gross_weight=float(gross),
        target_net_weight=float(net),
        status=portfolio.status,
        blockers=list(portfolio.blockers),
        positions=positions,
    )


def completed_slot_execution_gate(
    *,
    slot_record: dict[str, Any] | None,
    plan: ExecutionPlan,
    reexecution_authorization: dict[str, Any] | None = None,
    post_fill_cleanup_authorization: dict[str, Any] | None = None,
    risk_only_reduce_cleanup_authorization: dict[str, Any] | None = None,
    risk_only_reduce_cleanup_consumed: dict[str, Any] | None = None,
    current_budget_epoch_id: str | None = None,
) -> dict[str, Any]:
    record = dict(slot_record or {})
    if str(record.get("status") or "").strip().lower() != "completed":
        return {
            "status": "slot_not_completed",
            "blockers": [],
            "slot_completed": False,
            "hold_until_next_rebalance_slot": False,
        }
    target_hash = str(record.get("target_hash") or "")
    reauth = _matching_authorization(reexecution_authorization, record, target_hash)
    cleanup_auth = _matching_authorization(post_fill_cleanup_authorization, record, target_hash)
    risk_only_cleanup_auth = _matching_authorization(
        risk_only_reduce_cleanup_authorization,
        record,
        target_hash,
    )
    risk_only_cleanup_consumed = _matching_authorization(
        risk_only_reduce_cleanup_consumed,
        record,
        target_hash,
    )
    if reauth:
        return {
            "status": "manual_owner_reexecution_allowed",
            "blockers": [],
            "slot_completed": True,
            "hold_until_next_rebalance_slot": False,
            "authorization": reauth,
        }
    if cleanup_auth:
        return {
            "status": "post_fill_cleanup_allowed",
            "blockers": [],
            "slot_completed": True,
            "hold_until_next_rebalance_slot": False,
            "authorization": cleanup_auth,
        }
    if not plan.intents:
        return {
            "status": "hold_until_next_rebalance_slot",
            "blockers": [],
            "slot_completed": True,
            "hold_until_next_rebalance_slot": True,
        }
    if all(bool(intent.reduce_only) for intent in plan.intents):
        return _risk_only_reduce_cleanup_gate(
            record=record,
            target_hash=target_hash,
            authorization=risk_only_cleanup_auth,
            consumed=risk_only_cleanup_consumed,
            current_budget_epoch_id=current_budget_epoch_id,
        )
    return {
        "status": "hold_until_next_rebalance_slot",
        "blockers": [],
        "slot_completed": True,
        "hold_until_next_rebalance_slot": True,
        "blocked_non_reduce_only_intent_count": int(sum(not bool(intent.reduce_only) for intent in plan.intents)),
    }


def hold_execution_plan(plan: ExecutionPlan) -> ExecutionPlan:
    plan.status = "hold_until_next_rebalance_slot"
    plan.intents = []
    plan.active_execution_phase = "noop"
    plan.phase_counts = {"hold_until_next_rebalance_slot": 1}
    plan.deferred_phase_counts = {}
    plan.blockers = []
    return plan


def _matching_authorization(
    authorization: dict[str, Any] | None,
    record: dict[str, Any],
    target_hash: str,
) -> dict[str, Any]:
    auth = dict(authorization or {})
    if not auth:
        return {}
    if str(auth.get("status") or "") != "applied":
        return {}
    expected_slot = str(record.get("slot_id") or "")
    auth_slot = str(auth.get("slot_id") or auth.get("rebalance_slot_id") or "")
    if not auth_slot or auth_slot != expected_slot:
        return {}
    auth_hash = str(auth.get("target_hash") or auth.get("rebalance_target_hash") or "")
    if not auth_hash or auth_hash != target_hash:
        return {}
    return auth


def _risk_only_reduce_cleanup_gate(
    *,
    record: dict[str, Any],
    target_hash: str,
    authorization: dict[str, Any],
    consumed: dict[str, Any],
    current_budget_epoch_id: str | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not authorization:
        blockers.append("risk_only_reduce_cleanup_owner_authorization_missing")

    budget_epoch_id = _authorization_text(
        authorization,
        "budget_epoch_id",
        "unattended_budget_epoch_id",
        "expected_epoch_id",
        "epoch_id",
    )
    canary = _no_order_canary_context(authorization)
    single_use = _authorization_optional_bool(
        authorization,
        "single_use",
        "one_time",
        "risk_only_reduce_cleanup_single_use",
    )

    if authorization and single_use is not True:
        blockers.append("risk_only_reduce_cleanup_single_use_not_declared")
    if authorization and not budget_epoch_id:
        blockers.append("risk_only_reduce_cleanup_budget_epoch_missing")
    if authorization and current_budget_epoch_id is not None:
        current_epoch = str(current_budget_epoch_id or "").strip()
        if not current_epoch:
            blockers.append("risk_only_reduce_cleanup_requires_open_budget_epoch")
        elif budget_epoch_id and budget_epoch_id != current_epoch:
            blockers.append(
                f"risk_only_reduce_cleanup_budget_epoch_mismatch:expected={budget_epoch_id}:actual={current_epoch}"
            )
    if authorization and not bool(canary.get("passed")):
        blockers.append("risk_only_reduce_cleanup_no_order_canary_missing_or_failed")
    if authorization and not str(canary.get("artifact_root") or canary.get("run_id") or "").strip():
        blockers.append("risk_only_reduce_cleanup_no_order_canary_artifact_missing")
    if consumed:
        blockers.append("risk_only_reduce_cleanup_authorization_already_consumed")

    if blockers:
        return {
            "status": "risk_only_reduce_cleanup_requires_owner_budget_canary",
            "blockers": sorted(set(blockers)),
            "slot_completed": True,
            "hold_until_next_rebalance_slot": True,
            "allowed_exception": "",
            "slot_id": str(record.get("slot_id") or ""),
            "target_hash": str(target_hash or ""),
            "authorization_action_id": str(authorization.get("action_id") or ""),
            "consumed_action_id": str(consumed.get("action_id") or ""),
            "budget_epoch_id": budget_epoch_id,
            "current_open_budget_epoch_id": "" if current_budget_epoch_id is None else str(current_budget_epoch_id or ""),
            "no_order_canary": canary,
        }

    return {
        "status": "risk_only_reduce_cleanup_allowed",
        "blockers": [],
        "slot_completed": True,
        "hold_until_next_rebalance_slot": False,
        "allowed_exception": "risk_only_reduce_or_flatten",
        "slot_id": str(record.get("slot_id") or ""),
        "target_hash": str(target_hash or ""),
        "authorization_action_id": str(authorization.get("action_id") or ""),
        "budget_epoch_id": budget_epoch_id,
        "current_open_budget_epoch_id": "" if current_budget_epoch_id is None else str(current_budget_epoch_id or ""),
        "no_order_canary": canary,
        "authorization": authorization,
        "single_use": True,
    }


def _no_order_canary_context(authorization: dict[str, Any]) -> dict[str, Any]:
    auth = dict(authorization or {})
    nested = dict(auth.get("no_order_canary") or auth.get("risk_only_reduce_cleanup_no_order_canary") or {})
    status = _authorization_text(
        auth,
        "no_order_canary_status",
        "risk_only_reduce_cleanup_no_order_canary_status",
        "canary_status",
    )
    if not status:
        status = str(nested.get("status") or "").strip()
    passed = any(
        _authorization_optional_bool(auth, key) is True
        for key in (
            "no_order_canary_passed",
            "risk_only_reduce_cleanup_no_order_canary_passed",
            "canary_passed",
        )
    )
    if not passed and status.strip().lower() in {"passed", "ready"}:
        passed = True
    orders_submitted = _first_int(auth, nested, "orders_submitted", "submitted_order_count")
    if orders_submitted is not None and int(orders_submitted) != 0:
        passed = False
    authorized = _first_optional_bool(
        auth,
        nested,
        "mainnet_order_submission_authorized",
        "live_delta_authorized",
    )
    if authorized is True:
        passed = False
    artifact_root = _first_text(
        auth,
        nested,
        "no_order_canary_artifact_root",
        "artifact_root",
        "risk_only_reduce_cleanup_no_order_canary_artifact_root",
    )
    run_id = _first_text(auth, nested, "no_order_canary_run_id", "run_id")
    return {
        "passed": bool(passed),
        "status": status,
        "artifact_root": artifact_root,
        "run_id": run_id,
        "orders_submitted": orders_submitted,
        "mainnet_order_submission_authorized": authorized,
    }


def _authorization_text(payload: dict[str, Any], *keys: str) -> str:
    return _first_text(dict(payload or {}), {}, *keys)


def _authorization_optional_bool(payload: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in payload:
            return _boolish(payload.get(key))
    return None


def _first_text(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> str:
    for source in (primary, secondary):
        for key in keys:
            value = source.get(key)
            if isinstance(value, (list, tuple, set)):
                values = [str(item).strip() for item in value if str(item).strip()]
                if values:
                    return values[0]
            else:
                text = str(value or "").strip()
                if text:
                    return text
    return ""


def _first_optional_bool(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> bool | None:
    for source in (primary, secondary):
        for key in keys:
            if key in source:
                return _boolish(source.get(key))
    return None


def _first_int(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> int | None:
    for source in (primary, secondary):
        for key in keys:
            if key not in source:
                continue
            try:
                return int(float(source.get(key)))
            except (TypeError, ValueError):
                return None
    return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "passed", "ready"}


def _target_hash_payload(
    *,
    slot_id: str,
    target_engine: str,
    portfolio: TargetPortfolio,
    capital_allocation_context: dict[str, Any],
    decision_metadata: dict[str, Any],
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": FROZEN_TARGET_SNAPSHOT_VERSION,
        "slot_id": str(slot_id),
        "target_engine": str(target_engine),
        "strategy_label": str(portfolio.strategy_label),
        "decision_time_ms": decision_metadata.get("decision_time_ms"),
        "input_bar_end_ms": decision_metadata.get("input_bar_end_ms"),
        "phase_decision_time_ms": list(decision_metadata.get("phase_decision_time_ms") or []),
        "resolved_capital_usdt": float(portfolio.allocated_capital_usdt),
        "capital_sizing_basis": str(capital_allocation_context.get("sizing_basis") or ""),
        "positions": [
            {
                "symbol": str(row.get("symbol") or ""),
                "target_weight": _float(row.get("target_weight")),
                "target_notional_usdt": _float(row.get("target_notional_usdt")),
                "resolved_capital_usdt": _float(row.get("resolved_capital_usdt")),
                "reference_price": _float(row.get("reference_price")),
                "target_position_amt": _float(row.get("target_position_amt")),
            }
            for row in positions
        ],
    }


def _sizing_rows_by_symbol(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    output: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        symbol = str(row.get("symbol") or "")
        if symbol:
            output[symbol] = dict(row)
    return output


def _sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return 0.0
    return float(parsed)
