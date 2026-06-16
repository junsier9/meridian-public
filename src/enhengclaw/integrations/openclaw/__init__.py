from __future__ import annotations

from enhengclaw.integrations.openclaw.market_observer import (
    OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
    OpenClawMarketObserverRequest,
    OpenClawMarketObserverResponse,
    run_openclaw_market_observer,
)
from enhengclaw.integrations.openclaw.evidence_agent import (
    OPENCLAW_EVIDENCE_AGENT_CONTRACT_VERSION,
    run_openclaw_evidence_agent,
)
from enhengclaw.integrations.openclaw.risk_signal_agent import (
    OPENCLAW_RISK_SIGNAL_AGENT_CONTRACT_VERSION,
    run_openclaw_risk_signal_agent,
)
from enhengclaw.integrations.openclaw.attention_allocator import (
    OPENCLAW_ATTENTION_ALLOCATOR_CONTRACT_VERSION,
    run_openclaw_attention_allocator,
)
from enhengclaw.integrations.openclaw.research_synthesizer import (
    OPENCLAW_RESEARCH_SYNTHESIZER_CONTRACT_VERSION,
    run_openclaw_research_synthesizer,
)
from enhengclaw.integrations.openclaw.research_lead import (
    OPENCLAW_RESEARCH_LEAD_CONTRACT_VERSION,
    run_openclaw_research_lead,
)
from enhengclaw.integrations.openclaw.risk_governance_agent import (
    OPENCLAW_RISK_GOVERNANCE_AGENT_CONTRACT_VERSION,
    run_openclaw_risk_governance_agent,
)
from enhengclaw.integrations.openclaw.validation_agent import (
    OPENCLAW_VALIDATION_AGENT_CONTRACT_VERSION,
    run_openclaw_validation_agent,
)

__all__ = [
    "OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION",
    "OpenClawMarketObserverRequest",
    "OpenClawMarketObserverResponse",
    "run_openclaw_market_observer",
    "OPENCLAW_EVIDENCE_AGENT_CONTRACT_VERSION",
    "run_openclaw_evidence_agent",
    "OPENCLAW_RISK_SIGNAL_AGENT_CONTRACT_VERSION",
    "run_openclaw_risk_signal_agent",
    "OPENCLAW_ATTENTION_ALLOCATOR_CONTRACT_VERSION",
    "run_openclaw_attention_allocator",
    "OPENCLAW_RESEARCH_SYNTHESIZER_CONTRACT_VERSION",
    "run_openclaw_research_synthesizer",
    "OPENCLAW_RESEARCH_LEAD_CONTRACT_VERSION",
    "run_openclaw_research_lead",
    "OPENCLAW_RISK_GOVERNANCE_AGENT_CONTRACT_VERSION",
    "run_openclaw_risk_governance_agent",
    "OPENCLAW_VALIDATION_AGENT_CONTRACT_VERSION",
    "run_openclaw_validation_agent",
]
