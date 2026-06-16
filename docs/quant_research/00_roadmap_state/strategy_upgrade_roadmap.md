# Cross-Sectional Strategy Upgrade Roadmap

`Context-Version: 2026-04-28.1`
`Owner: quant_research_maintainer`
`Status: historical_superseded`
`Historical Phase 0 baseline: xs_minimal_v3_h5d (v83 manifest), shadow_only`

> **Supersession note (2026-05-13):** This is the original multi-quarter
> strategy-upgrade spine and historical evidence map, not the current execution
> mainline. Start from
> [`quant_research_roadmap_state_2026_05_12.md`](../quant_research_roadmap_state_2026_05_12.md)
> for current state. The active frontier is the Binance-only PIT h10d
> challenger path; older `active` language below is preserved as historical
> context.
>
> **Manifest status note (2026-05-14):** The current `hypothesis_batch.py`
> runtime default is `cross_sectional_hypothesis_batch_manifest_v97.json`.
> The v83 manifest remains the Phase 0 documented baseline/static historical
> anchor, not the current runtime default.

This document was the canonical multi-quarter plan for upgrading the cross-sectional cryptocurrency alpha pipeline from the then-current `xs_minimal_v3_h5d` (v83) toy baseline to a production-ready strategy. It remains historical evidence for why later manifest tracks were pursued.

## Phase 0: Baseline (completed 2026-04)

**Phase 0 baseline artifact**: `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v83.json`

**Form**:
- 4 features (`realized_volatility_20`, `intraday_realized_vol_4h_to_1d`, `distance_to_high_20`, `coinglass_top_trader_long_pct`)
- Static linear z-score combination, hand-set weights `-0.30 / -0.25 / +0.25 / -0.20`
- Output: `tanh((percentile_rank(raw_score) - 0.5) * 1.80)`
- Portfolio: top-3 long-only equal-weight, 5-day non-overlapping rebalance
- Universe: `liquid_perp_core_20` (top-20 by 30d quote volume, top+mid liquidity buckets)

**Measured 3-year performance**:
- rank IC mean: +0.20
- rank IC positive day rate: 73%
- walk-forward median sharpe: +0.94 (lite v2 PASS)
- walk-forward loss window fraction: 41% (lite v2 PASS)
- regime worst median sharpe: -3.08 (advisory FAIL)
- test segment net return: -27% (strict execution_stress FAIL)
- max trade participation rate: 0.0334 (strict cap 0.005, FAIL by 6.7x)
- strict validation: FAIL

**Promotion state**: `shadow_only`. Cannot ship.

**Archived predecessors**: v1 through v82 are kept in `src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/` as the historical record of the search that produced v83. Disproved post-v83 candidates (v85, v86, v87, v88) remain in the parent directory as recent audit evidence and are referenced by `config/quant_research/threshold_provenance.md`.

**What is wrong with v83 (concise)**:
1. Single time scale (all 4 features at 20-day window)
2. Static hand-set weights, no IR-optimized or dynamic
3. No factor de-correlation (`realized_volatility_20` and `intraday_realized_vol_4h_to_1d` are highly redundant)
4. Top-3 equal weight (15% concentration in a 20-name universe, no risk model)
5. No drawdown control, no alpha decay tracking, no capacity-aware sizing
6. Single data class (OHLCV + derivatives + CoinGlass positioning)
7. Validation methodology has known sparse-window-sharpe noise (see `threshold_provenance.md` 2026-04-28 addendum)

The roadmap below addresses each weakness in dependency order.

---

## Phase 1: Factor engineering (3–4 weeks)

**Goal**: Expand from 4 static factors to ~30 de-correlated factors with dynamic IR-weighted blending.

**Expected gain**: rank IC 0.20 → 0.25–0.30, walk-forward median sharpe +0.94 → 1.5+, regime worst median sharpe -3.08 → -1.0 band.

### 1a. Multi-timescale expansion (1 week)

For each existing factor, replicate at three time scales (5d / 20d / 60d) — 12 raw factors total.

| family | 5d (short) | 20d (mid, current) | 60d (long) |
| --- | --- | --- | --- |
| realized_volatility | rv_5d | rv_20d | rv_60d |
| intraday_realized_vol | iv_5d | iv_20d | iv_60d |
| distance_to_high | dh_5d | dh_20d | dh_60d |
| coinglass_top_trader_long_pct | tt_5d | tt_20d | tt_60d |

**Mechanism**: short windows capture momentum/squeeze, long windows capture cycle position; multi-scale agreement is more stable than any single scale.

**Implementation**: extend `build_cross_sectional_feature_bundle` in `features.py` to emit the additional time-scale columns. New `xs_minimal_v4_score` function takes a 12-factor input.

### 1b. New factor families (2 weeks)

