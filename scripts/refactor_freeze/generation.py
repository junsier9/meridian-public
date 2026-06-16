from __future__ import annotations

from contextlib import nullcontext
import os
from pathlib import Path

from .common import GENERATOR_VERSION, freeze_phase_root, git_ref, utc_now_iso, write_json
from .models import SnapshotEnvelope, SnapshotMeta
from .snapshot_cases import snapshot_definitions
from enhengclaw.core.execution_control import WORKER_MODE_ENV
from enhengclaw.testing import runtime_worker_harness


def generate_snapshots(
    *,
    kind: str,
    phase: str,
    snapshot_types: set[str] | None = None,
    freeze_root: Path | None = None,
) -> dict[str, object]:
    output_root = freeze_phase_root(kind=kind, phase=phase, freeze_root=freeze_root)
    definitions = snapshot_definitions(snapshot_types)
    generated_files: list[str] = []
    generated_at_utc = utc_now_iso()
    source_ref = git_ref()

    context = (
        nullcontext()
        if os.getenv(WORKER_MODE_ENV) == "1"
        else runtime_worker_harness(slug=f"refactor-freeze-{kind}-{phase}")
    )
    with context:
        for definition in definitions:
            envelope = SnapshotEnvelope(
                snapshot_meta=SnapshotMeta(
                    snapshot_type=definition.snapshot_type,
                    case_id=definition.case_id,
                    phase=phase,
                    generated_at_utc=generated_at_utc,
                    source_commit_or_worktree_ref=source_ref,
                    generator_version=GENERATOR_VERSION,
                ),
                snapshot=definition.generate(),
            )
            target_path = output_root / definition.file_name
            write_json(target_path, envelope)
            generated_files.append(definition.file_name)

    manifest = {
        "phase": phase,
        "kind": kind,
        "generated_at_utc": generated_at_utc,
        "source_commit_or_worktree_ref": source_ref,
        "snapshot_count": len(generated_files),
        "snapshot_types": sorted({definition.snapshot_type for definition in definitions}),
        "generated_files": generated_files,
    }
    write_json(output_root / "generation_manifest.json", manifest)
    return {
        "output_root": str(output_root),
        "manifest_path": str(output_root / "generation_manifest.json"),
        "snapshot_count": len(generated_files),
        "generated_files": generated_files,
    }
