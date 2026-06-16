from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.definitions._controlled_slice import CONTROLLED_AGENT_SLICE_CONTRACT_VERSION
from enhengclaw.agents.definitions.attention_allocator import ATTENTION_ALLOCATOR_AGENT
from enhengclaw.agents.definitions.evidence_agent import EVIDENCE_AGENT
from enhengclaw.agents.definitions.market_observer import MARKET_OBSERVER_AGENT
from enhengclaw.agents.definitions.research_lead import RESEARCH_LEAD_AGENT
from enhengclaw.agents.definitions.research_synthesizer import RESEARCH_SYNTHESIZER_AGENT
from enhengclaw.agents.definitions.risk_governance_agent import RISK_GOVERNANCE_AGENT
from enhengclaw.agents.definitions.risk_signal_agent import RISK_SIGNAL_AGENT
from enhengclaw.agents.definitions.validation_agent import VALIDATION_AGENT
from enhengclaw.agents.owner_state import OwnerArtifactStore, VerificationItem
from enhengclaw.agents.schemas.evidence_agent import EvidenceSignalDraft
from enhengclaw.agents.schemas.validation_agent import ValidationBlockerSignalDraft
from enhengclaw.agents.tools.runtime_signal_intake import (
    UnsupportedGovernedDelegateDirectCallError,
    submit_evidence_signal,
)
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.runtime import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness, sample_signals


ALL_SLICES = [
    MARKET_OBSERVER_AGENT,
    EVIDENCE_AGENT,
    RISK_SIGNAL_AGENT,
    RISK_GOVERNANCE_AGENT,
    VALIDATION_AGENT,
    ATTENTION_ALLOCATOR_AGENT,
    RESEARCH_SYNTHESIZER_AGENT,
    RESEARCH_LEAD_AGENT,
]


class MissingReviewOrchestrator(GovernedAgentOrchestrator):
    def _run_required_reviews(self, **kwargs):  # type: ignore[override]
        return (), "missing required review record"


class IncompleteVerificationOrchestrator(GovernedAgentOrchestrator):
    def _verification_items(self, **kwargs):  # type: ignore[override]
        spec_version = int(kwargs["spec_version"])
        step_id = str(kwargs["step_id"])
        return [
            VerificationItem(
                "delegate_recorded",
                "delegate append-only artifact exists",
                "passed",
                step_id=step_id,
                spec_version=spec_version,
            )
        ]


class CrashAfterWriteOrchestrator(GovernedAgentOrchestrator):
    def _execute_delegate_write(self, **kwargs):  # type: ignore[override]
        result = super()._execute_delegate_write(**kwargs)
        raise RuntimeError("simulated crash after delegate write")


