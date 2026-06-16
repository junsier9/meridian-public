from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research.parallel_1h import simulate_parallel_1h_fake_liquidity_parent_interaction as parent_sim  # noqa: E402


CONTRACT_VERSION = "parallel_1h_fake_liquidity_age_sidecar.v1"
RESEARCH_ID = "fake_liquidity_age_30_180d_sidecar_1h"
DEFAULT_SHUFFLE_ITERATIONS = 200
DEFAULT_HORIZONS = parent_sim.DEFAULT_HORIZONS
PRIMARY_SIDECAR = "age_30_180d_aggregate_haircut"
SIDECAR_WINDOWS = {
    PRIMARY_SIDECAR: (30.0, 180.0),
    "diagnostic_age_30_90d_aggregate_haircut": (30.0, 90.0),
    "diagnostic_age_90_180d_aggregate_haircut": (90.0, 180.0),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Strict simulator for the pre-registered listing-age sidecar redesign of the "
            "fake-liquidity aggregate haircut parent interaction."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _add_symbol_history_age(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    first_by_subject = out.groupby("subject")["open_time_ms"].transform("min")
    out["symbol_first_open_time_ms"] = first_by_subject
    out["symbol_history_age_days_at_event"] = (
        pd.to_numeric(out["open_time_ms"], errors="coerce")
        - pd.to_numeric(out["symbol_first_open_time_ms"], errors="coerce")
    ) / (24.0 * parent_sim.HOUR_MS)
    return out


def _sidecar_mask(frame: pd.DataFrame, *, window: tuple[float, float]) -> pd.Series:
    age = pd.to_numeric(frame["symbol_history_age_days_at_event"], errors="coerce")
    lower, upper = window
    return (
        frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
        & frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
        & age.ge(float(lower))
        & age.lt(float(upper))
    ).fillna(False)


def _simulate_sidecar(
    frame: pd.DataFrame,
    *,
    sidecar_name: str,
    shuffle_iterations: int,
) -> dict[str, Any]:
    if sidecar_name not in SIDECAR_WINDOWS:
        raise ValueError(f"Unknown sidecar: {sidecar_name}")
    local = frame.copy()
    original = local["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    sidecar = _sidecar_mask(local, window=SIDECAR_WINDOWS[sidecar_name])
    local["original_fake_liquidity_capacity_haircut_flag"] = original
    local["fake_liquidity_capacity_haircut_flag"] = sidecar
    candidates = local.loc[local["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    variant_reports = {
        variant: parent_sim._variant_report(
            local,
            candidates,
            variant=variant,
            shuffle_iterations=shuffle_iterations,
        )
        for variant in parent_sim.VARIANT_SIZE_ON_FLAG
    }
    ranked = parent_sim._rank_variants(variant_reports)
    passing = [row["variant"] for row in ranked if row.get("label") == "pass"]
    return {
        "sidecar_name": sidecar_name,
        "age_window_days": {
            "lower_inclusive": SIDECAR_WINDOWS[sidecar_name][0],
            "upper_exclusive": SIDECAR_WINDOWS[sidecar_name][1],
        },
        "candidate_count": int(len(candidates)),
        "original_aggregate_haircut_row_count": int(original.loc[candidates.index].sum()),
        "sidecar_haircut_row_count": int(sidecar.loc[candidates.index].sum()),
        "sidecar_fraction_of_candidates": float(sidecar.loc[candidates.index].mean()) if len(candidates) else None,
        "variant_reports": variant_reports,
        "ranked_variants": ranked,
        "pass_fail_decision": {
            "label": "pass" if passing else "fail",
            "passing_variants": passing,
            "failed_variants": [row["variant"] for row in ranked if row.get("label") != "pass"],
            "decision_rule": (
                "The primary sidecar admits only if at least one variant passes full-symbol strict simulator gates; "
                "diagnostic sidecars are not admission targets."
            ),
        },
    }


def _compact_sidecar(sidecar_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "sidecar_name": sidecar_report["sidecar_name"],
        "label": sidecar_report["pass_fail_decision"]["label"],
        "candidate_count": sidecar_report["candidate_count"],
        "sidecar_haircut_row_count": sidecar_report["sidecar_haircut_row_count"],
        "ranked_variants": sidecar_report["ranked_variants"],
        "passing_variants": sidecar_report["pass_fail_decision"]["passing_variants"],
    }


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    output_path: Path,
    as_of: str,
    shuffle_iterations: int,
) -> dict[str, Any]:
    aged = _add_symbol_history_age(frame)
    sidecars = {
        name: _simulate_sidecar(
            aged,
            sidecar_name=name,
            shuffle_iterations=shuffle_iterations,
        )
        for name in SIDECAR_WINDOWS
    }
    primary = sidecars[PRIMARY_SIDECAR]
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage0",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "preregistration": {
            "path": "docs/quant_research/04_parallel_1h/parallel_1h_fake_liquidity_age_sidecar_preregistration.md",
            "primary_sidecar": PRIMARY_SIDECAR,
            "rule": (
                "capacity_haircut_candidate_flag AND fake_liquidity_capacity_haircut_flag "
                "AND 30 <= local symbol history age days < 180"
            ),
            "no_symbol_name_exclusions": True,
            "watchlist_not_used_as_rescue": ["SYRUP", "SUN", "LUNC", "WIF"],
        },
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "data_sources_and_coverage": parent_sim.haircut_eval._data_sources_and_coverage(aged, meta, root),
        "sidecar_reports": sidecars,
        "ranked_sidecars_compact": [_compact_sidecar(sidecars[name]) for name in sidecars],
        "pass_fail_decision": {
            "label": primary["pass_fail_decision"]["label"],
            "primary_sidecar": PRIMARY_SIDECAR,
            "passing_primary_variants": primary["pass_fail_decision"]["passing_variants"],
            "failed_primary_variants": primary["pass_fail_decision"]["failed_variants"],
            "admission_allowed": primary["pass_fail_decision"]["label"] == "pass",
            "decision_rule": (
                "Only the pre-registered age_30_180d sidecar can admit this run. Split bins are diagnostics only."
            ),
        },
        "next_landing_shape": {
            "recommended_shape": "quarantined_age_sidecar_parent_interaction"
            if primary["pass_fail_decision"]["label"] == "pass"
            else "reject_age_sidecar_redesign",
            "next_step": (
                "If passed, run provider/venue sensitivity before any bridge discussion; if failed, stop this "
                "fake-liquidity branch unless a new exogenous venue sidecar is available."
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = parent_sim.haircut_eval.trap_eval._resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "fake_liquidity_age_30_180d_sidecar_1h.json"
    symbols = parent_sim.haircut_eval.trap_eval._discover_symbols(
        root,
        requested=str(args.symbols),
        limit=int(args.symbol_limit),
    )
    base_frame, meta = parent_sim.haircut_eval.trap_eval._load_research_frame(
        root,
        symbols,
        tuple(DEFAULT_HORIZONS),
    )
    frame = (
        parent_sim.haircut_eval._add_fake_liquidity_capacity_state(base_frame)
        if not base_frame.empty
        else base_frame
    )
    report = _write_report(
        frame=frame,
        meta=meta,
        root=root,
        output_path=output_path,
        as_of=str(args.as_of),
        shuffle_iterations=int(args.shuffle_iterations),
    )
    compact = {
        "output_path": str(output_path),
        "research_id": report["research_id"],
        "preregistration": report["preregistration"],
        "ranked_sidecars_compact": report["ranked_sidecars_compact"],
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
