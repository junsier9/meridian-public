# src quant_research binance_canonical_h10d datetime boundary owner-gated dry-run

`Status: read-only owner-gated dry-run`
`Date: 2026-05-15`
`Scope: _parse_date / _date_to_ms / _ms_to_date / _date_utc_series`

## Decision

Do not move the date/time helpers until a tiny UTC identity contract exists.
These helpers are not generic formatting utilities; they define the UTC day
boundary used by PIT universe selection, kline feature construction, funding
sync/load, validation artifacts, attribution ledgers, and paper-shadow ledgers.

The next safe automation step is a static/behavior contract that freezes a
small set of UTC conversion samples and signatures. Source migration can be
evaluated only after that contract is green.

## Current Caller Map

| Helper | Main call surfaces | Boundary risk |
| --- | --- | --- |
| `_parse_date(value)` | PIT universe freeze, symbol feature build, funding sync, validation run | Accepted input types and UTC conversion from aware datetimes. |
| `_date_to_ms(value)` | as-of filtering, funding sync window, lookback start windows | UTC midnight millisecond identity. |
| `_ms_to_date(value)` | PIT summaries, dataset date ranges, attribution ledgers, paper-shadow ledgers | UTC date identity from epoch milliseconds. |
| `_date_utc_series(values)` | funding daily load, daily bars, 4h/1h derived features | Vectorized UTC date labels and missing-value string behavior. |

AST import scan found no repo-local direct import of these helpers outside
`binance_canonical_h10d.py`. The migration risk is therefore semantic, not
external import compatibility.

## Observed Identity Samples

| Sample | Current result |
| --- | --- |
| `_parse_date("2026-01-02")` | `date(2026, 1, 2)` |
| `_parse_date(date(2026, 1, 2))` | `date(2026, 1, 2)` |
| `_parse_date(datetime(2026, 1, 2, 23, 0, tzinfo=UTC))` | `date(2026, 1, 2)` |
| `_date_to_ms(date(2026, 1, 1))` | `1767225600000` |
| `_ms_to_date(1767225600000)` | `date(2026, 1, 1)` |
| `_date_utc_series([1767225600000, 1767312000000, None, "bad"])` | `["2026-01-01", "2026-01-02", "NaT", "NaT"]` |

## Required Contract

The contract should freeze:

- importability and signatures for all four helpers;
- `_parse_date` string/date/aware-datetime samples;
- `_date_to_ms` UTC midnight samples;
- `_ms_to_date` UTC date samples;
- `_date_utc_series` vectorized output including the current missing-value
  `NaT` string behavior.

## Explicit Non-Goals

- Do not change local-time or naive-datetime behavior in this pass.
- Do not change missing timestamp behavior.
- Do not move helpers in the contract commit.
- Do not freeze all downstream validation/backtest outputs.
- Do not touch funding, PIT, artifact writer, feature-normalization, or hash
  helper modules in the same commit.

## Approved Next Automation

Approved next automatic step: add
`config/quant_research/src_quant_research_binance_canonical_h10d_datetime_boundary_contract.json`
and a static-contract test that verifies the signature and sample identities
above.

## Deferred Implementation

If the contract is green, a later implementation plan may move these helpers
into a private `_binance_canonical_time.py` module and import them back through
the root facade. That future move must keep root attribute access working.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```
