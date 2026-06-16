# Frozen Benchmark v35 Owner Decision

`Status: owner decision`
`Scope: frozen benchmark v35 identity vs resolver bridge`
`Date: 2026-05-15`

## Decision

Stop at the identity-only static contract.

Do not open an archive-aware resolver bridge dry-run now.

## Rationale

The current protected surface is the frozen benchmark identity, not a runtime
manifest loader:

- `FROZEN_BENCHMARK_SOURCE` remains `hypothesis_batch_manifest_v35`;
- `FROZEN_BENCHMARK_CANDIDATE_IDS` remains `("xs_pair_spread_book_v8_h5d",)`;
- the checked-in v35 payload remains available in
  `src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/`;
- the package-root v35 path is absent and should remain non-contractual;
- current hypothesis-batch runtime loading uses v97, not v35;
- no current script, test, or loader requires `FROZEN_BENCHMARK_*` to resolve a
  readable root manifest path.

The implemented static contract is sufficient for the current risk:

- it prevents silent benchmark identity drift;
- it confirms the archived v35 payload still contains the expected candidate;
- it explicitly excludes root-path existence, resolver bridge behavior, v35
  reactivation, active runtime loading, and pair-construction behavior.

## Deferred Medium-Risk Dry-Run

Open a separate medium-risk dry-run for an archive-aware resolver only if at
least one of these conditions becomes true:

- a real caller needs to load the v35 payload for a report, comparison, or audit
  workflow;
- a future static contract needs more than identity metadata and must inspect
  v35 manifest fields through a stable helper;
- owner explicitly asks for a compatibility bridge instead of direct archive
  reads;
- a root-path failure is observed in a test or script that should remain
  supported.

## Resolver Bridge Constraints If Reopened

A future resolver bridge must be audit-only and narrow:

- name it as a frozen/historical benchmark resolver, not a general manifest
  loader;
- check root first only for backwards compatibility, then archive fallback;
- never mutate `HYPOTHESIS_BATCH_MANIFEST_PATH`;
- never change v97 active runtime loading;
- never imply v35 reactivation, promotion, or current-line strategy status;
- test both archive fallback and unchanged v97 loading.

## Explicit Keep-Closed Items

- Do not copy or move v35 back to package root.
- Do not add a root v35 path-existence assertion.
- Do not add a public resolver helper without a new dry-run artifact.
- Do not expand the frozen benchmark contract into pair construction, scorer
  formulas, lab dispatch, execution weighting, or archived-manifest lifecycle
  semantics.

## Verification Baseline

Current sufficient verification:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Only run broader hypothesis-batch tests if a future resolver bridge changes
Python behavior.
