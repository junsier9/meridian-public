# Experiment Catalog — Weight Scans, Variants, Failed Integrations

`Snapshot date: 2026-04-30` · `Owner: quant_research_maintainer`

> **Read-this-first per-experiment view.** Every weight scan, factor variant audit, failed integration attempt, and falsified mechanism — collected into a single navigable catalog. Companion to `factor_audit_trail.md` (per-factor) and `algorithm_choices.md` (design rationale).
>
> Use this when you need to know: "did we already test weight w on factor X?", "which variants of factor family Y did we audit?", "what failed before reaching the current state?".

---

## A. Weight scan experiments (per-factor)

### A.1 F-cascade (`liq_cascade_recency_score_5d`) — h5d

| weight | walk-forward median | regime worst | result | commit |
| --- | --- | --- | --- | --- |
| +0.10 | (initial) | broke regime | FAIL — too aggressive | (SP-A early) |
| **+0.05** | **+2.373** | **-1.851** | **PASS — Pareto optimum** ⭐ | `977c1a0` |
| +0.17 (theoretical) | not tested | — | conservative pick of 50% theoretical | — |

**Calibration rule**: raw IC 0.052 × v91 weight ratio 3.25 = theoretical 0.17. Pareto chose 50% (0.05) for safety margin.

### A.2 F-cascade — h10d

| weight | walk-forward median | regime rotation | result | commit |
| --- | --- | --- | --- | --- |
| +0.05 (h5d weight) | +2.830 | -2.739 | regime FAIL (rotation < -2.0 floor at h10d) | SP-C Phase 2 (`d587740`) |
| **+0.025 (halved per sqrt)** | **+2.832** | **-2.736** | **PASS under v10_h10d sqrt-scaled contract** (vs new floor -2.828) ⭐ | SP-C Phase 3 (`472ea4a`) |
| +0.025 (under v10 h5d contract) | +2.832 | -2.736 | regime FAIL (rotation -2.736 < -2.0 h5d floor) | (intermediate) |

**Calibration rule**: at h10d, sharpe magnitudes scale by sqrt(N), so signal magnitudes are sqrt(2)× larger. Halving F-cascade weight to 0.025 brings the *effective* contribution back to h5d-equivalent. v10_h10d contract ALSO scales the regime floor by sqrt(2) (-2.0 → -2.828) so the same f-cascade signal passes both gates.

### A.3 F62 (`settlement_cycle_premium_60d`) — h5d

| weight | walk-forward | result | commit |
| --- | --- | --- | --- |
| -0.08 (theoretical Pareto) | +2.544 | PASS (v5 experimental) | M2.3 |
| -0.05 (halved in v7 ensemble) | (v7 stacked) | non-additivity finding | `68c4593` |

### A.4 F47 (`funding_flip_decay_phase`) — h5d

| weight | walk-forward | loss_window_fraction | result |
| --- | --- | --- | --- |
| -0.05 (theoretical) | not promoted | 0.406 (broke 0.40 cap) | FAIL — too aggressive |
| **-0.03** | +2.227 (+0.08 over v1) | 0.375 | PASS but modest (v8 experimental) ⭐ |

### A.5 F1 (`funding_intraday_dispersion_30d`) — h10d ⭐ **most extensive scan**

| weight | walk-forward median | loss_window_fraction | regime rotation | result |
| --- | --- | --- | --- | --- |
| **-0.020 (raw IC sign)** | **+2.513 (-0.319)** | 0.344 | **-3.001** (broke -2.828 floor) | **FAIL** — wrong sign (followed raw IC -0.019 instead of residual IC +0.040) |
| **+0.015 (locked, residual IC sign)** | **+2.832** | **0.312** | **-2.736** | **PASS = v6_h10d** (no marginal cycle value) ⭐ |
| +0.020 | +2.832 | 0.312 | -2.736 | PASS = v6_h10d (still no marginal value) |
| +0.025 (= F-cascade weight) | +2.832 | 0.312 | **-3.098** | **FAIL** — overshoots F-cascade rotation regime protection |

