from __future__ import annotations

import math
from typing import Any


def removed_daily_realized_pnl_gate(*, config: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "removed",
        "blockers": [],
        "enforcement": "disabled",
        "mechanism": "daily_realized_pnl_loss_cap_removed",
    }


def evaluate_margin_cushion_gate(
    account_summary: dict[str, Any],
    *,
    config: dict[str, Any],
    planned_additional_initial_margin_usdt: float = 0.0,
    require_configured: bool = False,
) -> dict[str, Any]:
    risk = dict(config.get("risk") or {})
    available = _float(account_summary.get("available_balance_usdt"))
    wallet = _float(account_summary.get("total_wallet_balance_usdt"))
    planned = max(0.0, float(planned_additional_initial_margin_usdt or 0.0))
    post_available = available - planned
    blockers: list[str] = []
    warnings: list[str] = []
    min_abs = _optional_float(
        risk.get("min_available_balance_after_plan_usdt", risk.get("min_available_balance_usdt"))
    )
    min_ratio = _optional_float(risk.get("min_available_balance_ratio_after_plan"))
    min_cushion = _optional_float(risk.get("min_margin_cushion_after_plan_usdt"))
    if require_configured and min_abs is None and min_ratio is None and min_cushion is None:
        blockers.append("margin_cushion_gate_not_configured")
    if min_abs is not None and post_available < float(min_abs):
        blockers.append(f"available_balance_below_min_after_plan:{post_available}<{float(min_abs)}")
    if min_cushion is not None and post_available < float(min_cushion):
        blockers.append(f"margin_cushion_below_min_after_plan:{post_available}<{float(min_cushion)}")
    ratio = post_available / wallet if wallet > 0.0 else 0.0
    if min_ratio is not None and ratio < float(min_ratio):
        blockers.append(f"available_balance_ratio_below_min_after_plan:{ratio}<{float(min_ratio)}")
    if post_available < 0.0:
        blockers.append(f"available_balance_negative_after_plan:{post_available}")
    if post_available < available * 0.05 and min_abs is None and min_ratio is None:
        warnings.append("margin_cushion_low_without_explicit_threshold")
    return {
        "status": "passed" if not blockers else "blocked",
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "available_balance_usdt": float(available),
        "total_wallet_balance_usdt": float(wallet),
        "planned_additional_initial_margin_usdt": float(planned),
        "post_plan_available_balance_usdt": float(post_available),
        "post_plan_available_balance_ratio": float(ratio),
        "min_available_balance_after_plan_usdt": min_abs,
        "min_available_balance_ratio_after_plan": min_ratio,
        "min_margin_cushion_after_plan_usdt": min_cushion,
    }


