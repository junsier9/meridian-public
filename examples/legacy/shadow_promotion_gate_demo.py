from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.shadow_promotion import ShadowPromotionCorpus, ShadowPromotionRunner


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    corpus_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "fixtures" / "shadow_promotion_corpus"
    report = ShadowPromotionRunner(ShadowPromotionCorpus(corpus_root)).compare_all()
    payload = {
        "corpus_root": report.corpus_root,
        "scenario_count": report.scenario_count,
        "promotion_metrics": asdict(report.metrics),
        "classification": asdict(report.classification),
        "sensitivity": [asdict(item) for item in report.sensitivity],
        "recommendation": asdict(report.recommendation),
        "scenario_summaries": [
            {
                "category": comparison.category,
                "scenario": comparison.scenario,
                "subject": comparison.subject,
                "scope": comparison.scope,
                "baseline": asdict(comparison.baseline),
                "official_shadow_decision_unchanged": comparison.official_shadow_decision_unchanged,
                "onchain_drift_status": comparison.onchain_drift_status,
                "onchain_drift_summary": comparison.onchain_drift_summary,
                "shadow_preview": None if comparison.shadow_preview is None else asdict(comparison.shadow_preview),
                "candidate_status": comparison.candidate_status,
                "candidate_error": comparison.candidate_error,
                "candidate_if_enabled": None if comparison.candidate_if_enabled is None else asdict(comparison.candidate_if_enabled),
                "diff": None if comparison.diff is None else asdict(comparison.diff),
            }
            for comparison in report.comparisons
        ],
    }
    print(json.dumps(payload, indent=2, default=_json_default))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="shadow-promotion-gate-demo"):
        main()

