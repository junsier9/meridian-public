from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Iterable

from .contracts import ROOT


EVENT_TAPE_VERSION = "quant_event_tape.v1"
DEFAULT_EVENT_TAPE_ROOT = ROOT / "data" / "quant_research" / "event_tape"

EVENT_SCOPE_SUBJECT = "subject"
EVENT_SCOPE_MARKET = "market"
EVENT_SCOPES = (
    EVENT_SCOPE_SUBJECT,
    EVENT_SCOPE_MARKET,
)

EVENT_CONFIRMATION_OFFICIAL = "official"
EVENT_CONFIRMATION_CONFIRMED = "confirmed"
EVENT_CONFIRMATION_NARRATIVE_ONLY = "narrative_only"
EVENT_CONFIRMATION_LEVELS = (
    EVENT_CONFIRMATION_OFFICIAL,
    EVENT_CONFIRMATION_CONFIRMED,
    EVENT_CONFIRMATION_NARRATIVE_ONLY,
)

EVENT_SOURCE_KINDS = (
    "official_exchange",
    "official_project",
    "regulator",
    "calendar",
    "newswire",
    "social",
    "manual",
)

EVENT_CATEGORIES = (
    "macro",
    "exchange_listing",
    "exchange_delisting",
    "regulatory",
    "security_incident",
    "protocol_upgrade",
    "governance",
    "token_unlock",
    "partnership",
    "airdrop",
    "other",
)


def parse_utc_timestamp(value: Any, *, field_name: str) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    normalized = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def utc_timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value.astimezone(UTC)
    else:
        parsed = parse_utc_timestamp(value, field_name="timestamp")
    return parsed.isoformat().replace("+00:00", "Z")


