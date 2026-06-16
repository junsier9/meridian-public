from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
VERIFY = ROOT / "scripts" / "verify"


def main() -> int:
    commands = [
        ("phase0 trust root", [sys.executable, str(VERIFY / "phase0_trust_root.py")]),
        ("phase1 runtime worker boundary", [sys.executable, str(VERIFY / "phase1_runtime_worker_boundary.py")]),
        ("phase2 provider helper boundary", [sys.executable, str(VERIFY / "phase2_provider_helper_boundary.py")]),
        ("phase3 lease and interrupts", [sys.executable, str(VERIFY / "phase3_lease_and_interrupts.py")]),
        ("phase4 legacy api retirement", [sys.executable, str(VERIFY / "phase4_legacy_api_retirement.py")]),
        ("phase5 owner verification boundary", [sys.executable, str(VERIFY / "phase5_owner_verification_boundary.py")]),
        ("shadow ingestion controller boundary", [sys.executable, str(ROOT / "scripts" / "verify_shadow_ingestion_controller_boundary.py")]),
        (
            "fail-closed boundary tests",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_boundary_fail_closed",
                "tests.test_execution_control_enforcement",
                "tests.test_shadow_ingestion",
                "tests.test_data_health_gate",
            ],
        ),
        (
            "real-24h, evidence, and documentation contracts",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_real_24h_shadow_bundle",
                "tests.test_real_shadow_acceptance",
                "tests.test_document_contracts",
                "tests.test_static_contracts",
                "tests.test_evidence_contracts",
                "tests.test_scheduled_task_contracts",
                "tests.test_binance_http",
            ],
        ),
        (
            "quant bridge summary contract",
            [sys.executable, str(VERIFY / "run_bridge_summary_contract_check.py")],
        ),
        (
            "quant research core",
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_quant_research_governance",
                "tests.test_quant_research_lab",
                "tests.test_quant_research_integrity",
                "tests.test_binance_ohlcv_history",
                "tests.test_research_workbench_queue_dashboard",
                "tests.test_openclaw_research_intake_cycle",
            ],
        ),
        ("final redteam acceptance", [sys.executable, str(ROOT / "scripts" / "redteam" / "final_boundary_acceptance.py")]),
    ]
    env = _build_env()
    for label, command in commands:
        print(f"[boundary-gate] START {label}")
        completed = subprocess.run(
            command,
            check=False,
            cwd=ROOT,
            env=env,
        )
        if completed.returncode != 0:
            print(f"[boundary-gate] FAIL {label} (exit={completed.returncode})")
            return completed.returncode
        print(f"[boundary-gate] PASS {label}")
    print("[boundary-gate] ALL GATES PASSED")
    return 0


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


if __name__ == "__main__":
    raise SystemExit(main())
