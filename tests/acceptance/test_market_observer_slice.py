from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT, SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.definitions._controlled_slice import CONTROLLED_AGENT_SLICE_CONTRACT_VERSION
from enhengclaw.agents.definitions.market_observer import MARKET_OBSERVER_AGENT
from enhengclaw.agents.schemas.market_observer import MarketObserverSignalDraft
from enhengclaw.agents.tools.runtime_signal_intake import (
    UnsupportedGovernedDelegateDirectCallError,
    submit_market_observer_signal,
)
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness


class MarketObserverSliceAcceptanceTests(unittest.TestCase):
    def test_definition_declares_governed_slice_contract(self) -> None:
        prompt_path = Path(MARKET_OBSERVER_AGENT["prompt_path"])
        self.assertTrue(prompt_path.exists())
        self.assertEqual(MARKET_OBSERVER_AGENT["status"], "governed_agent_slice")
        self.assertTrue(MARKET_OBSERVER_AGENT["enabled_under_current_governance"])
        self.assertEqual(MARKET_OBSERVER_AGENT["contract_version"], CONTROLLED_AGENT_SLICE_CONTRACT_VERSION)
        self.assertEqual(MARKET_OBSERVER_AGENT["slice_mode"], "create_new_object")
        self.assertEqual(
            MARKET_OBSERVER_AGENT["canonical_runtime_boundary"],
            "runtime.run_new_from_agent_payloads",
        )
        self.assertEqual(MARKET_OBSERVER_AGENT["max_tool_calls"], 1)
        self.assertEqual(MARKET_OBSERVER_AGENT["max_payloads"], 1)
        self.assertEqual(
            MARKET_OBSERVER_AGENT["schema"],
            "enhengclaw.agents.schemas.market_observer.MarketObserverSignalDraft",
        )
        self.assertEqual(
            MARKET_OBSERVER_AGENT["tool"],
            "enhengclaw.agents.tools.runtime_signal_intake.submit_market_observer_signal",
        )

    def test_market_observer_direct_submit_is_rejected_without_owner_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            firewall = AgentIngressFirewall(
                quarantine_buffer=QuarantineBuffer(Path(tmpdir) / "quarantine"),
                replayable_input_log=ReplayableInputLog(Path(tmpdir) / "replay_log"),
            )
            runtime = RuntimeOrchestrator(
                store=InMemoryObjectStore(),
                agent_ingress_firewall=firewall,
            )
            signal = MarketObserverSignalDraft(
                input_id="market-observer-1",
                subject="AIX",
                predicate="agent_market_structure_support",
                value="analyst notes spot-led continuation with supportive structure",
                confidence_hint=68,
            )

            with runtime_worker_harness(slug="market-observer-slice"):
                with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
                    submit_market_observer_signal(
                        runtime=runtime,
                        object_id="agent-slice-aix",
                        signal=signal,
                    )

            self.assertFalse(runtime.store.exists("agent-slice-aix"))


if __name__ == "__main__":
    unittest.main()
