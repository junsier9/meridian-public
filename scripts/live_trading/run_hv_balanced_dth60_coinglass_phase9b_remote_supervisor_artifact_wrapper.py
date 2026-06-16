from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9b_remote_supervisor_artifact_wrapper.v1"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9b_remote_supervisor_artifact_wrapper"
)
PLAN_HASH_REQUIRED_FILES = [
    "run_summary.json",
    "runtime_gate_context.json",
    "execution_plan.json",
    "execution_plan.csv",
    "order_sizing_report.csv",
    "risk_gate.json",
    "target_portfolio.json",
    "current_positions.csv",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a P9B read-only remote proof-artifacts wrapper from retained "
            "mainnet supervisor artifacts. The wrapper never starts the supervisor, "
            "never touches timers, and proves the executor input points to the "
            "baseline target plan only."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--supervisor-summary", required=True)
    parser.add_argument("--pre-control-snapshot", default="")
    parser.add_argument("--post-control-snapshot", default="")
    parser.add_argument(
        "--require-output-under-proof-artifacts",
        action="store_true",
        help="Fail closed unless output-root is inside a proof_artifacts path.",
    )
    return parser.parse_args(argv)


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


def resolve_path(path: str | Path, *, base: Path | None = None) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (base or ROOT) / p


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_file(path: Path, *, base: Path | None = None) -> dict[str, Any]:
    if not path:
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path, base=base)
    if not resolved.exists():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def plan_artifact_hash(plan_root: Path, names: list[str] | None = None) -> str:
    digest = hashlib.sha256()
    for name in sorted(names or PLAN_HASH_REQUIRED_FILES):
        path = plan_root / name
        if not path.exists():
            continue
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def output_under_proof_artifacts(path: Path) -> bool:
    return "proof_artifacts" in [part.lower() for part in path.resolve().parts]


def path_has_marker(path_value: str, marker: str) -> bool:
    return marker.lower() in [part.lower() for part in Path(str(path_value or "")).parts]


def control_state_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    systemd = dict(snapshot.get("systemd") or {})
    operator_state = snapshot.get("operator_state") or []
    if isinstance(operator_state, list):
        operator = {str(row.get("key")): str(row.get("value")) for row in operator_state}
    else:
        operator = dict(operator_state)
    return {
        "remote_live_config_sha256": snapshot.get("remote_live_config_sha256"),
        "systemd": systemd,
        "operator_state": operator,
    }


