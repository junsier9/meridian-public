# Algorithm Choices — Design Decision Rationale

`Snapshot date: 2026-04-30` · `Owner: quant_research_maintainer`

> **Architecture Decision Records (ADR) for quant research**. Every non-obvious design choice — admission thresholds, weight calibration rules, score architecture, lifecycle management, scaling rules — gets a short card here with **Context / Decision / Rationale / Status / References**. The goal: when you ask "why this number?" or "why this approach?", the answer is one click away instead of grep-and-pray.
>
> Companion docs:
> - `factor_audit_trail.md` — per-factor index
> - `experiment_catalog.md` — weight scans + failed attempts
> - `threshold_provenance.md` — chronological audit lineage
> - `alpha_ontology_and_factor_library.md` — mechanism families + 90-day plan

---

## A. Admission framework

### ADR-A1: 11-gate admission framework (G1-G11)

- **Context**: How do we decide whether a new factor is worth integrating into a score? Pure IC > threshold is too loose (cheap factors with high noise pass). Need multi-dimensional admission.
- **Decision**: Adopt the 11-gate G1-G11 admission framework per doc §G.2. Implementation in `src/enhengclaw/quant_research/feature_admission_v2.py`.
- **Rationale**: covers IC magnitude (G1), IC stability (G2), regime consistency (G3), concentration risk (G4), VIF (G5), residual orthogonality (G6), turnover (G7), capacity-aware IC (G8), crowding (G9), out-of-universe robustness (G10), and falsification declaration (G11). 11 gates ensure that admitted factors aren't just IC-strong but also stable, capacity-aware, and uncorrelated with public factors.
- **Status**: active (since 2026-04). Used by `feature_admission_v2.evaluate_admission_v2`.
- **References**: `factor_admission_v2.py`, `factor_report_card.py`, doc §G.2.

### ADR-A2: G1 |IC| threshold = 0.04

- **Context**: Per-timestamp rank IC magnitude floor for G1 admission.
- **Decision**: |raw IC| ≥ 0.04 strict-pass.
- **Rationale**: Empirically calibrated against v83 phase-0 baseline factors. 0.04 is the magnitude at which a factor's t-stat becomes ≥ 4 over typical 700-1100 ts panel — strong-enough that downstream G6 residual is likely meaningful. Lower thresholds (0.02) admit too many "noise factors" whose residual IC just reflects measurement noise.
- **Status**: active. Used in factor_lifecycle.py raw-IC sanity check (`RAW_IC_SANITY_STRONG_FLOOR`).
- **References**: `feature_admission_v2_contract.json`; doc §G.2 G1 spec.

### ADR-A3: G6 residual IC threshold = 0.02

- **Context**: Residual IC (factor orthogonalized against admitted baseline) magnitude floor for G6 admission.
- **Decision**: |residual IC| ≥ 0.02 PASS.
- **Rationale**: 0.02 is half of G1 floor 0.04 — captures the marginal-contribution intuition that a new factor needs at least 50% of standalone strength to add value beyond the baseline. Below 0.02, the residual is mostly noise + shared-signal projection.
- **Status**: active. Used in M2.5 demotion experiment + lifecycle state machine watch trigger.
- **Caveat (2026-04-30 finding)**: when baseline has high internal correlation (e.g., `iv_smooth_60` ↔ `dh_60` corr -0.522), residual IC can produce systematic false-positive demotion. Mitigation: `factor_lifecycle.assess_raw_ic_sanity_check` augments G.5 verdict with raw-IC cross-check.
- **References**: doc §G.2 G6; `factor_lifecycle.py`; lsk3 baseline late-2026 decay diagnostic.

### ADR-A4: G3 same-sign fraction threshold = 0.60

- **Context**: Cross-regime IC sign consistency floor for G3 admission. Regimes = vol tertiles (low / mid / high BTC realized vol).
- **Decision**: max(positive_regime_count, negative_regime_count) / 3 ≥ 0.60 (i.e., at least 2 of 3 regimes share sign).
- **Rationale**: 0.60 = 2/3, ensures factor isn't a single-regime artifact. Balanced against 1.0 (perfect consistency) which would over-reject — most legitimate factors have noise within one regime.
- **Status**: active.
- **References**: `feature_admission_v2.py` `gate_g3_regime_consistency`.

---

## B. Weight calibration rules

### ADR-B1: New score factor weight = 50% of theoretical Pareto-optimum

