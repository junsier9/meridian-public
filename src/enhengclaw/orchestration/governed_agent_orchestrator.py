from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from enhengclaw.agents.architecture import load_main_owner_manifest
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
    build_owner_run_id,
    compute_delegate_capability_id,
    compute_idempotency_key,
    compute_spec_fingerprint,
)
from enhengclaw.core.enums import ObjectType
from enhengclaw.orchestration.runtime_runner import AgentIngressRuntimeResult, RuntimeOrchestrator


class InvalidOwnerRunTransitionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GovernedWriteRequest:
    requested_delegate_id: str
    object_id: str
    subject: str
    scope: str
    signal_draft: Any | None
    artifacts_root: str | Path | None = None
    execution_permit: Any | None = None
    object_type: ObjectType = ObjectType.ASSET
    user_intent: str = ""
    constraints: tuple[str, ...] = ()
    initiated_by: str = "rulebook_owner"
    admission_blocked_reason: str | None = None
    spec_input_payload: dict[str, Any] | None = None
    admission_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GovernedWriteResult:
    owner_run_id: str
    spec_version: int
    run_state: str
    requested_delegate_id: str
    accepted_signal_ids: tuple[str, ...] = ()
    replay_log_paths: tuple[str, ...] = ()
    quarantine_paths: tuple[str, ...] = ()
    review_artifact_paths: tuple[str, ...] = ()
    delegate_artifact_path: str | None = None
    spec_path: str | None = None
    backlog_path: str | None = None
    verification_path: str | None = None
    final_output_path: str | None = None
    blocked_reason: str | None = None
    replayed: bool = False
    runtime_result: AgentIngressRuntimeResult | None = None


_ALLOWED_TRANSITIONS: dict[OwnerRunState, set[OwnerRunState]] = {
    OwnerRunState.INIT: {OwnerRunState.SPECIFIED, OwnerRunState.FAILED},
    OwnerRunState.SPECIFIED: {OwnerRunState.PLANNED, OwnerRunState.BLOCKED, OwnerRunState.FAILED},
    OwnerRunState.PLANNED: {OwnerRunState.DELEGATED, OwnerRunState.BLOCKED, OwnerRunState.FAILED},
    OwnerRunState.DELEGATED: {OwnerRunState.WRITTEN, OwnerRunState.BLOCKED, OwnerRunState.FAILED},
    OwnerRunState.WRITTEN: {OwnerRunState.REVIEWED, OwnerRunState.VERIFIED, OwnerRunState.BLOCKED, OwnerRunState.FAILED},
    OwnerRunState.REVIEWED: {OwnerRunState.VERIFIED, OwnerRunState.BLOCKED, OwnerRunState.FAILED},
    OwnerRunState.VERIFIED: {OwnerRunState.FINALIZED, OwnerRunState.BLOCKED, OwnerRunState.FAILED},
    OwnerRunState.FINALIZED: set(),
    OwnerRunState.BLOCKED: set(),
    OwnerRunState.FAILED: set(),
}

_REQUIRED_VERIFICATION_ITEM_IDS = {
    "delegate_recorded",
    "accepted_signal_ids",
    "required_reviews_present",
}


