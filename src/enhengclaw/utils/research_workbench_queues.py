from __future__ import annotations

from pathlib import Path


STRUCTURAL_QUEUE = "structural"
QUANT_QUEUE = "quant"
LEGACY_QUEUE = "legacy"
KNOWN_QUEUE_SOURCES = (STRUCTURAL_QUEUE, QUANT_QUEUE, LEGACY_QUEUE)

_QUEUE_DIR_NAMES = {
    STRUCTURAL_QUEUE: "_incoming_structural",
    QUANT_QUEUE: "_incoming_quant",
    LEGACY_QUEUE: "_incoming",
}


def incoming_queue_root(*, workbench_root: Path, source: str) -> Path:
    normalized = _normalize_source(source)
    return workbench_root / _QUEUE_DIR_NAMES[normalized]


def consumed_archive_root(*, workbench_root: Path, source: str) -> Path:
    normalized = _normalize_source(source)
    return workbench_root / "_incoming_archive" / "consumed" / normalized


def known_incoming_roots(*, workbench_root: Path) -> dict[str, Path]:
    return {
        source: incoming_queue_root(workbench_root=workbench_root, source=source)
        for source in KNOWN_QUEUE_SOURCES
    }


def all_pending_snapshot_roots(*, workbench_root: Path) -> tuple[Path, ...]:
    return tuple(known_incoming_roots(workbench_root=workbench_root).values())


def _normalize_source(source: str) -> str:
    normalized = str(source).strip().lower()
    if normalized not in _QUEUE_DIR_NAMES:
        raise ValueError(f"unsupported research workbench queue source: {source}")
    return normalized
