from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.core.cadence import CadencePlan
from enhengclaw.core.claims import Claim, EvidenceRef
from enhengclaw.core.conflicts import ConflictGroup
from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    ConflictResolution,
    ConflictSeverity,
    Direction,
    EvidenceLevel,
    MarketState,
    ObjectType,
    ProcessingState,
    ResourceTier,
    RiskState,
    SlotType,
    SourceFamily,
    ThesisStatus,
    ThesisType,
    TimeHorizon,
)
from enhengclaw.core.publish_gate import PublishDecision
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.resources import ResourceAllocation
from enhengclaw.core.thesis import Thesis


RUNTIME_SESSION_ROOT_ENV = "ENHENGCLAW_RUNTIME_SESSION_ROOT"


@dataclass(slots=True)
class RuntimeSession:
    object_id: str
    research_object: ResearchObject
    claims: list[Claim] = field(default_factory=list)
    conflict_groups: list[ConflictGroup] = field(default_factory=list)
    theses: list[Thesis] = field(default_factory=list)
    latest_decision: PublishDecision | None = None
    cadence: CadencePlan | None = None
    resource_allocation: ResourceAllocation | None = None
    last_steps: list[Any] = field(default_factory=list)


class InMemoryObjectStore:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSession] = {}

    def save(self, session: RuntimeSession) -> RuntimeSession:
        self._sessions[session.object_id] = deepcopy(session)
        return deepcopy(session)

    def load(self, object_id: str) -> RuntimeSession:
        if object_id not in self._sessions:
            raise KeyError(f"Unknown session: {object_id}")
        return deepcopy(self._sessions[object_id])

    def exists(self, object_id: str) -> bool:
        return object_id in self._sessions

    def list_sessions(self) -> list[RuntimeSession]:
        return [deepcopy(session) for session in self._sessions.values()]


class FileObjectStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = self._resolve_root(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, session: RuntimeSession) -> RuntimeSession:
        target = self._session_path(session.object_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(runtime_session_to_record(session), indent=2), encoding="utf-8")
        return deepcopy(session)

    def load(self, object_id: str) -> RuntimeSession:
        path = self._session_path(object_id)
        if not path.exists():
            raise KeyError(f"Unknown session: {object_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return runtime_session_from_record(payload)

    def exists(self, object_id: str) -> bool:
        return self._session_path(object_id).exists()

    def list_sessions(self) -> list[RuntimeSession]:
        sessions: list[RuntimeSession] = []
        for path in sorted(self.root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sessions.append(runtime_session_from_record(payload))
        return sessions

    def _session_path(self, object_id: str) -> Path:
        safe_object_id = quote(object_id, safe="._-")
        return self.root / f"{safe_object_id}.json"

    @staticmethod
    def _resolve_root(root: str | Path | None) -> Path:
        candidate = root or getenv_compat(RUNTIME_SESSION_ROOT_ENV)
        if candidate is not None and str(candidate).strip():
            return Path(candidate).resolve()
        local_appdata = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (local_appdata / "EnhengClaw" / "runtime_sessions").resolve()


def runtime_session_to_record(session: RuntimeSession) -> dict[str, Any]:
    return {
        "object_id": session.object_id,
        "research_object": research_object_to_record(session.research_object),
        "claims": [claim_to_record(claim) for claim in session.claims],
        "conflict_groups": [conflict_group_to_record(group) for group in session.conflict_groups],
        "theses": [thesis_to_record(thesis) for thesis in session.theses],
        "latest_decision": None if session.latest_decision is None else publish_decision_to_record(session.latest_decision),
        "cadence": None if session.cadence is None else cadence_plan_to_record(session.cadence),
        "resource_allocation": None
        if session.resource_allocation is None
        else resource_allocation_to_record(session.resource_allocation),
        "last_steps": [_step_to_record(step) for step in session.last_steps],
    }


def runtime_session_from_record(payload: dict[str, Any]) -> RuntimeSession:
    return RuntimeSession(
        object_id=str(payload["object_id"]),
        research_object=research_object_from_record(payload["research_object"]),
        claims=[claim_from_record(item) for item in payload.get("claims", [])],
        conflict_groups=[conflict_group_from_record(item) for item in payload.get("conflict_groups", [])],
        theses=[thesis_from_record(item) for item in payload.get("theses", [])],
        latest_decision=None
        if payload.get("latest_decision") is None
        else publish_decision_from_record(payload["latest_decision"]),
        cadence=None if payload.get("cadence") is None else cadence_plan_from_record(payload["cadence"]),
        resource_allocation=None
        if payload.get("resource_allocation") is None
        else resource_allocation_from_record(payload["resource_allocation"]),
        last_steps=[step_from_record(item) for item in payload.get("last_steps", [])],
    )


def research_object_to_record(research_object: ResearchObject) -> dict[str, Any]:
    return {
        "object_id": research_object.object_id,
        "object_type": research_object.object_type.value,
        "scope": research_object.scope,
        "time_horizon": research_object.time_horizon.value,
        "processing_state": research_object.processing_state.value,
        "risk_state": research_object.risk_state.value,
        "market_state": research_object.market_state.value,
        "attention_score": research_object.attention_score,
        "claim_ids": list(research_object.claim_ids),
        "thesis_ids": list(research_object.thesis_ids),
        "working_primary_thesis_id": research_object.working_primary_thesis_id,
        "working_opposing_thesis_id": research_object.working_opposing_thesis_id,
        "cycle_index": research_object.cycle_index,
        "processing_transitions_this_cycle": research_object.processing_transitions_this_cycle,
    }


def research_object_from_record(payload: dict[str, Any]) -> ResearchObject:
    return ResearchObject(
        object_id=str(payload["object_id"]),
        object_type=ObjectType(payload["object_type"]),
        scope=str(payload["scope"]),
        time_horizon=TimeHorizon(payload["time_horizon"]),
        processing_state=ProcessingState(payload.get("processing_state", ProcessingState.CANDIDATE.value)),
        risk_state=RiskState(payload.get("risk_state", RiskState.NORMAL.value)),
        market_state=MarketState(payload.get("market_state", MarketState.PRE_EMERGENCE.value)),
        attention_score=int(payload.get("attention_score", 0)),
        claim_ids=[str(item) for item in payload.get("claim_ids", [])],
        thesis_ids=[str(item) for item in payload.get("thesis_ids", [])],
        working_primary_thesis_id=payload.get("working_primary_thesis_id"),
        working_opposing_thesis_id=payload.get("working_opposing_thesis_id"),
        cycle_index=int(payload.get("cycle_index", 0)),
        processing_transitions_this_cycle=int(payload.get("processing_transitions_this_cycle", 0)),
    )


def evidence_ref_to_record(evidence: EvidenceRef) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "level": evidence.level.value,
        "source_family": evidence.source_family.value,
        "fresh": evidence.fresh,
    }


def evidence_ref_from_record(payload: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=str(payload["evidence_id"]),
        level=EvidenceLevel(payload["level"]),
        source_family=SourceFamily(payload["source_family"]),
        fresh=bool(payload.get("fresh", True)),
    )


def claim_to_record(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "object_id": claim.object_id,
        "claim_type": claim.claim_type.value,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "value": claim.value,
        "direction": claim.direction.value,
        "scope": claim.scope,
        "time_horizon": claim.time_horizon.value,
        "source_family": claim.source_family.value,
        "confidence": claim.confidence,
        "status": claim.status.value,
        "evidence": [evidence_ref_to_record(item) for item in claim.evidence],
        "conflict_group_id": claim.conflict_group_id,
    }


def claim_from_record(payload: dict[str, Any]) -> Claim:
    return Claim(
        claim_id=str(payload["claim_id"]),
        object_id=str(payload["object_id"]),
        claim_type=ClaimType(payload["claim_type"]),
        subject=str(payload["subject"]),
        predicate=str(payload["predicate"]),
        value=str(payload["value"]),
        direction=Direction(payload["direction"]),
        scope=str(payload["scope"]),
        time_horizon=TimeHorizon(payload["time_horizon"]),
        source_family=SourceFamily(payload["source_family"]),
        confidence=int(payload["confidence"]),
        status=ClaimStatus(payload["status"]),
        evidence=[evidence_ref_from_record(item) for item in payload.get("evidence", [])],
        conflict_group_id=payload.get("conflict_group_id"),
    )


def conflict_group_to_record(group: ConflictGroup) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "object_id": group.object_id,
        "claim_ids": list(group.claim_ids),
        "severity": group.severity.value,
        "resolution": group.resolution.value,
        "winning_claim_id": group.winning_claim_id,
    }