def evaluate_account_snapshot_age_gate(
    account_snapshot: dict[str, Any],
    *,
    config: dict[str, Any],
    now_ms: int,
    require_configured: bool = False,
) -> dict[str, Any]:
    """Fail-closed staleness guard on the account snapshot used for the delta decision.

    The Binance account/position payload carries no server timestamp, so the snapshot
    is stamped with ``fetched_at_ms`` at fetch time and this gate compares it against
    the preflight evaluation time (``now_ms``). It catches a delta decision made on an
    account snapshot that is too old relative to submission -- e.g. a long pause or a
    reused snapshot on a re-invoked / scheduled cycle -- which is precisely the
    unattended failure mode.

    Enforced only when ``risk.max_account_snapshot_age_seconds`` is configured (the host
    timer config sets it). With a configured threshold a missing / non-finite / future
    ``fetched_at_ms`` fails closed rather than scoring as fresh. When unconfigured the
    gate is a no-op unless ``require_configured`` is true.

    NOTE: there is deliberately no market-data-age gate on the delta path -- it fetches
    no market data; feature-feed freshness is enforced upstream in the p10a feature
    builder. ``risk.max_market_data_age_seconds`` therefore stays inert here by design.
    """
    risk = dict(config.get("risk") or {})
    max_age = _optional_float(risk.get("max_account_snapshot_age_seconds"))
    blockers: list[str] = []
    if max_age is None:
        if require_configured:
            blockers.append("account_snapshot_age_gate_not_configured")
        return {
            "status": "blocked" if blockers else "not_configured",
            "passed": not blockers,
            "blockers": blockers,
            "max_account_snapshot_age_seconds": None,
            "fetched_at_ms": None,
            "now_ms": int(now_ms),
            "age_seconds": None,
        }
    fetched_at_ms = _strict_finite_float(account_snapshot.get("fetched_at_ms"))
    age_seconds: float | None = None
    if fetched_at_ms is None:
        blockers.append("account_snapshot_fetched_at_unreadable")
    else:
        age_seconds = (float(now_ms) - float(fetched_at_ms)) / 1000.0
        if age_seconds < 0.0:
            blockers.append(f"account_snapshot_timestamp_in_future:{age_seconds}")
        elif age_seconds > float(max_age):
            blockers.append(f"account_snapshot_stale:{age_seconds}>{float(max_age)}")
    return {
        "status": "passed" if not blockers else "blocked",
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
        "max_account_snapshot_age_seconds": float(max_age),
        "fetched_at_ms": int(fetched_at_ms) if fetched_at_ms is not None else None,
        "now_ms": int(now_ms),
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
    }


def evaluate_per_order_notional_gate(
    planned_rows: list[dict[str, Any]],
    *,
    per_order_notional_cap_usdt: float | None,
    hard_multiplier: float = 1.5,
    require_configured: bool = True,
) -> dict[str, Any]:
    """Defense-in-depth sanity ceiling on a single order's notional.

    The PRIMARY bounds on order flow are the order-count cap and the unattended
    turnover/cycle budget; this gate only catches a grossly oversized single
    order from a logic error. The ceiling is the RESOLVED per-order cap
    (max(static, resolved_capital * max_order_weight_cap) ~= the per-symbol
    weight-cap notional) times ``hard_multiplier``, so legitimate rebalance /
    top-up orders -- which are bounded by that same weight cap by construction --
    pass comfortably, while a 5-10x error is rejected.

    Scoped to NON-reduce-only intents only: a reduce/de-risking order closing a
    drifted-large position may legitimately exceed the cap and must never be
    blocked (that would prevent the system from cutting risk).

    Fails closed (``per_order_notional_cap_not_configured``) when the cap cannot
    be resolved and ``require_configured`` is true. A row with an unreadable
    notional is rejected, not skipped.
    """
    blockers: list[str] = []
    cap = _optional_float(per_order_notional_cap_usdt)
    multiplier = float(hard_multiplier) if hard_multiplier and float(hard_multiplier) > 0.0 else 1.0
    if cap is None or cap <= 0.0:
        if require_configured:
            blockers.append("per_order_notional_cap_not_configured")
        return {
            "status": "blocked" if blockers else "not_configured",
            "passed": not blockers,
            "blockers": blockers,
            "per_order_notional_cap_usdt": cap,
            "hard_multiplier": multiplier,
            "ceiling_usdt": None,
            "offending_orders": [],
            "checked_order_count": 0,
        }
    ceiling = cap * multiplier
    offenders: list[dict[str, Any]] = []
    checked = 0
    for row in planned_rows or []:
        if bool(row.get("reduce_only")):
            continue
        checked += 1
        notional = _strict_finite_float(row.get("rounded_notional_usdt"))
        symbol = str(row.get("symbol") or row.get("usdm_symbol") or "")
        if notional is None:
            blockers.append(f"per_order_notional_unreadable:{symbol or 'unknown'}")
            continue
        if abs(notional) > ceiling:
            blockers.append(f"order_notional_exceeds_cap:{symbol}:{abs(notional):.2f}>{ceiling:.2f}")
            offenders.append({"symbol": symbol, "notional_usdt": abs(notional)})
    return {
        "status": "passed" if not blockers else "blocked",
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
        "per_order_notional_cap_usdt": float(cap),
        "hard_multiplier": multiplier,
        "ceiling_usdt": float(ceiling),
        "offending_orders": offenders,
        "checked_order_count": int(checked),
    }


