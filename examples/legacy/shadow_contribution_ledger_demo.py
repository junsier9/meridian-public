from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.shadow_contribution import ContributionLedger


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main() -> None:
    report = ContributionLedger().build()
    payload = {
        "provider_name": report.provider_name,
        "corpus_root": report.corpus_root,
        "summary": asdict(report.summary),
        "health": asdict(report.health),
        "entries": [asdict(entry) for entry in report.entries],
    }
    print(json.dumps(payload, indent=2, default=_json_default))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="shadow-contribution-ledger-demo"):
        main()

