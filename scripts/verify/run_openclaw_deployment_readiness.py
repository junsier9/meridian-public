from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


VERIFY_DIR = Path(__file__).resolve().parent
ROOT = VERIFY_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

from enhengclaw.compat.naming import pop_env_aliases
from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from scripts.openclaw._market_observer_live_inputs import (
    openclaw_bundle_live_env_specs,
    resolve_openclaw_bundle_operator_env,
)
from run_operational_readiness import build_sanitized_env


PASS_THROUGH_ENV = ("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", "OPENCLAW")
LIVE_GATE_ID = "market_observer_live"
CONTINUE_EXISTING_LIVE_GATE_ID = "continue_existing_live"
REVIEW_GATED_LIVE_GATE_ID = "review_gated_live"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the formal OpenClaw deployment-readiness bundle.")
    parser.add_argument(
        "--execution-permit",
        type=Path,
        help="Explicit external execution permit path required for the market_observer live deployment gate.",
    )
    parser.add_argument(
        "--trust-root-dir",
        type=Path,
        default=None,
        help="Optional trust-root directory forwarded to the market_observer live deployment gate.",
    )
    parser.add_argument(
        "--retain-root",
        type=Path,
        default=None,
        help="Optional bundle evidence root. When omitted, a temporary root is created and retained on disk.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_openclaw_deployment_readiness(
        execution_permit=args.execution_permit,
        trust_root_dir=args.trust_root_dir,
        retain_root=args.retain_root,
    )
    print(f"[openclaw-deployment-readiness] retain_root={result['retain_root']}")
    if result["status"] == "failed":
        print(f"[openclaw-deployment-readiness] failing_gate={result['failing_gate']}")
        print(f"[openclaw-deployment-readiness] failing_stage={result['failing_stage']}")
        print("[openclaw-deployment-readiness] FINAL CONCLUSION=FAILED")
        return int(result["exit_code"])
    print("[openclaw-deployment-readiness] FINAL CONCLUSION=PASSED")
    return 0