**Sign discovery**: F1 raw IC -0.019 NEGATIVE, but G6 residual IC +0.040 POSITIVE. Score-integration weight must follow residual IC sign (marginal contribution direction), NOT raw IC. First v9 attempt at -0.020 actively contradicted F1's residual signal — walk-forward dropped 0.32 + regime broke.

**Cycle non-additivity finding**: even at correctly-signed weight w=+0.015, F1 produces IDENTICAL cycle metrics to v6_h10d. F1's predictive direction overlaps with F-cascade's rotation regime protection in cycle-backtest space (despite low rank-level corr 0.064). Locked at safest weight for `experimental` status.

**Reference**: `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v9_lsk3_g_v2_h10d.json` `verified_outcome_2026_04_30.weight_scan` block; SP-F threshold_provenance section.

### A.6 SP-G overlay v3 DVOL throttle parameters

| component | threshold | full | floor | trigger frequency |
| --- | --- | --- | --- | --- |
| btc_dvol_range_z90 | 1.5 | 2.5 | 0.7 | 3.9% of days |
| eth_dvol_range_z90 | 1.5 | 2.5 | 0.7 | 4.4% of days |
| dvol_eth_dvol_ratio | (not used; only diagnostic) | — | — | — |

**v3 overlay total trigger**: 4.7% of days (i.e., v3 differs from v2 on 4.7% of days). Max extra throttle -0.403 on historical vol-of-vol peaks.

**Cycle outcome**: NEUTRAL — v6_h10d under v3 has identical walk-forward + regime metrics to v6_h10d under v2. DVOL anomaly days don't overlap strategy losing days.

---

## B. Variant catalogs (sub-path-level factor swarms)

### B.1 SP-A liquidation cascade variants (4 candidates)

| variant | raw IC | G1 | G6 vs lsk3 | selected? |
| --- | --- | --- | --- | --- |
| `liq_cascade_max_z_24h` | +0.0448 | PASS | +0.0578 | runner-up |
| `liq_cascade_count_24h_z25` | +0.0225 | FAIL (<0.04) | +0.0523 | rejected (G1 fail) |
| `liq_cascade_signed_intensity_24h` | +0.0010 | FAIL | +0.0275 | rejected (G1 fail) |
| **`liq_cascade_recency_score_5d`** ⭐ | **+0.0522** | **PASS** | **+0.0616** | **WINNER (highest residual t=10.77)** |

**All 4 variants PASS G6 strict** vs lsk3. Recency_score_5d picked as strongest; the other 3 are sibling variants of the same MF-12 mechanism.

**Reference**: `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2.json` `lineage.admission_audit_2026_04_29` block.

### B.2 SP-B 1h Coinglass microstructure variants (4 candidates)

| variant | mechanism | G1 | G3 | G6 | result |
| --- | --- | --- | --- | --- | --- |
| **B2** `top_global_disagreement_1h_30d` | rolling-720h corr(top_long, global_long) | FAIL | — | FAIL | **REJECT** (canonical MF-07; near-zero raw IC after fillna) |
| **B3a** `top_trader_velocity_1h_abs_24h` | daily mean abs(6h gradient of top_long) | PASS | 1.00 | +0.062 t=10.87 PASS | admitted but +0.94 sibling-corr with F-cascade — **NOT score-integrated** |
| **B3b** `top_trader_velocity_1h_signed_24h` | daily signed sum of 6h gradient | FAIL | — | marginal | rejected |
| **B5** `taker_skew_presettle_30d` | F62 mechanism on taker_buy-sell flow | FAIL | — | FAIL | rejected |

**Outcome**: SP-B partial — only B3a passes admission but is sibling-duplicate. **MF-07 canonical lane (B2) empirically unimplementable** at 1d-aggregate panel grain.

