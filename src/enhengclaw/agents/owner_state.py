from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


DEFAULT_OWNER_ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "artifacts" / "agent_owner"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _safe_fragment(value: str) -> str:
    fragment = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    return fragment or "unknown"


def _capability_artifact_filename(capability_id: str) -> str:
    safe = _safe_fragment(capability_id)
    digest = hashlib.sha1(safe.encode("utf-8")).hexdigest()[:20]
    prefix = safe[:12] if safe else "cap"
    return f"{prefix}_{digest}.json"


def _legacy_capability_artifact_filename(capability_id: str) -> str:
    return f"{_safe_fragment(capability_id)}.json"


def build_owner_run_id(*, requested_delegate_id: str, object_id: str) -> str:
    return f"{_safe_fragment(requested_delegate_id)}__{_safe_fragment(object_id)}"


class OwnerRunState(str, Enum):
    INIT = "INIT"
    SPECIFIED = "SPECIFIED"
    PLANNED = "PLANNED"
    DELEGATED = "DELEGATED"
    WRITTEN = "WRITTEN"
    REVIEWED = "REVIEWED"
    VERIFIED = "VERIFIED"
    FINALIZED = "FINALIZED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"

    @classmethod
    def normalize(cls, value: str | OwnerRunState) -> OwnerRunState:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().upper()
        aliases = {
            "COMPLETED": cls.FINALIZED,
            "COMPLETE": cls.FINALIZED,
            "DONE": cls.FINALIZED,
            "SUCCESS": cls.FINALIZED,
            "VERIFIED": cls.VERIFIED,
            "REVIEWED": cls.REVIEWED,
            "WRITTEN": cls.WRITTEN,
            "BLOCKED": cls.BLOCKED,
            "FAILED": cls.FAILED,
        }
        if normalized in cls._value2member_map_:
            return cls(normalized)
        if normalized in aliases:
            return aliases[normalized]
        raise ValueError(f"unsupported owner run state: {value}")


class CapabilityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    STALE = "STALE"
    FAILED = "FAILED"

    @classmethod
    def normalize(cls, value: str | CapabilityStatus) -> CapabilityStatus:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().upper()
        if normalized in cls._value2member_map_:
            return cls(normalized)
        raise ValueError(f"unsupported delegate capability status: {value}")


