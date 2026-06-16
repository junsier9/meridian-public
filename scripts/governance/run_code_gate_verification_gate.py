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


CONTRACT_VERSION = "project_governance_code_gate_verification_gate.v1"
APPROVE_CODE_GATE_VERIFICATION = (
    "approve_code_gate_verification_gate_only_no_runtime_enablement"
)
DEFAULT_OUTPUT_PARENT = "artifacts/governance/code_gate_verification_gate"

# Source files whose markers prove the §3/§5.1 fixes landed.
DELTA_RUNNER = "src/enhengclaw/live_trading/mainnet_delta_execution_runner.py"
CORE_LOOP_RUNNER = "src/enhengclaw/live_trading/mainnet_core_loop_runner.py"
LIVE_RISK_CONTROLS = "src/enhengclaw/live_trading/live_risk_controls.py"
LIVE_TIMER_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)

# Each marker is a stable, unique substring introduced by the corresponding fix.
SOURCE_MARKERS: dict[str, tuple[str, str]] = {
    "fix1_delta_margin_fail_closed": (
        DELTA_RUNNER,
        "Fail-closed: when no plan-stage source margin gate",
    ),
    "fix2_account_snapshot_age_gate_defined": (
        LIVE_RISK_CONTROLS,
        "def evaluate_account_snapshot_age_gate(",
    ),
    "fix2_account_snapshot_age_gate_wired": (
        DELTA_RUNNER,
        "evaluate_account_snapshot_age_gate(",
    ),
    "fix2_snapshot_fetched_at_stamped": (
        DELTA_RUNNER,
        '"fetched_at_ms": fetched_at_ms',
    ),
    "fix4_entry_second_reconcile_symmetry": (
        CORE_LOOP_RUNNER,
        "Prior-submission integrity applies to BOTH",
    ),
    "fix3_spread_guard_out_of_scope_recorded": (
        LIVE_TIMER_CONFIG,
        "OUT-OF-SCOPE by owner decision",
    ),
}

# The targeted test files whose green run the evidence artifact must attest to.
REQUIRED_TEST_FILES = (
    "tests/test_hv_balanced_live_risk_controls.py",
    "tests/test_hv_balanced_mainnet_core_loop_runner.py",
    "tests/test_hv_balanced_mainnet_delta_execution_runner.py",
)

NEXT_GATE = (
    "Stage4_profile_transition_and_manifest_unlock_gate_only_if_separately_requested"
)
NEXT_GATE_SCOPE = (
    "apply_stage4_profile_transition_and_manifest_unlocks_after_fresh_readbacks_"
    "without_live_runtime_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the §3/§5.1 code-gate fixes landed. This gate is proof-only: it "
            "reads source markers and a separately-produced pytest evidence artifact; "
            "it does not modify code, run tests itself, enable runtime, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--test-evidence", default="")
    parser.add_argument("--delta-runner", default=DELTA_RUNNER)
    parser.add_argument("--core-loop-runner", default=CORE_LOOP_RUNNER)
    parser.add_argument("--live-risk-controls", default=LIVE_RISK_CONTROLS)
    parser.add_argument("--live-timer-config", default=LIVE_TIMER_CONFIG)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_CODE_GATE_VERIFICATION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:code_gate_verification_gate",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: str | Path) -> dict[str, Any]:
    if not str(path).strip():
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def read_text_optional(path: str | Path) -> str | None:
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved.read_text(encoding="utf-8")


