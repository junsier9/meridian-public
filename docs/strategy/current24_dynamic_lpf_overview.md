# Strategy Overview — *current24 dynamic-LPF*

> A plain-language methodology overview of the current live cross-sectional
> strategy on Binance USD-M perpetual futures. **Sanitised:** this document
> describes the *approach and architecture* only. Fitted factor weights,
> regime-overlay thresholds, live performance numbers, and infrastructure
> details are operator-private and are intentionally **not** included in this
> public mirror (see [`PUBLIC_MIRROR.md`](../../PUBLIC_MIRROR.md)).

## What it is

`current24 dynamic-LPF` is a systematic, daily, **cross-sectional** relative-value
strategy on Binance USD-M perpetual futures. It runs a deliberate **net-short**
posture (market-aware, not market-neutral). The internal identity is
`h10d_dynamic_lpf_current24_pitrolling_top20_learned_prior_dth60`; "LPF" denotes
the *Long-Positive-Funding*, asymmetric net-short construction.

## Economic thesis

Crypto perpetual futures are dominated by leverage-seeking retail flow. Crowded
long positioning persistently **pays funding** and tends to **mean-revert**. A
disciplined short leg, restricted to mid-liquidity names where the effect is
strongest, harvests that contrarian funding-and-reversion premium. The edge is
behavioural and structural (leverage demand never clears) and is capacity-limited,
which is why it is not fully arbitraged away.

## Pipeline

```
Market data (Binance USD-M + CoinGlass)
   -> 12 cross-sectional factors
   -> point-in-time rolling universe (top-20 of a 24-candidate allowlist)
   -> ridge-with-learned-prior scorer (+ momentum clip)
   -> DTH60 regime overlay
   -> asymmetric net-short LPF construction
   -> multiphase 10-sleeve execution (cost-aware)
   -> governed, fail-closed live deployment
```

## Signal set — 12 factors (half are derivatives-microstructure)

**Microstructure / derivatives (6):** top-trader long-account share, taker
order-flow imbalance dispersion, funding x open-interest quality, funding-basis
implied-repo residual, settlement-cycle premium, quote-volume x implied-vol
liquidity stress.

**Price / volatility (5):** distance-to-high (60d and 5d), short-horizon realised
volatility, intraday 4h-to-1d realised-vol regime, downside/upside vol ratio.

**Momentum (1):** 5d-minus-20d momentum decay (contribution clipped).

Each factor is z-scored cross-sectionally each day; the model ranks names relative
to peers rather than in absolute units. (The *names* and *definitions* live in the
codebase; the fitted weights are zeroed in this public mirror.)

## Model

A **ridge regression shrunk toward an economically-signed learned prior** with a
weight cap and a momentum-contribution clip. It is deliberately **linear and
interpretable**: in research, frozen weights and freshly-learned weights perform
comparably, so the team kept the simple model — added complexity did not improve
robust out-of-sample behaviour. The performance driver is the *construction*, not
weight complexity.

## Construction

An asymmetric, net-short book: a small **half-weighted long leg** tilted toward
positive funding, a **cash sleeve** that holds the undeployed long capital, and a
**short leg** of the lowest-scored mid-liquidity names. Research attribution shows
the **short leg is the alpha workhorse**; the cash sleeve manages a structurally
weak long leg. Position sizing is gross-normalised.

## Regime overlay (DTH60)

Cross-sectional mean-reversion fails during market-wide co-shocks. The overlay
neutralises the distance-to-high mean-reversion factor for a name when either a
market co-shock index exceeds a **frozen, point-in-time** threshold, or the name
is simultaneously near its own high and crowded long. Thresholds are frozen on the
training window (no look-ahead).

## Execution

The book is executed as **10 daily-staggered sleeves**, each holding 10 days, so
the live book is the trailing average of the last 10 daily target books — a
TWAP-like schedule that spreads each rebalance over 10 days to cut per-day
participation and market impact.

## Validation discipline

Point-in-time rolling universe, walk-forward refit, an untouched hold-out window,
frozen overlay thresholds, leakage audits, and a no-order parity audit (research
replays generate zero live orders). Honest limitations are documented internally:
a relatively short effective sample, single-name short concentration as the
headline risk, mid-liquidity capacity limits, and regime dependence. The
deployable risk control is **short-leg diversification**.

## Governance

The system is deployed **fail-closed**: dormant and unarmed between authorised
windows, with no order flow without explicit owner, on-host, budget-epoch, and
timer-gate authorisation. Loss is bounded by an unattended budget ceiling, a
terminal disarm kill-switch, a per-order ceiling, and equity-scaled wallet caps.

---

*Related code:* `src/enhengclaw/live_trading/` (engine, scorer, construction,
risk controls), `src/enhengclaw/quant_research/` (features, backtest),
`config/quant_research/frontier_12factor/` (12-factor frontier contract — weights
redacted in this mirror).
