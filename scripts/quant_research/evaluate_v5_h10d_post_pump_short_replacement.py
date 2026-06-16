from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v5_score,
)
CONTRACT_VERSION = "quant_v5_h10d_post_pump_short_replacement_diagnostic.v1"
DEFAULT_AS_OF = "2026-05-01"
DEFAULT_TARGET_HORIZON_BARS = 10
BASELINE_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json"
)
CANDIDATE_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d.json"
)
BASELINE_CANDIDATE_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
CANDIDATE_CANDIDATE_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retest the SP-K `replace_mid_v1` short replacement rule on the v5_h10d parent."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    parser.add_argument("--force-cycle-run", action="store_true")
    return parser


def _variant_specs() -> list[dict[str, Any]]:
    return [
        {
            "label": "baseline_v5_rw_bridge_no_overlay_h10d",
            "candidate_id": BASELINE_CANDIDATE_ID,
            "manifest_path": BASELINE_MANIFEST_PATH,
            "description": "canonical v5_rw_bridge_no_overlay_h10d parent under the execution-aligned label contract.",
        },
        {
            "label": "replace_mid_v1_no_news",
            "candidate_id": CANDIDATE_CANDIDATE_ID,
            "manifest_path": CANDIDATE_MANIFEST_PATH,
            "description": (
                "Apply the checked-in SP-K `replace_mid_v1` short-slot rule to the canonical "
                "v5_rw_bridge_no_overlay_h10d parent, without any news-veto layer."
            ),
        },
    ]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "v5_h10d_post_pump_short_replacement_diagnostic.json")

    specs = _variant_specs()
    report_paths: dict[str, dict[str, str]] = {}
    variant_metrics: dict[str, dict[str, Any]] = {}
    generated_manifests: dict[str, str] = {}

    for spec in specs:
        manifest_path = Path(spec["manifest_path"])
        generated_manifests[spec["label"]] = str(manifest_path)

        validation_path = base_eval._validation_report_path(as_of=as_of, candidate_id=spec["candidate_id"])
        fast_reject_path = base_eval._fast_reject_report_path(as_of=as_of, candidate_id=spec["candidate_id"])
        report_paths[spec["label"]] = {
            "validation_report": str(validation_path),
            "fast_reject_report": str(fast_reject_path),
        }

        need_run = args.force_cycle_run or not validation_path.exists() and not fast_reject_path.exists()
        if not args.skip_cycle_run and need_run:
            base_eval._run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
            )

        if validation_path.exists():
            variant_metrics[spec["label"]] = base_eval._extract_validation_metrics(base_eval._load_json(validation_path))
        elif fast_reject_path.exists():
            variant_metrics[spec["label"]] = base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path))
        else:
            variant_metrics[spec["label"]] = {"report_kind": "missing"}

    baseline_metrics = variant_metrics.get("baseline_v5_rw_bridge_no_overlay_h10d", {})
    candidate_metrics = variant_metrics.get("replace_mid_v1_no_news", {})
    comparison = base_eval._compare_metric_dicts(
        baseline=baseline_metrics,
        candidate=candidate_metrics,
    )

    risk_frame = base_eval._build_risk_frame(
        base_eval._features_artifact_path(as_of),
        target_horizon_bars=args.target_horizon_bars,
    )
    selection_change = base_eval._selection_change_diagnostic(
        frame=risk_frame,
        baseline_scorer=xs_alpha_ontology_v5_score,
        candidate_scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        long_count=3,
        short_count=3,
        target_horizon_bars=args.target_horizon_bars,
    )
    short_risk = {
        "baseline_v5_bottom3": base_eval._short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_v5_score,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "replace_mid_v1_no_news_bottom3": base_eval._short_risk_diagnostic(
            frame=risk_frame,
            scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        ),
    }

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": int(args.target_horizon_bars),
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "features_artifact": str(base_eval._features_artifact_path(as_of)),
        "generated_manifests": generated_manifests,
        "cycle_report_paths": report_paths,
        "variant_metrics": variant_metrics,
        "comparison_vs_baseline": comparison,
        "selection_change_diagnostics": selection_change,
        "short_cost_and_squeeze_risk": short_risk,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