def conflict_group_from_record(payload: dict[str, Any]) -> ConflictGroup:
    return ConflictGroup(
        group_id=str(payload["group_id"]),
        object_id=str(payload["object_id"]),
        claim_ids=[str(item) for item in payload.get("claim_ids", [])],
        severity=ConflictSeverity(payload["severity"]),
        resolution=ConflictResolution(payload["resolution"]),
        winning_claim_id=payload.get("winning_claim_id"),
    )


def thesis_to_record(thesis: Thesis) -> dict[str, Any]:
    return {
        "thesis_id": thesis.thesis_id,
        "object_id": thesis.object_id,
        "thesis_type": thesis.thesis_type.value,
        "title": thesis.title,
        "direction": thesis.direction.value,
        "scope": thesis.scope,
        "time_horizon": thesis.time_horizon.value,
        "anchor_claim_ids": list(thesis.anchor_claim_ids),
        "supporting_claim_ids": list(thesis.supporting_claim_ids),
        "status": thesis.status.value,
        "confidence": thesis.confidence,
        "conflict_severity": thesis.conflict_severity.value,
        "invalidation_rules": list(thesis.invalidation_rules),
        "working_primary_streak": thesis.working_primary_streak,
    }


def thesis_from_record(payload: dict[str, Any]) -> Thesis:
    return Thesis(
        thesis_id=str(payload["thesis_id"]),
        object_id=str(payload["object_id"]),
        thesis_type=ThesisType(payload["thesis_type"]),
        title=str(payload["title"]),
        direction=Direction(payload["direction"]),
        scope=str(payload["scope"]),
        time_horizon=TimeHorizon(payload["time_horizon"]),
        anchor_claim_ids=[str(item) for item in payload.get("anchor_claim_ids", [])],
        supporting_claim_ids=[str(item) for item in payload.get("supporting_claim_ids", [])],
        status=ThesisStatus(payload.get("status", ThesisStatus.DRAFT.value)),
        confidence=int(payload.get("confidence", 0)),
        conflict_severity=ConflictSeverity(payload.get("conflict_severity", ConflictSeverity.CLEAN.value)),
        invalidation_rules=[str(item) for item in payload.get("invalidation_rules", [])],
        working_primary_streak=int(payload.get("working_primary_streak", 0)),
    )


def publish_decision_to_record(decision: PublishDecision) -> dict[str, Any]:
    return {
        "decision": decision.decision,
        "reasons": list(decision.reasons),
    }


def publish_decision_from_record(payload: dict[str, Any]) -> PublishDecision:
    return PublishDecision(
        decision=str(payload["decision"]),
        reasons=[str(item) for item in payload.get("reasons", [])],
    )


def cadence_plan_to_record(plan: CadencePlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "normal_review_after_seconds": None
        if plan.normal_review_after is None
        else plan.normal_review_after.total_seconds(),
        "deep_review_after_seconds": None
        if plan.deep_review_after is None
        else plan.deep_review_after.total_seconds(),
    }


def cadence_plan_from_record(payload: dict[str, Any]) -> CadencePlan:
    normal_seconds = payload.get("normal_review_after_seconds")
    deep_seconds = payload.get("deep_review_after_seconds")
    return CadencePlan(
        mode=str(payload["mode"]),
        normal_review_after=None if normal_seconds is None else timedelta(seconds=float(normal_seconds)),
        deep_review_after=None if deep_seconds is None else timedelta(seconds=float(deep_seconds)),
    )


def resource_allocation_to_record(allocation: ResourceAllocation) -> dict[str, Any]:
    return {
        "object_id": allocation.object_id,
        "tier": allocation.tier.value,
        "slot_type": allocation.slot_type.value,
    }


def resource_allocation_from_record(payload: dict[str, Any]) -> ResourceAllocation:
    return ResourceAllocation(
        object_id=str(payload["object_id"]),
        tier=ResourceTier(payload["tier"]),
        slot_type=SlotType(payload["slot_type"]),
    )


def _step_to_record(step: Any) -> dict[str, Any]:
    details = getattr(step, "details", {})
    if not isinstance(details, dict):
        details = {}
    return {
        "cycle": int(getattr(step, "cycle", 0)),
        "step": str(getattr(step, "step", "")),
        "status": str(getattr(step, "status", "")),
        "processing_state_before": str(getattr(step, "processing_state_before", "")),
        "processing_state_after": str(getattr(step, "processing_state_after", "")),
        "details": details,
    }


def step_from_record(payload: dict[str, Any]) -> Any:
    return dict(payload)
