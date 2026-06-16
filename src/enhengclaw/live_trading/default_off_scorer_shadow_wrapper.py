from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


CONTRACT_VERSION = "hv_balanced_default_off_scorer_shadow_wrapper.v1"


@dataclass(frozen=True)
class DefaultOffScorerShadowConfig:
    enabled: bool = False
    mode: str = "observe_only"
    artifact_sink: str = "proof_artifacts_only"
    output_root: Path | None = None
    execution_score_source: str = "baseline_only"
    candidate_scorer_execution_path: str = "excluded"
    candidate_order_authority: str = "disabled"
    candidate_live_order_submission_authorized: bool = False


@dataclass(frozen=True)
class ScorerShadowWrapperResult:
    executor_scores: pd.DataFrame
    summary: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def frame_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def frame_sha256(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame_to_csv_bytes(frame)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_default_off_scorer_shadow_wrapper(
    *,
    config: DefaultOffScorerShadowConfig,
    baseline_scores: pd.DataFrame,
    executor_input_scores: pd.DataFrame | None = None,
    shadow_scorer_scores: pd.DataFrame | None = None,
    scorer_context: dict[str, Any] | None = None,
    run_id: str = "",
    now: datetime | None = None,
) -> ScorerShadowWrapperResult:
    started_at = now or utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    effective_run_id = run_id or started_at.strftime("%Y%m%dT%H%M%SZ")
    context = dict(scorer_context or {})
    baseline_before_hash = frame_sha256(baseline_scores)
    executor_input = baseline_scores if executor_input_scores is None else executor_input_scores
    executor_before_hash = frame_sha256(executor_input)
    blockers = _config_blockers(config)

    baseline_after_hash = frame_sha256(baseline_scores)
    executor_after_hash = frame_sha256(executor_input)
    shadow_artifacts: list[Path] = []
    proof_root: Path | None = None
    shadow_hash = ""

    if not config.enabled:
        summary = _summary(
            run_id=effective_run_id,
            started_at=started_at,
            config=config,
            blockers=blockers,
            baseline_before_hash=baseline_before_hash,
            baseline_after_hash=baseline_after_hash,
            executor_before_hash=executor_before_hash,
            executor_after_hash=executor_after_hash,
            wrapper_output_hash=baseline_after_hash,
            shadow_hash="",
            shadow_artifacts=[],
            proof_root=None,
            scorer_context=context,
        )
        return ScorerShadowWrapperResult(executor_scores=baseline_scores, summary=summary)

    if config.output_root is None:
        blockers.append("enabled_wrapper_output_root_missing")
    else:
        proof_root = Path(config.output_root) / "shadow_scorer"
        if not path_contains_part(Path(config.output_root), "proof_artifacts"):
            blockers.append("enabled_wrapper_output_root_not_under_proof_artifacts")
    if shadow_scorer_scores is None:
        blockers.append("shadow_scorer_scores_missing")
    if executor_before_hash != baseline_before_hash:
        blockers.append("executor_input_scores_hash_not_baseline_before_wrapper")

    if not blockers and proof_root is not None and shadow_scorer_scores is not None:
        proof_root.mkdir(parents=True, exist_ok=True)
        shadow_output = proof_root / "shadow_scorer_scores.csv"
        shadow_scorer_scores.to_csv(shadow_output, index=False, lineterminator="\n")
        shadow_hash = file_sha256(shadow_output)
        shadow_artifacts.append(shadow_output)

        context_output = proof_root / "context.json"
        write_json(
            context_output,
            {
                "contract_version": CONTRACT_VERSION,
                "run_id": effective_run_id,
                "generated_at_utc": iso_z(started_at),
                "context": context,
                "baseline_scores_sha256": baseline_before_hash,
                "executor_input_scores_sha256": executor_before_hash,
                "shadow_scorer_scores": evidence_file(shadow_output),
            },
        )
        shadow_artifacts.append(context_output)

        executor_readback_output = proof_root / "exec_readback.json"
        write_json(
            executor_readback_output,
            {
                "contract_version": CONTRACT_VERSION,
                "run_id": effective_run_id,
                "execution_score_source": "baseline_only",
                "executor_input_scores_sha256": executor_before_hash,
                "baseline_scores_sha256": baseline_before_hash,
                "shadow_scorer_scores": evidence_file(shadow_output),
                "shadow_scorer_referenced_by_executor": False,
            },
        )
        shadow_artifacts.append(executor_readback_output)

        manifest_output = proof_root / "manifest.json"
        write_json(
            manifest_output,
            {
                "contract_version": CONTRACT_VERSION,
                "run_id": effective_run_id,
                "mode": config.mode,
                "artifact_sink": config.artifact_sink,
                "execution_score_source": config.execution_score_source,
                "candidate_scorer_execution_path": config.candidate_scorer_execution_path,
                "candidate_order_authority": config.candidate_order_authority,
                "candidate_live_order_submission_authorized": config.candidate_live_order_submission_authorized,
                "shadow_scorer_scores": evidence_file(shadow_output),
                "executor_score_input_readback": evidence_file(executor_readback_output),
                "orders_submitted": 0,
                "fill_count": 0,
            },
        )
        shadow_artifacts.append(manifest_output)

    baseline_after_hash = frame_sha256(baseline_scores)
    executor_after_hash = frame_sha256(executor_input)
    summary = _summary(
        run_id=effective_run_id,
        started_at=started_at,
        config=config,
        blockers=blockers,
        baseline_before_hash=baseline_before_hash,
        baseline_after_hash=baseline_after_hash,
        executor_before_hash=executor_before_hash,
        executor_after_hash=executor_after_hash,
        wrapper_output_hash=baseline_after_hash,
        shadow_hash=shadow_hash,
        shadow_artifacts=shadow_artifacts,
        proof_root=proof_root,
        scorer_context=context,
    )
    return ScorerShadowWrapperResult(executor_scores=baseline_scores, summary=summary)


def _config_blockers(config: DefaultOffScorerShadowConfig) -> list[str]:
    blockers: list[str] = []
    if config.mode != "observe_only":
        blockers.append("mode_not_observe_only")
    if config.artifact_sink != "proof_artifacts_only":
        blockers.append("artifact_sink_not_proof_artifacts_only")
    if config.execution_score_source != "baseline_only":
        blockers.append("execution_score_source_not_baseline_only")
    if config.candidate_scorer_execution_path != "excluded":
        blockers.append("candidate_scorer_execution_path_not_excluded")
    if config.candidate_order_authority != "disabled":
        blockers.append("candidate_order_authority_not_disabled")
    if config.candidate_live_order_submission_authorized is not False:
        blockers.append("candidate_live_order_submission_authorized")
    return blockers


def _summary(
    *,
    run_id: str,
    started_at: datetime,
    config: DefaultOffScorerShadowConfig,
    blockers: list[str],
    baseline_before_hash: str,
    baseline_after_hash: str,
    executor_before_hash: str,
    executor_after_hash: str,
    wrapper_output_hash: str,
    shadow_hash: str,
    shadow_artifacts: list[Path],
    proof_root: Path | None,
    scorer_context: dict[str, Any],
) -> dict[str, Any]:
    baseline_unchanged = bool(baseline_before_hash) and baseline_before_hash == baseline_after_hash
    executor_unchanged = bool(executor_before_hash) and executor_before_hash == executor_after_hash
    executor_equals_baseline = bool(executor_after_hash) and executor_after_hash == baseline_after_hash
    wrapper_output_equals_baseline = bool(wrapper_output_hash) and wrapper_output_hash == baseline_after_hash
    shadow_under_proof = (
        not shadow_artifacts
        if not config.enabled
        else bool(proof_root)
        and bool(shadow_artifacts)
        and all(path_under(path, proof_root.parent) for path in shadow_artifacts)
    )
    executor_consumes_baseline_only = (
        baseline_unchanged
        and executor_unchanged
        and executor_equals_baseline
        and wrapper_output_equals_baseline
    )
    gates = {
        "mode_observe_only": config.mode == "observe_only",
        "artifact_sink_proof_artifacts_only": config.artifact_sink == "proof_artifacts_only",
        "execution_score_source_baseline_only": config.execution_score_source == "baseline_only",
        "candidate_scorer_execution_path_excluded": config.candidate_scorer_execution_path == "excluded",
        "candidate_order_authority_disabled": config.candidate_order_authority == "disabled",
        "candidate_live_order_submission_authorized_false": config.candidate_live_order_submission_authorized is False,
        "baseline_scores_byte_for_byte_unchanged": baseline_unchanged,
        "executor_input_scores_hash_unchanged": executor_unchanged,
        "executor_input_scores_hash_equals_baseline": executor_equals_baseline,
        "wrapper_output_scores_hash_equals_baseline": wrapper_output_equals_baseline,
        "executor_consumes_baseline_only": executor_consumes_baseline_only,
        "shadow_artifacts_under_proof_artifacts_only": shadow_under_proof,
        "orders_submitted_zero": True,
        "fill_count_zero": True,
    }
    if config.enabled:
        gates["enabled_wrapper_output_root_under_proof_artifacts"] = bool(config.output_root) and path_contains_part(
            Path(config.output_root), "proof_artifacts"
        )
        gates["shadow_scorer_artifact_written"] = bool(shadow_hash)
        gates["shadow_scorer_referenced_by_executor_false"] = True
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
        "execution_score_source": config.execution_score_source,
        "candidate_scorer_execution_path": config.candidate_scorer_execution_path,
        "candidate_order_authority": config.candidate_order_authority,
        "candidate_live_order_submission_authorized": config.candidate_live_order_submission_authorized,
        "proof_root": str(proof_root or ""),
        "shadow_artifact_paths": [str(path) for path in shadow_artifacts],
        "shadow_artifacts_written_count": len(shadow_artifacts),
        "shadow_artifacts_under_proof_artifacts_only": shadow_under_proof,
        "baseline_scores_sha256_before_hook": baseline_before_hash,
        "baseline_scores_sha256_after_hook": baseline_after_hash,
        "executor_input_scores_sha256_before_hook": executor_before_hash,
        "executor_input_scores_sha256_after_hook": executor_after_hash,
        "wrapper_output_scores_sha256": wrapper_output_hash,
        "shadow_scorer_scores_sha256": shadow_hash,
        "baseline_scores_byte_for_byte_unchanged": baseline_unchanged,
        "executor_input_scores_hash_unchanged": executor_unchanged,
        "executor_input_scores_hash_equals_baseline": executor_equals_baseline,
        "wrapper_output_scores_hash_equals_baseline": wrapper_output_equals_baseline,
        "executor_consumes_baseline_only": executor_consumes_baseline_only,
        "shadow_scorer_referenced_by_executor": False,
        "candidate_scorer_loaded_into_executor": False,
        "candidate_scorer_loaded_into_timer": False,
        "candidate_executed": False,
        "executor_invoked": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "supervisor_invoked": False,
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
        "scorer_context": scorer_context,
        "gates": gates,
        "blockers": all_blockers,
    }
