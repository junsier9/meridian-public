from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT, SRC

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import CAP_RUNTIME_EXECUTE
from enhengclaw.core.session import FileObjectStore
from enhengclaw.testing.execution_testbed import execution_testbed


DEMO = ROOT / "examples" / "governed_agent_ingress_demo.py"
MARKET_FIXTURES = ROOT / "fixtures" / "agent_golden" / "market_observer"
EVIDENCE_FIXTURES = ROOT / "fixtures" / "agent_golden" / "evidence_agent"
RISK_FIXTURES = ROOT / "fixtures" / "agent_golden" / "risk_signal_agent"
RISK_GOVERNANCE_FIXTURES = ROOT / "fixtures" / "agent_golden" / "risk_governance_agent"
VALIDATION_FIXTURES = ROOT / "fixtures" / "agent_golden" / "validation_agent"
ATTENTION_FIXTURES = ROOT / "fixtures" / "agent_golden" / "attention_allocator"
SYNTHESIS_FIXTURES = ROOT / "fixtures" / "agent_golden" / "research_synthesizer"
LEAD_FIXTURES = ROOT / "fixtures" / "agent_golden" / "research_lead"


def pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class GovernedAgentIngressCliAcceptanceTests(unittest.TestCase):
    def _run_demo(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DEMO), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=pythonpath_env(env),
        )

    def test_market_observer_cli_creates_new_object(self) -> None:
        fixture = self._load_market_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "market_observer",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "market_observer_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._market_transcript("success")),
                "--observation-text",
                str(fixture["observation_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "market_observer")
            self.assertEqual(payload["slice_mode"], "create_new_object")
            self.assertEqual(payload["object_id"], str(fixture["object_id"]))
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["compiler_backend"], "recorded")
            self.assertEqual(payload["quarantine_paths"], [])
            self.assertEqual(payload["execution_status"], "success")
            self.assertGreaterEqual(len(payload["compiler_artifact_paths"]), 6)
            self.assertTrue(Path(payload["replay_log_paths"][0]).exists())
            self.assertTrue(Path(payload["final_output_path"]).exists())
            self.assertTrue((Path(tmpdir) / "agent_owner").exists())
            self.assertTrue((Path(tmpdir) / "runtime_sessions").exists())
            self.assertTrue((Path(tmpdir) / "operational_audit" / "runtime" / "runs").exists())

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(session.research_object.object_id, str(fixture["object_id"]))
            self.assertGreaterEqual(len(session.claims), 1)

    def test_market_observer_cli_blocks_when_compiler_cannot_emit_supported_predicate(self) -> None:
        fixture = self._load_market_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "market_observer",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "market_observer_blocked:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._market_transcript("blocked")),
                "--observation-text",
                str(fixture["observation_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "blocked")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(payload["accepted_signal_ids"], [])
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / f"{fixture['object_id']}.json").exists())

    def test_market_observer_cli_quarantines_candidate_without_runtime_mutation(self) -> None:
        fixture = self._load_market_fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "market_observer",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "market_observer_quarantine:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._market_transcript("quarantine")),
                "--observation-text",
                str(fixture["observation_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "quarantine")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertIsNotNone(payload["quarantine_reason"])
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / f"{fixture['object_id']}.json").exists())

    def test_market_observer_cli_uses_short_temp_root_when_artifacts_root_is_omitted(self) -> None:
        fixture = self._load_market_fixture("success")
        completed = self._run_demo(
            "market_observer",
            "--object-id",
            str(fixture["object_id"]),
            "--input-id",
            "market_observer_success:1",
            "--subject",
            str(fixture["subject"]),
            "--scope",
            str(fixture["scope"]),
            "--compiler-backend",
            "recorded",
            "--recorded-transcript",
            str(self._market_transcript("success")),
            "--observation-text",
            str(fixture["observation_text"]),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn("ecgd", payload["artifacts_root"].lower())

    def test_evidence_agent_cli_seeds_then_continues_existing_object(self) -> None:
        fixture = self._load_evidence_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "evidence_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "evidence_agent_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._evidence_transcript("success")),
                "--evidence-text",
                str(fixture["evidence_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "evidence_agent")
            self.assertEqual(payload["slice_mode"], "continue_existing_object")
            self.assertEqual(payload["object_id"], str(fixture["object_id"]))
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["quarantine_paths"], [])
            self.assertEqual(payload["compiler_backend"], "recorded")
            self.assertEqual(payload["execution_status"], "success")
            self.assertGreaterEqual(len(payload["compiler_artifact_paths"]), 6)
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["replay_log_paths"][0]).exists())
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertTrue(Path(payload["final_output_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["final_claim_count"])

    def test_risk_signal_agent_cli_promoted_path_finalizes_recorded_success_fixture(self) -> None:
        fixture = self._load_risk_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_signal_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "risk_signal_agent_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._risk_transcript("success")),
                "--risk-text",
                str(fixture["risk_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "risk_signal_agent")
            self.assertEqual(payload["slice_mode"], "continue_existing_object")
            self.assertEqual(payload["object_id"], str(fixture["object_id"]))
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(payload["compiler_backend"], "recorded")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

            session = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(session.claims), payload["final_claim_count"])

    def test_attention_allocator_cli_promoted_path_finalizes_recorded_success_fixture(self) -> None:
        fixture = self._load_attention_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "attention_allocator",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "attention_allocator_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._attention_transcript("success")),
                "--attention-text",
                str(fixture["attention_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "attention_allocator")
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_research_synthesizer_cli_promoted_path_finalizes_recorded_success_fixture(self) -> None:
        fixture = self._load_synthesis_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "research_synthesizer",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "research_synthesizer_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._synthesis_transcript("success")),
                "--synthesis-text",
                str(fixture["synthesis_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "research_synthesizer")
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_research_lead_cli_promoted_path_finalizes_recorded_success_fixture(self) -> None:
        fixture = self._load_lead_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "research_lead",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "research_lead_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._lead_transcript("success")),
                "--directive-text",
                str(fixture["directive_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "research_lead")
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_risk_governance_agent_cli_promoted_path_finalizes_recorded_success_fixture(self) -> None:
        fixture = self._load_risk_governance_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "risk_governance_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "risk_governance_agent_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._risk_governance_transcript("success")),
                "--governance-text",
                str(fixture["governance_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "risk_governance_agent")
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_validation_agent_cli_promoted_path_finalizes_recorded_success_fixture(self) -> None:
        fixture = self._load_validation_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "validation_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "validation_agent_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._validation_transcript("success")),
                "--validation-text",
                str(fixture["validation_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "validation_agent")
            self.assertEqual(payload["run_state"], "FINALIZED")
            self.assertEqual(payload["execution_status"], "success")
            self.assertEqual(len(payload["accepted_signal_ids"]), 1)
            self.assertTrue(Path(payload["session_path"]).exists())
            self.assertGreater(payload["final_claim_count"], payload["seeded_claim_count"])

    def test_cli_fails_closed_when_external_permit_is_required_but_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "market_observer",
                "--artifacts-root",
                tmpdir,
                "--require-external-permit",
                "--input-id",
                "market_observer_success:1",
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._market_transcript("success")),
                "--observation-text",
                "AIX still shows supportive structure with a higher low above support.",
            )

            self.assertNotEqual(completed.returncode, 0)
            payload = json.loads(completed.stderr)
            self.assertEqual(payload["error_type"], "MissingExecutionPermitError")
            self.assertIn("--execution-permit", payload["error"])
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / "market-observer-aix.json").exists())

    def test_cli_rejects_external_permit_scope_overreach(self) -> None:
        fixture = self._load_market_fixture("success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir:
            permit_path, _permit = bed.issue_permit(
                slug="governed-cli-scope-overreach",
                scope="spot-only",
                capabilities=[CAP_RUNTIME_EXECUTE],
                allowed_operations=["runtime.*"],
            )
            completed = self._run_demo(
                "market_observer",
                "--artifacts-root",
                tmpdir,
                "--execution-permit",
                str(permit_path),
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "market_observer_success:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                "spot+perp",
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._market_transcript("success")),
                "--observation-text",
                str(fixture["observation_text"]),
            )

            self.assertNotEqual(completed.returncode, 0)
            payload = json.loads(completed.stderr)
            self.assertEqual(payload["error_type"], "InvalidExecutionPermitError")
            self.assertIn("does not allow requested scope", payload["error"])

    def test_market_observer_cli_live_backend_fails_closed_without_required_env(self) -> None:
        fixture = self._load_market_fixture("success")
        env = {
            "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL": "",
            "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME": "",
            "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "market_observer",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--observation-text",
                str(fixture["observation_text"]),
                env=env,
            )

            self.assertNotEqual(completed.returncode, 0)
            payload = json.loads(completed.stderr)
            self.assertEqual(payload["error_type"], "MarketObserverLiveBackendConfigError")
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / f"{fixture['object_id']}.json").exists())

    def _load_market_fixture(self, name: str) -> dict[str, object]:
        return json.loads((MARKET_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _market_transcript(self, name: str) -> Path:
        return MARKET_FIXTURES / name / "model_transcript.json"

    def _load_evidence_fixture(self, name: str) -> dict[str, object]:
        return json.loads((EVIDENCE_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _evidence_transcript(self, name: str) -> Path:
        return EVIDENCE_FIXTURES / name / "model_transcript.json"

    def _load_risk_fixture(self, name: str) -> dict[str, object]:
        return json.loads((RISK_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _risk_transcript(self, name: str) -> Path:
        return RISK_FIXTURES / name / "model_transcript.json"

    def _load_risk_governance_fixture(self, name: str) -> dict[str, object]:
        return json.loads((RISK_GOVERNANCE_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _risk_governance_transcript(self, name: str) -> Path:
        return RISK_GOVERNANCE_FIXTURES / name / "model_transcript.json"

    def _load_validation_fixture(self, name: str) -> dict[str, object]:
        return json.loads((VALIDATION_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _validation_transcript(self, name: str) -> Path:
        return VALIDATION_FIXTURES / name / "model_transcript.json"

    def _load_attention_fixture(self, name: str) -> dict[str, object]:
        return json.loads((ATTENTION_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _attention_transcript(self, name: str) -> Path:
        return ATTENTION_FIXTURES / name / "model_transcript.json"

    def _load_synthesis_fixture(self, name: str) -> dict[str, object]:
        return json.loads((SYNTHESIS_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _synthesis_transcript(self, name: str) -> Path:
        return SYNTHESIS_FIXTURES / name / "model_transcript.json"

    def _load_lead_fixture(self, name: str) -> dict[str, object]:
        return json.loads((LEAD_FIXTURES / name / "input.json").read_text(encoding="utf-8"))

    def _lead_transcript(self, name: str) -> Path:
        return LEAD_FIXTURES / name / "model_transcript.json"

    def test_evidence_agent_skip_seed_blocks_when_object_is_missing(self) -> None:
        fixture = self._load_evidence_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "evidence_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                "missing-cli-evidence",
                "--skip-seed",
                "--input-id",
                "evidence_agent_missing_context:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._evidence_transcript("success")),
                "--evidence-text",
                str(fixture["evidence_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertEqual(payload["execution_status"], "blocked")
            self.assertEqual(payload["blocked_reason"], "missing existing object context for evidence_agent")
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / "missing-cli-evidence.json").exists())

    def test_evidence_agent_quarantines_candidate_without_mutating_session(self) -> None:
        fixture = self._load_evidence_fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "evidence_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--input-id",
                "evidence_agent_quarantine:1",
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--compiler-backend",
                "recorded",
                "--recorded-transcript",
                str(self._evidence_transcript("quarantine")),
                "--evidence-text",
                str(fixture["evidence_text"]),
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["execution_status"], "quarantine")
            self.assertEqual(payload["run_state"], "BLOCKED")
            self.assertIsNotNone(payload["quarantine_reason"])
            self.assertEqual(payload["final_claim_count"], payload["seeded_claim_count"])

            after = FileObjectStore(Path(tmpdir) / "runtime_sessions").load(str(fixture["object_id"]))
            self.assertEqual(len(after.claims), payload["seeded_claim_count"])

    def test_evidence_agent_cli_live_backend_fails_closed_without_required_env(self) -> None:
        fixture = self._load_evidence_fixture("success")
        env = {
            "ENHENGCLAW_EVIDENCE_AGENT_MODEL_BASE_URL": "",
            "ENHENGCLAW_EVIDENCE_AGENT_MODEL_NAME": "",
            "ENHENGCLAW_EVIDENCE_AGENT_API_KEY": "",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "evidence_agent",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                str(fixture["object_id"]),
                "--subject",
                str(fixture["subject"]),
                "--scope",
                str(fixture["scope"]),
                "--evidence-text",
                str(fixture["evidence_text"]),
                env=env,
            )

            self.assertNotEqual(completed.returncode, 0)
            payload = json.loads(completed.stderr)
            self.assertEqual(payload["error_type"], "EvidenceAgentLiveBackendConfigError")


if __name__ == "__main__":
    unittest.main()
