from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

VERIFY_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import utc_now_iso, with_evidence_metadata
from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance
from enhengclaw.compat.naming import materialize_env_alias
from run_evidence_freshness_contract import evaluate_project_state_evidence_freshness
from run_operational_readiness import build_sanitized_env


BROAD_UNLOCK_CONTRACT_PATH = ROOT / "config" / "agent_layer_governance" / "broad_unlock_contract.json"
EVIDENCE_FRESHNESS_CONTRACT_PATH = ROOT / "config" / "agent_layer_governance" / "evidence_freshness_contract.json"
PROJECT_PROFILE_PATH = ROOT / "config" / "project_governance" / "project_profile.json"
PROJECT_STAGE_CONTRACT_PATH = ROOT / "config" / "project_governance" / "stage_contract.json"
PROJECT_STATE_PATH = ROOT / "PROJECT_STATE.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full broad-agent-layer readiness bundle.")
    parser.add_argument(
        "--retain-root",
        type=Path,
        default=None,
        help="Optional bundle evidence root. When omitted, a temporary root is created and retained on disk.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_broad_agent_layer_readiness(retain_root=args.retain_root)
    print(f"[broad-agent-layer-readiness] retain_root={result['retain_root']}")
    print(f"[broad-agent-layer-readiness] summary={result['summary_path']}")
    print(f"[broad-agent-layer-readiness] unlock_evaluation={result['unlock_evaluation_path']}")
    print(f"[broad-agent-layer-readiness] status={result['status']}")
    return int(result["exit_code"])


def run_broad_agent_layer_readiness(*, retain_root: Path | None = None) -> dict[str, Any]:
    resolved_retain_root = _prepare_retain_root(retain_root)
    env = _build_env(retain_root=resolved_retain_root)
    command_results: list[dict[str, Any]] = []
    failing_command_label = None
    failing_command_exit_code = None

    for label, command in _commands(resolved_retain_root):
        print(f"[broad-agent-layer-readiness] START {label}")
        completed = subprocess.run(command, check=False, cwd=ROOT, env=env)
        result = {
            "label": label,
            "command": command,
            "exit_code": completed.returncode,
            "status": "passed" if completed.returncode == 0 else "failed",
        }
        command_results.append(result)
        if completed.returncode != 0:
            print(f"[broad-agent-layer-readiness] FAIL {label} (exit={completed.returncode})")
            if label == "operational readiness verify":
                _print_operational_failure_context(resolved_retain_root / "operational_readiness")
            failing_command_label = label
            failing_command_exit_code = completed.returncode
            break
        print(f"[broad-agent-layer-readiness] PASS {label}")

    freshness_summary = None
    freshness_summary_path = resolved_retain_root / "evidence_freshness_summary.json"
    if failing_command_label is None:
        freshness_summary = evaluate_project_state_evidence_freshness(
            project_state_path=PROJECT_STATE_PATH,
            contract_path=EVIDENCE_FRESHNESS_CONTRACT_PATH,
        )
        _write_json(freshness_summary_path, freshness_summary)

    governance = evaluate_agent_layer_governance()
    broad_unlock_contract = json.loads(BROAD_UNLOCK_CONTRACT_PATH.read_text(encoding="utf-8"))
    project_profile = json.loads(PROJECT_PROFILE_PATH.read_text(encoding="utf-8"))
    project_stage_contract = json.loads(PROJECT_STAGE_CONTRACT_PATH.read_text(encoding="utf-8"))
    unlock_evaluation = _evaluate_broad_unlock(
        contract=broad_unlock_contract,
        command_results=command_results,
        governance=governance,
        freshness_summary=freshness_summary,
        failing_command_label=failing_command_label,
        project_profile=project_profile,
        project_stage_contract=project_stage_contract,
    )
    unlock_evaluation_path = resolved_retain_root / "broad_unlock_evaluation.json"
    _write_json(unlock_evaluation_path, unlock_evaluation)

    exit_code = 0 if unlock_evaluation["status"] in {"eligible_for_manual_unlock", "enabled"} else int(
        failing_command_exit_code or 1
    )
    summary = with_evidence_metadata(
        {
            "generated_at_utc": utc_now_iso(),
            "retain_root": str(resolved_retain_root),
            "status": unlock_evaluation["status"],
            "exit_code": exit_code,
            "command_results": command_results,
            "governance_status": governance.get("status"),
            "governance_blockers": governance.get("blockers"),
            "freshness_summary_path": None if freshness_summary is None else str(freshness_summary_path.resolve()),
            "unlock_evaluation_path": str(unlock_evaluation_path.resolve()),
            "failing_command_label": failing_command_label,
        },
        evidence_family="broad_agent_layer_readiness",
        contract_version=str(broad_unlock_contract.get("contract_version", "broad_agent_layer_unlock.v1")),
        repo_root=ROOT,
    )
    summary_path = resolved_retain_root / "broad_readiness_summary.json"
    _write_json(summary_path, summary)

    if unlock_evaluation["status"] == "eligible_for_manual_unlock":
        print("[broad-agent-layer-readiness] ELIGIBLE FOR MANUAL UNLOCK")
    elif unlock_evaluation["status"] == "enabled":
        print("[broad-agent-layer-readiness] BROAD LAYER ALREADY ENABLED")
    else:
        print("[broad-agent-layer-readiness] BLOCKED")

    return {
        "status": unlock_evaluation["status"],
        "exit_code": exit_code,
        "retain_root": str(resolved_retain_root),
        "summary_path": str(summary_path.resolve()),
        "unlock_evaluation_path": str(unlock_evaluation_path.resolve()),
    }


def _commands(retain_root: Path) -> list[tuple[str, list[str]]]:
    return [
        ("owner architecture contract", [sys.executable, str(ROOT / "scripts" / "verify" / "run_agent_architecture_contract.py")]),
        ("market_observer execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_market_observer_execution.py")]),
        ("evidence_agent execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_evidence_agent_execution.py")]),
        ("risk_signal execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_risk_signal_agent_execution.py")]),
        ("risk_governance execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_risk_governance_agent_execution.py")]),
        ("validation execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_validation_agent_execution.py")]),
        ("attention_allocator execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_attention_allocator_execution.py")]),
        ("research_synthesizer execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_research_synthesizer_execution.py")]),
        ("research_lead execution verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_research_lead_execution.py")]),
        ("risk_signal promoted verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_risk_signal_agent_pending.py")]),
        ("risk_governance promoted public verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_risk_governance_agent_pending.py")]),
        ("validation promoted public verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_validation_agent_pending.py")]),
        ("attention_allocator promoted public verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_attention_allocator_pending.py")]),
        ("research_synthesizer promoted public verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_research_synthesizer_pending.py")]),
        ("research_lead promoted public verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_research_lead_pending.py")]),
        ("governed ingress verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_governed_agent_ingress.py")]),
        ("boundary gates verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_boundary_gates.py")]),
        (
            "operational readiness verify",
            [
                sys.executable,
                str(ROOT / "scripts" / "verify" / "run_operational_readiness.py"),
                "--attempts",
                "3",
                "--retain-root",
                str(retain_root / "operational_readiness"),
            ],
        ),
        ("real shadow verify", [sys.executable, str(ROOT / "scripts" / "verify" / "run_real_shadow_acceptance.py"), "--mode", "verify"]),
    ]


