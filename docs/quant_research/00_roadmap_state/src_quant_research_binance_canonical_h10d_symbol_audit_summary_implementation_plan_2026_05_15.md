# binance_canonical_h10d Symbol Audit Summary Implementation Plan

`Status: Phase B archive-helper implementation plan`
`Scope: facade-first extraction of _summarize_symbol_audits only`
`Date: 2026-05-15`

## Decision

Extract only `_summarize_symbol_audits` from
`src/enhengclaw/quant_research/binance_canonical_h10d.py` into the existing
internal archive helper module:

- `src/enhengclaw/quant_research/_binance_canonical_archive.py`

Root facade requirement:

- `binance_canonical_h10d.py` must continue to expose
  `_summarize_symbol_audits` as an importable name.

## Approved Movement

Move:

- `_summarize_symbol_audits(symbol_audits: list[dict[str, Any]]) -> dict[str, Any]`

Keep in root:

- `_stable_hash`
- `_stable_int`
- `_partition_month`
- `_symbol_partition_paths`
- all funding helpers and funding loaders
- all PIT universe, validation, attribution, paper ledger, risk-brake, and
  reporting orchestration code.

## Rationale

`_summarize_symbol_audits` is a narrow archive/gap-audit summarizer used only
when constructing `gap_audit["summary"]` in `build_binance_canonical_dataset`.

It does not depend on:

- pandas or numpy;
- funding-cost loaders;
- PIT universe selection;
- validation gates;
- feature-manifest hashing;
- execution helpers.

The nearby `_stable_hash` and `_stable_int` helpers are explicitly excluded:

- `_stable_hash` participates in `build_feature_manifest`;
- `_stable_int` participates in falsification holdout splitting.

Those belong to feature-manifest / validation behavior, not archive helper
cleanup.

## Explicit Non-Goals

Do not:

- change any gap-audit field name or count semantics;
- move `_stable_hash` or `_stable_int`;
- move `_partition_month` or `_symbol_partition_paths`;
- touch funding, PIT universe, validation, risk-brake, attribution, paper
  ledger, or reporting logic;
- add a broad archive module contract.

## Validation Commands

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_binance_canonical_h10d.py -k "archive or symbol_feature" -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Post-Commit Review Questions

- Does `binance_canonical_h10d.py` still expose `_summarize_symbol_audits`?
- Does `_binance_canonical_archive.py` remain limited to archive read/coercion
  and symbol-audit summary behavior?
- Did the implementation avoid `_stable_hash`, `_stable_int`, partition helpers,
  funding, PIT universe, and validation boundaries?
- Should archive helper extraction stop here until a stronger need appears?
