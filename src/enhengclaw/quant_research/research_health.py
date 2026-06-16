from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from .contracts import portable_path, utc_now, write_json
from .derivatives_quality import aggregate_strategy_derivatives_quality
from .experiment_status import NON_DECISIVE_EXPERIMENT_STATUSES
from .promotion import sharpe_anomaly_details


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_QUALITY_SUMMARY_CONTRACT_VERSION = "quant_research_quality_summary.v1"


def build_research_quality_summary(
    *,
    experiments: list[dict[str, Any]],
    artifacts_root: Path,
    scope: str,
    as_of: str | None = None,
    week_of: str | None = None,
    canonical_universe_count: int | None = None,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    cross_sectional_medians: list[float] = []
    walk_forward_window_counts: list[int] = []
    anomaly_candidates: list[dict[str, Any]] = []
    thesis_lane_counts: dict[str, int] = {}
    thesis_family_counts: dict[str, int] = {}
    thesis_funnel = {
        "hypothesis_factor": {"count": 0, "passed": 0},
        "hypothesis_portfolio": {"count": 0, "passed": 0},
        "hypothesis_model": {"count": 0, "passed": 0},
    }
    raw_pass_count = 0
    credible_research_evidence_pass_count = 0
    decisive_experiment_count = 0
    unverified_or_failed_falsification_candidates: list[dict[str, Any]] = []

    for experiment in experiments:
        if not isinstance(experiment, dict):
            continue
        alpha_card = dict(experiment.get("alpha_card") or {})
        experiment_id = str(experiment.get("experiment_id") or alpha_card.get("experiment_id") or "").strip()
        experiment_status = str(experiment.get("experiment_status") or alpha_card.get("experiment_status") or "fail").strip()
        status_counts[experiment_status] = status_counts.get(experiment_status, 0) + 1
        if experiment_status not in NON_DECISIVE_EXPERIMENT_STATUSES:
            decisive_experiment_count += 1
        if experiment_status == "pass":
            raw_pass_count += 1
        validation = str(experiment.get("validation") or alpha_card.get("validation") or "").strip()
        falsification_status = str(
            experiment.get("falsification_status")
            or alpha_card.get("falsification_status")
            or "not_required"
        ).strip()
        credible_research_evidence = bool(
            experiment.get("credible_research_evidence", alpha_card.get("credible_research_evidence", False))
        )
        if credible_research_evidence:
            credible_research_evidence_pass_count += 1
        if falsification_status == "failed" or not credible_research_evidence:
            unverified_or_failed_falsification_candidates.append(
                {
                    "experiment_id": experiment_id,
                    "strategy_id": str(experiment.get("strategy_id") or alpha_card.get("strategy_id") or "").strip(),
                    "experiment_status": experiment_status,
                    "validation": validation,
                    "falsification_status": falsification_status,
                    "publication_status": str(
                        experiment.get("publication_status") or alpha_card.get("publication_status") or ""
                    ).strip(),
                }
            )
        walk_forward = dict(experiment.get("walk_forward") or alpha_card.get("walk_forward") or {})
        research_lane = str(experiment.get("research_lane") or alpha_card.get("research_lane") or "").strip()
        thesis_family = str(experiment.get("thesis_family") or alpha_card.get("thesis_family") or "").strip()
        if research_lane:
            thesis_lane_counts[research_lane] = thesis_lane_counts.get(research_lane, 0) + 1
        if thesis_family:
            thesis_family_counts[thesis_family] = thesis_family_counts.get(thesis_family, 0) + 1
        if research_lane in thesis_funnel:
            thesis_funnel[research_lane]["count"] += 1
            if experiment_status == "pass":
                thesis_funnel[research_lane]["passed"] += 1
        if str(experiment.get("shape") or alpha_card.get("shape") or "") == "cross_sectional":
            cross_sectional_medians.append(float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0))
        walk_forward_window_counts.append(int(walk_forward.get("window_count", 0) or 0))
        anomaly = sharpe_anomaly_details(
            validation_metrics=dict(experiment.get("validation_metrics") or alpha_card.get("validation_metrics") or {}),
            test_metrics=dict(experiment.get("test_metrics") or alpha_card.get("test_metrics") or {}),
            walk_forward=walk_forward,
            threshold=5.0,
        )
        if anomaly is None:
            continue
        anomaly_candidates.append(
            {
                "experiment_id": experiment_id,
                "strategy_id": str(experiment.get("strategy_id") or alpha_card.get("strategy_id") or "").strip(),
                "shape": str(experiment.get("shape") or alpha_card.get("shape") or "").strip(),
                "experiment_status": experiment_status,
                "validation": validation,
                "publication_status": str(experiment.get("publication_status") or alpha_card.get("publication_status") or "").strip(),
                "falsification_status": falsification_status,
                "credible_research_evidence": credible_research_evidence,
                "metric": anomaly["metric"],
                "value": anomaly["value"],
            }
        )

    experiment_count = sum(status_counts.values())
    return {
        "contract_version": RESEARCH_QUALITY_SUMMARY_CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "scope": scope,
        "as_of": as_of,
        "week_of": week_of,
        "canonical_universe_count": canonical_universe_count,
        "experiment_count": experiment_count,
        "decisive_experiment_count": decisive_experiment_count,
        "experiment_status_counts": status_counts,
        "raw_pass_rate": (raw_pass_count / decisive_experiment_count) if decisive_experiment_count else 0.0,
        "credible_research_evidence_pass_rate": (
            credible_research_evidence_pass_count / decisive_experiment_count
        ) if decisive_experiment_count else 0.0,
        "cross_sectional_median_oos_sharpe": _distribution_summary(cross_sectional_medians),
        "walk_forward_window_count": _distribution_summary([float(item) for item in walk_forward_window_counts]),
        "thesis_lane_counts": thesis_lane_counts,
        "thesis_family_counts": thesis_family_counts,
        "thesis_funnel": {
            key: {
                "count": value["count"],
                "pass_rate": (value["passed"] / value["count"]) if value["count"] else 0.0,
            }
            for key, value in thesis_funnel.items()
        },
        "derivatives_strategy_quality_summary": aggregate_strategy_derivatives_quality(experiments),
        "unverified_or_failed_falsification_candidates": sorted(
            unverified_or_failed_falsification_candidates,
            key=lambda item: (str(item["experiment_status"]), str(item["experiment_id"])),
        ),
        "sharpe_anomaly_candidates": sorted(
            anomaly_candidates,
            key=lambda item: (-float(item["value"]), str(item["experiment_id"])),
        ),
    }


def write_research_quality_summary(
    *,
    path: Path,
    experiments: list[dict[str, Any]],
    artifacts_root: Path,
    scope: str,
    as_of: str | None = None,
    week_of: str | None = None,
    canonical_universe_count: int | None = None,
) -> dict[str, Any]:
    payload = build_research_quality_summary(
        experiments=experiments,
        artifacts_root=artifacts_root,
        scope=scope,
        as_of=as_of,
        week_of=week_of,
        canonical_universe_count=canonical_universe_count,
    )
    write_json(path, payload)
    payload["research_quality_summary_path"] = portable_path(path, repo_root=ROOT)
    return payload


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "median": None,
            "max": None,
            "positive_fraction": None,
        }
    return {
        "count": len(values),
        "min": min(values),
        "median": median(values),
        "max": max(values),
        "positive_fraction": sum(1 for item in values if item > 0.0) / len(values),
    }
