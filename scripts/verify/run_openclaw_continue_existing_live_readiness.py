from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify._openclaw_live_readiness_bundle import build_parser, run_live_readiness_bundle


LANE_IDS = (
    "evidence_agent",
    "risk_signal_agent",
    "attention_allocator",
    "research_synthesizer",
    "research_lead",
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(description="Run the archetype-level continue_existing non-review OpenClaw live readiness bundle.")
    args = parser.parse_args(argv)
    result = run_live_readiness_bundle(
        bundle_id="openclaw_continue_existing_live_readiness",
        bundle_label="continue_existing non-review live readiness",
        lane_ids=LANE_IDS,
        execution_permit=args.execution_permit,
        trust_root_dir=args.trust_root_dir,
        retain_root=args.retain_root,
    )
    print(f"[openclaw-continue-existing-live] retain_root={result['retain_root']}")
    if result["status"] != "success":
        print(f"[openclaw-continue-existing-live] failing_lane={result['failing_lane']}")
        print(f"[openclaw-continue-existing-live] failing_stage={result['failing_stage']}")
        print("[openclaw-continue-existing-live] FINAL CONCLUSION=FAILED")
        return int(result["exit_code"])
    print("[openclaw-continue-existing-live] FINAL CONCLUSION=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
