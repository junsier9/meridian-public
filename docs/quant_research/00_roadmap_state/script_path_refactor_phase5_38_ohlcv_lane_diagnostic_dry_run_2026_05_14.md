# Phase 5.38 OHLCV Lane Diagnostic Dry-Run

`Status: target decision only`
`Date: 2026-05-14`
`Scope: scripts/quant_research/run_quant_ohlcv_lane_ab.py`

## Decision

Target: future move to `scripts/quant_research/data_lane_diagnostics/` with a
root CLI compatibility wrapper.

Do not move this script into `provider_diagnostics/`, and do not permanently
freeze it at root.

This phase moved no scripts and changed no Python implementation.

## Why `data_lane_diagnostics/`

`run_quant_ohlcv_lane_ab.py` is a thin CLI over the package function
`enhengclaw.quant_research.ohlcv_lane_ab.run_quant_ohlcv_lane_ab`. The package
function runs two full quant lane comparisons:

- `binance_only`
- `coinapi_spot_binance_fallback`

Each lane runs `run_quant_universe_freeze(...)` and
`run_quant_research_cycle(...)`, then compares dataset subject counts, dataset
row counts, feature row counts, trainable strategy counts, and train split row
counts.

That makes the script a data-lane diagnostic runner. It checks how alternate
OHLCV lane selection affects downstream quant readiness and research-cycle
coverage. It is narrower than a public root-boundary entrypoint and broader
than a provider-only diagnostic.

## Why Not `provider_diagnostics/`

The current directory rule says `provider_diagnostics/` is for provider
validation, provenance, concordance, and dataset smoke diagnostics whose main
job is checking already synced provider artifacts or writing diagnostic
evidence.

This script does consume provider roots, but its main job is not provider
capability, provenance, or concordance. It runs lane-local quant cycles and
compares downstream research-cycle coverage. Moving it to
`provider_diagnostics/` would broaden that directory from provider evidence
checks into cross-lane quant-cycle A/B runners.

## Why Not Permanent Keep-Root

No scheduled task, config manifest, runtime bootstrap helper, or in-repo Python
caller hard-codes the root script path.

Known root-path reference:

- `docs/QUANT_RESEARCH_LAB.md` documents the public command:
  `python scripts\quant_research\run_quant_ohlcv_lane_ab.py --as-of 2026-04-20
  --compiler-backend deterministic`

Known package-function references:

- `tests/test_quant_research_lab.py` imports
  `enhengclaw.quant_research.ohlcv_lane_ab.run_quant_ohlcv_lane_ab` directly.
- The package implementation lives in
  `src/enhengclaw/quant_research/ohlcv_lane_ab.py`.

Because tests and reusable callers use the package function rather than the
root script module, root permanence is not required by current contracts.

## Wrapper Strategy

If a future implementation phase moves the script, a thin root wrapper should
be enough:

- moved implementation exposes the current `main(argv: list[str] | None)`
  contract;
- root wrapper imports `main` from
  `scripts.quant_research.data_lane_diagnostics.run_quant_ohlcv_lane_ab`;
- root wrapper exits with `raise SystemExit(main(sys.argv[1:]))`.

No root re-export shim is currently required because no test or script imports
private helpers or monkeypatches the old root module. If future callers start
importing the root script as a module before the move, re-check this decision.

## Artifact Surface

Default output root:

- `artifacts/benchmarks/quant_ohlcv_lanes/<run_stamp>/`

Per run, the package function writes:

- `lane_ab_summary.json`
- `lane_ab_summary.md`
- `a_binance/qa/...`
- `a_binance/wb/...`
- `b_mixed/qa/...`
- `b_mixed/wb/...`

This output belongs in benchmark/data-lane diagnostics, not canonical
`artifacts/quant_research/...` promotion evidence. The future moved script
must preserve these paths exactly unless a separate artifact contract migration
is approved.

## Future Implementation Updates

If Phase 5.39 or later moves the script, update:

- `docs/QUANT_RESEARCH_LAB.md`: either keep the documented root command through
  the compatibility wrapper or add the new implementation path as an internal
  note.
- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`:
  keep the root wrapper row as `safe-to-move = no` and add the moved
  implementation row under the new `data_lane_diagnostics/` directory.
- `scripts/quant_research/README.md`: add the new directory count and path
  policy note.
- `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`:
  add the admission rule for `data_lane_diagnostics/`.
- Tests: package-function tests should not need changes; add or run a root
  wrapper `--help` smoke if the script is moved.

Expected count effect for a future move with root wrapper:

- total script files: `+1`
- Python script files: `+1`
- root-level script files: unchanged
- `data_lane_diagnostics/`: `+1`
- root wrapper: `safe-to-move = no`
- moved implementation: `safe-to-move = yes-with-wrapper`

## Validation For This Dry-Run

Run after this documentation-only decision:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```
