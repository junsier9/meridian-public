from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhengclaw.compat.naming import pop_env_aliases
from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from scripts.openclaw._market_observer_live_inputs import (
    DEFAULT_EXPIRES_AFTER_HOURS,
    DEFAULT_TRUST_ROOT_MODE,
    describe_trust_root_source,
    resolve_external_root,
    resolve_openclaw_bundle_operator_env,
    resolve_trust_root_dir,
)


VERIFY_DEPLOYMENT_GATE = ROOT / "scripts" / "verify" / "run_openclaw_deployment_readiness.py"
PROVISIONING_CLI = SCRIPT_DIR / "provision_market_observer_live_inputs.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the formal operator workflow that provisions external live inputs and then runs the deployment gate."
    )
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help="External provisioning root. Defaults to %%LOCALAPPDATA%%\\EnhengClaw\\openclaw_live_market_observer.",
    )
    parser.add_argument(
        "--retain-root",
        type=Path,
        default=None,
        help="Optional retained root for the deployment bundle. Defaults to <external-root>\\retained\\<timestamp>.",
    )
    parser.add_argument(
        "--trust-root-dir",
        type=Path,
        default=None,
        help="Read-only trust root for permit validation. Defaults to C:\\ProgramData\\EnhengClaw\\trust.",
    )
    parser.add_argument(
        "--expires-after-hours",
        type=int,
        default=DEFAULT_EXPIRES_AFTER_HOURS,
        help="Permit lifetime in hours. Defaults to 24.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_market_observer_deployment_gate(
        external_root=args.external_root,
        retain_root=args.retain_root,
        trust_root_dir=args.trust_root_dir,
        expires_after_hours=args.expires_after_hours,
    )
    print(f"[market-observer-operator] retain_root={result['retain_root']}")
    print(f"[market-observer-operator] provisioning_summary_path={result.get('provisioning_summary_path')}")
    print(f"[market-observer-operator] deployment_bundle_summary_path={result.get('deployment_bundle_summary_path')}")
    print(f"[market-observer-operator] status={result['status']}")
    return int(result["exit_code"])


