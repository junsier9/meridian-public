# MF-05 Venue-Local Data Gate

`Run date: 2026-05-07`
`Parent boundary: v5_rw_bridge_no_overlay_h10d is not modified`
`Status: blocked for alpha rerun; data sidecar exists but remains pre-concordance`

---

## Question

R-5 asks whether MF-05 can be reopened as a sub-day venue-local stress lane
instead of repeating the older failed 1d cross-venue dispersion shape.

This gate asks the data-admission question first:

> Is the new 1h venue-concentration sidecar trusted enough to run MF-05 alpha
> validation?

The answer is **no**. The sidecar is a useful data unlock, but it is still
pre-concordance and cannot support alpha admission or h10d sidecar promotion.

---

## Artifacts

- data-gate evaluator:
  `scripts/quant_research/audit_mf05_venue_local_data_gate.py`
- unit tests:
  `tests/test_quant_mf05_venue_local_data_gate.py`
- primary report:
  `artifacts/quant_research/factor_reports/2026-05-07-mf05-venue-local-data-gate/mf05_venue_local_data_gate.json`
- input sidecar:
  `artifacts/quant_research/sidecars/venue_concentration_1h/venue_concentration_1h_sidecar.csv.gz`
- upstream sidecar build report:
  `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/venue_concentration_1h_sidecar_build_report.json`

---

## Sidecar Coverage

The sidecar contains:

- rows: `135,116`
- subjects: `30`
- venues configured: Binance, Coinbase, OKX, Bybit spot
- row trust status: `pre_concordance` for all rows
- research validation status: `not_started` for all rows
- multi-venue row fraction: `30.84%`
- three-plus-venue row fraction: `26.40%`
- four-venue row fraction: `9.97%`

The data is enough to describe venue concentration, but not yet enough to
trust venue concentration as an alpha input.

---

## Concordance Check

The audit compared CoinAPI Binance spot `1h` rows against the local native
Binance spot `1h` cache for the sidecar symbols.

Result:

- Binance close p95 absolute pct difference: `~0.0000`
- Binance quote-volume median absolute pct difference: `0.0009`
- Binance quote-volume p95 absolute pct difference: `0.0850`

This clears the current Binance sanity threshold, so Binance itself is not the
blocking issue.

The hard blocker is multi-venue trust:

- no native OKX local source was found for concordance;
- no native Bybit local source was found for concordance;
- no native Coinbase local source was found for concordance;
- the OKX / Bybit / Coinbase rows are sidecar input sources from CoinAPI, not
  independent native venue checks.

---

## Decision

`alpha_rerun_allowed = False`

Blockers:

- `sidecar_rows_pre_concordance`
- `sidecar_research_validation_not_started`
- `missing_native_okx_bybit_coinbase_concordance_sources`

Do not run MF-05 alpha validation or SP-K / h10d sidecar admission from this
sidecar yet. R-5 can reopen only after native multi-venue concordance exists or
after the research question is explicitly reframed as a data-quality / provider
coverage study rather than alpha validation.

The next roadmap step should move to R-6 MF-01 orderbook / inventory, because
that lane already uses local CoinGlass microstructure fields with clearer
single-provider provenance.
