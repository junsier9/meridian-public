# Frozen Benchmark v35 Owner-Gated Plan

`Status: owner-gated implementation plan`
`Scope: src/enhengclaw/quant_research/hypothesis_batch.py frozen benchmark metadata`
`Date: 2026-05-15`

## Decision

Implement the first step as an **identity-only static contract**.

Do not add an archive-aware resolver bridge yet. Do not restore
`cross_sectional_hypothesis_batch_manifest_v35.json` to package root.

## Evidence Baseline

- `hypothesis_batch.py` still defines:
  - `FROZEN_BENCHMARK_MANIFEST_PATH =
    Path(__file__).with_name("cross_sectional_hypothesis_batch_manifest_v35.json")`
  - `FROZEN_BENCHMARK_SOURCE = "hypothesis_batch_manifest_v35"`
  - `FROZEN_BENCHMARK_CANDIDATE_IDS = ("xs_pair_spread_book_v8_h5d",)`
- The root package path
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v35.json`
  is currently absent.
- The checked-in v35 payload exists under
  `src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/`.
- The archive README says Phase 0 manifests v1-v82 are historical records and
  are not loaded by runtime.
- Current runtime loading uses `HYPOTHESIS_BATCH_MANIFEST_PATH`, which points to
  `cross_sectional_hypothesis_batch_manifest_v97.json`.
- No direct loader/test reference to `FROZEN_BENCHMARK_*` was found beyond the
  constants and governance documentation during the dry-run.

## Option A: Identity-Only Static Contract

Freeze only the frozen benchmark identity:

- `FROZEN_BENCHMARK_SOURCE == "hypothesis_batch_manifest_v35"`
- `FROZEN_BENCHMARK_CANDIDATE_IDS == ("xs_pair_spread_book_v8_h5d",)`

Allowed implementation shape:

- add a small static test that parses `hypothesis_batch.py` without importing
  runtime-heavy modules;
- assert the source string and candidate tuple;
- optionally assert that the archived v35 payload still exists and contains the
  same candidate id;
- do not assert that the root v35 path exists.

Risk: low.

Why this is preferred:

- it protects the benchmark label from silent rename/drift;
- it does not reactivate archived Phase 0 material;
- it respects the manifest archive contract;
- it keeps path semantics owner-gated.

## Option B: Archive-Aware Resolver Bridge

Introduce a helper that resolves the frozen benchmark manifest by checking the
root path first and then the archive path.

Allowed only after owner approval.

Required proof before implementation:

- a real caller needs to read the frozen benchmark payload at runtime or in a
  static contract;
- the bridge is named explicitly as a historical benchmark resolver, not as a
  general manifest loader;
- the helper cannot affect `HYPOTHESIS_BATCH_MANIFEST_PATH`;
- tests prove v97 runtime loading is unchanged;
- docs state that archive fallback is audit-only, not reactivation.

Risk: medium.

Why this is deferred:

- it turns an otherwise dormant metadata pointer into a supported path surface;
- it could blur the archive README boundary that v1-v82 are not runtime-loaded;
- it may invite future code to depend on historical manifests without an
  explicit reactivation procedure.

## Explicit Non-Goals

- Do not copy or move v35 from `manifests_archive/phase0_v1_v82/` to package
  root.
- Do not update `HYPOTHESIS_BATCH_MANIFEST_PATH`.
- Do not reactivate v35.
- Do not assert v35 promotion quality or current-line strategy status.
- Do not freeze pair-construction formulas, lab dispatch, or archived manifest
  behavior in this step.

## Minimal Verification

For the identity-only contract:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

If an archive-aware resolver is later approved:

```powershell
python -m pytest tests\test_static_contracts.py tests\test_quant_hypothesis_batch.py -q
git diff --check
```

## Owner Gate

Default approved path:

1. Add the identity-only static contract.
2. Keep the root v35 path absence documented.
3. Keep resolver bridge deferred.

Escalate to owner review before any change that makes archived v35 loadable
through a public helper or restores the file to package root.