Add 8–10 factor families covering mechanisms not present in v83:

- **Momentum decay**: `momentum_5 - momentum_20` (short-term momentum weakening)
- **Quality**: `funding_rate * oi_change_5` (funding-rate-positioning crossing)
- **Liquidity stress**: `quote_volume_expansion * intraday_realized_vol_4h_to_1d` (anomalous flow + volatility)
- **Cross-section dispersion**: `vol_z_self - market_median_vol_z` (own volatility relative to market)
- **Order flow**: `coinglass_taker_imb_intraday_dispersion_24h` (already in selected columns, currently unused)
- **Funding crowding**: `funding_zscore_20 * abs(basis_zscore_20)` (rate crowding combined with basis tension)
- **Options skew**: BTC/ETH 25-delta put-call skew (requires Phase 4 data extension; can be deferred)

### 1c. Factor de-correlation (1 week)

- Compute rolling 60-day correlation matrix across the ~30 factor columns
- PCA: take top components capturing 80% cumulative variance (~10 PCs)
- GLS-residualize raw factors against the leading PCs to remove redundancy
- Equivalent gate in `feature_admission`: VIF > 5 → factor excluded

### 1d. Dynamic factor weights (1 week)

- Each 60 days, compute per-factor rolling IR (mean IC / std IC)
- New weight = `softmax(IR / temperature)` with temperature tuned so the top-5 factors carry ~70% weight
- **Critical constraint**: weight updates lag 5 days (prevent lookahead) and change at most 20% per update (prevent thrash)

### Phase 1 acceptance gates

- rank IC full-period >= 0.25 (v83: 0.20)
- walk-forward median sharpe >= 1.5 (v83: 0.94)
- regime worst median sharpe >= -1.0 (v83: -3.08)
- Strict validation may still FAIL (execution_stress, test net return) but research credibility materially strengthens.

### Phase 1 abort condition

If 30-factor expansion still gives rank IC < 0.22, factor space is saturated. Skip to Phase 4 (data source extension) before continuing.

---

## Phase 2: Portfolio construction (4–5 weeks)

**Goal**: Replace top-3 equal-weight with a fully risk-managed portfolio. Address v83's two structural failures: `execution_stress.max_trade_participation_rate = 0.0334` and `regime worst median sharpe = -3.08`.

**Expected gain**: execution_stress PASS, regime worst median sharpe halved on top of Phase 1 gain, capacity from ~$100k to ~$1M.

### 2a. Risk model (1.5 weeks)

- Estimate per-asset covariance matrix `Sigma_t` daily on a 60-day rolling window
- Apply Ledoit-Wolf shrinkage for stability
- Output: `Sigma_t` (20 x 20) and per-asset marginal volatility `sigma_i,t`

### 2b. Capacity-aware sizing (1 week)

For each asset, compute upper weight bound:

```
w_max_i = min( 1 / sqrt(N_active),
               participation_cap * ADV_i / capital )
```

with `participation_cap = 0.005` (strict gate threshold) and `ADV_i` = 30-day dollar volume.

This single change pulls `max_trade_participation_rate` from 0.0334 to <= 0.005.

### 2c. Mean-variance optimization (1.5 weeks)

Given alpha vector `alpha` (Phase 1 score) and risk model `Sigma`:

```
maximize  alpha' w  -  lambda * w' Sigma w
subject to:
  sum(w_i) = 1                       (full investment)
  0 <= w_i <= w_max_i                (long-only + capacity cap)
  sum(|w_i - w_prev_i|) <= 0.40      (turnover cap, vs current 1.0)
  N_active >= 5                      (force diversification, vs current 3)
```

`lambda` tuned so ex-ante portfolio volatility is approximately 8% annualized.

Implementation: use `cvxpy` solver. Per-day cost ~5 seconds; per 30-day walk-forward window ~2.5 minutes total.

### 2d. Drawdown-conditional throttle (1 week)

- Track portfolio rolling 30-day drawdown in real time
- DD > 5% → all positions x0.5
- DD > 10% → all positions x0.0 (full exit, re-arm only after DD < 5%)

This is the minimum risk-off mechanism; v83 has none.

### 2e. Trade execution model (config-only, no new code)

- `max_turnover_per_rebalance: 1.0 → 0.40` (annualized turnover 73x → 29x)
- `latency_bars`: keep at 1 (current default)
- `participation_cap`: 0.005 (already enforced via 2b)

### Phase 2 acceptance gates

- `max_trade_participation_rate <= 0.005` → execution_stress PASS
- regime worst median sharpe >= -0.5 (Phase 1: -1.0)
- max_drawdown <= 12% under DD-throttle
- test segment net return turns positive (v83: -27%)
- At least 2 of 4 strict gates PASS (factor_evidence + execution_stress as the highest-confidence pair)