def load_optional(path: str | Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        return dict(json.loads(resolved.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _marker_path_for(role: str, args: argparse.Namespace) -> str:
    return {
        DELTA_RUNNER: args.delta_runner,
        CORE_LOOP_RUNNER: args.core_loop_runner,
        LIVE_RISK_CONTROLS: args.live_risk_controls,
        LIVE_TIMER_CONFIG: args.live_timer_config,
    }[role]


def build_code_gate_verification_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "code_gate_verification" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    owner_decision_ok = str(args.owner_decision) == APPROVE_CODE_GATE_VERIFICATION

    # --- Source-marker checks (deterministic, read-only) ---
    marker_results: dict[str, dict[str, Any]] = {}
    source_checks: dict[str, bool] = {}
    for check_name, (role, marker) in SOURCE_MARKERS.items():
        rel_path = _marker_path_for(role, args)
        text = read_text_optional(rel_path)
        present = bool(text is not None and marker in text)
        marker_results[check_name] = {
            "path": rel_path,
            "marker": marker,
            "present": present,
        }
        source_checks[check_name] = present

    # --- Test-evidence checks (consume a separately-produced pytest result) ---
    evidence_path = resolve_path(args.test_evidence) if str(args.test_evidence).strip() else None
    evidence = load_optional(args.test_evidence) if evidence_path else {}
    evidence_exists = bool(evidence_path is not None and evidence_path.exists() and evidence)
    ev_exit_code = evidence.get("exit_code")
    ev_passed = evidence.get("passed")
    ev_failed = evidence.get("failed")
    ev_errors = evidence.get("errors")
    covered_files = {str(item) for item in (evidence.get("targeted_test_files") or [])}
    required_files = set(REQUIRED_TEST_FILES)

    evidence_checks = {
        "test_evidence_present": evidence_exists,
        # NOT exit-code-alone: we require zero failures/errors and a positive pass
        # count AND coverage of every required file, not just a green shell exit.
        "test_evidence_exit_code_zero": ev_exit_code == 0,
        "test_evidence_no_failures": ev_failed == 0 and ev_errors == 0,
        "test_evidence_has_passing_tests": isinstance(ev_passed, int) and ev_passed > 0,
        "test_evidence_covers_required_files": required_files.issubset(covered_files),
    }

    checks = {
        "owner_decision_code_gate_verification_recorded": owner_decision_ok,
        **source_checks,
        **evidence_checks,
    }
    blockers = sorted(key for key, value in checks.items() if not value)
    ready = not blockers
    status = "ready" if ready else "blocked"

    owner_record = {
        "contract_version": "project_governance_code_gate_verification_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "code_gate_verification_recorded": owner_decision_ok,
        "code_mutation_approved": False,
        "test_execution_in_this_gate": False,
        "runtime_enablement_approved_now": False,
    }

    non_authorization = {
        "contract_version": "project_governance_code_gate_verification_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "code_gate_verification_recorded": ready,
            "stage4_profile_transition_request_allowed": ready,
            "code_mutation_in_this_gate": False,
            "test_execution_in_this_gate": False,
            "project_profile_mutation_in_this_gate": False,
            "automated_execution_manifest_unlock_in_this_gate": False,
            "continuous_automated_order_flow": False,
            "live_order_submission": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }

    control = {
        "contract_version": "project_governance_code_gate_verification_control_readback.v1",
        "run_id": run_id,
        "scope": "verification_record_only_no_mutation_no_test_run",
        "code_changed": False,
        "tests_executed_by_this_gate": False,
        "project_profile_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "source_marker_readback": str(proof_root / "source_marker_readback.json"),
        "test_evidence_readback": str(proof_root / "test_evidence_readback.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "code_gate_verification_gate.md"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": status,
        "blockers": blockers,
        "code_gate_verification_gate_ready": ready,
        "owner_decision_code_gate_verification_recorded": owner_decision_ok,
        "verified_fixes": sorted(source_checks.keys()),
        "test_evidence": {
            "path": str(args.test_evidence) if str(args.test_evidence).strip() else "",
            "exit_code": ev_exit_code,
            "passed": ev_passed,
            "failed": ev_failed,
            "errors": ev_errors,
            "targeted_test_files": sorted(covered_files),
            "required_test_files": sorted(required_files),
        },
        "code_mutation_performed": False,
        "tests_executed_by_this_gate": False,
        "continuous_automated_order_flow_authorized": False,
        "live_order_submission_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "allowed_next_gate": NEXT_GATE if ready else "",
        "allowed_next_gate_scope": NEXT_GATE_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": ready,
        "source_evidence": {
            "delta_runner": evidence_file(args.delta_runner),
            "core_loop_runner": evidence_file(args.core_loop_runner),
            "live_risk_controls": evidence_file(args.live_risk_controls),
            "live_timer_config": evidence_file(args.live_timer_config),
            "test_evidence": evidence_file(args.test_evidence),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(
        Path(output_files["source_marker_readback"]),
        {
            "contract_version": "project_governance_code_gate_source_marker_readback.v1",
            "run_id": run_id,
            "markers": marker_results,
        },
    )
    write_json(
        Path(output_files["test_evidence_readback"]),
        {
            "contract_version": "project_governance_code_gate_test_evidence_readback.v1",
            "run_id": run_id,
            "evidence_present": evidence_exists,
            "evidence_checks": evidence_checks,
            "evidence": evidence,
        },
    )
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    ev = dict(summary.get("test_evidence") or {})
    lines = [
        "# Code-Gate Verification Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "Verifies the §3/§5.1 fixes landed via source markers and a separately-produced "
        "pytest evidence artifact. Proof-only: no code change, no test run, no runtime enablement.",
        "",
        "## Verification",
        "",
        "```text",
        f"code_gate_verification_gate_ready = {str(bool(summary['code_gate_verification_gate_ready'])).lower()}",
        f"test_evidence_exit_code = {ev.get('exit_code')}",
        f"test_evidence_passed = {ev.get('passed')}",
        f"test_evidence_failed = {ev.get('failed')}",
        f"test_evidence_errors = {ev.get('errors')}",
        "code_mutation_performed = false",
        "tests_executed_by_this_gate = false",
        "orders_submitted = 0",
        "```",
        "",
        "## Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        f"allowed_next_gate_must_be_separately_requested = {str(bool(summary['allowed_next_gate_must_be_separately_requested'])).lower()}",
        "```",
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_code_gate_verification_gate(parse_args(argv))
    print(
        "code_gate_verification_gate_ready="
        + str(bool(summary["code_gate_verification_gate_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
