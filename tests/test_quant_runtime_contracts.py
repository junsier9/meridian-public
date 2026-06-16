from __future__ import annotations

import contextlib
import json
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_helpers import ROOT


class QuantRuntimeContractTests(unittest.TestCase):
    def _load_cycle_wrapper_module(self):
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_research_cycle.py"
        spec = importlib.util.spec_from_file_location("test_run_quant_research_cycle_wrapper", script_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_quant_package_lazy_import_is_safe_in_repo_venv(self) -> None:
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            self.skipTest("repo .venv is unavailable")
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(ROOT)!r}); "
            f"sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "import enhengclaw.quant_research as qr; "
            "exported = dir(qr); "
            "print('run_quant_research_cycle' in exported); "
            "print('export_passed_alphas_to_workbench' in exported)"
        )
        result = subprocess.run([str(venv_python), "-c", code], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["True", "False"])

    def test_universe_input_producer_help_runs_in_repo_venv(self) -> None:
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            self.skipTest("repo .venv is unavailable")
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_universe_input_producer.py"
        result = subprocess.run(
            [str(venv_python), str(script_path), "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_quant_coinapi_spot_sync_help_runs_in_repo_venv(self) -> None:
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            self.skipTest("repo .venv is unavailable")
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_coinapi_spot_sync.py"
        result = subprocess.run(
            [str(venv_python), str(script_path), "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_quant_research_cycle_help_exposes_structured_summary_paths(self) -> None:
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            self.skipTest("repo .venv is unavailable")
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_research_cycle.py"
        result = subprocess.run(
            [str(venv_python), str(script_path), "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--summary-out", result.stdout)
        self.assertIn("--failure-summary-out", result.stdout)

    def test_quant_research_cycle_wrapper_writes_structured_failure_summary(self) -> None:
        module = self._load_cycle_wrapper_module()

        def _raise_failure(**_: object) -> dict[str, object]:
            raise AttributeError("'DataFrame' object has no attribute 'columns'")

        module.run_quant_research_cycle = _raise_failure
        with tempfile.TemporaryDirectory(prefix="quant_cycle_wrapper_failure_") as tmpdir:
            failure_summary_path = Path(tmpdir) / "failure.summary.json"
            stderr_buffer = io.StringIO()
            with contextlib.redirect_stderr(stderr_buffer):
                exit_code = module.main(
                    [
                        "--as-of",
                        "2026-04-23",
                        "--failure-summary-out",
                        str(failure_summary_path),
                    ]
                )
            self.assertEqual(exit_code, 1)
            failure_summary = json.loads(failure_summary_path.read_text(encoding="utf-8"))
            self.assertEqual(failure_summary["artifact_family"], "quant_research_cycle_failure")
            self.assertEqual(failure_summary["status"], "failed")
            self.assertEqual(failure_summary["error"]["exception_type"], "AttributeError")
            self.assertIn("'DataFrame' object has no attribute 'columns'", failure_summary["error"]["message"])
            self.assertIn("failure_summary_path=", stderr_buffer.getvalue())

    def test_quant_research_cycle_wrapper_writes_structured_success_summary(self) -> None:
        module = self._load_cycle_wrapper_module()

        def _return_summary(**_: object) -> dict[str, object]:
            return {
                "artifact_family": "quant_research_cycle",
                "contract_version": "quant_research_cycle.v1",
                "status": "success",
                "input_watermarks": {},
            }

        module.run_quant_research_cycle = _return_summary
        with tempfile.TemporaryDirectory(prefix="quant_cycle_wrapper_success_") as tmpdir:
            summary_path = Path(tmpdir) / "child.summary.json"
            stdout_buffer = io.StringIO()
            with contextlib.redirect_stdout(stdout_buffer):
                exit_code = module.main(
                    [
                        "--as-of",
                        "2026-04-23",
                        "--summary-out",
                        str(summary_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["artifact_family"], "quant_research_cycle")
            self.assertIn("\"artifact_family\": \"quant_research_cycle\"", stdout_buffer.getvalue())

    def test_quant_strategy_proposal_cycle_help_exposes_as_of_and_legacy_week_of(self) -> None:
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            self.skipTest("repo .venv is unavailable")
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_strategy_proposal_cycle.py"
        result = subprocess.run(
            [str(venv_python), str(script_path), "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--as-of", result.stdout)
        self.assertIn("--week-of", result.stdout)

    def test_quantagent_shadow_proposal_cycle_help_runs_in_repo_venv(self) -> None:
        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            self.skipTest("repo .venv is unavailable")
        script_path = ROOT / "scripts" / "quant_research" / "run_quantagent_shadow_proposal_cycle.py"
        result = subprocess.run(
            [str(venv_python), str(script_path), "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--base-strategy-id", result.stdout)
        self.assertIn("--spot-ohlcv-external-root", result.stdout)

    def test_quant_strategy_proposal_cycle_wrapper_reports_frozen_surface(self) -> None:
        script_path = ROOT / "scripts" / "quant_research" / "run_quant_strategy_proposal_cycle.py"
        env = dict(os.environ)
        env["SOURCE_COMMIT_SHA"] = "abc123"
        result = subprocess.run(
            [sys.executable, str(script_path), "--as-of", "2026-04-23"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 78, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["error_code"], "legacy_quant_surface_frozen")

    def test_quant_repo_health_wrapper_reports_frozen_surface(self) -> None:
        script_path = ROOT / "scripts" / "verify" / "run_quant_repo_health_guard.py"
        env = dict(os.environ)
        env["SOURCE_COMMIT_SHA"] = "abc123"
        result = subprocess.run(
            [sys.executable, str(script_path), "--as-of", "2026-04-23"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 78, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["error_code"], "legacy_quant_surface_frozen")

    def test_bootstrap_script_check_only_reports_stable_contract(self) -> None:
        script_path = ROOT / "scripts" / "quant_research" / "bootstrap_quant_runtime.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "--check-only"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(result.stdout)
        self.assertIn(payload["status"], {"success", "scientific_python_runtime_missing"})
        self.assertIn("repo_root", payload)
        self.assertIn("venv_python", payload)
        self.assertIn("scientific_stack_ready", payload)
        self.assertIn("bootstrap_script", payload)
        self.assertEqual(payload["mode"], "check_only")

    def test_quant_runner_preflight_contracts_are_explicit(self) -> None:
        helper_text = (ROOT / "scripts" / "common" / "openclaw_scheduled_task_helpers.ps1").read_text(encoding="utf-8")
        self.assertIn("function Get-OpenClawRepoVenvPythonExecutable", helper_text)
        self.assertIn("function Assert-OpenClawScientificPythonRuntime", helper_text)
        self.assertIn("scientific_python_runtime_missing", helper_text)
        self.assertIn("bootstrap_quant_runtime.py", helper_text)

        for relative_path in (
            "scripts/quant_research/run_openclaw_quant_derivatives_sync_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_research_daily_cycle_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_strategy_proposal_cycle_runner.ps1",
        ):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("Assert-OpenClawScientificPythonRuntime", text)
            self.assertIn("exit 86", text)
        proposal_runner_text = (ROOT / "scripts" / "quant_research" / "run_openclaw_quant_strategy_proposal_cycle_runner.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$AsOf", proposal_runner_text)
        self.assertIn("[string]$WeekOf", proposal_runner_text)
        self.assertIn("LEGACY_SURFACE_FROZEN", proposal_runner_text)

        for relative_path in (
            "scripts/quant_research/run_openclaw_quant_universe_input_producer_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_universe_freeze_runner.ps1",
            "scripts/quant_research/run_openclaw_quant_coinapi_spot_sync_runner.ps1",
        ):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("Get-OpenClawRepoVenvPythonExecutable", text)
            self.assertNotIn("Assert-OpenClawScientificPythonRuntime", text)


if __name__ == "__main__":
    unittest.main()
