# M3.2 ETF/On-Chain Sidecar Falsification Card

`Run date: 2026-05-07`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: failed hard-gate falsification; no cleared variants`

---

## Question

The direct M3.2 sparse boundary rules were Stage0-positive but failed strict
hard gates. This card asks the only allowed R-3 reopening question:

> Does a narrow, pre-registered CoinGlass ETF/on-chain participant sidecar
> change the activation definition enough for M3.2 to survive strict
> falsification?

The answer is **no**. The sidecar improves some Stage 0 local deltas, but no
variant clears deterministic hard gates, so no random-tail spend or manifest
A/B is allowed.

---

## Artifacts

- evaluator:
  `scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_2_etf_onchain_sidecar_falsification.py`
- unit tests:
  `tests/test_quant_m3_2_etf_onchain_sidecar_falsification.py`
- primary report:
  `artifacts/quant_research/factor_reports/2026-05-07-m3-2-etf-onchain-sidecar-falsification/m3_2_etf_onchain_sidecar_falsification.json`
- sidecar input:
  `artifacts/quant_research/coinglass/participant_context_1d.csv.gz`

Test command:

```powershell
python -m pytest tests/test_quant_m3_2_etf_onchain_sidecar_falsification.py tests/test_quant_m3_2_boundary_activation_stage0.py tests/test_quant_m3_2_boundary_activation_falsification.py -q
```

Result: `11 passed`.

---

## Pre-Registered Sidecar Definitions

Only the four direct Stage0-positive M3.2 labels were carried forward. The
exchange transfer feed is recorded as quarantined context because it is a
latest-event feed and raw transfer direction semantics are not provider-verified.

| variant | sidecar confirmation | active timestamps | Stage 0 delta | Stage 0 verdict |
| --- | --- | ---: | ---: | --- |
| `tron_impulse_short_high_beta_rs__cg_etf_10d_inflow_confirm` | ETF 10d flow `> 0` | 18 | +0.008530 | `stage0_positive` |
| `tron_heat_short_high_rs__cg_etf_10d_outflow_confirm` | ETF 10d flow `< 0` | 10 | +0.014983 | `stage0_positive` |
| `rebound_long_idio__cg_etf_10d_outflow_confirm` | ETF 10d flow `< 0` | 10 | +0.007398 | `stage0_positive` |
| `sell_pressure_short_high_beta_rs__cg_participant_risk_off_confirm` | ETF 10d outflow or whale-to-exchange stress | 4 | +0.018037 | `stage0_negative` |

The sell-pressure branch is rejected at Stage 0 despite a high local delta
because it has only `4` active timestamps, below the minimum `10` active
timestamp contract.

---

## Strict Gate Results

| variant | status | deterministic blockers | deterministic passes |
| --- | --- | --- | --- |
| `tron_impulse_short_high_beta_rs__cg_etf_10d_inflow_confirm` | `failed` | delay, liquidity bucket | symbol holdout, 2x cost |
| `tron_heat_short_high_rs__cg_etf_10d_outflow_confirm` | `failed` | delay, symbol holdout | liquidity bucket, 2x cost |
| `rebound_long_idio__cg_etf_10d_outflow_confirm` | `failed` | liquidity bucket | delay, symbol holdout, 2x cost |
| `sell_pressure_short_high_beta_rs__cg_participant_risk_off_confirm` | `not_run` | Stage 0 not positive | n/a |

Failure details:

- `tron_impulse_short_high_beta_rs__cg_etf_10d_inflow_confirm`: delay
  retention falls to `0.4186`; liquidity-bucket minimum side-edge improvement
  is `-0.048981`.
- `tron_heat_short_high_rs__cg_etf_10d_outflow_confirm`: delay retention is
  `0.4987`, just below the `0.50` threshold; symbol holdout minimum delta is
  `-0.009449`.
- `rebound_long_idio__cg_etf_10d_outflow_confirm`: bucket consistency fails
  with only one eligible bucket and minimum side-edge improvement of
  `-0.006277`.

Random controls were skipped after deterministic blockers under the fail-closed
policy. A variant that already fails delay, symbol holdout, or liquidity-bucket
consistency does not need random-tail budget to be rejected.

---

## Decision

`alpha_rerun_allowed = False`
`manifest_ab_allowed = False`
`strict_cleared_variants = []`

Do not reopen M3.2 with these ETF/on-chain sidecar activation definitions.
The remaining M3.2 work is not another confirmation rerun; it would require a
new mechanism definition with a different exogenous state transition and the
same hard-gate standard.
