from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.promotion import h10d_promotion_evidence_blockers


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed unless an h10d alpha card has required promotion evidence sidecars."
    )
    parser.add_argument("--alpha-card", type=Path, required=True)
    parser.add_argument(
        "--allow-non-applicable",
        action="store_true",
        help="Return success for non-h10d / non-applicable alpha cards instead of failing.",
    )
    args = parser.parse_args(argv)

    alpha_card_path = args.alpha_card
    if not alpha_card_path.exists():
        print(
            json.dumps(
                {
                    "passed": False,
                    "alpha_card_path": str(alpha_card_path),
                    "blockers": ["alpha_card_path_missing"],
                },
                indent=2,
            )
        )
        return 2

    alpha_card = _read_json(alpha_card_path)
    blockers = h10d_promotion_evidence_blockers(
        alpha_card=alpha_card,
        require_applicable=not bool(args.allow_non_applicable),
    )
    payload = {
        "passed": not blockers,
        "alpha_card_path": str(alpha_card_path),
        "experiment_id": str(alpha_card.get("experiment_id") or ""),
        "strategy_id": str(alpha_card.get("strategy_id") or ""),
        "required_fields": {
            "fixed_set_comparison.status": "computed",
            "fixed_set_comparison.promotion_gate.passed": True,
            "overlay_ablation.status": "computed",
            "blocker_attribution_gate.status": "completed_symbol_bucket_strict_gate",
            "blocker_attribution_gate.passed": True,
        },
        "blockers": blockers,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
