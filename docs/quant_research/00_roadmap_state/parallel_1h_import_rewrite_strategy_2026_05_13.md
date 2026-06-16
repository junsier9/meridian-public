# Parallel 1h Import Rewrite Strategy - 2026-05-13

`Status: implemented strategy artifact`
`Scope: scripts/quant_research parallel_1h path refactor only`
`Decision: Phase 5 used the cohesive package move plus root compatibility wrappers`

This note resolved the blocker left by
`script_path_refactor_dry_run_phase2a_2026_05_12.md`: the `parallel_1h` lane has
zero external path references for the 20 `safe-to-move = yes` scripts, but it
does have sibling Python imports. Moving files without rewiring imports would
make some scripts fail at import time.

## Recommendation

Use the cohesive package move:

```text
scripts/quant_research/parallel_1h/
```

Move all 23 `parallel_1h` implementation scripts into that directory, not only the 20
`safe-to-move = yes` scripts.

For the 3 scripts currently marked `yes-with-wrapper`, leave root-level thin
compatibility wrappers at their old paths:

- `scripts/quant_research/audit_parallel_1h_native_exchange_flow_sidecar.py`
- `scripts/quant_research/build_parallel_1h_trust_masked_venue_concentration_sidecar.py`
- `scripts/quant_research/evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py`

Reason: those three are part of the same import/dependency cluster. Keeping
their implementation at root while moving their dependencies would create a
half-moved lane. A package move plus wrappers keeps the public CLI surface stable
without splitting the implementation.

## Why Not Move Only The 20 `safe = yes` Scripts?

That narrower move is possible but less clean:

| option | impact |
| --- | --- |
| Move only 20 `safe = yes` scripts | requires root-level holdout scripts to import implementation modules from `scripts.quant_research.parallel_1h`; lane implementation remains split |
| Move all 23 and wrap 3 old paths | one implementation directory; old paths preserved where catalog says `yes-with-wrapper`; easier to reason about and test |

Use the second option unless there is a strong reason to preserve root-level
implementation files.

## Import Rewrite Rule

After moving implementation files into `scripts/quant_research/parallel_1h/`,
rewrite sibling imports to package-qualified imports:

```python
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval
```

Avoid bare sibling imports such as:

```python
import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval
```

Reason: package-qualified imports work from both direct script execution and
root-level compatibility wrappers as long as the repo root is on `sys.path`.

## Root Resolution Rule

Most current root-level scripts derive repo root from:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
```

After moving to `scripts/quant_research/parallel_1h/`, that becomes wrong.
Implementation files should use:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
```

Root-level thin wrappers should keep the existing root-level calculation and
call the moved implementation's `main(...)`.

## Observed Import Edges

These edges must be rewritten during the move:

| importer | imported module |
| --- | --- |
| `audit_parallel_1h_fake_liquidity_parent_symbol_provider_sensitivity.py` | `simulate_parallel_1h_fake_liquidity_parent_interaction` |
| `evaluate_parallel_1h_fake_liquidity_atomic_decomposition.py` | `evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0` |
| `evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0.py` | `evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0` |
| `evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_funding_normalization_after_deep_negative_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_funding_normalization_after_deep_negative_stage0.py` | `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0` |
| `evaluate_parallel_1h_funding_settlement_squeeze_window_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_funding_settlement_squeeze_window_stage0.py` | `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0` |
| `evaluate_parallel_1h_liquidation_cluster_aftershock_veto_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_liquidation_cluster_aftershock_veto_stage0.py` | `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0` |
| `evaluate_parallel_1h_low_liquidity_hour_kill_switch_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_low_liquidity_hour_kill_switch_stage0.py` | `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0` |
| `evaluate_parallel_1h_post_pump_bid_replenishment_failure_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_post_pump_bid_replenishment_failure_stage0.py` | `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0` |
| `evaluate_parallel_1h_post_squeeze_exit_short_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_top_trader_fade_retail_chase_veto_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `evaluate_parallel_1h_top_trader_fade_retail_chase_veto_stage0.py` | `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0` |
| `evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py` | `evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0` |
| `evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py` | `evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0` |
| `evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py` | `evaluate_parallel_1h_low_float_squeeze_trap_stage0` |
| `simulate_parallel_1h_fake_liquidity_age_gated_parent_interaction.py` | `simulate_parallel_1h_fake_liquidity_parent_interaction` |
| `simulate_parallel_1h_fake_liquidity_age_sidecar.py` | `simulate_parallel_1h_fake_liquidity_parent_interaction` |
| `simulate_parallel_1h_fake_liquidity_parent_interaction.py` | `evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0` |

## Wrapper Shape

Use a minimal wrapper for the three `yes-with-wrapper` old paths:

```python
from __future__ import annotations

import sys

from scripts.quant_research.parallel_1h.<module_name> import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

Only use wrappers where `safe-to-move = yes-with-wrapper`; do not add wrappers
for the 20 `safe-to-move = yes` scripts unless a later scan finds a real caller.

## Required Catalog Updates

When executing this move:

- catalog paths for all 23 `parallel_1h` rows should point at
  `scripts/quant_research/parallel_1h/...`
- the 3 moved implementation rows with preserved wrappers remain
  `safe-to-move = yes-with-wrapper`
- the 3 root wrapper rows are cataloged separately as `safe-to-move = no`
- the 20 clean rows can remain `safe-to-move = yes`
- `scripts/quant_research/README.md` coverage should become:

```text
162 root-level, 7 legacy_candidates, 23 parallel_1h
```

The Phase 5 implementation keeps the 3 root wrappers as extra files, so the
catalog count increases to 192 scripts: 23 moved implementations plus 3
root-level compatibility wrappers in the `parallel_1h` category.

## Minimum Validation

After the actual move:

```powershell
python -m compileall -q scripts\quant_research\parallel_1h
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run an old-path smoke for each wrapper:

```powershell
python scripts\quant_research\audit_parallel_1h_native_exchange_flow_sidecar.py --help
python scripts\quant_research\build_parallel_1h_trust_masked_venue_concentration_sidecar.py --help
python scripts\quant_research\evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py --help
```

## Out Of Scope

- no change to h10d canonical/Binance PIT entrypoints
- no change to scheduled wrappers
- no artifact movement
- no admission of any parallel 1h alpha
