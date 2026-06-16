from __future__ import annotations

from dataclasses import asdict
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
from enhengclaw.agents.definitions.research_synthesizer import RESEARCH_SYNTHESIZER_AGENT
from enhengclaw.agents.schemas.research_synthesizer import ResearchSynthesisSignalDraft
from enhengclaw.agents.tools.runtime_session_views import inspect_research_synthesis
from enhengclaw.agents.tools.runtime_signal_intake import (
    UnsupportedGovernedDelegateDirectCallError,
    submit_research_synthesis_signal,
)
from enhengclaw.core.enums import ObjectType, ProcessingState
from enhengclaw.core.session import FileObjectStore, InMemoryObjectStore
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness, sample_signals


GOVERNED_DEMO = ROOT / "examples" / "governed_agent_ingress_demo.py"
REVIEW_DEMO = ROOT / "examples" / "rulebook_agent_review_demo.py"
FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "research_synthesizer"


def pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class ResearchSynthesizerPromotedAcceptanceTests(unittest.TestCase):
    def _fixture(self, name: str) -> dict[str, object]:
        return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))

    def _transcript(self, name: str) -> Path:
        return FIXTURE_ROOT / name / "model_transcript.json"

    def _run_governed_demo(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GOVERNED_DEMO), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=pythonpath_env(),
        )

    def _run_review_demo(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REVIEW_DEMO), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=pythonpath_env(),
        )

    def test_definition_declares_promoted_writable_dual_surface_contract(self) -> None:
        prompt_path = Path(RESEARCH_SYNTHESIZER_AGENT["prompt_path"])
        self.assertTrue(prompt_path.exists())
        self.assertEqual(RESEARCH_SYNTHESIZER_AGENT["status"], "governed_agent_slice")
        self.assertTrue(RESEARCH_SYNTHESIZER_AGENT["enabled_under_current_governance"])
        self.assertTrue(RESEARCH_SYNTHESIZER_AGENT["registry_admission_eligible"])
        self.assertEqual(RESEARCH_SYNTHESIZER_AGENT["contract_version"], CONTROLLED_AGENT_SLICE_CONTRACT_VERSION)
        self.assertEqual(
            RESEARCH_SYNTHESIZER_AGENT["promotion_contract_version"],
            CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
        )
        self.assertEqual(RESEARCH_SYNTHESIZER_AGENT["slice_mode"], "continue_existing_object")
        self.assertEqual(
            RESEARCH_SYNTHESIZER_AGENT["canonical_runtime_boundary"],
            "runtime.continue_existing_from_agent_payloads",
        )
        self.assertEqual(
            RESEARCH_SYNTHESIZER_AGENT["schema"],
            "enhengclaw.agents.schemas.research_synthesizer.ResearchSynthesisSignalDraft",
        )
        self.assertEqual(
            RESEARCH_SYNTHESIZER_AGENT["tool"],
            "enhengclaw.agents.tools.runtime_signal_intake.submit_research_synthesis_signal",
        )
        review_surface = dict(RESEARCH_SYNTHESIZER_AGENT["operator_review_surface"])
        self.assertEqual(
            review_surface["schema"],
            "enhengclaw.agents.schemas.research_synthesizer.ResearchSynthesisDraft",
        )
        self.assertEqual(
            review_surface["tool"],
            "enhengclaw.agents.tools.runtime_session_views.inspect_research_synthesis",
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

            with runtime_worker_harness(slug="research-synthesizer-promoted-slice", scope="spot+perp"):
                runtime.run_new(
                    object_id="research-synthesizer-aix",
                    object_type=ObjectType.ASSET,
                    scope="spot+perp",
                    signals=sample_signals("research-synthesizer-aix"),
                )
                seeded_session = runtime.store.load("research-synthesizer-aix")
                seeded_claim_count = len(seeded_session.claims)
                with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
                    submit_research_synthesis_signal(
                        runtime=runtime,
                        object_id="research-synthesizer-aix",
                        signal=ResearchSynthesisSignalDraft(
                            input_id="research-synthesizer-agent-1",
                            subject="AIX",
                            predicate="synthesis_preview_monitor",
                            value="synthesis preview remains mixed and should stay bounded to one summary signal",
                            confidence_hint=66,
                        ),
                    )

            updated_session = runtime.store.load("research-synthesizer-aix")
            self.assertEqual(len(updated_session.claims), seeded_claim_count)

    def test_checked_in_governance_exposes_research_synthesizer_as_current_shipped_slice(self) -> None:
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
        self.assertEqual(governance["registered_pending_promotion_controlled_slice_ids"], [])
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
        self.assertIn("research_synthesizer", governance["current_controlled_slice_ids"])

    def test_public_governed_demo_success_fixture_finalizes_and_mutates_runtime(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_governed_demo(
                "research_synthesizer",
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
                "--synthesis-text",
                str(fixture["synthesis_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "research_synthesizer")
            self.assertEqual(payload["compiler_backend"], "recorded")
            self.assertEqual(payload["execution_status"], "success")
            self.assertGreaterEqual(len(payload["compiler_artifact_paths"]), 6)
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["final_claim_count"])

    def test_public_governed_demo_blocked_fixture_preserves_seeded_session_without_additional_runtime_mutation(self) -> None:
        fixture = self._fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_governed_demo(
                "research_synthesizer",
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
                "--synthesis-text",
                str(fixture["synthesis_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "blocked")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(payload["accepted_signal_ids"], [])
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_public_governed_demo_quarantine_fixture_preserves_seeded_session_without_additional_runtime_mutation(self) -> None:
        fixture = self._fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_governed_demo(
                "research_synthesizer",
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
                "--synthesis-text",
                str(fixture["synthesis_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "quarantine")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertIsNotNone(payload["quarantine_reason"])
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_operator_review_demo_matches_direct_tool_output_without_mutating_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_review_demo(
                "research_synthesizer",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                "research-synthesis-aix",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "research_synthesizer")
            self.assertEqual(payload["review_surface"], "research_synthesis")
            self.assertFalse(payload["session_mutated"])

            session_path = Path(payload["session_path"])
            before = session_path.read_text(encoding="utf-8")
            runtime = RuntimeOrchestrator(store=FileObjectStore(Path(tmpdir) / "runtime_sessions"))
            direct_review = inspect_research_synthesis(runtime=runtime, object_id="research-synthesis-aix")
            after = session_path.read_text(encoding="utf-8")

            self.assertEqual(before, after)
            self.assertEqual(payload["review"], json.loads(json.dumps(asdict(direct_review))))


if __name__ == "__main__":
    unittest.main()