def build_phase9b_summary(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    supervisor_summary_path = resolve_path(args.supervisor_summary)
    blockers: list[str] = []

    supervisor: dict[str, Any] = {}
    if not supervisor_summary_path.exists():
        blockers.append("supervisor_summary_missing")
    else:
        supervisor = load_json(supervisor_summary_path)

    supervisor_root = resolve_path(
        str(supervisor.get("artifact_root") or supervisor_summary_path.parent),
        base=supervisor_summary_path.parent,
    )
    supervisor_cycle, cycle_path = latest_cycle(supervisor=supervisor, supervisor_root=supervisor_root)
    cycle, executor_cycle_source = select_executor_cycle(supervisor_cycle)
    if not cycle:
        blockers.append("latest_supervisor_cycle_missing")

    plan_root_value = str(cycle.get("plan_artifact_root") or "").strip() if cycle else ""
    plan_root = resolve_path(plan_root_value, base=supervisor_root) if plan_root_value else Path("")
    executor_root, executor_kind = select_executor_artifact(cycle, base=supervisor_root)
    source_manifest_path = executor_root / "source_plan_manifest.json" if executor_root else Path("")
    source_manifest: dict[str, Any] = {}
    if source_manifest_path and source_manifest_path.exists():
        source_manifest = load_json(source_manifest_path)
    inline_strategy_artifacts = dict(cycle.get("strategy_plan_artifacts") or {}) if cycle else {}
    strategy_target = dict(cycle.get("strategy_target") or {}) if cycle else {}
    inline_run_summary = dict(inline_strategy_artifacts.get("run_summary") or {})
    plan_root_text = str(plan_root) if plan_root else ""
    plan_root_norm = normalize_path_text(plan_root_text)
    inline_reference_roots = [
        str(value)
        for value in (
            strategy_target.get("artifact_root"),
            inline_run_summary.get("artifact_root"),
        )
        if str(value or "").strip()
    ]
    inline_plan_reference_matches_baseline = bool(
        inline_strategy_artifacts
        and plan_root_norm
        and inline_reference_roots
        and all(normalize_path_text(value) == plan_root_norm for value in inline_reference_roots)
    )
    if not executor_root and inline_plan_reference_matches_baseline:
        executor_root = plan_root
        executor_kind = "core_loop_inline_strategy_plan"

    missing_plan_files = [name for name in PLAN_HASH_REQUIRED_FILES if plan_root and not (plan_root / name).exists()]
    computed_plan_hash = plan_artifact_hash(plan_root) if plan_root and plan_root.exists() else ""
    manifest_plan_hash = str(source_manifest.get("plan_hash") or "")
    manifest_plan_root = str(source_manifest.get("plan_root") or "")
    executor_manifest_exists = bool(source_manifest)
    executor_reference_exists = bool(executor_manifest_exists or inline_plan_reference_matches_baseline)
    executor_reference_kind = (
        "source_plan_manifest"
        if executor_manifest_exists
        else "core_loop_inline_strategy_plan"
        if inline_plan_reference_matches_baseline
        else ""
    )
    executor_reference_plan_root = manifest_plan_root or (inline_reference_roots[0] if inline_reference_roots else "")
    plan_root_same = normalize_path_text(executor_reference_plan_root) == plan_root_norm
    executor_input_matches_baseline = (
        bool(computed_plan_hash)
        and not missing_plan_files
        and plan_root_same
        and (
            (executor_manifest_exists and computed_plan_hash == manifest_plan_hash)
            or (not executor_manifest_exists and inline_plan_reference_matches_baseline)
        )
    )
    output_is_proof = output_under_proof_artifacts(output_root)
    manifest_points_to_proof_artifacts = path_has_marker(manifest_plan_root, "proof_artifacts")
    manifest_points_to_candidate = any(
        token in manifest_plan_root.lower() for token in ("coinglass_candidate", "candidate_shadow")
    )
    reference_root_points_to_proof_artifacts = path_has_marker(executor_reference_plan_root, "proof_artifacts")
    reference_root_points_to_candidate = any(
        token in executor_reference_plan_root.lower() for token in ("coinglass_candidate", "candidate_shadow")
    )
    baseline_plan_root_points_to_proof_artifacts = path_has_marker(plan_root_text, "proof_artifacts")
    baseline_plan_root_points_to_candidate = any(
        token in plan_root_text.lower() for token in ("coinglass_candidate", "candidate_shadow")
    )
    candidate_plan_referenced_by_executor = bool(
        manifest_points_to_proof_artifacts
        or manifest_points_to_candidate
        or reference_root_points_to_proof_artifacts
        or reference_root_points_to_candidate
        or baseline_plan_root_points_to_proof_artifacts
        or baseline_plan_root_points_to_candidate
    )

    pre_control = load_optional_json(str(getattr(args, "pre_control_snapshot", "") or ""))
    post_control = load_optional_json(str(getattr(args, "post_control_snapshot", "") or ""))
    control_plane_checked = bool(pre_control and post_control)
    pre_digest = control_state_digest(pre_control) if pre_control else {}
    post_digest = control_state_digest(post_control) if post_control else {}
    control_plane_unchanged = pre_digest == post_digest if control_plane_checked else True
    post_mutation_key = "p9b_remote_mutation_observed"
    post_no_mutation = post_control.get(post_mutation_key) is False if post_control else True

    gates = {
        "supervisor_summary_exists": bool(supervisor),
        "supervisor_status_completed": supervisor.get("status") == "mainnet_live_supervisor_completed",
        "latest_cycle_loaded": bool(cycle),
        "plan_artifact_root_exists": bool(plan_root and plan_root.exists()),
        "plan_artifact_required_files_present": not missing_plan_files,
        "executor_input_reference_exists": executor_reference_exists,
        "executor_artifact_root_exists": bool(executor_root and executor_root.exists()),
        "executor_input_plan_root_equals_supervisor_plan_root": plan_root_same,
        "executor_input_plan_hash_equals_baseline": executor_input_matches_baseline,
        "candidate_plan_not_referenced_by_executor": not candidate_plan_referenced_by_executor,
        "wrapper_output_under_proof_artifacts": output_is_proof,
        "control_plane_unchanged": control_plane_unchanged,
        "post_no_p9b_mutation_observed": post_no_mutation,
    }
    if not bool(getattr(args, "require_output_under_proof_artifacts", False)):
        gates["wrapper_output_under_proof_artifacts"] = True
    blockers.extend(key for key, value in gates.items() if not value)
    if missing_plan_files:
        blockers.extend(f"plan_artifact_missing_file:{name}" for name in missing_plan_files)
    blockers = sorted(set(str(item) for item in blockers if str(item).strip()))
    ready = not blockers

    read_only_manifest = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "candidate_shadow_plan_generated": False,
        "candidate_plan_referenced_by_executor": candidate_plan_referenced_by_executor,
        "execution_target_source": "baseline_only" if ready else "not_proven",
        "source_plan_manifest": evidence_file(source_manifest_path) if source_manifest_path else {"exists": False},
        "executor_input_reference_kind": executor_reference_kind,
        "executor_input_reference_plan_root": executor_reference_plan_root,
        "executor_cycle_source": executor_cycle_source,
        "inline_strategy_plan_artifacts_present": bool(inline_strategy_artifacts),
        "inline_plan_reference_matches_baseline": inline_plan_reference_matches_baseline,
        "baseline_plan_root": str(plan_root),
        "executor_artifact_root": str(executor_root) if executor_root else "",
        "executor_artifact_kind": executor_kind,
        "computed_baseline_plan_hash": computed_plan_hash,
        "manifest_plan_hash": manifest_plan_hash,
    }
    write_json(output_root / "candidate_readonly_manifest.json", read_only_manifest)
    write_json(
        output_root / "executor_input_readback.json",
        {
            "status": "ready" if ready else "blocked",
            "executor_artifact_kind": executor_kind,
            "executor_artifact_root": str(executor_root) if executor_root else "",
            "executor_input_reference_kind": executor_reference_kind,
            "executor_cycle_source": executor_cycle_source,
            "source_plan_manifest": evidence_file(source_manifest_path) if source_manifest_path else {"exists": False},
            "baseline_plan_root": str(plan_root),
            "executor_input_reference_plan_root": executor_reference_plan_root,
            "source_manifest_plan_root": manifest_plan_root,
            "baseline_plan_hash": computed_plan_hash,
            "source_manifest_plan_hash": manifest_plan_hash,
            "executor_input_plan_hash_equals_baseline": gates["executor_input_plan_hash_equals_baseline"],
            "candidate_plan_referenced_by_executor": candidate_plan_referenced_by_executor,
            "inline_strategy_plan_artifacts_present": bool(inline_strategy_artifacts),
            "inline_plan_reference_matches_baseline": inline_plan_reference_matches_baseline,
        },
    )
    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": "ready" if ready else "blocked",
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "source_evidence": {
            "supervisor_summary": evidence_file(supervisor_summary_path),
            "cycle": evidence_file(cycle_path) if cycle_path else {"exists": False},
            "plan_artifact_root": str(plan_root),
            "source_plan_manifest": evidence_file(source_manifest_path) if source_manifest_path else {"exists": False},
            "executor_cycle_source": executor_cycle_source,
            "executor_input_reference_kind": executor_reference_kind,
            "executor_input_reference_plan_root": executor_reference_plan_root,
            "inline_strategy_plan_artifacts_present": bool(inline_strategy_artifacts),
            "pre_control_snapshot": evidence_file(resolve_path(args.pre_control_snapshot))
            if str(getattr(args, "pre_control_snapshot", "") or "").strip()
            else {"exists": False},
            "post_control_snapshot": evidence_file(resolve_path(args.post_control_snapshot))
            if str(getattr(args, "post_control_snapshot", "") or "").strip()
            else {"exists": False},
        },
        "supervisor": {
            "run_id": supervisor.get("run_id"),
            "status": supervisor.get("status"),
            "artifact_root": supervisor.get("artifact_root"),
            "orders_submitted": int(supervisor.get("orders_submitted") or 0),
            "fill_count": int(supervisor.get("fill_count") or 0),
            "live_delta_authorized": bool(supervisor.get("live_delta_authorized")),
            "target_engine": supervisor.get("target_engine"),
            "live_delta_armed_at_start": supervisor.get("live_delta_armed_at_start"),
            "live_delta_armed_at_finish": supervisor.get("live_delta_armed_at_finish"),
        },
        "cycle": {
            "cycle_index": cycle.get("cycle_index") if cycle else None,
            "status": cycle.get("status") if cycle else "",
            "plan_artifact_root": str(plan_root),
            "plan_status": cycle.get("plan_status") if cycle else "",
            "execution_status": cycle.get("execution_status") if cycle else "",
            "executor_cycle_source": executor_cycle_source,
            "executor_artifact_kind": executor_kind,
            "executor_artifact_root": str(executor_root) if executor_root else "",
            "orders_submitted": int(cycle.get("orders_submitted") or 0) if cycle else 0,
            "fill_count": int(cycle.get("fill_count") or 0) if cycle else 0,
            "live_delta_authorized": bool(cycle.get("live_delta_authorized")) if cycle else False,
        },
        "baseline_plan_hash": computed_plan_hash,
        "executor_source_manifest_plan_hash": manifest_plan_hash,
        "executor_source_manifest_plan_root": manifest_plan_root,
        "executor_input_reference_kind": executor_reference_kind,
        "executor_input_reference_plan_root": executor_reference_plan_root,
        "inline_strategy_plan_artifacts_present": bool(inline_strategy_artifacts),
        "inline_plan_reference_matches_baseline": inline_plan_reference_matches_baseline,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "candidate_shadow_plan_generated": False,
        "candidate_artifact_sink": "proof_artifacts_only",
        "candidate_artifact_paths": ["candidate_readonly_manifest.json"],
        "candidate_plan_referenced_by_executor": candidate_plan_referenced_by_executor,
        "execution_target_source": "baseline_only" if ready else "not_proven",
        "executor_consumes_baseline_only": bool(ready),
        "executor_input_plan_hash_equals_baseline": gates["executor_input_plan_hash_equals_baseline"],
        "wrapper_output_under_proof_artifacts": output_is_proof,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "read_only_supervisor_artifacts": True,
        "control_plane": {
            "checked": control_plane_checked,
            "pre": pre_digest,
            "post": post_digest,
            "unchanged": control_plane_unchanged,
        },
        "candidate_orders_submitted": 0,
        "candidate_fill_count": 0,
        "orders_submitted": 0,
        "fill_count": 0,
        "mainnet_order_submission_authorized": False,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "gates": gates,
        "eligible_for_further_shadow_observation": bool(ready),
        "eligible_for_live_order_submission": False,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "executor_input_readback": str(output_root / "executor_input_readback.json"),
            "candidate_readonly_manifest": str(output_root / "candidate_readonly_manifest.json"),
            "report": str(output_root / "p9b_remote_supervisor_artifact_wrapper.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9b_remote_supervisor_artifact_wrapper.md").write_text(render_markdown(summary), encoding="utf-8")
    write_json(output_root / "summary.json", summary)
    return summary, 0 if ready else 2