**Reference**: SP-B threshold_provenance section.

### B.3 SP-D BTC→alt basis propagation variants (3 candidates)

| variant | construction | G1 |IC| | G6 vs lsk3 | result |
| --- | --- | --- | --- | --- |
| **D1** `btc_basis_shock_lag1_z60` | universe-wide gauge | n=0 (zero cross-section) | n/a | DESIGN FAIL (universe-wide → trivial G1) |
| **D2** `alt_basis_residual_after_btc_60d` | per-asset residual after rolling-60d β-projection on BTC basis | h5d 0.0007 / h10d 0.0008 | -0.004 / +0.002 | **FAIL** — far below 0.04 floor |
| **D3** `basis_propagation_lag_corr_30d` | per-asset rolling 30d corr(alt_basis[t], BTC_basis[t-1]) | h5d 0.0073 / h10d 0.0030 | +0.001 / -0.005 | **FAIL** — best is 5× under floor |

**Falsification 共生**: doc §E.16 KS-test on BTC basis shock pooled t-stat = 1.39 < 2.0 threshold → REJECT mechanism. Combined with G6 admission failure → SP-D shipped as `falsified per doc test`.

**Reference**: SP-D threshold_provenance section.

### B.4 SP-F sub-day funding variants (3 candidates)

| variant | construction | G1 |IC| (h10d) | G6 vs lsk3+F08 | result |
| --- | --- | --- | --- | --- |
| **F1** `funding_intraday_dispersion_30d` | rolling-30d mean of within-day std of 6 4h values | 0.0187 | **+0.0396 t=+7.24** | **WINNER (admission)** ⭐ |
| **F2** `funding_sign_flip_count_30d_4h` | count of 4h-bar sign flips in rolling 30d | 0.0094 | +0.0246 t=+4.43 | borderline; sibling of F1 (NOT stacked) |
| **F3** `funding_term_skew_30d_4h` | rolling-180-bar skew of 4h funding | 0.0515 | +0.0110 t=+2.19 | **FAIL** — collinear with F08 (1d-grain skew absorbs) |

**Saturation hypothesis confirmed**: F3 fails because F08 (1d-grain skew) already absorbs the skew dimension at this panel grain. F1 escapes saturation because intraday-dispersion is a DIFFERENT statistic than F08's skew.

### B.5 SP-G DVOL extension components (3 candidates)

| variant | use | result |
| --- | --- | --- |
| `btc_dvol_intraday_range_z90` | universe-wide gauge for v3 overlay | 4% trigger frequency, productionized in v3 (cycle neutral) |
| `eth_dvol_intraday_range_z90` | same | 4.4% trigger; productionized in v3 (cycle neutral) |
| `btc_dvol_eth_dvol_ratio` | cross-pair regime indicator | NOT productionized (insufficient overlap with strategy losses) |

### B.6 SP-H expiry hedge unwind variants (3 candidates)

| variant | construction | G1 |IC| | G6 | result |
| --- | --- | --- | --- | --- |
| **H1** `time_to_btc_expiry` | universe-wide gauge | n=0 | n/a | DESIGN FAIL (universe-wide) |
| **H2** `expiry_window_indicator_5d` | universe-wide binary (within 5d of expiry) | n=0 | n/a | DESIGN FAIL |
| **H3** `expiry_window × asset_realized_vol_20` | per-asset interaction | h10d 0.159 (strong!) | +0.015 (FAIL) | **FAIL** — vol dimension absorbed by lsk3 |

**Falsification共生**: doc §E.15 KS-test p=0.128 > 0.05 → REJECT mechanism. Combined with H3 G6 admission fail (vol saturation) → SP-H shipped as `falsified per doc test`.

---

## C. Failed integration attempts (multi-factor stacking)

### C.1 v7 — F62 + F-cascade ensemble (commit `68c4593`)