def _evaluate_broad_unlock(
    *,
    contract: dict[str, Any],
    command_results: list[dict[str, Any]],
    governance: dict[str, Any],
    freshness_summary: dict[str, Any] | None,
    failing_command_label: str | None,
    project_profile: dict[str, Any],
    project_stage_contract: dict[str, Any],
) -> dict[str, Any]:
    results_by_label = {str(item["label"]): item for item in command_results}
    required_checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    for label in contract.get("required_command_labels", []):
        result = results_by_label.get(str(label))
        passed = bool(result) and int(result.get("exit_code", 1)) == 0
        required_checks.append(
            {
                "label": label,
                "status": "passed" if passed else "failed",
                "exit_code": None if result is None else result.get("exit_code"),
            }
        )
        if not passed:
            blockers.append(f"required command did not pass: {label}")

    if failing_command_label:
        blockers.append(f"command failure blocked readiness: {failing_command_label}")

    if governance.get("status") != "enabled":
        blockers.append(f"agent-layer governance is not enabled: {governance.get('status')}")
    if governance.get("blockers"):
        blockers.append("agent-layer governance blockers are not empty")

    freshness_blockers: list[str] = []
    required_families = {str(item) for item in contract.get("required_fresh_evidence_families", [])}
    passed_families: set[str] = set()
    if freshness_summary is None:
        freshness_blockers.append("evidence freshness summary was not produced")
    else:
        for reference in freshness_summary.get("references", []):
            if reference.get("status") == "passed" and reference.get("evidence_family"):
                passed_families.add(str(reference["evidence_family"]))
        for family in required_families:
            if family not in passed_families:
                freshness_blockers.append(f"fresh evidence is missing or stale for family: {family}")
    blockers.extend(freshness_blockers)

    manual_manifest_unlock_required = bool(contract.get("manual_manifest_unlock_required"))
    broad_enabled = bool(governance.get("broad_agent_layer_enabled"))
    current_stage = str(project_profile.get("current_stage", "")).strip()
    minimum_stage = str(contract.get("minimum_project_stage_for_manual_unlock", "")).strip()
    stage_gate_ok = _project_stage_meets_minimum(
        current_stage=current_stage,
        minimum_stage=minimum_stage,
        project_stage_contract=project_stage_contract,
    )
    if not stage_gate_ok:
        blockers.append(
            "project stage does not permit broad manual unlock: "
            f"current={current_stage or '<missing>'}, minimum={minimum_stage or '<missing>'}"
        )
    eligible_for_manual_unlock = not blockers and not broad_enabled
    if broad_enabled and not blockers:
        status = "enabled"
    elif eligible_for_manual_unlock:
        status = "eligible_for_manual_unlock"
    else:
        status = "blocked"

    return with_evidence_metadata(
        {
            "status": status,
            "manual_manifest_unlock_required": manual_manifest_unlock_required,
            "eligible_for_manual_unlock": eligible_for_manual_unlock,
            "broad_agent_layer_enabled": broad_enabled,
            "project_stage_gate_passed": stage_gate_ok,
            "current_project_stage": current_stage,
            "minimum_project_stage_for_manual_unlock": minimum_stage,
            "required_checks": required_checks,
            "required_fresh_evidence_families": sorted(required_families),
            "governance_status": governance.get("status"),
            "governance_blockers": governance.get("blockers"),
            "freshness_status": None if freshness_summary is None else freshness_summary.get("status"),
            "blockers": blockers,
        },
        evidence_family="broad_agent_layer_readiness",
        contract_version=str(contract.get("contract_version", "broad_agent_layer_unlock.v1")),
        repo_root=ROOT,
    )


