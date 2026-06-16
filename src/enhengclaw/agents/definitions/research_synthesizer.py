from __future__ import annotations

from pathlib import Path

from enhengclaw.agents.definitions._controlled_slice import (
    build_governed_writable_slice,
    build_operator_review_surface,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "research_synthesizer.system.md"
SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.research_synthesizer.ResearchSynthesisSignalDraft"
TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_signal_intake.submit_research_synthesis_signal"
REVIEW_SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.research_synthesizer.ResearchSynthesisDraft"
REVIEW_TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_session_views.inspect_research_synthesis"

RESEARCH_SYNTHESIZER_AGENT = build_governed_writable_slice(
    agent_id="research_synthesizer",
    description="Attach one bounded synthesis-preview or thesis-risk signal to an existing research object without mutating the thesis graph directly.",
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
