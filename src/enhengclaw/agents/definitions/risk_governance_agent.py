from __future__ import annotations

from pathlib import Path

from enhengclaw.agents.definitions._controlled_slice import (
    build_governed_writable_slice,
    build_operator_review_surface,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "risk_governance_agent.system.md"
SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.risk_governance_agent.RiskGovernanceSignalDraft"
TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_signal_intake.submit_risk_governance_signal"
REVIEW_SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.risk_governance_agent.RiskGovernanceReview"
REVIEW_TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_session_views.inspect_risk_governance_review"

RISK_GOVERNANCE_AGENT = build_governed_writable_slice(
    agent_id="risk_governance_agent",
    description="Attach one bounded governance-pressure or suppression-required signal to an existing research object without broadening runtime authority.",
    prompt_path=PROMPT_PATH,
    schema_entrypoint=SCHEMA_ENTRYPOINT,
    tool_entrypoint=TOOL_ENTRYPOINT,
    slice_mode="continue_existing_object",
    canonical_runtime_boundary="runtime.continue_existing_from_agent_payloads",
    operator_review_surface=build_operator_review_surface(
        schema_entrypoint=REVIEW_SCHEMA_ENTRYPOINT,
        tool_entrypoint=REVIEW_TOOL_ENTRYPOINT,
    ),
)
