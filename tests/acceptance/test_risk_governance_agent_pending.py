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
from enhengclaw.agents.definitions.risk_governance_agent import RISK_GOVERNANCE_AGENT
from enhengclaw.agents.schemas.risk_governance_agent import RiskGovernanceSignalDraft
from enhengclaw.agents.tools.runtime_signal_intake import (
    UnsupportedGovernedDelegateDirectCallError,
    submit_risk_governance_signal,
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
FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "risk_governance_agent"


def pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class RiskGovernanceAgentPromotedAcceptanceTests(unittest.TestCase):
    def _fixture(self, name: str) -> dict[str, object]:
        return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))

    def _transcript(self, name: str) -> Path:
        return FIXTURE_ROOT / name / "model_transcript.json"

    def _run_demo(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DEMO), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=pythonpath_env(env),
        )

    def _review_artifacts(self, tmpdir: str) -> list[Path]:
        return list((Path(tmpdir) / "agent_owner").rglob("reviews/*/*.json"))

    def test_definition_declares_promoted_governed_contract(self) -> None:
        prompt_path = Path(RISK_GOVERNANCE_AGENT["prompt_path"])
        self.assertTrue(prompt_path.exists())
        self.assertEqual(RISK_GOVERNANCE_AGENT["status"], "governed_agent_slice")
        self.assertTrue(RISK_GOVERNANCE_AGENT["enabled_under_current_governance"])
        self.assertTrue(RISK_GOVERNANCE_AGENT["registry_admission_eligible"])
        self.assertEqual(RISK_GOVERNANCE_AGENT["contract_version"], CONTROLLED_AGENT_SLICE_CONTRACT_VERSION)
        self.assertEqual(
            RISK_GOVERNANCE_AGENT["promotion_contract_version"],
            CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
        )
        self.assertEqual(RISK_GOVERNANCE_AGENT["slice_mode"], "continue_existing_object")
        self.assertEqual(
            RISK_GOVERNANCE_AGENT["canonical_runtime_boundary"],
            "runtime.continue_existing_from_agent_payloads",
        )
        self.assertEqual(
            RISK_GOVERNANCE_AGENT["schema"],
            "enhengclaw.agents.schemas.risk_governance_agent.RiskGovernanceSignalDraft",
        )
        self.assertEqual(
            RISK_GOVERNANCE_AGENT["tool"],
            "enhengclaw.agents.tools.runtime_signal_intake.submit_risk_governance_signal",
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

            with runtime_worker_harness(slug="risk-governance-promoted-slice", scope="spot+perp"):
                runtime.run_new(
                    object_id="risk-governance-aix",
                    object_type=ObjectType.ASSET,
                    scope="spot+perp",
                    signals=sample_signals("risk-governance-aix"),
                )
                seeded_session = runtime.store.load("risk-governance-aix")
                seeded_claim_count = len(seeded_session.claims)
                with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
                    submit_risk_governance_signal(
                        runtime=runtime,
                        object_id="risk-governance-aix",
                        signal=RiskGovernanceSignalDraft(
                            input_id="risk-governance-agent-1",
                            subject="AIX",
                            predicate="governance_suppression_required",
                            value="derived governance posture requires a bounded suppression signal until forced review clears the object",
                            confidence_hint=72,
                        ),
                    )

            updated_session = runtime.store.load("risk-governance-aix")
            self.assertEqual(len(updated_session.claims), seeded_claim_count)

    def test_checked_in_governance_exposes_risk_governance_agent_as_current_shipped_slice(self) -> None:
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
        self.assertIn("risk_governance_agent", governance["current_controlled_slice_ids"])

    def test_public_demo_success_fixture_finalizes_and_mutates_runtime(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_governance_agent",
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
                "--governance-text",
                str(fixture["governance_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "risk_governance_agent")
            self.assertEqual(payload["compiler_backend"], "recorded")
            self.assertEqual(payload["execution_status"], "success")
            self.assertGreaterEqual(len(payload["compiler_artifact_paths"]), 6)
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["final_claim_count"])
            self.assertTrue(self._review_artifacts(tmpdir))

    def test_public_demo_blocked_fixture_preserves_seeded_session_without_additional_runtime_mutation(self) -> None:
        fixture = self._fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_governance_agent",
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
                "--governance-text",
                str(fixture["governance_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "blocked")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(payload["accepted_signal_ids"], [])
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_public_demo_quarantine_fixture_preserves_seeded_session_without_additional_runtime_mutation(self) -> None:
        fixture = self._fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_governance_agent",
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
                "--governance-text",
                str(fixture["governance_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "quarantine")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertIsNotNone(payload["quarantine_reason"])
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_public_demo_review_gate_block_returns_blocked_after_runtime_write(self) -> None:
        fixture = self._fixture("success")
        override = {
            "risk_governance_review": {
                "object_id": str(fixture["object_id"]),
                "processing_state": ProcessingState.ACTIVE_RESEARCH.value,
                "current_risk_state": "normal",
                "derived_risk_state": "normal",
                "governance_posture": "normal",
                "publish_suppressed": False,
                "review_name": "risk_governance_review",
                "gate_status": "block",
                "spec_version": 1,
                "reasons": ["forced block for promoted-path review gate acceptance"],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_governance_agent",
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
                "--governance-text",
                str(fixture["governance_text"]),
                env={"ENHENGCLAW_TEST_REVIEW_OVERRIDE": json.dumps(override)},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])
            self.assertTrue(self._review_artifacts(tmpdir))

    def test_public_demo_invalid_review_payload_returns_failed_after_runtime_write(self) -> None:
        fixture = self._fixture("success")
        override = {
            "risk_governance_review": {
                "object_id": str(fixture["object_id"]),
                "processing_state": ProcessingState.ACTIVE_RESEARCH.value,
                "current_risk_state": "normal",
                "derived_risk_state": "normal",
                "governance_posture": "normal",
                "publish_suppressed": False,
                "review_name": "risk_governance_review",
                "gate_status": "invalid",
                "spec_version": 1,
                "reasons": ["forced invalid payload for promoted-path review gate acceptance"],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_governance_agent",
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
                "--governance-text",
                str(fixture["governance_text"]),
                env={"ENHENGCLAW_TEST_REVIEW_OVERRIDE": json.dumps(override)},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(payload["run_state"], "FAILED")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])


if __name__ == "__main__":
    unittest.main()
