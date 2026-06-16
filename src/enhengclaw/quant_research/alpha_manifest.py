from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import (
    pit_universe_artifact_metadata,
    portable_path,
    read_json,
    resolve_portable_path,
    utc_now,
    write_json,
)
from .legacy_surface import raise_legacy_surface_frozen


ROOT = Path(__file__).resolve().parents[3]
DAILY_ALPHA_MANIFEST_CONTRACT_VERSION = "quant_daily_alpha_manifest.v1"
REQUIRED_MANIFEST_ENTRY_FIELDS = (
    "alpha_card_path",
    "as_of",
    "backend_mode",
    "dataset_provenance",
    "experiment_id",
    "strategy_id",
)


def daily_alpha_manifest_root(*, artifacts_root: Path) -> Path:
    return artifacts_root / "governance" / "daily_alpha_manifests"


def daily_alpha_manifest_path(*, artifacts_root: Path, as_of: str) -> Path:
    return daily_alpha_manifest_root(artifacts_root=artifacts_root) / f"{as_of}.json"


def build_daily_alpha_manifest_entry(
    *,
    alpha_card_path: Path,
    alpha_card: dict[str, Any],
) -> dict[str, Any] | None:
    experiment_id = str(alpha_card.get("experiment_id") or "").strip()
    strategy_id = str(alpha_card.get("strategy_id") or "").strip()
    as_of = str(alpha_card.get("as_of") or "").strip()
    if not experiment_id or not strategy_id or not as_of:
        return None
    compiler_backend = str(alpha_card.get("compiler_backend") or "").strip().lower()
    backend_mode = str(alpha_card.get("backend_mode") or "").strip() or ("live" if compiler_backend == "live" else "deterministic")
    universe_metadata = pit_universe_artifact_metadata(alpha_card)
    return {
        "experiment_id": experiment_id,
        "strategy_id": strategy_id,
        "alpha_card_path": portable_path(alpha_card_path, repo_root=ROOT),
        "as_of": as_of,
        "backend_mode": backend_mode,
        "dataset_provenance": str(alpha_card.get("dataset_provenance") or "").strip(),
        "experiment_status": str(alpha_card.get("experiment_status") or "").strip(),
        "shape": str(alpha_card.get("shape") or "").strip(),
        "source": str(alpha_card.get("source") or "").strip(),
        **universe_metadata,
    }


