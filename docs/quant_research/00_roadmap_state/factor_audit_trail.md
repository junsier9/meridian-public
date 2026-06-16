# Factor Audit Trail — Per-Factor One-Stop Index

`Snapshot date: 2026-05-03` · `Owner: quant_research_maintainer`

> **Read-this-first per-factor view.** For each factor that has appeared in any score / overlay / admission audit, this document lists: provenance, current state, admission audit outcomes, score-integration history, lifecycle markers, and cross-references to threshold_provenance / manifest / source code.
>
> Companion docs:
> - `data_utilization_roadmap.md` Snapshot status — sub-path level conclusions
> - `threshold_provenance.md` — chronological audit lineage with full detail
> - `experiment_catalog.md` — weight scans / variants / failed integrations
> - `algorithm_choices.md` — design decision rationale

---

## A. Active in score (12 factors)

### `intraday_realized_vol_4h_to_1d_smooth_60` (lsk3)

- **Mechanism family**: MF-10 higher_moment_fragility
- **Source**: pre-SP-A baseline (in lsk3 11-factor since v83+). 60d smoothed 4h→1d realized volatility.
- **Score weight**: -0.20 in lsk3 score (all v_alpha variants).
- **Lifecycle**: `active`. lsk3 baseline factor in v_alpha_v1_lsk3_g_v2 (h5d active), v6_lsk3_g_v2 (h5d active_alternative), v6_lsk3_g_v2_h10d (h10d active_alternative).
- **Admission**: implicit (carried from v83 / Phase-0 baseline).
- **Late-2026 lifecycle audit (M2.5 + lsk3 diagnostic)**:
  - G.5 verdict: `decay` (60d resid IC +0.0006 sustained 523 days below threshold)
  - Sanity check: **likely_artifact** (raw 60d IC -0.0352, |raw| > stable floor 0.02; raw IC actually STRENGTHENING in late period: early -0.038 → late -0.116, bootstrap CI [-0.143, -0.088] excludes G1 floor)
  - Diagnostic conclusion: **keep** — self-residual artifact from `dh_60` correlation -0.522
- **References**: lsk3 baseline mention in all v_alpha manifests; threshold_provenance.md "lsk3 baseline late-2026 decay diagnostic" section.

### `realized_volatility_5` (lsk3)

- **Mechanism family**: MF-10
- **Score weight**: -0.10 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**: G.5 verdict `active` (60d resid +0.0086); raw 60d -0.0107; bootstrap CI [-0.088, -0.037] excludes 0. Stable.

### `distance_to_high_60` (lsk3)

- **Mechanism family**: MF-11 liquidity_migration / structure
- **Score weight**: +0.18 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**: G.5 verdict `active`; raw 60d -0.0149 (mild negative); bootstrap CI [+0.034, +0.082] excludes 0 (STRENGTHENING late: early +0.022 → late +0.057).
- **Notes**: paired with `iv_smooth_60` at corr=-0.522 (lsk3 internal redundancy hotspot).

### `distance_to_high_5` (lsk3)

- **Mechanism family**: MF-11
- **Score weight**: +0.15 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**: G.5 verdict `active`; raw 60d +0.0399 (near G1 floor); bootstrap CI [+0.074, +0.115] crosses G1 floor 0.04 (STRENGTHENING late: early +0.037 → late +0.094). Strongest late-period factor by raw IC.

### `coinglass_top_trader_long_pct_smooth_5` (lsk3)

- **Mechanism family**: MF-07 participant_disagreement
- **Score weight**: -0.07 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**:
  - G.5 verdict: `retired` (90d cum -0.0407)
  - Sanity check: **likely_artifact_strong** (raw 60d IC -0.0423, |raw| > G1 floor 0.04)
  - Diagnostic conclusion: **TRUE regime shift** — raw IC degraded from -0.035 (early) to -0.008 (late, bootstrap CI [-0.019, +0.003] **includes 0**, signal weakened to near-zero in late period).
- **Per-regime deep dive (2026-04-30)**:
  - pre_regime_2024_2025h1 IC -0.030 t=-4.56 (n=830) — original strong direction
  - **trend_up_2025h2 IC = 0.000** (n=92) — signal completely fails in trend
  - rotation_high_vol_2025q4 IC -0.016 (n=92) — weakened but original sign
  - **drawdown_rebound_2026ytd IC = -0.033 t=-3.55** (n=80) — **signal RESTORED** to original strength
  - **NOT permanent decay** — signal is regime-fragile, fully recovers in non-trend regimes
- **Cross-section convergence onset 2025Q4**: p90-p10 spread cliff-drops from ~70 to ~30 across alts. ETF flow / institutional crowding hypothesis. Cross-asset rank loses differentiating power at panel grain.
- **Candidate causes (ranked)**:
  1. (STRONG) Cross-section convergence 2025Q4
  2. (STRONG) Trend-regime mechanism failure (universal mean-revert breakdown in trends)
  3. (MEDIUM) 2025Q3 anomaly: low-vol + crowded-long + uptrend disables reversion
- **Owner-action options**: (A) keep w=-0.07; (B) reduce to w=-0.04; (C) reformulate as cross-asset dispersion; (D) regime-conditional weighting. NOT auto-actioned.
- **References**: M2.5 demotion experiment + lsk3 baseline late-2026 decay diagnostic + tt_smooth_5 / momentum_decay per-regime deep dive.

### `liquidity_stress_qv_iv` (lsk3)

- **Mechanism family**: MF-04 carry_residuals (composite)
- **Score weight**: -0.10 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**: G.5 verdict `watch` (60d resid -0.0018); raw 60d -0.0070; bootstrap CI [-0.058, -0.022] excludes 0. Stable. Sanity check: not flagged. **TRUE watch** (raw also weak).

### `momentum_decay_5_20` (lsk3)

- **Mechanism family**: MF-09 cojump_contagion (decay component)
- **Score weight**: -0.06 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**:
  - G.5 verdict: `retired` (90d cum -0.0533)
  - Sanity check: **likely_artifact_strong** (raw 60d IC +0.0643, late-most-recent-60d strong but with FLIPPED SIGN)
  - Diagnostic conclusion: **TRUE regime shift** — sign flip from early -0.022 to late +0.015 (bootstrap CI [-0.008, +0.039] includes 0).
