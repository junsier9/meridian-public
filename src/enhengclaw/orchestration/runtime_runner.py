from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from enhengclaw.adapters.adapters import (
    AdapterBatch,
    AdapterRequest,
    SignalAdapter,
    collect_and_validate_batches,
    merge_adapter_batches,
)
from enhengclaw.core.execution_control import (
    CAP_PROVIDER_FETCH,
    CAP_RUNTIME_EXECUTE,
    EXECUTION_PERMIT_PATH_ENV,
    RUNTIME_WORKER_ENTRYPOINT,
    ExecutionPermit,
    WORKER_MODE_ENV,
    bind_execution_context,
    cleanup_orphan_execution_leases,
    resolve_execution_permit,
    require_active_worker_lease,
    require_execution_context,
)
from enhengclaw.core.attention import calculate_attention_score
from enhengclaw.core.cadence import CadencePlan, cadence_for_object
from enhengclaw.core.claims import Claim, claim_from_signal
from enhengclaw.core.conflicts import ConflictGroup, group_claim_conflicts
from enhengclaw.core.enums import (
    ClaimStatus,
    ConflictSeverity,
    ObjectType,
    ProcessingState,
    RiskState,
    ThesisStatus,
    ThesisType,
)
from enhengclaw.core.publish_gate import PublishDecision, PublishDecisionType, PublishGate
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.resources import ResourceAllocation, ResourceAllocator
from enhengclaw.core.runtime_rules import RuntimeRuleService
from enhengclaw.core.session import (
    FileObjectStore,
    InMemoryObjectStore,
    RuntimeSession,
    cadence_plan_from_record,
    cadence_plan_to_record,
    claim_from_record,
    claim_to_record,
    conflict_group_from_record,
    conflict_group_to_record,
    publish_decision_from_record,
    publish_decision_to_record,
    research_object_from_record,
    research_object_to_record,
    resource_allocation_from_record,
    resource_allocation_to_record,
    thesis_from_record,
    thesis_to_record,
)
from enhengclaw.core.signals import Signal
from enhengclaw.core.state_machine import StateMachine
from enhengclaw.core.thesis import Thesis, evaluate_thesis_conflict, select_working_theses
from enhengclaw.orchestration.worker_operations import (
    WORKER_REQUEST_SCHEMA_VERSION,
    WorkerTaskActiveError,
    acquire_task_lock,
    append_audit_event,
    audited_subprocess_run,
    build_run_id,
    build_worker_request_envelope,
    copy_request_artifact,
    default_runtime_audit_root,
    initialize_audit_record,
    prepare_run_root,
    read_audit_record,
    read_business_intent_record,
    release_task_lock,
    task_lock_path_for,
    update_audit_record,
    update_business_intent_record,
)
from enhengclaw.utils.subject_keys import SubjectKey, parse_subject_key_fragment

if TYPE_CHECKING:
    from enhengclaw.governance.provider_portfolio import ProviderPortfolioReport
    from enhengclaw.governance.provider_selection import ProviderRuntimeBinding, ProviderSelectionGateway, ProviderSelectionResult
    from enhengclaw.health.downstream_ingress import DownstreamIngressGuard
    from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall


class RuntimeBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeExecutionProfile:
    attention_threshold: int = 70
    extra_risk_penalty: int = 0


@dataclass(slots=True)
class RuntimeStepLog:
    cycle: int
    step: str
    status: str
    processing_state_before: str
    processing_state_after: str
    details: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeResult:
    research_object: ResearchObject
    claims: list[Claim]
    conflict_groups: list[ConflictGroup]
    theses: list[Thesis]
    decision: PublishDecision
    cadence: CadencePlan
    resource_allocation: ResourceAllocation | None
    steps: list[RuntimeStepLog]


@dataclass(slots=True)
class RuntimeRunRequest:
    mode: str
    object_id: str
    signals: list[Signal]
    object_type: ObjectType | None = None
    scope: str | None = None
    execution_profile: RuntimeExecutionProfile | None = None


@dataclass(slots=True)
class AdapterRuntimeResult:
    adapter_request: AdapterRequest
    adapter_batches: list[AdapterBatch]
    runtime_result: RuntimeResult
    selection_result: ProviderSelectionResult | None = None


@dataclass(slots=True)
class ProviderAdapterRuntimeResult:
    adapter_request: AdapterRequest
    adapter_batches: list[AdapterBatch]
    runtime_result: RuntimeResult
    selection_result: ProviderSelectionResult


@dataclass(slots=True)
class AgentIngressRuntimeResult:
    runtime_result: RuntimeResult
    replay_log_paths: list[str]
    quarantine_paths: list[str]
    accepted_signal_ids: list[str]


def signal_to_record(signal: Signal) -> dict[str, object]:
    return {
        "signal_id": signal.signal_id,
        "object_type": signal.object_type.value,
        "subject": signal.subject,
        "predicate": signal.predicate,
        "value": signal.value,
        "claim_type": signal.claim_type.value,
        "direction": signal.direction.value,
        "source_family": signal.source_family.value,
        "evidence_level": signal.evidence_level.value,
        "confidence_hint": signal.confidence_hint,
        "scope": signal.scope,
        "time_horizon": signal.time_horizon.value,
        "fresh": signal.fresh,
    }


def signal_from_record(payload: dict[str, object]) -> Signal:
    from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon

    return Signal(
        signal_id=str(payload["signal_id"]),
        object_type=ObjectType(payload["object_type"]),
        subject=str(payload["subject"]),
        predicate=str(payload["predicate"]),
        value=str(payload["value"]),
        claim_type=ClaimType(payload["claim_type"]),
        direction=Direction(payload["direction"]),
        source_family=SourceFamily(payload["source_family"]),
        evidence_level=EvidenceLevel(payload["evidence_level"]),
        confidence_hint=int(payload["confidence_hint"]),
        scope=str(payload.get("scope", "global")),
        time_horizon=TimeHorizon(payload.get("time_horizon", "intraday")),
        fresh=bool(payload.get("fresh", True)),
    )


def runtime_execution_profile_to_record(profile: RuntimeExecutionProfile | None) -> dict[str, object] | None:
    if profile is None:
        return None
    return {
        "attention_threshold": profile.attention_threshold,
        "extra_risk_penalty": profile.extra_risk_penalty,
    }


def runtime_execution_profile_from_record(payload: dict[str, object] | None) -> RuntimeExecutionProfile | None:
    if payload is None:
        return None
    return RuntimeExecutionProfile(
        attention_threshold=int(payload.get("attention_threshold", 70)),
        extra_risk_penalty=int(payload.get("extra_risk_penalty", 0)),
    )


def runtime_step_to_record(step: RuntimeStepLog) -> dict[str, object]:
    return {
        "cycle": step.cycle,
        "step": step.step,
        "status": step.status,
        "processing_state_before": step.processing_state_before,
        "processing_state_after": step.processing_state_after,
        "details": dict(step.details),
    }


def runtime_step_from_record(payload: dict[str, object]) -> RuntimeStepLog:
    return RuntimeStepLog(
        cycle=int(payload["cycle"]),
        step=str(payload["step"]),
        status=str(payload["status"]),
        processing_state_before=str(payload["processing_state_before"]),
        processing_state_after=str(payload["processing_state_after"]),
        details=dict(payload.get("details", {})),
    )


def runtime_result_to_record(result: RuntimeResult) -> dict[str, object]:
    return {
        "research_object": research_object_to_record(result.research_object),
        "claims": [claim_to_record(item) for item in result.claims],
        "conflict_groups": [conflict_group_to_record(item) for item in result.conflict_groups],
        "theses": [thesis_to_record(item) for item in result.theses],
        "decision": publish_decision_to_record(result.decision),
        "cadence": cadence_plan_to_record(result.cadence),
        "resource_allocation": None
        if result.resource_allocation is None
        else resource_allocation_to_record(result.resource_allocation),
        "steps": [runtime_step_to_record(item) for item in result.steps],
    }


def runtime_result_from_record(payload: dict[str, object]) -> RuntimeResult:
    return RuntimeResult(
        research_object=research_object_from_record(dict(payload["research_object"])),
        claims=[claim_from_record(dict(item)) for item in payload.get("claims", [])],
        conflict_groups=[conflict_group_from_record(dict(item)) for item in payload.get("conflict_groups", [])],
        theses=[thesis_from_record(dict(item)) for item in payload.get("theses", [])],
        decision=publish_decision_from_record(dict(payload["decision"])),
        cadence=cadence_plan_from_record(dict(payload["cadence"])),
        resource_allocation=None
        if payload.get("resource_allocation") is None
        else resource_allocation_from_record(dict(payload["resource_allocation"])),
        steps=[runtime_step_from_record(dict(item)) for item in payload.get("steps", [])],
    )


def runtime_run_request_to_record(request: RuntimeRunRequest) -> dict[str, object]:
    return {
        "mode": request.mode,
        "object_id": request.object_id,
        "signals": [signal_to_record(signal) for signal in request.signals],
        "object_type": None if request.object_type is None else request.object_type.value,
        "scope": request.scope,
        "execution_profile": runtime_execution_profile_to_record(request.execution_profile),
    }