def run_openclaw_deployment_readiness(
    *,
    execution_permit: Path | None,
    trust_root_dir: Path | None = None,
    retain_root: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_retain_root = _prepare_retain_root(retain_root)
    summary = _initial_summary(resolved_retain_root)

    if execution_permit is None:
        _set_failure(
            summary,
            failing_gate="bundle_preflight",
            failing_stage="execution_permit_required",
        )
        summary["exit_code"] = 2
        _write_bundle_failure_snapshot(
            resolved_retain_root,
            error="OpenClaw deployment readiness requires --execution-permit <WindowsPath>.",
            execution_permit=None,
            trust_root_dir=trust_root_dir,
            summary=summary,
        )
        _write_bundle_summary(summary, resolved_retain_root)
        return summary

    recorded_env = _build_recorded_env(base_env=base_env)
    live_env, env_meta = _build_live_env(base_env=base_env)
    summary["live_env_baseline"] = _live_env_baseline_from_meta(env_meta)

    recorded_root = resolved_retain_root / "recorded"
    for gate in _recorded_gate_specs():
        gate_root = recorded_root / gate["lane_id"]
        print(f"[openclaw-deployment-readiness] START {gate['label']}")
        result = _run_recorded_gate(gate=gate, retain_root=gate_root, env=recorded_env)
        summary["recorded_results"][gate["lane_id"]] = result
        summary["evidence_roots"]["recorded"][gate["lane_id"]] = str(gate_root)
        _write_bundle_summary(summary, resolved_retain_root)
        if result["status"] != "passed":
            _set_failure(summary, failing_gate=gate["lane_id"], failing_stage="recorded_smoke")
            summary["exit_code"] = int(result["exit_code"])
            _write_bundle_summary(summary, resolved_retain_root)
            print(f"[openclaw-deployment-readiness] FAIL {gate['label']}")
            return summary
        print(f"[openclaw-deployment-readiness] PASS {gate['label']}")

    live_root = resolved_retain_root / LIVE_GATE_ID
    print("[openclaw-deployment-readiness] START market_observer live deployment")
    live_result = _run_live_gate(
        execution_permit=execution_permit,
        trust_root_dir=trust_root_dir,
        retain_root=live_root,
        env=live_env,
    )
    summary["live_result"] = live_result.get("live_summary")
    summary["market_observer_live_summary_path"] = live_result["summary_path"]
    summary["evidence_roots"]["market_observer_live"] = str(live_root)
    summary["live_gate_result"] = {
        "status": live_result["status"],
        "exit_code": live_result["exit_code"],
        "stdout_path": live_result["stdout_path"],
        "stderr_path": live_result["stderr_path"],
        "result_path": live_result["result_path"],
    }
    _write_bundle_summary(summary, resolved_retain_root)
    if live_result["status"] != "passed":
        _set_failure(
            summary,
            failing_gate=LIVE_GATE_ID,
            failing_stage=_extract_live_failure_stage(live_result.get("live_summary")),
        )
        summary["exit_code"] = int(live_result["exit_code"])
        if live_result.get("live_summary") is None:
            _write_bundle_failure_snapshot(
                resolved_retain_root,
                error="market_observer live gate failed before live_smoke_summary.json was available.",
                execution_permit=execution_permit,
                trust_root_dir=trust_root_dir,
                summary=summary,
            )
        _write_bundle_summary(summary, resolved_retain_root)
        print("[openclaw-deployment-readiness] FAIL market_observer live deployment")
        return summary

    print("[openclaw-deployment-readiness] PASS market_observer live deployment")
    for gate in _archetype_live_gate_specs():
        gate_root = resolved_retain_root / gate["gate_id"]
        print(f"[openclaw-deployment-readiness] START {gate['label']}")
        gate_result = _run_archetype_live_gate(
            gate=gate,
            execution_permit=execution_permit,
            trust_root_dir=trust_root_dir,
            retain_root=gate_root,
            env=live_env,
        )
        summary[f"{gate['gate_id']}_result"] = gate_result.get("bundle_summary")
        summary[f"{gate['gate_id']}_gate_result"] = {
            "status": gate_result["status"],
            "exit_code": gate_result["exit_code"],
            "stdout_path": gate_result["stdout_path"],
            "stderr_path": gate_result["stderr_path"],
            "result_path": gate_result["result_path"],
        }
        summary[f"{gate['gate_id']}_summary_path"] = gate_result["summary_path"]
        summary["evidence_roots"][gate["gate_id"]] = str(gate_root)
        _write_bundle_summary(summary, resolved_retain_root)
        if gate_result["status"] != "passed":
            _set_failure(
                summary,
                failing_gate=gate["gate_id"],
                failing_stage=gate_result.get("failing_stage"),
            )
            summary["exit_code"] = int(gate_result["exit_code"])
            if gate_result.get("bundle_summary") is None:
                _write_bundle_failure_snapshot(
                    resolved_retain_root,
                    error=f"{gate['label']} failed before bundle_summary.json was available.",
                    execution_permit=execution_permit,
                    trust_root_dir=trust_root_dir,
                    summary=summary,
                )
            _write_bundle_summary(summary, resolved_retain_root)
            print(f"[openclaw-deployment-readiness] FAIL {gate['label']}")
            return summary
        print(f"[openclaw-deployment-readiness] PASS {gate['label']}")

    summary["status"] = "success"
    summary["completed_at_utc"] = _utc_now()
    summary["exit_code"] = 0
    _write_bundle_summary(summary, resolved_retain_root)
    return summary


def _build_live_env(*, base_env: dict[str, str] | None) -> tuple[dict[str, str], dict[str, Any]]:
    env = build_sanitized_env(base_env=base_env)
    source_env = os.environ if base_env is None else base_env
    for name in PASS_THROUGH_ENV:
        value = source_env.get(name)
        if value is not None:
            env[name] = value
    return resolve_openclaw_bundle_operator_env(env, fail_closed=False)


def _build_recorded_env(*, base_env: dict[str, str] | None) -> dict[str, str]:
    env = build_sanitized_env(base_env=base_env)
    for base_url_name, model_name_name, api_key_name in openclaw_bundle_live_env_specs().values():
        timeout_name = base_url_name.replace("_BASE_URL", "_TIMEOUT_SECONDS")
        for name in (base_url_name, model_name_name, api_key_name, timeout_name):
            pop_env_aliases(env, name)
    env.pop("OPENCLAW", None)
    env.pop("OPENCLAW_BASE_URL", None)
    env.pop("OPENCLAW_MODEL_NAME", None)
    env.pop("OPENCLAW_MODEL_TIMEOUT_SECONDS", None)
    return env


def _live_env_baseline_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "live_env_mode": meta.get("live_env_mode"),
        "openclaw_mapping_used_by_lane": dict(meta.get("openclaw_mapping_used_by_lane", {})),
        "dedicated_env_preserved_by_lane": dict(meta.get("dedicated_env_preserved_by_lane", {})),
        "defaulted_base_url_by_lane": dict(meta.get("defaulted_base_url_by_lane", {})),
        "defaulted_model_name_by_lane": dict(meta.get("defaulted_model_name_by_lane", {})),
        "defaulted_timeout_by_lane": dict(meta.get("defaulted_timeout_by_lane", {})),
        "shared_openclaw_base_url": meta.get("shared_openclaw_base_url"),
        "shared_openclaw_model_name": meta.get("shared_openclaw_model_name"),
        "shared_openclaw_model_timeout_seconds": meta.get("shared_openclaw_model_timeout_seconds"),
    }


