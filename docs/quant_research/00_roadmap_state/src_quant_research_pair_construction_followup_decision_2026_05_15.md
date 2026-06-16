# Pair-Construction Follow-Up Decision

`Status: owner decision`
`Scope: hypothesis_batch normalization, execution quality_bucket_pairs, frozen benchmark`
`Date: 2026-05-15`

## Decision

Do not continue into three broader pair-construction contracts now.

Close the current pair-construction follow-up at the behavior-test level:

- keep the `hypothesis_batch` pair-book profile normalization behavior test as
  the active contract surface;
- keep `execution_backtest.py` `quality_bucket_pairs` under existing behavior
  tests, without a new static contract;
- keep frozen benchmark v35 closed at the identity-only static contract and
  owner decision.

## Why

The original dry-run split the surface into three boundaries so scorer-family
contracts would not accidentally freeze execution behavior:

1. `hypothesis_batch.py` profile normalization;
2. `execution_backtest.py` `quality_bucket_pairs` target-weight construction;
3. frozen benchmark metadata for `xs_pair_spread_book_v8_h5d`.

That split has now served its purpose:

- `hypothesis_batch` normalization has a focused positive behavior test and a
  negative validation test for out-of-range stability constraints;
- `execution_backtest.py` already has broad pair behavior coverage across pair
  selection, soft caps, quality balance, trend crowding, pair switching, and
  turnover modes;
- frozen benchmark v35 is separately protected by an identity-only static
  contract and a docs-only owner decision that rejects resolver bridge work for
  now.

## Current Boundary State

| boundary | state | next action |
| --- | --- | --- |
| `hypothesis_batch` pair-book normalization | covered by focused behavior tests | no new static JSON unless facade-first split touches `_normalize_profile_constraints` |
| `execution_backtest.py` `quality_bucket_pairs` | covered by existing behavior tests | defer any new contract until a target-weight refactor is proposed |
| frozen benchmark v35 | identity-only static contract + owner decision | closed; do not add resolver bridge without new medium-risk dry-run |

## Explicit Non-Goals

- Do not write one combined pair-construction contract.
- Do not add execution target-weight golden outputs.
- Do not freeze exact pair ordering, scorer formulas, or alpha quality.
- Do not expand the frozen benchmark contract beyond identity.
- Do not add an archive-aware v35 resolver bridge.
- Do not move `hypothesis_batch.py`, `execution_backtest.py`, or archived
  manifests as part of this decision.

## Reopen Conditions

Open a separate dry-run only if one of these becomes true:

- `_normalize_profile_constraints` is extracted, renamed, or hidden behind a
  facade;
- `quality_bucket_pairs` target-weight construction is refactored or moved;
- execution pair tests fail in a way that indicates an intended compatibility
  surface rather than a normal behavior bug;
- a real caller needs to load frozen v35 through a stable helper;
- owner explicitly asks to freeze a narrower execution sub-surface.

## Verification Baseline

Current verification:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k "pair_book_profile_constraints or pair_normalization" -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

The current decision is documentation-only and does not change Python behavior.
