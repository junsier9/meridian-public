from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify._openclaw_live_readiness_bundle import build_parser, run_live_readiness_bundle


LANE_IDS = (
    "risk_governance_agent",
    "validation_agent",
)


def _review_override_payload() -> dict[str, object]:
    return {
        "risk_governance_review": {
            "review_name": "risk_governance_review",
            "gate_status": "pass",
            "reasons": ["forced pass for review-gated OpenClaw live readiness success-path proof"],
        },
        "validation_review": {
            "review_name": "validation_review",
            "gate_status": "pass",
            "reasons": ["forced pass for review-gated OpenClaw live readiness success-path proof"],
        },
    }


def _build_review_gated_env() -> dict[str, str]:
    env = dict(os.environ)
    env["ENHENGCLAW_TEST_REVIEW_OVERRIDE"] = json.dumps(_review_override_payload(), sort_keys=True)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(description="Run the archetype-level review-gated OpenClaw live readiness bundle.")
    args = parser.parse_args(argv)
    result = run_live_readiness_bundle(
        bundle_id="openclaw_review_gated_live_readiness",
        bundle_label="review-gated live readiness",
        lane_ids=LANE_IDS,
        execution_permit=args.execution_permit,
        trust_root_dir=args.trust_root_dir,
        retain_root=args.retain_root,
        base_env=_build_review_gated_env(),
    )
    print(f"[openclaw-review-gated-live] retain_root={result['retain_root']}")
    if result["status"] != "success":
        print(f"[openclaw-review-gated-live] failing_lane={result['failing_lane']}")
        print(f"[openclaw-review-gated-live] failing_stage={result['failing_stage']}")
        print("[openclaw-review-gated-live] FINAL CONCLUSION=FAILED")
        return int(result["exit_code"])
    print("[openclaw-review-gated-live] FINAL CONCLUSION=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
