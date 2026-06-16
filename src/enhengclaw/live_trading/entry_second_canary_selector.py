from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from enhengclaw.quant_research.contracts import sha256_canonical_json


CONTRACT_VERSION = "entry_second_canary_selector_contract.v1"
RESULT_VERSION = "entry_second_canary_selector_result.v1"
OWNER_BINDING_VERSION = "entry_second_canary_selector_owner_payload_binding.v1"


def default_selector_contract(
    *,
    max_order_count: int = 4,
    max_turnover_usdt: float = 75.0,
    required_stability_samples: int = 2,
    notional_buffer_multiplier: float = 1.5,
    notional_buffer_additive_usdt: float = 2.5,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "transport_canary_selector_only_not_strategy_portfolio_construction",
        "expected_execution_stage": "entry_second",
        "allowed_delta_classifications": ["increase_same_side"],
        "expected_reduce_only": False,
        "required_stability_samples": int(required_stability_samples),
        "require_consecutive_samples": True,
        "require_same_side_across_samples": True,
        "require_executable_no_blockers_across_samples": True,
        "notional_buffer": {
            "formula": (
                "latest_rounded_notional_usdt >= "
                "max(min_executable_notional_usdt * multiplier, "
                "min_executable_notional_usdt + additive_usdt)"
            ),
            "multiplier": float(notional_buffer_multiplier),
            "additive_usdt": float(notional_buffer_additive_usdt),
        },
        "deterministic_partial_selection": {
            "enabled_for_canary_only": True,
            "sort_key": ["seq_ascending_from_order_sizing_report", "symbol_ascending_tiebreak"],
            "packing": "greedy_include_if_next_order_keeps_turnover_within_cap",
            "max_order_count": int(max_order_count),
            "max_turnover_usdt": float(max_turnover_usdt),
            "min_selected_order_count": 1,
            "full_strategy_unattended_use": "forbidden",
        },
        "owner_payload_binding_fields": [
            "expected_execution_stage",
            "expected_symbols",
            "expected_sides",
            "expected_reduce_only",
            "expected_max_order_count",
            "expected_max_turnover_usdt",
            "selector_contract_sha256",
            "selector_output_sha256",
            "fresh_plan_only_plan_root",
        ],
    }


