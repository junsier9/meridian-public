from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.contracts import portable_path, read_json, utc_now, write_json
from enhengclaw.quant_research.fixed_set_comparison import pairwise_comparison, periods_per_year
from enhengclaw.quant_research.overlay_ablation import (
    build_overlay_ablation_gate_assessment,
    load_overlay_ablation_contract,
    overlay_ablation_candidate_entries,
    overlay_ablation_variant_entries,
)


CONTRACT = load_overlay_ablation_contract()
BOOTSTRAP_SEED = int(dict(CONTRACT.get("bootstrap") or {}).get("seed", 20260503) or 20260503)
BOOTSTRAP_ITERATIONS = int(dict(CONTRACT.get("bootstrap") or {}).get("iterations", 4000) or 4000)


def _resolve_repo_path(path_text: str | Path) -> Path:
    candidate = Path(str(path_text))
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _candidate_experiment_root(*, artifacts_root: Path, experiment_id: str) -> Path:
    root = artifacts_root / "experiments" / experiment_id
    if not root.exists():
        raise FileNotFoundError(f"experiment artifact missing: {root}")
    return root


def _load_partial(*, artifacts_root: Path, output_date: str, key: str) -> dict[str, Any]:
    partial_root = artifacts_root / "factor_reports" / (
        f"{output_date}-alpha_ontology_h10d_overlay_ablation-{key.replace('__', '-')}"
    )
    summary_path = partial_root / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"missing overlay ablation partial: {summary_path}")
    summary = dict(read_json(summary_path))
    summaries = list(summary.get("variant_summaries") or [])
    if len(summaries) != 1:
        raise ValueError(f"partial {summary_path} expected exactly one variant summary")
    returns_path = _resolve_repo_path(dict(summary.get("artifacts") or {})["aligned_period_returns_csv"])
    returns_frame = pd.read_csv(returns_path)
    if key not in returns_frame.columns:
        raise ValueError(f"partial returns missing {key}: {returns_path}")
    periods = returns_frame[["timestamp_ms", "timestamp_utc", key]].rename(columns={key: "net_period_return"})
    return {
        "summary": dict(summaries[0]),
        "periods": periods,
        "periods_per_year": periods_per_year(bar_interval_ms=86400000, evaluation_step_bars=10),
    }


