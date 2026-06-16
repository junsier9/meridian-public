# src quant_research binance_canonical_h10d reporting metric sanitation behavior contract dry-run

`Status: owner-gated behavior-contract dry-run`
`Date: 2026-05-15`
`Scope: _rank_ic_summary / _strip_periods / _drop_periods_from_metrics / _split_contract`

## Decision

Approve a minimal behavior contract for the reporting metric sanitation surface,
but do not move source code in this batch.

This group is the next narrowest medium-risk owner-gated surface after the score
surface contract. It supports validation reports, ablation summaries,
falsification summaries, and split-realization contract construction. The
helpers are not generic utilities; they decide which heavy period payloads are
omitted from reports and how rank-IC summary fields are computed.

## Contract Candidate

The smallest approved contract should freeze:

- root-facade importability and signatures for `_rank_ic_summary(...)`,
  `_strip_periods(...)`, `_drop_periods_from_metrics(...)`, and
  `_split_contract(...)`;
- `_rank_ic_summary(...)` on a two-period, three-subject fixture with one
  perfect positive and one perfect negative Spearman period;
- zero-output behavior for an empty or missing-column rank-IC frame;
- `_strip_periods(...)` removing only the top-level `periods` key from one
  metrics dictionary;
- `_drop_periods_from_metrics(...)` stripping nested `periods` fields from
  report metric buckets while retaining non-dict payloads;
- `_split_contract(...)` output for one explicit `4h` / `15` bar config and
  one default config.

## Explicit Non-Goals

The contract must not freeze:

- source migration or internal module layout;
- full validation report payloads;
- full falsification metrics;
- full ablation report schemas;
- `_run_backtest(...)` behavior or period-return construction;
- execution ledger behavior;
- PIT universe or risk-brake semantics;
- funding behavior;
- caller counts.

## Fixture Boundary

Use a six-row rank-IC fixture with two timestamps and three subjects. The first
timestamp has score and target in the same rank order, and the second timestamp
has the inverse rank order. The expected summary is:

```text
period_count = 2
mean_rank_ic = 0.0
std_rank_ic = 1.4142135623730951
t_stat = 0.0
```

This is a tiny behavior sample. It does not become a golden snapshot for all
validation or falsification outputs.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The follow-up implementation, if performed, touches only a contract JSON and
  `tests/test_static_contracts.py`.
- No `src/enhengclaw/quant_research` files move or change.
- No checked-in artifact paths are staged.