@dataclass(frozen=True, slots=True)
class OwnerWorkSpec:
    run_id: str
    owner_agent_id: str
    requested_delegate_id: str
    object_id: str
    subject: str
    scope: str
    user_intent: str
    constraints: tuple[str, ...] = ()
    signal_payload_fingerprint: str = ""
    spec_version: int = 1
    spec_fingerprint: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class DelegateCallContext:
    initiated_by: str
    owner_run_id: str
    spec_version: int
    step_id: str
    idempotency_key: str
    requested_delegate_id: str
    issued_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class DelegateCapabilityRecord:
    capability_id: str
    owner_run_id: str
    requested_delegate_id: str
    spec_version: int
    step_id: str
    idempotency_key: str
    object_id: str
    subject: str
    scope: str
    issued_by: str = "rulebook_owner"
    status: str = CapabilityStatus.ACTIVE.value
    provenance: str = "owner_capability"
    issued_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    consumed_at: str | None = None
    stale_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BacklogItem:
    task_id: str
    title: str
    status: str
    owner_agent_id: str
    notes: str = ""
    step_id: str = ""
    spec_version: int = 1
    updated_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class IntermediateFinding:
    finding_id: str
    author_agent_id: str
    summary: str
    evidence: tuple[str, ...] = ()
    severity: str = "info"
    step_id: str = ""
    spec_version: int = 1
    recorded_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class VerificationItem:
    item_id: str
    description: str
    status: str
    evidence: tuple[str, ...] = ()
    required: bool = True
    step_id: str = ""
    spec_version: int = 1
    updated_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class OwnerRunRecord:
    run_id: str
    owner_agent_id: str
    requested_delegate_id: str
    object_id: str
    subject: str
    scope: str
    state: str
    spec_version: int
    spec_fingerprint: str
    current_step_id: str = ""
    current_idempotency_key: str = ""
    latest_delegate_sequence: int = 0
    latest_review_sequence: int = 0
    stale_spec_versions: tuple[int, ...] = ()
    blocked_reason: str | None = None
    final_output_path: str | None = None
    reconciliation_notes: tuple[str, ...] = ()
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class DelegateArtifactRecord:
    run_id: str
    delegate_name: str
    sequence: int
    step_id: str
    spec_version: int
    owner_run_id: str
    idempotency_key: str
    requested_delegate_id: str
    initiated_by: str
    object_id: str
    subject: str
    scope: str
    scenario: str
    signal_payload: dict[str, Any]
    accepted_signal_ids: tuple[str, ...] = ()
    replay_log_paths: tuple[str, ...] = ()
    quarantine_paths: tuple[str, ...] = ()
    runtime_decision: str | None = None
    runtime_processing_state: str | None = None
    runtime_risk_state: str | None = None
    runtime_claim_count: int | None = None
    provenance: str = "owner_first_delegate"
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class ReviewArtifactRecord:
    run_id: str
    review_name: str
    sequence: int
    step_id: str
    spec_version: int
    owner_run_id: str
    requested_delegate_id: str
    reviewer_agent_id: str
    object_id: str
    gate_applied: bool
    gate_passed: bool
    payload: dict[str, Any]
    rationale: tuple[str, ...] = ()
    provenance: str = "owner_review_gate"
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class OwnerSynthesisRecord:
    run_id: str
    owner_agent_id: str
    spec_version: int
    step_id: str
    findings: tuple[IntermediateFinding, ...] = ()
    summary: str = ""
    provenance: str = "owner_synthesis"
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class FinalOutputRecord:
    run_id: str
    owner_agent_id: str
    selected_delegate_id: str
    status: str
    summary: str
    output_paths: tuple[str, ...] = ()
    run_state: str = OwnerRunState.FINALIZED.value
    spec_version: int = 1
    step_id: str = ""
    blocked_reason: str | None = None
    provenance: str = "owner_finalizer"
    finalized_at: str = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class OwnerArtifactPaths:
    root: Path
    owner_root: Path
    agent_execution_root: Path
    delegates_root: Path
    reviews_root: Path
    capabilities_root: Path
    spec_path: Path
    backlog_path: Path
    findings_path: Path
    synthesis_path: Path
    verification_path: Path
    final_output_path: Path
    run_state_path: Path


