from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.refactor_freeze.generation import generate_snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate baseline freeze snapshots.")
    parser.add_argument("--phase", required=True, help="Phase identifier, for example: phase_01")
    parser.add_argument(
        "--snapshot-type",
        action="append",
        dest="snapshot_types",
        help="Optional snapshot type filter. Repeat the flag to include multiple types.",
    )
    parser.add_argument(
        "--freeze-root",
        type=Path,
        default=None,
        help="Optional override for the refactor freeze root directory.",
    )
    args = parser.parse_args()

    result = generate_snapshots(
        kind="baselines",
        phase=args.phase,
        snapshot_types=None if not args.snapshot_types else set(args.snapshot_types),
        freeze_root=args.freeze_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
