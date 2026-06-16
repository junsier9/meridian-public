from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import read_json


ROOT = Path(__file__).resolve().parents[3]
EXECUTION_COST_MODEL_PATH = ROOT / "config" / "quant_research" / "execution_cost_model.json"
EXECUTION_COST_MODEL_VERSION = "quant_execution_cost_model.v1"


def load_execution_cost_model() -> dict[str, Any]:
    return read_json(EXECUTION_COST_MODEL_PATH)


def resolve_execution_cost_model(
    *,
    contract: dict[str, Any] | None = None,
    scenario: str = "base",
) -> dict[str, Any]:
    payload = dict(contract or load_execution_cost_model())
    normalized_scenario = str(scenario or "base").strip().lower() or "base"
    if normalized_scenario not in {"base", "stress"}:
        raise ValueError(f"unsupported execution cost scenario: {scenario}")
    venues = dict(payload.get("venues") or {})
    stress_multipliers = dict(payload.get("stress_multipliers") or {})
    spread_multiplier = 1.0
    impact_multiplier = 1.0
    liquidity_volume_scale = 1.0
    if normalized_scenario == "stress":
        spread_multiplier = float(stress_multipliers.get("spread_x", 1.5) or 1.5)
        impact_multiplier = float(stress_multipliers.get("impact_x", 1.5) or 1.5)
        liquidity_volume_scale = float(stress_multipliers.get("liquidity_x", 0.5) or 0.5)
    resolved_venues: dict[str, Any] = {}
    for venue_name in ("spot", "perp"):
        venue_payload = dict(venues.get(venue_name) or {})
        resolved_venues[venue_name] = {
            "fee_bps_one_way": float(venue_payload.get("fee_bps_one_way", 0.0) or 0.0),
            "half_spread_bps": float(venue_payload.get("half_spread_bps", 0.0) or 0.0) * spread_multiplier,
            "impact_coefficient_bps": float(venue_payload.get("impact_coefficient_bps", 0.0) or 0.0) * impact_multiplier,
        }
    return {
        "contract_version": str(payload.get("contract_version") or EXECUTION_COST_MODEL_VERSION),
        "scenario": normalized_scenario,
        "latency_bars": max(int(payload.get("latency_bars", 1) or 1), 1),
        "spot_short_borrow_bps_per_day": float(payload.get("spot_short_borrow_bps_per_day", 15.0) or 15.0),
        "liquidity_volume_scale": max(float(liquidity_volume_scale or 1.0), 1e-9),
        "stress_multipliers": {
            "spread_x": float(stress_multipliers.get("spread_x", 1.5) or 1.5),
            "impact_x": float(stress_multipliers.get("impact_x", 1.5) or 1.5),
            "liquidity_x": float(stress_multipliers.get("liquidity_x", 0.5) or 0.5),
        },
        "venues": resolved_venues,
    }


def execution_venue_for_constraints(constraints: dict[str, Any]) -> str:
    explicit = str(constraints.get("execution_venue") or "").strip().lower()
    if explicit in {"spot", "perp"}:
        return explicit
    if "spot_only" not in constraints:
        return "spot"
    return "spot" if bool(constraints.get("spot_only")) else "perp"
