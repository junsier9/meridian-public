from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import enhengclaw.quant_research.hypothesis_batch as hb  # noqa: E402
from enhengclaw.ops.evidence_contracts import required_source_commit_sha  # noqa: E402
from enhengclaw.quant_research.lab import run_quant_experiments_for_strategies  # noqa: E402

from scripts.quant_research.run_coinglass_h10d_parent_frozen_reset_strict import (  # noqa: E402
    _experiment_summary,
    _first_strict_result,
    _json_default,
    _load_frozen_feature_set,
    _patch_contracts,
    _read_json,
    _utc_now,
    _write_json,
)


AS_OF = "2026-05-04"
TARGET_HORIZON_BARS = 10
CANDIDATE_ID = "r1a_top_liquidity_ex_trx_h10d"
DEFAULT_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_r1a_top_liquidity_ex_trx_h10d.json"
)
DEFAULT_FROZEN_REPLAY_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "h10d_parent_reset_replay_2026-05-04_2026-05-06_01"
)
DEFAULT_STRICT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "r1a_top_liquidity_ex_trx_strict_2026-05-04_2026-05-07_01"
)
DEFAULT_JSON_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "r1a_top_liquidity_ex_trx_strict_2026-05-07.json"
)
DEFAULT_REPORT_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "reports"
    / "r1a_top_liquidity_ex_trx_strict_2026-05-07.md"
)


def _write_batch_summary(
    *,
    strict_root: Path,
    as_of: str,
    manifest: dict[str, Any],
    feature_set: dict[str, Any],
    stage_report: dict[str, Any],
    strict_results: dict[str, Any],
    strict_candidate_list: dict[str, Any],
    source_commit_sha: str,
    compiler_backend: str,
) -> dict[str, Any]:
    cycle_root = strict_root / "hypothesis_batches" / as_of
    entry = dict((manifest.get("entries") or [{}])[0])
    fast_reject_passed = bool(stage_report.get("fast_reject_passed"))
    summary = {
        "status": "success",
        "success": True,
        "generated_at_utc": _utc_now(),
        "as_of": as_of,
        "source_commit_sha": source_commit_sha,
        "compiler_backend": compiler_backend,
        "artifacts_root": str(strict_root),
        "batch_manifest_path": str(hb.HYPOTHESIS_BATCH_MANIFEST_PATH),
        "batch_manifest_contract_version": str(manifest.get("contract_version") or ""),
        "feature_set_ids": [str(feature_set.get("feature_set_id") or "")],
        "candidate_count": 1,
        "candidate_ids": [CANDIDATE_ID],
        "candidate_count_by_horizon": {"h10d": 1},
        "fast_reject_pass_count": 1 if fast_reject_passed else 0,
        "fast_reject_pass_candidate_ids": [CANDIDATE_ID] if fast_reject_passed else [],
        "candidate_count_by_base_mechanism": {str(entry.get("base_mechanism_id") or ""): 1},
        "blocked_candidate_ids": [],
        "strict_candidate_count": len(strict_results["strict_candidates"]),
        "strict_candidate_ids": [str(item["candidate_id"]) for item in strict_results["strict_candidates"]],
        "strict_survivor_count": len(strict_results["strict_survivors"]),
        "strict_survivor_ids": [str(item["candidate_id"]) for item in strict_results["strict_survivors"]],
        "strict_survivor_count_by_horizon": {
            "h10d": sum(1 for item in strict_results["strict_survivors"] if item.get("horizon_id") == "h10d")
        },
        "strict_candidate_list_path": hb.portable_path(Path(str(strict_candidate_list["path"])), repo_root=ROOT),
    }
    out = cycle_root / "batch_summary.json"
    _write_json(out, summary)
    summary["path"] = str(out)
    summary["summary_path"] = str(out)
    return summary