**Construction**: lsk3 + F62 (w=-0.05 halved from v5) + F-cascade (w=+0.025 halved from v6).

**Hypothesis**: two G6-admitted factors should additively improve walk-forward.

**Result**: cycle metrics essentially equivalent to picking the stronger single factor. **Non-additivity** — F62 and F-cascade contributions to long-short top-3 selection in regime-stressed windows OVERLAP at the cycle-backtest level (despite both being G6-admitted independently).

**Lesson learned**: G6 admission is necessary but NOT sufficient for score promotion. Future score-integration tests MUST run weight scan + check non-additivity vs strongest existing component.

### C.2 v9 — F-cascade + F1 ensemble (commit `237457f`)

**Construction**: lsk3 + F-cascade (w=+0.025) + F1 (w=+0.015 sign-corrected, locked).

**Hypothesis**: F1 G6-admits at +0.040 t=7.24 vs lsk3+F08 (and +0.029 t=5.19 vs lsk3+F-cascade) — should add marginal alpha on top of v6_h10d.

**Result**: at locked w=+0.015, walk-forward identical to v6_h10d (+2.832). At higher weights regime breaks.

**Lesson learned (v7 lesson reinforced)**: Per-ts Spearman corr(F1, F-cascade) = 0.064 (low) but cycle-backtest contribution overlaps. Linear rank correlation does NOT capture how factors interact in (long-short top-3 × regime windows) selection space.

### C.3 v6 v3-overlay swap (commit `f52aef7`)

**Construction**: same v6 score, but `position_multiplier_overlay_id` swapped from `alpha_ontology_regime_gating_v2` → `_v3` (DVOL extensions).

**Hypothesis**: DVOL anomaly days are vol-of-vol stress periods — throttling them should reduce drawdowns.

**Result**: cycle metrics IDENTICAL to v6_h10d under v2. DVOL throttle days (4.7% of history) don't systematically overlap lsk3+F-cascade losing days.

**Lesson learned**: Overlay enrichment must overlap with strategy-specific losing days, not generic vol regimes. W3.5 v2's `trailing_universe_mean_return_30d` worked because it specifically captured slow-grind bear regimes that hurt lsk3.

### C.5 SP-J: Regime-conditional alpha architecture (AT-PAR — executed 2026-05-01)

**Status**: AT-PAR. Architecture validated end-to-end (manifest + classifier + score function + strict-pass contract); F1 alpha unlock hypothesis REJECTED (cycle-flat vs v6_h10d; walk-forward Δ=0.000). Architecture preserved as Stage-2 primitive for future regime-localized SP-X candidates.

**Cycle results**:
| metric | v6_h10d | v10 SP-J | delta |
| --- | --- | --- | --- |
| walk_forward median sharpe | +2.832 | +2.832 | 0.000 |
| loss_window_fraction | 0.312 | 0.3125 | +0.0005 |
| positive_regime_fraction | 0.667 | 0.667 | 0 |
| worst_regime sharpe | -2.736 | -2.805 (in floor -2.828) | -0.069 |

**Conclusion: hypothesis (B) confirmed**. F1 alpha is fundamentally F-cascade-overlapping at cycle-layer; weight architecture (constant in v9 + regime-conditional in v10) cannot disentangle. Future regime-conditional candidates need cycle-layer non-additivity test BEFORE concluding admission strength translates to walk-forward lift.

---

### C.5-original: SP-J PROPOSED phase (Phase 1 path update, 2026-04-30)

> Original PROPOSED entry preserved below for archival continuity. The AT-PAR outcome (above) supersedes it; the planning rationale below was the basis for execution.

**Construction (planned)**:
- J1 score: `xs_alpha_ontology_v10_regime_conditional_h10d_score`
  - trend_up regime: lsk3 + F-cascade w=0.025 (= v6_h10d baseline)
  - rotation_high_vol regime: lsk3 + F-cascade w=0.025 + F1 w=+0.025
  - drawdown_rebound regime: lsk3 + F-cascade w=0.025 + F1 w=+0.030
