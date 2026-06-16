"""Generate a versioned cross-sectional feature panel without invoking the
hypothesis-batch fast_reject / strict validation cycle.

Used to materialize a panel containing newly-added factor candidates (e.g.
v92 B-batch) so phase_1c_factor_correlation_analysis.py can score them
before they are promoted into a hand-authored v92 hypothesis-batch manifest.

Reuses the same dataset assembly helpers as run_quant_hypothesis_batch_cycle
(load_quant_universe_snapshot -> require_derivatives_sync_summary ->
build_quant_datasets -> build_quant_feature_sets) but bypasses the manifest
contract check at hypothesis_batch.py:701, which would otherwise refuse to
load until cross_sectional_hypothesis_batch_manifest_v<N>.json exists.

Example:
    python scripts/quant_research/generate_versioned_panel.py \\
        --as-of 2026-04-26 --feature-set-version v92

Writes:
    artifacts/quant_research/features/<as_of>-cross-sectional-daily-1d-h5d-features-<version>/features.csv.gz
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import required_source_commit_sha
from enhengclaw.quant_research.contracts import QuantUniverseCandidate
from enhengclaw.quant_research.data_readiness import resolve_default_spot_ohlcv_external_root
from enhengclaw.quant_research.features import DEFAULT_LABEL_CONTRACT_ID
from enhengclaw.quant_research.hypothesis_batch import HYPOTHESIS_BATCH_TARGET_HORIZONS
from enhengclaw.quant_research.lab import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    build_quant_datasets,
    build_quant_feature_sets,
    load_quant_universe_snapshot,
    require_derivatives_sync_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Panel-only feature generator (skips fast_reject/strict cycles).",
    )
    parser.add_argument(
        "--as-of", required=True,
        help="Sample date in YYYY-MM-DD (e.g. 2026-04-26 to align with v90/v91 baseline).",
    )
    parser.add_argument(
        "--feature-set-version", required=True,
        help="Output panel version label (e.g. v92).",
    )
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts_root = Path(args.artifacts_root).expanduser().resolve()
    spot_root = resolve_default_spot_ohlcv_external_root(
        spot_ohlcv_external_root=args.spot_ohlcv_external_root,
    )
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)

    universe_snapshot = load_quant_universe_snapshot(
        as_of=args.as_of, artifacts_root=artifacts_root,
    )
    universe_candidates = tuple(
        QuantUniverseCandidate.from_payload(item)
        for item in list(universe_snapshot.get("candidates", []))
        if isinstance(item, dict)
    )
    derivatives_sync, _ = require_derivatives_sync_summary(
        as_of=args.as_of,
        derivatives_external_root=args.derivatives_external_root,
    )
    datasets = build_quant_datasets(
        as_of=args.as_of,
        artifacts_root=artifacts_root,
        universe_snapshot=universe_snapshot,
        universe_candidates=universe_candidates,
        ohlcv_external_root=args.ohlcv_external_root,
        spot_ohlcv_external_root=spot_root,
        derivatives_external_root=args.derivatives_external_root,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
    )
    feature_sets = build_quant_feature_sets(
        artifacts_root=artifacts_root,
        datasets=datasets,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
        cross_sectional_daily_target_horizons=HYPOTHESIS_BATCH_TARGET_HORIZONS,
        cross_sectional_daily_label_contract_ids=(DEFAULT_LABEL_CONTRACT_ID,),
        feature_set_version=args.feature_set_version,
    )

    print(f"=== Generated {len(feature_sets)} feature set(s) at version={args.feature_set_version}:")
    for fs in feature_sets:
        fs_id = str(fs.get("feature_set_id", "?"))
        path = artifacts_root / "features" / fs_id / "features.csv.gz"
        size = path.stat().st_size if path.exists() else 0
        print(f"  {fs_id}  ({size:,} bytes at {path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
