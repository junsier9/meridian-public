Locked decisions:
- real-24h permit margin = 86460.0 across real-24h / preflight-only / wrapper / PowerShell / run_config / preflight evidence; READY_FOR_AGENT_LAYER stays false.
- rerun allowed only if <ArtifactsRoot>\preflight_only\<PreflightLabel>\preflight_assertions.json has all_green=true and <RerunLabel> != <PreflightLabel>.
Current blockers:
- explicit ExecutionPermitPath missing
- trust root missing
- Binance websocket preflight timeout at data_wait
Canonical command source:
- Exact commands live in CANONICAL_RUNBOOK.md
Next exact action:
- Populate <ExecutionPermitPath>, <ArtifactsRoot>, <TrustRootDir>, <PreflightLabel>, <RerunLabel>; run preflight-only; stop unless all_green=true; then run rerun and read only <ArtifactsRoot>\soak_runs\<RerunLabel>.