- **Per-regime deep dive (2026-04-30)**:
  - pre_regime_2024_2025h1 IC -0.021 t=-2.37 (n=833) — original direction
  - trend_up_2025h2 IC -0.022 t=-0.96 (n=92) — original direction but t weak
  - **rotation_high_vol_2025q4 IC = +0.075 t=+3.01** (n=92) — **STRONGLY POSITIVE, single regime drives entire sign flip**
  - drawdown_rebound_2026ytd IC +0.004 (n=80) — near zero
  - **The sign flip is ALMOST ENTIRELY driven by rotation_high_vol_2025q4 alone**.
- **Historical precedent**: 2024Q3 IC = +0.047 (similar mid-vol positive-universe regime). Sign flips correlate with regime transitions; **NOT unprecedented**.
- **Cross-section dispersion**: stable in 0.11-0.23 range, NO convergence (unlike tt_smooth_5).
- **Mechanism**: in negative universe regime (2025Q4-2026Q1 sustained negative fwd return), "short momentum < long momentum" assets = lagging losers (continued decline), not mean-revert candidates. Signal direction reverses BY MECHANISM.
- **Candidate causes (ranked)**:
  1. (DECISIVE) Pure regime-conditional sign flip — rotation_high_vol_2025q4 single driver
  2. (STRONG) Negative universe regime mechanism — fwd return regime drives flip
  3. (MEDIUM) 2024Q3 historical precedent confirms regime-conditional pattern
- **Owner-action options**: (A) keep w=-0.06; (B) regime-conditional weighting; (C) replace with universe-mean-adjusted momentum_decay; (D) drop. NOT auto-actioned.
- **References**: M2.5 demotion experiment + lsk3 baseline late-2026 decay diagnostic + tt_smooth_5 / momentum_decay per-regime deep dive.

### `coinglass_taker_imb_intraday_dispersion_24h` (lsk3)

- **Mechanism family**: MF-06 reflexive_flow
- **Score weight**: +0.05 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**: G.5 verdict `watch` (60d resid +0.0120); raw 60d +0.0070; bootstrap CI [-0.001, +0.027] **includes 0**. Noisy but no clear decay or redundancy. **TRUE watch**.

### `quality_funding_oi` (F12, lsk3)

- **Mechanism family**: MF-04 carry_residuals
- **Source**: W1.1 F12 — funding × OI quality composite.
- **Score weight**: -0.05 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline. **MF-04 family workhorse** — the dominant absorber of MF-04 cross-asset basis signal (validated by SP-D §E.16 falsification: D2/D3 alt_basis_residual factors fail G6 because F12 already absorbs the dimension).
- **Late-2026 audit**:
  - G.5 verdict: `retired` (90d cum -0.0266)
  - Sanity check: **likely_artifact** (raw 60d IC -0.0388, |raw| > stable floor 0.02; bootstrap CI [-0.032, -0.010] excludes 0, raw IC stable)
  - Diagnostic conclusion: **keep** — self-residual artifact, raw signal stable.
- **References**: SP-D threshold_provenance section (saturation evidence); lsk3 baseline late-2026 decay diagnostic.

### `downside_upside_vol_ratio_30` (F33, lsk3)

- **Mechanism family**: MF-10
- **Source**: W1.1 F33 realized_volatility_downside / upside ratio over 30d.
- **Score weight**: +0.10 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline.
- **Late-2026 audit**: G.5 verdict `active` (60d resid +0.0241); raw 60d +0.0360 (near G1 floor); bootstrap CI [+0.042, +0.071] crosses G1 floor (STRENGTHENING late: early +0.020 → late +0.055).

### `funding_basis_residual_implied_repo_30` (F12 sibling, lsk3)

- **Mechanism family**: MF-04
- **Source**: W1.1 F12 family — funding-basis residual after implied repo orthogonalization, 30d.
- **Score weight**: +0.07 in lsk3 score.
- **Lifecycle**: `active`. lsk3 baseline. **MF-04 family workhorse #2** (with F12).
- **Late-2026 audit**:
  - G.5 verdict: `watch` (60d resid +0.0159, 8 consecutive windows below 0.02)
  - Sanity check: not flagged (raw 60d +0.0051 also weak)
  - Diagnostic conclusion: **keep** — raw IC +0.027 stable per bootstrap CI [+0.015, +0.039]. Late-period self-residual weakness is partially-redundancy + partially weakness; either way, raw is healthy.
- **References**: SP-D threshold_provenance (MF-04 saturation evidence).

### `liq_cascade_recency_score_5d` ⭐ (F-cascade, score-integrated)

- **Mechanism family**: MF-12 state_space_regime
- **Source**: SP-A — per-subject 1h liquidation cascade exponential-decay 5d recency accumulator. doc §E.12 falsification PASS (post-cascade 24h abnormal log return t=+10.75, 4× the 2.5σ doc threshold).
- **Score weight**: +0.05 in v6_lsk3_g_v2 (h5d), +0.025 in v6_lsk3_g_v2_h10d (halved per sqrt scaling), +0.025 in v9_lsk3_g_v2_h10d (alongside F1 attempt).
- **Lifecycle**: `active`. **MF-12 family productionized** — the SP-A winner that promoted v6 to active_alternative (h5d 2026-04-29, h10d 2026-04-30).
- **Admission audit (2026-04-29)**:
  - G1: raw IC +0.0522, t=+10.50 — PASS strict
  - G3: regime same-sign 1.0 (perfect across vol regimes) — PASS
  - G6 vs lsk3: residual IC +0.0616, t=+10.77 — PASS strict
  - All 4 cascade variants passed G6 (max_z_24h, count_24h_z25, signed_intensity_24h, recency_score_5d); recency_score_5d picked as strongest.