- **Context**: When integrating a new factor F into score with raw IC = ic_F, what weight w to use?
- **Decision**: Initial pick = 50% of theoretical Pareto: `w_initial = 0.5 × ic_F × (lsk3_baseline_ratio)`. lsk3 ratio is empirically ~3.25 (sum of |w_i| / mean |IC_i| in lsk3 = ~0.07/0.022 ≈ 3.18, typically rounded to 3.25). Then run cycle and tune.
- **Rationale**: 100% Pareto-optimal weight tends to overshoot regime gates (v6 initial w=0.10 broke regime; F47 initial -0.05 broke loss_window_fraction). 50% = safe starting point that preserves regime margin while capturing most alpha.
- **Status**: active. Applied to F-cascade (raw IC 0.052 → theoretical 0.17 → conservative 0.05), F47 (-0.014 → -0.05 → -0.03 final), F1 (residual 0.040 → 0.02 → 0.015 final after sign correction).
- **References**: `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2.json` `weight_calibration` block; experiment_catalog.md §A.

### ADR-B2: New factor weight signed by RESIDUAL IC, not raw IC (when they differ)

- **Context**: SP-F discovered a textbook over-correction case: F1 raw IC = -0.019 (negative) but G6 residual IC = +0.040 (positive vs lsk3+F08; +0.029 vs lsk3+F-cascade). What sign for w_F1?
- **Decision**: Score-integration weight sign = **sign(residual IC)**, NOT sign(raw IC). For F1: w = +0.015 (positive), not -0.020.
- **Rationale**: When baseline over-projects in factor F's direction, residual signal flips sign relative to raw. The marginal contribution to score IC = w × residual_IC (because lsk3+F08 already captures the raw direction). For w × residual_IC > 0, w must match residual sign.
- **Empirical validation**: SP-F first attempt at w=-0.020 (raw sign) → walk-forward dropped 0.32 + regime broke. Sign-corrected to w=+0.015 → metrics restored to v6_h10d level.
- **Status**: active rule. New score-integration tests must check residual IC sign separately from raw.
- **References**: SP-F threshold_provenance section; v9 manifest `weight_scan` block; experiment_catalog.md §A.5.

### ADR-B3: Horizon scaling — sharpe-magnitude weights halve under sqrt(N) scaling

- **Context**: F-cascade weight at h5d is +0.05. At h10d, what weight?
- **Decision**: Halve the weight: w_h10d = w_h5d × (1 / sqrt(2)) ≈ w_h5d / 1.41 ≈ w_h5d × 0.71. Empirically rounded to halving (×0.5) for simplicity. Final: F-cascade w_h10d = +0.025.
- **Rationale**: at h10d, signal magnitudes scale by sqrt(2) under random-walk-IID. To preserve *effective* contribution at lsk3-baseline level, weight must scale inversely. v10_h10d validation contract simultaneously scales magnitude thresholds by sqrt(2) (e.g., regime worst floor -2.0 → -2.828) so net contribution to gate-passing remains comparable.
- **Status**: active. Applied to F-cascade (0.05 → 0.025 at h10d).
- **Caveat**: rate-based thresholds (loss_window_fraction, positive_regime_fraction) are horizon-agnostic and DO NOT scale.
- **References**: SP-C Phase 3 threshold_provenance section; `validation_contract_h10d.json` `horizon_basis` block; ADR-D2 below.

---

## C. Score architecture

### ADR-C1: lsk3 11-factor baseline composition

- **Context**: which factors anchor the cross-sectional score?
- **Decision**: 11 hand-picked factors covering MF-04 (carry), MF-06 (reflexive), MF-07 (disagreement), MF-09 (contagion), MF-10 (vol fragility), MF-11 (structure). Specific list:
  1. `intraday_realized_vol_4h_to_1d_smooth_60` w=-0.20
  2. `realized_volatility_5` w=-0.10
  3. `distance_to_high_60` w=+0.18
  4. `distance_to_high_5` w=+0.15
  5. `coinglass_top_trader_long_pct_smooth_5` w=-0.07
  6. `liquidity_stress_qv_iv` w=-0.10
  7. `momentum_decay_5_20` w=-0.06
  8. `coinglass_taker_imb_intraday_dispersion_24h` w=+0.05
  9. `quality_funding_oi` w=-0.05
  10. `downside_upside_vol_ratio_30` w=+0.10
  11. `funding_basis_residual_implied_repo_30` w=+0.07
- **Rationale**: lsk3 was originally hand-engineered in phase-0 v83 ("xs_minimal_v3", 4-feature) → v91 (9-feature) → lsk3 (11-feature). lsk3 outperforms all earlier ML-style heavy combinations on rank IC (~0.20) and walk-forward stability. The 11 weights are not Pareto-optimal — they're *robust* picks chosen for low turnover + interpretability.
- **Status**: active. lsk3 is the baseline of all v_alpha candidates. Late-2026 decay diagnostic confirmed lsk3 does NOT need restructuring.
- **References**: `manifests_archive/phase0_v1_v82/README.md`; ADR-C5 below.

### ADR-C2: Final score normalization — `tanh((percentile_rank(raw_score) - 0.5) × 1.80)`