def build_entry_second_canary_selector_result(
    *,
    plan_roots: list[Path | str],
    contract: dict[str, Any] | None = None,
    owner_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selector_contract = dict(contract or default_selector_contract())
    normalized_roots = [Path(path) for path in plan_roots]
    blockers: list[str] = []
    if not normalized_roots:
        blockers.append("selector_plan_roots_missing")

    samples: list[dict[str, Any]] = []
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for sample_index, plan_root in enumerate(normalized_roots, start=1):
        sample, sample_blockers = _load_plan_sample(plan_root, sample_index=sample_index)
        samples.append(sample)
        blockers.extend(sample_blockers)
        for symbol, row in dict(sample.get("rows_by_symbol") or {}).items():
            by_symbol.setdefault(symbol, []).append(dict(row))

    expected_stage = str(selector_contract.get("expected_execution_stage") or "entry_second")
    latest_stage = str(samples[-1].get("active_execution_phase") or "") if samples else ""
    if samples and latest_stage != expected_stage:
        blockers.append(f"latest_full_plan_stage_not_{expected_stage}:{latest_stage or 'missing'}")

    results_by_symbol: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for symbol in sorted(by_symbol):
        result = _evaluate_symbol(symbol, by_symbol[symbol], selector_contract, latest_stage=latest_stage)
        results_by_symbol.append(result)
        if result["status"] == "eligible":
            eligible.append(result)

    selected, selected_turnover = _select_partial_canary_orders(eligible, selector_contract)
    if not selected:
        blockers.append("no_selected_orders_after_filter")
    selection_caps = dict(selector_contract.get("deterministic_partial_selection") or {})
    max_order_count = int(selection_caps.get("max_order_count") or 0)
    max_turnover = _finite(selection_caps.get("max_turnover_usdt"))
    if max_order_count > 0 and len(selected) > max_order_count:
        blockers.append("selected_order_count_exceeds_cap")
    if max_turnover is not None and selected_turnover > max_turnover + 1e-9:
        blockers.append("selected_turnover_exceeds_cap")

    selected_orders = [dict(item["latest"]) for item in selected]
    selector_output = {
        "contract_version": RESULT_VERSION,
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "contract": selector_contract,
        "contract_sha256": sha256_canonical_json(selector_contract),
        "sample_plan_roots": [str(path) for path in normalized_roots],
        "latest_plan_root": str(normalized_roots[-1]) if normalized_roots else "",
        "latest_active_execution_phase": latest_stage,
        "samples": samples,
        "eligible_symbols": [item["symbol"] for item in eligible],
        "filtered_symbols": [item["symbol"] for item in results_by_symbol if item["status"] == "filtered"],
        "selected_symbols": [item["symbol"] for item in selected],
        "selected_sides": sorted({str(order.get("side") or "") for order in selected_orders if str(order.get("side") or "")}),
        "selected_order_count": len(selected_orders),
        "selected_turnover_usdt": selected_turnover,
        "selected_orders": selected_orders,
        "results_by_symbol": results_by_symbol,
        "non_authorizations": {
            "open_budget_epoch": False,
            "restricted_gate_apply": False,
            "arm_live_delta": False,
            "supervisor_trigger": False,
            "timer_enable": False,
            "live_order_submission": False,
            "production_config_mutation": False,
            "operator_state_mutation": False,
        },
    }
    selector_output["selector_output_sha256"] = selector_output_sha256(selector_output)
    selector_output["owner_payload_template"] = build_owner_payload_template(selector_output)
    selector_output["owner_payload_binding"] = validate_owner_payload_binding(
        owner_payload=owner_payload,
        selector_output=selector_output,
    )
    return selector_output


def selector_output_sha256(selector_output: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in selector_output.items()
        if key not in {"selector_output_sha256", "owner_payload_template", "owner_payload_binding"}
    }
    return sha256_canonical_json(canonical)


def build_owner_payload_template(selector_output: dict[str, Any]) -> dict[str, Any]:
    selected_symbols = list(selector_output.get("selected_symbols") or [])
    selected_sides = list(selector_output.get("selected_sides") or [])
    contract = dict(selector_output.get("contract") or {})
    selection_caps = dict(contract.get("deterministic_partial_selection") or {})
    selected_turnover = float(selector_output.get("selected_turnover_usdt") or 0.0)
    return {
        "contract_version": "live_delta_owner_intent_payload.v1",
        "owner_decision": "approve_single_cycle_entry_second_canary_selector_output",
        "expected_execution_stage": str(contract.get("expected_execution_stage") or "entry_second"),
        "expected_symbols": selected_symbols,
        "expected_sides": selected_sides,
        "expected_reduce_only": bool(contract.get("expected_reduce_only")),
        "expected_max_order_count": int(selector_output.get("selected_order_count") or 0),
        "expected_max_turnover_usdt": min(
            float(selection_caps.get("max_turnover_usdt") or selected_turnover),
            selected_turnover,
        )
        if selected_turnover > 0.0
        else 0.0,
        "selected_turnover_usdt": selected_turnover,
        "selected_orders": list(selector_output.get("selected_orders") or []),
        "selector_contract_sha256": str(selector_output.get("contract_sha256") or ""),
        "selector_output_sha256": str(selector_output.get("selector_output_sha256") or ""),
        "fresh_plan_only_plan_root": str(selector_output.get("latest_plan_root") or ""),
        "orders_authorized_in_this_step": False,
        "supervisor_trigger_authorized_in_this_step": False,
        "timer_enable_authorized": False,
    }


def validate_owner_payload_binding(
    *,
    owner_payload: dict[str, Any] | None,
    selector_output: dict[str, Any],
) -> dict[str, Any]:
    if owner_payload is None:
        return {
            "contract_version": OWNER_BINDING_VERSION,
            "status": "not_provided",
            "blockers": [],
        }
    payload = dict(owner_payload)
    selected_symbols = sorted(str(item).strip().upper() for item in selector_output.get("selected_symbols") or [])
    selected_sides = sorted(str(item).strip().upper() for item in selector_output.get("selected_sides") or [])
    selected_count = int(selector_output.get("selected_order_count") or 0)
    selected_turnover = float(selector_output.get("selected_turnover_usdt") or 0.0)
    contract = dict(selector_output.get("contract") or {})
    caps = dict(contract.get("deterministic_partial_selection") or {})
    blockers: list[str] = []

    if str(payload.get("selector_contract_sha256") or "") != str(selector_output.get("contract_sha256") or ""):
        blockers.append("selector_contract_sha256_mismatch")
    if str(payload.get("selector_output_sha256") or "") != str(selector_output.get("selector_output_sha256") or ""):
        blockers.append("selector_output_sha256_mismatch")
    if str(payload.get("fresh_plan_only_plan_root") or "") != str(selector_output.get("latest_plan_root") or ""):
        blockers.append("fresh_plan_only_plan_root_mismatch")
    expected_stage = str(contract.get("expected_execution_stage") or "entry_second")
    if str(payload.get("expected_execution_stage") or "").strip().lower() != expected_stage:
        blockers.append("expected_execution_stage_mismatch")
    if _values_upper(payload.get("expected_symbols")) != selected_symbols:
        blockers.append("expected_symbols_mismatch")
    if _values_upper(payload.get("expected_sides")) != selected_sides:
        blockers.append("expected_sides_mismatch")
    if _optional_bool(payload.get("expected_reduce_only")) is not bool(contract.get("expected_reduce_only")):
        blockers.append("expected_reduce_only_mismatch")
    if _optional_int(payload.get("expected_max_order_count")) != selected_count:
        blockers.append("expected_max_order_count_mismatch")

    expected_turnover = _finite(payload.get("expected_max_turnover_usdt"))
    max_cap = _finite(caps.get("max_turnover_usdt"))
    if expected_turnover is None:
        blockers.append("expected_max_turnover_usdt_missing")
    else:
        if expected_turnover + 1e-9 < selected_turnover:
            blockers.append("expected_max_turnover_usdt_below_selected_turnover")
        if max_cap is not None and expected_turnover > max_cap + 1e-9:
            blockers.append("expected_max_turnover_usdt_above_selector_cap")

    if selected_count <= 0:
        blockers.append("selector_output_has_no_selected_orders")
    return {
        "contract_version": OWNER_BINDING_VERSION,
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "expected_symbols": selected_symbols,
        "expected_sides": selected_sides,
        "selected_order_count": selected_count,
        "selected_turnover_usdt": selected_turnover,
    }


def _load_plan_sample(plan_root: Path, *, sample_index: int) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    summary_path = plan_root / "summary.json"
    sizing_path = plan_root / "order_sizing_report.csv"
    summary: dict[str, Any] = {}
    if not summary_path.exists():
        blockers.append(f"summary_json_missing:{plan_root}")
    else:
        try:
            summary = dict(json.loads(summary_path.read_text(encoding="utf-8")))
        except (TypeError, ValueError) as exc:
            blockers.append(f"summary_json_unparseable:{plan_root}:{type(exc).__name__}")
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    if not sizing_path.exists():
        blockers.append(f"order_sizing_report_missing:{plan_root}")
    else:
        try:
            with sizing_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    compact = _compact_sizing_row(row)
                    if compact["symbol"]:
                        rows_by_symbol[compact["symbol"]] = compact
        except (OSError, csv.Error, ValueError) as exc:
            blockers.append(f"order_sizing_report_unparseable:{plan_root}:{type(exc).__name__}")
    return (
        {
            "sample_index": int(sample_index),
            "plan_root": str(plan_root),
            "active_execution_phase": str(summary.get("active_execution_phase") or ""),
            "phase_counts": dict(summary.get("phase_counts") or {}),
            "planned_delta_order_count": int(_finite(summary.get("planned_delta_order_count")) or 0),
            "risk_gate_status": str(summary.get("risk_gate_status") or ""),
            "rows_by_symbol": rows_by_symbol,
        },
        blockers,
    )


def _compact_sizing_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": int(_finite(row.get("seq")) or 999999),
        "symbol": str(row.get("symbol") or "").strip().upper(),
        "side": str(row.get("side") or "").strip().upper(),
        "execution_phase": str(row.get("execution_phase") or "").strip(),
        "delta_classification": str(row.get("delta_classification") or "").strip(),
        "reduce_only": _optional_bool(row.get("reduce_only")) is True,
        "executable": _optional_bool(row.get("executable")) is True,
        "blockers": str(row.get("blockers") or "").strip(),
        "rounded_quantity": float(_finite(row.get("rounded_quantity")) or 0.0),
        "rounded_notional_usdt": float(_finite(row.get("rounded_notional_usdt")) or 0.0),
        "min_executable_notional_usdt": float(_finite(row.get("min_executable_notional_usdt")) or 0.0),
        "current_position_amt": float(_finite(row.get("current_position_amt")) or 0.0),
        "target_position_amt": float(_finite(row.get("target_position_amt")) or 0.0),
        "delta_position_amt": float(_finite(row.get("delta_position_amt")) or 0.0),
    }


