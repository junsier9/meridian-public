# SP-K Non-Kline Confirmation Stage 0

`Run date: 2026-05-07`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: no confirmation variant kept for strict falsification`

---

## Question

SP-K short replacement remains useful mechanism evidence, but the current
canonical-parent result is not promotable. This run asks whether CoinGlass /
non-kline sidecars can improve false-positive separation by allowing SP-K
replacement candidates only when a matching non-price confirmation state is
present.

The answer is **no for the first confirmation battery**. Several filters reduce
the replacement count and keep entered shorts negative, but none beats the raw
SP-K replacement on the required combined checks.

---

## Artifacts

- evaluator:
  `scripts/quant_research/evaluate_spk_non_kline_confirmation_stage0.py`
- unit tests:
  `tests/test_quant_spk_non_kline_confirmation_stage0.py`
- primary report:
  `artifacts/quant_research/factor_reports/2026-05-07-spk-non-kline-confirmation-stage0/spk_non_kline_confirmation_stage0.json`
- stdout/stderr logs:
  `artifacts/quant_research/factor_reports/2026-05-07-spk-non-kline-confirmation-stage0/run.stdout.log`
  and
  `artifacts/quant_research/factor_reports/2026-05-07-spk-non-kline-confirmation-stage0/run.stderr.log`

The evaluator does not mutate the parent or SP-K scoring functions. It uses the
existing SP-K replacement implementation with a variant-specific
`candidate_veto_column`.

---

## Baseline

Raw canonical-parent SP-K replacement on the same frame:

- total replacements: `571`
- entered short h10d mean: `-0.009062`
- exited short h10d mean: `-0.002691`
- entered next-1d squeeze `> 5%`: `0.0858`
- full selected short basket h10d mean: `-0.002781`

This baseline is the benchmark every non-kline confirmation must beat before
being considered for strict falsification.

---

## Confirmation Battery

| variant | verdict | replacements | entered h10d mean | entered 1d squeeze >5% | short-basket h10d mean | primary blockers |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `funding_oi_crowding_top_decile` | `stage0_watch` | 88 | -0.006694 | 0.0909 | -0.001941 | weaker entered shorts than raw SP-K; basket weaker; squeeze worse |
| `liquidation_cascade_exhaustion_top_decile` | `stage0_watch` | 84 | -0.007764 | 0.0833 | -0.002194 | weaker entered shorts than raw SP-K; basket weaker |
| `taker_orderbook_exhaustion_top_decile` | `stage0_watch` | 37 | -0.016913 | 0.1622 | -0.001544 | too few replacements; exited rows were better shorts; basket weaker; squeeze worse |
| `top_trader_fade_retail_chase_top_decile` | `stage0_watch` | 86 | -0.006249 | 0.1047 | -0.001406 | weaker entered shorts than raw SP-K; exited rows were better shorts; basket weaker; squeeze worse |
| `stablecoin_stress_context_top_decile` | `stage0_reject` | 0 | n/a | n/a | -0.001673 | no eligible replacement under ready-gated stablecoin confirmation |

No variant met the `stage0_keep_for_strict_falsification` threshold.

---

## Interpretation

The non-kline sidecars are real and available in the frame, but the first
confirmation shapes do not rescue SP-K on the current canonical parent:

- funding/OI crowding is directionally sensible but too weak versus raw SP-K;
- liquidation confirmation is the least bad filter, but it still weakens the
  selected short basket;
- taker/orderbook exhaustion finds some very negative entered shorts, but only
  `37` replacements and a worse next-day squeeze profile;
- top-trader fade / retail chase does not separate good replacements from bad
  ones;
- stablecoin daily context is not usable as a candidate-level confirmation in
  this landing shape.

This is a Stage 0 rejection, not a proof that every possible non-kline SP-K
interaction is impossible. It does close the generic "add non-kline
confirmation to SP-K replacement" branch for now.

---

## Decision

Do not promote any R-4 SP-K non-kline confirmation variant.

Do not run manifest A/B or strict falsification for these variants. Reopen R-4
only with a narrower, pre-registered mechanism that changes the landing shape
rather than simply vetoing replacement candidates with broad non-kline top
deciles.

Roadmap should move to the next lane: MF-05 sub-day venue stress or MF-01
orderbook / inventory, depending on which has the cleaner local data contract.
