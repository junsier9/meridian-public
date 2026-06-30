# Public Mirror — Sanitization Manifest

This repository is a **sanitized public mirror** of a private quant-trading platform. It exists to share the
engineering and architecture. It is **not** runnable as a live trading strategy as-published, by design.

## What was removed or redacted

| Item | Action | Why |
|---|---|---|
| Fitted 12-factor frozen-frontier weights | Zeroed placeholders (`feature_weights` → `0.0`) | The fitted vector is the live edge |
| Research weight/IC ontology (`alpha_ontology_v3_weights.json`) | Numeric research stats zeroed | Proprietary research output |
| `artifacts/` (alpha cards, backtests, governance/registry/assessments) | Excluded (kept a stub `README.md`) | Research evidence / strategy IP |
| `docs/live_trading/` operational logs (runbooks, arm handoffs, owner attestations, balance snapshots) | Excluded (kept a stub `README.md`) | Operator-private operational records |
| Modular live-state / governance registries (`current_state.json`, `live_strategy_baseline_registry.json`, `remote_endpoint_registry.json`, `run_log_index.json`, `live_gate_registry.json`, and the other `config/project_governance/*_registry.json`) | Excluded | Carry live endpoints/IPs, run history, config hashes, and current live-strategy identity — operator-private current state, not architecture |
| Production host IP, internal/VPS IPs, SSH targets | Replaced with RFC 5737 documentation IPs (`203.0.113.x`, `198.51.100.x`) | Real infrastructure |
| Wallet / equity / allocated-capital balances | Replaced with round placeholders | Real account data |
| Operator username and GitHub handle | Genericized in paths and ownership lines | Personal identifiers |
| Source-file UTF-8 BOMs | Stripped | Cleanliness / tooling correctness |

## What was kept

- All application **code** under `src/` (including the live-trading algorithm and engine), `tests/`, and `scripts/`.
- Architecture / research **design docs** (`docs/quant_research/`, governance/templates, root docs).
- **Config structure** (live-trading and research configs) with monetary/weight values replaced by placeholders.
- The 5-factor baseline scoring weights (`BINANCE_OHLCV_CORE_WEIGHTS`), which are a published baseline.

## Secrets

No API keys, secrets, tokens, or private keys were ever committed to the source history. Provider credentials are
read from environment variables at runtime; see [`.env.example`](.env.example) for the variable names (values are
intentionally blank).

## Tests

The deterministic Linux contract gates in [`.github/workflows/boundary-gates.yml`](.github/workflows/boundary-gates.yml)
pass on this mirror. Contract tests that validate the excluded research artifacts skip themselves when those
artifacts are absent.

## Mirror refreshes

- **v0.2.0 (2026-07-01)** — Added a sanitized plain-language methodology overview of the current live
  cross-sectional strategy ([`docs/strategy/current24_dynamic_lpf_overview.md`](docs/strategy/current24_dynamic_lpf_overview.md))
  and documented the exclusion of the modular live-state / governance registries. The repository remains a
  point-in-time **architecture** snapshot; live current-state, performance, fitted weights, and infrastructure
  stay operator-private.
- **v0.1.0 (2026-06-17)** — Initial sanitized public mirror.