def _write_markdown(*, output_path: Path, title: str, section: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Status: `{section.get('status')}`")
    if section.get("candidate_label"):
        lines.append(f"- Candidate: `{section.get('candidate_label')}`")
    promotion_gate = dict(section.get("promotion_gate") or {})
    if promotion_gate:
        lines.append(f"- Promotion gate passed: `{promotion_gate.get('passed')}`")
        lines.append(f"- Promotion blockers: `{', '.join(promotion_gate.get('blocker_codes') or []) or 'none'}`")
    lines.append("")
    lines.append("| Candidate | Overlay | WF Median | Full OOS CumRet | Full OOS Sharpe | Loss Period Frac | Worst Regime | Max Trade Part. |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in list(section.get("variant_summaries") or []):
        lines.append(
            "| {candidate} | {overlay} | {wf:.3f} | {cum:.3f} | {sharpe:.3f} | {loss:.3f} | {worst:.3f} | {max_trade:.4f} |".format(
                candidate=item["candidate_label"],
                overlay=item["overlay_label"],
                wf=float(item["walk_forward_median_oos_sharpe"]),
                cum=float(item["full_oos_cumulative_net_return"]),
                sharpe=float(item["full_oos_period_sharpe"]),
                loss=float(item["full_oos_loss_period_fraction"]),
                worst=float(item["worst_regime_median_oos_sharpe"]),
                max_trade=float(item["full_oos_max_trade_participation_rate"]),
            )
        )
    if section.get("pairwise_results"):
        lines.append("")
        lines.append("## Pairwise Results")
        lines.append("")
        lines.append("| A | B | N | CumRet Diff | Sharpe Diff | P(A>B CumRet) |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
        for item in list(section.get("pairwise_results") or []):
            lines.append(
                "| {a} | {b} | {n} | {cum:.3f} | {sharpe:.3f} | {prob:.3f} |".format(
                    a=item["candidate_a"],
                    b=item["candidate_b"],
                    n=int(item["aligned_period_count"]),
                    cum=float(item["observed_cumulative_return_diff"]),
                    sharpe=float(item["observed_sharpe_diff"]),
                    prob=float(dict(item.get("bootstrap") or {}).get("probability_a_beats_b_on_cumulative_return", 0.0) or 0.0),
                )
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _candidate_section(
    *,
    candidate_entry: dict[str, Any],
    results_by_key: dict[str, dict[str, Any]],
    pairwise_results: list[dict[str, Any]],
    experiment_root: Path,
) -> dict[str, Any]:
    candidate_label = str(candidate_entry.get("label") or "").strip()
    variant_summaries = [
        dict(results_by_key[f"{candidate_label}__{str(variant.get('label') or '').strip()}"]["summary"])
        for variant in overlay_ablation_variant_entries(CONTRACT)
    ]
    candidate_pairwise = [
        dict(item)
        for item in pairwise_results
        if str(item.get("candidate_a") or "").startswith(f"{candidate_label}__")
        and str(item.get("candidate_b") or "").startswith(f"{candidate_label}__")
    ]
    promotion_gate = build_overlay_ablation_gate_assessment(
        variant_summaries=variant_summaries,
        contract=CONTRACT,
    )
    return {
        "contract_version": str(CONTRACT.get("contract_version") or ""),
        "status": "computed",
        "candidate_label": candidate_label,
        "experiment_id": str(candidate_entry.get("experiment_id") or ""),
        "overlay_variant_labels": [
            str(item.get("label") or "").strip()
            for item in overlay_ablation_variant_entries(CONTRACT)
            if str(item.get("label") or "").strip()
        ],
        "variant_summaries": variant_summaries,
        "pairwise_results": candidate_pairwise,
        "promotion_gate": promotion_gate,
        "artifact_paths": {
            "comparison_json_path": portable_path(experiment_root / "overlay_ablation.json", repo_root=ROOT),
            "comparison_markdown_path": portable_path(experiment_root / "overlay_ablation.md", repo_root=ROOT),
            "aligned_period_returns_path": portable_path(
                experiment_root / "overlay_ablation_aligned_period_returns.csv",
                repo_root=ROOT,
            ),
            "pairwise_comparisons_path": portable_path(
                experiment_root / "overlay_ablation_pairwise_comparisons.csv",
                repo_root=ROOT,
            ),
        },
    }


def _write_candidate_artifacts(
    *,
    candidate_entry: dict[str, Any],
    section: dict[str, Any],
    results_by_key: dict[str, dict[str, Any]],
    artifacts_root: Path,
) -> None:
    experiment_root = _candidate_experiment_root(
        artifacts_root=artifacts_root,
        experiment_id=str(candidate_entry.get("experiment_id") or ""),
    )
    write_json(experiment_root / "overlay_ablation.json", section)
    _write_markdown(
        output_path=experiment_root / "overlay_ablation.md",
        title="Alpha Ontology H10D Overlay Ablation",
        section=section,
    )
    candidate_label = str(candidate_entry.get("label") or "").strip()
    period_frames = []
    for variant in overlay_ablation_variant_entries(CONTRACT):
        variant_label = str(variant.get("label") or "").strip()
        key = f"{candidate_label}__{variant_label}"
        periods = results_by_key[key]["periods"].copy()
        periods.rename(columns={"net_period_return": variant_label}, inplace=True)
        period_frames.append(periods[["timestamp_ms", "timestamp_utc", variant_label]])
    aligned = period_frames[0]
    for frame in period_frames[1:]:
        aligned = aligned.merge(frame, on=["timestamp_ms", "timestamp_utc"], how="outer")
    aligned.sort_values("timestamp_ms").to_csv(experiment_root / "overlay_ablation_aligned_period_returns.csv", index=False)
    pd.DataFrame.from_records(section["pairwise_results"]).to_csv(
        experiment_root / "overlay_ablation_pairwise_comparisons.csv",
        index=False,
    )
    for file_name in ("validation_report.json", "alpha_card.json"):
        path = experiment_root / file_name
        payload = dict(read_json(path))
        payload["overlay_ablation"] = section
        payload["updated_at_utc"] = utc_now()
        write_json(path, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine overlay ablation partial runs.")
    parser.add_argument("--artifacts-root", type=Path, default=ROOT / "artifacts" / "quant_research")
    parser.add_argument("--output-date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--bootstrap-iterations", type=int, default=BOOTSTRAP_ITERATIONS)
    parser.add_argument("--no-backfill", action="store_true")
    args = parser.parse_args(argv)

    candidate_entries = overlay_ablation_candidate_entries(CONTRACT)
    variant_entries = overlay_ablation_variant_entries(CONTRACT)
    ordered_keys = [
        f"{candidate.get('label')}__{variant.get('label')}"
        for candidate in candidate_entries
        for variant in variant_entries
    ]
    results_by_key = {
        key: _load_partial(artifacts_root=args.artifacts_root, output_date=args.output_date, key=key)
        for key in ordered_keys
    }
    pairwise_results: list[dict[str, Any]] = []
    for pair_index, (key_a, key_b) in enumerate(combinations(ordered_keys, 2)):
        result_a = results_by_key[key_a]
        result_b = results_by_key[key_b]
        pairwise_results.append(
            pairwise_comparison(
                label_a=key_a,
                label_b=key_b,
                periods_a=result_a["periods"],
                periods_b=result_b["periods"],
                periods_per_year=int(result_a["periods_per_year"]),
                iterations=int(args.bootstrap_iterations),
                seed=BOOTSTRAP_SEED + pair_index,
            )
        )

    output_root = args.artifacts_root / "factor_reports" / f"{args.output_date}-alpha_ontology_h10d_overlay_ablation"
    output_root.mkdir(parents=True, exist_ok=True)
    aligned_period_returns_path = output_root / "aligned_period_returns.csv"
    pairwise_csv_path = output_root / "pairwise_comparisons.csv"
    summary_json_path = output_root / "summary.json"
    summary_md_path = output_root / "summary.md"

    all_period_frames = []
    for key in ordered_keys:
        periods = results_by_key[key]["periods"].copy()
        periods.rename(columns={"net_period_return": key}, inplace=True)
        all_period_frames.append(periods[["timestamp_ms", "timestamp_utc", key]])
    aligned = all_period_frames[0]
    for frame in all_period_frames[1:]:
        aligned = aligned.merge(frame, on=["timestamp_ms", "timestamp_utc"], how="outer")
    aligned.sort_values("timestamp_ms").to_csv(aligned_period_returns_path, index=False)
    pd.DataFrame.from_records(pairwise_results).to_csv(pairwise_csv_path, index=False)

    candidate_sections = []
    for candidate in candidate_entries:
        experiment_root = _candidate_experiment_root(
            artifacts_root=args.artifacts_root,
            experiment_id=str(candidate.get("experiment_id") or ""),
        )
        candidate_sections.append(
            _candidate_section(
                candidate_entry=candidate,
                results_by_key=results_by_key,
                pairwise_results=pairwise_results,
                experiment_root=experiment_root,
            )
        )

    summary_payload = {
        "contract_version": str(CONTRACT.get("contract_version") or ""),
        "analysis_date": str(args.output_date),
        "status": "computed",
        "variant_summaries": [dict(results_by_key[key]["summary"]) for key in ordered_keys],
        "pairwise_results": pairwise_results,
        "candidate_sections": candidate_sections,
        "artifacts": {
            "aligned_period_returns_csv": portable_path(aligned_period_returns_path, repo_root=ROOT),
            "pairwise_comparisons_csv": portable_path(pairwise_csv_path, repo_root=ROOT),
            "summary_md": portable_path(summary_md_path, repo_root=ROOT),
        },
    }
    write_json(summary_json_path, summary_payload)
    _write_markdown(
        output_path=summary_md_path,
        title="Alpha Ontology H10D Overlay Ablation",
        section=summary_payload,
    )
    if not args.no_backfill:
        for candidate, section in zip(candidate_entries, candidate_sections, strict=True):
            _write_candidate_artifacts(
                candidate_entry=candidate,
                section=section,
                results_by_key=results_by_key,
                artifacts_root=args.artifacts_root,
            )
    print(json.dumps(summary_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
