# src quant_research binance_canonical_h10d hash identity implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: _stable_hash / _stable_int identity helper extraction`

## Decision

Create `src/enhengclaw/quant_research/_binance_canonical_identity.py` and move
only `_stable_hash` and `_stable_int` into it. Keep
`binance_canonical_h10d.py` as the root facade through explicit imports.

This implementation is allowed because the hash identity contract now freezes:

- `_stable_hash` signature and representative digest samples;
- `_stable_int` signature and representative subject holdout bucket identity.

## Approved Move Set

Move these names into `_binance_canonical_identity.py`:

- `_stable_hash`
- `_stable_int`

Import both names back into `binance_canonical_h10d.py` so existing root
attribute access remains compatible.

## Explicit Deferred Surfaces

Do not move or change:

- `build_feature_manifest(...)`
- `_run_falsification_suite(...)`
- feature-manifest payload construction
- symbol holdout selection logic
- `_timestamp_zscore` / `_timestamp_percentile_rank`
- date/time helpers
- artifact writers

## Compatibility Strategy

- Keep root facade access working:
  - `binance_canonical_h10d._stable_hash`
  - `binance_canonical_h10d._stable_int`
- Keep identity behavior protected by
  `config/quant_research/src_quant_research_binance_canonical_h10d_hash_identity_contract.json`.
- Avoid importing `binance_canonical_h10d.py` from the new identity module.
- Remove `hashlib` from `binance_canonical_h10d.py` only if it is no longer used
  after the move.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_identity.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `_stable_hash.__module__` and `_stable_int.__module__` point at
  `_binance_canonical_identity`.
- Root facade attribute access still works from `binance_canonical_h10d.py`.
- Static hash identity contract stays green.
- No artifact paths are staged or committed.
