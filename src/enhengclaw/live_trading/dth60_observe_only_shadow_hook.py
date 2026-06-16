from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "hv_balanced_dth60_observe_only_shadow_hook.v1"


@dataclass(frozen=True)
class ObserveOnlyShadowHookConfig:
    enabled: bool = False
    mode: str = "observe_only"
    artifact_sink: str = "proof_artifacts_only"
    output_root: Path | None = None
    candidate_order_authority: str = "disabled"
    candidate_live_order_submission_authorized: bool = False
    execution_target_source: str = "baseline_only"
    candidate_overlay_execution_path: str = "excluded"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_file(path: Path | None) -> dict[str, Any]:
    if not path:
        return {"path": "", "exists": False, "sha256": ""}
    if not path.exists():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(path)}


def path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def path_contains_part(path: Path, part: str) -> bool:
    return part.lower() in [item.lower() for item in path.resolve().parts]


def run_observe_only_shadow_hook(
    *,
    config: ObserveOnlyShadowHookConfig,
    baseline_target_plan_path: Path,
    executor_input_plan_path: Path,
    candidate_shadow_plan_path: Path | None = None,
    supervisor_context: dict[str, Any] | None = None,
    run_id: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    started_at = now or utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    effective_run_id = run_id or started_at.strftime("%Y%m%dT%H%M%SZ")
    baseline_target_plan_path = Path(baseline_target_plan_path)
    executor_input_plan_path = Path(executor_input_plan_path)
    candidate_shadow_plan_path = Path(candidate_shadow_plan_path) if candidate_shadow_plan_path else None
    blockers: list[str] = []

    if config.mode != "observe_only":
        blockers.append("mode_not_observe_only")
    if config.artifact_sink != "proof_artifacts_only":
        blockers.append("artifact_sink_not_proof_artifacts_only")
    if config.candidate_order_authority != "disabled":
        blockers.append("candidate_order_authority_not_disabled")
    if config.candidate_live_order_submission_authorized is not False:
        blockers.append("candidate_live_order_submission_authorized")
    if config.execution_target_source != "baseline_only":
        blockers.append("execution_target_source_not_baseline_only")
    if config.candidate_overlay_execution_path != "excluded":
        blockers.append("candidate_overlay_execution_path_not_excluded")
    if not baseline_target_plan_path.exists():
        blockers.append("baseline_target_plan_missing")
    if not executor_input_plan_path.exists():
        blockers.append("executor_input_plan_missing")

    baseline_before_hash = file_sha256(baseline_target_plan_path) if baseline_target_plan_path.exists() else ""
    executor_before_hash = file_sha256(executor_input_plan_path) if executor_input_plan_path.exists() else ""
    baseline_after_hash = baseline_before_hash
    executor_after_hash = executor_before_hash
    candidate_shadow_hash = ""
    candidate_artifact_paths: list[Path] = []
    proof_root: Path | None = None

    if not config.enabled:
        baseline_after_hash = file_sha256(baseline_target_plan_path) if baseline_target_plan_path.exists() else ""
        executor_after_hash = file_sha256(executor_input_plan_path) if executor_input_plan_path.exists() else ""
        return _summary(
            run_id=effective_run_id,
            started_at=started_at,
            config=config,
            blockers=blockers,
            baseline_target_plan_path=baseline_target_plan_path,
            executor_input_plan_path=executor_input_plan_path,
            candidate_source_path=candidate_shadow_plan_path,
            baseline_before_hash=baseline_before_hash,
            baseline_after_hash=baseline_after_hash,
            executor_before_hash=executor_before_hash,
            executor_after_hash=executor_after_hash,
            candidate_shadow_hash="",
            candidate_artifact_paths=[],
            proof_root=None,
            supervisor_context=supervisor_context or {},
        )

    if config.output_root is None:
        blockers.append("enabled_hook_output_root_missing")
    else:
        proof_root = Path(config.output_root) / "shadow_hook"
        if not path_contains_part(Path(config.output_root), "proof_artifacts"):
            blockers.append("enabled_hook_output_root_not_under_proof_artifacts")
    if candidate_shadow_plan_path is None or not candidate_shadow_plan_path.exists():
        blockers.append("candidate_shadow_plan_missing")
    if executor_before_hash != baseline_before_hash:
        blockers.append("executor_input_plan_hash_not_baseline_before_hook")

    if not blockers and proof_root is not None and candidate_shadow_plan_path is not None:
        proof_root.mkdir(parents=True, exist_ok=True)
        candidate_shadow_output = proof_root / "candidate_shadow_plan.json"
        shutil.copyfile(candidate_shadow_plan_path, candidate_shadow_output)
        candidate_shadow_hash = file_sha256(candidate_shadow_output)
        candidate_artifact_paths.append(candidate_shadow_output)

        context_output = proof_root / "supervisor_context_snapshot.json"
        write_json(
            context_output,
            {
                "contract_version": CONTRACT_VERSION,
                "run_id": effective_run_id,
                "generated_at_utc": iso_z(started_at),
                "context": supervisor_context or {},
                "baseline_target_plan": evidence_file(baseline_target_plan_path),
                "executor_input_plan": evidence_file(executor_input_plan_path),
                "candidate_source_plan": evidence_file(candidate_shadow_plan_path),
            },
        )
        candidate_artifact_paths.append(context_output)

        executor_readback_output = proof_root / "executor_input_readback.json"
        write_json(
            executor_readback_output,
            {
                "contract_version": CONTRACT_VERSION,
                "run_id": effective_run_id,
                "execution_target_source": "baseline_only",
                "executor_input_plan": evidence_file(executor_input_plan_path),
                "baseline_target_plan": evidence_file(baseline_target_plan_path),
                "candidate_shadow_plan": evidence_file(candidate_shadow_output),
                "candidate_plan_referenced_by_executor": False,
            },
        )
        candidate_artifact_paths.append(executor_readback_output)

        manifest_output = proof_root / "manifest.json"
        write_json(
            manifest_output,
            {
                "contract_version": CONTRACT_VERSION,
                "run_id": effective_run_id,
                "mode": config.mode,
                "candidate_order_authority": config.candidate_order_authority,
                "candidate_live_order_submission_authorized": config.candidate_live_order_submission_authorized,
                "execution_target_source": config.execution_target_source,
                "candidate_overlay_execution_path": config.candidate_overlay_execution_path,
                "artifact_sink": config.artifact_sink,
                "candidate_shadow_plan": evidence_file(candidate_shadow_output),
                "executor_input_readback": evidence_file(executor_readback_output),
                "orders_submitted": 0,
                "fill_count": 0,
            },
        )
        candidate_artifact_paths.append(manifest_output)

    baseline_after_hash = file_sha256(baseline_target_plan_path) if baseline_target_plan_path.exists() else ""
    executor_after_hash = file_sha256(executor_input_plan_path) if executor_input_plan_path.exists() else ""
    return _summary(
        run_id=effective_run_id,
        started_at=started_at,
        config=config,
        blockers=blockers,
        baseline_target_plan_path=baseline_target_plan_path,
        executor_input_plan_path=executor_input_plan_path,
        candidate_source_path=candidate_shadow_plan_path,
        baseline_before_hash=baseline_before_hash,
        baseline_after_hash=baseline_after_hash,
        executor_before_hash=executor_before_hash,
        executor_after_hash=executor_after_hash,
        candidate_shadow_hash=candidate_shadow_hash,
        candidate_artifact_paths=candidate_artifact_paths,
        proof_root=proof_root,
        supervisor_context=supervisor_context or {},
    )


def _summary(
    *,
    run_id: str,
    started_at: datetime,
    config: ObserveOnlyShadowHookConfig,
    blockers: list[str],
    baseline_target_plan_path: Path,
    executor_input_plan_path: Path,
    candidate_source_path: Path | None,
    baseline_before_hash: str,
    baseline_after_hash: str,
    executor_before_hash: str,
    executor_after_hash: str,
    candidate_shadow_hash: str,
    candidate_artifact_paths: list[Path],
    proof_root: Path | None,
    supervisor_context: dict[str, Any],
) -> dict[str, Any]:
    candidate_artifacts_under_proof = (
        not candidate_artifact_paths
        if not config.enabled
        else bool(proof_root)
        and bool(candidate_artifact_paths)
        and all(path_under(path, proof_root.parent) for path in candidate_artifact_paths)
    )
    baseline_byte_for_byte_unchanged = bool(baseline_before_hash) and baseline_before_hash == baseline_after_hash
    executor_hash_unchanged = bool(executor_before_hash) and executor_before_hash == executor_after_hash
    executor_input_plan_hash_equals_baseline = bool(executor_after_hash) and executor_after_hash == baseline_after_hash
    executor_consumes_baseline_only = (
        baseline_byte_for_byte_unchanged
        and executor_hash_unchanged
        and executor_input_plan_hash_equals_baseline
        and (not candidate_shadow_hash or candidate_shadow_hash != executor_after_hash)
    )
    gates = {
        "mode_observe_only": config.mode == "observe_only",
        "artifact_sink_proof_artifacts_only": config.artifact_sink == "proof_artifacts_only",
        "candidate_order_authority_disabled": config.candidate_order_authority == "disabled",
        "candidate_live_order_submission_authorized_false": config.candidate_live_order_submission_authorized is False,
        "execution_target_source_baseline_only": config.execution_target_source == "baseline_only",
        "candidate_overlay_execution_path_excluded": config.candidate_overlay_execution_path == "excluded",
        "baseline_target_plan_exists": baseline_target_plan_path.exists(),
        "executor_input_plan_exists": executor_input_plan_path.exists(),
        "baseline_target_plan_byte_for_byte_unchanged": baseline_byte_for_byte_unchanged,
        "executor_input_plan_hash_unchanged": executor_hash_unchanged,
        "executor_input_plan_hash_equals_baseline": executor_input_plan_hash_equals_baseline,
        "executor_consumes_baseline_only": executor_consumes_baseline_only,
        "candidate_artifacts_under_proof_artifacts_only": candidate_artifacts_under_proof,
        "candidate_orders_submitted_zero": True,
        "candidate_fill_count_zero": True,
    }
    if config.enabled:
        gates["enabled_hook_output_root_under_proof_artifacts"] = bool(config.output_root) and path_contains_part(
            Path(config.output_root), "proof_artifacts"
        )
        gates["candidate_shadow_plan_exists"] = bool(candidate_source_path and candidate_source_path.exists())
        gates["candidate_shadow_artifact_written"] = bool(candidate_shadow_hash)
    gate_blockers = [key for key, value in gates.items() if not value]
    all_blockers = sorted(set(blockers + gate_blockers))
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "ready" if not all_blockers else "blocked",
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "hook_enabled": bool(config.enabled),
        "mode": config.mode,
        "artifact_sink": config.artifact_sink,
        "candidate_order_authority": config.candidate_order_authority,
        "candidate_live_order_submission_authorized": config.candidate_live_order_submission_authorized,
        "execution_target_source": config.execution_target_source,
        "candidate_overlay_execution_path": config.candidate_overlay_execution_path,
        "baseline_target_plan": evidence_file(baseline_target_plan_path),
        "executor_input_plan": evidence_file(executor_input_plan_path),
        "candidate_source_plan": evidence_file(candidate_source_path),
        "proof_root": str(proof_root or ""),
        "candidate_artifact_paths": [str(path) for path in candidate_artifact_paths],
        "candidate_artifacts_written_count": len(candidate_artifact_paths),
        "candidate_artifacts_under_proof_artifacts_only": candidate_artifacts_under_proof,
        "baseline_target_plan_sha256_before_hook": baseline_before_hash,
        "baseline_target_plan_sha256_after_hook": baseline_after_hash,
        "executor_input_plan_sha256_before_hook": executor_before_hash,
        "executor_input_plan_sha256_after_hook": executor_after_hash,
        "candidate_shadow_plan_sha256": candidate_shadow_hash,
        "baseline_target_plan_byte_for_byte_unchanged": baseline_byte_for_byte_unchanged,
        "executor_input_plan_hash_unchanged": executor_hash_unchanged,
        "executor_input_plan_hash_equals_baseline": executor_input_plan_hash_equals_baseline,
        "executor_consumes_baseline_only": executor_consumes_baseline_only,
        "candidate_plan_referenced_by_executor": False,
        "candidate_orders_submitted": 0,
        "candidate_fill_count": 0,
        "orders_submitted": 0,
        "fill_count": 0,
        "mainnet_order_submission_authorized": False,
        "exchange_order_submission": "disabled",
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "timer_path_invoked": False,
        "ran_supervisor": False,
        "wrote_hook_config": False,
        "deployed_hook": False,
        "supervisor_context": supervisor_context,
        "gates": gates,
        "blockers": all_blockers,
    }
