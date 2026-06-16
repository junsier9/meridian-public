from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .contracts import portable_path, utc_now, write_json
from .execution_cost_model import load_execution_cost_model, resolve_execution_cost_model
from .features import (
    DEFAULT_LABEL_CONTRACT_ID,
    EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
    EXECUTION_ALIGNED_LABEL_CONTRACT_ID,
    EXECUTION_ALIGNED_TARGET_COLUMN,
    PARTICIPATION_DRIFT_LABEL_CONTRACT_ID,
)
from .reproducibility import sha256_canonical_json, sha256_dataframe_csv


ROOT = Path(__file__).resolve().parents[3]
QUANT_LABEL_MANIFEST_CONTRACT_VERSION = "quant_label_manifest.v1"
QUANT_LABEL_MANIFEST_ARTIFACT_FAMILY = "quant_label_manifest"
NEUTRAL_ZONE_MIN_ABS_RETURN = 0.003
NEUTRAL_ZONE_VOL_MULTIPLIER = 0.25
NEUTRAL_ZONE_VOL_WINDOW = 60
NEUTRAL_ZONE_VOL_MIN_PERIODS = 20


def build_label_artifact(
    *,
    features: pd.DataFrame,
    feature_root: Path,
    feature_set_id: str,
    dataset_id: str,
    shape: str,
    dataset_profile: str,
    label_contract_id: str,
    source_commit_sha: str,
) -> dict[str, Any]:
    feature_root.mkdir(parents=True, exist_ok=True)
    metadata = _base_label_metadata(shape=shape, label_contract_id=label_contract_id)
    if metadata["label_contract_id"] == EXECUTION_ALIGNED_LABEL_CONTRACT_ID:
        cost_adjustment, neutral_zone = _apply_execution_aligned_label_contract(
            features=features,
            dataset_profile=dataset_profile,
            target_column=str(metadata["target_column"]),
            forward_return_column=str(metadata["forward_return_column"]),
        )
        label_columns = [
            "target_forward_return",
            "target_up",
            "target_execution_forward_return_raw",
            "target_execution_roundtrip_cost_proxy",
            "target_execution_neutral_zone_threshold",
            "target_execution_is_neutral",
            "target_execution_class",
            EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
            EXECUTION_ALIGNED_TARGET_COLUMN,
        ]
        metadata["label_columns"] = label_columns
        metadata["raw_forward_return_column"] = "target_execution_forward_return_raw"
        metadata["cost_adjustment"] = cost_adjustment
        metadata["neutral_zone"] = neutral_zone
    else:
        label_columns = list(metadata["label_columns"])
    labels = _label_frame(
        features=features,
        label_columns=label_columns,
    )
    labels_path = feature_root / "labels.csv.gz"
    labels.to_csv(labels_path, index=False, compression="gzip")
    label_frame_sha256 = sha256_dataframe_csv(labels)
    label_hash = sha256_canonical_json(
        {
            "feature_set_id": str(feature_set_id),
            "dataset_id": str(dataset_id),
            "shape": str(shape),
            "dataset_profile": str(dataset_profile),
            "label_contract_id": str(metadata["label_contract_id"]),
            "row_count": int(len(labels)),
            "label_columns": list(label_columns),
            "label_frame_sha256": label_frame_sha256,
        }
    )
    manifest = with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "feature_set_id": str(feature_set_id),
            "dataset_id": str(dataset_id),
            "shape": str(shape),
            "dataset_profile": str(dataset_profile),
            "label_contract_id": str(metadata["label_contract_id"]),
            "target_column": str(metadata["target_column"]),
            "forward_return_column": str(metadata["forward_return_column"]),
            "raw_forward_return_column": str(metadata["raw_forward_return_column"]),
            "label_columns": list(label_columns),
            "row_count": int(len(labels)),
            "labels_path": portable_path(labels_path, repo_root=ROOT),
            "label_frame_sha256": label_frame_sha256,
            "label_hash": label_hash,
            "neutral_zone": dict(metadata.get("neutral_zone") or {}),
            "cost_adjustment": dict(metadata.get("cost_adjustment") or {}),
        },
        evidence_family=QUANT_LABEL_MANIFEST_ARTIFACT_FAMILY,
        contract_version=QUANT_LABEL_MANIFEST_CONTRACT_VERSION,
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    manifest_path = feature_root / "label_manifest.json"
    write_json(manifest_path, manifest)
    return {
        "label_contract_id": str(metadata["label_contract_id"]),
        "target_column": str(metadata["target_column"]),
        "forward_return_column": str(metadata["forward_return_column"]),
        "raw_forward_return_column": str(metadata["raw_forward_return_column"]),
        "label_columns": list(label_columns),
        "labels_path": str(labels_path),
        "label_manifest_path": str(manifest_path),
        "label_frame_sha256": label_frame_sha256,
        "label_hash": label_hash,
        "neutral_zone": dict(metadata.get("neutral_zone") or {}),
        "cost_adjustment": dict(metadata.get("cost_adjustment") or {}),
    }


