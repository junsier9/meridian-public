# src quant_research features.py F3-A v11 Stablecoin Flow Scorer-Family Dry-Run

`Status: read-only docs-only dry-run baseline`
`Scope: src/enhengclaw/quant_research/features.py F3-A v11 stablecoin flow scorer family`
`Date: 2026-05-15`
`Mode: documentation-only; no static contract, no code change, no migration approved`

This artifact records the smallest viable F3 scorer-family candidate after the
F1 utility-helper contract and F2 raw-scorer-shim import/signature contract. It
does not create a contract. It decides whether the v11 stablecoin flow scorer
family is narrow enough to consider for a future import/signature-only static
contract.

## Decision

F3-A may proceed to a future importability/signature-only contract after owner
approval.

Do not freeze formula output. Do not freeze stablecoin sidecar construction,
feature-bundle merge behavior, provider sync behavior, or alpha promotion
semantics.

The v11 stablecoin flow scorer family is currently narrow enough to isolate
from v5/v6/SP-K/pair scorer surfaces:

- it has three direct public scorer names;
- it has one focused test file;
- scripts do not directly import these three scorer names;
- `lab.py` is the only runtime orchestration caller;
- the formulas sit behind `features.py` and reuse the already owner-gated v6 raw
  substrate.

## In Scope

| scorer | source line | current role | current direct caller surface |
| --- | ---: | --- | --- |
| `xs_alpha_ontology_v11_absorb_qshare_h10d_score` | `features.py:8421` | absorption x quote-share acceleration candidate | `lab.py`, `tests/test_stablecoin_flow_interaction_scores.py` |
| `xs_alpha_ontology_v11_drain_rs_h10d_score` | `features.py:8439` | drain x relative-strength reversal candidate | `lab.py`, `tests/test_stablecoin_flow_interaction_scores.py` |
| `xs_alpha_ontology_v11_flow_blend_h10d_score` | `features.py:8457` | absorption, drain, and whale-stress blend candidate | `lab.py`, `tests/test_stablecoin_flow_interaction_scores.py` |

All three scorer signatures currently use:

```python
def scorer(frame: pd.DataFrame, *, feature_columns: Iterable[str] | None = None) -> pd.Series
```

The `feature_columns` parameter is present for scorer/facade compatibility; the
current implementations do not use it internally.

## Existing Coverage

Focused behavior coverage exists in
`tests/test_stablecoin_flow_interaction_scores.py`:

| test | covered scorer | behavior checked |
| --- | --- | --- |
| `test_absorption_quote_share_promotes_share_gainers` | `xs_alpha_ontology_v11_absorb_qshare_h10d_score` | absorption flow can promote quote-share gainers |
| `test_drain_relative_strength_penalizes_recent_leaders` | `xs_alpha_ontology_v11_drain_rs_h10d_score` | drain flow can penalize recent leaders |
| `test_flow_blend_hits_mid_liquidity_name_harder_under_whale_stress` | `xs_alpha_ontology_v11_flow_blend_h10d_score` | whale-stress blend can penalize mid-liquidity exposure |

This coverage is useful as a smoke check, but it is not a broad formula
contract. A future F3-A static contract should not expand these tests into
golden-output snapshots.

## Boundary Notes

The three v11 scorers depend on these local helpers and columns:

- `_xs_alpha_ontology_v6_h10d_base_raw_score`;
- `_xs_alpha_ontology_interaction_single_z`;
- `_stablecoin_absorption_activation`;
- `_stablecoin_drain_activation`;
- `_stablecoin_whale_stress_activation`;
- `_mid_liquidity_mask`;
- `stablecoin_flow_signal_ready`;
- `stablecoin_labeled_coverage_ratio`;
- `stablecoin_exchange_netflow_ratio`;
- `stablecoin_exchange_absorption_score_v1`;
- `stablecoin_whale_exchange_stress_score_v1`;
- `quote_share_change_30d`;
- `relative_strength_20`;
- `liquidity_bucket`.

These dependencies are intentionally not frozen by this dry-run. In particular,
stablecoin sidecar availability and feature-bundle merge behavior remain outside
F3-A.

## Explicitly Out Of Scope

This dry-run does not approve:

- a full `features.py` scorer-family contract;
- moving or splitting `features.py`;
- moving the v11 scorers into a new source module;
- freezing formula output or score ordering beyond existing focused tests;
- freezing `_xs_alpha_ontology_v6_h10d_base_raw_score` behavior;
- freezing stablecoin provider sync paths or sidecar artifact schemas;
- freezing `build_cross_sectional_feature_bundle` sidecar merge behavior;
- freezing stablecoin admission or promotion semantics;
- including v12 MF14, v13 MF13 TRON, SP-K, MF01, pair, v5, or v6 scorers in
  this F3-A surface.

## Future Contract Shape

If owner-approved, the first F3-A contract should be import/signature only:

- source module: `enhengclaw.quant_research.features`;
- target names: the three v11 stablecoin flow scorer names listed above;
- validation mode: `importability_signature_only`;
- expected signature: `frame` positional/keyword plus optional keyword-only
  `feature_columns`;
- excluded surfaces: formulas, weights, sidecar merge, provider sync,
  `lab.py` registry semantics, caller counts, and source migration.

The existing behavior test can remain the runtime smoke:

```powershell
python -m pytest tests\test_stablecoin_flow_interaction_scores.py -q
```

Do not add golden snapshots unless a separate research owner explicitly approves
formula freeze.

## Validation Matrix

For this docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_stablecoin_flow_interaction_scores.py -q
git diff --check
```

If a future import/signature-only contract is added:

```powershell
python -m pytest tests\test_static_contracts.py tests\test_stablecoin_flow_interaction_scores.py -q
git diff --check
```

If formula, sidecar, or bundle behavior changes, this F3-A boundary is no longer
sufficient; return to an owner-gated dry-run that includes provider sidecars,
feature construction, and hypothesis-batch/lab dispatch.

## Next Gate

The next gate is an owner decision on whether to implement the F3-A
import/signature-only contract. If approved, keep the change limited to one JSON
contract and one static test addition. Do not include v12/v13, SP-K/MF01, v5/v6,
or pair scorers in the same contract.
