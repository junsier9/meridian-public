# AGENTS.md

`Context-Version: 2026-06-13.1`

`Meridian Alpha Platform` is a dual-track Python project, formerly `EnhengClaw`: `Agent Control Framework` plus `Research & Alpha Platform`. The checked-in repo is now at `Stage 4: Automated Execution` (`config/project_governance/project_profile.json.current_stage = stage_4_automated_execution`). Stage 4 is a governance/stage-contract fact, not a standing live-order authorization: broad rollout remains disabled, current remote timers are disabled/inactive, `live_delta_armed=false`, and live order flow still requires explicit owner arm/on-host gates.

## Read Order
- Read `docs/README_FOR_AGENT.md` first for the project map, glossary, artifact vocabulary, and failure-routing overview.
- Read `PROJECT_STATE.md` next for canonical checked-in facts, blockers, and accepted evidence.
- Read `CANONICAL_RUNBOOK.md` for exact commands and real-24h failure routing.

## Precedence Contract
- `README.md` is the project and developer entrypoint.
- `AGENTS.md` is the dense agent startup page.
- `CLAUDE.md` is a legacy compatibility entrypoint and must defer to `AGENTS.md` on startup-role wording.
- `PROJECT_STATE.md` is the canonical truth source.
- `CANONICAL_RUNBOOK.md` is the exact command source.
- External launcher or Cowork prompt injection must consume this disk file; the repo does not maintain a second `AGENTS.md` prompt copy.
- If summaries or chat history conflict with `PROJECT_STATE.md`, `PROJECT_STATE.md` wins.

## Artifact Vocabulary
- `<ArtifactsRoot>` means the operator-supplied root for the formal real-24h bundle only.
- `RunArtifactsRoot` means a generated per-run root for owner, review, demo, or readiness flows. Repo-local `artifacts\...` paths are examples, not required checkout state.
- `ObjectArtifactsRoot` means a generated per-object workbench root. Repo-local `artifacts\research_workbench\<object_id>` is one example, not a required path contract.

## Red Lines
- Never reintroduce `1800.0` into any real-24h acceptance path.
  Why: `1800.0` is the non-real default margin, not the 24h gate.
- Real-24h permit margin is `86460.0` (`24h + 60s`).
  Why: the 24h gate must reserve the full window plus boundary slack.
- Never use exit code alone as pass criteria.
  Why: a green rerun shell exit is necessary but the retained verdict files remain authoritative.
- Never read old `verify`, `smoke`, or unrelated `preflight` evidence for a rerun verdict.
  Why: the current rerun label is the only valid decision boundary.
- Never hand-edit docs or status files to force `READY_FOR_AGENT_LAYER`.
  Why: readiness is computed from acceptance evidence plus checked-in governance state.
- Execution permit and trust-root paths must stay outside the repo and outside temp paths.
  Why: those are host-side safety boundaries, not repo-owned fixtures.
- Preserve Binance preflight structured diagnostics:
  - `failure_category`
  - `transport_stage`
  - `endpoint`
  - `transport`
  - `host`
  - `port`
  - `exception_type`
  - `exception_message`
  - `exception_chain`

## Evidence Rules
- For real-24h preflight admission, read only `<ArtifactsRoot>\preflight_only\<PreflightLabel>\preflight_assertions.json` and require `all_green = true`.
- For real-24h rerun verdict, read only the current `<ArtifactsRoot>\soak_runs\<RerunLabel>\{go_no_go.json, soak_summary.json, provider_health_snapshot.json, audit_record.json}` bundle.
- Read `READY_FOR_AGENT_LAYER` and `READY_FOR_BROAD_AGENT_LAYER` from `go_no_go.json`; do not infer them from docs or prior thread state.
- Owner control-plane artifacts live under `RunArtifactsRoot\agent_owner\<run_id>\`; repo-local `artifacts\agent_owner\<run_id>\` is only one generated example.
