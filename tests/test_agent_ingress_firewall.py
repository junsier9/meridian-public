from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import CAP_RUNTIME_EXECUTE
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall, AgentIngressValidationError
from enhengclaw.ingress.schema_validator import AgentIngressContext
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing.execution_testbed import execution_testbed


class AgentIngressFirewallTests(unittest.TestCase):
    def _payload(
        self,
        *,
        input_id: str,
        subject: str = "AIX",
        predicate: str = "agent_market_signal",
        value: str = "agent observed supportive market structure",
    ) -> dict[str, object]:
        return {
            "input_id": input_id,
            "subject": subject,
            "predicate": predicate,
            "value": value,
            "claim_type": "measurement",
            "direction": "bullish",
            "source_family": "analytics",
            "evidence_level": "E4",
            "confidence_hint": 72,
            "scope": "spot+perp",
            "time_horizon": "intraday",
        }

    def _firewall(self, tmpdir: str) -> AgentIngressFirewall:
        firewall = AgentIngressFirewall(
            quarantine_buffer=QuarantineBuffer(Path(tmpdir) / "quarantine"),
            replayable_input_log=ReplayableInputLog(Path(tmpdir) / "replay_log"),
        )
        return firewall

    def _context(self, *, object_id: str, scenario: str) -> AgentIngressContext:
        return AgentIngressContext(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario=scenario,
        )

    def test_valid_agent_payloads_are_logged_and_can_enter_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            firewall = self._firewall(tmpdir)
            with execution_testbed() as bed:
                _, permit = bed.issue_permit(
                    slug="agent-ingress-valid",
                    scope="spot+perp",
                    capabilities=[CAP_RUNTIME_EXECUTE],
                    allowed_operations=["runtime.*"],
                )
                runtime = RuntimeOrchestrator(execution_permit=permit, agent_ingress_firewall=firewall)
                result = runtime.run_new_from_agent_payloads(
                    object_id="agent-valid",
                    object_type=ObjectType.ASSET,
                    subject="AIX",
                    scope="spot+perp",
                    scenario="agent_valid",
                    payloads=[self._payload(input_id="agent-1")],
                )

            self.assertEqual(len(result.replay_log_paths), 1)
            self.assertEqual(result.quarantine_paths, [])
            self.assertTrue(Path(result.replay_log_paths[0]).exists())
            self.assertIn("symbol=aix__venue=agent_ingress__instrument_type=agent_output", result.accepted_signal_ids[0])

    def test_invalid_agent_payload_is_quarantined_and_does_not_pollute_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            firewall = self._firewall(tmpdir)
            bad_payload = self._payload(input_id="agent-bad")
            del bad_payload["predicate"]

            with self.assertRaises(AgentIngressValidationError) as ctx:
                firewall.intake(
                    context=self._context(object_id="agent-invalid", scenario="agent_invalid"),
                    payloads=[bad_payload],
                )

            self.assertEqual(len(ctx.exception.replay_records), 1)
            self.assertEqual(len(ctx.exception.quarantine_records), 1)
            self.assertTrue(Path(ctx.exception.replay_records[0].path).exists())
            self.assertTrue(Path(ctx.exception.quarantine_records[0].path).exists())

    def test_mixed_agent_batch_fails_closed_when_any_payload_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            firewall = self._firewall(tmpdir)
            payloads = [
                self._payload(input_id="agent-good"),
                self._payload(input_id="agent-mismatch", subject="BTC"),
            ]

            with self.assertRaises(AgentIngressValidationError) as ctx:
                firewall.intake(
                    context=self._context(object_id="agent-mixed", scenario="agent_mixed"),
                    payloads=payloads,
                )

            self.assertEqual(len(ctx.exception.replay_records), 2)
            self.assertEqual(len(ctx.exception.quarantine_records), 1)
            self.assertEqual(ctx.exception.replay_records[0].verdict, "accepted")
            self.assertEqual(ctx.exception.replay_records[1].verdict, "quarantined")


if __name__ == "__main__":
    unittest.main()
