Start with `AGENTS.md`; treat `PROJECT_STATE.md` as the canonical fact source and `CANONICAL_RUNBOOK.md` as the exact command source. `CLAUDE.md` is retained only as a legacy compatibility entrypoint and must defer to `AGENTS.md` on startup-role wording.

Precedence summary:
- `PROJECT_STATE.md` wins on checked-in facts, current stage, and accepted evidence.
- `config/project_governance/project_profile.json` and `config/project_governance/stage_contract.json` are the machine contracts for project identity and stage.
- `config/project_governance/runtime_ownership_contract.json` is the machine contract for runtime ownership phase and owner-verification enforcement state.
- `EnhengClaw` is a dual-track repo: framework plus research platform. Research may depend on framework governance/runtime code; framework code must not depend on research modules.
- The checked-in repo is at `stage_4_automated_execution` per `config/project_governance/project_profile.json`, but broad rollout and live order flow remain separately gated and fail-closed. Quant bridge publication follows `config/quant_research/publication_contract.json`: Stage 0/1 are archive-only, and Stage 4 outputs still require promotion-decision, hash/freshness, backend-mode, validation, and bridge-contract gates before any `_incoming_quant` publication.
- Before local commits, run `python scripts/verify/run_local_integrity_gates.py` to confirm `compileall`, JSON parsing, disk-integrity checks, and quant bridge-summary contract checks all stay green.