def latest_cycle(*, supervisor: dict[str, Any], supervisor_root: Path) -> tuple[dict[str, Any], Path]:
    cycles = [dict(item) for item in list(supervisor.get("cycles") or []) if isinstance(item, dict)]
    if not cycles:
        return {}, Path("")
    cycle = sorted(cycles, key=lambda item: int(item.get("cycle_index") or 0))[-1]
    cycle_index = int(cycle.get("cycle_index") or len(cycles))
    cycle_path = supervisor_root / f"cycle_{cycle_index:03d}.json"
    if cycle_path.exists():
        return load_json(cycle_path), cycle_path
    return cycle, Path("")


def select_executor_cycle(supervisor_cycle: dict[str, Any]) -> tuple[dict[str, Any], str]:
    core_loop_summary = dict(supervisor_cycle.get("core_loop_summary") or {})
    core_cycles = [dict(item) for item in list(core_loop_summary.get("cycles") or []) if isinstance(item, dict)]
    if core_cycles:
        cycle = sorted(core_cycles, key=lambda item: int(item.get("cycle_index") or 0))[-1]
        return cycle, "core_loop_summary.cycles"
    return dict(supervisor_cycle), "supervisor_cycle"


def select_executor_artifact(cycle: dict[str, Any], *, base: Path) -> tuple[Path, str]:
    for key, kind in (
        ("execution_artifact_root", "live_execution"),
        ("delta_preflight_artifact_root", "delta_preflight"),
    ):
        value = str(cycle.get(key) or "").strip()
        if value:
            root = resolve_path(value, base=base)
            if (root / "source_plan_manifest.json").exists():
                return root, kind
    for key, kind in (
        ("execution_artifact_root", "live_execution"),
        ("delta_preflight_artifact_root", "delta_preflight"),
    ):
        value = str(cycle.get(key) or "").strip()
        if value:
            return resolve_path(value, base=base), kind
    return Path(""), ""


