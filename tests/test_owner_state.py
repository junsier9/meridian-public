from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enhengclaw.agents.owner_state import (
    BacklogItem,
    CapabilityStatus,
    DelegateArtifactRecord,
    DelegateCapabilityRecord,
    FinalOutputRecord,
    IntermediateFinding,
    OwnerArtifactStore,
    OwnerArtifactWriter,
    OwnerRunRecord,
    OwnerRunState,
    OwnerWorkSpec,
    ReviewArtifactRecord,
    VerificationItem,
    _legacy_capability_artifact_filename,
    compute_delegate_capability_id,
    compute_spec_fingerprint,
)


class OwnerArtifactStoreTests(unittest.TestCase):
    def test_owner_artifact_store_persists_nested_owner_delegate_and_review_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(tmpdir)
            run_id = "demo-run"
            paths = store.paths_for(run_id)

            spec_path = store.write_spec(
                OwnerWorkSpec(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    requested_delegate_id="evidence_agent",
                    object_id="aix-demo",
                    subject="AIX",
                    scope="spot+perp",
                    user_intent="Continue one existing object with one evidence signal.",
                    spec_version=2,
                )
            )
            run_state_path = store.write_run_state(
                OwnerRunRecord(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    requested_delegate_id="evidence_agent",
                    object_id="aix-demo",
                    subject="AIX",
                    scope="spot+perp",
                    state=OwnerRunState.PLANNED.value,
                    spec_version=2,
                    spec_fingerprint="spec-v2",
                    current_step_id="plan-1",
                )
            )
            backlog_path = store.write_backlog(
                run_id,
                [BacklogItem("t1", "Capture spec", "done", "rulebook_owner", step_id="plan-1", spec_version=2)],
                spec_version=2,
                step_id="plan-1",
            )
            findings_path = store.write_findings(
                run_id,
                [IntermediateFinding("f1", "rulebook_owner", "owner rollup updated", step_id="plan-1", spec_version=2)],
                spec_version=2,
                step_id="plan-1",
            )
            execution_path = store.write_execution_artifact(
                run_id,
                "input",
                {
                    "run_id": run_id,
                    "step_id": "plan-1",
                    "spec_version": 2,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "provenance": "market_observer_execution",
                    "artifact_kind": "market_observer_input",
                    "input": {"observation_text": "supportive structure"},
                },
            )
            delegate_path = store.append_delegate_artifact(
                DelegateArtifactRecord(
                    run_id=run_id,
                    delegate_name="evidence_agent",
                    sequence=1,
                    step_id="delegate-1",
                    spec_version=2,
                    owner_run_id=run_id,
                    idempotency_key="idem-1",
                    requested_delegate_id="evidence_agent",
                    initiated_by="rulebook_owner",
                    object_id="aix-demo",
                    subject="AIX",
                    scope="spot+perp",
                    scenario="owner_first:evidence_agent",
                    signal_payload={"predicate": "fresh_supportive_flow"},
                    accepted_signal_ids=("signal-1",),
                )
            )
            review_path = store.append_review_artifact(
                ReviewArtifactRecord(
                    run_id=run_id,
                    review_name="validation_review",
                    sequence=1,
                    step_id="delegate-1",
                    spec_version=2,
                    owner_run_id=run_id,
                    requested_delegate_id="evidence_agent",
                    reviewer_agent_id="rulebook_owner",
                    object_id="aix-demo",
                    gate_applied=True,
                    gate_passed=True,
                    payload={"decision": "monitoring"},
                )
            )
            verification_path = store.write_verification(
                run_id,
                [VerificationItem("v1", "replay log exists", "passed", ("replay.json",), step_id="delegate-1", spec_version=2)],
                spec_version=2,
                step_id="delegate-1",
            )
            final_output_path = store.write_final_output(
                FinalOutputRecord(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    selected_delegate_id="evidence_agent",
                    status="completed",
                    summary="Owner finalized one bounded delegate execution.",
                    output_paths=("session.json",),
                    run_state=OwnerRunState.FINALIZED.value,
                    spec_version=2,
                    step_id="delegate-1",
                )
            )

            self.assertEqual(spec_path, paths.spec_path)
            self.assertEqual(run_state_path, paths.run_state_path)
            self.assertEqual(backlog_path, paths.backlog_path)
            self.assertEqual(findings_path, paths.findings_path)
            self.assertEqual(Path(execution_path).parent, paths.agent_execution_root)
            self.assertEqual(Path(delegate_path).parent.parent, paths.delegates_root)
            self.assertEqual(Path(review_path).parent.parent, paths.reviews_root)
            self.assertEqual(verification_path, paths.verification_path)
            self.assertEqual(final_output_path, paths.final_output_path)

            for path in (
                spec_path,
                run_state_path,
                backlog_path,
                findings_path,
                execution_path,
                delegate_path,
                review_path,
                verification_path,
                final_output_path,
            ):
                self.assertTrue(Path(path).exists())
                self.assertIsInstance(store.load_json(path), dict)
            self.assertEqual(len(store.list_execution_artifacts(run_id)), 1)
            self.assertEqual(store.load_execution_artifact(run_id, "input")["artifact_kind"], "market_observer_input")

    def test_owner_artifact_store_recovers_run_state_from_nested_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(tmpdir)
            run_id = "recover-run"
            store.write_spec(
                OwnerWorkSpec(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    requested_delegate_id="validation_agent",
                    object_id="recover-aix",
                    subject="AIX",
                    scope="spot+perp",
                    user_intent="Recover and resume the owner run.",
                )
            )
            store.append_delegate_artifact(
                DelegateArtifactRecord(
                    run_id=run_id,
                    delegate_name="validation_agent",
                    sequence=1,
                    step_id="validation:1:abc",
                    spec_version=1,
                    owner_run_id=run_id,
                    idempotency_key="abc",
                    requested_delegate_id="validation_agent",
                    initiated_by="rulebook_owner",
                    object_id="recover-aix",
                    subject="AIX",
                    scope="spot+perp",
                    scenario="owner_first:validation_agent",
                    signal_payload={"predicate": "publish_gate_hold"},
                    accepted_signal_ids=("signal-1",),
                )
            )

            recovered = store.load_run_record(run_id)
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered["state"], OwnerRunState.WRITTEN.value)
            self.assertEqual(recovered["requested_delegate_id"], "validation_agent")

    def test_owner_artifact_store_persists_and_filters_delegate_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(tmpdir)
            run_id = "capability-run"
            capability_id = compute_delegate_capability_id(
                owner_run_id=run_id,
                requested_delegate_id="evidence_agent",
                spec_version=2,
                step_id="evidence:2:abc",
                idempotency_key="idem-2",
                object_id="capability-aix",
                subject="AIX",
                scope="spot+perp",
            )
            store.write_capability(
                DelegateCapabilityRecord(
                    capability_id=capability_id,
                    owner_run_id=run_id,
                    requested_delegate_id="evidence_agent",
                    spec_version=2,
                    step_id="evidence:2:abc",
                    idempotency_key="idem-2",
                    object_id="capability-aix",
                    subject="AIX",
                    scope="spot+perp",
                )
            )
            active = store.find_capability(capability_id, run_id=run_id)
            self.assertIsNotNone(active)
            self.assertEqual(active["status"], CapabilityStatus.ACTIVE.value)
            store.mark_capability_status(
                capability_id,
                run_id=run_id,
                status=CapabilityStatus.STALE.value,
                stale_reason="spec_version_advanced_to_3",
            )
            stale_records = store.list_capabilities(run_id, status=CapabilityStatus.STALE.value)
            self.assertEqual(len(stale_records), 1)
            self.assertEqual(stale_records[0]["capability_id"], capability_id)

    def test_owner_artifact_store_writes_capabilities_under_long_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_id = "market_observer__golden_success_aix"
            capability_id = compute_delegate_capability_id(
                owner_run_id=run_id,
                requested_delegate_id="market_observer",
                spec_version=1,
                step_id="market_observer:1:a68935c5abac",
                idempotency_key="a68935c5abac9e01b09645e1b35e8c650508ccabb588f0cf327bf2d440289b9e",
                object_id="golden-success-aix",
                subject="AIX",
                scope="spot+perp",
            )
            root = None
            for extra in range(40, 180):
                candidate_root = Path(tmpdir) / ("retained_" + ("x" * extra))
                candidate_store = OwnerArtifactWriter(candidate_root)
                new_length = len(str(candidate_store.capability_path(run_id, capability_id)))
                legacy_length = len(
                    str(candidate_store.capabilities_directory(run_id) / _legacy_capability_artifact_filename(capability_id))
                )
                if new_length < 260 and legacy_length > 260:
                    root = candidate_root
                    break
            self.assertIsNotNone(root, "expected a candidate root where the new capability path is shorter than the legacy path")
            store = OwnerArtifactWriter(root)
            capability_path = store.write_capability(
                DelegateCapabilityRecord(
                    capability_id=capability_id,
                    owner_run_id=run_id,
                    requested_delegate_id="market_observer",
                    spec_version=1,
                    step_id="market_observer:1:a68935c5abac",
                    idempotency_key="a68935c5abac9e01b09645e1b35e8c650508ccabb588f0cf327bf2d440289b9e",
                    object_id="golden-success-aix",
                    subject="AIX",
                    scope="spot+perp",
                )
            )
            self.assertTrue(Path(capability_path).exists())
            self.assertLess(len(str(capability_path)), 260)
            payload = store.find_capability(capability_id, run_id=run_id)
            self.assertIsNotNone(payload)
            self.assertEqual(payload["capability_id"], capability_id)

    def test_owner_artifact_store_finds_legacy_capability_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(tmpdir)
            run_id = "legacy-capability-run"
            capability_id = compute_delegate_capability_id(
                owner_run_id=run_id,
                requested_delegate_id="evidence_agent",
                spec_version=1,
                step_id="evidence_agent:1:legacy",
                idempotency_key="legacy-key",
                object_id="legacy-aix",
                subject="AIX",
                scope="spot+perp",
            )
            legacy_path = store.capabilities_directory(run_id) / _legacy_capability_artifact_filename(capability_id)
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                '{"capability_id": "%s", "owner_run_id": "%s", "requested_delegate_id": "evidence_agent", '
                '"spec_version": 1, "step_id": "evidence_agent:1:legacy", "idempotency_key": "legacy-key", '
                '"object_id": "legacy-aix", "subject": "AIX", "scope": "spot+perp", "status": "ACTIVE"}'
                % (capability_id, run_id),
                encoding="utf-8",
            )

            payload = store.find_capability(capability_id, run_id=run_id)
            self.assertIsNotNone(payload)
            self.assertEqual(payload["capability_id"], capability_id)
            self.assertEqual(Path(payload["artifact_path"]), legacy_path)

    def test_owner_artifact_store_fails_closed_on_finalized_without_delegate_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(tmpdir)
            run_id = "reconcile-run"
            spec = OwnerWorkSpec(
                run_id=run_id,
                owner_agent_id="rulebook_owner",
                requested_delegate_id="validation_agent",
                object_id="reconcile-aix",
                subject="AIX",
                scope="spot+perp",
                user_intent="Recover and reconcile run state.",
            )
            store.write_spec(spec)
            store.write_run_state(
                OwnerRunRecord(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    requested_delegate_id="validation_agent",
                    object_id="reconcile-aix",
                    subject="AIX",
                    scope="spot+perp",
                    state=OwnerRunState.FINALIZED.value,
                    spec_version=1,
                    spec_fingerprint=compute_spec_fingerprint(spec),
                    current_step_id="validation:1:abc",
                )
            )
            store.write_final_output(
                FinalOutputRecord(
                    run_id=run_id,
                    owner_agent_id="rulebook_owner",
                    selected_delegate_id="validation_agent",
                    status="completed",
                    summary="This artifact should be rejected because no delegate record exists.",
                    output_paths=(),
                    run_state=OwnerRunState.FINALIZED.value,
                    spec_version=1,
                    step_id="validation:1:abc",
                )
            )

            reconciled = store.load_run_record(run_id)
            self.assertIsNotNone(reconciled)
            self.assertEqual(reconciled["state"], OwnerRunState.FAILED.value)
            self.assertIn("final_output_finalized_without_delegate_records", reconciled["reconciliation_notes"])


if __name__ == "__main__":
    unittest.main()