def normalize_subject(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("subject must be non-empty")
    return normalized


def normalize_optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def normalize_string_list(values: Iterable[Any] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values or ():
        item = str(value or "").strip()
        if item and item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def normalize_subjects(values: Iterable[Any] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values or ():
        item = normalize_subject(value)
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class EventTapeRecord:
    event_id: str
    observed_at_utc: str
    effective_at_utc: str
    scope: str
    category: str
    confirmation_level: str
    source_kind: str
    source_ref: str
    title: str
    subjects: tuple[str, ...]
    narrative_tags: tuple[str, ...]
    metadata: dict[str, Any]

    @property
    def observed_at(self) -> datetime:
        return parse_utc_timestamp(self.observed_at_utc, field_name="observed_at_utc")

    @property
    def effective_at(self) -> datetime:
        return parse_utc_timestamp(self.effective_at_utc, field_name="effective_at_utc")

    def affects_subject(self, subject: str) -> bool:
        normalized = normalize_subject(subject)
        if self.scope == EVENT_SCOPE_MARKET:
            return True
        return normalized in self.subjects

    def is_replay_safe(self, *, as_of_utc: str | datetime) -> bool:
        cutoff = parse_utc_timestamp(as_of_utc, field_name="as_of_utc") if isinstance(as_of_utc, str) else as_of_utc.astimezone(UTC)
        return self.observed_at <= cutoff

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_tape_version": EVENT_TAPE_VERSION,
            "observed_at_utc": self.observed_at_utc,
            "effective_at_utc": self.effective_at_utc,
            "scope": self.scope,
            "category": self.category,
            "confirmation_level": self.confirmation_level,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "title": self.title,
            "subjects": list(self.subjects),
            "narrative_tags": list(self.narrative_tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EventTapeRecord":
        if not isinstance(payload, dict):
            raise ValueError("event tape row must be a JSON object")
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("event_id must be non-empty")
        scope = str(payload.get("scope") or "").strip()
        if scope not in EVENT_SCOPES:
            raise ValueError(f"unsupported event scope: {scope!r}")
        category = str(payload.get("category") or "").strip()
        if category not in EVENT_CATEGORIES:
            raise ValueError(f"unsupported event category: {category!r}")
        confirmation_level = str(payload.get("confirmation_level") or "").strip()
        if confirmation_level not in EVENT_CONFIRMATION_LEVELS:
            raise ValueError(f"unsupported confirmation level: {confirmation_level!r}")
        source_kind = str(payload.get("source_kind") or "").strip()
        if source_kind not in EVENT_SOURCE_KINDS:
            raise ValueError(f"unsupported source kind: {source_kind!r}")
        observed_at = parse_utc_timestamp(payload.get("observed_at_utc"), field_name="observed_at_utc")
        effective_at = parse_utc_timestamp(payload.get("effective_at_utc"), field_name="effective_at_utc")
        if effective_at < observed_at - timedelta(days=30):
            raise ValueError("effective_at_utc is implausibly earlier than observed_at_utc")
        subjects = normalize_subjects(payload.get("subjects"))
        if scope == EVENT_SCOPE_SUBJECT and not subjects:
            raise ValueError("subject-scoped events must include at least one subject")
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("title must be non-empty")
        source_ref = str(payload.get("source_ref") or "").strip()
        if not source_ref:
            raise ValueError("source_ref must be non-empty")
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        narrative_tags = normalize_string_list(payload.get("narrative_tags"))
        if confirmation_level == EVENT_CONFIRMATION_NARRATIVE_ONLY and not narrative_tags:
            raise ValueError("narrative_only events must include at least one narrative tag")
        return cls(
            event_id=event_id,
            observed_at_utc=utc_timestamp(observed_at),
            effective_at_utc=utc_timestamp(effective_at),
            scope=scope,
            category=category,
            confirmation_level=confirmation_level,
            source_kind=source_kind,
            source_ref=source_ref,
            title=title,
            subjects=subjects,
            narrative_tags=narrative_tags,
            metadata={str(key): value for key, value in metadata.items()},
        )


def load_event_tape(path: Path) -> list[EventTapeRecord]:
    rows: list[EventTapeRecord] = []
    if not path.exists():
        return rows
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        rows.append(EventTapeRecord.from_payload(payload))
    return rows


def write_event_tape(path: Path, records: Iterable[EventTapeRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record.to_payload(), sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def replay_safe_records(
    records: Iterable[EventTapeRecord],
    *,
    as_of_utc: str | datetime,
) -> list[EventTapeRecord]:
    return [record for record in records if record.is_replay_safe(as_of_utc=as_of_utc)]


def recent_events_for_subject(
    records: Iterable[EventTapeRecord],
    *,
    subject: str,
    as_of_utc: str | datetime,
    lookback_days: int,
    categories: Iterable[str] | None = None,
    confirmation_levels: Iterable[str] | None = None,
    include_market_scope: bool = True,
) -> list[EventTapeRecord]:
    cutoff = parse_utc_timestamp(as_of_utc, field_name="as_of_utc") if isinstance(as_of_utc, str) else as_of_utc.astimezone(UTC)
    category_filter = set(normalize_string_list(categories))
    confirmation_filter = set(normalize_string_list(confirmation_levels))
    results: list[EventTapeRecord] = []
    for record in replay_safe_records(records, as_of_utc=cutoff):
        if record.observed_at < cutoff - timedelta(days=lookback_days):
            continue
        if not include_market_scope and record.scope == EVENT_SCOPE_MARKET:
            continue
        if not record.affects_subject(subject):
            continue
        if category_filter and record.category not in category_filter:
            continue
        if confirmation_filter and record.confirmation_level not in confirmation_filter:
            continue
        results.append(record)
    return sorted(results, key=lambda item: (item.observed_at_utc, item.event_id))


def has_recent_confirmed_event(
    records: Iterable[EventTapeRecord],
    *,
    subject: str,
    as_of_utc: str | datetime,
    lookback_days: int = 3,
    categories: Iterable[str] | None = None,
    include_market_scope: bool = True,
) -> bool:
    return bool(
        recent_events_for_subject(
            records,
            subject=subject,
            as_of_utc=as_of_utc,
            lookback_days=lookback_days,
            categories=categories,
            confirmation_levels=(EVENT_CONFIRMATION_OFFICIAL, EVENT_CONFIRMATION_CONFIRMED),
            include_market_scope=include_market_scope,
        )
    )


def summarize_event_tape(records: Iterable[EventTapeRecord]) -> dict[str, Any]:
    materialized = list(records)
    category_counts = Counter(record.category for record in materialized)
    confirmation_counts = Counter(record.confirmation_level for record in materialized)
    scope_counts = Counter(record.scope for record in materialized)
    source_kind_counts = Counter(record.source_kind for record in materialized)
    subjects = sorted({subject for record in materialized for subject in record.subjects})
    observed_values = sorted(record.observed_at_utc for record in materialized)
    return {
        "event_tape_version": EVENT_TAPE_VERSION,
        "event_count": len(materialized),
        "subject_count": len(subjects),
        "subjects": subjects,
        "category_counts": dict(sorted(category_counts.items())),
        "confirmation_level_counts": dict(sorted(confirmation_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "source_kind_counts": dict(sorted(source_kind_counts.items())),
        "observed_start_utc": observed_values[0] if observed_values else None,
        "observed_end_utc": observed_values[-1] if observed_values else None,
    }