- **Late-2026 lifecycle audit**: G.5 verdict `active` (60d resid +0.0346); raw 60d +0.0056 (signal at residual layer, not raw layer — consistent with the orthogonal-to-lsk3 nature of MF-12).
- **Dual-horizon ensemble analysis (2026-04-30)**:
  - v6_h5d cumulative compound return over 32 months: **+109.04%** (highest of any candidate)
  - v6_h10d cumulative compound return: +75.88% (lower despite higher median window sharpe)
  - Pearson correlation of per-window net returns: **+0.843** (high — same alpha thesis at different horizons)
  - 50/50 ensemble: median sharpe +2.401, cumulative +92.44%, regime breakdown weakened in drawdown_rebound (h5d -3.37 + h10d +2.17 → ensemble -0.60)
  - **DECLINE 50/50 promote** — both v6_h5d and v6_h10d remain separate `active_alternative`
- **References**: SP-A threshold_provenance section; SP-C Phase 2/3 (h10d productionization); v6 dual-horizon ensemble analysis; manifests v6_lsk3_g_v2.json + v6_lsk3_g_v2_h10d.json; `intraday_liquidation_features.py`.

---

## B. Score-experimental (admitted but not promoted)

### `settlement_cycle_premium_60d` (F62)

- **Mechanism family**: MF-15 settlement_friction
- **Source**: M2.3 — per-subject pre-settlement-hour drift in 1h perp returns, 60d rolling.
- **Score weight**: -0.08 in v_alpha_v5_lsk3_g_v2 (h5d).
- **Lifecycle**: `experimental`. v5 ships strong walk-forward at h5d but regime-fragile at h10d (rotation regime collapse).
- **Admission audit**: G1+G3+G6 PASS at h5d; G6 residual IC -0.0437 vs lsk3.
- **v7 attempt**: F62 + F-cascade stacked → non-additivity (commit 68c4593). Net no improvement over v6.
- **Late-2026 audit**: G.5 `retired` (90d cum -0.0515); raw 60d -0.0067 weak; sanity check not flagged. **TRUE decay**.
- **References**: SP-A/SP-C Phase 1 threshold_provenance; manifest v5/v7.

### `funding_flip_decay_phase` (F47)

- **Mechanism family**: MF-08 event_impulse
- **Source**: W3.1 — "days since last funding sign flip" state-machine factor. Originally G6-failed at h5d in W3.1; SP-C horizon scan unlocked it at h5d (residual t -3.89) via different threshold calibration.
- **Score weight**: -0.03 in v_alpha_v8_lsk3_g_v2 (h5d).
- **Lifecycle**: `experimental`. Modest +0.08 walk-forward improvement over v1 — admissible but not winner.
- **Admission audit**: G6 borderline PASS at h5d (-0.020 t=-3.89), stronger at h10d (-0.026 t=-5.61).
- **Mutual orthogonality**: F47 residual FAILS G6 when stacked on lsk3+F62 OR lsk3+F-cascade — overlaps with both. v8 stacks on lsk3 ALONE.
- **Late-2026 audit**: G.5 `decay` (60d resid -0.0218 sustained 31 days below decay floor); raw 60d -0.0070 weak; sanity check not flagged. **TRUE decay**.
- **References**: SP-C threshold_provenance section; manifest v8.

### `funding_intraday_dispersion_30d` (F1)

- **Mechanism family**: MF-03 funding_microstructure
- **Source**: SP-F — per-subject 4h-grain rolling-30d mean of within-day funding_rate std. NEW data dimension orthogonal to F08 (1d-grain skew).
- **Score weight**: +0.015 in v_alpha_v9_lsk3_g_v2_h10d (constant weight, locked); +0/+0.025/+0.030 (regime-conditional) in v_alpha_v10_regime_conditional_lsk3_g_v2_h10d.
- **Lifecycle**: `experimental` in BOTH v9 and v10. **G6 admission PASS but cycle non-additive at BOTH constant weight (v9) AND regime-conditional weight (v10)** — confirmed FUNDAMENTAL cycle-layer overlap with F-cascade.
- **Admission audit (2026-04-29)**:
  - G1: raw IC -0.0187 (weak by raw measure)
  - G6 vs lsk3+F08 at h10d: residual IC **+0.0396, t=+7.24** — STRICT PASS (strongest among SP-F candidates)
  - G6 vs lsk3+F-cascade at h10d: residual IC +0.029 t=+5.19 — also strong