def _stage_summary(stage_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(stage_report.get("path") or ""),
        "fast_reject_passed": stage_report.get("fast_reject_passed"),
        "split_row_counts": stage_report.get("split_row_counts"),
        "validation_net_return": dict(stage_report.get("validation_metrics_lite") or {}).get("net_return"),
        "validation_sharpe": dict(stage_report.get("validation_metrics_lite") or {}).get("sharpe"),
        "test_net_return": dict(stage_report.get("test_metrics_lite") or {}).get("net_return"),
        "test_sharpe": dict(stage_report.get("test_metrics_lite") or {}).get("sharpe"),
        "blocker_codes": stage_report.get("blocker_codes"),
        "advisory_codes": stage_report.get("advisory_codes"),
    }


def _render_report(payload: dict[str, Any]) -> str:
    strict = dict(payload.get("strict_result") or {})
    stage = dict(payload.get("stage_fast_reject") or {})
    experiment = dict(payload.get("experiment") or {})
    frozen = dict(payload.get("frozen_feature_matrix") or {})
    lines = [
        "# R-1a Top Liquidity ex-TRX Strict Validation",
        "",
        f"- generated_at_utc: `{payload.get('generated_at_utc')}`",
        f"- status: `{payload.get('status')}`",
        f"- decision: `{payload.get('decision')}`",
        f"- as_of: `{payload.get('as_of')}`",
        f"- candidate_id: `{payload.get('candidate_id')}`",
        f"- canonical_parent: `{payload.get('canonical_parent')}`",
        f"- manifest_path: `{payload.get('inputs', {}).get('manifest_path')}`",
        f"- strict_root: `{payload.get('inputs', {}).get('strict_root')}`",
        "",
        "## Frozen Matrix",
        "",
        f"- feature_rows: `{frozen.get('feature_rows')}`",
        f"- feature_subject_count: `{frozen.get('feature_subject_count')}`",
        f"- feature_hash: `{frozen.get('feature_hash')}`",
        f"- dataset_fingerprint: `{frozen.get('dataset_fingerprint')}`",
        "",
        "## Candidate Contract",
        "",
        "- universe_filter: `top_liquidity` whitelist excluding `TRX`",
        "- promotion_state: `quarantined_research_candidate`",
        "- parent inheritance: `blocked`",
        "",
        "## Fast Reject",
        "",
        f"- fast_reject_passed: `{stage.get('fast_reject_passed')}`",
        f"- validation_net_return / sharpe: `{stage.get('validation_net_return')}` / `{stage.get('validation_sharpe')}`",
        f"- test_net_return / sharpe: `{stage.get('test_net_return')}` / `{stage.get('test_sharpe')}`",
        f"- blocker_codes: `{', '.join(stage.get('blocker_codes') or []) or 'none'}`",
        f"- advisory_codes: `{', '.join(stage.get('advisory_codes') or []) or 'none'}`",
        f"- fast_reject_report_path: `{stage.get('path')}`",
        "",
        "## Strict Result",
        "",
        f"- strict_validation_passed: `{strict.get('strict_validation_passed')}`",
        f"- validation_contract_status: `{strict.get('validation_contract_status')}`",
        f"- falsification_status: `{strict.get('falsification_status')}`",
        f"- statistical_falsification_status: `{strict.get('statistical_falsification_status')}`",
        f"- statistical_falsification_blocker_codes: `{', '.join(strict.get('statistical_falsification_blocker_codes') or []) or 'none'}`",
        f"- alpha_experiment_card_status: `{strict.get('alpha_experiment_card_status')}`",
        f"- alpha_experiment_card_go_no_go: `{strict.get('alpha_experiment_card_go_no_go')}`",
        f"- alpha_experiment_card_blocker_codes: `{', '.join(strict.get('alpha_experiment_card_blocker_codes') or []) or 'none'}`",
        f"- credible_research_evidence: `{strict.get('credible_research_evidence')}`",
        f"- strict_result_path: `{strict.get('path')}`",
        "",
        "## Experiment",
        "",
        f"- experiment_id: `{experiment.get('experiment_id')}`",
        f"- alpha_card_path: `{experiment.get('alpha_card_path')}`",
        f"- validation_report_path: `{experiment.get('validation_report_path')}`",
        f"- validation_metrics.net_return / sharpe: `{dict(experiment.get('validation_metrics') or {}).get('net_return')}` / `{dict(experiment.get('validation_metrics') or {}).get('sharpe')}`",
        f"- test_metrics.net_return / sharpe: `{dict(experiment.get('test_metrics') or {}).get('net_return')}` / `{dict(experiment.get('test_metrics') or {}).get('sharpe')}`",
        "",
        "## Next Gate",
        "",
        str(payload.get("next_gate") or ""),
        "",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    manifest_path = args.manifest.expanduser().resolve()
    replay_root = args.frozen_replay_root.expanduser().resolve()
    strict_root = args.strict_root.expanduser().resolve()
    json_out = args.json_out.expanduser().resolve()
    report_out = args.report_out.expanduser().resolve()

    payload: dict[str, Any] = {
        "status": "running",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "as_of": args.as_of,
        "candidate_id": CANDIDATE_ID,
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "inputs": {
            "manifest_path": str(manifest_path),
            "frozen_replay_root": str(replay_root),
            "strict_root": str(strict_root),
            "json_out": str(json_out),
            "report_out": str(report_out),
            "compiler_backend": str(args.compiler_backend),
        },
        "promotion_allowed": False,
        "alpha_rerun_allowed": False,
    }

    try:
        manifest = _read_json(manifest_path)
        entries = list(manifest.get("entries") or [])
        if len(entries) != 1:
            raise ValueError(f"expected one manifest entry, found {len(entries)}")
        entry = dict(entries[0])
        if str(entry.get("candidate_id") or "") != CANDIDATE_ID:
            raise ValueError(f"unexpected candidate_id: {entry.get('candidate_id')!r}")
        if int(entry.get("target_horizon_bars") or 0) != int(args.target_horizon_bars):
            raise ValueError("manifest horizon does not match requested target horizon")
        _patch_contracts(
            manifest_path=manifest_path,
            manifest=manifest,
            entry=entry,
            target_horizon_bars=int(args.target_horizon_bars),
        )
        loaded_manifest = hb.load_cross_sectional_hypothesis_batch_manifest(path=manifest_path)
        entry = dict(loaded_manifest["entries"][0])
        feature_set, feature_manifest, dataset_manifest, frame = _load_frozen_feature_set(
            replay_root=replay_root,
            as_of=args.as_of,
        )
        source_commit_sha = required_source_commit_sha(repo_root=ROOT)
        cycle_root = strict_root / "hypothesis_batches" / args.as_of
        fast_reject_contract = hb.load_fast_reject_contract()
        stage_report = hb._run_fast_reject_candidate(
            as_of=args.as_of,
            batch_root=cycle_root,
            candidate_entry=entry,
            feature_sets=[feature_set],
            fast_reject_contract=fast_reject_contract,
            source_commit_sha=source_commit_sha,
        )
        experiments: list[dict[str, Any]] = []
        if bool(stage_report.get("fast_reject_passed")):
            strict_strategy = hb._materialize_strict_strategy_entry(entry)
            experiments = run_quant_experiments_for_strategies(
                as_of=args.as_of,
                artifacts_root=strict_root,
                strategies=[strict_strategy],
                feature_sets=[feature_set],
                compiler_backend=str(args.compiler_backend),
                source_commit_sha=source_commit_sha,
            )
        strict_results = hb._write_strict_results(
            as_of=args.as_of,
            batch_root=cycle_root,
            reports=[stage_report],
            strict_experiments=experiments,
            source_commit_sha=source_commit_sha,
        )
        strict_candidate_list = hb._write_strict_candidate_list(
            path=cycle_root / "strict_candidate_list.json",
            as_of=args.as_of,
            manifest=loaded_manifest,
            strict_results=strict_results,
            source_commit_sha=source_commit_sha,
        )
        batch_summary = _write_batch_summary(
            strict_root=strict_root,
            as_of=args.as_of,
            manifest=loaded_manifest,
            feature_set=feature_set,
            stage_report=stage_report,
            strict_results=strict_results,
            strict_candidate_list=strict_candidate_list,
            source_commit_sha=source_commit_sha,
            compiler_backend=str(args.compiler_backend),
        )
        strict_result = _first_strict_result(strict_root, args.as_of, CANDIDATE_ID)
        strict_passed = bool(strict_result.get("strict_validation_passed"))
        payload.update(
            {
                "status": "pass_r1a_strict_validation" if strict_passed else "fail_closed_r1a_strict_validation",
                "decision": "r1a_candidate_survived_strict_validation_requires_promotion_guard"
                if strict_passed
                else "r1a_candidate_failed_strict_falsification_keep_quarantined",
                "alpha_rerun_allowed": bool(strict_passed),
                "promotion_allowed": False,
                "source_commit_sha": source_commit_sha,
                "frozen_feature_matrix": {
                    "feature_set_id": feature_set.get("feature_set_id"),
                    "feature_rows": int(len(frame)),
                    "feature_subject_count": int(frame["subject"].nunique()) if "subject" in frame.columns else None,
                    "feature_hash": feature_manifest.get("feature_hash"),
                    "feature_matrix_sha256": feature_manifest.get("feature_matrix_sha256"),
                    "dataset_fingerprint": feature_manifest.get("dataset_fingerprint")
                    or dataset_manifest.get("dataset_fingerprint"),
                    "dataset_min_timestamp_utc": dataset_manifest.get("min_timestamp_utc"),
                    "dataset_max_timestamp_utc": dataset_manifest.get("max_timestamp_utc"),
                    "feature_manifest_path": str(Path(str(feature_set["manifest_path"]))),
                    "features_path": str(Path(str(feature_set["features_path"]))),
                    "dataset_manifest_path": str(Path(str(feature_set["dataset_manifest_path"]))),
                },
                "candidate_contract": {
                    "lifecycle": "quarantined",
                    "universe_filter": dict(entry.get("universe_filter") or {}),
                    "profile_constraints": dict(entry.get("profile_constraints") or {}),
                    "parent_inheritance_allowed": False,
                },
                "stage_fast_reject": _stage_summary(stage_report),
                "strict_result": strict_result,
                "strict_candidate_list": {
                    "path": str(strict_candidate_list.get("path")),
                    "strict_candidate_count": strict_candidate_list.get("strict_candidate_count"),
                    "strict_survivor_count": strict_candidate_list.get("strict_survivor_count"),
                    "strict_candidates": strict_candidate_list.get("strict_candidates"),
                    "strict_survivors": strict_candidate_list.get("strict_survivors"),
                },
                "batch_summary": {
                    "path": str(batch_summary.get("path") or batch_summary.get("summary_path") or ""),
                    "fast_reject_pass_count": batch_summary.get("fast_reject_pass_count"),
                    "strict_candidate_count": batch_summary.get("strict_candidate_count"),
                    "strict_survivor_count": batch_summary.get("strict_survivor_count"),
                },
                "experiment": _experiment_summary(experiments),
                "next_gate": "Strict validation passed for R-1a. Keep it quarantined until h10d promotion guard, overlay ablation, and independent OOS review complete."
                if strict_passed
                else "Strict validation failed for R-1a. Keep the residual sublane quarantined and do not optimize against this result without a new mechanism reason.",
            }
        )
    except Exception as exc:  # pragma: no cover - operational script
        payload.update(
            {
                "status": "error",
                "decision": "fail_closed_runner_error",
                "alpha_rerun_allowed": False,
                "promotion_allowed": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "next_gate": "Fix the runner error before interpreting R-1a.",
            }
        )
        _write_json(json_out, payload)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(_render_report(payload), encoding="utf-8")
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1

    _write_json(json_out, payload)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(_render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run R-1a top_liquidity_ex_trx as a quarantined new candidate through strict validation."
    )
    parser.add_argument("--as-of", default=AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=TARGET_HORIZON_BARS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--frozen-replay-root", type=Path, default=DEFAULT_FROZEN_REPLAY_ROOT)
    parser.add_argument("--strict-root", type=Path, default=DEFAULT_STRICT_ROOT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--compiler-backend", default="deterministic")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