def _project_stage_meets_minimum(
    *,
    current_stage: str,
    minimum_stage: str,
    project_stage_contract: dict[str, Any],
) -> bool:
    if not current_stage or not minimum_stage:
        return False
    ordered_stage_ids = [
        str(stage.get("stage_id", "")).strip()
        for stage in project_stage_contract.get("stages", [])
        if isinstance(stage, dict) and str(stage.get("stage_id", "")).strip()
    ]
    try:
        return ordered_stage_ids.index(current_stage) >= ordered_stage_ids.index(minimum_stage)
    except ValueError:
        return False


def _build_env(*, retain_root: Path) -> dict[str, str]:
    env = build_sanitized_env()
    materialize_env_alias(env, "ENHENGCLAW_BROAD_READINESS_RETAIN_ROOT", str(retain_root))
    return env


def _prepare_retain_root(retain_root: Path | None) -> Path:
    if retain_root is not None:
        retain_root.mkdir(parents=True, exist_ok=True)
        return retain_root.resolve()
    return Path(tempfile.mkdtemp(prefix="enhengclaw_broad_readiness_")).resolve()


def _print_operational_failure_context(operational_retain_root: Path) -> None:
    summary_path = operational_retain_root / "operational_readiness_summary.json"
    if not summary_path.exists():
        print(
            "[broad-agent-layer-readiness] operational_readiness_summary_missing="
            f"{summary_path}"
        )
        return
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(
            "[broad-agent-layer-readiness] operational_readiness_summary_unreadable="
            f"{summary_path} error={exc}"
        )
        return

    attempts = summary.get("attempts", [])
    failing_attempt = None
    for attempt in attempts:
        if isinstance(attempt, dict) and attempt.get("status") != "passed":
            failing_attempt = attempt
            break
    if failing_attempt is None and attempts:
        candidate = attempts[-1]
        if isinstance(candidate, dict):
            failing_attempt = candidate

    print(
        "[broad-agent-layer-readiness] operational_readiness_summary="
        f"{summary_path}"
    )
    if failing_attempt is None:
        return
    print(
        "[broad-agent-layer-readiness] failing_operational_attempt_root="
        f"{failing_attempt.get('attempt_root')}"
    )
    print(
        "[broad-agent-layer-readiness] failing_operational_step="
        f"{_extract_failing_step_label(failing_attempt)}"
    )
    failure_snapshot_path = failing_attempt.get("failure_snapshot_path")
    if failure_snapshot_path:
        print(
            "[broad-agent-layer-readiness] failing_operational_snapshot="
            f"{failure_snapshot_path}"
        )


def _extract_failing_step_label(attempt: dict[str, object]) -> str:
    step_results = attempt.get("step_results")
    if not isinstance(step_results, list) or not step_results:
        return "<unknown>"
    for step in step_results:
        if isinstance(step, dict) and int(step.get("returncode", 0) or 0) != 0:
            label = step.get("label")
            if isinstance(label, str) and label.strip():
                return label
    last = step_results[-1]
    if isinstance(last, dict):
        label = last.get("label")
        if isinstance(label, str) and label.strip():
            return label
    return "<unknown>"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
