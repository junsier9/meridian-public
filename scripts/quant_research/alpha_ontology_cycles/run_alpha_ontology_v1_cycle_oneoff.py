"""run_alpha_ontology_v1_cycle_oneoff.py — one-off cycle invocation for the
xs_alpha_ontology_v1_h5d candidate.

The hypothesis_batch module is hardcoded to a single active manifest (v97 =
xs_minimal_v12 at the time of writing). To gather Week 2 exit criterion #1
evidence (cycle fast_reject_report + validation_report) on the alpha-ontology
manifest without altering the active strategy, this script monkey-patches the
relevant module constants at runtime, runs the cycle, and prints the summary.

The patches are NOT persisted to disk; the active strategy on next invocation
of run_quant_hypothesis_batch_cycle remains v97.
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
from enhengclaw.quant_research.lab import (  # noqa: E402
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
)


DEFAULT_MANIFEST = (
    SRC / "enhengclaw" / "quant_research" /
    "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_lsk3.json"
)
DEFAULT_CONTRACT_TAG = "alpha_ontology_v1_lsk3"


def _patch_hypothesis_batch_for_variant(
    *,
    manifest_path: Path,
    contract_tag: str,
    base_mechanism_id: str,
    candidate_id: str,
) -> dict:
    """Override hypothesis_batch module constants to accept a non-default manifest.

    Patches are not persisted; subsequent invocations of run_quant_hypothesis_batch_cycle
    after this process exits revert to the active strategy (v97 = xs_minimal_v12).
    """
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

    return original


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="One-off cycle for an alpha-ontology variant (Week 2 / W2-A iteration evidence)"
    )
    parser.add_argument("--as-of", required=True, help="Sample date in YYYY-MM-DD format.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to the cross_sectional_hypothesis_batch_manifest_*.json variant to run.",
    )
    parser.add_argument(
        "--contract-tag",
        default=None,
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

    print(f"[patch] overriding hypothesis_batch constants for {contract_tag}")
    _patch_hypothesis_batch_for_variant(
        manifest_path=manifest_path,
        contract_tag=contract_tag,
        base_mechanism_id=base_mechanism_id,
        candidate_id=candidate_id,
    )
    print(f"[patch] HYPOTHESIS_BATCH_MANIFEST_PATH = {hb.HYPOTHESIS_BATCH_MANIFEST_PATH}")
    print(f"[patch] EXPECTED_CANDIDATE_IDS = {hb.EXPECTED_CANDIDATE_IDS}")

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
