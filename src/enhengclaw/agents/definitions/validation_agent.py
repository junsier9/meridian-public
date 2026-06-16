from __future__ import annotations

from pathlib import Path

from enhengclaw.agents.definitions._controlled_slice import (
    build_governed_writable_slice,
    build_operator_review_surface,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "validation_agent.system.md"
SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.validation_agent.ValidationBlockerSignalDraft"
TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_signal_intake.submit_validation_signal"
REVIEW_SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.validation_agent.ValidationReviewDraft"
REVIEW_TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_session_views.inspect_validation_review"

VALIDATION_AGENT = build_governed_writable_slice(
    agent_id="validation_agent",
    description="Attach one bounded validation-blocker or publish-gate-hold signal to an existing research object without broadening runtime authority.",
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