- **Context**: how to map raw_score (sum of weighted z's) to a bounded score in [-1, +1]?
- **Decision**: percentile-rank the raw score per timestamp → center at 0.5 → multiply by 1.80 → tanh. Final score ∈ [-1, +1] with most mass near tanh-saturation tails (because 1.80 × 0.5 = 0.90 ≈ tanh-saturation).
- **Rationale**: percentile-rank removes scale dependence on raw_score units (z's can have arbitrary spread). The 1.80 multiplier ensures **edge-of-distribution** assets (top 5% / bottom 5%) saturate to ±1, while middle assets stay near 0. tanh keeps the function bounded and differentiable. 1.80 was chosen empirically in v91+ Phase 0 to balance edge-saturation vs middle-sensitivity.
- **Status**: active across all v_alpha score functions.
- **References**: `features.py` `_timestamp_percentile_rank` + `np.tanh(centered_rank * 1.80)` in every `xs_alpha_ontology_v*_score`.

### ADR-C3: Top-K = 3 long-short construction

- **Context**: long-short portfolio construction — how many names long / short?
- **Decision**: Top-3 long + Bottom-3 short per timestamp; long_leverage = 0.5, short_leverage = 0.5; max_gross_leverage = 1.0.
- **Rationale**: Top-3 balances cross-sectional diversification (3 names each side dilutes single-asset noise) with capacity (max_trade_participation_rate stays < 0.005 — see `ADR-G1`). Larger K (top-7) was tested in v_alpha_v1_topk7 manifest but produced lower walk-forward sharpe — likely because the signal is concentrated in top/bottom 5% of cross-section.
- **Status**: active across all v_alpha candidates.
- **References**: `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_topk7.json` (alternative); profile_constraints `top_long_count: 3, bottom_short_count: 3`.

### ADR-C4: Score / overlay layer separation

- **Context**: Where do regime-adaptive components belong? In the score function or as a separate multiplier?
- **Decision**: Score function = pure cross-sectional ranking (raw → percentile → tanh). Overlay = position-multiplier in [0.30, 1.00] applied AFTER score, in `execution_backtest._cross_sectional_period`. Score factors are signal-direction; overlay factors are exposure-magnitude.
- **Rationale**: separation prevents weight scan on one layer from leaking into the other. Score weight tuning has different objectives (rank IC) than overlay tuning (regime-conditional exposure). Empirically validated by W3.5 v1 → v2 evolution: when v1 missed slow-grind regimes, fix was overlay-only (added F55 + trailing return) — score remained unchanged.
- **Status**: active. Manifest field `position_multiplier_overlay_id` declares overlay; `multiplier_overlay.OVERLAY_BUILDERS` dispatches.
- **References**: `regime_gating.py`, `multiplier_overlay.py`.

### ADR-C5: Cross-sectional z-score per timestamp (not subject)

- **Context**: When constructing weighted-sum raw_score, z-score factors before summing. Per-timestamp z (cross-sectional) or per-subject z (time-series)?
- **Decision**: Per-timestamp z-score (cross-sectional) — `_timestamp_zscore`.
- **Rationale**: cross-sectional ranking is the strategy's core (top-K long-short). Per-timestamp z normalizes magnitude across assets at each rebalance, letting the score reflect relative ranking at that timestamp. Per-subject z would normalize across time within an asset — irrelevant for cross-sectional ranking.
- **Status**: active.
- **References**: `features.py` `_timestamp_zscore`, `_timestamp_percentile_rank`.

### ADR-C6: Regime-conditional weight architecture (proposed for SP-J)

- **Context**: Multiple independent deep dives (SP-F cycle non-additivity, tt_smooth_5 + momentum_decay per-regime, dual-horizon ensemble) converge: factor alpha is increasingly regime-localized at this panel size + lsk3 saturation level. Constant-weight score architecture cannot capture regime-conditional alpha (e.g., F1 G6-passes admission but adds zero cycle value at constant weight; momentum_decay sign flips per regime).
- **Decision (proposed, pending SP-J cycle test)**: extend score-layer architecture to support per-regime weights. Score function takes a regime label per timestamp and emits regime-specific weighted sum:
  ```
  score(t, asset) = sum_i weight_i[regime(t)] × z(factor_i, t)
  ```
  Implementation options:
  - (J1) Single score function with per-regime weight dict (simpler, in features.py)
  - (J2) Multiple score functions + regime-aware dispatcher (cleaner separation)
- **Rationale**:
  - Empirically validated overlay-layer precedent (W3.5 v2 trailing_universe_mean_return) shows regime-conditional throttling at the position-multiplier layer adds value when its trigger overlaps lsk3 losing days.
  - Score-layer regime conditioning is the natural extension: instead of "throttle position when X regime", "use different factor weights when X regime".
  - F1 (SP-F) is the canonical use case: G6-admitted at residual IC +0.040 t=+7.24 vs lsk3+F08 at h10d, but cycle non-additive at constant weight when stacked on F-cascade. Hypothesis: F1 alpha is concentrated in rotation/drawdown regimes; constant weight averages it out.
- **Doc anchor**: doc §G.5 mentions regime gating multipliers but not regime-conditional score weights. SP-J extends the gating-pattern from overlay layer to score layer.
- **Risks**:
  - **Regime label lookahead risk**: calendar-based regime windows are post-hoc; production regime detection (W3.5 v2 trailing components) is tail-prone (regime detection lags actual transitions).
  - **Overfitting risk**: 3 regime windows × N factors × possibly different weights per regime → search space explodes. Must constrain to single-factor regime sensitivity (e.g., F1 active in rotation only) rather than full-matrix tuning.
  - **Manifest complexity**: per-regime weight dict adds spec_hash dimensions; cycle infrastructure must support regime dispatch.
- **Status**: **VALIDATED ARCHITECTURE, NOT VALIDATED ALPHA** (2026-05-01). SP-J cycle (Phase 2 of post-Day-60 plan) executed v10 regime-conditional score under v10_h10d contract: strict-pass + cycle-flat metrics vs v6_h10d (walk-forward Δ=0.000). Architecture works correctly end-to-end (manifest + classifier + score function); F1 alpha unlock hypothesis rejected (cycle non-additivity is fundamental, not weight-architecture-driven). Architecture preserved as Stage-2 primitive for future regime-localized SP-X candidates.
- **References**: SP-J entry in `data_utilization_roadmap.md` §C + §G; threshold_provenance.md "SP-J regime-conditional alpha architecture cycle test" section; SP-F section; v10 manifest `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v10_regime_conditional_lsk3_g_v2_h10d.json`.

---

---

## D. Validation contract / cycle gates

### ADR-D1: validation_contract.v10 thresholds (h5d)

- **Context**: cycle-level acceptance gates — what does a candidate need to PASS to ship as `active_alternative`?
- **Decision**: per `validation_contract.json` v10:
  - `walk_forward.median_oos_sharpe_min` = 0.8
  - `walk_forward.loss_window_fraction_max` = 0.4
  - `walk_forward.window_count_min` = 10
  - `regime_holdout.regime_coverage_min` = 3
  - `regime_holdout.positive_regime_fraction_min` = 0.3
  - `regime_holdout.worst_regime_median_oos_sharpe_min` = -2.0
  - `factor_evidence.rank_ic_mean_abs_min` = 0.01
  - `factor_evidence.rank_ic_positive_rate_min` = 0.52
  - `factor_evidence.top_minus_bottom_return_min_exclusive` = 0.0
  - `sharpe_anomaly_quarantine_threshold` = 20.0
- **Rationale**: thresholds are calibrated against v83+ phase-0 baseline candidates that empirically passed walk-forward + regime tests. 0.8 walk-forward median ≈ 0.8 × sqrt(252) × daily-IR (annualized). -2.0 regime worst is the deepest acceptable trough for a long-short top-3 strategy.
- **Status**: active for h5d cycles.
- **References**: `validation_contract.json`; threshold_provenance.md (legacy phase-0 calibration sections).

### ADR-D2: validation_contract.v10_h10d sqrt-scaled thresholds (h10d)

- **Context**: h10d cycles fail v10 (h5d) regime worst floor -2.0 by design (sharpe magnitudes sqrt(2)× larger). Solution: scale thresholds.
- **Decision**: per `validation_contract_h10d.json` v10_h10d:
  - sharpe-magnitude thresholds × sqrt(2): worst_regime_floor -2.0 → **-2.828**, walk_forward median 0.8 → **1.131**
  - rate-based thresholds UNCHANGED: loss_window_fraction_max 0.4, positive_regime_fraction_min 0.3, regime_coverage_min 3
  - factor_evidence rank IC thresholds UNCHANGED (rank-based)
  - `sharpe_anomaly_quarantine_threshold` = **200.0** (NOT sqrt-scaled — see ADR-D3)
- **Rationale**: sharpe(N-period) ≈ sqrt(N) × sharpe(1-period) under random-walk-IID. Magnitude thresholds must scale with sqrt(horizon_ratio); rate thresholds (probabilities, sample fractions) are dimensionless.
- **Status**: active for h10d cycles. Used by v6_lsk3_g_v2_h10d (active_alternative), v9_lsk3_g_v2_h10d (experimental).
- **References**: SP-C Phase 3 threshold_provenance section; `validation_contract_h10d.json` `horizon_basis` block.

### ADR-D3: sharpe_anomaly_quarantine_threshold = 200 at h10d (NOT sqrt-scaled)

- **Context**: h10d uses sqrt-scaled magnitude thresholds for regime + walk-forward. Should sharpe_anomaly_quarantine_threshold also sqrt-scale (20 → 28.3)?
- **Decision**: NO. Set to 200 as "numerical pathology floor".
- **Rationale**: sqrt-scaled 28.3 was tested first — 7 of 32 v6_h10d walk-forward windows triggered anomaly (median window sharpe was healthy +2.83). Investigation found: at h10d, individual 10-day windows with strong directional bias routinely produce sharpes in 25-150 range — these are statistically real (heavy short-window bias), NOT pathological. sharpe_anomaly threshold targets *zero-variance numerical pathology* (not magnitude rescaling). 200 = "physically impossible under cross-sectional rank-strategy" floor.
- **Status**: active. Documented in `validation_contract_h10d.json` `_sharpe_anomaly_h10d_note`.
- **References**: SP-C Phase 3 empirical sharpe_anomaly tuning section.

### ADR-D4: Cumulative compound return as supplementary metric (proposed)

- **Context**: dual-horizon ensemble analysis (2026-04-30) found that v6_h10d wins on validation contract metric `median_oos_sharpe_min` (+2.832 > v6_h5d +2.373) BUT v6_h5d wins on terminal portfolio value (32-month cumulative compound return +109.04% vs +75.88%). The two metrics REVERSE.
- **Decision (proposed, pending owner approval)**: amend `validation_contract.json` v10 / `validation_contract_h10d.json` v10_h10d to add `cumulative_compound_return_min` as a SUPPLEMENTARY metric alongside `median_oos_sharpe_min`. Possible specifications:
  - Hard floor: `cumulative_compound_return_min: 0.5` (50% over walk-forward span; below this → contract FAIL)
  - Soft annotation: `cumulative_compound_return_target: 1.0` (100% target; emit warning if below but don't fail)
  - Separate metric not in gate logic, just reported: `cumulative_compound_return: <value>` (informational only)
- **Rationale**:
  - Validation contract median sharpe favors low-frequency-high-edge horizons (h10d 3 rebalance/month × high edge has higher per-window sharpe).
  - Cumulative return favors high-frequency-moderate-edge horizons (h5d 6 rebalance/month × moderate edge has more compounding).
  - Stage-2 deployment criterion is closer to terminal portfolio value, not risk-adjusted-edge.
  - Without this metric, ranking active candidates by sharpe alone underweights deployment efficiency.
- **Implementation note**: cumulative compound return = `prod(1 + r_i) - 1` over walk-forward windows. Easy to compute from existing `walk_forward.windows[i].net_return` arrays. No new data needed.
- **Risk**: hard floor could over-constrain low-edge but high-frequency strategies that compound to acceptable terminal value via volatility (e.g., capacity-aware large-N strategies). Recommend starting with informational-only reporting, then formalizing soft warning, then hard floor over multiple cycles.
- **Status**: PROPOSED. Not yet implemented in contract. Owner-action required for ratification.
- **References**: dual-horizon ensemble analysis in threshold_provenance.md; lesson 11 in `data_utilization_roadmap.md` Snapshot status.

---

---

## E. Overlay (regime gating) architecture

### ADR-E1: Overlay multiplier range [0.30, 1.00]

- **Context**: overlay multiplier output bounds.
- **Decision**: `_MULTIPLIER_FLOOR = 0.30` (never trade below 30% of full size); ceiling = 1.00 (never inflate position above target weight).
- **Rationale**: Floor 0.30 allows extreme regimes to deeply throttle without zero-position which would lose all signal exposure. Ceiling 1.00 prevents the overlay from becoming a leverage amplifier — it can only scale DOWN, not up. Combined, this creates a safe-asymmetric overlay (stress-only throttle).
- **Status**: active across v1/v2/v3 overlays.
- **References**: `regime_gating.py` `_MULTIPLIER_FLOOR`.

### ADR-E2: Per-component floor 0.50 / 0.70 to prevent product collapse

- **Context**: overlay = product of N component multipliers. If each component can independently hit floor 0.30, the product collapses geometrically (e.g., 5 components × 0.30 = 0.0024, then clipped back to 0.30 — defeats the multi-component design).
- **Decision**: Per-component floors:
  - v1 components (F49, F26): 0.30 (overall floor; they're the "primary" stress signals)
  - F44 dispersion floor: 0.50 (prevents low-dispersion-only days from collapsing)
  - v2 extras (F55, trailing return): 0.50 each (`_V2_EXTRAS_COMPONENT_FLOOR`)
  - v3 DVOL components: 0.70 each (`_V3_DVOL_COMPONENT_FLOOR`) — added cautiously
- **Rationale**: 0.50 ^ 2 = 0.25 (still above floor 0.30) — guarantees that v2 extras alone can't drive the multiplier to floor on otherwise-calm days. v3 DVOL at 0.70 is more conservative because DVOL is an unproven addition.
- **Status**: active.
- **References**: `regime_gating.py` constants; W3.5 v1 → v2 calibration section in threshold_provenance.

### ADR-E3: Overlay must overlap with strategy-specific losing days

- **Context**: SP-G DVOL extension overlay (v3) was operationally well-calibrated (4% trigger, sensible thresholds) but did NOT shift cycle metrics over v6_h10d. Why?
- **Decision (lesson learned)**: Overlay components only add value when their throttle days **systematically overlap with strategy losing days**. Generic "vol of vol regime" detection isn't sufficient.
- **Rationale**: W3.5 v2's `trailing_universe_mean_return_30d` worked because slow-grind bear regimes are exactly lsk3's specific failure mode. DVOL anomaly days don't have this overlap with lsk3+F-cascade losing days at h10d → throttling them shaves winning compounds without saving losses.
- **Status**: active rule. Future overlay candidates need failure-mode-aware design + cycle-overlap diagnostic before promotion.
- **References**: SP-G threshold_provenance section; experiment_catalog.md §C.3.

---

## F. Lifecycle management

### ADR-F1: G.5 state machine — verbatim doc compliance

- **Context**: how to manage factor lifecycle (active → watch → decay → retired)?
- **Decision**: Implement G.5 spec verbatim in `factor_lifecycle.py`. Thresholds:
  - `WATCH_RESID_IC_THRESHOLD` = 0.02 (60d resid IC < 0.02 for 2 consecutive 30d-step windows)
  - `DECAY_RESID_IC_THRESHOLD` = 0.01 (60d resid IC < 0.01 sustained 30d)
  - `DECAY_SUSTAIN_DAYS` = 30
  - `RETIRED_CUM_90D_THRESHOLD` = 0 (90d cum residual IC < 0)
  - `REVIVED_SHADOW_OOS_THRESHOLD` = 0.05
- **Rationale**: doc compliance is the priority. G.5 thresholds are doc-specified; deviating would require doc amendment.
- **Status**: active. Used in M2.5 demotion experiment (Day 60 exit criterion bullet 3).
- **References**: doc §G.5; `factor_lifecycle.py`; ADR-F2 below for sanity check augmentation.

### ADR-F2: Raw-IC sanity check augments G.5 (does NOT override)

- **Context**: M2.5 demotion experiment recommended demote for 7/11 lsk3 factors. lsk3 baseline late-2026 decay diagnostic showed 5/7 were measurement artifacts (high internal correlation `iv_smooth_60` ↔ `dh_60` -0.522 → self-residual collapse).
- **Decision**: Add `assess_raw_ic_sanity_check` annotation to G.5 verdicts (preserves verbatim doc compliance). New thresholds:
  - `RAW_IC_SANITY_STABLE_FLOOR` = 0.02 (|raw IC| above: factor stable)
  - `RAW_IC_SANITY_STRONG_FLOOR` = 0.04 (|raw IC| above G1 floor: factor strong)
- **Rationale**: G.5 alone produces systematic false-positive demotion when baseline has high internal correlation. Raw-IC cross-check identifies "G.5 demotes but raw IC stable" cases as `likely_artifact` / `likely_artifact_strong`. Sanity check ANNOTATES the verdict but does NOT override — owner-side reads both signals.
- **Status**: active. Re-run M2.5 with sanity check shows 10/14 demote recommendations are artifact-flagged (3 strong).
- **References**: lsk3 baseline late-2026 decay diagnostic; `factor_lifecycle.py` `assess_raw_ic_sanity_check`.

### ADR-F3: Stage-1 invariant — factor_lifecycle is recommendation engine, NOT auto-mutation

- **Context**: factor_lifecycle.py outputs demote / retire recommendations. Should it auto-mutate manifest `lifecycle` fields?
- **Decision**: NO. factor_lifecycle is a recommendation engine. Manifest edits remain owner-driven. Pipeline:
  1. `run_factor_lifecycle_demotion_experiment.py` writes JSON report.
  2. Owner reads report.
  3. Owner manually updates manifest `lifecycle` fields.
- **Rationale**: per Stage-1 publication policy (PROJECT_STATE.md "Locked Decisions"), no auto-runtime mutation of admitted-factor state without owner review. Auto-mutation would violate the archive-only Stage-1 invariant and risk silent slide into higher-risk execution behavior.
- **Status**: active. Stage-1 invariant.
- **References**: PROJECT_STATE.md "Locked Decisions"; CLAUDE.md "Red Lines"; `factor_lifecycle.py` module docstring.

---

## G. Capacity / execution

### ADR-G1: max_trade_participation_rate = 0.005 + max_inventory_participation_rate = 0.02

- **Context**: capacity gate — max fraction of (per-rebalance volume / OI) the strategy can participate in.
- **Decision**: `max_trade_participation_rate_max` = 0.005 (0.5% of per-rebalance volume); `max_inventory_participation_rate_max` = 0.02 (2% of OI).
- **Rationale**: Stage-1 / capacity-aware research policy. 0.5% per rebalance keeps slippage estimates stable for backtests; 2% OI is the standard "you're not the market" threshold. These are horizon-agnostic (doc §G.4 + validation_contract).
- **Status**: active across all v_alpha cycles + h5d/h10d horizons.
- **References**: `validation_contract.json` `factor_evidence.max_trade_participation_rate_max`; doc §G.4.

### ADR-G2: long_leverage = 0.5, short_leverage = 0.5, max_gross_leverage = 1.0

- **Context**: portfolio gross / net leverage.
- **Decision**: long-side 0.5, short-side 0.5 → gross 1.0, net 0.
- **Rationale**: 1× gross leverage is the simplest "no leverage" baseline. Net 0 (long-short symmetric) hedges market exposure. Stage-1 conservative.
- **Status**: active.
- **References**: profile_constraints in all v_alpha manifests.

---

## H. Regime windows

### ADR-H1: 3 fixed-calendar regime windows for regime_holdout

- **Context**: regime_holdout test partitions panel into N regimes, requires positive_regime_fraction ≥ X. Which regimes?
- **Decision**: 3 fixed-calendar regimes:
  - `trend_up_2025h2`: Aug-Oct 2025 (extended bull trend)
  - `rotation_high_vol_2025q4`: Nov 2025-Jan 2026 (rotation regime, high-vol)
  - `drawdown_rebound_2026ytd`: Feb-Apr 2026 (post-cascade rebound)
- **Rationale**: 3 distinct regimes with sufficient sample size (each ~3 months). Calendar-fixed (not data-driven) prevents lookahead. Each regime tests a different stress: trend, rotation, drawdown.
- **Status**: active. Used in regime_holdout validation gate.
- **References**: validation_contract.json regime_holdout block.

---

## I. Per-horizon dispatch (cycle infrastructure)

### ADR-I1: Per-horizon validation contract dispatch via monkey-patch

- **Context**: SP-C Phase 3 introduced v10_h10d contract for h10d cycles. How to dispatch the right contract at runtime?
- **Decision**: Monkey-patch `vc.VALIDATION_CONTRACT_PATH` and `vc.VALIDATION_CONTRACT_VERSION` in `run_alpha_ontology_horizon_cycle_oneoff.py` based on `--target-horizon-bars` flag. h5d → v10 contract; h10d → v10_h10d contract; other horizons fall through to v10.
- **Rationale**: monkey-patching keeps the cycle infrastructure code paths simple (single function `run_quant_hypothesis_batch_cycle`) without needing horizon-aware multiplexing inside hypothesis_batch.py. The patch is per-invocation and cleanly reversible after the cycle.
- **Status**: active. Used for v6_h10d / v9_h10d / v3 (overlay) cycles.
- **References**: root wrapper `run_alpha_ontology_horizon_cycle_oneoff.py`;
  implementation `alpha_ontology_cycles/run_alpha_ontology_horizon_cycle_oneoff.py`
  `_HORIZON_CONTRACT_PATHS` map.

### ADR-I2: Manifest-time spec_hash validation

- **Context**: each manifest entry has `spec_hash` (SHA-256 of canonical JSON of cycle-relevant fields). Cycle runner validates spec_hash matches expected before running. Why?
- **Decision**: enforce spec_hash match in `_normalize_hypothesis_candidate_entry`. Mismatch raises `ValueError` and aborts cycle.
- **Rationale**: spec_hash binds manifest config → cycle output. If someone edits the manifest's profile_constraints / required_feature_columns / model_family without re-computing spec_hash, the cycle would silently produce inconsistent artifacts. Hard-failing forces explicit hash recomputation when fields change.
- **Status**: active. Used during all manifest edits in SP-C Phase 3 + SP-F (spec_hash recomputed per weight change).
- **References**: `hypothesis_batch.py` `_compute_hypothesis_candidate_spec_hash`.

---

## J. Falsification / mechanism rejection

### ADR-J1: Hold the line on doc-prescribed thresholds (sub-significance ≠ admission)

- **Context**: SP-D §E.16 t-stat 1.39 (vs 2.0 threshold) and SP-H §E.15 KS p=0.128 (vs 0.05 threshold) both have correct mechanism direction but sub-significance. Tempting to relax thresholds.
- **Decision**: Hold doc-prescribed thresholds. Sub-significance → REJECT.
- **Rationale**: doc thresholds were calibrated to control false-positive admission rate. Sub-threshold mechanisms typically don't survive walk-forward at cycle layer (even if they pass admission). Holding the line prevents accumulating weak-but-correlated factors that compound into stale-alpha noise.
- **Status**: active. Applied to SP-D / SP-H rejections.
- **References**: SP-D / SP-H threshold_provenance sections; experiment_catalog.md §D.

### ADR-J2: Tertile-stratified IC for regime-gate falsification (sample-size aware)

- **Context**: SP-E §E.17 falsification uses absolute-threshold split (low-corr <0.5 vs high-corr ≥0.7). Low-corr regime had n=9 timestamps only → unreliable.
- **Decision**: ALSO compute tertile-stratified IC (each tertile n≈365). Use tertile result as the gating evidence when sample sizes are unbalanced.
- **Rationale**: tertile split provides balanced statistical power (n≈365 per cell) vs absolute split (n=9 vs 935). SP-E tertile-stratified IC ratio = 0.90 (sign-reversed vs doc prediction of ≥1.20) → REJECT. Without tertile diagnostic, absolute split's borderline pass (1.21 at h10d, n=9) would have been misleading.
- **Status**: active rule for regime-gate audits.
- **References**: SP-E threshold_provenance section; experiment_catalog.md §D.

---

## K. Documentation / audit infrastructure

### ADR-K1: 5-layer documentation pyramid for quant research

- **Context**: how to record sub-path findings + per-factor state + per-experiment data + algorithm rationale without single-document bloat?
- **Decision**: 5-layer documentation pyramid:
  1. **Main file integration**: `PROJECT_STATE.md` Quant Research section + `README_FOR_AGENT.md` directory map (entry pointers)
  2. **Snapshot status**: `data_utilization_roadmap.md` top section (1-page status board)
  3. **Sub-path conclusions**: `data_utilization_roadmap.md` §G (per-sub-path entries with lessons)
  4. **Full audit lineage**: `config/quant_research/threshold_provenance.md` (chronological per-SP sections)
  5. **Per-candidate detail**: each manifest's `lineage` + `verified_outcome_*` blocks
- **Rationale**: each layer serves a different read pattern. Layer 1 = "where do I start?". Layer 2 = "what's the current state?". Layer 3 = "what did SP-X conclude?". Layer 4 = "show me the audit". Layer 5 = "exact numbers for candidate Y".
- **Status**: active since commit `796655e` (3-step ledger fix).
- **References**: README_FOR_AGENT.md directory map; PROJECT_STATE.md Quant Research section.

### ADR-K2: ABC catalog docs (factor / experiment / algorithm)

- **Context**: layer-3/4 docs are chronological by sub-path. Cross-cutting views (per-factor, per-experiment, per-algorithm decision) require grep-and-pray.
- **Decision**: Build 3 catalog docs:
  - `factor_audit_trail.md` — per-factor one-stop index
  - `experiment_catalog.md` — weight scans / variants / failed integrations / falsifications / horizon scans
  - `algorithm_choices.md` — design decision rationale (this doc)
- **Rationale**: catalog docs complement chronological docs (layer 3/4). When you need "F-cascade complete history" or "did we test weight w on factor X?", ABC catalogs surface it in one place. Chronological docs (threshold_provenance) remain the source of truth; ABC are reorganized views.
- **Status**: active since this commit.
- **References**: this doc; `factor_audit_trail.md`; `experiment_catalog.md`.

---

## L. Index by sub-path

| sub-path | ADRs touched |
| --- | --- |
| Phase 0 (W1.x / W3.x / M2.x / lsk3) | A1-A4, B1, C1-C5, D1, E1-E2, G1-G2, H1 |
| **SP-A** (cascade) | B1, C1, J1 |
| **SP-B** (microstructure) | A1, A3 |
| **SP-C Phase 1** (multi-horizon audit) | E.1 (experiment_catalog) |
| **SP-C Phase 2** (h10d cycle infra) | I1 |
| **SP-C Phase 3** (sqrt-scaled v10_h10d) | B3, D2, D3, I1 |
| **SP-D** (basis propagation) | J1 |
| **SP-E** (corr regime gate) | J1, J2 |
| **SP-F** (sub-day funding) | A3, B1, B2 |
| **SP-G** (DVOL overlay) | E2, E3 |
| **SP-H** (expiry hedge unwind) | J1 |
| **M2.5** (factor_lifecycle) | F1, F3 |
| **lsk3 decay diagnostic** | A3, F2 |
| **3-step ledger fix** | K1 |
| **ABC catalog docs** | K2 |
| **Dual-horizon ensemble + per-regime deep dive** | D4 (proposed cumulative return metric) |
| **SP-J (proposed) regime-conditional architecture** | C6 (proposed regime-conditional weights) |