def _evaluate_symbol(
    symbol: str,
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    latest_stage: str,
) -> dict[str, Any]:
    required = int(contract.get("required_stability_samples") or 2)
    recent = history[-required:]
    latest = dict(history[-1]) if history else {}
    expected_stage = str(contract.get("expected_execution_stage") or "entry_second")
    allowed_classifications = set(str(item) for item in list(contract.get("allowed_delta_classifications") or []))
    buffer_config = dict(contract.get("notional_buffer") or {})
    threshold = max(
        float(latest.get("min_executable_notional_usdt") or 0.0) * float(buffer_config.get("multiplier") or 0.0),
        float(latest.get("min_executable_notional_usdt") or 0.0) + float(buffer_config.get("additive_usdt") or 0.0),
    )
    checks = {
        "present_in_required_sample_count": len(history) >= required,
        "latest_stage_matches_contract": latest_stage == expected_stage,
        "all_required_samples_entry_second": all(row.get("execution_phase") == expected_stage for row in recent)
        and len(recent) == required,
        "all_required_samples_executable": all(bool(row.get("executable")) for row in recent) and len(recent) == required,
        "all_required_samples_no_blockers": all(not str(row.get("blockers") or "") for row in recent)
        and len(recent) == required,
        "same_side_required_samples": len({str(row.get("side") or "") for row in recent}) == 1 and len(recent) == required,
        "latest_delta_classification_allowed": str(latest.get("delta_classification") or "") in allowed_classifications,
        "latest_reduce_only_matches_contract": bool(latest.get("reduce_only")) is bool(contract.get("expected_reduce_only")),
        "latest_notional_above_buffer": float(latest.get("rounded_notional_usdt") or 0.0) >= threshold - 1e-9,
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "symbol": symbol,
        "status": "eligible" if not blockers else "filtered",
        "blockers": blockers,
        "checks": checks,
        "latest_buffer_threshold_usdt": threshold,
        "latest": latest,
        "history": history,
    }


def _select_partial_canary_orders(
    eligible: list[dict[str, Any]],
    contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    caps = dict(contract.get("deterministic_partial_selection") or {})
    max_count = int(caps.get("max_order_count") or 0)
    max_turnover = float(caps.get("max_turnover_usdt") or 0.0)
    selected: list[dict[str, Any]] = []
    turnover = 0.0
    for item in sorted(eligible, key=lambda value: (int(value["latest"].get("seq") or 999999), str(value["symbol"]))):
        notional = abs(float(item["latest"].get("rounded_notional_usdt") or 0.0))
        if max_count > 0 and len(selected) >= max_count:
            continue
        if max_turnover > 0.0 and turnover + notional > max_turnover + 1e-9:
            continue
        selected.append(item)
        turnover += notional
    return selected, turnover


def _values_upper(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = str(value).split(",")
    return sorted(str(item).strip().upper() for item in raw if str(item).strip())


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _optional_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
