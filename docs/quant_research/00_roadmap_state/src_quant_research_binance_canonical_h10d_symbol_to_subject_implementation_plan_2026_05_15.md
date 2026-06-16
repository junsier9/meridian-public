# src quant_research binance_canonical_h10d symbol_to_subject implementation plan

`Status: approved low-risk facade-first slice`
`Date: 2026-05-15`
`Scope: src/enhengclaw/quant_research/binance_canonical_h10d.py`

## Decision

Extract `symbol_to_subject(symbol: str) -> str` from
`binance_canonical_h10d.py` into the existing private helper module
`_binance_canonical_archive.py`, while keeping the root module facade import in
place.

This is a narrow archive/subject-normalization helper. It strips a trailing
`USDT` suffix after string coercion, whitespace trimming, and uppercasing. It is
not a formula scorer, funding-sync helper, PIT-universe helper, validation gate,
artifact writer, or runtime path helper.

## Evidence

- Current internal callers:
  - `build_symbol_feature_frame(...)` uses it to write the symbol audit
    `subject` field.
  - `_daily_bars_to_feature_panel(...)` uses it to derive the feature-panel
    subject.
- No repo-level direct import of `symbol_to_subject` was found outside
  `binance_canonical_h10d.py` during the dry-run scan.
- The helper belongs with `_read_kline_path`, `_coerce_kline_frame`, and
  `_summarize_symbol_audits` because those already represent the first
  archive-ingestion helper slice.

## Approved Change

- Add `symbol_to_subject` to
  `src/enhengclaw/quant_research/_binance_canonical_archive.py`.
- Re-export it through the existing import block in
  `src/enhengclaw/quant_research/binance_canonical_h10d.py`.
- Remove the local root implementation after the facade import is in place.

## Non-Goals

- Do not change `symbol_to_subject` semantics.
- Do not introduce broader exchange-symbol parsing.
- Do not move `_stable_hash`, `_stable_int`, `_write_json`,
  `_frame_or_empty`, `_default_run_id`, `_today_compact`,
  `_partition_month`, `_parse_date`, `_date_to_ms`, funding sync, PIT universe,
  validation, attribution, or reporting helpers in this slice.
- Do not change public CLI, manifest, or artifact paths.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_archive.py
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_binance_canonical_h10d.py -k "archive or symbol_feature" -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `binance_canonical_h10d.symbol_to_subject(...)` remains importable.
- `symbol_to_subject("btcusdt") == "BTC"` and
  `symbol_to_subject("ETH") == "ETH"` still hold.
- The archive helper module remains a narrow ingestion/normalization helper
  surface and does not absorb funding, PIT, validation, reporting, or runtime
  path policy.
