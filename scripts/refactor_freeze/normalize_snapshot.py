from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TIMESTAMP_IGNORE_FIELDS = {
    "$.generated_at_utc",
    "$.recorded_at",
    "$.blocked_at_utc",
}

PATH_RELATIVE_FIELDS = {
    "$.path",
    "$.output_root",
    "$.json_path",
    "$.markdown_path",
    "$.archive_path",
    "$.run_root",
    "$.raw_payload_dir",
    "$.provider_selection_result",
    "$.normalized_signal_summary",
    "$.runtime_result",
    "$.ops_report",
    "$.warnings_errors",
    "$.batch_root",
    "$.batch_summary_path",
    "$.corpus_root",
    "$.manifest_path",
}

PATH_RELATIVE_LIST_FIELDS = {
    "$.replay_log_paths",
    "$.quarantine_paths",
    "$.raw_payload_record_paths",
}

ORDER_SORT_FIELDS = {
    "$.allowed_provider_names",
    "$.rejected_provider_names",
    "$.default_runtime_provider_names",
    "$.shadow_provider_names",
    "$.provider_selection_modes_available",
}

ALLOWED_OPERATIONS = {"PATH_RELATIVE", "TIMESTAMP_IGNORE", "ORDER_SORT"}
TIMESTAMP_SENTINEL = "__IGNORED_TIMESTAMP__"


def normalize_snapshot(snapshot: Any, *, repo_root: Path) -> tuple[Any, list[str]]:
    normalized, operations = _normalize_node(snapshot, path="$", repo_root=repo_root)
    deduped = sorted(set(operations))
    invalid = [operation for operation in deduped if operation not in ALLOWED_OPERATIONS]
    if invalid:
        raise ValueError(f"non-whitelisted normalization requested: {invalid}")
    return normalized, deduped


def _normalize_node(value: Any, *, path: str, repo_root: Path) -> tuple[Any, list[str]]:
    operations: list[str] = []

    if path in TIMESTAMP_IGNORE_FIELDS:
        return TIMESTAMP_SENTINEL, ["TIMESTAMP_IGNORE"]

    if path in PATH_RELATIVE_FIELDS and isinstance(value, str):
        return _relative_path(value, repo_root), ["PATH_RELATIVE"]

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value.keys()):
            child_value, child_ops = _normalize_node(
                value[key],
                path=f"{path}.{key}",
                repo_root=repo_root,
            )
            operations.extend(child_ops)
            normalized[key] = child_value
        return normalized, operations

    if isinstance(value, list):
        normalized_items: list[Any] = []
        for index, item in enumerate(value):
            child_value, child_ops = _normalize_node(
                item,
                path=f"{path}[{index}]",
                repo_root=repo_root,
            )
            operations.extend(child_ops)
            normalized_items.append(child_value)
        if path in PATH_RELATIVE_LIST_FIELDS:
            normalized_items = [
                _relative_path(item, repo_root) if isinstance(item, str) else item
                for item in normalized_items
            ]
            operations.append("PATH_RELATIVE")
        if path in ORDER_SORT_FIELDS:
            normalized_items = sorted(
                normalized_items,
                key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True),
            )
            operations.append("ORDER_SORT")
        return normalized_items, operations

    return value, operations


def _relative_path(value: str, repo_root: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        return value.replace("\\", "/")
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
        return relative.as_posix()
    except ValueError:
        return path.as_posix()