def classify_exception_strategy(
    blockers: list[str],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = [str(item) for item in blockers]
    action = "continue_plan_only_reconcile"
    severity = "ok"
    rationale = "No blockers detected; continue read-only reconcile and plan-only observation."
    if any("daily_realized_pnl" in item or "pnl" in item.lower() for item in normalized):
        action = "pause_new_entries_and_review_reduce_only_flatten"
        severity = "critical"
        rationale = "Daily realized PnL gate breached or unreadable; stop new entries and review reduce-only flatten."
    elif any("margin_cushion" in item or "available_balance" in item for item in normalized):
        action = "pause_new_entries_margin_reconcile"
        severity = "critical"
        rationale = "Margin cushion is below the configured floor; stop new entries and reconcile before any new risk."
    elif any("open_orders" in item for item in normalized):
        action = "stop_new_entries_cancel_or_reconcile_open_orders"
        severity = "high"
        rationale = "Open orders exist; do not submit new orders until they are canceled or reconciled."
    elif any("position_drift" in item or "position_mismatch" in item or "unexpected_live_position" in item for item in normalized):
        action = "stop_new_entries_forced_reconcile"
        severity = "high"
        rationale = "Live position drift exists; run forced reconciliation before any rebalance."
    elif any("endpoint_failed" in item or "unreadable" in item or "missing_api" in item for item in normalized):
        action = "stop_new_entries_api_recovery"
        severity = "high"
        rationale = "A required read-only API path failed; fail closed until account state is readable."
    elif any("unknown_order" in item or "unknown_status" in item for item in normalized):
        action = "stop_new_entries_unknown_order_recovery"
        severity = "high"
        rationale = "Order status is unknown; query/reconcile by clientOrderId and do not resubmit."
    elif any("stale" in item or "funding" in item or "market_data" in item for item in normalized):
        action = "skip_rebalance_wait_for_fresh_data"
        severity = "medium"
        rationale = "Market/funding data is stale or incomplete; skip strategy changes until data is fresh."
    return {
        "action": action,
        "severity": severity,
        "rationale": rationale,
        "blockers": normalized,
        "context": dict(context or {}),
        "new_entries_allowed": action == "continue_plan_only_reconcile",
        "live_delta_allowed": False,
        "flatten_requires_explicit_confirmation": True,
        "allowed_next_actions": _allowed_actions_for(action),
    }


def _allowed_actions_for(action: str) -> list[str]:
    if action == "continue_plan_only_reconcile":
        return ["read_only_monitor", "plan_only_rebalance", "paper_shadow"]
    if action == "pause_new_entries_and_review_reduce_only_flatten":
        return ["read_only_monitor", "forced_reconcile", "explicit_reduce_only_flatten_review"]
    if action == "pause_new_entries_margin_reconcile":
        return ["read_only_monitor", "forced_reconcile", "reduce_only_deleveraging_review"]
    if action == "stop_new_entries_cancel_or_reconcile_open_orders":
        return ["read_only_monitor", "cancel_or_query_open_orders", "forced_reconcile"]
    if action == "stop_new_entries_unknown_order_recovery":
        return ["query_by_client_order_id", "forced_reconcile", "operator_review"]
    if action == "skip_rebalance_wait_for_fresh_data":
        return ["wait_for_fresh_data", "read_only_monitor", "plan_only_retry"]
    return ["read_only_monitor", "forced_reconcile", "operator_review"]


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _float(value)


def _strict_finite_float(value: Any) -> float | None:
    """Unlike _optional_float (which coerces junk to 0.0 via _float), this returns
    None for any unparseable or non-finite value, so an unreadable order notional
    fails closed instead of silently scoring as 0.0."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
