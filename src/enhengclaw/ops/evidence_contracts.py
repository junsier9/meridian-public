from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import subprocess
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def current_source_commit_sha(*, repo_root: Path | None = None) -> str | None:
    github_sha = str(os.getenv("GITHUB_SHA", "")).strip()
    if github_sha:
        return github_sha

    source_sha = str(os.getenv("SOURCE_COMMIT_SHA", "")).strip()
    if source_sha:
        return source_sha

    resolved_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        cwd=resolved_root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    candidate = (completed.stdout or "").strip()
    return candidate or None


def required_source_commit_sha(*, repo_root: Path | None = None) -> str:
    candidate = current_source_commit_sha(repo_root=repo_root)
    if candidate:
        return candidate
    raise RuntimeError(
        "source_commit_sha is required but no Git commit or SOURCE_COMMIT_SHA/GITHUB_SHA override was available"
    )


def with_evidence_metadata(
    payload: dict[str, Any],
    *,
    evidence_family: str,
    contract_version: str,
    repo_root: Path | None = None,
    produced_at_utc: str | None = None,
    source_commit_sha: str | None = None,
    require_source_commit_sha: bool = False,
) -> dict[str, Any]:
    decorated = dict(payload)
    decorated["produced_at_utc"] = (
        produced_at_utc
        or str(
            decorated.get("produced_at_utc")
            or decorated.get("generated_at_utc")
            or decorated.get("evaluated_at_utc")
            or utc_now_iso()
        )
    )
    resolved_source_commit_sha = str(source_commit_sha or "").strip()
    if not resolved_source_commit_sha:
        resolved_source_commit_sha = (
            required_source_commit_sha(repo_root=repo_root)
            if require_source_commit_sha
            else str(current_source_commit_sha(repo_root=repo_root) or "").strip()
        )
    decorated["source_commit_sha"] = resolved_source_commit_sha or None
    decorated["evidence_family"] = evidence_family
    decorated["artifact_family"] = str(decorated.get("artifact_family") or evidence_family)
    decorated["contract_version"] = contract_version
    return decorated
