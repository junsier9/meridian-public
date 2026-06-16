# M3.1 Options Volume-Shock Veto Falsification Card

`Run date: 2026-05-09`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: failed strict falsification; mechanism evidence only`

---

## Question

The R-8 Stage 0/data gate kept one quarantined market-gate candidate:

`r8_high_option_volume_shock_flag`

The pre-registered landing shape is a parent short-exposure veto/throttle:

> When aggregate BTC/ETH options volume shock is high, does the canonical
> parent short basket rally enough, robustly enough, that short exposure should
> be vetoed?

The answer is **not promotable**. The signal is real enough to preserve as
mechanism evidence, but it fails strict liquidity-bucket consistency.

---

## Artifacts

- evaluator:
  `scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_1_options_volume_shock_veto_falsification.py`
- unit tests:
  `tests/test_quant_m3_1_options_volume_shock_veto_falsification.py`
- primary report:
  `artifacts/quant_research/factor_reports/2026-05-09-m3-1-options-volume-shock-veto-falsification/m3_1_options_volume_shock_veto_falsification.json`
- input sidecar:
  `artifacts/quant_research/coinglass/options_regime_panel_1d.csv.gz`

Test command:

```powershell
python -m pytest tests/test_quant_m3_1_options_volume_shock_veto_falsification.py tests/test_quant_m3_1_options_regime_stage0.py -q
```

Result: `7 passed`.

---

## Observed Edge

The evaluator aligns the market-level options volume-shock flag to the
canonical parent short basket, then computes the parent short basket's next
`10d` return by date.

Positive edge means the selected short names rally more when the gate is active,
so a short-veto would have avoided worse short exposure.

| metric | value |
| --- | ---: |
| total evaluated dates | `1083` |
| active dates | `153` |
| active-date fraction | `14.13%` |
| active next-10d short-basket mean | `+0.0298` |
| inactive next-10d short-basket mean | `-0.0069` |
| active-minus-inactive veto edge | `+0.0366` |

---

## Strict Tests

| test | status | key evidence |
| --- | --- | --- |
| observed Stage 0 contract | pass | `+0.0366` edge, `153` active dates |
| +1d delayed activation | pass | edge `+0.0322`, retention `87.85%` |
| contiguous era split | pass | era edges `+0.0367`, `+0.0687`, `+0.0089` |
| symbol holdout | pass | minimum holdout edge `+0.0309`, positive fraction `100%` |
| active-date time shuffle | pass | random q95 `+0.0185`, empirical p `0.0010` |
| return-date shuffle | pass | random q95 `+0.0196`, empirical p `0.0020` |
| liquidity-bucket consistency | **fail** | tail-liquidity edge `-0.0199` |

Liquidity detail:

| bucket | active dates | subject count | edge | status |
| --- | ---: | ---: | ---: | --- |
| `top_liquidity` | `149` | `13` | `+0.0378` | pass |
| `mid_liquidity` | `111` | `3` | `+0.0547` | pass |
| `tail_liquidity` | `12` | `1` | `-0.0199` | fail |

The tail bucket is small, but it is still eligible under the pre-registered
bucket minimums (`10` active dates and `10` inactive dates). Strict promotion
therefore fails closed.

---

## Decision

`status = failed`

`alpha_rerun_allowed = False`

`manifest_ab_allowed = False`

`strict_cleared_variants = []`

Blocker:

- `liquidity_bucket_consistency_failed`

Keep `r8_high_option_volume_shock_flag` as quarantined mechanism evidence. Do
not add it as a parent overlay or manifest A/B. A future R-8 reopening must
either prove a liquidity-aware throttle that explicitly excludes tail exposure
before testing, or bring a richer PIT options surface that can define a
cross-sectional options exposure rather than a broad market gate.