- **Sign discovery**: raw IC NEGATIVE but residual IC POSITIVE — score-integration weight must follow residual IC sign (textbook over-correction case).
- **v9 cycle outcome (constant weight)**: at safe weight w=+0.015, walk-forward identical to v6_h10d (+2.832); at w=+0.025 regime breaks (overshoots F-cascade's rotation regime protection).
- **v10 cycle outcome (regime-conditional, 2026-05-01)**: SP-J AT-PAR. Walk-forward median +2.832 (Δ=0.000 vs v6_h10d), positive_regime_fraction 2/3 preserved, worst_regime -2.805 (still in floor -2.828). **F1 alpha unlock hypothesis REJECTED at regime-conditional architecture too** — cycle non-additivity is FUNDAMENTAL, not weight-architecture-driven.
- **Late-2026 audit**: G.5 `retired` (90d cum -0.0459); raw 60d -0.0309; sanity check **likely_artifact** (raw above stable floor).
- **Conclusion**: F1 has admission-real residual IC vs lsk3+F08 + lsk3+F-cascade BUT cycle-layer overlap with F-cascade is fundamental. The +29-40 bp residual IC works AGAINST F-cascade's rotation regime protection in long-short top-3 selection × regime-windowed sharpe metric integration. Future similar candidates (high admission residual IC + high cycle-layer overlap) should expect AT-PAR / DECLINE at any weighting scheme.
- **References**: SP-F threshold_provenance section; SP-J threshold_provenance section; manifests v9 + v10; `subday_funding_features.py`.

### `xs_alpha_ontology_v3` (Bayesian variant)

- **Mechanism family**: composite (lsk3 + posterior weights)
- **Source**: M2.5 / W3.6 v3 manifest — Bayesian IR-weighted lsk3 reweighting with W3.5 v2 overlay.
- **Lifecycle**: `experimental`. Better regime breadth than v1 baseline but superseded by v6 (F-cascade).
- **References**: manifest v_alpha_v3_lsk3_g_v2.json.

---

## C. Plumbed (panel column exists, NOT in score, NOT empirically falsified)

### `top_trader_velocity_1h_abs_24h` (B3a)

- **Mechanism family**: MF-07
- **Source**: SP-B partial — daily mean abs(6h gradient of top_long), 24h grain.
- **Status**: G6 standalone PASS (residual +0.062 vs lsk3) BUT +0.94 per-ts spearman with F-cascade — sibling-duplicate.
- **NOT score-integrated** per non-additivity prediction.
- **Late-2026 audit**: G.5 `active` (60d resid +0.0372); raw 60d +0.0049 weak; sanity check not flagged. **Sibling-duplicate caveat applies — owner-side keeps at watch.**

### `funding_sign_flip_count_30d_4h` (F2)

- **Mechanism family**: MF-03
- **Source**: SP-F secondary — count of 4h-bar sign changes in rolling 30d (180 4h bars).
- **Status**: G6 PASS at h10d only (residual +0.025 vs lsk3+F08); sibling-correlated with F1 (same 4h sequence).
- **NOT score-integrated** — would re-introduce same dimension as F1.
- **Late-2026 audit**: G.5 `active` (60d resid +0.0441); raw 60d +0.0358 (near G1 floor). Owner-side keeps at watch (sibling caveat).

### `funding_term_skew_30d_4h` (F3)

- **Mechanism family**: MF-03
- **Source**: SP-F tertiary — rolling-180-bar skew of 4h funding_rate.
- **Status**: G6 FAIL at all baselines (residual <0.02). Sub-day analog of F08 — collinear with F08 funding_term_skew_60.
- **Plumbed for diagnostic**, NOT score-integrated.
- **Late-2026 audit**: G.5 `watch` (60d resid +0.0102); sanity check **likely_artifact** (raw 60d +0.0280, sibling F08 absorbs).

### `top_global_disagreement_1h_30d` (B2)

- **Mechanism family**: MF-07 (canonical participant_disagreement)
- **Source**: SP-B partial — rolling-720h corr(top_long, global_long).
- **Status**: G1 fail + G6 fail (near-zero raw IC after fillna(0)). MF-07 canonical lane EMPIRICALLY UNIMPLEMENTABLE on this panel at 1d-aggregate grain.
- **Plumbed for diagnostic**, NOT score-integrated.
- **References**: SP-B threshold_provenance section.

### `taker_skew_presettle_30d` (B5)

- **Mechanism family**: MF-15 (F62 sibling on flow side)
- **Source**: SP-B — F62 mechanism applied to taker_buy-sell flow side.
- **Status**: G1 fail + G6 fail.
- **Plumbed**, NOT score-integrated.

### `post_pump_stall_core_score_3d` (SP-K lead)

- **Mechanism family**: MF-08 event_impulse + MF-06 reflexive_flow + MF-10 higher_moment_fragility
- **Source**: SP-K small-cap post-pump short path. Per-subject event-state factor built from prior-day pump intensity and next-day continuation failure.
- **Status**: **lead SP-K candidate**. On `mid_tail_ex_majors`, `h5d`, admission extension clears `G1/G3/G6`: raw IC `+0.0411`, regime same-sign `1.00`, residual IC vs lsk3 `-0.0444`.
- **Cycle integration (2026-05-01)**: when stacked into the dedicated mid/tail score family, the full-contribution v1 variant improves fast-reject-lite walk-forward only marginally (`-0.608` -> `-0.603` median OOS Sharpe) and remains non-promotable. The clipped short-side-only v2 variant improves more materially to `-0.141`, but still fast-rejects.
- **Main-strategy overlay (2026-05-01)**: attached to the active `v6_h10d` parent on `liquid_perp_core_20`, short-side only, the low-weight overlays `w=0.05` and `w=0.10` both **validation-pass** and remain cycle-flat versus the parent (`walk_forward_median_oos_sharpe = 2.832`, loss-window fraction `0.3125`, positive-regime fraction `2/3`). The aggressive `w=0.15` version degrades the walk-forward median to `2.428`.
- **Trading-risk readout**: short baskets built from this family still receive funding about 70% of the time; v2 reduces 1d `>10%` squeeze frequency modestly (`4.94%` -> `4.66%`) at the cost of a slightly weaker 5d mean short payoff.
- **Overlay basket readout**: `w=0.10` is the current best exploratory weight. It nudges the parent short basket toward more mid-liquidity post-pump-stall names, improves next-10d short payoff slightly (`-0.17%` -> `-0.19%`), and does not worsen next-1d `>10%` squeeze frequency. The improvement is real but too small for promotion.
- **Main-strategy replacement / veto (2026-05-01)**: the lead short-slot rule `replace_mid_v1` is stronger than the smooth overlay. It keeps longs unchanged, replaces at most one marginal short from the bottom-6 pool, and **validation-passes** with walk-forward median OOS Sharpe `4.076` (vs baseline `2.832`), worst-regime `-1.783` (vs `-2.736`), and unchanged loss-window fraction `0.3125`. Selection changes occur on ~`52.7%` of timestamps and affect ~`17.6%` of all short slots.
- **Basket readout for `replace_mid_v1`**: the short basket shifts from `28.4%` to `42.5%` mid-liquidity names, next-10d mean short payoff improves from `-0.17%` to `-0.28%`, next-1d `>5%` squeeze frequency drops from `11.83%` to `11.44%`, and funding receive fraction rises from `75.8%` to `76.6%`.
- **Post-audit mainline correction (2026-05-03)**: the no-news SP-K replacement is retained as factor evidence and as a legacy comparator, but it is not the canonical h10d parent because it is built on `v6_h10d` + `regime_gating_v2`. The canonical parent is now `v5_rw_bridge_no_overlay_h10d`; SP-K follow-ons must attach there and pass fixed-set paired comparison plus overlay ablation before promotion.
- **Selected-short news-veto A/B (formal, 2026-05-01)**: after wiring the news-veto flags into the core feature-set builder, the selected-short variants `ss_veto_mini` and `ss_veto_adjudicated` both **validation-pass** on top of `replace_mid_v1_no_news`. They raise walk-forward median OOS Sharpe from `4.076` to `4.611`, but worsen loss-window fraction from `0.3125` to `0.34375`, worsen worst-regime median OOS Sharpe from `-1.783` to `-2.392`, and reduce validation Sharpe / net return from `2.400` / `0.228` to `2.121` / `0.181`.
- **Portfolio transmission is real, but the incremental replacements are poor**: the news layer now reaches actual selected shorts. `mini` labels hit about `21.1%` of selected-short rows across `47.3%` of timestamps; `adjudicated` hits `20.0%` / `45.4%`. Relative to `replace_mid_v1_no_news`, the two news-veto variants force `241` / `227` additional short-slot replacements, but those entered names are weaker shorts than the names they eject (mini entered next-10d mean `+0.78%` vs exited `-0.28%`; adjudicated entered `+0.80%` vs exited `-0.15%`).
- **Exposure-shape rerun (formal, 2026-05-02)**: treating adjudicated durable-news labels as a sizing problem works better than treating them as a replacement problem. `ss_do_not_fill_adjudicated` is clearly worse (`walk_forward_median_oos_sharpe = 2.755`, `loss_window_fraction = 0.375`, average short notional only `~80%` of baseline). `ss_reduced_exposure_adjudicated` is the cleanest news-aware landing shape so far: it fast-reject-passes with `walk_forward_median_oos_sharpe = 4.711`, `worst_regime_median_oos_sharpe = -1.769`, and preserves about `90%` of baseline short notional.
- **Why `reduced-exposure` still stops short of promotion**: versus `replace_mid_v1_no_news`, it still worsens `loss_window_fraction` from `0.3125` to `0.34375` and weakens weighted short-basket `next_10d_mean` from about `-0.28%` to `-0.23%`. So this is the strongest current news-aware shape, but not yet a better deployment than the no-news SP-K winner.
- **Why mini vs adjudicated still tie at strategy level**: the two corpora are no longer mechanically disconnected from the portfolio, but their differences do not improve the realized replacement choices enough to separate the cycle metrics under the current bottom-3 construction. Stronger adjudication helps the labels, not the present landing shape.
- **Lifecycle**: `research_only` for the current mainline. Code-plumbed in `features.py`, `feature_admission.py`, `deterministic_core.py`, `hypothesis_batch.py`, `execution_backtest.py`, and `lab.py`. Current owner-side read: SP-K is a valid factor family but not suitable as the current canonical strategy parent; `do-not-fill` is rejected, `reduced-exposure` stays exploratory, and selected-short news / MF-01 challenger layers remain research-only.
- **Sibling context**: `post_pump_stall_oi_score_3d` also passes factor-level admission in the same universe; `pump_exhaustion_recency_score_5d` and `pump_funding_oi_crowding_score_3d` remain secondary diagnostics.
- **References**: `small_cap_post_pump_short_proposal.md`; `small_cap_post_pump_event_study.json`; `post_pump_stall_cycle_increment_diagnostic.json`; `v6_h10d_post_pump_short_overlay_diagnostic.json`; `v6_h10d_post_pump_short_replacement_diagnostic.json`; `v6_h10d_post_pump_news_veto_ab_diagnostic.json`; `v6_h10d_post_pump_selected_short_news_veto_ab_diagnostic.json`; `v6_h10d_post_pump_selected_short_exposure_ab_diagnostic.json`.

### `post_pump_stall_oi_score_3d` (SP-K sibling)

- **Mechanism family**: MF-08 + MF-06
- **Source**: SP-K sibling that multiplies `post_pump_stall_core_score_3d` by positive OI expansion.
- **Status**: admission-pass sibling. On `mid_tail_ex_majors`, `h5d`, raw IC `+0.0417`, regime same-sign `1.00`, residual IC vs lsk3 `-0.0411`.
- **Lifecycle**: `plumbed_research_active`. Useful as a confirmation / comparison branch, but currently not stronger than core after cycle-layer evaluation.
- **References**: SP-K factor report and proposal addendum.

### `triangle_residual_60d` (F-triangle)

- **Mechanism family**: MF-04 (Funding-OI-Basis residual)
- **Source**: M2.4 — 3-equation OLS residual: funding_rate ~ α + β1×basis_proxy + β2×oi_change_5.
- **Status**: doc §E.11 PASS (no-arb relation residual mechanism) BUT G6 standalone fail (lsk3 saturation).
- **Plumbed**, NOT score-integrated.
- **Late-2026 audit**: G.5 `retired` (90d cum -0.0342); sanity check **likely_artifact_strong** (raw 60d -0.0418 ≥ G1 floor 0.04). Owner-side: keep but acknowledge non-promotion (raw signal real, residual blocked by lsk3).
- **References**: M2.4 threshold_provenance.

### `cross_venue_spot_dispersion` (M2.1 v1)

- **Mechanism family**: MF-05 cross_venue_inventory
- **Source**: M2.1 — multi-venue spot price dispersion via `coinapi_spot_sync.py`.
- **Status**: G6 fail (collinear with vol factors).
- **Currently NOT in features.py** (sync pipeline available but not productionized; column missing from rebuilt panel).
- **NOT score-integrated**. MF-05 lane needs SP-J cross-venue data productionization.

---

## D. Empirically falsified (mechanism-level rejection)

> All factors below have a `mechanism_falsified=True` flag in `factor_lifecycle.py` inventory. State machine recommends `retired` regardless of IC.

### `alt_basis_residual_after_btc_60d` (SP-D D2)

- **Mechanism family**: MF-04 cross-asset basis topology (doc §E.16)
- **Falsified by**: SP-D §E.16 falsification (KS / t-stat 1.39 < 2.0); admission G1 |IC| 0.0008 << 0.04 floor.
- **Conclusion**: §E.16 mechanism subsumed by F12 + funding_basis_residual_implied_repo_30 at 1d-aggregate panel grain.
- **References**: SP-D threshold_provenance section.

### `basis_propagation_lag_corr_30d` (SP-D D3)

- **Mechanism family**: MF-04 / MF-09
- **Falsified by**: SP-D §E.16; G1 |IC| 0.007 < 0.04. Sibling of D2.

### `btc_eth_corr_30d` (SP-E E1)

- **Mechanism family**: MF-09 cojump_contagion (regime gate variant)
- **Source**: SP-E — BTC-ETH 30d realized correlation; intended as universe-wide gating var per doc §E.17.
- **Falsified by**: SP-E §E.17 falsification — tertile-stratified IC ratio 0.90 (h5d) / 0.895 (h10d) **REVERSED** vs doc-prescribed ≥1.20. doc-mechanism direction is empirically inverted on this panel.
- **References**: SP-E threshold_provenance section.

### `expiry_window_x_rv20` (SP-H H3)

- **Mechanism family**: MF-08 (expiry hedge unwind)
- **Source**: SP-H — `expiry_window_indicator_5d × realized_volatility_20`.
- **Falsified by**: SP-H §E.15 KS-test p=0.128 > 0.05; G6 residual 0.018 < 0.02 (vol dimension absorbed by lsk3).
- **References**: SP-H threshold_provenance section.

---

## E. W1.1 / W3.x leftovers (admission-failed, plumbed for future)

### `funding_basis_residual_20` (F09)

- **Mechanism family**: MF-04
- **Source**: W1.1 — funding-basis residual at 20d.
- **Status**: G6 fail vs lsk3 (F12 absorbs).
- **Late-2026 audit**: G.5 `retired` (90d cum -0.0252); sanity check **likely_artifact** (raw 60d -0.0343 ≥ stable floor; raw signal real but residual blocked).

### `realized_skew_20_xs_z` (F31)

- **Mechanism family**: MF-10
- **Source**: W1.1 — cross-sectional z-score of realized skew over 20d.
- **Status**: G6 fail vs lsk3 (vol dimension absorbed).
- **Late-2026 audit**: G.5 `retired`; sanity check **likely_artifact** (raw 60d -0.0320 ≥ stable floor).

### `realized_kurt_20_xs_z` (F32)

- **Mechanism family**: MF-10
- **Status**: G6 fail; G.5 `retired`; sanity check **likely_artifact**.

### `vol_of_vol_60` (F35)

- **Mechanism family**: MF-10
- **Source**: W1.1 — rolling 60d std of realized_volatility (vol of vol).
- **Status**: G6 fail; G.5 `active` (60d resid -0.0171; barely above watch); sanity check not flagged. Slow-variable.

---

## F. Overlay components (in regime_gating.py, NOT in score)

> Overlay components affect position sizing via `regime_gating_v{1,2,3}_multiplier(t)` in [0.30, 1.00], multiplied into raw target weights. They do NOT enter score functions.

### `shock_co_occurrence_index` (F49)

- **Mechanism family**: MF-08 event_impulse
- **Role**: v1+v2+v3 overlay component. Throttle when shock fraction high.
- **Throttle slope**: -4.0 × F49; floor 0.30.
- **Source**: W3.1 / W3.5 v1.

### `co_jump_count_3d` (F26)

- **Mechanism family**: MF-09
- **Role**: v1+v2+v3 overlay. Throttle when 3-day cluster density high.
- **Throttle**: 1 - F26 / (N × 0.30); floor 0.30.
- **Source**: W3.2 / W3.5 v1.

### `dispersion_of_returns` (F44)

- **Mechanism family**: MF-11
- **Role**: v1+v2+v3 overlay. Floor when dispersion below 60d median.
- **Throttle**: F44 / median_60d, clipped [0.5, 1.0].
- **Source**: W3.3 / W3.5 v1.

### `btc_realized_volatility_20_quantile` (F55)

- **Mechanism family**: MF-10
- **Role**: v2+v3 overlay component. Throttle when BTC vol regime in top 30% quantile.
- **Throttle**: rolling 60d quantile rank of BTC RV20; component floor 0.5.
- **Source**: W3.5 v2.

### `trailing_universe_mean_return_30d`

- **Mechanism family**: composite (slow-grind regime detector)
- **Role**: v2+v3 overlay component. Throttle when 30-day mean universe return is sustained-negative.
- **Throttle**: 1 + 3.0 × cum_signal; component floor 0.5.
- **Source**: W3.5 v2 (slow-grind regime that v1 missed).
- **Why critical**: this is what made v2 successful — captures lsk3's specific failure mode (slow-grind bear regimes).

### `btc_dvol_range_z90`, `eth_dvol_range_z90` (SP-G)

- **Mechanism family**: MF-10 (vol of vol)
- **Role**: v3 overlay only. Throttle when DVOL intraday range z90 > 1.5.
- **Throttle**: 1 - max(0, z-1.5)/1.0, floor 0.7 per currency.
- **Lifecycle**: v3 overlay strict-passes but **CYCLE NEUTRAL** on v6_h10d (DVOL anomaly days don't overlap strategy losing days). Not promoted.
- **References**: SP-G threshold_provenance section.

---

## G. Cross-references summary

| sub-path | factors introduced | factors falsified | factors promoted | commit |
| --- | --- | --- | --- | --- |
| W1.1 (Phase 0) | F09, F11-F13, F16-F20, F31-F36 | F09/F16-20/F31/F32 | F12, F33 (into lsk3) | (legacy) |
| W3.1 | F46-F49 | F46/F47/F48 (initially) | F49 (into overlay v1) | (legacy) |
| W3.2 | F26-F29 | F27/F28 | F26 (overlay), F29 (v2) | (legacy) |
| W3.3 | F41-F45 | F41/F42/F45 | F44 (overlay) | (legacy) |
| W3.5 v1/v2 | F49+F26+F44 / +F55+trailing_return | — | overlay v1/v2 | (legacy) |
| M2.1 | cross_venue_spot_dispersion | M2.1 | — | (legacy) |
| M2.2 | F08 (funding_term_skew_60) | funding_term_kurt_60 | F08 (v4 experimental) | (legacy) |
| M2.3 | F62 (settlement_cycle_premium_60d) | — | F62 (v5 experimental) | (legacy) |
| M2.4 | triangle_residual_60d | (G6 fail) | — | (legacy) |
| **SP-A** | F-cascade (4 variants) | — | **F-cascade in v6 (active_alternative)** ⭐ | `977c1a0` |
| SP-B partial | B2/B3a/B3b/B5 | B2/B5 | B3a admitted but sibling-corr | `329a76b` |
| SP-C Phase 1 | (multi-horizon audit only) | — | F47 unlocked → v8 | `7199b89` |
| SP-C Phase 2 | (h10d cycle infra) | — | v6_h10d (preliminary) | `d587740` |
| SP-C Phase 3 | (sqrt-scaled v10_h10d) | — | **v6_h10d (active_alternative)** ⭐ | `472ea4a` |
| SP-D | D1/D2/D3 | **all 3** (§E.16 falsified) | — | `2cc580b` |
| SP-E | btc_eth_corr_30d | btc_eth_corr_30d (§E.17 falsified) | — | `f52aef7` |
| SP-G | DVOL extensions | — | overlay v3 (experimental, not promoted) | `f52aef7` |
| SP-F | F1/F2/F3 | F3 (G6 fail) | F1 (admitted but cycle non-additive in v9 experimental) | `237457f` |
| SP-H | H1/H2/H3 | **all 3** (§E.15 falsified) | — | `b3a69fb` |
| M2.5 | (factor_lifecycle infrastructure) | — | — | `cf3d2b7` |
| lsk3 diagnostic | — | (only `tt_smooth_5` + `momentum_decay_5_20` true regime shift) | (none demote needed) | `a340f87` |

---

## H. Mechanism family coverage status (2026-05-02)

| MF | family | productionized? | active in score | score-experimental |
| --- | --- | --- | --- | --- |
| MF-01 inventory_risk_transfer | Stage 0 + SP-L broad/narrow trials shipped; broad replacement non-additive, `mf01_spk_confirm_v1` changes `89` shorts but adds no cycle lift, `mf01_spk_ss_veto_v1` is a no-op, and `mf01_post_cascade_guardrail_v1` is sparse / AT-PAR | — | experimental confirmation / veto / guardrail rules only (not promoted) |
| MF-02 dealer_gamma | NO | — | — |
| MF-03 funding_microstructure | F08 ✓ | (in v4 experimental) | F1 (v9 experimental, cycle non-additive) |
| MF-04 carry_residuals | F12 ✓ + funding_basis_residual_implied_repo_30 ✓ | **lsk3 baseline** | (saturated; SP-D confirmed) |
| MF-05 cross_venue_inventory | M2.1 G6 fail | — | — (needs SP-J data uplift) |
| MF-06 reflexive_flow | F16-F20 admission-failed; taker_imb_dispersion ✓ in lsk3 | **lsk3 baseline** | — |
| MF-07 participant_disagreement | tt_smooth_5 ✓ in lsk3 | **lsk3 baseline** | (B2 1d failed; B3a sibling-corr) |
| MF-08 event_impulse | F49 in overlay; F47 in v8 | (overlay only); v8 experimental | — |
| MF-09 cojump_contagion | F29 in v2; F26 in overlay; momentum_decay_5_20 ✓ in lsk3 | **lsk3 baseline + overlay** | — |
| MF-10 higher_moment_fragility | F33 ✓ in lsk3; iv_smooth_60 + rv_5 ✓ | **lsk3 baseline** | — |
| MF-11 liquidity_migration | F44 in overlay; dh_5/dh_60 ✓ in lsk3 | **lsk3 baseline + overlay** | — |
| **MF-12 state_space_regime** | **F-cascade ⭐ (SP-A 解锁)** | **v6_h5d + v6_h10d active_alternative** | — |
| MF-13 stablecoin_plumbing | M3.2 admission winners now exist (`MF13_tron_flow_impulse_*`), but both regime-aware and local-gate A/B remain non-additive | — | admission-only / not promoted |
| MF-14 onchain_reflexivity | M3.2 admission winners now exist (`sell_pressure`, `capitulation_rebound`), but overlay + local-gate A/B remain no-material-change | — | admission-only / not promoted |
| MF-15 settlement_friction | F62 ✓ | — (v5 experimental) | — |
| MF-16 narrative_state | NO | — | — (needs M3.x NLP) |

**Coverage**: 9/16 MF families with at least one productionized factor; 11/16 now have at least one admission-grade or stronger research path; 6/16 in lsk3 baseline + overlay; 1/16 newly active (MF-12 via F-cascade).

---

## M3.2 first-pass audit (2026-05-02)

### Infrastructure

- `CryptoQuant` aggregate sync is live and default-root validated.
- `Alchemy` raw stablecoin lane and `CryptoQuant` aggregate lane are now fused into:
  - `artifacts/quant_research/onchain/m3_2_feature_panel_1d.csv`
- First admission run is recorded in:
  - `artifacts/quant_research/factor_reports/2026-05-02/m3_2_mf13_mf14_admission_report.json`

### Coverage caveat

- current live-verified CryptoQuant `supply` coverage is `usdt_eth + usdc + dai + tusd + usdt_trx + usdt_omni`
- current live-verified CryptoQuant `exchange-flow` coverage is `usdt_eth + usdc + dai + tusd`
- `usdt_trx` and `usdt_omni` are currently `supply-only` in the production sync because flow endpoints are not uniformly valid on those routes
- `usdc_eth` and `dai_eth` returned `400 invalid token`, so chain naming is mixed on the current endpoint surface
- the fused panel now starts at `2024-05-01`, decision dates start at `2024-05-02`, `tronscan_tron_flow_days = 730`, and `m3_2_panel_ready_days = 124`
- all `MF-13` conclusions below are still provisional / partial-coverage because the lane now has verified non-ETH USDT supply, but still lacks non-ETH USDT exchange-flow completion

### MF-13 / MF-14 candidate outcomes

| factor | horizon | active timestamps | verdict | G1 | G6 | read |
| --- | --- | --- | --- | --- | --- | --- |
| `MF13_supply_beta_gate_v1` | h5d | 25 | fail | -0.0333 | -0.0171 | no support |
| `MF13_supply_beta_gate_v1` | h10d | 23 | fail | -0.0266 | -0.0154 | no support |
| `MF13_flow_rotation_gate_v1` | h5d | 7 | strict_pass | -0.0173 | -0.0418 | sign-discovery only |
| `MF13_flow_rotation_gate_v1` | h10d | 6 | strict_pass | -0.0601 | -0.0351 | strong but **negative sign** |
| `MF13_flow_idio_gate_v1` | h5d | 7 | strict_pass | -0.1080 | -0.1064 | strong but **negative sign** |
| `MF13_flow_idio_gate_v1` | h10d | 6 | strict_pass | -0.1118 | -0.0913 | strong but **negative sign** |
| `MF13_tron_flow_impulse_defensive_beta_gate_v1` | h5d | 11 | strict_pass | +0.0803 | +0.0996 | first clean positive-sign non-ETH MF-13 winner |
| `MF13_tron_flow_impulse_defensive_beta_gate_v1` | h10d | 11 | strict_pass | +0.0409 | +0.0499 | positive-sign and still clean at longer horizon |
| `MF13_tron_flow_impulse_idio_gate_v1` | h5d | 11 | strict_pass | +0.0765 | +0.1008 | positive-sign TRON-triggered idio gate |
| `MF13_tron_flow_impulse_idio_gate_v1` | h10d | 11 | fail | -0.0083 | -0.0058 | short-lived, h10d does not hold |
| `MF13_tron_speculative_heat_defensive_beta_gate_v1` | h5d | 3 | strict_pass | +0.1107 | +0.0489 | strongest h5d trigger, but very sparse |
| `MF13_tron_speculative_heat_defensive_beta_gate_v1` | h10d | 3 | strict_pass | +0.2028 | +0.1078 | strongest residual read on current TRON trigger set, but very sparse |
| `MF14_sell_pressure_defensive_gate_v1` | h5d | 16 | strict_pass | +0.0834 | +0.0734 | clean early winner |
| `MF14_sell_pressure_defensive_gate_v1` | h10d | 16 | fail | +0.0780 | +0.0562 | positive but regime consistency breaks |
| `MF14_capitulation_rebound_idio_gate_v1` | h5d | 13 | strict_pass | +0.0433 | +0.0661 | broader supply set improves this lane |
| `MF14_capitulation_rebound_idio_gate_v1` | h10d | 12 | strict_pass | +0.0772 | +0.0870 | strongest residual read on current panel |

### MF-14 overlay A/B

- Formal overlay A/B is recorded in:
  - `artifacts/quant_research/factor_reports/2026-05-02/mf14_regime_gate_ab_diagnostic.json`
- `alpha_ontology_regime_gating_v2_mf14_sell_pressure_v1`:
  - `walk_forward_median_oos_sharpe = 2.832` (unchanged vs baseline)
  - `test_net_return` and `test_sharpe` are both worse than baseline
- `alpha_ontology_regime_gating_v2_mf14_rebound_release_v1`:
  - `walk_forward_median_oos_sharpe = 2.832` (unchanged vs baseline)
  - execution-layer degradation is larger than the sell-pressure variant

### MF-14 cross-sectional gate A/B

- Formal local-gate A/B is recorded in:
  - `artifacts/quant_research/factor_reports/2026-05-02/mf14_cross_sectional_gate_increment_diagnostic.json`
- `xs_alpha_ontology_v12_mf14_sell_beta_h10d`
- `xs_alpha_ontology_v12_mf14_sell_mid_short_h10d`
- `xs_alpha_ontology_v12_mf14_rebound_idio_h10d`
  - all three validation-pass
  - all three finish `no_material_change` on `walk_forward_median_oos_sharpe = 2.832`
  - all three reduce `test_net_return` by about `-0.0132`
  - all three reduce `test_sharpe` by about `-0.3357`
  - all three increase `test_max_drawdown` by about `+0.0187`

### MF-13 TRON local / regime-aware gate A/B

- Formal regime-aware overlay A/B is recorded in:
  - `artifacts/quant_research/factor_reports/2026-05-02/mf13_tron_regime_gate_ab_diagnostic.json`
- `alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1`:
  - validation-pass, but finishes `no_material_change` on `walk_forward_median_oos_sharpe = 2.832`
  - execution-layer read is worse than baseline: `delta_test_net_return = -0.0132`, `delta_test_sharpe = -0.3357`, `delta_test_max_drawdown = +0.0187`
  - overlay is likely too broad / too active for the parent strategy's current risk budget
- Formal local cross-sectional gate A/B is recorded in:
  - `artifacts/quant_research/factor_reports/2026-05-02/mf13_tron_cross_sectional_gate_increment_diagnostic.json`
- `xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d`:
  - fast-rejects with blocker `factor_evidence_lite_failed`
  - lite walk-forward metrics stay flat versus baseline (`walk_forward_median_oos_sharpe = 2.832`, `loss_window_fraction = 0.3125`)
  - `test_net_return` and `test_sharpe` weaken by about `-0.0132` / `-0.3357`
  - conclusion: the first clean positive-sign non-ETH `MF-13` admission winner is real, but the current cross-sectional landing still does not transmit to mother-strategy improvement

### Owner-side interpretation

- `MF-14` is the first family to show economically aligned, positive-sign admissions on the current fused panel.
- `MF-13` does show information, but current `flow-asymmetry` gates still come through with reversed sign and sparse active windows even after broadening the stablecoin token set into non-ETH USDT supply.
- `USDT_TRX` changes that read materially:
  - the first positive-sign `MF-13` winners on this lane are now **TRON-triggered cross-sectional gates**, not smooth market-wide supply states
  - `defensive beta under TRON flow impulse / speculative heat` is the clearest early pattern
  - however, both the first regime-aware overlay and the first local cross-sectional gate A/B remain non-additive / negative at the mother-strategy layer
  - `idio under TRON flow impulse` works at `h5d` but does not persist to `h10d`
  - the dominant risk is now **sparsity**, not reversed sign
- `MF-14` now has two positive-sign admission winners on the broader supply panel, but it still does **not** convert into a promotable landing shape:
  - neither `regime gate / sleeve multiplier` overlays nor `cross-sectional gate` score families improve the mother strategy
- The lane should stay in **exploratory admission** status until:
  - stablecoin coverage expands beyond the current ETH-native flow set into more decisive non-ETH stablecoin flow routes
  - at least one positive-sign `MF-13` candidate survives that broader universe and proves robust to a natural landing shape
  - at least one `MF-14` landing shape improves the mother strategy rather than only passing admission
