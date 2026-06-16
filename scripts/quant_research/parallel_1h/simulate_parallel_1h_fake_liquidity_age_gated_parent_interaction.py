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


CONTRACT_VERSION = "parallel_1h_fake_liquidity_age_gated_parent_interaction.v1"
RESEARCH_ID = "fake_liquidity_age_gated_parent_interaction_1h"
DEFAULT_HORIZONS = parent_sim.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = parent_sim.DEFAULT_SHUFFLE_ITERATIONS
AGE_GATE_MIN_DAYS = 30.0
AGE_GATE_MAX_DAYS = 180.0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pre-registered listing-age gated 1h parent-interaction simulator for the aggregate "
            "fake-liquidity state. Research diagnostic only; does not touch h10d promotion state."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _add_listing_age_gate(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["subject", "open_time_ms"]).copy()
    first_open = out.groupby("subject")["open_time_ms"].transform("min")
    out["symbol_history_age_days_at_signal"] = (
        pd.to_numeric(out["open_time_ms"], errors="coerce") - pd.to_numeric(first_open, errors="coerce")
    ) / (24.0 * parent_sim.HOUR_MS)
    out["listing_age_30_180d_gate_flag"] = (
        pd.to_numeric(out["symbol_history_age_days_at_signal"], errors="coerce").ge(AGE_GATE_MIN_DAYS)
        & pd.to_numeric(out["symbol_history_age_days_at_signal"], errors="coerce").lt(AGE_GATE_MAX_DAYS)
    ).fillna(False)
    out["raw_fake_liquidity_capacity_haircut_flag"] = (
        out["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    )
    out["fake_liquidity_capacity_haircut_flag"] = (
        out["raw_fake_liquidity_capacity_haircut_flag"]
        & out["listing_age_30_180d_gate_flag"].fillna(False).astype(bool)
    ).fillna(False)
    return out


def _age_gate_summary(frame: pd.DataFrame) -> dict[str, Any]:
    candidates = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    if candidates.empty:
        return {"candidate_count": 0}
    raw = candidates["raw_fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    gated = candidates["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
    age = pd.to_numeric(candidates["symbol_history_age_days_at_signal"], errors="coerce")
    bins = [-np.inf, 30, 90, 180, 365, np.inf]
    labels = ["lt_30d", "30_90d", "90_180d", "180_365d", "gte_365d"]
    local = candidates.copy()
    local["listing_age_bin"] = pd.cut(age, bins=bins, labels=labels)
    by_bin: dict[str, Any] = {}
    for label, group in local.groupby("listing_age_bin", observed=True):
        raw_group = group["raw_fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
        gated_group = group["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool)
        by_bin[str(label)] = {
            "row_count": int(len(group)),
            "raw_haircut_row_count": int(raw_group.sum()),
            "age_gated_policy_row_count": int(gated_group.sum()),
            "raw_haircut_fraction": float(raw_group.mean()) if len(group) else None,
            "age_gated_policy_fraction": float(gated_group.mean()) if len(group) else None,
        }
    return {
        "candidate_count": int(len(candidates)),
        "raw_aggregate_haircut_row_count": int(raw.sum()),
        "age_gated_policy_row_count": int(gated.sum()),
        "age_gate_candidate_row_count": int(candidates["listing_age_30_180d_gate_flag"].fillna(False).sum()),
        "age_gate_candidate_fraction": float(candidates["listing_age_30_180d_gate_flag"].fillna(False).mean()),
        "policy_row_retention_vs_raw_haircut": float(gated.sum() / max(int(raw.sum()), 1)),
        "age_days_summary": {
            "mean": float(age.mean()) if age.notna().any() else None,
            "p10": float(age.quantile(0.10)) if age.notna().any() else None,
            "median": float(age.median()) if age.notna().any() else None,
            "p90": float(age.quantile(0.90)) if age.notna().any() else None,
        },
        "by_listing_age_bin": by_bin,
    }


def _variant_reports(
    frame: pd.DataFrame,
    *,
    shuffle_iterations: int,
) -> dict[str, Any]:
    candidates = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    return {
        variant: parent_sim._variant_report(
            frame,
            candidates,
            variant=variant,
            shuffle_iterations=shuffle_iterations,
        )
        for variant in parent_sim.VARIANT_SIZE_ON_FLAG
    }


def _rank_variants(reports: dict[str, Any]) -> list[dict[str, Any]]:
    return parent_sim._rank_variants(reports)


def _overall_decision(reports: dict[str, Any]) -> dict[str, Any]:
    ranked = _rank_variants(reports)
    passing = [row["variant"] for row in ranked if row.get("label") == "pass"]
    failed = [row["variant"] for row in ranked if row.get("label") != "pass"]
    return {
        "label": "pass" if passing else "fail",
        "passing_variants": passing,
        "failed_variants": failed,
        "data_mining_quarantine": True,
        "admission_allowed": False,
        "h10d_canonical_parent_status": "not_read_not_modified",
        "decision_rule": (
            "Per-variant pass means strict Stage 0 simulator gates passed. Because this age gate was derived "
            "from prior attribution, even a pass is quarantined and requires a fresh out-of-sample or walk-forward "
            "confirmation before any admission or h10d bridge."
        ),
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
    reports = _variant_reports(frame, shuffle_iterations=shuffle_iterations) if not frame.empty else {}
    ranked = _rank_variants(reports) if reports else []
    decision = _overall_decision(reports) if reports else {
        "label": "blocked",
        "blockers": ["no_research_frame"],
        "passing_variants": [],
        "failed_variants": [],
        "data_mining_quarantine": True,
        "admission_allowed": False,
        "h10d_canonical_parent_status": "not_read_not_modified",
    }
    candidates = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage0",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "pre_registration": {
            "source": "Prior symbol/provider sensitivity attribution suggested 30_90d and 90_180d listing-age bins.",
            "gate": "30 <= symbol_history_age_days_at_signal < 180",
            "important_caveat": (
                "symbol_history_age_days_at_signal is measured from the first local 1h bar, not a trusted exchange "
                "listing timestamp. This is a Stage 0 proxy and remains quarantined."
            ),
            "no_post_hoc_symbol_exclusion": True,
        },
        "data_sources_and_coverage": parent_sim.haircut_eval._data_sources_and_coverage(frame, meta, root),
        "parent_definition": {
            "parent": "capacity_haircut_candidate_flag",
            "policy_state": "raw_fake_liquidity_capacity_haircut_flag AND listing_age_30_180d_gate_flag",
            "candidate_count": int(len(candidates)),
        },
        "age_gate_summary": _age_gate_summary(frame),
        "shuffle_iterations": int(shuffle_iterations),
        "variant_reports": reports,
        "ranked_variants": ranked,
        "pass_fail_decision": decision,
        "next_landing_shape": {
            "recommended_shape": "quarantined_age_gated_parent_interaction"
            if decision.get("passing_variants")
            else "fail_closed_age_gate",
            "next_step": (
                "If any variant passes, run walk-forward/OOS split and provider-concordance sensitivity before "
                "admission. If none passes, do not continue this rescue path."
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
    output_path = output_dir / "fake_liquidity_age_gated_parent_interaction_1h.json"
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
    if not frame.empty:
        frame = _add_listing_age_gate(frame)
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
        "loaded_symbol_count": report["data_sources_and_coverage"].get("loaded_symbol_count"),
        "row_count": report["data_sources_and_coverage"].get("row_count"),
        "age_gate_summary": report.get("age_gate_summary"),
        "ranked_variants": report.get("ranked_variants"),
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