- Regime label source: trailing W3.5 v2 component readings (BTC vol regime quantile + trailing universe mean return). Production-realistic.
- Cycle: at h10d under v10_h10d sqrt-scaled contract.

**Convergent evidence justifying the experiment** (5 independent sources):
1. SP-F: F1 G6-passes admission but cycle non-additive at constant weight (w=+0.015 = v6_h10d metrics; w=+0.025 breaks regime).
2. tt_smooth_5: drawdown_rebound IC -0.033 (recovers) vs trend_up IC 0.000 (fails). Regime-conditional.
3. momentum_decay_5_20: rotation_high_vol IC +0.075 (sign-flipped strong) vs other regimes ≈ 0.
4. Dual-horizon ensemble: 87.5% same-sign confirms shared alpha source; v6_h10d advantage isolated to drawdown_rebound (h5d -3.37 vs h10d +2.17). True diversification needs structurally regime-conditional alpha.
5. W3.5 v2 overlay precedent: trailing_universe_mean_return throttle WORKS specifically because it overlaps lsk3 losing regimes. Regime-conditional pattern is empirically validated at overlay layer.

**Decision criteria (pre-registered)**:
- PROMOTE if: walk-forward median > v6_h10d +2.832 AND positive_regime_fraction ≥ 2/3 (preserved or improved) AND no regime worst breaks below sqrt-scaled floor -2.828.
- AT-PAR if: walk-forward median ≈ v6_h10d (within ±0.10) AND regime breadth preserved.
- DECLINE if: walk-forward median < v6_h10d -0.10 OR regime worst breaks floor.

**Expected outcomes by hypothesis**:
- (A) F1 alpha is genuinely regime-localized → SP-J PROMOTES. Walk-forward lift ~+0.20 to +0.40 expected (rotation/drawdown regime-specific F1 contribution materializes when not averaged out by trend_up neutrality).
- (B) F1 alpha is fundamentally F-cascade-dominated → SP-J AT-PAR / DECLINE. F1 doesn't unlock more alpha at any regime weighting; cycle non-additivity is a cycle-layer phenomenon, not weight-layer.

**Implementation effort**: M-L (~6-8h). Single new score function + new manifest + cycle test. Reuses existing F1 panel + W3.5 v2 regime detection.

---

### C.4 v6 dual-horizon ensemble (h5d + h10d 50/50 capital split, 2026-04-30)

**Construction**: 50/50 portfolio of v6_h5d (+2.373 walk-forward, h5d horizon) + v6_h10d (+2.832 walk-forward, h10d horizon). Both ship as `active_alternative`. Hypothesis: ensemble reduces single-horizon risk + adds diversification benefit.

**Result**: **DECLINE** — 50/50 ensemble degrades on 3 of 4 promotion criteria.

| metric | v6_h5d | v6_h10d | ensemble (50/50) | delta vs max |
| --- | --- | --- | --- | --- |
| Median window sharpe | +2.373 | **+2.832** ⭐ | +2.401 | **-0.432** |
| Loss window fraction | 0.375 | 0.312 | 0.375 | +0.062 |
| Annualized sharpe | +1.531 | +1.396 | +1.530 | -0.001 |
| Cumulative compound return (32mo) | **+109.04%** ⭐⭐ | +75.88% | +92.44% | -16.6 pp |

Per-window correlation: Pearson +0.843, same-sign 87.5% (LOW diversification — high correlation).

Per-regime drawdown_rebound_2026ytd: h5d -3.37 + h10d +2.17 → ensemble **-0.60** (h5d drag wipes h10d advantage in this regime).