class GovernedAgentOrchestrator:
    def __init__(
        self,
        *,
        runtime: RuntimeOrchestrator,
        artifact_store: OwnerArtifactWriter | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self.runtime = runtime
        self.default_store = artifact_store or OwnerArtifactWriter()
        self.manifest = load_main_owner_manifest(manifest_path)
        self.owner = dict(self.manifest["owner"])
        self.delegate_contracts = {
            str(agent["runtime_agent_id"]): dict(agent)
            for agent in self.manifest.get("agents", [])
            if isinstance(agent, dict) and str(agent.get("kind", "")).strip() == "delegate"
        }

    def run_governed_write(
        self,
        *,
        requested_delegate_id: str,
        object_id: str,
        subject: str,
        scope: str,
        signal_draft: Any | None,
        artifacts_root: str | Path | None = None,
        execution_permit: Any | None = None,
        object_type: ObjectType = ObjectType.ASSET,
        user_intent: str = "",
        constraints: tuple[str, ...] = (),
        initiated_by: str = "rulebook_owner",
        admission_blocked_reason: str | None = None,
        spec_input_payload: dict[str, Any] | None = None,
        admission_artifacts: tuple[str, ...] = (),
    ) -> GovernedWriteResult:
        request = GovernedWriteRequest(
            requested_delegate_id=requested_delegate_id,
            object_id=object_id,
            subject=subject,
            scope=scope,
            signal_draft=signal_draft,
            artifacts_root=artifacts_root,
            execution_permit=execution_permit,
            object_type=object_type,
            user_intent=user_intent,
            constraints=constraints,
            initiated_by=initiated_by,
            admission_blocked_reason=admission_blocked_reason,
            spec_input_payload=spec_input_payload,
            admission_artifacts=admission_artifacts,
        )
        return self._run(request)

    def _run(self, request: GovernedWriteRequest) -> GovernedWriteResult:
        contract = self._delegate_contract(request.requested_delegate_id)
        store = self._owner_store(request.artifacts_root)
        if request.signal_draft is None:
            if request.admission_blocked_reason is None:
                raise ValueError("signal_draft=None requires admission_blocked_reason")
            if request.spec_input_payload is None:
                raise ValueError("signal_draft=None requires spec_input_payload")
        owner_run_id = build_owner_run_id(
            requested_delegate_id=request.requested_delegate_id,
            object_id=request.object_id,
        )
        paths = store.paths_for(owner_run_id)
        signal_payload = {} if request.signal_draft is None else dict(request.signal_draft.to_agent_payload())
        spec_input_payload = self._request_spec_payload(request, signal_payload)
        run_record = self._initialize_or_restore_run(
            store=store,
            owner_run_id=owner_run_id,
            request=request,
            spec_input_payload=spec_input_payload,
        )
        spec_version = int(run_record["spec_version"])
        idempotency_key = compute_idempotency_key(
            requested_delegate_id=request.requested_delegate_id,
            object_id=request.object_id,
            subject=request.subject,
            scope=request.scope,
            signal_payload=signal_payload or spec_input_payload,
            spec_version=spec_version,
        )
        step_id = f"{request.requested_delegate_id}:{spec_version}:{idempotency_key[:12]}"
        existing_delegate = None
        if request.signal_draft is not None:
            existing_delegate = store.find_delegate_artifact(
                owner_run_id,
                request.requested_delegate_id,
                spec_version=spec_version,
                idempotency_key=idempotency_key,
            )
        current_state = OwnerRunState.normalize(str(run_record["state"]))
        if current_state in {OwnerRunState.FINALIZED, OwnerRunState.BLOCKED, OwnerRunState.FAILED}:
            final_output_path = paths.final_output_path if paths.final_output_path.exists() else None
            if final_output_path is not None:
                final_output_payload = store.load_json(final_output_path)
                return GovernedWriteResult(
                    owner_run_id=owner_run_id,
                    spec_version=spec_version,
                    run_state=current_state.value,
                    requested_delegate_id=request.requested_delegate_id,
                    accepted_signal_ids=tuple(str(item) for item in (() if existing_delegate is None else existing_delegate.get("accepted_signal_ids", ()))),
                    replay_log_paths=tuple(str(item) for item in (() if existing_delegate is None else existing_delegate.get("replay_log_paths", ()))),
                    quarantine_paths=tuple(str(item) for item in (() if existing_delegate is None else existing_delegate.get("quarantine_paths", ()))),
                    delegate_artifact_path=None if existing_delegate is None else str(existing_delegate["artifact_path"]),
                    spec_path=str(paths.spec_path),
                    backlog_path=str(paths.backlog_path) if paths.backlog_path.exists() else None,
                    verification_path=str(paths.verification_path) if paths.verification_path.exists() else None,
                    final_output_path=str(final_output_path),
                    blocked_reason=str(final_output_payload.get("blocked_reason", "")) or None,
                    replayed=True,
                    runtime_result=None,
                )
        run_record = self._rewrite_backlog(
            store=store,
            run_record=run_record,
            spec_version=spec_version,
            step_id=step_id,
        )
        if request.admission_blocked_reason:
            return self._blocked_without_delegate_result(
                store=store,
                run_record=run_record,
                request=request,
                paths=paths,
                step_id=step_id,
                spec_version=spec_version,
                blocked_reason=request.admission_blocked_reason,
                replayed=False,
            )
        live_result: AgentIngressRuntimeResult | None = None
        replayed = existing_delegate is not None
        if existing_delegate is None:
            run_record = self._transition(
                store=store,
                run_record=run_record,
                new_state=OwnerRunState.DELEGATED,
                step_id=step_id,
                idempotency_key=idempotency_key,
            )
            live_result = self._execute_delegate_write(
                store=store,
                run_record=run_record,
                contract=contract,
                request=request,
                step_id=step_id,
                spec_version=spec_version,
                idempotency_key=idempotency_key,
                signal_payload=signal_payload,
            )
            existing_delegate = store.find_delegate_artifact(
                owner_run_id,
                request.requested_delegate_id,
                spec_version=spec_version,
                idempotency_key=idempotency_key,
            )
        if existing_delegate is None:
            raise RuntimeError("delegate write did not persist an artifact record")

        return self._complete_run(
            store=store,
            run_record=store.load_run_record(owner_run_id) or run_record,
            contract=contract,
            request=request,
            paths=paths,
            step_id=step_id,
            spec_version=spec_version,
            delegate_payload=existing_delegate,
            replayed=replayed,
            runtime_result=live_result,
        )

    def _complete_run(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        contract: dict[str, Any],
        request: GovernedWriteRequest,
        paths,
        step_id: str,
        spec_version: int,
        delegate_payload: dict[str, Any],
        replayed: bool,
        runtime_result: AgentIngressRuntimeResult | None,
    ) -> GovernedWriteResult:
        try:
            review_paths, blocked_reason = self._run_required_reviews(
                store=store,
                run_record=run_record,
                contract=contract,
                request=request,
                spec_version=spec_version,
                step_id=step_id,
            )
        except Exception as exc:
            self._fail_closed(
                store=store,
                run_record=run_record,
                spec_version=spec_version,
                step_id=step_id,
                requested_delegate_id=request.requested_delegate_id,
                summary=f"Owner failed while evaluating required reviews for '{request.requested_delegate_id}'.",
                blocked_reason=str(exc),
            )
            run_record = store.load_run_record(str(run_record["run_id"])) or run_record
            return GovernedWriteResult(
                owner_run_id=str(run_record["run_id"]),
                spec_version=spec_version,
                run_state=OwnerRunState.FAILED.value,
                requested_delegate_id=request.requested_delegate_id,
                accepted_signal_ids=tuple(str(item) for item in delegate_payload.get("accepted_signal_ids", ())),
                replay_log_paths=tuple(str(item) for item in delegate_payload.get("replay_log_paths", ())),
                quarantine_paths=tuple(str(item) for item in delegate_payload.get("quarantine_paths", ())),
                delegate_artifact_path=str(delegate_payload["artifact_path"]),
                spec_path=str(paths.spec_path),
                backlog_path=str(paths.backlog_path),
                verification_path=str(paths.verification_path) if paths.verification_path.exists() else None,
                final_output_path=str(paths.final_output_path) if paths.final_output_path.exists() else None,
                blocked_reason=str(exc),
                replayed=replayed,
                runtime_result=runtime_result,
            )
        run_record = store.load_run_record(str(run_record["run_id"])) or run_record
        if blocked_reason is not None:
            return self._blocked_result(
                store=store,
                run_record=run_record,
                request=request,
                paths=paths,
                step_id=step_id,
                spec_version=spec_version,
                delegate_payload=delegate_payload,
                review_paths=review_paths,
                required_review_count=len(self._required_reviews(contract)),
                blocked_reason=blocked_reason,
                replayed=replayed,
                runtime_result=runtime_result,
            )

        verification_items = self._verification_items(
            delegate_payload=delegate_payload,
            review_paths=review_paths,
            required_review_count=len(self._required_reviews(contract)),
            spec_version=spec_version,
            step_id=step_id,
            blocked_reason=None,
        )
        verification_path = store.write_verification(
            str(run_record["run_id"]),
            verification_items,
            owner_agent_id=str(self.owner["agent_id"]),
            spec_version=spec_version,
            step_id=step_id,
        )
        if not self._verification_complete(verification_items):
            return self._blocked_result(
                store=store,
                run_record=run_record,
                request=request,
                paths=paths,
                step_id=step_id,
                spec_version=spec_version,
                delegate_payload=delegate_payload,
                review_paths=review_paths,
                required_review_count=len(self._required_reviews(contract)),
                blocked_reason="verification_incomplete",
                replayed=replayed,
                runtime_result=runtime_result,
                verification_path=str(verification_path),
            )

        if self._required_reviews(contract):
            run_record = self._transition(
                store=store,
                run_record=run_record,
                new_state=OwnerRunState.REVIEWED,
                step_id=step_id,
            )
        run_record = self._transition(
            store=store,
            run_record=run_record,
            new_state=OwnerRunState.VERIFIED,
            step_id=step_id,
        )
        store.write_findings(
            str(run_record["run_id"]),
            [
                IntermediateFinding(
                    finding_id=f"{step_id}:delegate",
                    author_agent_id=request.requested_delegate_id,
                    summary=f"Delegate '{request.requested_delegate_id}' completed one bounded write.",
                    evidence=(*request.admission_artifacts, str(delegate_payload["artifact_path"]), *review_paths),
                    step_id=step_id,
                    spec_version=spec_version,
                )
            ],
            owner_agent_id=str(self.owner["agent_id"]),
            spec_version=spec_version,
            step_id=step_id,
                summary=f"Owner finalized delegate '{request.requested_delegate_id}' after verification.",
        )
        final_output_path = store.write_final_output(
            FinalOutputRecord(
                run_id=str(run_record["run_id"]),
                owner_agent_id=str(self.owner["agent_id"]),
                selected_delegate_id=request.requested_delegate_id,
                status="completed",
                summary=f"Owner finalized one governed write via '{request.requested_delegate_id}'.",
                output_paths=(*request.admission_artifacts, str(delegate_payload["artifact_path"]), *review_paths),
                run_state=OwnerRunState.FINALIZED.value,
                spec_version=spec_version,
                step_id=step_id,
            )
        )
        run_record = self._transition(
            store=store,
            run_record=run_record,
            new_state=OwnerRunState.FINALIZED,
            step_id=step_id,
            final_output_path=str(final_output_path),
        )
        return GovernedWriteResult(
            owner_run_id=str(run_record["run_id"]),
            spec_version=spec_version,
            run_state=OwnerRunState.FINALIZED.value,
            requested_delegate_id=request.requested_delegate_id,
            accepted_signal_ids=tuple(str(item) for item in delegate_payload.get("accepted_signal_ids", ())),
            replay_log_paths=tuple(str(item) for item in delegate_payload.get("replay_log_paths", ())),
            quarantine_paths=tuple(str(item) for item in delegate_payload.get("quarantine_paths", ())),
            review_artifact_paths=review_paths,
            delegate_artifact_path=str(delegate_payload["artifact_path"]),
            spec_path=str(paths.spec_path),
            backlog_path=str(paths.backlog_path),
            verification_path=str(verification_path),
            final_output_path=str(final_output_path),
            replayed=replayed,
            runtime_result=runtime_result,
        )

    def _blocked_result(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        request: GovernedWriteRequest,
        paths,
        step_id: str,
        spec_version: int,
        delegate_payload: dict[str, Any],
        review_paths: tuple[str, ...],
        required_review_count: int,
        blocked_reason: str,
        replayed: bool,
        runtime_result: AgentIngressRuntimeResult | None,
        verification_path: str | None = None,
    ) -> GovernedWriteResult:
        if verification_path is None:
            verification_path = str(
                store.write_verification(
                    str(run_record["run_id"]),
                    self._verification_items(
                        delegate_payload=delegate_payload,
                        review_paths=review_paths,
                        required_review_count=required_review_count,
                        spec_version=spec_version,
                        step_id=step_id,
                        blocked_reason=blocked_reason,
                    ),
                    owner_agent_id=str(self.owner["agent_id"]),
                    spec_version=spec_version,
                    step_id=step_id,
                    blocked_reason=blocked_reason,
                )
            )
        final_output_path = store.write_final_output(
            FinalOutputRecord(
                run_id=str(run_record["run_id"]),
                owner_agent_id=str(self.owner["agent_id"]),
                selected_delegate_id=request.requested_delegate_id,
                status="blocked",
                summary=f"Owner blocked finalization for '{request.requested_delegate_id}'.",
                output_paths=(*request.admission_artifacts, str(delegate_payload["artifact_path"]), *review_paths),
                run_state=OwnerRunState.BLOCKED.value,
                spec_version=spec_version,
                step_id=step_id,
                blocked_reason=blocked_reason,
            )
        )
        run_record = self._transition(
            store=store,
            run_record=run_record,
            new_state=OwnerRunState.BLOCKED,
            step_id=step_id,
            blocked_reason=blocked_reason,
            final_output_path=str(final_output_path),
        )
        return GovernedWriteResult(
            owner_run_id=str(run_record["run_id"]),
            spec_version=spec_version,
            run_state=OwnerRunState.BLOCKED.value,
            requested_delegate_id=request.requested_delegate_id,
            accepted_signal_ids=tuple(str(item) for item in delegate_payload.get("accepted_signal_ids", ())),
            replay_log_paths=tuple(str(item) for item in delegate_payload.get("replay_log_paths", ())),
            quarantine_paths=tuple(str(item) for item in delegate_payload.get("quarantine_paths", ())),
            review_artifact_paths=review_paths,
            delegate_artifact_path=str(delegate_payload["artifact_path"]),
            spec_path=str(paths.spec_path),
            backlog_path=str(paths.backlog_path),
            verification_path=verification_path,
            final_output_path=str(final_output_path),
            blocked_reason=blocked_reason,
            replayed=replayed,
            runtime_result=runtime_result,
        )

    def _blocked_without_delegate_result(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        request: GovernedWriteRequest,
        paths,
        step_id: str,
        spec_version: int,
        blocked_reason: str,
        replayed: bool,
    ) -> GovernedWriteResult:
        verification_path = str(
            store.write_verification(
                str(run_record["run_id"]),
                [
                    VerificationItem(
                        "delegate_admission",
                        "delegate passed owner admission checks before execution",
                        "failed",
                        (blocked_reason, *request.admission_artifacts),
                        step_id=step_id,
                        spec_version=spec_version,
                    )
                ],
                owner_agent_id=str(self.owner["agent_id"]),
                spec_version=spec_version,
                step_id=step_id,
                blocked_reason=blocked_reason,
            )
        )
        final_output_path = store.write_final_output(
            FinalOutputRecord(
                run_id=str(run_record["run_id"]),
                owner_agent_id=str(self.owner["agent_id"]),
                selected_delegate_id=request.requested_delegate_id,
                status="blocked",
                summary=f"Owner blocked delegate '{request.requested_delegate_id}' before runtime delegation.",
                output_paths=request.admission_artifacts,
                run_state=OwnerRunState.BLOCKED.value,
                spec_version=spec_version,
                step_id=step_id,
                blocked_reason=blocked_reason,
            )
        )
        run_record = self._transition(
            store=store,
            run_record=run_record,
            new_state=OwnerRunState.BLOCKED,
            step_id=step_id,
            blocked_reason=blocked_reason,
            final_output_path=str(final_output_path),
        )
        return GovernedWriteResult(
            owner_run_id=str(run_record["run_id"]),
            spec_version=spec_version,
            run_state=OwnerRunState.BLOCKED.value,
            requested_delegate_id=request.requested_delegate_id,
            review_artifact_paths=(),
            delegate_artifact_path=None,
            spec_path=str(paths.spec_path),
            backlog_path=str(paths.backlog_path) if paths.backlog_path.exists() else None,
            verification_path=verification_path,
            final_output_path=str(final_output_path),
            blocked_reason=blocked_reason,
            replayed=replayed,
            runtime_result=None,
        )

    def _execute_delegate_write(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        contract: dict[str, Any],
        request: GovernedWriteRequest,
        step_id: str,
        spec_version: int,
        idempotency_key: str,
        signal_payload: dict[str, Any],
    ) -> AgentIngressRuntimeResult:
        capability_id = compute_delegate_capability_id(
            owner_run_id=str(run_record["run_id"]),
            requested_delegate_id=request.requested_delegate_id,
            spec_version=spec_version,
            step_id=step_id,
            idempotency_key=idempotency_key,
            object_id=request.object_id,
            subject=request.subject,
            scope=request.scope,
        )
        store.write_capability(
            DelegateCapabilityRecord(
                capability_id=capability_id,
                owner_run_id=str(run_record["run_id"]),
                requested_delegate_id=request.requested_delegate_id,
                spec_version=spec_version,
                step_id=step_id,
                idempotency_key=idempotency_key,
                object_id=request.object_id,
                subject=request.subject,
                scope=request.scope,
                issued_by=str(self.owner["agent_id"]),
                status=CapabilityStatus.ACTIVE.value,
            )
        )
        try:
            result = self._submit_delegate(
                contract=contract,
                request=request,
                delegate_capability=capability_id,
                artifact_store=store,
            )
        except Exception as exc:
            store.mark_capability_status(
                capability_id,
                run_id=str(run_record["run_id"]),
                status=CapabilityStatus.FAILED.value,
                stale_reason=str(exc),
            )
            self._fail_closed(
                store=store,
                run_record=run_record,
                spec_version=spec_version,
                step_id=step_id,
                requested_delegate_id=request.requested_delegate_id,
                summary=f"Owner failed while delegating '{request.requested_delegate_id}'.",
                blocked_reason=str(exc),
            )
            raise
        sequence = store.next_delegate_sequence(str(run_record["run_id"]), request.requested_delegate_id)
        artifact_path = store.append_delegate_artifact(
            DelegateArtifactRecord(
                run_id=str(run_record["run_id"]),
                delegate_name=request.requested_delegate_id,
                sequence=sequence,
                step_id=step_id,
                spec_version=spec_version,
                owner_run_id=str(run_record["run_id"]),
                idempotency_key=idempotency_key,
                requested_delegate_id=request.requested_delegate_id,
                initiated_by=request.initiated_by,
                object_id=request.object_id,
                subject=request.subject,
                scope=request.scope,
                scenario=self._delegate_scenario(contract),
                signal_payload=signal_payload,
                accepted_signal_ids=tuple(result.accepted_signal_ids),
                replay_log_paths=tuple(result.replay_log_paths),
                quarantine_paths=tuple(result.quarantine_paths),
                runtime_decision=result.runtime_result.decision.decision,
                runtime_processing_state=result.runtime_result.research_object.processing_state.value,
                runtime_risk_state=result.runtime_result.research_object.risk_state.value,
                runtime_claim_count=len(result.runtime_result.claims),
            )
        )
        store.mark_capability_status(
            capability_id,
            run_id=str(run_record["run_id"]),
            status=CapabilityStatus.CONSUMED.value,
        )
        self._transition(
            store=store,
            run_record=run_record,
            new_state=OwnerRunState.WRITTEN,
            step_id=step_id,
            latest_delegate_sequence=sequence,
            idempotency_key=idempotency_key,
        )
        return result

    def _submit_delegate(
        self,
        *,
        contract: dict[str, Any],
        request: GovernedWriteRequest,
        delegate_capability: str,
        artifact_store: OwnerArtifactStore,
    ) -> AgentIngressRuntimeResult:
        submit = _load_callable(self._delegate_submitter(contract))
        return submit(
            runtime=self.runtime,
            object_id=request.object_id,
            signal=request.signal_draft,
            delegate_capability=delegate_capability,
            artifact_store=artifact_store,
            execution_permit=request.execution_permit,
            object_type=request.object_type,
        )

    def _run_required_reviews(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        contract: dict[str, Any],
        request: GovernedWriteRequest,
        spec_version: int,
        step_id: str,
    ) -> tuple[tuple[str, ...], str | None]:
        owner_run_id = str(run_record["run_id"])
        review_paths: list[str] = []
        last_sequence = int(run_record.get("latest_review_sequence", 0))
        for review_tool in self._required_reviews(contract):
            review_name = _review_name(review_tool)
            existing = store.find_review_artifact(
                owner_run_id,
                review_name,
                spec_version=spec_version,
                step_id=step_id,
            )
            if existing is None:
                inspect = _load_callable(review_tool)
                review_payload = inspect(runtime=self.runtime, object_id=request.object_id, spec_version=spec_version)
                gate_passed, rationale = self._evaluate_review_gate(review_tool, review_payload)
                last_sequence = store.next_review_sequence(owner_run_id, review_name)
                artifact_path = store.append_review_artifact(
                    ReviewArtifactRecord(
                        run_id=owner_run_id,
                        review_name=review_name,
                        sequence=last_sequence,
                        step_id=step_id,
                        spec_version=spec_version,
                        owner_run_id=owner_run_id,
                        requested_delegate_id=request.requested_delegate_id,
                        reviewer_agent_id=str(self.owner["agent_id"]),
                        object_id=request.object_id,
                        gate_applied=True,
                        gate_passed=gate_passed,
                        payload=_as_dict(review_payload),
                        rationale=rationale,
                    )
                )
                review_paths.append(str(artifact_path))
                if not gate_passed:
                    self._transition(
                        store=store,
                        run_record=run_record,
                        new_state=OwnerRunState.BLOCKED,
                        step_id=step_id,
                        latest_review_sequence=last_sequence,
                        blocked_reason=f"required review gate failed: {review_name}",
                    )
                    return tuple(review_paths), f"required review gate failed: {review_name}"
            else:
                review_paths.append(str(existing["artifact_path"]))
                last_sequence = max(last_sequence, int(existing.get("sequence", 0)))
                if not bool(existing.get("gate_passed", False)):
                    self._transition(
                        store=store,
                        run_record=run_record,
                        new_state=OwnerRunState.BLOCKED,
                        step_id=step_id,
                        latest_review_sequence=last_sequence,
                        blocked_reason=f"required review gate failed: {review_name}",
                    )
                    return tuple(review_paths), f"required review gate failed: {review_name}"
        if self._required_reviews(contract):
            self._transition(
                store=store,
                run_record=run_record,
                new_state=OwnerRunState.REVIEWED,
                step_id=step_id,
                latest_review_sequence=last_sequence,
            )
        return tuple(review_paths), None

    def _initialize_or_restore_run(
        self,
        *,
        store: OwnerArtifactWriter,
        owner_run_id: str,
        request: GovernedWriteRequest,
        spec_input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        restored = store.load_run_record(owner_run_id)
        previous_spec_version = 0 if restored is None else int(restored.get("spec_version", 0))
        stale_spec_versions = tuple(int(item) for item in (() if restored is None else restored.get("stale_spec_versions", ())))
        base_spec = OwnerWorkSpec(
            run_id=owner_run_id,
            owner_agent_id=str(self.owner["agent_id"]),
            requested_delegate_id=request.requested_delegate_id,
            object_id=request.object_id,
            subject=request.subject,
            scope=request.scope,
            user_intent=request.user_intent or f"Run governed write via '{request.requested_delegate_id}'.",
            constraints=request.constraints,
            signal_payload_fingerprint=_payload_fingerprint(spec_input_payload),
            spec_version=max(previous_spec_version, 1),
        )
        fingerprint = compute_spec_fingerprint(base_spec)
        if restored is not None and str(restored.get("spec_fingerprint", "")) != fingerprint:
            spec_version = previous_spec_version + 1
            if previous_spec_version:
                stale_spec_versions = (*stale_spec_versions, previous_spec_version)
        else:
            spec_version = max(previous_spec_version, 1)
        spec = OwnerWorkSpec(
            run_id=base_spec.run_id,
            owner_agent_id=base_spec.owner_agent_id,
            requested_delegate_id=base_spec.requested_delegate_id,
            object_id=base_spec.object_id,
            subject=base_spec.subject,
            scope=base_spec.scope,
            user_intent=base_spec.user_intent,
            constraints=base_spec.constraints,
            signal_payload_fingerprint=base_spec.signal_payload_fingerprint,
            spec_version=spec_version,
            spec_fingerprint=fingerprint,
        )
        if restored is not None and str(restored.get("spec_fingerprint", "")) == fingerprint:
            if not store.paths_for(owner_run_id).spec_path.exists():
                store.write_spec(spec)
            return restored
        initial = OwnerRunRecord(
            run_id=owner_run_id,
            owner_agent_id=str(self.owner["agent_id"]),
            requested_delegate_id=request.requested_delegate_id,
            object_id=request.object_id,
            subject=request.subject,
            scope=request.scope,
            state=OwnerRunState.INIT.value,
            spec_version=spec.spec_version,
            spec_fingerprint=spec.spec_fingerprint,
            stale_spec_versions=stale_spec_versions,
        )
        store.write_run_state(initial)
        store.write_spec(spec)
        if stale_spec_versions:
            store.clear_owner_control_plane(owner_run_id)
            store.stale_capabilities(
                owner_run_id,
                before_spec_version=spec_version,
                stale_reason=f"spec_version_advanced_to_{spec_version}",
            )
        return self._transition(
            store=store,
            run_record=_as_dict(initial),
            new_state=OwnerRunState.SPECIFIED,
            spec_version=spec.spec_version,
            spec_fingerprint=spec.spec_fingerprint,
            stale_spec_versions=stale_spec_versions,
        )

    def _rewrite_backlog(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        spec_version: int,
        step_id: str,
    ) -> dict[str, Any]:
        current_state = OwnerRunState.normalize(str(run_record["state"]))
        if current_state in {OwnerRunState.INIT, OwnerRunState.SPECIFIED}:
            run_record = self._transition(
                store=store,
                run_record=run_record,
                new_state=OwnerRunState.PLANNED,
                step_id=step_id,
            )
        delegate_id = str(run_record["requested_delegate_id"])
        store.write_backlog(
            str(run_record["run_id"]),
            [
                BacklogItem("capture_spec", "Capture explicit request spec", "done", str(self.owner["agent_id"]), step_id=step_id, spec_version=spec_version),
                BacklogItem("plan_delegate", f"Plan owner-first delegation for {delegate_id}", "done", str(self.owner["agent_id"]), step_id=step_id, spec_version=spec_version),
                BacklogItem("delegate_execution", f"Execute bounded delegate write for {delegate_id}", "pending", str(self.owner["agent_id"]), step_id=step_id, spec_version=spec_version),
                BacklogItem("review_gate", "Run required review gates", "pending", str(self.owner["agent_id"]), step_id=step_id, spec_version=spec_version),
                BacklogItem("verification", "Persist verification checklist", "pending", str(self.owner["agent_id"]), step_id=step_id, spec_version=spec_version),
                BacklogItem("finalize", "Persist owner final output", "pending", str(self.owner["agent_id"]), step_id=step_id, spec_version=spec_version),
            ],
            owner_agent_id=str(self.owner["agent_id"]),
            spec_version=spec_version,
            step_id=step_id,
            stale_spec_versions=tuple(int(item) for item in run_record.get("stale_spec_versions", ())),
        )
        return run_record

    def _verification_items(
        self,
        *,
        delegate_payload: dict[str, Any],
        review_paths: tuple[str, ...],
        required_review_count: int,
        spec_version: int,
        step_id: str,
        blocked_reason: str | None,
    ) -> list[VerificationItem]:
        items = [
            VerificationItem(
                "delegate_recorded",
                "delegate append-only artifact exists",
                "passed" if delegate_payload.get("artifact_path") else "failed",
                (str(delegate_payload.get("artifact_path", "")),),
                step_id=step_id,
                spec_version=spec_version,
            ),
            VerificationItem(
                "accepted_signal_ids",
                "delegate write accepted at least one signal id",
                "passed" if delegate_payload.get("accepted_signal_ids") else "failed",
                tuple(str(item) for item in delegate_payload.get("accepted_signal_ids", ())),
                step_id=step_id,
                spec_version=spec_version,
            ),
            VerificationItem(
                "required_reviews_present",
                "all required review records exist and passed for the current spec version",
                "passed" if len(review_paths) >= required_review_count else "failed",
                review_paths,
                step_id=step_id,
                spec_version=spec_version,
            ),
        ]
        if blocked_reason is not None:
            items.append(
                VerificationItem(
                    "blocked_reason",
                    "owner recorded a blocking reason",
                    "failed",
                    (blocked_reason,),
                    step_id=step_id,
                    spec_version=spec_version,
                )
            )
        return items

    def _verification_complete(self, items: list[VerificationItem]) -> bool:
        present_ids = {item.item_id for item in items}
        if not _REQUIRED_VERIFICATION_ITEM_IDS.issubset(present_ids):
            return False
        return all(item.status == "passed" for item in items if item.required)

    def _evaluate_review_gate(self, review_tool: str, review_payload: Any) -> tuple[bool, tuple[str, ...]]:
        payload = _as_dict(review_payload)
        review_name = str(payload.get("review_name", "")).strip()
        gate_status = str(payload.get("gate_status", "")).strip().lower()
        reasons = tuple(str(item) for item in payload.get("reasons", ()))
        if not review_name:
            raise ValueError(f"review payload is missing review_name for {review_tool}")
        if gate_status not in {"pass", "block"}:
            raise ValueError(f"review payload is missing a valid gate_status for {review_tool}")
        return gate_status == "pass", reasons or ("review record captured",)

    def _transition(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        new_state: OwnerRunState,
        step_id: str = "",
        idempotency_key: str | None = None,
        spec_version: int | None = None,
        spec_fingerprint: str | None = None,
        latest_delegate_sequence: int | None = None,
        latest_review_sequence: int | None = None,
        stale_spec_versions: tuple[int, ...] | None = None,
        blocked_reason: str | None = None,
        final_output_path: str | None = None,
    ) -> dict[str, Any]:
        current_state = OwnerRunState.normalize(str(run_record.get("state", OwnerRunState.INIT.value)))
        if current_state != new_state and new_state not in _ALLOWED_TRANSITIONS[current_state]:
            raise InvalidOwnerRunTransitionError(f"illegal owner run transition: {current_state.value} -> {new_state.value}")
        updated = {
            **run_record,
            "state": new_state.value,
            "current_step_id": step_id or str(run_record.get("current_step_id", "")),
            "current_idempotency_key": idempotency_key if idempotency_key is not None else str(run_record.get("current_idempotency_key", "")),
            "spec_version": int(run_record.get("spec_version", 1) if spec_version is None else spec_version),
            "spec_fingerprint": str(run_record.get("spec_fingerprint", "") if spec_fingerprint is None else spec_fingerprint),
            "latest_delegate_sequence": int(run_record.get("latest_delegate_sequence", 0) if latest_delegate_sequence is None else latest_delegate_sequence),
            "latest_review_sequence": int(run_record.get("latest_review_sequence", 0) if latest_review_sequence is None else latest_review_sequence),
            "stale_spec_versions": list(run_record.get("stale_spec_versions", ()) if stale_spec_versions is None else stale_spec_versions),
            "blocked_reason": blocked_reason if blocked_reason is not None else run_record.get("blocked_reason"),
            "final_output_path": final_output_path if final_output_path is not None else run_record.get("final_output_path"),
        }
        store.write_run_state(
            OwnerRunRecord(
                run_id=str(updated["run_id"]),
                owner_agent_id=str(updated["owner_agent_id"]),
                requested_delegate_id=str(updated["requested_delegate_id"]),
                object_id=str(updated["object_id"]),
                subject=str(updated["subject"]),
                scope=str(updated["scope"]),
                state=str(updated["state"]),
                spec_version=int(updated["spec_version"]),
                spec_fingerprint=str(updated["spec_fingerprint"]),
                current_step_id=str(updated.get("current_step_id", "")),
                current_idempotency_key=str(updated.get("current_idempotency_key", "")),
                latest_delegate_sequence=int(updated.get("latest_delegate_sequence", 0)),
                latest_review_sequence=int(updated.get("latest_review_sequence", 0)),
                stale_spec_versions=tuple(int(item) for item in updated.get("stale_spec_versions", ())),
                blocked_reason=None if updated.get("blocked_reason") is None else str(updated["blocked_reason"]),
                final_output_path=None if updated.get("final_output_path") is None else str(updated["final_output_path"]),
            )
        )
        return updated

    def _fail_closed(
        self,
        *,
        store: OwnerArtifactWriter,
        run_record: dict[str, Any],
        spec_version: int,
        step_id: str,
        requested_delegate_id: str,
        summary: str,
        blocked_reason: str,
    ) -> None:
        verification_path = store.write_verification(
            str(run_record["run_id"]),
            [
                VerificationItem(
                    "delegate_execution",
                    "delegate execution completed without runtime exception",
                    "failed",
                    (blocked_reason,),
                    step_id=step_id,
                    spec_version=spec_version,
                )
            ],
            owner_agent_id=str(self.owner["agent_id"]),
            spec_version=spec_version,
            step_id=step_id,
            blocked_reason=blocked_reason,
        )
        final_output_path = store.write_final_output(
            FinalOutputRecord(
                run_id=str(run_record["run_id"]),
                owner_agent_id=str(self.owner["agent_id"]),
                selected_delegate_id=requested_delegate_id,
                status="failed",
                summary=summary,
                output_paths=(str(verification_path),),
                run_state=OwnerRunState.FAILED.value,
                spec_version=spec_version,
                step_id=step_id,
                blocked_reason=blocked_reason,
            )
        )
        self._transition(
            store=store,
            run_record=run_record,
            new_state=OwnerRunState.FAILED,
            step_id=step_id,
            blocked_reason=blocked_reason,
            final_output_path=str(final_output_path),
        )

    def _delegate_contract(self, requested_delegate_id: str) -> dict[str, Any]:
        contract = self.delegate_contracts.get(requested_delegate_id)
        if contract is None:
            raise ValueError(f"unsupported governed delegate id: {requested_delegate_id}")
        return contract

    def _owner_store(self, artifacts_root: str | Path | None) -> OwnerArtifactWriter:
        if artifacts_root is None:
            return self.default_store
        root = Path(artifacts_root).resolve()
        if root.name != "agent_owner":
            root = root / "agent_owner"
        return OwnerArtifactWriter(root)

    def _required_reviews(self, contract: dict[str, Any]) -> list[str]:
        return [str(item) for item in contract.get("required_reviews", []) if str(item).strip()]

    def _request_spec_payload(self, request: GovernedWriteRequest, signal_payload: dict[str, Any]) -> dict[str, Any]:
        if request.spec_input_payload is not None:
            return {str(key): _normalize_value(value) for key, value in request.spec_input_payload.items()}
        return signal_payload

    def _delegate_submitter(self, contract: dict[str, Any]) -> str:
        for tool in contract.get("allowed_tools", []):
            tool_name = str(tool).strip()
            if ".runtime_signal_intake.submit_" in tool_name:
                return tool_name
        raise ValueError(f"delegate contract is missing a runtime submitter: {contract.get('agent_id')}")

    def _delegate_scenario(self, contract: dict[str, Any]) -> str:
        return f"owner_first:{contract['runtime_agent_id']}"


def _load_callable(entrypoint: str):
    module_name, _, attribute_name = entrypoint.rpartition(".")
    module = import_module(module_name)
    return getattr(module, attribute_name)


def _review_name(tool_entrypoint: str) -> str:
    return tool_entrypoint.rsplit(".", 1)[-1].removeprefix("inspect_")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {str(key): _normalize_value(item) for key, item in asdict(value).items()}
    raise TypeError(f"payload must be dataclass-like or dict, got {type(value).__name__}")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return value


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
