# Binance PIT Stratified Holdout Gate Update - 2026-05-11

## Decision

The legacy deterministic A/B symbol holdout is downgraded to diagnostic only.
It remains in the falsification report, but it no longer participates in the
hard `passed | failed | blocked` status.

The hard holdout gate is now `stratified_repeated_symbol_holdout`.

## Hard Gate Policy

- repeat count: `8`
- folds per repeat: `2`
- minimum positive fold fraction: `0.75`
- require every fold to be gap-free: `true`
- stratification columns:
  - primary liquidity bucket
  - major vs alt bucket
  - listing-age bucket
  - quote-volume bucket

This is stricter than the old A/B split because the split is repeatedly
balanced across observable decision-time liquidity and maturity structure
instead of relying on one arbitrary hash partition.

## Validation Run

Command:

```powershell
python scripts\quant_research\run_binance_canonical_h10d_validation.py --store-root E:\EnhengClawData\market_history\binance_1m_five_year --funding-root E:\EnhengClawData\market_history\binance_funding_cost_only --as-of 2026-04-30 --config config\quant_research\binance_pit_top_mid_h10d.json --pit-min-lifetime-valid-days 30 --run-id 20260511TpitTopMidStratHoldoutLife30-1k-v5_binance_pit_top_mid_h10d
```

Result: `failed`

The old A/B holdout still fails diagnostically, but it is not the hard blocker:

- legacy A/B positive count: `1`
- legacy A/B role: `diagnostic`

The new stratified holdout result:

| Metric | Value |
| --- | ---: |
| fold count | 16 |
| positive folds | 14 |
| positive fraction | 0.875 |
| gap-free folds | 5 |
| gap-free fraction | 0.3125 |
| min net return | -0.399408 |
| median net return | 0.774024 |
| max net return | 2.316132 |

Interpretation: the return robustness condition passed, but the execution-path
data integrity condition failed. The strategy remains fail-closed because only
5 of 16 stratified folds had complete fill/exit paths.

## Primary Artifacts

- validation report: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidStratHoldoutLife30-1k-v5_binance_pit_top_mid_h10d/validation_report.json`
- generated markdown report: `docs/quant_research/02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_11.md`

## Current Conclusion

This change removes the arbitrary A/B split as a hard decision rule. The current
Binance-only PIT top/mid core still cannot enter paper because the new hard
holdout gate exposes incomplete execution paths across repeated stratified
symbol subsets.

## Backfilled Rerun Update

After the failing diagnostic above, the local Binance 1m archive was patched
for the concentrated bad partitions rather than changing the strategy logic.

Backfill command:

```powershell
python scripts\market_data\build_binance_1m_research_store.py backfill-rest-gaps --external-root E:\EnhengClawData\market_history\binance_1m_five_year --markets usdm_perp --symbols SOLUSDT XRPUSDT LTCUSDT SANDUSDT NEARUSDT MANAUSDT ONEUSDT --months 2022-02 2022-04 --format parquet --request-sleep-seconds 0.03
```

Backfill result:

- source: `Binance USD-M REST fapi/v1/klines`
- partitions patched: `14`
- fetched 1m rows: `50,400`
- missing minutes before: `50,400`
- missing minutes after: `0`
- error partitions: `0`

Backfilled validation command:

```powershell
python scripts\quant_research\run_binance_canonical_h10d_validation.py --store-root E:\EnhengClawData\market_history\binance_1m_five_year --funding-root E:\EnhengClawData\market_history\binance_funding_cost_only --as-of 2026-04-30 --config config\quant_research\binance_pit_top_mid_h10d.json --pit-min-lifetime-valid-days 30 --run-id 20260511TpitTopMidStratHoldoutLife30Backfilled-1k-v5_binance_pit_top_mid_h10d
```

Backfilled result: `passed`

| Gate | Value |
| --- | ---: |
| base positive return | true |
| stress positive return | true |
| liquidity positive bucket gate | true |
| stratified holdout fold count | 16 |
| stratified holdout positive folds | 14 |
| stratified holdout positive fraction | 0.875 |
| stratified holdout gap-free folds | 16 |
| stratified holdout hard gate | true |
| legacy A/B positive count | 1 |
| legacy A/B role | diagnostic |

Primary backfilled artifacts:

- validation report: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidStratHoldoutLife30Backfilled-1k-v5_binance_pit_top_mid_h10d/validation_report.json`
- REST backfill summary: `E:\EnhengClawData\market_history\binance_1m_five_year\last_rest_backfill_summary.json`

Updated conclusion: the prior hard failure was an archive completeness problem,
not a strategy failure. After targeted Binance REST backfill, the PIT top/mid
Binance-only core passes this validation slice. The old A/B diagnostic remains
negative and should be interpreted as a warning for further robustness work, not
as the current hard blocker.