### Phase 2 abort condition

If after the optimizer the walk-forward sharpe is < 1.0, Phase 1 alpha is not stable enough. Return to Phase 1 and add more factors before continuing Phase 2.

---

## Phase 3: Alpha lifecycle (2–3 weeks)

**Goal**: Build "alpha decay detection + automatic position throttling + retirement" mechanisms. This is the production-required "knows when to stop" capability.

### 3a. IC tracker (1 week)

- Daily, record portfolio realized rank IC (per-day score vs forward 5d return)
- Compute 30 / 60 / 90-day rolling IC and t-statistic
- Trigger ladder:
  - `IC_60d < 0.05` → state `decaying`, positions x0.5
  - `IC_60d < 0` → state `retired`, full exit + audit review

### 3b. Regime-aware risk multiplier (1.5 weeks)

Do not regime-switch the score (the v82 ensemble approach was disproved). Instead, regime-aware sizing:

- Compute BTC 5-day realized volatility daily
- Compute current regime quantile against trailing 252-day distribution
- regime quantile > 80% (high vol) → positions x0.7
- regime quantile > 90% (extreme) → positions x0.4

The multiplier uses BTC vol (a universe-wide signal not in the per-asset score), so no lookahead.

### 3c. Capacity dashboard (0.5 weeks)

- Daily snapshot: each held position's `trade_participation_rate` at the current capital level
- Early warning: if any position approaches `participation_cap * 0.6`, trigger universe trim
- Output: `artifacts/quant_research/strategy_capacity/<as_of>/capacity_snapshot.json`

### Phase 3 acceptance gates

- IC tracker historical replay: timely throttle on real declines (e.g. v83 showed IC_60d = 0.011 in 2024Q4; tracker should have triggered 50% throttle)
- regime-aware multiplier brings worst regime sharpe >= 0
- All 4 strict gates PASS

---

## Phase 4: Data source extension (6–8 weeks, can run in parallel with Phase 1–3)

**Goal**: Expand from 1 data class (OHLCV + derivatives + CoinGlass positioning) to 3+ classes.

**Expected gain**: rank IC 0.25 → 0.35+, alpha source diversification reduces single-data-source-failure risk.

### 4a. On-chain (2 weeks)

- Glassnode and / or CryptoQuant API integration
- Indicators: exchange net flow, SOPR (Spent Output Profit Ratio), stablecoin supply ratio, whale wallet activity (>1000 BTC transfers)
- Add 4–6 on-chain factor families, each multi-scale per Phase 1 structure

### 4b. Options skew (2 weeks)

- Deribit API integration for BTC and ETH option chains
- Daily indicators: 25-delta put-call skew (front-month, mid-month), IV term structure slope, realized-implied vol spread
- Universe-wide signals (not per-ticker), enter the score as modulation factors

### 4c. Microstructure (2 weeks)

- Binance L2 order book 5-minute snapshots
- Indicators: top-of-book imbalance, depth-weighted imbalance, aggressive taker flow ratio
- Aggregate to 1h or daily before entering the score

### 4d. Cross-asset spillovers (1.5 weeks)

- DXY, Gold, SPX, US 10y yield - lagged correlations to crypto
- Per-asset 60-day beta to each cross-asset variable
- Add 4 cross-asset modulation factors

### Phase 4 acceptance gates

- rank IC after Phase 1 + 4 expansion >= 0.35
- Factor families 30 → 50
- At least 3 data classes each contribute independent IC > 0.05 (after orthogonalization)

### Phase 4 abort per-stream

Any data source whose IC < 0.03 after orthogonalization → discard that stream.

---

## Phase 5: Model upgrade (4–6 weeks; only after Phases 1–4 are shipped)

**Goal**: Move from static linear to ensemble. Order matters: skipping to Phase 5 before Phase 1 is exhausted is what failed in the v86 boosted-tree experiment.

**Expected gain**: rank IC 0.35 → 0.40+, but more importantly stability improvements.

### 5a. Linear ensemble (2 weeks)

Three sub-models, each linear in the Phase 1+4 factor space:

- **Long-window linear**: weights from 60-day IR
- **Short-window linear**: weights from 5-day IR (more reactive)
- **Cross-section dispersion linear**: factor weights based on z-score against market median

Final score = mean of the three sub-models' percentile ranks, then `tanh`.

### 5b. Walk-forward retraining cadence (1 week)

- Current Phase 1d retrains weights every 60 days
- Move to every 5 days with 60-day EMA smoothing on weights
- Tighter cadence captures alpha drift; smoothing prevents over-reaction

### 5c. Bayesian shrinkage (1.5 weeks)

- Replace pure-IR weights with Bayesian posterior:
  - prior: equal weights
  - likelihood: per-factor 60-day IC scaled by sample size
  - posterior: maximum a posteriori (MAP) shrinkage
