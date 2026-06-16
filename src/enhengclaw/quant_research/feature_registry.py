from __future__ import annotations

from typing import Any


FEATURE_REGISTRY_CONTRACT_VERSION = "quant_feature_registry.v1"


def build_feature_registry_section(
    *,
    strategy_entry: dict[str, Any] | None,
    selected_feature_columns: list[str] | None,
) -> dict[str, Any]:
    resolved_strategy_entry = dict(strategy_entry or {})
    thesis_profile = dict(resolved_strategy_entry.get("thesis_profile") or {})
    required_feature_columns = [
        str(item).strip()
        for item in list(thesis_profile.get("required_feature_columns") or [])
        if str(item).strip()
    ]
    seen_required: set[str] = set()
    deduped_required_feature_columns: list[str] = []
    for column in required_feature_columns:
        if column in seen_required:
            continue
        seen_required.add(column)
        deduped_required_feature_columns.append(column)

    selected = [
        str(item).strip()
        for item in list(selected_feature_columns or [])
        if str(item).strip()
    ]
    selected_set = set(selected)
    missing_required_feature_columns = [
        column for column in deduped_required_feature_columns if column not in selected_set
    ]
    return {
        "contract_version": FEATURE_REGISTRY_CONTRACT_VERSION,
        "thesis_id": str(
            thesis_profile.get("thesis_id")
            or resolved_strategy_entry.get("strategy_id")
            or ""
        ).strip(),
        "required_feature_columns": deduped_required_feature_columns,
        "selected_feature_columns": selected,
        "missing_required_feature_columns": missing_required_feature_columns,
        "passed": not missing_required_feature_columns,
    }