def write_daily_alpha_manifest(
    *,
    artifacts_root: Path,
    as_of: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_entries = sorted(
        _dedupe_manifest_entries([dict(entry) for entry in entries if isinstance(entry, dict)]),
        key=lambda item: (str(item.get("experiment_id") or ""), str(item.get("alpha_card_path") or "")),
    )
    payload = {
        "contract_version": DAILY_ALPHA_MANIFEST_CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "entry_count": len(normalized_entries),
        "entries": normalized_entries,
    }
    path = daily_alpha_manifest_path(artifacts_root=artifacts_root, as_of=as_of)
    write_json(path, payload)
    payload["path"] = str(path)
    return payload


def write_daily_alpha_manifest_from_experiments(
    *,
    artifacts_root: Path,
    as_of: str,
    experiments: list[dict[str, Any]],
) -> dict[str, Any]:
    raise_legacy_surface_frozen(
        operation="daily_alpha_manifest_write",
        as_of=as_of,
        artifacts_root=artifacts_root,
    )
    entries: list[dict[str, Any]] = []
    for experiment in experiments:
        if not isinstance(experiment, dict):
            continue
        alpha_card = experiment.get("alpha_card")
        alpha_card_path = experiment.get("alpha_card_path")
        if not isinstance(alpha_card, dict) or not str(alpha_card_path or "").strip():
            continue
        entry = build_daily_alpha_manifest_entry(
            alpha_card_path=Path(str(alpha_card_path)),
            alpha_card=alpha_card,
        )
        if entry is not None and entry["as_of"] == as_of:
            entries.append(entry)
    return write_daily_alpha_manifest(artifacts_root=artifacts_root, as_of=as_of, entries=entries)


def write_daily_alpha_manifest_from_artifacts(
    *,
    artifacts_root: Path,
    as_of: str,
) -> dict[str, Any]:
    experiments_root = artifacts_root / "experiments"
    entries: list[dict[str, Any]] = []
    for alpha_card_path in sorted(experiments_root.glob("*/alpha_card.json")):
        alpha_card = read_json(alpha_card_path)
        entry = build_daily_alpha_manifest_entry(
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
        )
        if entry is not None and entry["as_of"] == as_of:
            entries.append(entry)
    return write_daily_alpha_manifest(artifacts_root=artifacts_root, as_of=as_of, entries=entries)


def load_daily_alpha_manifest(*, artifacts_root: Path, as_of: str) -> dict[str, Any]:
    path = daily_alpha_manifest_path(artifacts_root=artifacts_root, as_of=as_of)
    if not path.exists():
        raise FileNotFoundError(f"daily alpha manifest not found for as_of={as_of}: {path}")
    payload = read_json(path)
    entries = [dict(item) for item in payload.get("entries", []) if isinstance(item, dict)]
    for entry in entries:
        missing = [field_name for field_name in REQUIRED_MANIFEST_ENTRY_FIELDS if not str(entry.get(field_name) or "").strip()]
        if missing:
            experiment_id = str(entry.get("experiment_id") or "<missing>")
            raise ValueError(
                f"daily alpha manifest entry {experiment_id} is missing required fields: {', '.join(missing)}"
            )
    payload["entries"] = sorted(
        _dedupe_manifest_entries(entries),
        key=lambda item: str(item.get("experiment_id") or ""),
    )
    payload["entry_count"] = len(payload["entries"])
    payload["path"] = str(path)
    return payload


def manifest_entries_by_experiment_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("experiment_id")): dict(entry)
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("experiment_id") or "").strip()
    }


def ignored_legacy_alpha_cards(*, artifacts_root: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    manifest_paths = {
        resolve_portable_path(str(entry.get("alpha_card_path") or ""), repo_root=ROOT)
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("alpha_card_path") or "").strip()
    }
    ignored: list[dict[str, str]] = []
    for alpha_card_path in sorted((artifacts_root / "experiments").glob("*/alpha_card.json")):
        resolved = alpha_card_path.resolve()
        if resolved in manifest_paths:
            continue
        alpha_card = read_json(alpha_card_path)
        if str(alpha_card.get("strategy_id") or "").strip():
            continue
        ignored.append(
            {
                "experiment_id": str(alpha_card.get("experiment_id") or alpha_card_path.parent.name),
                "alpha_card_path": portable_path(alpha_card_path, repo_root=ROOT),
                "reason": "manifest_external_legacy_alpha_card",
            }
        )
    return ignored


def _dedupe_manifest_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        experiment_id = str(entry.get("experiment_id") or "").strip()
        if not experiment_id:
            continue
        current = deduped.get(experiment_id)
        if current is None or _manifest_entry_preference_key(entry) > _manifest_entry_preference_key(current):
            deduped[experiment_id] = dict(entry)
    return list(deduped.values())


def _manifest_entry_preference_key(entry: dict[str, Any]) -> tuple[str, float, str]:
    alpha_card_path = resolve_portable_path(str(entry.get("alpha_card_path") or ""), repo_root=ROOT)
    generated_at_utc = ""
    modified_time = 0.0
    if alpha_card_path.exists():
        try:
            generated_at_utc = str(read_json(alpha_card_path).get("generated_at_utc") or "")
        except Exception:
            generated_at_utc = ""
        try:
            modified_time = float(alpha_card_path.stat().st_mtime)
        except OSError:
            modified_time = 0.0
    return generated_at_utc, modified_time, str(entry.get("alpha_card_path") or "")
