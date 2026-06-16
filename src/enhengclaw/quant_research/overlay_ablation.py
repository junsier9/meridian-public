from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import read_json


ROOT = Path(__file__).resolve().parents[3]
OVERLAY_ABLATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "overlay_ablation_contract.json"
OVERLAY_ABLATION_CONTRACT_VERSION = "quant_overlay_ablation_contract.v1"


def load_overlay_ablation_contract(*, path: Path | None = None) -> dict[str, Any]:
    contract_path = (path or OVERLAY_ABLATION_CONTRACT_PATH).expanduser().resolve()
    payload = dict(read_json(contract_path))
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != OVERLAY_ABLATION_CONTRACT_VERSION:
        raise ValueError(
            "overlay ablation contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    variants = [
        dict(item)
        for item in list(payload.get("overlay_variants") or [])
        if isinstance(item, dict)
    ]
    if not variants:
        raise ValueError("overlay ablation contract missing overlay_variants")
    return {
        "path": str(contract_path),
        "contract_version": contract_version,
        "applicability": dict(payload.get("applicability") or {}),
        "candidate_set": [
            dict(item)
            for item in list(payload.get("candidate_set") or [])
            if isinstance(item, dict)
        ],
        "overlay_variants": variants,
        "bootstrap": dict(payload.get("bootstrap") or {}),
        "promotion_gate": dict(payload.get("promotion_gate") or {}),
    }


def overlay_ablation_candidate_entries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(contract.get("candidate_set") or [])
        if isinstance(item, dict)
    ]


def overlay_ablation_variant_entries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(contract.get("overlay_variants") or [])
        if isinstance(item, dict)
    ]


def overlay_ablation_candidate_label(*, strategy_id: str | None, contract: dict[str, Any]) -> str:
    normalized = str(strategy_id or "").strip()
    for entry in overlay_ablation_candidate_entries(contract):
        if normalized and normalized in {
            str(entry.get("label") or "").strip(),
            str(entry.get("strategy_id") or "").strip(),
            str(entry.get("experiment_id") or "").strip(),
        }:
            return str(entry.get("label") or normalized).strip()
    return normalized or "candidate"


def overlay_ablation_applicability(
    *,
    shape: str,
    bar_interval_ms: int,
    target_horizon_bars: int,
    label_contract_id: str,
    research_lane: str | None,
    overlay_id: str | None,
    contract: dict[str, Any],
) -> dict[str, Any]:
    rules = dict(contract.get("applicability") or {})
    reasons: list[str] = []
    expected_shape = str(rules.get("shape") or "").strip()
    if expected_shape and str(shape).strip() != expected_shape:
        reasons.append("shape_mismatch")
    expected_bar_interval_ms = int(rules.get("bar_interval_ms") or 0)
    if expected_bar_interval_ms and int(bar_interval_ms) != expected_bar_interval_ms:
        reasons.append("bar_interval_mismatch")
    expected_horizon = int(rules.get("target_horizon_bars") or 0)
    if expected_horizon and int(target_horizon_bars) != expected_horizon:
        reasons.append("target_horizon_mismatch")
    allowed_label_contract_ids = {
        str(item).strip()
        for item in list(rules.get("label_contract_ids") or [])
        if str(item).strip()
    }
    if allowed_label_contract_ids and str(label_contract_id).strip() not in allowed_label_contract_ids:
        reasons.append("label_contract_mismatch")
    required_research_lanes = {
        str(item).strip()
        for item in list(rules.get("required_research_lanes") or [])
        if str(item).strip()
    }
    if required_research_lanes and str(research_lane or "").strip() not in required_research_lanes:
        reasons.append("research_lane_mismatch")
    required_overlay_ids = {
        str(item).strip()
        for item in list(rules.get("required_overlay_ids") or [])
        if str(item).strip()
    }
    if required_overlay_ids and str(overlay_id or "").strip() not in required_overlay_ids:
        reasons.append("overlay_id_mismatch")
    return {
        "applicable": not reasons,
        "reason_codes": sorted(reasons),
        "rules": rules,
    }


def build_overlay_ablation_gate_assessment(
    *,
    variant_summaries: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    gate_contract = dict(contract.get("promotion_gate") or {})
    current_label = str(gate_contract.get("current_overlay_label") or "").strip()
    base_label = str(gate_contract.get("base_signal_label") or "").strip()
    summaries_by_label = {
        str(item.get("overlay_label") or "").strip(): dict(item)
        for item in list(variant_summaries or [])
        if str(item.get("overlay_label") or "").strip()
    }
    current_summary = summaries_by_label.get(current_label)
    base_summary = summaries_by_label.get(base_label)
    blockers: list[str] = []
    if current_label and current_summary is None:
        blockers.append("missing_current_overlay_summary")
    if base_label and base_summary is None:
        blockers.append("missing_base_signal_summary")
    if current_summary is not None:
        max_trade = float(current_summary.get("full_oos_max_trade_participation_rate", 0.0) or 0.0)
        if max_trade > float(gate_contract.get("max_trade_participation_rate_max", 0.005) or 0.005):
            blockers.append("current_overlay_capacity_above_max")
    if base_summary is not None:
        base_cum = float(base_summary.get("full_oos_cumulative_net_return", 0.0) or 0.0)
        base_sharpe = float(base_summary.get("full_oos_period_sharpe", 0.0) or 0.0)
        if base_cum <= float(gate_contract.get("base_signal_cumulative_return_min_exclusive", 0.0) or 0.0):
            blockers.append("base_signal_cumulative_return_non_positive")
        if base_sharpe <= float(gate_contract.get("base_signal_period_sharpe_min_exclusive", 0.0) or 0.0):
            blockers.append("base_signal_period_sharpe_non_positive")
        if current_summary is not None:
            current_cum = float(current_summary.get("full_oos_cumulative_net_return", 0.0) or 0.0)
            if current_cum > 0.0:
                retention = base_cum / current_cum
                if retention < float(gate_contract.get("base_signal_retention_min", 0.0) or 0.0):
                    blockers.append("base_signal_retention_below_min")
            else:
                retention = None
        else:
            retention = None
    else:
        retention = None
    return {
        "passed": not blockers,
        "blocker_codes": blockers,
        "current_overlay_summary": current_summary,
        "base_signal_summary": base_summary,
        "base_signal_retention": retention,
        "rules": gate_contract,
    }