- Eliminates IR-estimation noise driving weight oscillation

### 5d. Optional simple neural net (1.5 weeks; only if 5a–5c shipped)

- 1-hidden-layer MLP (64 units), input is the ~50-factor z-score vector, output is predicted rank
- Compare to ensemble 5a; require sharpe improvement >= 20% to adopt
- If insufficient, stop and stay on the linear ensemble (v86 already showed deep models do not help on the current narrow feature space)

### Phase 5 acceptance gates

- Full-period walk-forward median sharpe >= 2.5
- Per-month IC variance reduced >= 30% relative to Phase 3 baseline
- All 3 regime windows have sharpe >= 0.5

### Phase 5 abort condition

Ensemble's sharpe improvement over Phase 1+2+3 baseline < 20% → ROI insufficient, stay on the linear path.

---

## Phase 6: Production hardening (3 weeks; must be last)

**Goal**: Convert the research system into a 24/7 production system. This is the prerequisite step before Stage 4 automated execution per `CLAUDE.md`.

### 6a. Real-time inference loop (1.5 weeks)

- Daily UTC close → run inference
- Write predicted positions to `artifacts/quant_research/strategy_signals/<as_of>/predictions.json`
- Integrate with existing `bridge.py` daily cycle framework

### 6b. Risk monitoring (1 week)

- Real-time tracking:
  - Current PnL vs expected (from inference)
  - Held positions vs predicted positions (slippage in execution)
  - Capacity utilization
  - Drawdown
- Trigger conditions → automatic position throttling, pause, or operator alert

### 6c. Production audit (0.5 weeks)

- Daily generation of `daily_strategy_audit.json`:
  - Decision timestamp
  - Score distribution snapshot
  - Portfolio selections
  - Execution simulation
  - Comparison vs previous day
- This is mandatory evidence for Stage 3 → Stage 4 promotion.

### Phase 6 acceptance gates

- Real-time inference produces signals matching offline cycle within 1bp
- Risk monitor catches at least one synthetic adverse event per integration test
- Production audit JSON validates against schema for 30 consecutive days

### Phase 6 abort condition

If production audit shows divergence > 10% from offline simulation, the simulation model itself is wrong → return to Phase 5 and fix before continuing.

---

## Total timeline

| Phase | effort | cumulative | key milestone |
| --- | --- | --- | --- |
| Phase 1 (factor engineering) | 3–4 weeks | 4 weeks | rank IC >= 0.25 |
| Phase 2 (portfolio construction) | 4–5 weeks | 9 weeks | execution_stress PASS |
| Phase 3 (alpha lifecycle) | 2–3 weeks | 12 weeks | all 4 strict gates PASS |
| Phase 4 (data extension) | 6–8 weeks (parallel) | 12 weeks | rank IC >= 0.35 |
| Phase 5 (model upgrade) | 4–6 weeks | 18 weeks | sharpe >= 2.5 |
| Phase 6 (production hardening) | 3 weeks | 21 weeks | Stage 4 ready |

Approximately 5 months of full-time engineering to move from v83 toy strategy to production-deployable.

---

## Recommended near-term sequencing

**Weeks 1–9**: Phase 1 + Phase 2 in series. This produces the first strict-FULL-PASS candidate on disk. v83 → vNN (next manifest version after Phase 2 ships) becomes the first ship-ready candidate.

**Decision point at week 9**: Does vNN survive shadow_only OOS for 30 calendar days at predicted sharpe? If yes, proceed to Phase 3. If no, return to Phase 1 with the gap analysis.

**Weeks 10–12**: Phase 3 (alpha lifecycle).

**Beyond week 12**: Phase 4 / 5 / 6 are conditional on results. Phase 4 can also start in parallel after week 4 if data engineering bandwidth is available.

---

## Cross-references

- Phase 0 baseline manifest: [src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v83.json](../../../src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v83.json)
- Audit history: [config/quant_research/threshold_provenance.md](../../../config/quant_research/threshold_provenance.md)
- Lite contract: [config/quant_research/fast_reject_contract.json](../../../config/quant_research/fast_reject_contract.json) (v2)
- Strict contract: [config/quant_research/validation_contract.json](../../../config/quant_research/validation_contract.json) (v8, unchanged in 2026-04 refactor)
- Phase 0 archive: [src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/README.md](../../../src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/README.md)
- Disproved post-v83 candidates remain in the package root as audit evidence: v85 (1d horizon), v86 (HistGradientBoosting), v87 (vol-weighted top-5), v88 (vol-weighted top-3).
- Forward-looking factor ontology, library, and 90-day frontier program (complement to this roadmap; covers the *what* of Phase 1 / Phase 4): [alpha_ontology_and_factor_library.md](alpha_ontology_and_factor_library.md)
