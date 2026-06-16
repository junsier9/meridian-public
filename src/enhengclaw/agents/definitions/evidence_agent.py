from __future__ import annotations

from pathlib import Path

from enhengclaw.agents.definitions._controlled_slice import build_governed_writable_slice

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "evidence_agent.system.md"
SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.evidence_agent.EvidenceSignalDraft"
TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_signal_intake.submit_evidence_signal"

EVIDENCE_AGENT = build_governed_writable_slice(
    agent_id="evidence_agent",
    description="Attach one bounded follow-up evidence signal to an existing research object through agent ingress.",
    prompt_path=PROMPT_PATH,
    schema_entrypoint=SCHEMA_ENTRYPOINT,
    tool_entrypoint=TOOL_ENTRYPOINT,
    slice_mode="continue_existing_object",
    canonical_runtime_boundary="runtime.continue_existing_from_agent_payloads",
)
