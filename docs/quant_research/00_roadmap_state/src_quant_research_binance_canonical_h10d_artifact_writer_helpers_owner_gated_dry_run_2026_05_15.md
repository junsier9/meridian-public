# src quant_research binance_canonical_h10d artifact writer helpers owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _write_json / _frame_or_empty / _write_universe_membership`

## Decision

Do not migrate the full artifact writer surface as one batch.

Approve only a narrow contract-first implementation path for the two generic
helpers:

- `_write_json`
- `_frame_or_empty`

Keep `_write_universe_membership` deferred until its risk-brake column boundary
has an explicit owner decision. It is not a pure writer helper because it
expands `BINANCE_RISK_BRAKE_COLUMNS`, which is also used by feature construction
and risk-brake logic.

## Caller Baseline

### `_write_json`

Internal callers in `binance_canonical_h10d.py`:

- `sync_funding_cost_history`
- `write_funding_cost_rows`
- `write_validation_artifacts`

Observed usage:

- funding sync summary JSON;
- funding symbol manifest JSON;
- dataset manifest JSON;
- gap audit JSON;
- feature manifest JSON;
- validation report JSON;
- attribution summary JSON;
- factor leave-one-out summary JSON;
- paper-shadow execution summary JSON;
- ablation summary JSON.

### `_frame_or_empty`

Internal callers in `binance_canonical_h10d.py`:

- `write_validation_artifacts`
- `compute_factor_leave_one_out_attribution`

Observed usage:

- normalize optional attribution frames before CSV writes;
- normalize optional factor attribution frames before CSV writes;
- normalize optional paper-shadow and ablation frames before CSV writes;
- protect factor leave-one-out attribution from missing nested frame payloads.

### `_write_universe_membership`

Internal caller in `binance_canonical_h10d.py`:

- `write_validation_artifacts`

Observed usage:

- writes `universe_membership.csv`;
- selects a fixed support-column set;
- includes `*BINANCE_RISK_BRAKE_COLUMNS`.

## Risk Classification

| helper | risk | first-batch decision | rationale |
| --- | --- | --- | --- |
| `_write_json` | low/medium | approve with contract | Generic JSON serialization helper; behavior can be sampled without freezing artifact schemas. |
| `_frame_or_empty` | low | approve with contract | Pure DataFrame normalization; no path or schema ownership. |
| `_write_universe_membership` | medium/high | defer | Coupled to `BINANCE_RISK_BRAKE_COLUMNS`; moving it alone would either duplicate a risk-brake constant or create circular facade pressure. |

## Required Contract Before Movement

Before moving `_write_json` or `_frame_or_empty`, add a minimal static contract
that freezes only:

- importability through `enhengclaw.quant_research.binance_canonical_h10d`;
- `inspect.signature` shape;
- `_write_json` sorting/indent/no-trailing-newline sample behavior;
- `_frame_or_empty` DataFrame-copy and non-DataFrame-empty behavior.

The contract must explicitly exclude:

- full artifact schemas;
- output path selection;
- markdown report content;
- funding sync semantics;
- validation metrics;
- universe membership column schema;
- risk-brake column ownership;
- caller counts.

## Approved Next Automation

If the minimal contract is green, the next automated step may:

1. create `src/enhengclaw/quant_research/_binance_canonical_artifacts.py`;
2. move only `_write_json` and `_frame_or_empty` into that module;
3. import both names back into `binance_canonical_h10d.py`;
4. leave `_write_universe_membership` in the root facade.

## Explicit Deferred Surfaces

Do not move or change:

- `_write_universe_membership`;
- `BINANCE_RISK_BRAKE_COLUMNS`;
- `write_validation_artifacts`;
- `_render_markdown_report` and `_metric_row` beyond their existing extracted
  reporting module;
- funding entrypoints;
- PIT universe construction;
- feature/risk-brake construction;
- CSV schemas or artifact filenames.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- The dry-run baseline is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- `_write_universe_membership` remains root-owned.
- No artifact paths are staged or committed.