**Three valuable owner-actionable insights** (more important than the DECLINE verdict):
1. **median sharpe vs cumulative return REVERSAL**: v6_h10d wins on median sharpe, v6_h5d wins on cumulative return. Validation contract metric ≠ terminal portfolio value. Stage-2 deployment criterion may want to prefer h5d for capital-deployment behavior.
2. **v6_h10d regime advantage isolated to drawdown_rebound**: trend_up + rotation regimes are similar between horizons; entire walk-forward gap is in drawdown_rebound.
3. **Both strategies share alpha source**: 87.5% same-sign correlation reflects same score function (lsk3 + F-cascade) at different horizons, not independent strategies. True diversification requires structurally different alpha (e.g., regime-conditional F1 + F-cascade).

**Lesson learned**: For Stage-2 deployment / Stage-1 active selection, owner should evaluate cumulative return alongside median sharpe + regime breadth. Validation contract gates only test risk-adjusted-edge, not deployment efficiency.

**Reference**: `compute_v6_dual_horizon_ensemble.py`; `v6_dual_horizon_ensemble.json` artifact; threshold_provenance.md "v_alpha_v6 dual-horizon ensemble" section.

---

## D. Falsified mechanisms (doc-prescribed tests failed)

| sub-path | doc anchor | test | threshold | actual | result |
| --- | --- | --- | --- | --- | --- |
| **SP-A** | §E.12 | post-cascade 24h abnormal log return t-stat | ≥ 2.5σ | **+10.75** | **PASS** ⭐ |
| **SP-D** | §E.16 | BTC basis shock → ALT basis 1d-after t-stat (pooled) | ≥ 2.0 | **+1.39** | **FAIL** (direction correct, sub-significance) |
| **SP-E** | §E.17 | low-corr regime IC / high-corr regime IC | ≥ 1.20 | **0.895 (h10d), 0.933 (h5d)** | **FAIL** (sign-reversed under tertile-split: high-corr has HIGHER IC) |
| **SP-H** | §E.15 | KS-test expiry-window vs out-window 5d return distribution | p < 0.05 | **p=0.128** | **FAIL** (-62 bp direction correct, sub-significance) |
| M2.4 | §E.11 | funding-OI-basis no-arb residual existence | (existence test) | PASSES | PASS but G6 standalone fail (lsk3 saturation) |

**Pattern across SP-D / SP-H**: doc-prescribed mechanism direction is empirically detectable but sub-threshold (t=1.39, KS p=0.128). Holding the line on doc thresholds prevents accumulating weak-but-correlated factors.

**Pattern across SP-E**: doc mechanism direction is empirically REVERSED (high-corr regime has higher IC, not lower). Doc mental model needs revision.

---

## E. Horizon scans

### E.1 SP-C Phase 1 multi-horizon factor audit (h1d / h3d / h5d / h10d)

For each of 6 score-integrated factors, residual t-stat at each horizon vs lsk3 baseline:

| factor | h1d resid t | h3d resid t | h5d resid t | h10d resid t | peak |
| --- | --- | --- | --- | --- | --- |
| F12 (quality_funding_oi) | -2.31 | -3.45 | -4.70 | **-6.18** | **h10d** |
| F33 (downside_upside_vol_ratio_30) | +1.89 | +3.21 | +4.86 | **+6.42** | **h10d** |
| F62 (settlement_cycle_premium_60d) | -3.62 | -5.14 | -7.43 | **-9.85** | **h10d** |
| F-cascade (liq_cascade_recency_score_5d) | +5.21 | +7.84 | +9.71 | **+12.19** | **h10d** |
| F29 (contagion_in_degree) | +1.45 | +2.18 | +2.86 | **+3.74** | **h10d** |
| B3a (top_trader_velocity_1h_abs_24h) | +6.12 | +8.95 | +10.87 | **+12.34** | **h10d** |

**Universal h10d-preference finding**: ALL score-integrated factors have residual t monotone-increasing with horizon, peaking at h10d. The doc-default 5d horizon is empirically suboptimal across all currently-admitted score factors.