def normalize_path_text(path_value: str) -> str:
    if not str(path_value or "").strip():
        return ""
    try:
        return str(Path(path_value).resolve())
    except OSError:
        return str(Path(path_value))


def load_optional_json(path_value: str) -> dict[str, Any]:
    if not str(path_value or "").strip():
        return {}
    path = resolve_path(path_value)
    return load_json(path) if path.exists() else {}


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9B Remote Supervisor Artifact Wrapper",
        "",
        f"Status: `{summary['status']}`",
        f"Generated: `{summary['generated_at_utc']}`",
        "",
        "## Boundary",
        "",
        "- The wrapper read retained supervisor artifacts only.",
        "- The wrapper did not run the supervisor or invoke the timer path.",
        "- Candidate order authority remained disabled.",
        "",
        "## Proof",
        "",
        f"- executor_consumes_baseline_only: `{str(summary['executor_consumes_baseline_only']).lower()}`",
        f"- executor_input_plan_hash_equals_baseline: `{str(summary['executor_input_plan_hash_equals_baseline']).lower()}`",
        f"- candidate_plan_referenced_by_executor: `{str(summary['candidate_plan_referenced_by_executor']).lower()}`",
        f"- wrapper_output_under_proof_artifacts: `{str(summary['wrapper_output_under_proof_artifacts']).lower()}`",
        f"- candidate_orders_submitted: `{summary['candidate_orders_submitted']}`",
        f"- candidate_fill_count: `{summary['candidate_fill_count']}`",
        f"- eligible_for_live_order_submission: `{str(summary['eligible_for_live_order_submission']).lower()}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9b_summary(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