def compute_spec_fingerprint(spec: OwnerWorkSpec) -> str:
    payload = {
        "run_id": spec.run_id,
        "owner_agent_id": spec.owner_agent_id,
        "requested_delegate_id": spec.requested_delegate_id,
        "object_id": spec.object_id,
        "subject": spec.subject,
        "scope": spec.scope,
        "user_intent": spec.user_intent,
        "constraints": list(spec.constraints),
        "signal_payload_fingerprint": spec.signal_payload_fingerprint,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_idempotency_key(
    *,
    requested_delegate_id: str,
    object_id: str,
    subject: str,
    scope: str,
    signal_payload: dict[str, Any],
    spec_version: int,
) -> str:
    payload = {
        "requested_delegate_id": requested_delegate_id,
        "object_id": object_id,
        "subject": subject,
        "scope": scope,
        "signal_payload": signal_payload,
        "spec_version": spec_version,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def compute_delegate_capability_id(
    *,
    owner_run_id: str,
    requested_delegate_id: str,
    spec_version: int,
    step_id: str,
    idempotency_key: str,
    object_id: str,
    subject: str,
    scope: str,
) -> str:
    payload = {
        "owner_run_id": owner_run_id,
        "requested_delegate_id": requested_delegate_id,
        "spec_version": spec_version,
        "step_id": step_id,
        "idempotency_key": idempotency_key,
        "object_id": object_id,
        "subject": subject,
        "scope": scope,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"cap_{digest}"


class OwnerArtifactStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (Path(root) if root is not None else DEFAULT_OWNER_ARTIFACT_ROOT).resolve()

    def paths_for(self, run_id: str) -> OwnerArtifactPaths:
        bundle_root = self.root / _safe_fragment(run_id)
        owner_root = bundle_root / "owner"
        findings_path = owner_root / "findings_rollup.json"
        return OwnerArtifactPaths(
            root=bundle_root,
            owner_root=owner_root,
            agent_execution_root=owner_root / "agent_execution",
            delegates_root=bundle_root / "delegates",
            reviews_root=bundle_root / "reviews",
            capabilities_root=owner_root / "capabilities",
            spec_path=owner_root / "spec.json",
            backlog_path=owner_root / "backlog.json",
            findings_path=findings_path,
            synthesis_path=findings_path,
            verification_path=owner_root / "verification.json",
            final_output_path=owner_root / "final_output.json",
            run_state_path=owner_root / "run_state.json",
        )

    def legacy_paths_for(self, run_id: str) -> OwnerArtifactPaths:
        bundle_root = self.root / _safe_fragment(run_id)
        findings_path = bundle_root / "findings.json"
        return OwnerArtifactPaths(
            root=bundle_root,
            owner_root=bundle_root,
            agent_execution_root=bundle_root / "agent_execution",
            delegates_root=bundle_root / "delegates",
            reviews_root=bundle_root / "reviews",
            capabilities_root=bundle_root / "capabilities",
            spec_path=bundle_root / "spec.json",
            backlog_path=bundle_root / "backlog.json",
            findings_path=findings_path,
            synthesis_path=findings_path,
            verification_path=bundle_root / "verification.json",
            final_output_path=bundle_root / "final_output.json",
            run_state_path=bundle_root / "run_state.json",
        )

    def capabilities_directory(self, run_id: str) -> Path:
        return self.paths_for(run_id).capabilities_root

    def capability_path(self, run_id: str, capability_id: str) -> Path:
        return self.capabilities_directory(run_id) / _capability_artifact_filename(capability_id)

    def legacy_capability_path(self, run_id: str, capability_id: str) -> Path:
        return self.capabilities_directory(run_id) / _legacy_capability_artifact_filename(capability_id)

    def execution_directory(self, run_id: str) -> Path:
        return self.paths_for(run_id).agent_execution_root

    def execution_artifact_path(self, run_id: str, artifact_name: str) -> Path:
        return self.execution_directory(run_id) / f"{_safe_fragment(artifact_name)}.json"

    def load_json(self, path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"owner artifact must be a JSON object: {path}")
        return payload

    def load_run_record(self, run_id: str) -> dict[str, Any] | None:
        spec_payload = self._load_first_existing(self.paths_for(run_id).spec_path, self.legacy_paths_for(run_id).spec_path)
        if spec_payload is None:
            return None
        derived = self.recover_run_record(run_id)
        if derived is None:
            return None
        stored = self._load_first_existing(self.paths_for(run_id).run_state_path, self.legacy_paths_for(run_id).run_state_path)
        if stored is None:
            return derived
        return self._reconcile_run_records(run_id, stored, derived)

    def recover_run_record(self, run_id: str) -> dict[str, Any] | None:
        paths = self.paths_for(run_id)
        legacy = self.legacy_paths_for(run_id)
        spec_payload = self._load_first_existing(paths.spec_path, legacy.spec_path)
        if spec_payload is None:
            return None
        spec_version = int(spec_payload.get("spec_version", 1))
        delegate_records = self.list_delegate_artifacts(run_id, spec_version=spec_version)
        review_records = self.list_review_artifacts(run_id, spec_version=spec_version)
        verification_payload = self._load_first_existing(paths.verification_path, legacy.verification_path)
        final_output = self._load_first_existing(paths.final_output_path, legacy.final_output_path)
        backlog_payload = self._load_first_existing(paths.backlog_path, legacy.backlog_path)
        contradictions: list[str] = []

        state = OwnerRunState.SPECIFIED
        current_step_id = ""
        latest_delegate_sequence = 0
        latest_review_sequence = 0
        current_idempotency_key = ""

        if backlog_payload is not None:
            state = OwnerRunState.PLANNED
            current_step_id = str(backlog_payload.get("step_id", "")).strip()
        if delegate_records:
            state = OwnerRunState.WRITTEN
            latest_delegate_sequence = max(int(item.get("sequence", 0)) for item in delegate_records)
            latest_delegate = delegate_records[-1]
            current_step_id = str(latest_delegate.get("step_id", current_step_id)).strip()
            current_idempotency_key = str(latest_delegate.get("idempotency_key", "")).strip()
        if review_records:
            latest_review_sequence = max(int(item.get("sequence", 0)) for item in review_records)
            current_step_id = str(review_records[-1].get("step_id", current_step_id)).strip()
            if not delegate_records:
                contradictions.append("review_records_exist_without_delegate_records")
            else:
                state = OwnerRunState.REVIEWED
        if verification_payload is not None:
            current_step_id = str(verification_payload.get("step_id", current_step_id)).strip()
            if _verification_passed(verification_payload):
                if not delegate_records:
                    contradictions.append("verification_passed_without_delegate_records")
                else:
                    state = OwnerRunState.VERIFIED
        if final_output is not None:
            current_step_id = str(final_output.get("step_id", current_step_id)).strip()
            final_state = OwnerRunState.normalize(str(final_output.get("run_state", final_output.get("status", state.value))))
            if final_state == OwnerRunState.FINALIZED and not delegate_records:
                contradictions.append("final_output_finalized_without_delegate_records")
            if str(final_output.get("status", "")).strip().lower() == "completed" and not delegate_records:
                contradictions.append("completed_final_output_without_delegate_records")
            state = final_state

        if contradictions:
            state = OwnerRunState.FAILED

        record = OwnerRunRecord(
            run_id=run_id,
            owner_agent_id=str(spec_payload.get("owner_agent_id", "rulebook_owner")),
            requested_delegate_id=str(spec_payload.get("requested_delegate_id", "")),
            object_id=str(spec_payload.get("object_id", "")),
            subject=str(spec_payload.get("subject", "")),
            scope=str(spec_payload.get("scope", "")),
            state=state.value,
            spec_version=spec_version,
            spec_fingerprint=str(spec_payload.get("spec_fingerprint", "")),
            current_step_id=current_step_id,
            current_idempotency_key=current_idempotency_key,
            latest_delegate_sequence=latest_delegate_sequence,
            latest_review_sequence=latest_review_sequence,
            stale_spec_versions=tuple(int(item) for item in spec_payload.get("stale_spec_versions", ()) if str(item).strip()),
            blocked_reason=None if final_output is None else final_output.get("blocked_reason"),
            final_output_path=None if final_output is None else str(paths.final_output_path if paths.final_output_path.exists() else legacy.final_output_path),
            reconciliation_notes=tuple(contradictions),
            created_at=str(spec_payload.get("created_at", _utc_now())),
            updated_at=_utc_now(),
        )
        return _as_record(record)

    def list_delegate_artifacts(
        self,
        run_id: str,
        delegate_name: str | None = None,
        *,
        spec_version: int | None = None,
    ) -> list[dict[str, Any]]:
        base = self.paths_for(run_id).delegates_root
        roots = [base / _safe_fragment(delegate_name)] if delegate_name is not None else self._child_dirs(base)
        return self._list_artifacts(roots, spec_version=spec_version)

    def list_review_artifacts(
        self,
        run_id: str,
        review_name: str | None = None,
        *,
        spec_version: int | None = None,
    ) -> list[dict[str, Any]]:
        base = self.paths_for(run_id).reviews_root
        roots = [base / _safe_fragment(review_name)] if review_name is not None else self._child_dirs(base)
        return self._list_artifacts(roots, spec_version=spec_version)

    def list_capabilities(
        self,
        run_id: str,
        *,
        spec_version: int | None = None,
        requested_delegate_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self._list_artifacts([self.capabilities_directory(run_id)], spec_version=spec_version)
        if requested_delegate_id is not None:
            records = [item for item in records if str(item.get("requested_delegate_id", "")).strip() == requested_delegate_id]
        if status is not None:
            normalized_status = CapabilityStatus.normalize(status).value
            records = [item for item in records if str(item.get("status", "")).strip().upper() == normalized_status]
        return records

    def find_delegate_artifact(
        self,
        run_id: str,
        delegate_name: str,
        *,
        spec_version: int,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        for payload in self.list_delegate_artifacts(run_id, delegate_name, spec_version=spec_version):
            if str(payload.get("idempotency_key", "")) == idempotency_key:
                return payload
        return None

    def find_review_artifact(
        self,
        run_id: str,
        review_name: str,
        *,
        spec_version: int,
        step_id: str,
    ) -> dict[str, Any] | None:
        for payload in self.list_review_artifacts(run_id, review_name, spec_version=spec_version):
            if str(payload.get("step_id", "")) == step_id:
                return payload
        return None

    def find_capability(self, capability_id: str, *, run_id: str | None = None) -> dict[str, Any] | None:
        if run_id is not None:
            for path in (self.capability_path(run_id, capability_id), self.legacy_capability_path(run_id, capability_id)):
                if path.exists():
                    payload = self.load_json(path)
                    payload["artifact_path"] = str(path)
                    return payload
            for payload in self.list_capabilities(run_id):
                if str(payload.get("capability_id", "")) == capability_id:
                    return payload
            return None
        for bundle_root in self._child_dirs(self.root):
            for filename in (_capability_artifact_filename(capability_id), _legacy_capability_artifact_filename(capability_id)):
                path = bundle_root / "owner" / "capabilities" / filename
                if path.exists():
                    payload = self.load_json(path)
                    payload["artifact_path"] = str(path)
                    return payload
            for path in sorted((bundle_root / "owner" / "capabilities").glob("*.json")):
                payload = self.load_json(path)
                if str(payload.get("capability_id", "")) == capability_id:
                    payload["artifact_path"] = str(path)
                    return payload
        return None

    def find_step_capability(
        self,
        run_id: str,
        *,
        requested_delegate_id: str,
        spec_version: int,
        step_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        for payload in self.list_capabilities(run_id, spec_version=spec_version, requested_delegate_id=requested_delegate_id):
            if str(payload.get("step_id", "")) != step_id:
                continue
            if str(payload.get("idempotency_key", "")) != idempotency_key:
                continue
            return payload
        return None

    def load_execution_artifact(self, run_id: str, artifact_name: str) -> dict[str, Any] | None:
        path = self.execution_artifact_path(run_id, artifact_name)
        if not path.exists():
            return None
        payload = self.load_json(path)
        payload["artifact_path"] = str(path)
        return payload

    def list_execution_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.execution_directory(run_id).glob("*.json")):
            payload = self.load_json(path)
            payload["artifact_path"] = str(path)
            records.append(payload)
        return records

    def next_delegate_sequence(self, run_id: str, delegate_name: str) -> int:
        return self._next_sequence(self.paths_for(run_id).delegates_root / _safe_fragment(delegate_name))

    def next_review_sequence(self, run_id: str, review_name: str) -> int:
        return self._next_sequence(self.paths_for(run_id).reviews_root / _safe_fragment(review_name))

    def _child_dirs(self, directory: Path) -> list[Path]:
        return [candidate for candidate in directory.iterdir() if candidate.is_dir()] if directory.exists() else []

    def _list_artifacts(self, roots: list[Path], *, spec_version: int | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.json")):
                payload = self.load_json(path)
                if spec_version is not None and int(payload.get("spec_version", 1)) != spec_version:
                    continue
                payload["artifact_path"] = str(path)
                records.append(payload)
        records.sort(key=lambda item: (int(item.get("sequence", 0)), str(item.get("timestamp", item.get("updated_at", "")))))
        return records

    def _next_sequence(self, directory: Path) -> int:
        if not directory.exists():
            return 1
        max_value = 0
        for path in directory.glob("*.json"):
            try:
                max_value = max(max_value, int(path.stem))
            except ValueError:
                continue
        return max_value + 1

    def _load_first_existing(self, *paths: Path) -> dict[str, Any] | None:
        for path in paths:
            if path.exists():
                return self.load_json(path)
        return None

    def _reconcile_run_records(
        self,
        run_id: str,
        stored: dict[str, Any],
        derived: dict[str, Any],
    ) -> dict[str, Any]:
        stored_state = OwnerRunState.normalize(str(stored.get("state", OwnerRunState.INIT.value)))
        derived_state = OwnerRunState.normalize(str(derived.get("state", OwnerRunState.INIT.value)))
        reconciliation_notes = [str(item) for item in derived.get("reconciliation_notes", ()) if str(item).strip()]
        if str(stored.get("spec_fingerprint", "")) and str(derived.get("spec_fingerprint", "")):
            if str(stored.get("spec_fingerprint", "")) != str(derived.get("spec_fingerprint", "")):
                reconciliation_notes.append("stored_run_state_spec_fingerprint_mismatch")
        if derived_state == OwnerRunState.FAILED:
            return self._failed_run_record(run_id, stored, derived, reconciliation_notes or ["run_state_reconciliation_failed"])
        if stored_state != derived_state:
            reconciliation_notes.append(f"state_reconciled:{stored_state.value}->{derived_state.value}")
        return {
            **stored,
            "state": derived_state.value,
            "spec_version": int(derived.get("spec_version", stored.get("spec_version", 1))),
            "spec_fingerprint": str(derived.get("spec_fingerprint", stored.get("spec_fingerprint", ""))),
            "current_step_id": str(derived.get("current_step_id", stored.get("current_step_id", ""))),
            "current_idempotency_key": str(derived.get("current_idempotency_key", stored.get("current_idempotency_key", ""))),
            "latest_delegate_sequence": int(derived.get("latest_delegate_sequence", stored.get("latest_delegate_sequence", 0))),
            "latest_review_sequence": int(derived.get("latest_review_sequence", stored.get("latest_review_sequence", 0))),
            "stale_spec_versions": list(derived.get("stale_spec_versions", stored.get("stale_spec_versions", ()))),
            "blocked_reason": derived.get("blocked_reason", stored.get("blocked_reason")),
            "final_output_path": derived.get("final_output_path", stored.get("final_output_path")),
            "reconciliation_notes": reconciliation_notes,
        }

    def _failed_run_record(
        self,
        run_id: str,
        stored: dict[str, Any],
        derived: dict[str, Any],
        reconciliation_notes: list[str],
    ) -> dict[str, Any]:
        spec_payload = self._load_first_existing(self.paths_for(run_id).spec_path, self.legacy_paths_for(run_id).spec_path)
        if spec_payload is None:
            return derived
        return _as_record(
            OwnerRunRecord(
                run_id=run_id,
                owner_agent_id=str(spec_payload.get("owner_agent_id", stored.get("owner_agent_id", "rulebook_owner"))),
                requested_delegate_id=str(spec_payload.get("requested_delegate_id", stored.get("requested_delegate_id", ""))),
                object_id=str(spec_payload.get("object_id", stored.get("object_id", ""))),
                subject=str(spec_payload.get("subject", stored.get("subject", ""))),
                scope=str(spec_payload.get("scope", stored.get("scope", ""))),
                state=OwnerRunState.FAILED.value,
                spec_version=int(derived.get("spec_version", spec_payload.get("spec_version", 1))),
                spec_fingerprint=str(derived.get("spec_fingerprint", spec_payload.get("spec_fingerprint", ""))),
                current_step_id=str(derived.get("current_step_id", stored.get("current_step_id", ""))),
                current_idempotency_key=str(derived.get("current_idempotency_key", stored.get("current_idempotency_key", ""))),
                latest_delegate_sequence=int(derived.get("latest_delegate_sequence", 0)),
                latest_review_sequence=int(derived.get("latest_review_sequence", 0)),
                stale_spec_versions=tuple(int(item) for item in derived.get("stale_spec_versions", ()) if str(item).strip()),
                blocked_reason="run_state_artifact_conflict",
                final_output_path=derived.get("final_output_path"),
                reconciliation_notes=tuple(reconciliation_notes),
            )
        )


class OwnerArtifactWriter(OwnerArtifactStore):
    def write_spec(self, spec: OwnerWorkSpec) -> Path:
        normalized = spec
        fingerprint = spec.spec_fingerprint or compute_spec_fingerprint(spec)
        if normalized.spec_fingerprint != fingerprint:
            normalized = OwnerWorkSpec(
                run_id=spec.run_id,
                owner_agent_id=spec.owner_agent_id,
                requested_delegate_id=spec.requested_delegate_id,
                object_id=spec.object_id,
                subject=spec.subject,
                scope=spec.scope,
                user_intent=spec.user_intent,
                constraints=spec.constraints,
                signal_payload_fingerprint=spec.signal_payload_fingerprint,
                spec_version=spec.spec_version,
                spec_fingerprint=fingerprint,
                created_at=spec.created_at,
                updated_at=spec.updated_at,
            )
        self._write_json(self.paths_for(spec.run_id).spec_path, _as_record(normalized))
        return self.paths_for(spec.run_id).spec_path

    def write_run_state(self, record: OwnerRunRecord) -> Path:
        self._write_json(self.paths_for(record.run_id).run_state_path, _as_record(record))
        return self.paths_for(record.run_id).run_state_path

    def write_backlog(
        self,
        run_id: str,
        items: list[BacklogItem],
        *,
        owner_agent_id: str = "rulebook_owner",
        spec_version: int = 1,
        step_id: str = "",
        stale_spec_versions: tuple[int, ...] = (),
    ) -> Path:
        payload = {
            "run_id": run_id,
            "owner_agent_id": owner_agent_id,
            "spec_version": spec_version,
            "step_id": step_id,
            "stale_spec_versions": list(stale_spec_versions),
            "timestamp": _utc_now(),
            "items": [_as_record(item) for item in items],
        }
        self._write_json(self.paths_for(run_id).backlog_path, payload)
        return self.paths_for(run_id).backlog_path

    def write_findings(
        self,
        run_id: str,
        findings: list[IntermediateFinding],
        *,
        owner_agent_id: str = "rulebook_owner",
        spec_version: int = 1,
        step_id: str = "",
        summary: str = "",
    ) -> Path:
        payload = _as_record(
            OwnerSynthesisRecord(
                run_id=run_id,
                owner_agent_id=owner_agent_id,
                spec_version=spec_version,
                step_id=step_id,
                findings=tuple(findings),
                summary=summary,
            )
        )
        self._write_json(self.paths_for(run_id).findings_path, payload)
        return self.paths_for(run_id).findings_path

    def write_synthesis(self, record: OwnerSynthesisRecord) -> Path:
        self._write_json(self.paths_for(record.run_id).synthesis_path, _as_record(record))
        return self.paths_for(record.run_id).synthesis_path

    def write_verification(
        self,
        run_id: str,
        items: list[VerificationItem],
        *,
        owner_agent_id: str = "rulebook_owner",
        spec_version: int = 1,
        step_id: str = "",
        blocked_reason: str | None = None,
    ) -> Path:
        payload = {
            "run_id": run_id,
            "owner_agent_id": owner_agent_id,
            "spec_version": spec_version,
            "step_id": step_id,
            "blocked_reason": blocked_reason,
            "timestamp": _utc_now(),
            "items": [_as_record(item) for item in items],
        }
        self._write_json(self.paths_for(run_id).verification_path, payload)
        return self.paths_for(run_id).verification_path

    def write_final_output(self, record: FinalOutputRecord) -> Path:
        self._write_json(self.paths_for(record.run_id).final_output_path, _as_record(record))
        return self.paths_for(record.run_id).final_output_path

    def write_execution_artifact(self, run_id: str, artifact_name: str, payload: dict[str, Any]) -> Path:
        path = self.execution_artifact_path(run_id, artifact_name)
        self._write_json(path, payload)
        return path

    def clear_owner_control_plane(self, run_id: str) -> None:
        paths = self.paths_for(run_id)
        for path in (
            paths.backlog_path,
            paths.findings_path,
            paths.synthesis_path,
            paths.verification_path,
            paths.final_output_path,
        ):
            if path.exists():
                path.unlink()
        if paths.agent_execution_root.exists():
            for artifact_path in paths.agent_execution_root.glob("*.json"):
                artifact_path.unlink()

    def append_delegate_artifact(self, record: DelegateArtifactRecord) -> Path:
        path = self.paths_for(record.run_id).delegates_root / _safe_fragment(record.delegate_name) / f"{record.sequence:04d}.json"
        self._write_json(path, _as_record(record))
        return path

    def append_review_artifact(self, record: ReviewArtifactRecord) -> Path:
        path = self.paths_for(record.run_id).reviews_root / _safe_fragment(record.review_name) / f"{record.sequence:04d}.json"
        self._write_json(path, _as_record(record))
        return path

    def write_capability(self, record: DelegateCapabilityRecord) -> Path:
        path = self.capability_path(record.owner_run_id, record.capability_id)
        self._write_json(path, _as_record(record))
        return path

    def mark_capability_status(
        self,
        capability_id: str,
        *,
        run_id: str,
        status: str,
        stale_reason: str | None = None,
        consumed_at: str | None = None,
    ) -> Path:
        existing = self.find_capability(capability_id, run_id=run_id)
        if existing is None:
            raise FileNotFoundError(f"unknown delegate capability: {capability_id}")
        record = DelegateCapabilityRecord(
            capability_id=str(existing["capability_id"]),
            owner_run_id=str(existing["owner_run_id"]),
            requested_delegate_id=str(existing["requested_delegate_id"]),
            spec_version=int(existing["spec_version"]),
            step_id=str(existing["step_id"]),
            idempotency_key=str(existing["idempotency_key"]),
            object_id=str(existing["object_id"]),
            subject=str(existing["subject"]),
            scope=str(existing["scope"]),
            issued_by=str(existing.get("issued_by", "rulebook_owner")),
            status=CapabilityStatus.normalize(status).value,
            provenance=str(existing.get("provenance", "owner_capability")),
            issued_at=str(existing.get("issued_at", _utc_now())),
            updated_at=_utc_now(),
            consumed_at=consumed_at if consumed_at is not None else existing.get("consumed_at"),
            stale_reason=stale_reason if stale_reason is not None else existing.get("stale_reason"),
        )
        return self.write_capability(record)

    def stale_capabilities(
        self,
        run_id: str,
        *,
        before_spec_version: int | None = None,
        except_capability_id: str | None = None,
        stale_reason: str,
    ) -> None:
        for payload in self.list_capabilities(run_id):
            if except_capability_id is not None and str(payload.get("capability_id", "")) == except_capability_id:
                continue
            if before_spec_version is not None and int(payload.get("spec_version", 0)) >= before_spec_version:
                continue
            if CapabilityStatus.normalize(str(payload.get("status", CapabilityStatus.ACTIVE.value))) == CapabilityStatus.STALE:
                continue
            self.mark_capability_status(
                str(payload["capability_id"]),
                run_id=run_id,
                status=CapabilityStatus.STALE.value,
                stale_reason=stale_reason,
            )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _as_record(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _as_record(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_record(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _as_record(asdict(value))
    return value


def _verification_passed(payload: dict[str, Any]) -> bool:
    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if item.get("required", True) and str(item.get("status", "")).strip().lower() != "passed":
            return False
    return True