class RulebookAgentArchitectureAcceptanceTests(unittest.TestCase):
    def test_controlled_slice_definitions_still_point_to_real_prompt_schema_and_tool(self) -> None:
        for agent in ALL_SLICES:
            self.assertEqual(agent["contract_version"], CONTROLLED_AGENT_SLICE_CONTRACT_VERSION)
            self.assertTrue(Path(agent["prompt_path"]).exists(), agent["agent_id"])
            self.assertTrue(str(agent["schema"]).startswith("enhengclaw.agents.schemas."), agent["agent_id"])
            self.assertTrue(str(agent["tool"]).startswith("enhengclaw.agents.tools."), agent["agent_id"])

    def test_owner_first_evidence_write_finalizes_and_persists_nested_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "rulebook-evidence-aix")
            before_claims = len(runtime.store.load("rulebook-evidence-aix").claims)

            with runtime_worker_harness(slug="rulebook-owner-first-evidence", scope="spot+perp"):
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id="rulebook-evidence-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=EvidenceSignalDraft(
                        input_id="owner-first-evidence-1",
                        subject="AIX",
                        predicate="fresh_supportive_flow",
                        value="owner-first evidence write stays bounded to one signal",
                        confidence_hint=74,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Continue one existing governed object with one evidence signal.",
                )

            store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            after_claims = len(runtime.store.load("rulebook-evidence-aix").claims)
            self.assertEqual(result.run_state, "FINALIZED")
            self.assertFalse(result.replayed)
            self.assertEqual(after_claims, before_claims + 1)
            self.assertTrue(Path(result.delegate_artifact_path).exists())
            self.assertTrue(Path(result.final_output_path).exists())
            self.assertTrue(Path(result.spec_path).exists())
            self.assertTrue(Path(result.verification_path).exists())
            final_output = store.load_json(result.final_output_path)
            self.assertEqual(final_output["run_state"], "FINALIZED")
            self.assertEqual(final_output["selected_delegate_id"], "evidence_agent")
            self.assertEqual(final_output["provenance"], "owner_finalizer")

    def test_direct_delegate_write_is_rejected_without_owner_context(self) -> None:
        runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        with runtime_worker_harness(slug="rulebook-direct-evidence", scope="spot+perp"):
            runtime.run_new(
                object_id="direct-evidence-aix",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=sample_signals("direct-evidence-aix"),
            )
            with self.assertRaises(UnsupportedGovernedDelegateDirectCallError):
                submit_evidence_signal(
                    runtime=runtime,
                    object_id="direct-evidence-aix",
                    signal=EvidenceSignalDraft(
                        input_id="direct-evidence-1",
                        subject="AIX",
                        predicate="fresh_supportive_flow",
                        value="this path should be rejected without an owner-issued capability",
                        confidence_hint=70,
                    ),
                )

    def test_missing_required_review_record_blocks_final_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "validation-blocked-aix")

            with runtime_worker_harness(slug="rulebook-missing-review", scope="spot+perp"):
                result = MissingReviewOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="validation_agent",
                    object_id="validation-blocked-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=ValidationBlockerSignalDraft(
                        input_id="validation-owner-first-1",
                        subject="AIX",
                        predicate="publish_gate_hold",
                        value="validation stays blocked until the required review exists",
                        confidence_hint=71,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach one bounded validation blocker.",
                )

            final_output = OwnerArtifactStore(Path(tmpdir) / "agent_owner").load_json(result.final_output_path)
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertEqual(final_output["run_state"], "BLOCKED")
            self.assertEqual(final_output["blocked_reason"], "missing required review record")

    def test_review_veto_blocks_finalization_when_review_tool_returns_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "validation-review-veto-aix")
            original_loader = __import__(
                "enhengclaw.orchestration.governed_agent_orchestrator",
                fromlist=["_load_callable"],
            )._load_callable

            def _patched_loader(entrypoint: str):
                if entrypoint == "enhengclaw.agents.tools.runtime_session_views.inspect_validation_review":
                    return lambda **kwargs: {
                        "review_name": "validation_review",
                        "gate_status": "block",
                        "reasons": ["forced review veto"],
                        "object_id": kwargs["object_id"],
                        "spec_version": kwargs["spec_version"],
                    }
                return original_loader(entrypoint)

            with runtime_worker_harness(slug="rulebook-review-veto", scope="spot+perp"):
                with patch(
                    "enhengclaw.orchestration.governed_agent_orchestrator._load_callable",
                    side_effect=_patched_loader,
                ):
                    result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                        requested_delegate_id="validation_agent",
                        object_id="validation-review-veto-aix",
                        subject="AIX",
                        scope="spot+perp",
                        signal_draft=ValidationBlockerSignalDraft(
                            input_id="validation-review-veto-1",
                            subject="AIX",
                            predicate="publish_gate_hold",
                            value="review veto should block owner finalization",
                            confidence_hint=71,
                        ),
                        artifacts_root=tmpdir,
                        user_intent="Attach one validation blocker only if review passes.",
                    )

            final_output = OwnerArtifactStore(Path(tmpdir) / "agent_owner").load_json(result.final_output_path)
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertEqual(final_output["run_state"], "BLOCKED")
            self.assertEqual(final_output["blocked_reason"], "required review gate failed: validation_review")

    def test_missing_verification_item_generates_blocked_final_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "verification-blocked-aix")

            with runtime_worker_harness(slug="rulebook-incomplete-verification", scope="spot+perp"):
                result = IncompleteVerificationOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id="verification-blocked-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=EvidenceSignalDraft(
                        input_id="verification-owner-first-1",
                        subject="AIX",
                        predicate="fresh_supportive_flow",
                        value="verification should fail closed when required items are missing",
                        confidence_hint=74,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach one bounded evidence signal.",
                )

            final_output = OwnerArtifactStore(Path(tmpdir) / "agent_owner").load_json(result.final_output_path)
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertEqual(final_output["blocked_reason"], "verification_incomplete")

    def test_idempotent_retry_reuses_delegate_artifact_without_second_runtime_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "idempotent-evidence-aix")
            orchestrator = GovernedAgentOrchestrator(runtime=runtime)

            with runtime_worker_harness(slug="rulebook-idempotent-evidence", scope="spot+perp"):
                first = orchestrator.run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id="idempotent-evidence-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=EvidenceSignalDraft(
                        input_id="idempotent-evidence-1",
                        subject="AIX",
                        predicate="fresh_supportive_flow",
                        value="this write should not be duplicated on retry",
                        confidence_hint=74,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach one bounded evidence signal.",
                )
                after_first = len(runtime.store.load("idempotent-evidence-aix").claims)
                second = orchestrator.run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id="idempotent-evidence-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=EvidenceSignalDraft(
                        input_id="idempotent-evidence-1",
                        subject="AIX",
                        predicate="fresh_supportive_flow",
                        value="this write should not be duplicated on retry",
                        confidence_hint=74,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach one bounded evidence signal.",
                )

            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            delegate_records = artifact_store.list_delegate_artifacts(first.owner_run_id, "evidence_agent", spec_version=1)
            self.assertEqual(first.run_state, "FINALIZED")
            self.assertEqual(second.run_state, "FINALIZED")
            self.assertTrue(second.replayed)
            self.assertEqual(len(runtime.store.load("idempotent-evidence-aix").claims), after_first)
            self.assertEqual(len(delegate_records), 1)

    def test_crash_recovery_resumes_from_delegate_artifact_without_duplicate_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "crash-recovery-aix")
            crash_orchestrator = CrashAfterWriteOrchestrator(runtime=runtime)
            with runtime_worker_harness(slug="rulebook-crash-recovery", scope="spot+perp"):
                with self.assertRaises(RuntimeError):
                    crash_orchestrator.run_governed_write(
                        requested_delegate_id="evidence_agent",
                        object_id="crash-recovery-aix",
                        subject="AIX",
                        scope="spot+perp",
                        signal_draft=EvidenceSignalDraft(
                            input_id="crash-recovery-1",
                            subject="AIX",
                            predicate="fresh_supportive_flow",
                            value="delegate write should be reused after a crash",
                            confidence_hint=74,
                        ),
                        artifacts_root=tmpdir,
                        user_intent="Attach one bounded evidence signal.",
                    )
                after_crash = len(runtime.store.load("crash-recovery-aix").claims)
                resumed = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id="crash-recovery-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=EvidenceSignalDraft(
                        input_id="crash-recovery-1",
                        subject="AIX",
                        predicate="fresh_supportive_flow",
                        value="delegate write should be reused after a crash",
                        confidence_hint=74,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach one bounded evidence signal.",
                )

            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            delegate_records = artifact_store.list_delegate_artifacts(resumed.owner_run_id, "evidence_agent", spec_version=1)
            self.assertEqual(resumed.run_state, "FINALIZED")
            self.assertTrue(resumed.replayed)
            self.assertEqual(len(runtime.store.load("crash-recovery-aix").claims), after_crash)
            self.assertEqual(len(delegate_records), 1)

    def test_spec_version_change_creates_new_review_records_and_ignores_old_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, "spec-version-aix")
            orchestrator = GovernedAgentOrchestrator(runtime=runtime)

            with runtime_worker_harness(slug="rulebook-spec-version", scope="spot+perp"):
                first = orchestrator.run_governed_write(
                    requested_delegate_id="validation_agent",
                    object_id="spec-version-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=ValidationBlockerSignalDraft(
                        input_id="spec-version-1",
                        subject="AIX",
                        predicate="publish_gate_hold",
                        value="first validation run",
                        confidence_hint=71,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach validation blocker v1.",
                )
                second = orchestrator.run_governed_write(
                    requested_delegate_id="validation_agent",
                    object_id="spec-version-aix",
                    subject="AIX",
                    scope="spot+perp",
                    signal_draft=ValidationBlockerSignalDraft(
                        input_id="spec-version-2",
                        subject="AIX",
                        predicate="publish_gate_hold",
                        value="second validation run with a changed spec",
                        confidence_hint=72,
                    ),
                    artifacts_root=tmpdir,
                    user_intent="Attach validation blocker v2 with updated operator intent.",
                )

            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            old_reviews = artifact_store.list_review_artifacts(first.owner_run_id, "validation_review", spec_version=1)
            new_reviews = artifact_store.list_review_artifacts(second.owner_run_id, "validation_review", spec_version=2)
            self.assertEqual(first.spec_version, 1)
            self.assertEqual(second.spec_version, 2)
            self.assertEqual(len(old_reviews), 1)
            self.assertEqual(len(new_reviews), 1)
            self.assertNotEqual(old_reviews[0]["artifact_path"], new_reviews[0]["artifact_path"])


def _build_runtime(tmpdir: str) -> RuntimeOrchestrator:
    firewall = AgentIngressFirewall(
        quarantine_buffer=QuarantineBuffer(Path(tmpdir) / "quarantine"),
        replayable_input_log=ReplayableInputLog(Path(tmpdir) / "replay_log"),
    )
    return RuntimeOrchestrator(
        store=InMemoryObjectStore(),
        agent_ingress_firewall=firewall,
    )


def _seed_object(runtime: RuntimeOrchestrator, object_id: str) -> None:
    with runtime_worker_harness(slug=f"seed-{object_id}", scope="spot+perp"):
        runtime.run_new(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=sample_signals(object_id),
        )


if __name__ == "__main__":
    unittest.main()
