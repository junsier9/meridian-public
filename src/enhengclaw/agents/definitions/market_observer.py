from __future__ import annotations

from pathlib import Path

from enhengclaw.agents.definitions._controlled_slice import build_governed_writable_slice

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "market_observer.system.md"
SCHEMA_ENTRYPOINT = "enhengclaw.agents.schemas.market_observer.MarketObserverSignalDraft"
TOOL_ENTRYPOINT = "enhengclaw.agents.tools.runtime_signal_intake.submit_market_observer_signal"

MARKET_OBSERVER_AGENT = build_governed_writable_slice(
    agent_id="market_observer",
    description="Convert one bounded market observation into a governed runtime ingress payload.",
    prompt_path=PROMPT_PATH,
    schema_entrypoint=SCHEMA_ENTRYPOINT,
    tool_entrypoint=TOOL_ENTRYPOINT,
    slice_mode="create_new_object",
    canonical_runtime_boundary="runtime.run_new_from_agent_payloads",
)
