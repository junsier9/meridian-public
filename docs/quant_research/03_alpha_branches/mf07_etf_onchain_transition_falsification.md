# MF-07 ETF/On-Chain Transition Falsification Card

`Run date: 2026-05-09`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: failed Stage 0; no strict survivors`

---

## Question

The R-7 gate rejected old daily top/global and sub-day participant-pivot forms,
but left one valid reopening path:

> Integrate PIT CoinGlass ETF/exchange/whale sidecars into a new
> pre-registered MF-07 transition definition, then test whether it beats raw
> SP-K on the canonical parent.

This card executes that reopening. The answer is **no**. The sidecars are now
integrated into the transition test, but no variant clears Stage 0 admission.

---

## Artifacts

- evaluator:
  `scripts/quant_research/evaluate_mf07_etf_onchain_transition_falsification.py`
- unit tests:
  `tests/test_quant_mf07_etf_onchain_transition_falsification.py`
- primary report:
  `artifacts/quant_research/factor_reports/2026-05-09-r7-mf07-etf-onchain-transition-falsification/mf07_etf_onchain_transition_falsification.json`
- input sidecar:
  `artifacts/quant_research/coinglass/participant_context_1d.csv.gz`

Test command:

```powershell
python -m pytest tests/test_quant_mf07_etf_onchain_transition_falsification.py tests/test_quant_mf07_participant_disagreement_spk_stage0.py tests/test_quant_mf07_participant_stack_r7_gate.py -q
```

Result: `10 passed`.

---

## Sidecar Coverage

The transition test uses only PIT-lagged ETF and whale fields. Exchange-transfer
activity is reported but kept quarantined because raw transfer direction is not
provider-verified.

| state | timestamp count | row fraction |
| --- | ---: | ---: |
| ETF context available | n/a | `53.52%` timestamp coverage |
| whale context available | n/a | `14.09%` timestamp coverage |
| exchange context available | n/a | `0.37%` timestamp coverage, quarantined |
| `cg_risk_off_state` | `187` | `17.11%` |
| `cg_risk_on_state` | `420` | `38.44%` |
| `r7_any_mf07_stress_cg_risk_off_flag` | `181` | `5.91%` |
| `r7_any_mf07_stress_cg_risk_on_flag` | `386` | `10.30%` |
| `r7_low_corr_cg_risk_off_flag` | `154` | `2.70%` |

---

## Stage 0 Results

Admission requires:

- edge vs raw SP-K `>= +0.0005`;
- changed timestamp fraction `>= 5%`;
- entered names better than exited names.

| variant | landing shape | flag timestamps | edge vs raw SP-K | changed timestamps | entered edge vs exited | Stage 0 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `confirm_any_mf07_stress_cg_risk_off` | candidate confirm | `181` | `-0.001313` | `50.96%` | `-0.007744` | fail |
| `confirm_high_gap_cg_risk_off` | candidate confirm | `135` | `-0.001033` | `51.24%` | `-0.006059` | fail |
| `confirm_low_corr_cg_risk_off` | candidate confirm | `154` | `-0.001087` | `52.06%` | `-0.006273` | fail |
| `confirm_high_velocity_cg_risk_off` | candidate confirm | `143` | `-0.001407` | `51.97%` | `-0.008135` | fail |
| `veto_any_mf07_stress_cg_risk_on` | selected-short veto | `386` | `+0.000068` | `11.25%` | `+0.001825` | fail |
| `veto_low_corr_cg_risk_off` | selected-short veto | `154` | `+0.000333` | `3.11%` | `+0.031802` | fail |

Interpretation:

- Confirm-style transitions are active enough, but they make SP-K worse.
- Veto-style transitions point in the right direction, but the edge is at-par
  or the selection change is too sparse.
- There is no Stage 0 survivor, so randomized strict falsification is not run.

---

## Decision

`status = failed`

`stage0_survivors = []`

`strict_cleared_variants = []`

`alpha_rerun_allowed = False`

`manifest_ab_allowed = False`

Blocker:

- `no_stage0_positive_mf07_etf_onchain_transition`

This closes the current MF-07 participant-stack reopening. Do not add an MF-07
ETF/on-chain transition to the parent overlay. A future MF-07 reopening needs a
materially different mechanism, not another combination of the same top/global
flags with ETF/whale confirmation.