def _base_label_metadata(*, shape: str, label_contract_id: str) -> dict[str, Any]:
    resolved = str(label_contract_id or DEFAULT_LABEL_CONTRACT_ID).strip() or DEFAULT_LABEL_CONTRACT_ID
    if resolved == EXECUTION_ALIGNED_LABEL_CONTRACT_ID:
        return {
            "label_contract_id": resolved,
            "target_column": EXECUTION_ALIGNED_TARGET_COLUMN,
            "forward_return_column": EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
            "raw_forward_return_column": EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
            "label_columns": [
                "target_forward_return",
                "target_up",
                EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
                EXECUTION_ALIGNED_TARGET_COLUMN,
            ],
        }
    if resolved == PARTICIPATION_DRIFT_LABEL_CONTRACT_ID:
        return {
            "label_contract_id": resolved,
            "target_column": "target_participation_drift_up",
            "forward_return_column": "target_participation_drift_forward_return",
            "raw_forward_return_column": "target_forward_return",
            "label_columns": [
                "target_forward_return",
                "target_up",
                "target_participation_drift_forward_return",
                "target_participation_drift_up",
            ],
        }
    return {
        "label_contract_id": DEFAULT_LABEL_CONTRACT_ID,
        "target_column": "target_up",
        "forward_return_column": "target_forward_return",
        "raw_forward_return_column": "target_forward_return",
        "label_columns": ["target_forward_return", "target_up"],
    }


def _apply_execution_aligned_label_contract(
    *,
    features: pd.DataFrame,
    dataset_profile: str,
    target_column: str,
    forward_return_column: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if features.empty:
        features["target_execution_forward_return_raw"] = pd.Series(dtype="float64")
        features["target_execution_roundtrip_cost_proxy"] = pd.Series(dtype="float64")
        features["target_execution_neutral_zone_threshold"] = pd.Series(dtype="float64")
        features["target_execution_is_neutral"] = pd.Series(dtype="bool")
        features["target_execution_class"] = pd.Series(dtype="int64")
        return (
            {
                "mode": "roundtrip_fee_spread_proxy",
                "roundtrip_cost_proxy_return": 0.0,
            },
            {
                "mode": "abs_net_return_threshold",
                "min_abs_return": NEUTRAL_ZONE_MIN_ABS_RETURN,
                "vol_multiplier": NEUTRAL_ZONE_VOL_MULTIPLIER,
                "vol_window": NEUTRAL_ZONE_VOL_WINDOW,
                "vol_min_periods": NEUTRAL_ZONE_VOL_MIN_PERIODS,
            },
        )
    raw_forward_return = pd.to_numeric(features[forward_return_column], errors="coerce").astype("float64")
    features["target_execution_forward_return_raw"] = raw_forward_return
    roundtrip_cost_proxy = _roundtrip_cost_proxy_return(dataset_profile=dataset_profile)
    features["target_execution_roundtrip_cost_proxy"] = roundtrip_cost_proxy
    net_forward_return = raw_forward_return - roundtrip_cost_proxy
    features[forward_return_column] = net_forward_return
    sigma_horizon = (
        net_forward_return.groupby(features["subject"]).transform(
            lambda series: series.rolling(
                NEUTRAL_ZONE_VOL_WINDOW,
                min_periods=NEUTRAL_ZONE_VOL_MIN_PERIODS,
            ).std()
        )
        if "subject" in features.columns
        else net_forward_return.rolling(
            NEUTRAL_ZONE_VOL_WINDOW,
            min_periods=NEUTRAL_ZONE_VOL_MIN_PERIODS,
        ).std()
    )
    fallback_sigma = float(sigma_horizon.dropna().median()) if sigma_horizon.notna().any() else 0.02
    threshold = np.maximum(
        NEUTRAL_ZONE_MIN_ABS_RETURN,
        NEUTRAL_ZONE_VOL_MULTIPLIER * sigma_horizon.fillna(fallback_sigma),
    )
    features["target_execution_neutral_zone_threshold"] = threshold.astype("float64")
    neutral_mask = net_forward_return.abs() < threshold
    features["target_execution_is_neutral"] = neutral_mask.astype("bool")
    features["target_execution_class"] = np.where(
        net_forward_return > threshold,
        1,
        np.where(net_forward_return < -threshold, -1, 0),
    ).astype("int64")
    features[target_column] = (net_forward_return > threshold).astype("int64")
    return (
        {
            "mode": "roundtrip_fee_spread_proxy",
            "roundtrip_cost_proxy_return": float(roundtrip_cost_proxy),
        },
        {
            "mode": "abs_net_return_threshold",
            "min_abs_return": NEUTRAL_ZONE_MIN_ABS_RETURN,
            "vol_multiplier": NEUTRAL_ZONE_VOL_MULTIPLIER,
            "vol_window": NEUTRAL_ZONE_VOL_WINDOW,
            "vol_min_periods": NEUTRAL_ZONE_VOL_MIN_PERIODS,
        },
    )


def _roundtrip_cost_proxy_return(*, dataset_profile: str) -> float:
    execution_cost_model = resolve_execution_cost_model(
        contract=load_execution_cost_model(),
        scenario="base",
    )
    venue = "perp" if str(dataset_profile).startswith("cross_sectional") else "spot"
    venue_costs = dict(dict(execution_cost_model.get("venues") or {}).get(venue) or {})
    roundtrip_bps = 2.0 * (
        float(venue_costs.get("fee_bps_one_way", 0.0) or 0.0)
        + float(venue_costs.get("half_spread_bps", 0.0) or 0.0)
    )
    return float(roundtrip_bps / 10_000.0)


def _label_frame(*, features: pd.DataFrame, label_columns: list[str]) -> pd.DataFrame:
    leading_columns = [
        column
        for column in ("timestamp_ms", "timestamp_utc", "subject")
        if column in features.columns
    ]
    available_label_columns = [
        column for column in label_columns if column in features.columns
    ]
    return features[leading_columns + available_label_columns].copy()
