from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.shadow_admission import ShadowAdmissionRunner


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    report = ShadowAdmissionRunner().compare_with_filter()
    payload = {
        "corpus_root": report.corpus_root,
        "before": {
            "metrics": asdict(report.before.metrics),
            "classification": asdict(report.before.classification),
            "recommendation": asdict(report.before.recommendation),
        },
        "after": {
            "metrics": asdict(report.after.metrics),
            "classification": asdict(report.after.classification),
            "recommendation": asdict(report.after.recommendation),
            "sensitivity": [asdict(item) for item in report.after.sensitivity],
        },
        "scenarios": [
            {
                "category": scenario.category,
                "scenario": scenario.scenario,
                "subject": scenario.subject,
                "scope": scenario.scope,
                "original_shadow_preview": None if scenario.original.shadow_preview is None else asdict(scenario.original.shadow_preview),
                "rejected_shadow_signals": [asdict(item) for item in scenario.admission.rejected_signals],
                "accepted_shadow_signal_ids": [signal.signal_id for signal in scenario.admission.accepted_signals],
                "rejection_reasons": scenario.admission.rejection_reasons,
                "filtered_runtime_result": {
                    "candidate_status": scenario.filtered.candidate_status,
                    "candidate_error": scenario.filtered.candidate_error,
                    "candidate_if_enabled": None if scenario.filtered.candidate_if_enabled is None else asdict(scenario.filtered.candidate_if_enabled),
                    "diff": None if scenario.filtered.diff is None else asdict(scenario.filtered.diff),
                },
            }
            for scenario in report.scenarios
        ],
    }
    print(json.dumps(payload, indent=2, default=_json_default))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="shadow-admission-filter-demo"):
        main()