def _recorded_gate_specs() -> list[dict[str, Any]]:
    return [
        _recorded_gate("market_observer", "market_observer recorded deployment smoke"),
        _recorded_gate("evidence_agent", "evidence_agent recorded deployment smoke"),
        _recorded_gate("risk_signal_agent", "risk_signal_agent recorded deployment smoke"),
        _recorded_gate("attention_allocator", "attention_allocator recorded deployment smoke"),
        _recorded_gate("research_synthesizer", "research_synthesizer recorded deployment smoke"),
        _recorded_gate("research_lead", "research_lead recorded deployment smoke"),
        _recorded_gate("risk_governance_agent", "risk_governance_agent recorded deployment smoke"),
        _recorded_gate("validation_agent", "validation_agent recorded deployment smoke"),
    ]


def _archetype_live_gate_specs() -> list[dict[str, Any]]:
    return [
        _archetype_live_gate(
            CONTINUE_EXISTING_LIVE_GATE_ID,
            "continue-existing live readiness",
            VERIFY_DIR / "run_openclaw_continue_existing_live_readiness.py",
        ),
        _archetype_live_gate(
            REVIEW_GATED_LIVE_GATE_ID,
            "review-gated live readiness",
            VERIFY_DIR / "run_openclaw_review_gated_live_readiness.py",
        ),
    ]


def _recorded_gate(lane_id: str, label: str) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "label": label,
        "command": [
            sys.executable,
            str(VERIFY_DIR / f"run_openclaw_{lane_id}_smoke.py"),
        ],
    }


def _archetype_live_gate(gate_id: str, label: str, script_path: Path) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "label": label,
        "command": [
            sys.executable,
            str(script_path),
        ],
    }


