# src quant_research features.py F2 Raw Scorer Shim Dry-Run

`Status: owner-gated read-only dry-run baseline`
`Scope: src/enhengclaw/quant_research/features.py F2 raw scorer shim surface`
`Date: 2026-05-14`
`Mode: documentation-only; no static contract, no code change, no migration approved`

This artifact expands the F2 row from
`src_quant_research_features_compatibility_dry_run_2026_05_14.md`. It records
the current raw scorer shim surface before any future source split or facade
work. It is intentionally not a test contract and intentionally does not freeze
formula output.

## Decision

Do not migrate the F2 raw scorer helpers.

Do not freeze scorer formula values with golden-output tests.

Any future extraction must be facade-first: `features.py` must remain the stable
import surface, and any internal implementation module must be introduced behind
that facade only after a separate owner-approved implementation plan.

## F2 Surface

| helper | current source line | current role | governance read |
| --- | ---: | --- | --- |
| `_xs_alpha_ontology_v5_h10d_base_raw_score` | `features.py:8330` | v5 h10d parent raw score shim | owner-gated; quarantine/stage0 evidence depends on current import |
| `_xs_alpha_ontology_v6_h10d_base_raw_score` | `features.py:8323` | v6 h10d raw substrate | high-risk; reused by v6/v11/v12/v13 scorer families |
| `_xs_alpha_ontology_v6_h10d_spk_short_replacement_score` | `features.py:8583` | SP-K/MF01 replacement helper | high-risk; complex kw-only shim used by `features.py`, `lab.py`, scripts, and tests |

These helpers are private by name but public-by-use inside the repo. Treat them
as compatibility shims until a narrower facade plan exists.

## Reverse Dependency Baseline

Read-only AST and text scans found the following live caller shape:

| helper | external direct import/call surface | internal caller surface |
| --- | --- | --- |
| `_xs_alpha_ontology_v5_h10d_base_raw_score` | 8 `scripts/quant_research/alpha_stage0_quarantine/` files | used as alternate base raw scorer for v5/SP-K replacement paths |
| `_xs_alpha_ontology_v6_h10d_base_raw_score` | 1 root v6 news-veto diagnostic script | 9 internal scorer or overlay functions |
| `_xs_alpha_ontology_v6_h10d_spk_short_replacement_score` | 8 `alpha_stage0_quarantine` files plus `tests/test_quant_m3_3_hype_chatter_gate_stage0.py` | 14 internal scorer wrappers plus 2 `lab.py` bundle scoring helpers |

The important escalation versus F1 utility helpers is `lab.py`: the SP-K
replacement helper is imported from `features.py` and used inside bundle scoring
helpers. That makes it a facade-sensitive scoring primitive, not a simple
utility helper.

## Formula-Freeze Boundary

Formula output must not be frozen in this phase.

Reasons:

- raw-score values depend on timestamp-local z-score/rank behavior and available
  panel columns;
- v5/v6 factor-weight composition is research-state dependent;
- SP-K replacement behavior has multiple kw-only controls, veto columns,
  liquidity-bucket filters, and selected-short replacement paths;
- a broad golden-output fixture would accidentally bless current research
  formulas as long-term public API;
- future research may need to revise formulas while preserving import and
  facade compatibility.

Allowed future test shape, after owner approval:

- importability of the three helper names from
  `enhengclaw.quant_research.features`;
- signature stability for required positional and kw-only parameters;
- narrow branch behavior tests only when tied to an existing research contract;
- no broad golden-value scorer snapshots.

## Not Approved

This dry-run does not approve:

- moving any F2 helper out of `features.py`;
- adding a F2 static contract now;
- adding golden-output scorer tests for the F2 formulas;
- rewriting stage0/quarantine imports;
- rewriting `lab.py` scoring helper imports;
- converting the private helpers into new documented public APIs;
- expanding F2 into a whole `features.py` scorer-family contract.

## Facade-First Only Path

If an owner later approves implementation work, use this order:

1. Write an implementation plan that lists every direct script, test, `lab.py`,
   and internal `features.py` caller.
2. Add a small compatibility contract for importability and signature only.
3. Introduce any internal implementation module behind the existing
   `features.py` names.
4. Keep the `features.py` helper names import-compatible for scripts and tests.
5. Run family-specific tests before considering any import rewrite.

The facade must be proven before moving code. Direct extraction without a
stable `features.py` facade is out of scope.

## Future Validation Matrix

If a future F2 import/signature contract is approved:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_m3_3_hype_chatter_gate_stage0.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -q
git diff --check
```

If `lab.py` scoring paths are touched:

```powershell
python -m pytest tests\test_quant_research_lab.py tests\test_quant_hypothesis_batch.py -q
```

If a formula or scorer wrapper changes:

```powershell
python -m pytest tests\test_quant_m3_3_hype_chatter_gate_stage0.py tests\test_quant_m3_3_strict_event_state_scorer.py -q
python -m pytest tests\test_stablecoin_flow_interaction_scores.py -q
```

## Next Gate

The next gate is owner approval for a minimal F2 import/signature contract. Until
then, the F2 raw scorer shim surface remains owner-gated, formula-unfrozen, and
facade-first only.
