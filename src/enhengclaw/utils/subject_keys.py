"""Backward-compatible shim for the SubjectKey identity module."""

from enhengclaw.domain.identity.subject_key import (
    _FRAGMENT_PATTERN,
    _SUBJECT_KEY_PATTERN,
    SubjectKey,
    ensure_subject_key_matches,
    ensure_subject_symbol_matches,
    iter_subject_key_paths,
    normalize_subject_fragment,
    parse_subject_key_fragment,
    subject_key_hourly_jsonl_path,
    subject_key_path,
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
