"""run_alpha_ontology_horizon_cycle_oneoff.py — horizon-flexible variant of
run_alpha_ontology_v1_cycle_oneoff.py.

Adds `--target-horizon-bars` so a single runner can drive cycles at h1d / h5d
/ h10d / etc. Monkey-patches `HYPOTHESIS_BATCH_TARGET_HORIZONS` and
`EXPECTED_HORIZON_SPECS` in addition to the manifest constants.

SP-C Phase 2 motivation: the multi-horizon audit
(`compute_multi_horizon_factor_audit.py`) found ALL score-integrated factors
peak at h10d (not h5d). This runner enables h10d cycles for v_alpha_v5 /
v6 / v7 / v8 to verify the audit's predicted walk-forward improvement.

Usage:
    python scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py \\
        --as-of 2026-04-29 \\
        --manifest src/.../cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2_h10d.json \\
        --target-horizon-bars 10
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import enhengclaw.quant_research.hypothesis_batch as hb  # noqa: E402
import enhengclaw.quant_research.validation_contract as vc  # noqa: E402
from enhengclaw.quant_research.lab import (  # noqa: E402
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
)


# SP-C Phase 3: per-horizon validation_contract paths. h10d uses a sqrt(2)-
# scaled regime+walk-forward sharpe threshold (sharpe under random-walk-IID
# scales with sqrt(N) for N-period returns). h5d uses the canonical v10
# contract. Other horizons fall back to v10 (will need their own scaled
# contract if/when other horizon strategies productionize).
_HORIZON_CONTRACT_PATHS = {
    10: ROOT / "config" / "quant_research" / "validation_contract_h10d.json",
}


def _patch_hypothesis_batch_for_variant(
    *,
    manifest_path: Path,
    contract_tag: str,
    base_mechanism_id: str,
    candidate_id: str,
    target_horizon_bars: int,
) -> dict:
    """Override hypothesis_batch module constants for both manifest + horizon."""
    horizon_id = f"h{target_horizon_bars}d"
    original = {
        "HYPOTHESIS_BATCH_MANIFEST_PATH": hb.HYPOTHESIS_BATCH_MANIFEST_PATH,
        "HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION": hb.HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION,
        "FAST_REJECT_REPORT_CONTRACT_VERSION": hb.FAST_REJECT_REPORT_CONTRACT_VERSION,
        "STRICT_CANDIDATE_LIST_CONTRACT_VERSION": hb.STRICT_CANDIDATE_LIST_CONTRACT_VERSION,
        "STRICT_RESULT_CONTRACT_VERSION": hb.STRICT_RESULT_CONTRACT_VERSION,
        "BATCH_SUMMARY_CONTRACT_VERSION": hb.BATCH_SUMMARY_CONTRACT_VERSION,
        "HYPOTHESIS_BATCH_SOURCE": hb.HYPOTHESIS_BATCH_SOURCE,
        "EXPECTED_BASE_MECHANISM_IDS": hb.EXPECTED_BASE_MECHANISM_IDS,
        "EXPECTED_CANDIDATE_IDS": hb.EXPECTED_CANDIDATE_IDS,
        "EXPECTED_HORIZON_SPECS": hb.EXPECTED_HORIZON_SPECS,
        "EXPECTED_HORIZON_MAP": hb.EXPECTED_HORIZON_MAP,
        "HYPOTHESIS_BATCH_TARGET_HORIZONS": hb.HYPOTHESIS_BATCH_TARGET_HORIZONS,
    }
    hb.HYPOTHESIS_BATCH_MANIFEST_PATH = manifest_path
    hb.HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION = (
        f"quant_cross_sectional_hypothesis_batch_manifest.{contract_tag}"
    )
    hb.FAST_REJECT_REPORT_CONTRACT_VERSION = (
        f"quant_cross_sectional_fast_reject_report.{contract_tag}"
    )
    hb.STRICT_CANDIDATE_LIST_CONTRACT_VERSION = (
        f"quant_cross_sectional_strict_candidate_list.{contract_tag}"
    )
    hb.STRICT_RESULT_CONTRACT_VERSION = (
        f"quant_cross_sectional_strict_result.{contract_tag}"
    )
    hb.BATCH_SUMMARY_CONTRACT_VERSION = (
        f"quant_cross_sectional_hypothesis_batch_cycle.{contract_tag}"
    )
    hb.HYPOTHESIS_BATCH_SOURCE = f"hypothesis_batch_manifest_{contract_tag}"
    hb.EXPECTED_BASE_MECHANISM_IDS = (base_mechanism_id,)
    hb.EXPECTED_CANDIDATE_IDS = (candidate_id,)
    hb.EXPECTED_HORIZON_SPECS = ((horizon_id, target_horizon_bars),)
    hb.EXPECTED_HORIZON_MAP = dict(hb.EXPECTED_HORIZON_SPECS)
    hb.HYPOTHESIS_BATCH_TARGET_HORIZONS = (target_horizon_bars,)
    # Per-horizon validation contract — load the sqrt-scaled h10d contract
    # when target_horizon_bars == 10 etc.
    horizon_contract_path = _HORIZON_CONTRACT_PATHS.get(target_horizon_bars)
    if horizon_contract_path is not None and horizon_contract_path.exists():
        original["VALIDATION_CONTRACT_PATH"] = vc.VALIDATION_CONTRACT_PATH
        original["VALIDATION_CONTRACT_VERSION"] = vc.VALIDATION_CONTRACT_VERSION
        vc.VALIDATION_CONTRACT_PATH = horizon_contract_path
        # Read contract version from the file to keep audit lineage clean
        import json as _json
        _payload = _json.loads(horizon_contract_path.read_text(encoding="utf-8"))
        vc.VALIDATION_CONTRACT_VERSION = str(_payload.get("contract_version") or vc.VALIDATION_CONTRACT_VERSION)
        print(f"[patch] VALIDATION_CONTRACT_PATH = {vc.VALIDATION_CONTRACT_PATH}")
        print(f"[patch] VALIDATION_CONTRACT_VERSION = {vc.VALIDATION_CONTRACT_VERSION}")
    return original


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="One-off cycle for an alpha-ontology variant at custom horizon."
    )
    parser.add_argument("--as-of", required=True, help="Sample date in YYYY-MM-DD format.")
    parser.add_argument(
        "--manifest", type=Path, required=True,
        help="Path to the cross_sectional_hypothesis_batch_manifest_*.json variant to run.",
    )
    parser.add_argument(
        "--target-horizon-bars", type=int, default=5,
        help="Forward-return horizon in bars (e.g. 5 = h5d, 10 = h10d).",
    )
    parser.add_argument(
        "--contract-tag", default=None,
        help="Contract version suffix; auto-derived from the manifest's contract_version if omitted.",
    )
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument("--compiler-backend", default="deterministic")
    parser.add_argument("--no-auto-api-gap-backfill", action="store_true")
    args = parser.parse_args(argv)

    manifest_path = args.manifest.resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract_version = str(manifest_payload.get("contract_version") or "")
    contract_tag = args.contract_tag or contract_version.rsplit(".", 1)[-1]
    if not contract_tag:
        raise ValueError(f"could not infer contract tag from {contract_version!r}")

    entries = manifest_payload.get("entries") or []
    if not entries:
        raise ValueError(f"manifest has no entries: {manifest_path}")
    entry = entries[0]
    base_mechanism_id = str(entry["base_mechanism_id"])
    candidate_id = str(entry["candidate_id"])
    declared_horizon_bars = int(entry.get("target_horizon_bars") or 0)
    declared_horizon_id = str(entry.get("horizon_id") or "")
    expected_horizon_id = f"h{args.target_horizon_bars}d"

    if declared_horizon_bars != args.target_horizon_bars:
        raise ValueError(
            f"manifest entry target_horizon_bars={declared_horizon_bars} does not match "
            f"--target-horizon-bars={args.target_horizon_bars}"
        )
    if declared_horizon_id != expected_horizon_id:
        raise ValueError(
            f"manifest entry horizon_id={declared_horizon_id!r} does not match "
            f"expected {expected_horizon_id!r}"
        )

    print(f"[patch] overriding hypothesis_batch constants for {contract_tag} at {expected_horizon_id}")
    _patch_hypothesis_batch_for_variant(
        manifest_path=manifest_path,
        contract_tag=contract_tag,
        base_mechanism_id=base_mechanism_id,
        candidate_id=candidate_id,
        target_horizon_bars=args.target_horizon_bars,
    )
    print(f"[patch] HYPOTHESIS_BATCH_MANIFEST_PATH = {hb.HYPOTHESIS_BATCH_MANIFEST_PATH}")
    print(f"[patch] EXPECTED_CANDIDATE_IDS = {hb.EXPECTED_CANDIDATE_IDS}")
    print(f"[patch] EXPECTED_HORIZON_SPECS = {hb.EXPECTED_HORIZON_SPECS}")
    print(f"[patch] HYPOTHESIS_BATCH_TARGET_HORIZONS = {hb.HYPOTHESIS_BATCH_TARGET_HORIZONS}")

    try:
        summary = hb.run_quant_hypothesis_batch_cycle(
            as_of=args.as_of,
            compiler_backend=args.compiler_backend,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            workbench_root=args.workbench_root,
            ohlcv_external_root=args.ohlcv_external_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            derivatives_external_root=args.derivatives_external_root,
            auto_api_gap_backfill=not args.no_auto_api_gap_backfill,
        )
    except Exception:
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