def _run_recorded_gate(*, gate: dict[str, Any], retain_root: Path, env: dict[str, str]) -> dict[str, Any]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "stdout.log"
    stderr_path = retain_root / "stderr.log"
    result_path = retain_root / "result.json"
    completed = subprocess.run(
        gate["command"],
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    result = {
        "lane_id": gate["lane_id"],
        "label": gate["label"],
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, result)
    return result


def _run_archetype_live_gate(
    *,
    gate: dict[str, Any],
    execution_permit: Path,
    trust_root_dir: Path | None,
    retain_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "bundle_stdout.log"
    stderr_path = retain_root / "bundle_stderr.log"
    result_path = retain_root / "bundle_result.json"
    summary_path = retain_root / "bundle_summary.json"
    command = [
        *gate["command"],
        "--execution-permit",
        str(execution_permit),
        "--retain-root",
        str(retain_root),
    ]
    if trust_root_dir is not None:
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
    bundle_summary = _safe_load_json(summary_path)
    result = {
        "gate_id": gate["gate_id"],
        "label": gate["label"],
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "bundle_summary": bundle_summary,
        "failing_stage": None if bundle_summary is None else bundle_summary.get("failing_stage"),
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, result)
    return result


def _run_live_gate(
    *,
    execution_permit: Path,
    trust_root_dir: Path | None,
    retain_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    retain_root.mkdir(parents=True, exist_ok=True)
    stdout_path = retain_root / "bundle_stdout.log"
    stderr_path = retain_root / "bundle_stderr.log"
    result_path = retain_root / "bundle_result.json"
    summary_path = retain_root / "live_smoke_summary.json"
    command = [
        sys.executable,
        str(VERIFY_DIR / "run_openclaw_market_observer_smoke.py"),
        "--live-smoke",
        "--execution-permit",
        str(execution_permit),
        "--retain-root",
        str(retain_root),
    ]
    if trust_root_dir is not None:
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

    live_summary = _safe_load_json(summary_path)
    result = {
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path),
        "summary_path": str(summary_path),
        "live_summary": live_summary,
        "failing_stage": _extract_live_failure_stage(live_summary),
        "evidence_root": str(retain_root),
    }
    _write_json(result_path, result)
    return result


def _extract_live_failure_stage(live_summary: dict[str, Any] | None) -> str | None:
    if not isinstance(live_summary, dict):
        return None
    stages = live_summary.get("stages")
    if not isinstance(stages, dict):
        return None
    for stage_key, stage_value in stages.items():
        if not isinstance(stage_value, dict):
            continue
        if stage_value.get("status") == "failed":
            label = stage_value.get("label")
            if isinstance(label, str) and label.strip():
                return label
            return stage_key
    return None


def _prepare_retain_root(retain_root: Path | None) -> Path:
    if retain_root is not None:
        retain_root.mkdir(parents=True, exist_ok=True)
        return retain_root.resolve()
    return Path(tempfile.mkdtemp(prefix="ecodr_")).resolve()


def _initial_summary(retain_root: Path) -> dict[str, Any]:
    return {
        "status": "pending",
        "retain_root": str(retain_root),
        "generated_at_utc": _utc_now(),
        "completed_at_utc": None,
        "recorded_results": {},
        "live_result": None,
        "live_gate_result": None,
        "live_env_baseline": None,
        "continue_existing_live_result": None,
        "continue_existing_live_gate_result": None,
        "continue_existing_live_summary_path": str(retain_root / CONTINUE_EXISTING_LIVE_GATE_ID / "bundle_summary.json"),
        "review_gated_live_result": None,
        "review_gated_live_gate_result": None,
        "review_gated_live_summary_path": str(retain_root / REVIEW_GATED_LIVE_GATE_ID / "bundle_summary.json"),
        "failing_gate": None,
        "failing_stage": None,
        "market_observer_live_summary_path": str(retain_root / LIVE_GATE_ID / "live_smoke_summary.json"),
        "evidence_roots": {
            "recorded": {},
            "market_observer_live": str(retain_root / LIVE_GATE_ID),
            CONTINUE_EXISTING_LIVE_GATE_ID: str(retain_root / CONTINUE_EXISTING_LIVE_GATE_ID),
            REVIEW_GATED_LIVE_GATE_ID: str(retain_root / REVIEW_GATED_LIVE_GATE_ID),
        },
        "exit_code": 1,
    }


def _set_failure(summary: dict[str, Any], *, failing_gate: str, failing_stage: str | None) -> None:
    summary["status"] = "failed"
    summary["completed_at_utc"] = _utc_now()
    summary["failing_gate"] = failing_gate
    summary["failing_stage"] = failing_stage


def _write_bundle_summary(summary: dict[str, Any], retain_root: Path) -> None:
    _write_json(
        retain_root / "bundle_summary.json",
        with_evidence_metadata(
            summary,
            evidence_family="openclaw_deployment_gate",
            contract_version="openclaw_deployment_gate.v1",
            repo_root=ROOT,
        ),
    )


def _write_bundle_failure_snapshot(
    retain_root: Path,
    *,
    error: str,
    execution_permit: Path | None,
    trust_root_dir: Path | None,
    summary: dict[str, Any],
) -> None:
    snapshot = {
        "error": error,
        "generated_at_utc": _utc_now(),
        "execution_permit": None if execution_permit is None else str(execution_permit),
        "trust_root_dir": None if trust_root_dir is None else str(trust_root_dir),
        "bundle_summary_path": str(retain_root / "bundle_summary.json"),
        "summary": summary,
    }
    _write_json(retain_root / "failure_snapshot.json", snapshot)


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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