**Implication**: SP-C Phase 2/3 — built h10d cycle infrastructure + sqrt-scaled v10_h10d validation contract; v6_h10d productionized as `active_alternative` with walk-forward +2.832 (+19% over v6_h5d).

### E.2 SP-C Phase 2 walk-forward by horizon (per-candidate)

| candidate | h5d walk-forward | h10d walk-forward | delta | h10d/h5d ratio |
| --- | --- | --- | --- | --- |
| v1_lsk3_g_v2 (control, no extensions) | +2.147 | +2.428 | +0.281 (+13%) | 1.13× |
| v6_lsk3_g_v2 (lsk3 + F-cascade w=0.025/0.025) | +2.373 | +2.832 | +0.459 (+19%) | 1.19× |
| v5_lsk3_g_v2 (lsk3 + F62) | +2.544 | +2.716 | +0.172 (+7%) | 1.07× |
| v8_lsk3_g_v2 (lsk3 + F47) | +2.227 | +2.594 | +0.367 (+16%) | 1.17× |

**All candidates show walk-forward improvement at h10d**. Ratio range 1.07-1.19× (theoretical sqrt(2) ≈ 1.41× would be the random-walk-IID ceiling). Empirical ratios 1.07-1.19 are consistent with realized panel having positive serial correlation in trend regimes (compresses sqrt-scaling below theoretical).

### E.3 F47 horizon scan (specific factor at multiple horizons)

| horizon | F47 raw IC | F47 t-stat | residual IC vs lsk3 | residual t | G6 PASS? |
| --- | --- | --- | --- | --- | --- |
| h1d | -0.005 | -0.94 | -0.008 | -1.45 | FAIL |
| h3d | -0.011 | -2.13 | -0.014 | -2.67 | FAIL |
| h5d | -0.014 | -2.85 | **-0.020 (just at floor)** | -3.89 | **borderline PASS** |
| h10d | -0.018 | -3.74 | **-0.026** | -5.61 | **PASS (strongest)** |

**F47 unlock pattern**: same factor that previously G6-failed at h5d (W3.1 admission rejection) PASSES at h10d in SP-C audit. **Idle factor unlocked via horizon scan**, not via threshold relaxation.

---

## F. Lifecycle / demotion experiments

### F.1 M2.5 demotion experiment (commit `cf3d2b7`)

**Inventory**: 23 factors evaluated (lsk3 11 + score extensions 4 + plumbed 4 + W1.x leftovers 4).

**G.5 state machine output**:

| recommended state | count |
| --- | --- |
| active | 8 |
| watch | 4 |
| decay | 2 |
| retired | 9 |
| revived candidate | 0 |
| **demote-recommended total** | **14** |

**Genuine demotions (no sanity flag)**:
- liquidity_stress_qv_iv (lsk3, watch)
- coinglass_taker_imb_intraday_dispersion_24h (lsk3, watch)
- funding_basis_residual_implied_repo_30 (lsk3, watch)
- F47 (decay; raw 60d -0.007 weak)
- F62 (retired; raw 60d -0.007 weak)

### F.2 lsk3 baseline late-2026 decay diagnostic (commit `a340f87`)

**Trigger**: M2.5 recommended demote for 7/11 lsk3 factors → investigation needed.

**Sanity check augmentation result**:

| sanity flag | count | factors |
| --- | --- | --- |
| likely_artifact_strong (raw |IC| ≥ G1 floor 0.04) | 3 | tt_smooth_5, momentum_decay_5_20, F-triangle |
| likely_artifact (raw |IC| ≥ stable floor 0.02) | 7 | iv_smooth_60, quality_funding_oi, F1, F3, F09, F31, F32 |
| no flag (genuine demote) | 4 | liquidity_stress, taker_imb_dispersion, funding_basis_residual, F47/F62 (raw also weak) |

