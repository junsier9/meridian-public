# Binance PIT Factor Attribution And Shadow Ledger - 2026-05-11

## Scope

This note upgrades the `v5_binance_pit_top_mid_h10d` explanation from static
input weights to realized validation artifacts:

- per-factor leave-one-out attribution
- paper/shadow execution ledger

The strategy remains Binance-only for core alpha. No live orders are created by
this slice.

## Validation Run

```powershell
python scripts\quant_research\run_binance_canonical_h10d_validation.py --store-root E:\EnhengClawData\market_history\binance_1m_five_year --funding-root E:\EnhengClawData\market_history\binance_funding_cost_only --as-of 2026-04-30 --config config\quant_research\binance_pit_top_mid_h10d.json --pit-min-lifetime-valid-days 30 --run-id 20260511TpitTopMidFactorLedgerBackfilled-1k-v5_binance_pit_top_mid_h10d
```

Result: `passed`

Primary artifacts:

- validation report: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFactorLedgerBackfilled-1k-v5_binance_pit_top_mid_h10d/validation_report.json`
- factor leave-one-out: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFactorLedgerBackfilled-1k-v5_binance_pit_top_mid_h10d/factor_leave_one_out.csv`
- factor summary: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFactorLedgerBackfilled-1k-v5_binance_pit_top_mid_h10d/factor_leave_one_out_summary.json`
- shadow ledger: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFactorLedgerBackfilled-1k-v5_binance_pit_top_mid_h10d/paper_shadow_execution_ledger.csv`
- shadow summary: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFactorLedgerBackfilled-1k-v5_binance_pit_top_mid_h10d/paper_shadow_execution_summary.json`

## Factor Leave-One-Out

Method: remove one feature, rescore the full portfolio with the remaining
Binance-only features, then rerun base/stress backtests. A positive
`base-minus-LOO net` means the feature helped realized portfolio performance;
a negative value means the strategy would have performed better without it.

Baseline base net return: `2.198882`

| Removed feature | Weight share | Base-minus-LOO net | Base-minus-LOO Sharpe | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `downside_upside_vol_ratio_30` | 0.103 | 1.173067 | 0.360 | Strong realized positive contributor. |
| `distance_to_high_5` | 0.155 | 1.110208 | 0.350 | Strong realized positive contributor. |
| `intraday_realized_vol_4h_to_1d_smooth_60` | 0.206 | 0.817929 | 0.213 | Strong realized positive contributor. |
| `distance_to_high_60` | 0.186 | 0.364557 | 0.104 | Moderate positive contributor. |
| `realized_volatility_5` | 0.103 | 0.231392 | 0.068 | Modest positive contributor. |
| `liquidity_stress_qv_iv` | 0.103 | -0.369338 | -0.095 | Negative realized contributor. |
| `momentum_decay_5_20` | 0.062 | -0.369655 | -0.064 | Negative realized contributor. |
| `settlement_cycle_premium_60d` | 0.082 | -0.458923 | -0.079 | Negative realized contributor. |

Current interpretation: the realized alpha is carried mostly by downside/upside
vol structure, short-term proximity to highs, and low sustained intraday
volatility. The liquidity-stress, momentum-decay, and settlement-cycle sleeves
are not earning their keep in this backfilled validation slice.

## Paper/Shadow Execution Ledger

The ledger is `paper_shadow_no_live_orders`: it records what the strategy would
try to hold and how the historical fill/exit/cost model realizes it, but it does
not place or simulate exchange order state beyond the validation cost contract.

| Metric | Value |
| --- | ---: |
| ledger rows | 1,477 |
| order rows | 830 |
| position rows | 1,102 |
| period count | 177 |
| trade notional USD | 126,397.435897 |
| turnover | 126.397436 |
| max trade participation | 0.000020 |
| capacity breach count | 0 |
| data gap blockers | 0 |

Side summary from the shadow ledger:

| Side | Gross contribution | Fee cost | Slippage cost | Funding cost | Net contribution |
| --- | ---: | ---: | ---: | ---: | ---: |
| long | 0.674746 | 0.013475 | 0.003395 | 0.096593 | 0.561284 |
| short | 0.804883 | 0.027744 | 0.007054 | -0.068178 | 0.838264 |
| flat/close rows | 0.000000 | 0.034619 | 0.008791 | 0.000000 | -0.043410 |

The flat rows are close/reduce trades where the target position becomes zero;
they carry execution cost but no holding return.

## Updated Research Takeaway

The earlier weight-based explanation overstated three sleeves that now look
weak on realized leave-one-out evidence:

- `settlement_cycle_premium_60d`
- `momentum_decay_5_20`
- `liquidity_stress_qv_iv`

The current liveable core should be treated as a passed candidate with a clear
next research question: either remove or re-parameterize those negative LOO
contributors, then rerun the same strict Binance-only gates before paper.
