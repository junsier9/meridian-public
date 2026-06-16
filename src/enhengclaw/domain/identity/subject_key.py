from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Iterable


_FRAGMENT_PATTERN = re.compile(r"[^a-z0-9]+")
_SUBJECT_KEY_PATTERN = re.compile(
    r"^symbol=(?P<symbol>.+)__venue=(?P<venue>.+)__instrument_type=(?P<instrument_type>.+)$"
)


def normalize_subject_fragment(value: object, *, fallback: str = "unknown") -> str:
    text = "" if value is None else str(value).strip().lower()
    if not text:
        return fallback
    normalized = _FRAGMENT_PATTERN.sub("_", text).strip("_")
    return normalized or fallback


@dataclass(frozen=True, slots=True)
class SubjectKey:
    symbol: str
    venue: str
    instrument_type: str

    @classmethod
    def build(
        cls,
        *,
        symbol: object,
        venue: object,
        instrument_type: object,
    ) -> SubjectKey:
        return cls(
            symbol=normalize_subject_fragment(symbol),
            venue=normalize_subject_fragment(venue),
            instrument_type=normalize_subject_fragment(instrument_type),
        )

    @classmethod
    def from_request(
        cls,
        request: object,
        *,
        default_venue: str,
        default_instrument_type: str,
    ) -> SubjectKey:
        return cls.build(
            symbol=getattr(request, "subject"),
            venue=getattr(request, "venue", None) or default_venue,
            instrument_type=getattr(request, "instrument_type", None) or default_instrument_type,
        )

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.symbol, self.venue, self.instrument_type)

    def as_stable_string(self) -> str:
        return f"{self.symbol.upper()}.{self.venue.lower()}.{self.instrument_type.lower()}"

    def as_path_fragment(self) -> str:
        return (
            f"symbol={self.symbol}"
            f"__venue={self.venue}"
            f"__instrument_type={self.instrument_type}"
        )


def parse_subject_key_fragment(fragment: object) -> SubjectKey | None:
    if not isinstance(fragment, str):
        return None
    match = _SUBJECT_KEY_PATTERN.match(fragment)
    if match is None:
        return None
    return SubjectKey.build(
        symbol=match.group("symbol"),
        venue=match.group("venue"),
        instrument_type=match.group("instrument_type"),
    )


def subject_key_path(root: Path, scenario: str, subject_key: SubjectKey, file_name: str) -> Path:
    return root / scenario / subject_key.as_path_fragment() / file_name


def subject_key_hourly_jsonl_path(root: Path, subject_key: SubjectKey, timestamp: datetime) -> Path:
    utc_timestamp = timestamp.astimezone(timezone.utc)
    return (
        root
        / subject_key.as_stable_string()
        / utc_timestamp.strftime("%Y-%m-%d")
        / f"{utc_timestamp.strftime('%H')}.jsonl"
    )


def iter_subject_key_paths(root: Path, scenario: str, file_name: str) -> Iterable[tuple[SubjectKey, Path]]:
    scenario_root = root / scenario
    if not scenario_root.exists():
        return []
    matches: list[tuple[SubjectKey, Path]] = []
    for child in scenario_root.iterdir():
        if not child.is_dir():
            continue
        subject_key = parse_subject_key_fragment(child.name)
        if subject_key is None:
            continue
        candidate = child / file_name
        if candidate.exists():
            matches.append((subject_key, candidate))
    return matches


def ensure_subject_symbol_matches(
    expected_subject: object,
    observed_subject: object,
    *,
    context: str,
) -> None:
    expected = normalize_subject_fragment(expected_subject)
    observed = normalize_subject_fragment(observed_subject)
    if expected != observed:
        raise ValueError(
            f"{context} subject mismatch: expected '{expected}', observed '{observed}'"
        )


def ensure_subject_key_matches(
    expected_subject_key: SubjectKey,
    observed_subject_key: SubjectKey,
    *,
    context: str,
) -> None:
    if expected_subject_key != observed_subject_key:
        raise ValueError(
            f"{context} subject_key mismatch: "
            f"expected '{expected_subject_key.as_stable_string()}', "
            f"observed '{observed_subject_key.as_stable_string()}'"
        )


__all__ = [
    "SubjectKey",
    "ensure_subject_key_matches",
    "ensure_subject_symbol_matches",
    "iter_subject_key_paths",
    "normalize_subject_fragment",
    "parse_subject_key_fragment",
    "subject_key_hourly_jsonl_path",
    "subject_key_path",
]
