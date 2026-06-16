# MF-01 Canonical Parent Alpha Validation

`Snapshot date: 2026-05-03`
`Owner: quant_research_maintainer`
`Status: validated research candidate; not promotable`

---

## Question

Can a new MF-01 orderbook / inventory-transfer short-boundary rule add alpha on
top of the current high-confidence h10d parent:

- `v5_rw_bridge_no_overlay_h10d`

Candidate tested:

- `xs_alpha_ontology_v5_rw_bridge_no_overlay_mf01_combo_replace_v1_h10d`

Mechanism:

- keep the canonical parent long leg and rolling-weight parent score
- search only near the bottom-6 short boundary
- allow at most one short-slot replacement when
  `mf01_short_boundary_combo_score` identifies stronger orderbook fragility
- no SP-K, no event tape, no score overlay, no long-side change

---

## Evidence Artifacts

Primary run:

- `artifacts/quant_research/hypothesis_batches/2026-05-02/families/xs_alpha_ontology_v5_rw_bridge_no_overlay_mf01_combo_replace_v1_h10d/fast_reject_report.json`
- `artifacts/quant_research/hypothesis_batches/2026-05-02/families/xs_alpha_ontology_v5_rw_bridge_no_overlay_mf01_combo_replace_v1_h10d/strict_result.json`
- `artifacts/quant_research/experiments/2026-05-02-xs_alpha_ontology_v5_rw_bridg-e43aae508b46/validation_report.json`
- `artifacts/quant_research/experiments/2026-05-02-xs_alpha_ontology_v5_rw_bridg-e43aae508b46/fixed_set_comparison.md`
- `artifacts/quant_research/experiments/2026-05-02-xs_alpha_ontology_v5_rw_bridg-e43aae508b46/alpha_experiment_card.json`

Independent black-box confidence pass:

- `artifacts/quant_research/factor_reports/2026-05-03-mf01-new-alpha-validation/baseline_alpha_confidence_validation.json`
- `artifacts/quant_research/factor_reports/2026-05-03-mf01-new-alpha-validation/baseline_alpha_confidence_validation.md`

---

## Results

Fast-reject:

- `fast_reject_passed = true`
- `rank_ic_mean = 0.1159`
- `rank_ic_positive_rate = 0.6095`
- `top_minus_bottom_return = 0.0173`
- `walk_forward_median_oos_sharpe = 3.158`
- `loss_window_fraction = 0.34375`
- `worst_regime_median_oos_sharpe = -0.161`

Fixed-set comparison:

| Reference | CumRet diff | Sharpe diff | Win rate | Sign p | P(candidate > reference cumret) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `lsk3_g_v2_h10d` | 1.330 | 0.770 | 0.641 | 0.0328 | 0.999 |
| `v5_h10d` | 1.065 | 0.256 | 0.625 | 0.0599 | 0.972 |
| `v6_h10d` | 1.334 | 0.771 | 0.641 | 0.0328 | 0.998 |
| `v5_rw_bridge_no_overlay_h10d` | 0.248 | 0.174 | 0.519 | 0.8899 | 0.751 |

Black-box path confidence:

- label: `medium_high`
- checks passed: `5/6`
- standalone OOS sum: `1.1828`
- standalone win fraction: `0.6719`
- first-half sum: `0.6249`
- second-half sum: `0.5578`
- top-10 positive share of total sum: `0.683`

The failed black-box check is important:

- paired edge versus the canonical parent does **not** survive dropping the best
  three delta periods
- candidate minus `v5_rw_bridge_no_overlay_h10d` total diff is only `0.0871`
  by simple period-return sum in the independent validator

Strict validation:

- `strict_validation_passed = false`
- `experiment_status = quarantined`
- `statistical_falsification_status = failed`
- blocker codes:
  - `time_shuffle_failed`
  - `label_shuffle_failed`
  - `cost_stress_failed`
  - `symbol_holdout_failed`
  - `liquidity_bucket_consistency_failed`

Alpha experiment card:

- `go_no_go = false`
- blocker codes:
  - `cost_stress_failed`
  - `liquidity_bucket_consistency_failed`
  - `symbol_holdout_failed`

---

## Verdict

MF-01 on the canonical parent is a **real research signal**, but not a validated
new alpha for promotion.

Why it is real enough to keep:

- It passes fast-reject.
- It beats legacy references strongly.
- It improves full-OOS cumulative return and Sharpe versus the current parent.
- It improves worst-regime median OOS Sharpe from roughly `-0.951` to `-0.161`.

Why it is not enough:

- The canonical-parent paired evidence is weak:
  win rate `0.519`, sign-test `p=0.8899`, bootstrap probability only `0.751`.
- The edge does not survive the independent "drop best 3 delta periods" stress.
- Full strict falsification fails on shuffle, cost, symbol-holdout, and
  liquidity-bucket consistency.

Operational decision:

- Do **not** promote `xs_alpha_ontology_v5_rw_bridge_no_overlay_mf01_combo_replace_v1_h10d`.
- Keep MF-01 as a live research lane, but classify this exact candidate as
  `research_only / no_go`.
- The next attempt should narrow the trigger, not broaden it:
  require stronger orderbook fragility plus cost-aware liquidity and symbol
  holdout stability before re-running the canonical-parent fixed-set gate.

---

## Next Candidate Shape

The next MF-01 variant should not be another broad bottom-6 replacement rule.
The failure pattern says the broad rule finds some real periods but is too
fragile across names and liquidity buckets.

Recommended next shape:

- keep canonical parent `v5_rw_bridge_no_overlay_h10d`
- require `boundary_fragile_orderbook_score < 0`
- require `pump_bid_replenishment_failure_score < 0` only as a kicker, not as
  a standalone broad trigger
- restrict replacement to names whose historical cost stress is below the
  parent short being ejected
- require the replacement candidate to pass a symbol-holdout minimum before it
  can enter the short slot

Promotion gate stays unchanged:

- beat `v5_rw_bridge_no_overlay_h10d` in fixed-set paired comparison
- clear statistical falsification
- pass cost stress, symbol holdout, and liquidity-bucket consistency
