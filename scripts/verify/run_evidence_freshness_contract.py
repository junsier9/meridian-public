from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import current_source_commit_sha, utc_now_iso


DEFAULT_CONTRACT_PATH = ROOT / "config" / "agent_layer_governance" / "evidence_freshness_contract.json"
DEFAULT_PROJECT_STATE_PATH = ROOT / "PROJECT_STATE.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate freshness for the accepted evidence referenced by PROJECT_STATE.md.")
    parser.add_argument("--project-state", type=Path, default=DEFAULT_PROJECT_STATE_PATH)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--current-commit-sha", default=None)
    parser.add_argument("--now-utc", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = evaluate_project_state_evidence_freshness(
        project_state_path=args.project_state,
        contract_path=args.contract,
        current_commit_sha=args.current_commit_sha,
        now_utc=args.now_utc,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "passed" else 1


def evaluate_project_state_evidence_freshness(
    *,
    project_state_path: Path = DEFAULT_PROJECT_STATE_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    current_commit_sha: str | None = None,
    now_utc: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    current_sha = (current_commit_sha or current_source_commit_sha(repo_root=ROOT) or "").strip() or None
    now_value = _parse_utc(now_utc) if now_utc else datetime.now(UTC)
    references = extract_project_state_evidence_references(Path(project_state_path))

    results = [
        evaluate_evidence_reference(
            reference,
            contract=contract,
            current_commit_sha=current_sha,
            now_utc=now_value,
            env=env,
        )
        for reference in references
    ]
    status = "passed" if current_sha and results and all(item["status"] == "passed" for item in results) else "failed"
    blockers: list[str] = []
    if current_sha is None:
        blockers.append("current commit SHA is unavailable")
    if not results:
        blockers.append("PROJECT_STATE.md does not reference any accepted evidence paths")
    for item in results:
        blockers.extend(item["blockers"])
    return {
        "generated_at_utc": utc_now_iso(),
        "project_state_path": str(Path(project_state_path).resolve()),
        "contract_path": str(Path(contract_path).resolve()),
        "current_commit_sha": current_sha,
        "status": status,
        "references": results,
        "blockers": blockers,
    }


def extract_project_state_evidence_references(project_state_path: Path) -> list[str]:
    text = Path(project_state_path).read_text(encoding="utf-8")
    section = _section_body(text, "## Current Accepted Evidence")
    references: list[str] = []
    for line in section.splitlines():
        for match in re.findall(r"`([^`]+)`", line):
            references.append(match)
    return references


def evaluate_evidence_reference(
    reference: str,
    *,
    contract: dict[str, Any],
    current_commit_sha: str | None,
    now_utc: datetime,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    expanded_text = expand_percent_env_vars(reference, env=env)
    family = classify_evidence_family(expanded_text)
    candidate_path = resolve_metadata_candidate_path(expanded_text, family)
    blockers: list[str] = []
    metadata: dict[str, Any] | None = None
    config = None if family is None else dict(contract.get("families", {}).get(family, {}))
    age_hours = None

    if family is None:
        blockers.append(f"unrecognized evidence family for reference: {reference}")
    elif config is None or not config:
        blockers.append(f"no freshness contract configured for evidence family: {family}")

    if not candidate_path.exists():
        blockers.append(f"evidence path does not exist: {candidate_path}")
    else:
        try:
            metadata = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            blockers.append(f"unable to read evidence metadata: {candidate_path} ({exc})")

    if isinstance(metadata, dict):
        produced_at = _parse_utc(metadata.get("produced_at_utc"))
        if produced_at is None:
            blockers.append("produced_at_utc is missing or invalid")
        else:
            age_hours = round((now_utc - produced_at).total_seconds() / 3600.0, 3)
            max_age_hours = float(config.get("max_age_hours", 0)) if config else 0.0
            if age_hours > max_age_hours:
                blockers.append(
                    f"evidence is stale for {family}: age_hours={age_hours} > max_age_hours={max_age_hours}"
                )
        if family is not None and metadata.get("evidence_family") != family:
            blockers.append(
                f"evidence_family mismatch for {candidate_path}: expected {family}, got {metadata.get('evidence_family')!r}"
            )
        source_commit_sha = metadata.get("source_commit_sha")
        if config and bool(config.get("require_current_commit_match")):
            if not current_commit_sha:
                blockers.append("current commit SHA is unavailable")
            elif not source_commit_sha:
                blockers.append(f"source_commit_sha missing for {candidate_path}")
            elif str(source_commit_sha) != current_commit_sha:
                blockers.append(
                    f"source_commit_sha mismatch for {candidate_path}: expected {current_commit_sha}, got {source_commit_sha}"
                )

    return {
        "reference": reference,
        "expanded_reference": expanded_text,
        "resolved_metadata_path": str(candidate_path),
        "evidence_family": family,
        "age_hours": age_hours,
        "status": "passed" if not blockers else "failed",
        "blockers": blockers,
    }


def expand_percent_env_vars(value: str, *, env: dict[str, str] | None = None) -> str:
    source = os.environ if env is None else env

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(source.get(name, match.group(0)))

    return re.sub(r"%([^%]+)%", _replace, value)


def classify_evidence_family(path_text: str) -> str | None:
    normalized = path_text.replace("/", "\\").lower()
    if normalized.endswith("\\bundle_summary.json") and "openclaw_live_market_observer\\retained" in normalized:
        return "openclaw_deployment_gate"
    if normalized.endswith("\\verify_summary.json") and "real_shadow_acceptance\\verify_runs" in normalized:
        return "real_shadow_verify"
    if normalized.endswith("\\preflight_assertions.json") and "\\preflight_only\\" in normalized:
        return "real_24h_preflight"
    if normalized.endswith("\\bundle_summary.json") and "\\real_24h_bundles\\" in normalized:
        return "real_24h_bundle"
    if normalized.endswith("\\operational_readiness_summary.json"):
        return "operational_readiness"
    if normalized.endswith("\\broad_unlock_evaluation.json") or normalized.endswith("\\broad_readiness_summary.json"):
        return "broad_agent_layer_readiness"
    return None


def resolve_metadata_candidate_path(path_text: str, family: str | None) -> Path:
    candidate = Path(path_text.replace("\\", os.sep).replace("/", os.sep))
    if candidate.is_dir():
        if family == "real_24h_preflight":
            return candidate / "preflight_assertions.json"
        if family in {"real_24h_bundle", "openclaw_deployment_gate"}:
            return candidate / "bundle_summary.json"
        if family == "real_shadow_verify":
            return candidate / "verify_summary.json"
        if family == "operational_readiness":
            return candidate / "operational_readiness_summary.json"
        if family == "broad_agent_layer_readiness":
            return candidate / "broad_unlock_evaluation.json"
    return candidate


def _section_body(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    tail = text[start + len(heading) :]
    next_heading = re.search(r"^##\s+", tail, flags=re.MULTILINE)
    if next_heading is None:
        return tail
    return tail[: next_heading.start()]


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
