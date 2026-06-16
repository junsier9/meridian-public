from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


QUANT_DATASET_MANIFEST_CONTRACT_VERSION = "quant_dataset_manifest.v2"
QUANT_FEATURE_MANIFEST_CONTRACT_VERSION = "quant_feature_manifest.v2"
QUANT_REPRODUCIBILITY_CONTRACT_VERSION = "quant_reproducibility_contract.v1"
QUANT_DATASET_MANIFEST_ARTIFACT_FAMILY = "quant_dataset_manifest"
QUANT_FEATURE_MANIFEST_ARTIFACT_FAMILY = "quant_feature_manifest"
REPRODUCIBILITY_REQUIRED_FIELDS = (
    "source_commit_sha",
    "dataset_fingerprint",
    "feature_hash",
    "dataset_manifest_path",
    "feature_manifest_path",
)


def sha256_canonical_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_dataframe_csv(frame: pd.DataFrame) -> str:
    csv_payload = frame.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(csv_payload.encode("utf-8")).hexdigest()


def build_dataset_fingerprint(
    *,
    dataset_id: str,
    shape: str,
    primary_interval: str,
    row_count: int,
    subjects: list[str],
    min_timestamp_utc: str | None,
    max_timestamp_utc: str | None,
    columns: list[str],
    dataset_panel_sha256: str,
) -> str:
    return sha256_canonical_json(
        {
            "dataset_id": str(dataset_id),
            "shape": str(shape),
            "primary_interval": str(primary_interval),
            "row_count": int(row_count),
            "subjects": [str(item) for item in subjects],
            "min_timestamp_utc": min_timestamp_utc,
            "max_timestamp_utc": max_timestamp_utc,
            "columns": [str(item) for item in columns],
            "dataset_panel_sha256": str(dataset_panel_sha256),
        }
    )


def build_feature_hash(
    *,
    feature_set_id: str,
    dataset_id: str,
    shape: str,
    row_count: int,
    numeric_feature_columns: list[str],
    excluded_numeric_columns: list[str],
    feature_admission_policy_contract_version: str,
    split_realization_contract: dict[str, Any],
    feature_matrix_sha256: str,
) -> str:
    return sha256_canonical_json(
        {
            "feature_set_id": str(feature_set_id),
            "dataset_id": str(dataset_id),
            "shape": str(shape),
            "row_count": int(row_count),
            "numeric_feature_columns": [str(item) for item in numeric_feature_columns],
            "excluded_numeric_columns": [str(item) for item in excluded_numeric_columns],
            "feature_admission_policy_contract_version": str(feature_admission_policy_contract_version),
            "split_realization_contract": dict(split_realization_contract or {}),
            "feature_matrix_sha256": str(feature_matrix_sha256),
        }
    )


def build_reproducibility_section(
    *,
    source_commit_sha: str | None,
    dataset_fingerprint: str | None,
    feature_hash: str | None,
    dataset_manifest_path: str | None,
    feature_manifest_path: str | None,
) -> dict[str, Any]:
    payload = {
        "contract_version": QUANT_REPRODUCIBILITY_CONTRACT_VERSION,
        "source_commit_sha": str(source_commit_sha or "").strip(),
        "dataset_fingerprint": str(dataset_fingerprint or "").strip(),
        "feature_hash": str(feature_hash or "").strip(),
        "dataset_manifest_path": str(dataset_manifest_path or "").strip(),
        "feature_manifest_path": str(feature_manifest_path or "").strip(),
    }
    missing_fields = [
        field_name
        for field_name in REPRODUCIBILITY_REQUIRED_FIELDS
        if not str(payload.get(field_name) or "").strip()
    ]
    payload["missing_fields"] = missing_fields
    payload["passed"] = not missing_fields
    return payload


def apply_reproducibility_fields(payload: dict[str, Any], reproducibility: dict[str, Any] | None) -> dict[str, Any]:
    section = dict(reproducibility or {})
    decorated = dict(payload)
    decorated["source_commit_sha"] = str(section.get("source_commit_sha") or "").strip() or None
    decorated["dataset_fingerprint"] = str(section.get("dataset_fingerprint") or "").strip() or None
    decorated["feature_hash"] = str(section.get("feature_hash") or "").strip() or None
    decorated["dataset_manifest_path"] = str(section.get("dataset_manifest_path") or "").strip() or None
    decorated["feature_manifest_path"] = str(section.get("feature_manifest_path") or "").strip() or None
    decorated["reproducibility"] = section
    return decorated


def resolve_reproducibility_tuple(payload: dict[str, Any] | None) -> tuple[str, str, str, str, str]:
    resolved = dict(payload or {})
    return (
        str(resolved.get("source_commit_sha") or "").strip(),
        str(resolved.get("dataset_fingerprint") or "").strip(),
        str(resolved.get("feature_hash") or "").strip(),
        str(resolved.get("dataset_manifest_path") or "").strip(),
        str(resolved.get("feature_manifest_path") or "").strip(),
    )


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
