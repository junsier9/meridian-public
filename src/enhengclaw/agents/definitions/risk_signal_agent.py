from __future__ import annotations

from pathlib import Path

from enhengclaw.agents.definitions._controlled_slice import build_governed_writable_slice

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "risk_signal_agent.system.md"
SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.risk_signal_agent.RiskSignalDraft"
TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_signal_intake.submit_risk_signal"

RISK_SIGNAL_AGENT = build_governed_writable_slice(
    agent_id="risk_signal_agent",
    description="Attach one bounded risk or invalidation signal to an existing research object without broadening runtime authority.",
    prompt_path=PROMPT_PATH,
    schema_entrypoint=SCHEMA_ENTRYPOINT,
    tool_entrypoint=TOOL_ENTRYPOINT,
    slice_mode="continue_existing_object",
    canonical_runtime_boundary="runtime.continue_existing_from_agent_payloads",
)
