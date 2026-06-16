# src quant_research binance_canonical_h10d hash identity owner-gated dry-run

`Status: read-only owner-gated dry-run`
`Date: 2026-05-15`
`Scope: _stable_hash / _stable_int in binance_canonical_h10d.py`

## Decision

Do not move `_stable_hash` or `_stable_int` yet. They look like generic helper
functions, but both control identity surfaces:

- `_stable_hash` writes `feature_manifest_hash`.
- `_stable_int` assigns symbols to deterministic falsification holdout buckets.

The next safe automation step is a tiny identity contract that freezes known
hash digests and known subject-to-holdout bucket assignments. Source movement
requires a later implementation plan after that contract is green.

## Current Caller Map

| Helper | Current root caller | Identity surface | Risk |
| --- | --- | --- | --- |
| `_stable_hash(payload)` | `build_feature_manifest(...)` | `feature_manifest_hash` in the Binance canonical h10d feature manifest | medium/high |
| `_stable_int(value)` | `_run_falsification_suite(...)` | `holdout_a` / `holdout_b` subject partitioning | medium/high |

No repo-local direct import of either helper outside
`binance_canonical_h10d.py` was required for this decision. The risk is not
external import compatibility; it is silent identity drift.

## Required Identity Contract

The contract should freeze:

- `_stable_hash` importability and signature.
- `_stable_int` importability and signature.
- At least two canonical `_stable_hash` sample payload digests:
  - a feature-manifest-shaped payload;
  - an order-invariance payload with intentionally unsorted keys.
- A small subject bucket map for `_stable_int`, including common h10d subjects
  and at least one `USDT`-suffixed symbol string.

## Explicit Non-Goals

- Do not move `_stable_hash` or `_stable_int` in the contract commit.
- Do not freeze all feature-manifest content.
- Do not freeze falsification metrics, backtest output, or pass/fail decisions.
- Do not change holdout logic or subject normalization.
- Do not reuse this contract for unrelated hash helpers in other modules.

## Approved Next Automation

Approved next automatic step: add a small
`config/quant_research/src_quant_research_binance_canonical_h10d_hash_identity_contract.json`
and a static-contract test that:

1. imports `enhengclaw.quant_research.binance_canonical_h10d`;
2. verifies `_stable_hash` and `_stable_int` signatures;
3. verifies known `_stable_hash` digests;
4. verifies known `_stable_int` integer values and holdout buckets;
5. asserts that source migration and formula/output broadening are excluded.

## Deferred Implementation

A later source-move plan may evaluate a private helper module such as
`_binance_canonical_identity.py`, but only after the identity contract is
present and green. Any move must keep root facade access working.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```
