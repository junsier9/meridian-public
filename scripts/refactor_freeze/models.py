from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class SnapshotDefinition:
    snapshot_type: str
    case_id: str
    generate: Callable[[], Any]

    @property
    def file_name(self) -> str:
        return f"{self.snapshot_type}.{self.case_id}.snapshot.json"


@dataclass(frozen=True, slots=True)
class SnapshotMeta:
    snapshot_type: str
    case_id: str
    phase: str
    generated_at_utc: str
    source_commit_or_worktree_ref: str | None
    generator_version: str


@dataclass(frozen=True, slots=True)
class SnapshotEnvelope:
    snapshot_meta: SnapshotMeta
    snapshot: Any


@dataclass(frozen=True, slots=True)
class DiffEntry:
    field: str
    before: Any
    after: Any
    normalization_applied: list[str] = field(default_factory=list)
    is_approved_change: bool = False
    approval_ref: str | None = None
    stopline_triggered: bool = True
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotDiffResult:
    snapshot_type: str
    case_id: str
    baseline_file: str
    candidate_file: str
    diff_count: int
    stopline_triggered: bool
    diffs: list[DiffEntry]


@dataclass(frozen=True, slots=True)
class DiffSummary:
    snapshot_count: int
    snapshot_with_diff_count: int
    total_diff_count: int
    unapproved_diff_count: int
    stopline_triggered: bool
    can_continue: bool
    missing_snapshot_count: int = 0
    invalid_normalization_count: int = 0


@dataclass(frozen=True, slots=True)
class DiffReport:
    phase: str
    generated_at_utc: str
    baseline_root: str
    candidate_root: str
    summary: DiffSummary
    snapshots: list[SnapshotDiffResult]