def run_market_observer_deployment_gate(
    *,
    external_root: Path | None = None,
    retain_root: Path | None = None,
    trust_root_dir: Path | None = None,
    expires_after_hours: int = DEFAULT_EXPIRES_AFTER_HOURS,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_env = dict(os.environ if base_env is None else base_env)
    resolved_external_root = resolve_external_root(external_root=external_root, base_env=source_env)
    resolved_trust_root = resolve_trust_root_dir(trust_root_dir=trust_root_dir, base_env=source_env)
    trust_root_meta = describe_trust_root_source(trust_root_dir=trust_root_dir)
    resolved_external_root.mkdir(parents=True, exist_ok=True)
    resolved_retain_root = _resolve_retain_root(resolved_external_root, retain_root)
    resolved_retain_root.mkdir(parents=True, exist_ok=True)

    provisioning = _run_provisioning_command(
        external_root=resolved_external_root,
        trust_root_dir=resolved_trust_root,
        trust_root_dir_explicit=trust_root_dir is not None,
        expires_after_hours=expires_after_hours,
        env=source_env,
        retain_root=resolved_retain_root,
    )
    if provisioning["status"] != "success":
        result = {
            "status": "failed",
            "exit_code": int(provisioning["exit_code"]),
            "retain_root": str(resolved_retain_root),
            "provisioning_summary_path": provisioning.get("summary_path"),
            "deployment_bundle_summary_path": None,
            "permit_expires_at_utc": None,
            "openclaw_mapping_used": False,
            "live_env_mode": "unified_openclaw_baseline",
            "openclaw_mapping_used_by_lane": {},
            "dedicated_env_preserved_by_lane": {},
            "defaulted_base_url_by_lane": {},
            "defaulted_model_name_by_lane": {},
            "trust_root_override_applied": trust_root_meta["trust_root_override_applied"],
            "trust_root_dir": str(resolved_trust_root),
            "trust_root_mode": trust_root_meta["trust_root_mode"],
            "trust_root_validation": "failed",
            "failing_gate": "provisioning",
            "failing_stage": "provisioning_cli",
        }
        _write_operator_summary(resolved_retain_root / "operator_run_summary.json", result)
        return result

    try:
        _validated_env, operator_env_meta = resolve_openclaw_bundle_operator_env(source_env, fail_closed=True)
    except RuntimeError as exc:
        result = {
            "status": "failed",
            "exit_code": 1,
            "retain_root": str(resolved_retain_root),
            "provisioning_summary_path": provisioning["summary_path"],
            "deployment_bundle_summary_path": None,
            "permit_expires_at_utc": provisioning["summary"]["expires_at_utc"],
            "openclaw_mapping_used": False,
            "live_env_mode": "unified_openclaw_baseline",
            "openclaw_mapping_used_by_lane": {},
            "dedicated_env_preserved_by_lane": {},
            "defaulted_base_url_by_lane": {},
            "defaulted_model_name_by_lane": {},
            "trust_root_override_applied": provisioning["summary"].get(
                "trust_root_override_applied",
                trust_root_meta["trust_root_override_applied"],
            ),
            "trust_root_dir": provisioning["summary"]["trust_root_dir"],
            "trust_root_mode": provisioning["summary"].get("trust_root_mode", DEFAULT_TRUST_ROOT_MODE),
            "trust_root_validation": provisioning["summary"].get("trust_root_validation", "failed"),
            "failing_gate": "operator_env",
            "failing_stage": "openclaw_env_mapping",
            "error": str(exc),
        }
        _write_operator_summary(resolved_retain_root / "operator_run_summary.json", result)
        return result

    deployment_env = _build_deployment_gate_env(source_env)
    gate_result = _run_deployment_gate_command(
        execution_permit=Path(provisioning["summary"]["permit_path"]),
        trust_root_dir=Path(provisioning["summary"]["trust_root_dir"]),
        retain_root=resolved_retain_root,
        env=deployment_env,
    )
    bundle_summary = _safe_load_json(resolved_retain_root / "bundle_summary.json")
    result = {
        "status": "success" if gate_result["exit_code"] == 0 else "failed",
        "exit_code": int(gate_result["exit_code"]),
        "retain_root": str(resolved_retain_root),
        "provisioning_summary_path": provisioning["summary_path"],
        "deployment_bundle_summary_path": str(resolved_retain_root / "bundle_summary.json"),
        "permit_expires_at_utc": provisioning["summary"]["expires_at_utc"],
        "openclaw_mapping_used": operator_env_meta["openclaw_mapping_used"],
        "live_env_mode": operator_env_meta["live_env_mode"],
        "openclaw_mapping_used_by_lane": operator_env_meta["openclaw_mapping_used_by_lane"],
        "dedicated_env_preserved_by_lane": operator_env_meta["dedicated_env_preserved_by_lane"],
        "defaulted_base_url_by_lane": operator_env_meta["defaulted_base_url_by_lane"],
        "defaulted_model_name_by_lane": operator_env_meta["defaulted_model_name_by_lane"],
        "trust_root_override_applied": provisioning["summary"].get(
            "trust_root_override_applied",
            trust_root_meta["trust_root_override_applied"],
        ),
        "trust_root_dir": provisioning["summary"]["trust_root_dir"],
        "trust_root_mode": provisioning["summary"].get("trust_root_mode", DEFAULT_TRUST_ROOT_MODE),
        "trust_root_validation": provisioning["summary"].get("trust_root_validation", "failed"),
        "deployment_stdout_path": gate_result["stdout_path"],
        "deployment_stderr_path": gate_result["stderr_path"],
        "failing_gate": None if bundle_summary is None else bundle_summary.get("failing_gate"),
        "failing_stage": None if bundle_summary is None else bundle_summary.get("failing_stage"),
        "generated_at_utc": _utc_now(),
    }
    _write_operator_summary(resolved_retain_root / "operator_run_summary.json", result)
    return result


def _run_provisioning_command(
    *,
    external_root: Path,
    trust_root_dir: Path,
    trust_root_dir_explicit: bool,
    expires_after_hours: int,
    env: dict[str, str],
    retain_root: Path,
) -> dict[str, Any]:
    stdout_path = retain_root / "provisioning_stdout.log"
    stderr_path = retain_root / "provisioning_stderr.log"
    command = [
        sys.executable,
        str(PROVISIONING_CLI),
        "--external-root",
        str(external_root),
        "--expires-after-hours",
        str(expires_after_hours),
    ]
    if trust_root_dir_explicit:
        command.extend(["--trust-root-dir", str(trust_root_dir)])
    completed = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    summary_path = external_root / "provision_summary.json"
    summary = _safe_load_json(summary_path)
    return {
        "status": "success" if completed.returncode == 0 and summary is not None else "failed",
        "exit_code": completed.returncode or (0 if summary is not None else 1),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "summary_path": str(summary_path),
        "summary": summary,
    }


def _run_deployment_gate_command(
    *,
    execution_permit: Path,
    trust_root_dir: Path,
    retain_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    stdout_path = retain_root / "deployment_gate_stdout.log"
    stderr_path = retain_root / "deployment_gate_stderr.log"
    command = [
        sys.executable,
        str(VERIFY_DEPLOYMENT_GATE),
        "--execution-permit",
        str(execution_permit),
        "--trust-root-dir",
        str(trust_root_dir),
        "--retain-root",
        str(retain_root),
    ]
    completed = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    return {
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _build_deployment_gate_env(source_env: dict[str, str]) -> dict[str, str]:
    env = dict(source_env)
    pop_env_aliases(env, "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT")
    return env


def _resolve_retain_root(external_root: Path, retain_root: Path | None) -> Path:
    if retain_root is not None:
        return retain_root.resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return (external_root / "retained" / timestamp).resolve()


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_operator_summary(path: Path, payload: dict[str, Any]) -> None:
    _write_json(
        path,
        with_evidence_metadata(
            payload,
            evidence_family="openclaw_operator_workflow",
            contract_version="openclaw_operator_workflow.v1",
            repo_root=ROOT,
        ),
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