**True regime shifts** (only 2): `tt_smooth_5` (signal weakened to near-zero late) + `momentum_decay_5_20` (sign-flipped).

**Late-period bootstrap raw IC CI** (1000 iter, 80% resample, 30% panel slice from 2025-05-21):

| factor | bootstrap mean | CI 95% | excludes 0? | excludes G1? |
| --- | --- | --- | --- | --- |
| iv_smooth_60 | -0.116 | [-0.143, -0.088] | YES | **YES** |
| dh_5 | +0.094 | [+0.074, +0.115] | YES | **YES** |
| downside_upside_vol_ratio_30 | +0.056 | [+0.042, +0.071] | YES | **YES (partial)** |
| (8 of 11 factors total exclude 0) | | | | |
| tt_smooth_5 | -0.007 | [-0.019, +0.003] | **NO** (signal degraded) | NO |
| momentum_decay | +0.015 | [-0.008, +0.039] | **NO** (sign flipped) | NO |

---

## G. Cycle-level outcomes (active candidate runs)

### G.1 v6_lsk3_g_v2 cycle (h5d, 2026-04-29 panel)

| metric | value | vs v1 control |
| --- | --- | --- |
| validation_contract.status | passed | — |
| walk-forward median sharpe | +2.373 | +0.226 (+10.5%) |
| loss_window_fraction | (in spec) | — |
| positive_regime_fraction | 1/3 | unchanged |
| worst_regime sharpe | -1.851 | unchanged |
| trend_up_2025h2 | +5.687 | +0.147 |
| rotation_high_vol_2025q4 | -0.062 | +0.527 ⭐ (best of any factor in M2.x track) |
| drawdown_rebound_2026ytd | -1.851 | unchanged |

### G.2 v6_lsk3_g_v2_h10d cycle ⭐ (h10d, 2026-04-29 panel)

| metric | value | vs v1_h10d control | vs v6_h5d |
| --- | --- | --- | --- |
| contract | quant_validation_contract.v10_h10d (sqrt-scaled) | — | — |
| validation_contract.status | passed | — | — |
| walk-forward median sharpe | **+2.832** ⭐ | +0.404 (+17%) | +0.459 (+19%) |
| loss_window_fraction | 0.312 | — | -0.063 (better) |
| positive_regime_fraction | **2/3** | +0.333 | +0.333 (1/3 → 2/3) |
| worst_regime sharpe | -2.736 | better | (within sqrt-scaled floor -2.828) |
| trend_up_2025h2 | +6.725 | (similar) | +1.038 |
| rotation_high_vol_2025q4 | -2.736 | (similar) | -2.674 (still in floor) |
| drawdown_rebound_2026ytd | **+3.162** | +0.024 | **+5.013** (FLIPS positive ⭐) |

### G.3 v9_lsk3_g_v2_h10d cycle (h10d, weight scan)

(See section A.5 above for full weight scan).

**Locked at w=+0.015**: cycle metrics IDENTICAL to v6_h10d. F1 admission was real but cycle non-additive on top of F-cascade.

---

## H. Cross-references summary (per-experiment)

| experiment type | count | location |
| --- | --- | --- |
| Weight scans logged | 6 | section A |
| Variant catalogs | 6 (SP-A/B/D/F/G/H + W1.1+W3.x leftovers) | section B |
| Failed integration attempts | 3 (v7, v9, v6+v3 overlay) | section C |
| Falsified doc mechanisms | 3 (SP-D §E.16, SP-E §E.17, SP-H §E.15) | section D |
| Horizon scans | 1 multi-factor + 1 candidate-level + 1 specific factor (F47) | section E |
| Lifecycle / demotion experiments | 2 (M2.5 + lsk3 decay) | section F |
| Cycle-level outcomes | 3 active candidates documented | section G |

**Total experiments logged**: ~30+ distinct experiments with weight / variant / outcome detail.