def runtime_run_request_from_record(payload: dict[str, object]) -> RuntimeRunRequest:
    from enhengclaw.core.enums import ObjectType

    return RuntimeRunRequest(
        mode=str(payload["mode"]),
        object_id=str(payload["object_id"]),
        signals=[signal_from_record(dict(item)) for item in payload.get("signals", [])],
        object_type=None if payload.get("object_type") is None else ObjectType(payload["object_type"]),
        scope=None if payload.get("scope") is None else str(payload["scope"]),
        execution_profile=runtime_execution_profile_from_record(
            None if payload.get("execution_profile") is None else dict(payload["execution_profile"])
        ),
    )


def normalize_business_request_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("run_batch requires a non-empty business_request_id")
    return value.strip()


def fingerprint_runtime_batch_requests(request_records: list[dict[str, object]]) -> str:
    canonical = json.dumps(request_records, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def adapter_request_to_record(request: AdapterRequest) -> dict[str, object]:
    return {
        "object_id": request.object_id,
        "object_type": request.object_type.value,
        "subject": request.subject,
        "scope": request.scope,
        "scenario": request.scenario,
        "venue": request.venue,
        "instrument_type": request.instrument_type,
        "time_horizon": request.time_horizon.value,
    }


def adapter_request_from_record(payload: dict[str, object]) -> AdapterRequest:
    from enhengclaw.core.enums import ObjectType, TimeHorizon

    return AdapterRequest(
        object_id=str(payload["object_id"]),
        object_type=ObjectType(payload["object_type"]),
        subject=str(payload["subject"]),
        scope=str(payload["scope"]),
        scenario=str(payload["scenario"]),
        venue=None if payload.get("venue") is None else str(payload["venue"]),
        instrument_type=None if payload.get("instrument_type") is None else str(payload["instrument_type"]),
        time_horizon=TimeHorizon(payload.get("time_horizon", "intraday")),
    )


def adapter_batch_to_record(batch: AdapterBatch) -> dict[str, object]:
    return {
        "adapter_name": batch.adapter_name,
        "source_family": batch.source_family.value,
        "source_metadata": dict(batch.source_metadata),
        "retrieval_timestamp": batch.retrieval_timestamp.isoformat(),
        "signals": [signal_to_record(signal) for signal in batch.signals],
    }


def adapter_batch_from_record(payload: dict[str, object]) -> AdapterBatch:
    from enhengclaw.core.enums import SourceFamily

    return AdapterBatch(
        adapter_name=str(payload["adapter_name"]),
        source_family=SourceFamily(payload["source_family"]),
        source_metadata={str(key): str(value) for key, value in dict(payload.get("source_metadata", {})).items()},
        retrieval_timestamp=datetime.fromisoformat(str(payload["retrieval_timestamp"])),
        signals=[signal_from_record(dict(item)) for item in payload.get("signals", [])],
    )


def agent_ingress_result_to_record(result: AgentIngressRuntimeResult) -> dict[str, object]:
    return {
        "runtime_result": runtime_result_to_record(result.runtime_result),
        "replay_log_paths": list(result.replay_log_paths),
        "quarantine_paths": list(result.quarantine_paths),
        "accepted_signal_ids": list(result.accepted_signal_ids),
    }


def agent_ingress_result_from_record(payload: dict[str, object]) -> AgentIngressRuntimeResult:
    return AgentIngressRuntimeResult(
        runtime_result=runtime_result_from_record(dict(payload["runtime_result"])),
        replay_log_paths=[str(item) for item in payload.get("replay_log_paths", [])],
        quarantine_paths=[str(item) for item in payload.get("quarantine_paths", [])],
        accepted_signal_ids=[str(item) for item in payload.get("accepted_signal_ids", [])],
    )


def _current_worker_entrypoint() -> str | None:
    main_module = sys.modules.get("__main__")
    if main_module is None:
        return None
    spec = getattr(main_module, "__spec__", None)
    name = getattr(spec, "name", None)
    if isinstance(name, str) and name.strip():
        return name
    return None


class RuntimeOrchestrator:
    def __init__(
        self,
        *,
        store: InMemoryObjectStore | None = None,
        rule_service: RuntimeRuleService | None = None,
        resource_allocator: ResourceAllocator | None = None,
        selection_gateway: ProviderSelectionGateway | None = None,
        agent_ingress_firewall: AgentIngressFirewall | None = None,
        downstream_ingress_guard: DownstreamIngressGuard | None = None,
        execution_permit: ExecutionPermit | None = None,
        execution_profile: RuntimeExecutionProfile | None = None,
    ) -> None:
        self.state_machine = StateMachine()
        self.execution_profile = execution_profile or RuntimeExecutionProfile()
        self.publish_gate = PublishGate(attention_threshold=self.execution_profile.attention_threshold)
        self.extra_risk_penalty = self.execution_profile.extra_risk_penalty
        self.resource_allocator = resource_allocator or ResourceAllocator()
        self.rule_service = rule_service or RuntimeRuleService()
        self.store = store or FileObjectStore()
        self.downstream_ingress_guard = downstream_ingress_guard
        self.execution_permit = execution_permit
        if selection_gateway is None:
            from enhengclaw.governance.provider_selection import ProviderSelectionGateway

            self.selection_gateway = ProviderSelectionGateway()
        else:
            self.selection_gateway = selection_gateway
        if agent_ingress_firewall is None:
            from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall

            self.agent_ingress_firewall = AgentIngressFirewall()
        else:
            self.agent_ingress_firewall = agent_ingress_firewall

    @staticmethod
    def _is_worker_process() -> bool:
        return os.getenv(WORKER_MODE_ENV) == "1"

    def _bind_execution(
        self,
        execution_permit: ExecutionPermit | None,
        *,
        operation: str,
        requested_scope: str | None = None,
        required_capabilities: set[str] | None = None,
    ):
        capabilities = {CAP_RUNTIME_EXECUTE, *(required_capabilities or set())}
        return bind_execution_context(
            execution_permit or self.execution_permit,
            operation=operation,
            required_capabilities=capabilities,
            requested_scope=requested_scope,
        )

    def _assert_worker_dispatch_supported(self) -> None:
        if not isinstance(self.store, FileObjectStore):
            raise RuntimeBoundaryError(
                "controller-side runtime execution requires FileObjectStore so the worker can share persisted sessions"
            )
        if type(self) is not RuntimeOrchestrator:
            raise RuntimeBoundaryError(
                "subclassed RuntimeOrchestrator kernels are not supported across the worker boundary; "
                "move custom kernel logic into a dedicated worker implementation"
            )

    def _kernel_guard(self, *, operation: str, requested_scope: str | None = None) -> None:
        require_active_worker_lease(
            operation=operation,
            required_capabilities={CAP_RUNTIME_EXECUTE},
            requested_scope=requested_scope,
            allowed_entrypoints={RUNTIME_WORKER_ENTRYPOINT},
        )

    def _require_worker_only_api(self, api_name: str) -> None:
        if not self._is_worker_process() or _current_worker_entrypoint() != RUNTIME_WORKER_ENTRYPOINT:
            raise RuntimeBoundaryError(
                f"{api_name} is no longer callable in-process; dispatch it through the runtime worker boundary"
            )

    def _resolve_permit_path_for_worker(self, execution_permit: ExecutionPermit | None) -> tuple[str, Path | None]:
        env_path = os.getenv(EXECUTION_PERMIT_PATH_ENV)
        if env_path and env_path.strip():
            return str(Path(env_path).resolve()), None
        permit = execution_permit or self.execution_permit
        if permit is None:
            try:
                permit = resolve_execution_permit()
            except Exception as exc:
                raise RuntimeBoundaryError(
                    "runtime worker dispatch requires a permit path or a resolved execution_permit on the controller"
                ) from exc
        if permit is None:
            raise RuntimeBoundaryError(
                "runtime worker dispatch requires a permit path or a resolved execution_permit on the controller"
            )
        tempdir = Path(tempfile.mkdtemp(prefix="enhengclaw_permit_"))
        permit_path = tempdir / "execution_permit.json"
        permit_path.write_text(json.dumps(permit.to_payload(), indent=2), encoding="utf-8")
        return str(permit_path), tempdir

    def _build_run_batch_payload(
        self,
        requests: list[RuntimeRunRequest],
        *,
        business_request_id: str,
    ) -> dict[str, object]:
        normalized_business_request_id = normalize_business_request_id(business_request_id)
        request_records = [runtime_run_request_to_record(request) for request in requests]
        return {
            "business_request_id": normalized_business_request_id,
            "request_fingerprint": fingerprint_runtime_batch_requests(request_records),
            "requests": request_records,
        }

    def _load_replayable_batch_response(self, response_path: Path) -> dict[str, object]:
        if not response_path.exists() or not response_path.is_file():
            raise RuntimeBoundaryError(
                f"completed batch replay artifact is missing: {response_path}"
            )
        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuntimeBoundaryError(
                f"completed batch replay artifact is unreadable: {response_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeBoundaryError(
                f"completed batch replay artifact is invalid JSON: {response_path}"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise RuntimeBoundaryError(
                f"completed batch replay artifact has unexpected shape: {response_path}"
            )
        return payload

    def _worker_task_key(self, *, method: str, request_payload: dict[str, object]) -> str:
        if method == "run_batch":
            business_request_id = normalize_business_request_id(str(request_payload.get("business_request_id", "")))
            return f"runtime.{method}.{business_request_id}"
        object_id = request_payload.get("object_id")
        if isinstance(object_id, str) and object_id.strip():
            return f"runtime.{method}.{object_id.strip()}"
        canonical = json.dumps(request_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        return f"runtime.{method}.{digest}"

    def _dispatch_worker(self, *, method: str, request_payload: dict[str, object], execution_permit: ExecutionPermit | None):
        self._assert_worker_dispatch_supported()
        permit_path, tempdir = self._resolve_permit_path_for_worker(execution_permit)
        request_dir = tempdir if tempdir is not None else Path(tempfile.mkdtemp(prefix="enhengclaw_worker_req_"))
        cleanup_dirs: list[Path] = [request_dir]
        if tempdir is not None and tempdir not in cleanup_dirs:
            cleanup_dirs.append(tempdir)
        audit_root = default_runtime_audit_root()
        run_id = build_run_id("runtime")
        task_key = self._worker_task_key(method=method, request_payload=request_payload)
        task_lock_path = task_lock_path_for(audit_root, task_key)
        request_path = request_dir / "request.json"
        response_path = request_dir / "response.json"
        run_root = prepare_run_root(audit_root, run_id)
        initialize_audit_record(
            run_root,
            component="runtime_controller",
            run_id=run_id,
            task_key=task_key,
            controller_pid=os.getpid(),
            request_path=run_root / "request.json",
            request_kind="runtime",
            request_schema_version=WORKER_REQUEST_SCHEMA_VERSION,
        )
        business_request_id: str | None = None
        request_fingerprint: str | None = None
        existing_intent: dict[str, object] = {}
        if method == "run_batch":
            business_request_id = normalize_business_request_id(str(request_payload.get("business_request_id", "")))
            request_fingerprint = str(request_payload.get("request_fingerprint", "")).strip()
            if not request_fingerprint:
                request_fingerprint = fingerprint_runtime_batch_requests(
                    [dict(item) for item in request_payload.get("requests", [])]
                )
                request_payload["request_fingerprint"] = request_fingerprint
            update_audit_record(
                run_root,
                business_request_id=business_request_id,
                request_fingerprint=request_fingerprint,
            )
        cleanup_records = cleanup_orphan_execution_leases()
        if cleanup_records:
            update_audit_record(run_root, cleanup=cleanup_records)
            for record in cleanup_records:
                append_audit_event(
                    run_root,
                    "lease.cleanup",
                    component="runtime_controller",
                    lease_id=record["lease_id"],
                    cleanup_reason=record["cleanup_reason"],
                    cleaned_status=record["status"],
                    worker_pid_state=record.get("worker_pid_state"),
                    heartbeat_age_seconds=record.get("heartbeat_age_seconds"),
                )
        envelope = build_worker_request_envelope(
            request_kind="runtime",
            run_id=run_id,
            task_key=task_key,
            audit_root=audit_root,
            task_lock_path=task_lock_path,
            payload=request_payload,
        )
        request_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        copy_request_artifact(request_path, run_root)
        update_audit_record(run_root, request_path=str(request_path.resolve()))
        if business_request_id is not None and request_fingerprint is not None:
            existing_intent = read_business_intent_record(audit_root, business_request_id)
            existing_fingerprint = str(existing_intent.get("request_fingerprint") or "").strip()
            if existing_fingerprint and existing_fingerprint != request_fingerprint:
                detail = (
                    f"business_request_id '{business_request_id}' was previously recorded with a different batch payload"
                )
                append_audit_event(
                    run_root,
                    "controller.batch_intent_conflict",
                    component="runtime_controller",
                    business_request_id=business_request_id,
                    request_fingerprint=request_fingerprint,
                    existing_request_fingerprint=existing_fingerprint,
                )
                update_audit_record(
                    run_root,
                    status="failed",
                    exit_code=1,
                    failure_category="business_request_conflict",
                    interruption_reason=detail,
                )
                raise RuntimeBoundaryError(detail)
            if str(existing_intent.get("status") or "").strip() == "completed":
                replay_path = Path(str(existing_intent.get("response_path") or "").strip())
                try:
                    payload = self._load_replayable_batch_response(replay_path)
                except RuntimeBoundaryError as exc:
                    append_audit_event(
                        run_root,
                        "controller.batch_intent_replay_inconsistent",
                        component="runtime_controller",
                        business_request_id=business_request_id,
                        response_path=str(replay_path),
                    )
                    update_audit_record(
                        run_root,
                        status="failed",
                        exit_code=1,
                        failure_category="business_request_consistency_error",
                        interruption_reason=str(exc),
                        response_path=str(replay_path),
                    )
                    raise
                append_audit_event(
                    run_root,
                    "controller.batch_intent_replay",
                    component="runtime_controller",
                    business_request_id=business_request_id,
                    request_fingerprint=request_fingerprint,
                    replayed_from_run_id=existing_intent.get("completed_run_id"),
                    response_path=str(replay_path),
                )
                update_audit_record(
                    run_root,
                    status="completed",
                    exit_code=0,
                    failure_category=None,
                    interruption_reason=None,
                    response_path=str(replay_path),
                    replayed_from_run_id=existing_intent.get("completed_run_id"),
                )
                return payload
        try:
            task_lock_path, reclaimed_lock = acquire_task_lock(
                audit_root=audit_root,
                task_key=task_key,
                run_id=run_id,
                controller_pid=os.getpid(),
            )
        except WorkerTaskActiveError as exc:
            append_audit_event(
                run_root,
                "controller.task_rejected_duplicate",
                component="runtime_controller",
                task_key=task_key,
                business_request_id=business_request_id,
            )
            update_audit_record(
                run_root,
                status="failed",
                exit_code=1,
                failure_category="duplicate_task_active",
                interruption_reason=str(exc),
            )
            raise RuntimeBoundaryError(str(exc)) from exc
        if business_request_id is not None and request_fingerprint is not None:
            previous_status = str(existing_intent.get("status") or "").strip()
            timestamp = utc_timestamp()
            update_business_intent_record(
                audit_root,
                business_request_id,
                defaults={
                    "business_request_id": business_request_id,
                    "request_fingerprint": request_fingerprint,
                    "task_key": task_key,
                    "status": "created",
                    "created_at_utc": timestamp,
                    "updated_at_utc": timestamp,
                    "latest_run_id": run_id,
                    "completed_run_id": None,
                    "response_path": None,
                    "failure_category": None,
                },
                request_fingerprint=request_fingerprint,
                task_key=task_key,
                status="active",
                latest_run_id=run_id,
                updated_at_utc=timestamp,
                failure_category=None,
            )
            if previous_status in {"failed", "interrupted"}:
                append_audit_event(
                    run_root,
                    "controller.batch_intent_retry",
                    component="runtime_controller",
                    business_request_id=business_request_id,
                    previous_status=previous_status,
                    previous_run_id=existing_intent.get("latest_run_id"),
                )
        if reclaimed_lock is not None:
            append_audit_event(
                run_root,
                "task_lock.reclaimed",
                component="runtime_controller",
                previous_run_id=reclaimed_lock.get("run_id"),
                previous_status=reclaimed_lock.get("status"),
                reclaim_reason=reclaimed_lock.get("reclaim_reason"),
                worker_pid_state=reclaimed_lock.get("worker_pid_state"),
                controller_pid_state=reclaimed_lock.get("controller_pid_state"),
                lock_updated_at_utc=reclaimed_lock.get("lock_updated_at_utc"),
            )
        env = os.environ.copy()
        pythonpath_parts = [str(Path(__file__).resolve().parents[2])]
        if env.get("PYTHONPATH"):
            pythonpath_parts.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        try:
            update_audit_record(run_root, status="controller_dispatch")
            append_audit_event(
                run_root,
                "controller.worker_dispatch",
                component="runtime_controller",
                method=method,
                worker_module="enhengclaw.orchestration.runtime_worker",
            )
            completed = None
            for attempt in range(1, 3):
                try:
                    completed = audited_subprocess_run(
                        [
                            sys.executable,
                            "-m",
                            "enhengclaw.orchestration.runtime_worker",
                            "--method",
                            method,
                            "--permit",
                            permit_path,
                            "--request",
                            str(request_path),
                            "--response",
                            str(response_path),
                        ],
                        env=env,
                        run_root=run_root,
                    )
                    break
                except OSError as exc:
                    append_audit_event(
                        run_root,
                        "controller.worker_spawn_failed",
                        component="runtime_controller",
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt == 1:
                        append_audit_event(
                            run_root,
                            "controller.worker_spawn_retry",
                            component="runtime_controller",
                            retry_attempt=2,
                        )
                        continue
                    update_audit_record(
                        run_root,
                        status="failed",
                        exit_code=1,
                        failure_category="worker_spawn_error",
                        interruption_reason=str(exc),
                    )
                    if business_request_id is not None:
                        timestamp = utc_timestamp()
                        update_business_intent_record(
                            audit_root,
                            business_request_id,
                            request_fingerprint=request_fingerprint,
                            task_key=task_key,
                            status="failed",
                            latest_run_id=run_id,
                            updated_at_utc=timestamp,
                            failure_category="worker_spawn_error",
                        )
                    release_task_lock(
                        task_lock_path,
                        status="failed",
                        failure_category="worker_spawn_error",
                        extra_fields={"worker_pid": None, "lease_id": None},
                    )
                    raise RuntimeBoundaryError(f"runtime worker '{method}' failed to spawn: {exc}") from exc
            if completed is None:
                raise RuntimeBoundaryError(f"runtime worker '{method}' failed to obtain a worker process")
            update_audit_record(
                run_root,
                worker_pid=completed.worker_pid,
                exit_code=completed.returncode,
                stdout=completed.stdout.to_payload(),
                stderr=completed.stderr.to_payload(),
            )
            append_audit_event(
                run_root,
                "controller.worker_exit",
                component="runtime_controller",
                method=method,
                worker_pid=completed.worker_pid,
                returncode=completed.returncode,
                stdout=completed.stdout.to_payload(),
                stderr=completed.stderr.to_payload(),
            )
            audit_record = read_audit_record(run_root)
            if completed.returncode != 0:
                detail = (
                    str(audit_record.get("interruption_reason") or "").strip()
                    or (
                        completed.stderr.to_payload().get("byte_count")
                        and (run_root / "worker.stderr.log").read_text(encoding="utf-8", errors="replace").strip()
                    )
                    or (run_root / "worker.stdout.log").read_text(encoding="utf-8", errors="replace").strip()
                    or f"exit code {completed.returncode}"
                )
                failure_category = str(audit_record.get("failure_category") or "worker_exit_nonzero")
                update_audit_record(
                    run_root,
                    status="failed",
                    failure_category=failure_category,
                )
                if business_request_id is not None:
                    intent_status = str(audit_record.get("status") or "").strip()
                    if intent_status not in {"failed", "interrupted"}:
                        intent_status = "failed"
                    timestamp = utc_timestamp()
                    update_business_intent_record(
                        audit_root,
                        business_request_id,
                        request_fingerprint=request_fingerprint,
                        task_key=task_key,
                        status=intent_status,
                        latest_run_id=run_id,
                        updated_at_utc=timestamp,
                        failure_category=failure_category,
                    )
                release_task_lock(
                    task_lock_path,
                    status="failed",
                    failure_category=failure_category,
                    extra_fields={"worker_pid": completed.worker_pid, "lease_id": audit_record.get("lease_id")},
                )
                raise RuntimeBoundaryError(f"runtime worker '{method}' failed: {detail}")
            stable_response_path = run_root / "response.json"
            stable_response_path.write_text(response_path.read_text(encoding="utf-8"), encoding="utf-8")
            payload = json.loads(stable_response_path.read_text(encoding="utf-8"))
            if business_request_id is not None:
                timestamp = utc_timestamp()
                update_business_intent_record(
                    audit_root,
                    business_request_id,
                    request_fingerprint=request_fingerprint,
                    task_key=task_key,
                    status="completed",
                    latest_run_id=run_id,
                    completed_run_id=run_id,
                    response_path=str(stable_response_path),
                    updated_at_utc=timestamp,
                    failure_category=None,
                )
                append_audit_event(
                    run_root,
                    "controller.batch_intent_completed",
                    component="runtime_controller",
                    business_request_id=business_request_id,
                    request_fingerprint=request_fingerprint,
                    response_path=str(stable_response_path),
                )
            release_task_lock(
                task_lock_path,
                status="completed",
                failure_category=None,
                extra_fields={"worker_pid": completed.worker_pid, "lease_id": audit_record.get("lease_id")},
            )
            update_audit_record(run_root, response_path=str(stable_response_path))
            return payload
        finally:
            for directory in cleanup_dirs:
                if directory.exists():
                    shutil.rmtree(directory, ignore_errors=True)

    def run(
        self,
        object_id: str,
        object_type: ObjectType,
        scope: str,
        signals: list[Signal],
        *,
        execution_permit: ExecutionPermit | None = None,
        execution_profile: RuntimeExecutionProfile | None = None,
    ) -> RuntimeResult:
        with self._bind_execution(
            execution_permit,
            operation="runtime.run",
            requested_scope=scope,
        ):
            return self.run_new(
                object_id=object_id,
                object_type=object_type,
                scope=scope,
                signals=signals,
                execution_profile=execution_profile,
            )

    def collect_adapter_batches(
        self,
        *,
        object_id: str,
        object_type: ObjectType,
        subject: str,
        scope: str,
        scenario: str,
        adapters: list[SignalAdapter],
        execution_permit: ExecutionPermit | None = None,
    ) -> tuple[AdapterRequest, list[AdapterBatch], list[Signal]]:
        # Retired controller surface: canonical source-backed callers must use ProviderSnapshotRunner.
        self._require_worker_only_api("collect_adapter_batches")
        with self._bind_execution(
            execution_permit,
            operation="runtime.collect_adapter_batches",
            requested_scope=scope,
            required_capabilities={CAP_PROVIDER_FETCH},
        ):
            request = AdapterRequest(
                object_id=object_id,
                object_type=object_type,
                subject=subject,
                scope=scope,
                scenario=scenario,
            )
            batches = collect_and_validate_batches(adapters, request)
            signals = merge_adapter_batches(batches)
            return request, batches, signals

    def run_new_from_adapters(
        self,
        *,
        object_id: str,
        object_type: ObjectType,
        subject: str,
        scope: str,
        scenario: str,
        adapters: list[SignalAdapter],
        execution_permit: ExecutionPermit | None = None,
    ) -> AdapterRuntimeResult:
        # Retired controller surface: canonical source-backed callers must use ProviderSnapshotRunner.
        self._require_worker_only_api("run_new_from_adapters")
        with self._bind_execution(
            execution_permit,
            operation="runtime.run_new_from_adapters",
            requested_scope=scope,
            required_capabilities={CAP_PROVIDER_FETCH},
        ):
            request, batches, signals = self.collect_adapter_batches(
                object_id=object_id,
                object_type=object_type,
                subject=subject,
                scope=scope,
                scenario=scenario,
                adapters=adapters,
            )
            self._guard_downstream_subject_keys(
                subject_keys=self._subject_keys_from_batches(batches),
                consumer="runtime.adapters.create",
            )
            result = self.run_new(
                object_id=object_id,
                object_type=object_type,
                scope=scope,
                signals=signals,
            )
            return AdapterRuntimeResult(
                adapter_request=request,
                adapter_batches=batches,
                runtime_result=result,
                selection_result=None,
            )

    def continue_existing_from_adapters(
        self,
        *,
        object_id: str,
        subject: str,
        scenario: str,
        adapters: list[SignalAdapter],
        execution_permit: ExecutionPermit | None = None,
    ) -> AdapterRuntimeResult:
        self._require_worker_only_api("continue_existing_from_adapters")
        with self._bind_execution(
            execution_permit,
            operation="runtime.continue_existing_from_adapters",
            required_capabilities={CAP_PROVIDER_FETCH},
        ):
            session = self.store.load(object_id)
            require_execution_context(
                operation="runtime.continue_existing_from_adapters.scope_check",
                required_capabilities={CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH},
                requested_scope=session.research_object.scope,
            )
            request, batches, signals = self.collect_adapter_batches(
                object_id=object_id,
                object_type=session.research_object.object_type,
                subject=subject,
                scope=session.research_object.scope,
                scenario=scenario,
                adapters=adapters,
            )
            self._guard_downstream_subject_keys(
                subject_keys=self._subject_keys_from_batches(batches),
                consumer="runtime.adapters.continue",
            )
            result = self.continue_existing(
                object_id=object_id,
                signals=signals,
            )
            return AdapterRuntimeResult(
                adapter_request=request,
                adapter_batches=batches,
                runtime_result=result,
                selection_result=None,
            )

    def collect_provider_batches(
        self,
        *,
        object_id: str,
        object_type: ObjectType,
        subject: str,
        scope: str,
        scenario: str,
        portfolio_report: ProviderPortfolioReport,
        provider_bindings: list[ProviderRuntimeBinding],
        selection_mode: str = "default",
        manual_allowlist: list[str] | None = None,
        execution_permit: ExecutionPermit | None = None,
    ) -> tuple[AdapterRequest, list[AdapterBatch], list[Signal], ProviderSelectionResult]:
        # Retired controller surface: canonical source-backed callers must use ProviderSnapshotRunner.
        self._require_worker_only_api("collect_provider_batches")
        with self._bind_execution(
            execution_permit,
            operation="runtime.collect_provider_batches",
            requested_scope=scope,
            required_capabilities={CAP_PROVIDER_FETCH},
        ):
            selection = self.selection_gateway.select(
                portfolio_report=portfolio_report,
                bindings=provider_bindings,
                mode=selection_mode,
                manual_allowlist=manual_allowlist,
            )
            if not selection.allowed_bindings:
                from enhengclaw.governance.provider_selection import ProviderSelectionError

                raise ProviderSelectionError(
                    "provider selection rejected all candidate providers",
                    selection,
                )
            request = AdapterRequest(
                object_id=object_id,
                object_type=object_type,
                subject=subject,
                scope=scope,
                scenario=scenario,
            )
            adapters = [binding.adapter for binding in selection.allowed_bindings]
            batches = collect_and_validate_batches(adapters, request)
            signals = merge_adapter_batches(batches)
            return request, batches, signals, selection

    def run_new_from_provider_bindings(
        self,
        *,
        object_id: str,
        object_type: ObjectType,
        subject: str,
        scope: str,
        scenario: str,
        portfolio_report: ProviderPortfolioReport,
        provider_bindings: list[ProviderRuntimeBinding],
        selection_mode: str = "default",
        manual_allowlist: list[str] | None = None,
        execution_permit: ExecutionPermit | None = None,
    ) -> ProviderAdapterRuntimeResult:
        # Retired controller surface: canonical source-backed callers must use ProviderSnapshotRunner.
        self._require_worker_only_api("run_new_from_provider_bindings")
        with self._bind_execution(
            execution_permit,
            operation="runtime.run_new_from_provider_bindings",
            requested_scope=scope,
            required_capabilities={CAP_PROVIDER_FETCH},
        ):
            request, batches, signals, selection = self.collect_provider_batches(
                object_id=object_id,
                object_type=object_type,
                subject=subject,
                scope=scope,
                scenario=scenario,
                portfolio_report=portfolio_report,
                provider_bindings=provider_bindings,
                selection_mode=selection_mode,
                manual_allowlist=manual_allowlist,
            )
            self._guard_downstream_subject_keys(
                subject_keys=self._subject_keys_from_batches(batches),
                consumer="runtime.providers.create",
            )
            result = self.run_new(
                object_id=object_id,
                object_type=object_type,
                scope=scope,
                signals=signals,
            )
            return ProviderAdapterRuntimeResult(
                adapter_request=request,
                adapter_batches=batches,
                runtime_result=result,
                selection_result=selection,
            )

    def continue_existing_from_provider_bindings(
        self,
        *,
        object_id: str,
        subject: str,
        scenario: str,
        portfolio_report: ProviderPortfolioReport,
        provider_bindings: list[ProviderRuntimeBinding],
        selection_mode: str = "default",
        manual_allowlist: list[str] | None = None,
        execution_permit: ExecutionPermit | None = None,
    ) -> ProviderAdapterRuntimeResult:
        # Retired controller surface: canonical source-backed callers must use ProviderSnapshotRunner.
        self._require_worker_only_api("continue_existing_from_provider_bindings")
        with self._bind_execution(
            execution_permit,
            operation="runtime.continue_existing_from_provider_bindings",
            required_capabilities={CAP_PROVIDER_FETCH},
        ):
            session = self.store.load(object_id)
            require_execution_context(
                operation="runtime.continue_existing_from_provider_bindings.scope_check",
                required_capabilities={CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH},
                requested_scope=session.research_object.scope,
            )
            request, batches, signals, selection = self.collect_provider_batches(
                object_id=object_id,
                object_type=session.research_object.object_type,
                subject=subject,
                scope=session.research_object.scope,
                scenario=scenario,
                portfolio_report=portfolio_report,
                provider_bindings=provider_bindings,
                selection_mode=selection_mode,
                manual_allowlist=manual_allowlist,
            )
            self._guard_downstream_subject_keys(
                subject_keys=self._subject_keys_from_batches(batches),
                consumer="runtime.providers.continue",
            )
            result = self.continue_existing(
                object_id=object_id,
                signals=signals,
            )
            return ProviderAdapterRuntimeResult(
                adapter_request=request,
                adapter_batches=batches,
                runtime_result=result,
                selection_result=selection,
            )

    def run_new_from_agent_payloads(
        self,
        *,
        object_id: str,
        object_type: ObjectType,
        subject: str,
        scope: str,
        payloads: list[dict[str, object]],
        scenario: str = "agent_ingress",
        execution_permit: ExecutionPermit | None = None,
    ) -> AgentIngressRuntimeResult:
        with self._bind_execution(
            execution_permit,
            operation="runtime.run_new_from_agent_payloads",
            requested_scope=scope,
        ):
            from enhengclaw.ingress.schema_validator import AgentIngressContext

            context = AgentIngressContext(
                object_id=object_id,
                object_type=object_type,
                subject=subject,
                scope=scope,
                scenario=scenario,
            )
            ingress = self.agent_ingress_firewall.intake(
                context=context,
                payloads=payloads,
            )
            self._guard_downstream_subject_keys(
                subject_keys=[context.subject_key],
                consumer="runtime.agent_ingress.create",
            )
            result = self.run_new(
                object_id=object_id,
                object_type=object_type,
                scope=scope,
                signals=ingress.signals,
            )
            return AgentIngressRuntimeResult(
                runtime_result=result,
                replay_log_paths=[record.path for record in ingress.replay_records],
                quarantine_paths=[record.path for record in ingress.quarantine_records],
                accepted_signal_ids=[signal.signal_id for signal in ingress.signals],
            )

    def continue_existing_from_agent_payloads(
        self,
        *,
        object_id: str,
        subject: str,
        payloads: list[dict[str, object]],
        scenario: str = "agent_ingress",
        execution_permit: ExecutionPermit | None = None,
    ) -> AgentIngressRuntimeResult:
        with self._bind_execution(
            execution_permit,
            operation="runtime.continue_existing_from_agent_payloads",
        ):
            from enhengclaw.ingress.schema_validator import AgentIngressContext

            session = self.store.load(object_id)
            require_execution_context(
                operation="runtime.continue_existing_from_agent_payloads.scope_check",
                required_capabilities={CAP_RUNTIME_EXECUTE},
                requested_scope=session.research_object.scope,
            )
            context = AgentIngressContext(
                object_id=object_id,
                object_type=session.research_object.object_type,
                subject=subject,
                scope=session.research_object.scope,
                scenario=scenario,
            )
            ingress = self.agent_ingress_firewall.intake(
                context=context,
                payloads=payloads,
            )
            self._guard_downstream_subject_keys(
                subject_keys=[context.subject_key],
                consumer="runtime.agent_ingress.continue",
            )
            result = self.continue_existing(
                object_id=object_id,
                signals=ingress.signals,
            )
            return AgentIngressRuntimeResult(
                runtime_result=result,
                replay_log_paths=[record.path for record in ingress.replay_records],
                quarantine_paths=[record.path for record in ingress.quarantine_records],
                accepted_signal_ids=[signal.signal_id for signal in ingress.signals],
            )
    def run_new(
        self,
        object_id: str,
        object_type: ObjectType,
        scope: str,
        signals: list[Signal],
        *,
        execution_permit: ExecutionPermit | None = None,
        execution_profile: RuntimeExecutionProfile | None = None,
    ) -> RuntimeResult:
        with self._bind_execution(
            execution_permit,
            operation="runtime.run_new",
            requested_scope=scope,
        ):
            if not self._is_worker_process():
                payload = self._dispatch_worker(
                    method="run_new",
                    request_payload=runtime_run_request_to_record(
                        RuntimeRunRequest(
                            mode="create",
                            object_id=object_id,
                            object_type=object_type,
                            scope=scope,
                            signals=signals,
                            execution_profile=execution_profile,
                        )
                    ),
                    execution_permit=execution_permit,
                )
                return runtime_result_from_record(dict(payload))
            if execution_profile is not None:
                runtime = RuntimeOrchestrator(
                    store=self.store,
                    rule_service=self.rule_service,
                    resource_allocator=self.resource_allocator,
                    selection_gateway=self.selection_gateway,
                    agent_ingress_firewall=self.agent_ingress_firewall,
                    downstream_ingress_guard=self.downstream_ingress_guard,
                    execution_permit=execution_permit or self.execution_permit,
                    execution_profile=execution_profile,
                )
                return runtime._run_new_impl(
                    object_id=object_id,
                    object_type=object_type,
                    scope=scope,
                    signals=signals,
                )
            return self._run_new_impl(
                object_id=object_id,
                object_type=object_type,
                scope=scope,
                signals=signals,
            )

    def _run_new_impl(self, object_id: str, object_type: ObjectType, scope: str, signals: list[Signal]) -> RuntimeResult:
        self._require_worker_only_api("_run_new_impl")
        self._kernel_guard(operation="runtime.kernel.run_new", requested_scope=scope)
        if not signals:
            raise ValueError("RuntimeOrchestrator requires at least one signal")

        research_object = ResearchObject(
            object_id=object_id,
            object_type=object_type,
            scope=scope,
            time_horizon=signals[0].time_horizon,
        )
        claims: list[Claim] = []
        conflict_groups: list[ConflictGroup] = []
        theses: list[Thesis] = []
        steps: list[RuntimeStepLog] = []

        self.state_machine.begin_cycle(research_object)
        steps.append(
            self._ok_step(
                research_object,
                "signal_intake",
                details={"mode": "create", "signal_count": len(signals), "signal_ids": [signal.signal_id for signal in signals]},
            )
        )

        claims = self.create_initial_claims(research_object, signals)
        research_object.claim_ids = [claim.claim_id for claim in claims]
        steps.append(
            self._ok_step(
                research_object,
                "claim_creation",
                details={"claim_count": len(claims), "claim_ids": research_object.claim_ids},
            )
        )

        conflict_groups = self.group_claim_conflicts(research_object, claims)
        research_object.risk_state = self.rule_service.derive_risk_state(claims)
        research_object.attention_score = self.calculate_attention(research_object, claims, conflict_groups)
        steps.append(
            self._ok_step(
                research_object,
                "candidate_assessment",
                details={
                    "group_count": len(conflict_groups),
                    "max_conflict": self._max_conflict(conflict_groups).value,
                    "risk_state": research_object.risk_state.value,
                    "attention_score": research_object.attention_score,
                },
            )
        )

        self._transition_with_log(
            research_object,
            self.rule_service.candidate_exit_target(claims),
            "candidate_exit",
            steps,
        )

        if research_object.processing_state == ProcessingState.ARCHIVED:
            return self._finalize(
                research_object,
                claims,
                conflict_groups,
                theses,
                PublishDecision(PublishDecisionType.ARCHIVED, ["candidate rejected"]),
                steps,
            )

        self.state_machine.begin_cycle(research_object)
        screened_target = self.rule_service.screened_exit_target(research_object, claims, conflict_groups)
        self._transition_with_log(
            research_object,
            screened_target,
            "screening_decision",
            steps,
            extra_details={
                "attention_score": research_object.attention_score,
                "max_conflict": self._max_conflict(conflict_groups).value,
            },
        )

        if research_object.processing_state != ProcessingState.ACTIVE_RESEARCH:
            steps.append(self._rejected_step(research_object, "publish_gate", {"reason": "processing_state is not publish_ready"}))
            return self._finalize(
                research_object,
                claims,
                conflict_groups,
                theses,
                self._decision_without_publish_gate(research_object),
                steps,
            )

        return self._process_from_active_research(research_object, claims, conflict_groups, theses, steps)

    def continue_existing(
        self,
        object_id: str,
        signals: list[Signal],
        *,
        execution_permit: ExecutionPermit | None = None,
        execution_profile: RuntimeExecutionProfile | None = None,
    ) -> RuntimeResult:
        with self._bind_execution(
            execution_permit,
            operation="runtime.continue_existing",
        ):
            if not self._is_worker_process():
                payload = self._dispatch_worker(
                    method="continue_existing",
                    request_payload=runtime_run_request_to_record(
                        RuntimeRunRequest(
                            mode="continue",
                            object_id=object_id,
                            signals=signals,
                            execution_profile=execution_profile,
                        )
                    ),
                    execution_permit=execution_permit,
                )
                return runtime_result_from_record(dict(payload))
            if execution_profile is not None:
                runtime = RuntimeOrchestrator(
                    store=self.store,
                    rule_service=self.rule_service,
                    resource_allocator=self.resource_allocator,
                    selection_gateway=self.selection_gateway,
                    agent_ingress_firewall=self.agent_ingress_firewall,
                    downstream_ingress_guard=self.downstream_ingress_guard,
                    execution_permit=execution_permit or self.execution_permit,
                    execution_profile=execution_profile,
                )
                return runtime._continue_existing_impl(
                    object_id=object_id,
                    signals=signals,
                )
            return self._continue_existing_impl(
                object_id=object_id,
                signals=signals,
            )

    def _continue_existing_impl(
        self,
        object_id: str,
        signals: list[Signal],
        *,
        session: RuntimeSession | None = None,
    ) -> RuntimeResult:
        self._require_worker_only_api("_continue_existing_impl")
        if not signals:
            raise ValueError("continue_existing requires at least one signal")

        session = self.store.load(object_id) if session is None else session
        self._kernel_guard(
            operation="runtime.kernel.continue_existing",
            requested_scope=session.research_object.scope,
        )
        research_object = session.research_object
        claims = session.claims
        conflict_groups = session.conflict_groups
        theses = session.theses
        steps: list[RuntimeStepLog] = []

        steps.append(
            self._ok_step(
                research_object,
                "session_load",
                details={
                    "mode": "continue",
                    "existing_processing_state": research_object.processing_state.value,
                    "existing_risk_state": research_object.risk_state.value,
                    "existing_claim_count": len(claims),
                },
            )
        )

        if research_object.processing_state == ProcessingState.BLOCKED:
            steps.append(self._rejected_step(research_object, "session_resume", {"reason": "blocked objects require forced review, not normal resume"}))
            return self._finalize(
                research_object,
                claims,
                conflict_groups,
                theses,
                PublishDecision(PublishDecisionType.BLOCKED, ["object is blocked before normal resume"]),
                steps,
            )

        if research_object.processing_state not in {ProcessingState.MONITORING, ProcessingState.ARCHIVED, ProcessingState.PUBLISHED}:
            raise RuntimeBoundaryError(
                f"continue_existing cannot resume from {research_object.processing_state.value}; allowed states: monitoring, archived, published"
            )

        if research_object.processing_state == ProcessingState.PUBLISHED:
            self.state_machine.begin_cycle(research_object)
            self._transition_with_log(research_object, ProcessingState.MONITORING, "published_resume_transition", steps)

        self.state_machine.begin_cycle(research_object)
        steps.append(
            self._ok_step(
                research_object,
                "signal_intake",
                details={"mode": "continue", "signal_count": len(signals), "signal_ids": [signal.signal_id for signal in signals]},
            )
        )

        new_claims = self.ingest_new_claims(research_object, claims, signals)
        claims.extend(new_claims)
        research_object.claim_ids = [claim.claim_id for claim in claims]
        steps.append(
            self._ok_step(
                research_object,
                "claim_creation",
                details={"new_claim_count": len(new_claims), "total_claim_count": len(claims)},
            )
        )

        conflict_groups = self.group_claim_conflicts(research_object, claims)
        research_object.risk_state = self.rule_service.derive_risk_state(claims)
        research_object.attention_score = self.calculate_attention(research_object, claims, conflict_groups)
        steps.append(
            self._ok_step(
                research_object,
                "resume_reassessment",
                details={
                    "group_count": len(conflict_groups),
                    "max_conflict": self._max_conflict(conflict_groups).value,
                    "risk_state": research_object.risk_state.value,
                    "attention_score": research_object.attention_score,
                },
            )
        )

        if research_object.processing_state == ProcessingState.ARCHIVED:
            if not self.rule_service.archived_can_reactivate(new_claims):
                steps.append(self._rejected_step(research_object, "archived_reactivation", {"reason": "new signals do not meet archived reactivation threshold"}))
                return self._finalize(
                    research_object,
                    claims,
                    conflict_groups,
                    theses,
                    PublishDecision(PublishDecisionType.ARCHIVED, ["archived object did not meet reactivation threshold"]),
                    steps,
                )
            self._transition_with_log(research_object, ProcessingState.ACTIVE_RESEARCH, "archived_reactivation", steps)
        elif research_object.processing_state == ProcessingState.MONITORING:
            resume_target = self.rule_service.monitoring_resume_target(research_object, claims, conflict_groups)
            if resume_target != ProcessingState.MONITORING:
                self._transition_with_log(research_object, resume_target, "monitoring_resume_decision", steps)
            else:
                steps.append(
                    self._ok_step(
                        research_object,
                        "monitoring_resume_decision",
                        details={"target": ProcessingState.MONITORING.value},
                    )
                )

        if research_object.processing_state != ProcessingState.ACTIVE_RESEARCH:
            steps.append(self._rejected_step(research_object, "publish_gate", {"reason": "processing_state is not publish_ready"}))
            return self._finalize(
                research_object,
                claims,
                conflict_groups,
                theses,
                self._decision_without_publish_gate(research_object),
                steps,
            )

        return self._process_from_active_research(research_object, claims, conflict_groups, theses, steps)

    def run_batch(
        self,
        requests: list[RuntimeRunRequest],
        *,
        business_request_id: str,
        execution_permit: ExecutionPermit | None = None,
    ) -> list[RuntimeResult]:
        normalized_business_request_id = normalize_business_request_id(business_request_id)
        with self._bind_execution(
            execution_permit,
            operation="runtime.run_batch",
        ):
            if not self._is_worker_process():
                payload = self._dispatch_worker(
                    method="run_batch",
                    request_payload=self._build_run_batch_payload(
                        requests,
                        business_request_id=normalized_business_request_id,
                    ),
                    execution_permit=execution_permit,
                )
                return [runtime_result_from_record(dict(item)) for item in payload.get("results", [])]
            results: list[RuntimeResult] = []
            for request in requests:
                if request.mode == "create":
                    if request.object_type is None or request.scope is None:
                        raise ValueError("create batch requests require object_type and scope")
                    result = self.run_new(
                        object_id=request.object_id,
                        object_type=request.object_type,
                        scope=request.scope,
                        signals=request.signals,
                        execution_profile=request.execution_profile,
                    )
                elif request.mode == "continue":
                    result = self.continue_existing(
                        object_id=request.object_id,
                        signals=request.signals,
                        execution_profile=request.execution_profile,
                    )
                else:
                    raise ValueError(f"Unsupported batch request mode: {request.mode}")
                results.append(result)

            allocation_map = self._reallocate_store_sessions()
            for result in results:
                result.resource_allocation = allocation_map.get(result.research_object.object_id)
            return results

    def create_initial_claims(self, research_object: ResearchObject, signals: list[Signal]) -> list[Claim]:
        self._require_state("claim_creation", research_object, {ProcessingState.CANDIDATE})
        return [claim_from_signal(signal, research_object.object_id, f"c{idx}") for idx, signal in enumerate(signals, start=1)]

    def ingest_new_claims(
        self,
        research_object: ResearchObject,
        existing_claims: list[Claim],
        signals: list[Signal],
    ) -> list[Claim]:
        self._require_state(
            "claim_creation",
            research_object,
            {ProcessingState.MONITORING, ProcessingState.ARCHIVED},
        )
        start_index = len(existing_claims) + 1
        return [
            claim_from_signal(signal, research_object.object_id, f"c{start_index + idx}")
            for idx, signal in enumerate(signals)
        ]

    def group_claim_conflicts(self, research_object: ResearchObject, claims: list[Claim]) -> list[ConflictGroup]:
        self._require_state(
            "claim_conflict_grouping",
            research_object,
            {ProcessingState.CANDIDATE, ProcessingState.MONITORING, ProcessingState.ARCHIVED, ProcessingState.ACTIVE_RESEARCH},
        )
        return group_claim_conflicts(claims)

    def calculate_attention(
        self,
        research_object: ResearchObject,
        claims: list[Claim],
        conflict_groups: list[ConflictGroup],
    ) -> int:
        self._require_state(
            "attention_calculation",
            research_object,
            {ProcessingState.CANDIDATE, ProcessingState.MONITORING, ProcessingState.ARCHIVED, ProcessingState.ACTIVE_RESEARCH},
        )
        score = calculate_attention_score(
            research_object.object_type,
            claims,
            conflict_groups,
            research_object.risk_state,
        )
        if self.extra_risk_penalty > 0 and research_object.risk_state in {
            RiskState.CAUTION,
            RiskState.RESTRICTED,
            RiskState.BLOCKED,
        }:
            score = max(0, score - self.extra_risk_penalty)
        return score

    def advance_claims(self, research_object: ResearchObject, claims: list[Claim]) -> None:
        self._require_state("claim_status_refresh", research_object, {ProcessingState.ACTIVE_RESEARCH})
        for claim in claims:
            claim.advance_basic_status()

    def build_theses(self, research_object: ResearchObject, claims: list[Claim], conflict_groups: list[ConflictGroup]) -> list[Thesis]:
        self._require_state(
            "thesis_building",
            research_object,
            {ProcessingState.ACTIVE_RESEARCH, ProcessingState.EVIDENCE_COMPLETE},
        )
        from enhengclaw.core.thesis import build_theses_for_object

        return build_theses_for_object(research_object, claims, conflict_groups)

    def select_working_theses(
        self,
        research_object: ResearchObject,
        theses: list[Thesis],
        claim_index: dict[str, Claim],
    ) -> tuple[Thesis | None, Thesis | None]:
        self._require_state(
            "thesis_selection",
            research_object,
            {ProcessingState.ACTIVE_RESEARCH, ProcessingState.EVIDENCE_COMPLETE},
        )
        return select_working_theses(research_object, theses, claim_index)

    def evaluate_thesis_conflicts(
        self,
        research_object: ResearchObject,
        working_primary: Thesis | None,
        working_opposing: Thesis | None,
        claim_index: dict[str, Claim],
    ) -> None:
        self._require_state(
            "thesis_conflict_evaluation",
            research_object,
            {ProcessingState.ACTIVE_RESEARCH, ProcessingState.EVIDENCE_COMPLETE},
        )
        if working_primary is None:
            return
        severity = evaluate_thesis_conflict(working_primary, working_opposing, claim_index, research_object.risk_state)
        working_primary.conflict_severity = severity
        if working_opposing is not None:
            working_opposing.conflict_severity = severity
        if severity.rank >= ConflictSeverity.MEDIUM.rank and working_primary.thesis_type == ThesisType.PREDICTIVE:
            working_primary.status = ThesisStatus.CHALLENGED

    def promote_publishable_claims(
        self,
        research_object: ResearchObject,
        working_primary: Thesis | None,
        claim_index: dict[str, Claim],
    ) -> None:
        self._require_state("claim_promotion", research_object, {ProcessingState.EVIDENCE_COMPLETE})
        if working_primary is None or working_primary.thesis_type != ThesisType.PREDICTIVE:
            return
        claim_ids = [*working_primary.anchor_claim_ids, *working_primary.supporting_claim_ids]
        for claim_id in claim_ids[:3]:
            claim = claim_index[claim_id]
            if claim.status == ClaimStatus.SUPPORTED:
                claim.promote()

    def evaluate_publish_gate(
        self,
        research_object: ResearchObject,
        working_primary: Thesis | None,
        working_opposing: Thesis | None,
        claim_index: dict[str, Claim],
    ) -> PublishDecision:
        self._require_state("publish_gate", research_object, {ProcessingState.PUBLISH_READY})
        return self.publish_gate.evaluate(research_object, working_primary, working_opposing, claim_index)

    def _process_from_active_research(
        self,
        research_object: ResearchObject,
        claims: list[Claim],
        conflict_groups: list[ConflictGroup],
        theses: list[Thesis],
        steps: list[RuntimeStepLog],
    ) -> RuntimeResult:
        self._kernel_guard(
            operation="runtime.kernel.active_research",
            requested_scope=research_object.scope,
        )
        self.state_machine.begin_cycle(research_object)
        self.advance_claims(research_object, claims)
        steps.append(
            self._ok_step(
                research_object,
                "claim_status_refresh",
                details={"claim_statuses": {claim.claim_id: claim.status.value for claim in claims}},
            )
        )

        conflict_groups = self.group_claim_conflicts(research_object, claims)
        steps.append(
            self._ok_step(
                research_object,
                "claim_conflict_regrouping",
                details={"group_count": len(conflict_groups), "max_conflict": self._max_conflict(conflict_groups).value},
            )
        )

        theses = self.build_theses(research_object, claims, conflict_groups)
        research_object.thesis_ids = [thesis.thesis_id for thesis in theses]
        steps.append(
            self._ok_step(
                research_object,
                "thesis_building",
                details={
                    "thesis_ids": research_object.thesis_ids,
                    "thesis_types": {thesis.thesis_id: thesis.thesis_type.value for thesis in theses},
                },
            )
        )

        claim_index = {claim.claim_id: claim for claim in claims}
        working_primary, working_opposing = self.select_working_theses(research_object, theses, claim_index)
        steps.append(
            self._ok_step(
                research_object,
                "thesis_selection",
                details={
                    "working_primary": None if working_primary is None else working_primary.thesis_id,
                    "working_opposing": None if working_opposing is None else working_opposing.thesis_id,
                },
            )
        )

        self.evaluate_thesis_conflicts(research_object, working_primary, working_opposing, claim_index)
        steps.append(
            self._ok_step(
                research_object,
                "thesis_conflict_evaluation",
                details={
                    "working_primary_conflict": None if working_primary is None else working_primary.conflict_severity.value,
                    "working_opposing_conflict": None if working_opposing is None else working_opposing.conflict_severity.value,
                },
            )
        )

        research_object.risk_state = self.rule_service.derive_risk_state(claims)
        research_object.market_state = self.rule_service.derive_market_state(research_object, claims)
        research_object.attention_score = self.calculate_attention(research_object, claims, conflict_groups)
        steps.append(
            self._ok_step(
                research_object,
                "state_refresh",
                details={
                    "risk_state": research_object.risk_state.value,
                    "market_state": research_object.market_state.value,
                    "attention_score": research_object.attention_score,
                },
            )
        )

        self._transition_with_log(
            research_object,
            self.rule_service.active_research_exit_target(research_object, claims),
            "active_research_exit",
            steps,
        )

        if research_object.processing_state != ProcessingState.EVIDENCE_COMPLETE:
            steps.append(self._rejected_step(research_object, "publish_gate", {"reason": "processing_state is not publish_ready"}))
            return self._finalize(
                research_object,
                claims,
                conflict_groups,
                theses,
                self._decision_without_publish_gate(research_object),
                steps,
            )

        self.state_machine.begin_cycle(research_object)
        previous_theses = {thesis.thesis_id: thesis for thesis in theses}
        theses = self.build_theses(research_object, claims, conflict_groups)
        research_object.thesis_ids = [thesis.thesis_id for thesis in theses]
        self._carry_thesis_state(previous_theses, theses)
        working_primary, working_opposing = self.select_working_theses(research_object, theses, claim_index)
        self.evaluate_thesis_conflicts(research_object, working_primary, working_opposing, claim_index)
        self.promote_publishable_claims(research_object, working_primary, claim_index)
        steps.append(
            self._ok_step(
                research_object,
                "evidence_complete_evaluation",
                details={
                    "working_primary": None if working_primary is None else working_primary.thesis_id,
                    "working_primary_streak": None if working_primary is None else working_primary.working_primary_streak,
                    "promoted_claims": {
                        claim.claim_id: claim.status.value
                        for claim in claims
                        if claim.status in {ClaimStatus.PROMOTED, ClaimStatus.SUPPORTED}
                    },
                },
            )
        )

        self._transition_with_log(
            research_object,
            self.rule_service.evidence_complete_exit_target(research_object, working_primary),
            "evidence_complete_exit",
            steps,
        )

        self.state_machine.begin_cycle(research_object)
        if research_object.processing_state != ProcessingState.PUBLISH_READY:
            steps.append(self._rejected_step(research_object, "publish_gate", {"reason": "processing_state is not publish_ready"}))
            return self._finalize(
                research_object,
                claims,
                conflict_groups,
                theses,
                self._decision_without_publish_gate(research_object),
                steps,
            )

        decision = self.evaluate_publish_gate(research_object, working_primary, working_opposing, claim_index)
        steps.append(
            self._ok_step(
                research_object,
                "publish_gate",
                details={"decision": decision.decision, "reasons": decision.reasons},
            )
        )

        if decision.decision == PublishDecisionType.PUBLISH:
            if working_primary is not None:
                working_primary.status = ThesisStatus.PUBLISHED
            self._transition_with_log(research_object, ProcessingState.PUBLISHED, "publish_transition", steps)
        elif decision.decision == PublishDecisionType.MONITORING:
            if working_primary is not None and working_primary.thesis_type == ThesisType.PREDICTIVE:
                working_primary.status = ThesisStatus.CHALLENGED
            self._transition_with_log(research_object, ProcessingState.MONITORING, "publish_rejected_transition", steps)
        else:
            self._transition_with_log(research_object, ProcessingState.BLOCKED, "publish_block_transition", steps)
            research_object.risk_state = RiskState.BLOCKED

        return self._finalize(research_object, claims, conflict_groups, theses, decision, steps)

    def _carry_thesis_state(self, previous: dict[str, Thesis], current: list[Thesis]) -> None:
        for thesis in current:
            prior = previous.get(thesis.thesis_id)
            if prior is None:
                continue
            thesis.working_primary_streak = prior.working_primary_streak
            if prior.status in {ThesisStatus.CHALLENGED, ThesisStatus.PUBLISHABLE, ThesisStatus.PUBLISHED}:
                thesis.status = prior.status
            if prior.conflict_severity.rank > thesis.conflict_severity.rank:
                thesis.conflict_severity = prior.conflict_severity

    def _decision_without_publish_gate(self, research_object: ResearchObject) -> PublishDecision:
        if research_object.processing_state == ProcessingState.BLOCKED or research_object.risk_state == RiskState.BLOCKED:
            return PublishDecision(PublishDecisionType.BLOCKED, ["object is blocked before publish gate"])
        if research_object.processing_state == ProcessingState.ARCHIVED:
            return PublishDecision(PublishDecisionType.ARCHIVED, ["object archived before publish gate"])
        return PublishDecision(PublishDecisionType.MONITORING, ["object did not reach publish_ready"])

    def _guard_downstream_subject_keys(
        self,
        *,
        subject_keys: list[SubjectKey],
        consumer: str,
    ) -> None:
        if self.downstream_ingress_guard is None:
            return
        seen: set[str] = set()
        for subject_key in subject_keys:
            stable_key = subject_key.as_stable_string()
            if stable_key in seen:
                continue
            seen.add(stable_key)
            self.downstream_ingress_guard.guard_downstream_input(
                subject_key=subject_key,
                consumer=consumer,
                payload=None,
            )

    def _subject_keys_from_batches(self, batches: list[AdapterBatch]) -> list[SubjectKey]:
        subject_keys: list[SubjectKey] = []
        for batch in batches:
            raw_subject_key = str(batch.source_metadata.get("subject_key", "")).strip()
            subject_key = parse_subject_key_fragment(raw_subject_key)
            if subject_key is None:
                raise ValueError(
                    "adapter batch source_metadata subject_key must be a valid subject_key fragment; "
                    f"observed '{raw_subject_key}'"
                )
            subject_keys.append(subject_key)
        return subject_keys

    def _reallocate_store_sessions(self) -> dict[str, ResourceAllocation]:
        sessions = self.store.list_sessions()
        objects = [session.research_object for session in sessions]
        max_conflicts = {session.object_id: self._max_conflict(session.conflict_groups) for session in sessions}
        allocations = self.resource_allocator.allocate(objects, max_conflicts)
        allocation_map = {allocation.object_id: allocation for allocation in allocations}

        for session in sessions:
            session.resource_allocation = allocation_map.get(session.object_id)
            self.store.save(session)
        return allocation_map

    def _finalize(
        self,
        research_object: ResearchObject,
        claims: list[Claim],
        conflict_groups: list[ConflictGroup],
        theses: list[Thesis],
        decision: PublishDecision,
        steps: list[RuntimeStepLog],
    ) -> RuntimeResult:
        self._kernel_guard(
            operation="runtime.kernel.finalize",
            requested_scope=research_object.scope,
        )
        cadence = cadence_for_object(research_object)
        allocation = self._allocate_single(research_object, conflict_groups)
        steps.append(
            self._ok_step(
                research_object,
                "cadence_planning",
                details={
                    "mode": cadence.mode,
                    "normal_review_after": None if cadence.normal_review_after is None else str(cadence.normal_review_after),
                    "deep_review_after": None if cadence.deep_review_after is None else str(cadence.deep_review_after),
                },
            )
        )
        steps.append(
            self._ok_step(
                research_object,
                "resource_allocation",
                details={}
                if allocation is None
                else {
                    "tier": allocation.tier.value,
                    "slot_type": allocation.slot_type.value,
                },
            )
        )
        steps.append(
            self._ok_step(
                research_object,
                "session_save",
                details={"decision": decision.decision, "claim_count": len(claims), "thesis_count": len(theses)},
            )
        )

        session = RuntimeSession(
            object_id=research_object.object_id,
            research_object=research_object,
            claims=claims,
            conflict_groups=conflict_groups,
            theses=theses,
            latest_decision=decision,
            cadence=cadence,
            resource_allocation=allocation,
            last_steps=steps,
        )
        self.store.save(session)
        return RuntimeResult(
            research_object=research_object,
            claims=claims,
            conflict_groups=conflict_groups,
            theses=theses,
            decision=decision,
            cadence=cadence,
            resource_allocation=allocation,
            steps=steps,
        )

    def _allocate_single(self, research_object: ResearchObject, conflict_groups: list[ConflictGroup]) -> ResourceAllocation | None:
        allocations = self.resource_allocator.allocate(
            [research_object],
            {research_object.object_id: self._max_conflict(conflict_groups)},
        )
        return allocations[0] if allocations else None

    def _max_conflict(self, groups: list[ConflictGroup]) -> ConflictSeverity:
        return self.rule_service.max_conflict(groups)

    def _transition_with_log(
        self,
        research_object: ResearchObject,
        target: ProcessingState,
        step: str,
        steps: list[RuntimeStepLog],
        extra_details: dict[str, object] | None = None,
    ) -> None:
        self._kernel_guard(
            operation=f"runtime.kernel.transition.{step}",
            requested_scope=research_object.scope,
        )
        before = research_object.processing_state
        if target != before:
            self.state_machine.transition_processing(research_object, target)
        details = {"target": target.value}
        if extra_details:
            details.update(extra_details)
        steps.append(self._ok_step(research_object, step, before=before, details=details))

    def _require_state(self, step: str, research_object: ResearchObject, allowed: set[ProcessingState]) -> None:
        if research_object.processing_state not in allowed:
            allowed_text = ", ".join(state.value for state in sorted(allowed, key=lambda state: state.value))
            raise RuntimeBoundaryError(
                f"{step} cannot run in {research_object.processing_state.value}; allowed states: {allowed_text}"
            )

    def _ok_step(
        self,
        research_object: ResearchObject,
        step: str,
        *,
        before: ProcessingState | None = None,
        details: dict[str, object] | None = None,
    ) -> RuntimeStepLog:
        self._kernel_guard(
            operation=f"runtime.kernel.step.{step}",
            requested_scope=research_object.scope,
        )
        previous = research_object.processing_state if before is None else before
        return RuntimeStepLog(
            cycle=research_object.cycle_index,
            step=step,
            status="ok",
            processing_state_before=previous.value,
            processing_state_after=research_object.processing_state.value,
            details=details or {},
        )

    def _rejected_step(self, research_object: ResearchObject, step: str, details: dict[str, object] | None = None) -> RuntimeStepLog:
        self._kernel_guard(
            operation=f"runtime.kernel.step.{step}",
            requested_scope=research_object.scope,
        )
        return RuntimeStepLog(
            cycle=research_object.cycle_index,
            step=step,
            status="rejected",
            processing_state_before=research_object.processing_state.value,
            processing_state_after=research_object.processing_state.value,
            details=details or {},
        )
