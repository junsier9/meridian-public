# Phase 0 archive: cross_sectional_hypothesis_batch_manifest v1 through v82

This directory contains the historical record of the Phase 0 search that produced `xs_minimal_v3_h5d` (v83) as the Phase 0 baseline. **None of these archived manifests are loaded by the runtime.** They are kept here for audit and roadmap traceability per [docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md](../../../../../docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md).

## What lives here

- 80 manifest JSON files: the unversioned `cross_sectional_hypothesis_batch_manifest.json` plus `_v2.json` through `_v82.json` (with gaps at v16 and v79; those version numbers were skipped during research, never assigned).
- Each file is the frozen `quant_cross_sectional_hypothesis_batch_manifest` payload that drove one or more historical hypothesis batch cycles. Each carries its own `spec_hash` and `thesis_profile` documenting the candidate it represented.

## What is NOT here

- **v83**: the Phase 0 documented baseline/static historical anchor, kept at the parent directory `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v83.json` for path-stable roadmap, catalog, and static-contract references. It is not the current `hypothesis_batch.py` runtime default; as of the 2026-05-14 S2 manifest lifecycle catalog, `hypothesis_batch.py:HYPOTHESIS_BATCH_MANIFEST_PATH` points at `cross_sectional_hypothesis_batch_manifest_v97.json`. Moving v83 would break historical links and governance catalog traceability, not current runtime loading.
- **v85, v86, v87, v88**: post-v83 candidates that were tried in 2026-04 and found to underperform v83. They remain at the parent directory as recent audit evidence; they are referenced by `config/quant_research/threshold_provenance.md` addenda. Once they are old enough to be considered "historical" rather than "recent disproved", they may be moved here under a `phase0_followup_v85_v88/` subdirectory.

## Why the search ended at v83

v1 through v82 progressively explored:
- factor selection (single-factor IC discovery, ablation tests)
- score function families (xs_relative_strength, xs_quality_strength, xs_dual_regime_filter, xs_pair_spread_book, xs_minimal)
- universe rules (liquid_perp_core_20, liquid_perp_core_30, liquid_perp_tier2_20)
- regime gating (xs_dual_regime_filter v1 through v9, v11)
- portfolio construction (default top-3, pair_construction quality_bucket_pairs)

The conclusion of this search, recorded in 2026-04 cycle artifacts and `threshold_provenance.md`, is that:
1. A simple 4-feature linear baseline (`xs_minimal_v3`, v83) outperforms all earlier hand-engineered combinations on rank IC and walk-forward stability (rank IC 0.20, walk-forward median sharpe +0.94).
2. v83 still does not pass strict validation; it sits at promotion state `shadow_only`.
3. The next path forward is structural upgrade (multi-timescale factors, risk-managed portfolio, alpha lifecycle, data extension) rather than further hand-tuned variations on the same factor set.

See [docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md](../../../../../docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md) for the multi-quarter plan.

## How to consult these archives

Typical reasons to read a manifest from this archive:
- **Reproducing a historical experiment**: pin the spec_hash and read the `thesis_profile.market_mechanism` and `factor_formula` fields.
- **Understanding why a previous candidate failed**: cross-reference with `artifacts/quant_research/hypothesis_batches/<as_of>/families/<candidate_id>/fast_reject_report.json` for the matching cycle date.
- **Verifying that a new candidate is not a duplicate** of a previously-rejected one: compare `spec_hash` and `thesis_profile.directional_claim`.

To re-activate any archived manifest temporarily:
1. Move the chosen `_vNN.json` back to the parent directory (next to `hypothesis_batch.py`).
2. Update `hypothesis_batch.py` constants:
   - `HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION`
   - `FAST_REJECT_REPORT_CONTRACT_VERSION`
   - `STRICT_CANDIDATE_LIST_CONTRACT_VERSION`
   - `STRICT_RESULT_CONTRACT_VERSION`
   - `BATCH_SUMMARY_CONTRACT_VERSION`
   - `HYPOTHESIS_BATCH_MANIFEST_PATH`
   - `HYPOTHESIS_BATCH_SOURCE`
   - `HYPOTHESIS_BATCH_FEATURE_SET_VERSION`
   - `EXPECTED_BASE_MECHANISM_IDS`
3. Run `python scripts/quant_research/run_quant_hypothesis_batch_cycle.py --as-of <YYYY-MM-DD>`.

After the experiment, restore the pre-experiment runtime default by reverting
these constants. As of 2026-05-14, that default is v97
(`cross_sectional_hypothesis_batch_manifest_v97.json`). v83 remains the Phase 0
documented baseline/static historical anchor, not the current runtime default.

## Do not modify

These files are immutable historical records. If you find an error in one, do not edit it — instead, write a correction note in `config/quant_research/threshold_provenance.md` referencing the file by name.
