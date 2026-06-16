from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_helpers import ROOT, SRC

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.definitions._controlled_slice import (
    CONTROLLED_AGENT_SLICE_CONTRACT_VERSION,
    CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
)
from enhengclaw.agents.definitions.risk_signal_agent import RISK_SIGNAL_AGENT
from enhengclaw.agents.schemas.risk_signal_agent import RiskSignalDraft
from enhengclaw.agents.tools.runtime_signal_intake import (
    UnsupportedGovernedDelegateDirectCallError,
    submit_risk_signal,
)
from enhengclaw.core.enums import ObjectType, ProcessingState
from enhengclaw.core.session import FileObjectStore, InMemoryObjectStore
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness, sample_signals


DEMO = ROOT / "examples" / "governed_agent_ingress_demo.py"
FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "risk_signal_agent"


def pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class RiskSignalAgentPromotedAcceptanceTests(unittest.TestCase):
    def _fixture(self, name: str) -> dict[str, object]:
        return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))

    def _transcript(self, name: str) -> Path:
        return FIXTURE_ROOT / name / "model_transcript.json"

    def _run_demo(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DEMO), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=pythonpath_env(),
        )

    def test_definition_declares_promoted_governed_contract(self) -> None:
        prompt_path = Path(RISK_SIGNAL_AGENT["prompt_path"])
        self.assertTrue(prompt_path.exists())
        self.assertEqual(RISK_SIGNAL_AGENT["status"], "governed_agent_slice")
        self.assertTrue(RISK_SIGNAL_AGENT["enabled_under_current_governance"])
        self.assertTrue(RISK_SIGNAL_AGENT["registry_admission_eligible"])
        self.assertEqual(RISK_SIGNAL_AGENT["contract_version"], CONTROLLED_AGENT_SLICE_CONTRACT_VERSION)
        self.assertEqual(
            RISK_SIGNAL_AGENT["promotion_contract_version"],
            CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
        )
        self.assertEqual(RISK_SIGNAL_AGENT["slice_mode"], "continue_existing_object")
        self.assertEqual(
            RISK_SIGNAL_AGENT["canonical_runtime_boundary"],
            "runtime.continue_existing_from_agent_payloads",
        )
        self.assertEqual(
            RISK_SIGNAL_AGENT["schema"],
            "enhengclaw.agents.schemas.risk_signal_agent.RiskSignalDraft",
        )
        self.assertEqual(
            RISK_SIGNAL_AGENT["tool"],
            "enhengclaw.agents.tools.runtime_signal_intake.submit_risk_signal",
        )

    def test_direct_submit_is_rejected_without_owner_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            firewall = AgentIngressFirewall(
                quarantine_buffer=QuarantineBuffer(Path(tmpdir) / "quarantine"),
                replayable_input_log=ReplayableInputLog(Path(tmpdir) / "replay_log"),
            )
            runtime = RuntimeOrchestrator(
                store=InMemoryObjectStore(),
                agent_ingress_firewall=firewall,
            )

            with runtime_worker_harness(slug="risk-signal-pending-slice", scope="spot+perp"):
                runtime.run_new(
                    object_id="risk-signal-aix",
                    object_type=ObjectType.ASSET,
                    scope="spot+perp",
                    signals=sample_signals("risk-signal-aix"),
                )
                seeded_session = runtime.store.load("risk-signal-aix")
                seeded_claim_count = len(seeded_session.claims)
                with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
                    submit_risk_signal(
                        runtime=runtime,
                        object_id="risk-signal-aix",
                        signal=RiskSignalDraft(
                            input_id="risk-signal-agent-1",
                            subject="AIX",
                            predicate="fresh_invalidation_risk",
                            value="host risk notes highlight a bounded invalidation path worth attaching",
                            confidence_hint=67,
                        ),
                    )

            updated_session = runtime.store.load("risk-signal-aix")
            self.assertEqual(len(updated_session.claims), seeded_claim_count)

    def test_checked_in_governance_exposes_risk_signal_agent_as_current_shipped_slice(self) -> None:
        governance = evaluate_agent_layer_governance()
        self.assertEqual(governance["status"], "enabled")
        self.assertEqual(governance["blockers"], [])
        self.assertEqual(
            governance["admitted_controlled_slice_ids"],
            [
                "market_observer",
                "evidence_agent",
                "risk_signal_agent",
                "risk_governance_agent",
                "validation_agent",
                "attention_allocator",
                "research_synthesizer",
                "research_lead",
            ],
        )
        self.assertEqual(
            governance["current_controlled_slice_ids"],
            [
                "market_observer",
                "attention_allocator",
                "evidence_agent",
                "research_lead",
                "research_synthesizer",
                "risk_governance_agent",
                "risk_signal_agent",
                "validation_agent",
            ],
        )
        self.assertEqual(governance["registered_pending_promotion_controlled_slice_ids"], [])

    def test_public_demo_success_fixture_finalizes_and_mutates_runtime(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_signal_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                f"{fixture['case_id']}:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._transcript("success")),
                "--risk-text",
                str(fixture["risk_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "risk_signal_agent")
            self.assertEqual(payload["compiler_backend"], "recorded")
            self.assertEqual(payload["execution_status"], "success")
            self.assertGreaterEqual(len(payload["compiler_artifact_paths"]), 6)
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["final_output_path"]).exists())
            self.assertTrue(Path(payload["verification_path"]).exists())
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["final_claim_count"])

    def test_public_demo_blocked_fixture_preserves_seeded_session_without_additional_runtime_mutation(self) -> None:
        fixture = self._fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_signal_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                f"{fixture['case_id']}:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._transcript("blocked")),
                "--risk-text",
                str(fixture["risk_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "risk_signal_agent")
            self.assertEqual(payload["execution_status"], "blocked")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(payload["accepted_signal_ids"], [])
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["seeded_claim_count"])

    def test_public_demo_quarantine_fixture_preserves_seeded_session_without_additional_runtime_mutation(self) -> None:
        fixture = self._fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_signal_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                f"{fixture['case_id']}:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._transcript("quarantine")),
                "--risk-text",
                str(fixture["risk_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "risk_signal_agent")
            self.assertEqual(payload["execution_status"], "quarantine")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(payload["accepted_signal_ids"], [])
            self.assertIsNotNone(payload["quarantine_reason"])
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["seeded_claim_count"])


if __name__ == "__main__":
    unittest.main()
