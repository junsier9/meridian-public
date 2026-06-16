from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import yaml


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _as_yaml_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return []


def _as_int(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that the deployable live config preserves the owner-approved "
            "12-factor frontier scorer and PIT rolling live universe state."
        )
    )
    parser.add_argument("--config", required=True, help="Path to the live runner YAML.")
    parser.add_argument(
        "--allow-frontier-dormant",
        action="store_true",
        help="Opt-out escape hatch for a separately approved dormant rollback deploy.",
    )
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    if not isinstance(doc, dict):
        raise SystemExit(f"{path} did not load as a YAML mapping")
    return doc


def _validate(doc: dict[str, Any], *, allow_frontier_dormant: bool) -> dict[str, Any]:
    blockers: list[str] = []

    strategy = doc.get("strategy") if isinstance(doc.get("strategy"), dict) else {}
    frontier = strategy.get("frontier") if isinstance(strategy.get("frontier"), dict) else {}
    frontier_enabled = frontier.get("enabled") is True
    if not frontier_enabled and not allow_frontier_dormant:
        blockers.append("frontier_enabled_not_true")

    for key in (
        "weights_contract_path",
        "weights_file_sha256",
        "weights_spec_hash",
        "scoring_config_path",
        "scoring_config_sha256",
    ):
        if not str(frontier.get(key) or "").strip():
            blockers.append(f"frontier_missing_{key}")

    overlay = frontier.get("overlay") if isinstance(frontier.get("overlay"), dict) else {}
    if overlay.get("enabled") is not True:
        blockers.append("frontier_overlay_enabled_not_true")
    for key in ("contract_path", "file_sha256", "spec_hash"):
        if not str(overlay.get(key) or "").strip():
            blockers.append(f"frontier_overlay_missing_{key}")

    universe_policy = doc.get("universe_policy") if isinstance(doc.get("universe_policy"), dict) else {}
    mode = str(universe_policy.get("live_selection_mode") or "").strip()
    if mode != "pit_rolling":
        blockers.append(f"live_selection_mode_not_pit_rolling:{mode or '<missing>'}")

    try:
        top_n = int(universe_policy.get("top_n") or 0)
    except (TypeError, ValueError):
        top_n = 0
    if top_n <= 0:
        blockers.append(f"top_n_not_positive:{top_n}")

    if not isinstance(universe_policy.get("candidate_symbols"), list):
        blockers.append("candidate_symbols_not_yaml_list")
    candidate_symbols = _as_yaml_list(universe_policy.get("candidate_symbols"))
    unique_candidates = sorted(set(candidate_symbols))
    if len(candidate_symbols) != len(unique_candidates):
        blockers.append("candidate_symbols_not_unique")
    if len(candidate_symbols) < max(top_n, 0):
        blockers.append(f"candidate_symbols_below_top_n:{len(candidate_symbols)}<{top_n}")
    non_usdt = [symbol for symbol in candidate_symbols if not symbol.endswith("USDT")]
    if non_usdt:
        blockers.append("candidate_symbols_not_usdt:" + ",".join(non_usdt))

    market_data = doc.get("market_data") if isinstance(doc.get("market_data"), dict) else {}
    market_symbols = _as_list(market_data.get("symbols"))
    missing_market_symbols = sorted(set(market_symbols) - set(candidate_symbols))
    if missing_market_symbols:
        blockers.append("market_data_symbols_missing_from_candidate_symbols:" + ",".join(missing_market_symbols))

    churn_gate = universe_policy.get("churn_gate") if isinstance(universe_policy.get("churn_gate"), dict) else {}
    churn_gate_enabled = churn_gate.get("enabled") is True
    if universe_policy.get("churn_gate") is not None and not isinstance(universe_policy.get("churn_gate"), dict):
        blockers.append("churn_gate_not_mapping")
    if churn_gate_enabled:
        threshold_keys = ("max_entered_count", "max_exited_count", "max_churn_count", "max_churn_ratio")
        if not any(churn_gate.get(key) is not None for key in threshold_keys):
            blockers.append("churn_gate_missing_thresholds")
        for key in ("max_entered_count", "max_exited_count", "max_churn_count"):
            value = _as_int(churn_gate.get(key))
            if value is None:
                blockers.append(f"churn_gate_{key}_invalid")
            elif value < 0:
                blockers.append(f"churn_gate_{key}_negative:{value}")
            elif key == "max_churn_count" and top_n > 0 and value > top_n * 2:
                blockers.append(f"churn_gate_{key}_above_possible_max:{value}>{top_n * 2}")
            elif key != "max_churn_count" and top_n > 0 and value > top_n:
                blockers.append(f"churn_gate_{key}_above_top_n:{value}>{top_n}")
        ratio = _as_float(churn_gate.get("max_churn_ratio"))
        if ratio is None:
            blockers.append("churn_gate_max_churn_ratio_invalid")
        elif ratio < 0.0 or ratio > 2.0:
            blockers.append(f"churn_gate_max_churn_ratio_out_of_range:{ratio}")
        bootstrap = _as_yaml_list(churn_gate.get("bootstrap_reference_symbols"))
        if not isinstance(churn_gate.get("bootstrap_reference_symbols"), list):
            blockers.append("churn_gate_bootstrap_reference_symbols_not_yaml_list")
        if top_n > 0 and len(bootstrap) != top_n:
            blockers.append(f"churn_gate_bootstrap_reference_size_not_top_n:{len(bootstrap)}!={top_n}")
        if len(bootstrap) != len(set(bootstrap)):
            blockers.append("churn_gate_bootstrap_reference_not_unique")
        missing_bootstrap = sorted(set(bootstrap) - set(candidate_symbols))
        if missing_bootstrap:
            blockers.append("churn_gate_bootstrap_reference_missing_from_candidate_symbols:" + ",".join(missing_bootstrap))
        non_usdt_bootstrap = [symbol for symbol in bootstrap if not symbol.endswith("USDT")]
        if non_usdt_bootstrap:
            blockers.append("churn_gate_bootstrap_reference_not_usdt:" + ",".join(non_usdt_bootstrap))

    return {
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "frontier_enabled": frontier_enabled,
        "frontier_overlay_enabled": overlay.get("enabled") is True,
        "live_selection_mode": mode or None,
        "top_n": top_n,
        "candidate_symbol_count": len(candidate_symbols),
        "candidate_symbols": candidate_symbols,
        "candidate_symbols_sorted": candidate_symbols == unique_candidates,
        "market_symbol_count": len(market_symbols),
        "churn_gate_enabled": churn_gate_enabled,
    }


def main() -> int:
    args = _parse_args()
    path = Path(args.config)
    summary = _validate(_load_yaml(path), allow_frontier_dormant=bool(args.allow_frontier_dormant))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
