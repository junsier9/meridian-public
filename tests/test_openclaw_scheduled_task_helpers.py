from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT


HELPER_PATH = ROOT / "scripts" / "common" / "openclaw_scheduled_task_helpers.ps1"


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "PowerShell tests require Windows")
class OpenClawScheduledTaskHelperTests(unittest.TestCase):
    def _run_powershell(self, script: str, *, env: dict[str, str] | None = None) -> str:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return completed.stdout.strip()

    def test_summary_path_expands_powershell_and_percent_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_helper_env_") as tmpdir:
            localappdata = str((Path(tmpdir) / "LocalAppData").resolve())
            env = os.environ.copy()
            env["LOCALAPPDATA"] = localappdata
            script = rf"""
$env:LOCALAPPDATA = '{localappdata}';
. '{HELPER_PATH}';
$powershellEntry = [pscustomobject]@{{ success_discovery_command = 'Get-Content "$env:LOCALAPPDATA\EnhengClaw\runner.summary.json"' }};
$percentEntry = [pscustomobject]@{{ success_discovery_command = 'Get-Content "%LOCALAPPDATA%\EnhengClaw\runner.summary.json"' }};
[pscustomobject]@{{
    powershell = (Resolve-OpenClawScheduledTaskSummaryPath -TaskEntry $powershellEntry)
    percent = (Resolve-OpenClawScheduledTaskSummaryPath -TaskEntry $percentEntry)
}} | ConvertTo-Json -Compress
"""
            payload = json.loads(self._run_powershell(script, env=env))
            expected = str(Path(localappdata) / "EnhengClaw" / "runner.summary.json")
            self.assertEqual(payload["powershell"], expected)
            self.assertEqual(payload["percent"], expected)

    def test_immediate_summary_helper_supports_skip_and_retry_runner_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_helper_summary_") as tmpdir:
            runner_root = Path(tmpdir) / "runner"
            log_path = runner_root / "runner.log"
            runner_root.mkdir(parents=True, exist_ok=True)
            script = rf"""
. '{HELPER_PATH}';
$taskEntry = [pscustomobject]@{{
    task_key = 'research_intake_cycle'
    task_name = 'OpenClaw Research Intake Cycle'
    runner_script = 'scripts\openclaw\run_openclaw_research_intake_cycle_runner.ps1'
    produces_artifact_family = 'openclaw_research_intake_cycle'
    upstream_dependencies = @('quant_repo_health_guard', 'structural_research_scan')
}};
$skipSummary = Write-OpenClawScheduledTaskImmediateSummary -RepoRoot '{ROOT}' -TaskEntry $taskEntry -RunnerRoot '{runner_root}' -ExitCode 0 -LogPath '{log_path}' -StdoutPath '{runner_root / "skip.stdout.tmp"}';
$skipPayload = Get-Content -LiteralPath $skipSummary -Raw | ConvertFrom-Json;
$taskEntry.task_key = 'research_intake_cycle_retry';
$taskEntry.task_name = 'OpenClaw Research Intake Cycle Retry';
$retrySummary = Write-OpenClawScheduledTaskImmediateSummary -RepoRoot '{ROOT}' -TaskEntry $taskEntry -RunnerRoot '{runner_root}' -ExitCode 75 -LogPath '{log_path}' -StdoutPath '{runner_root / "retry.stdout.tmp"}';
[pscustomobject]@{{
    skip = $skipPayload
    retry = (Get-Content -LiteralPath $retrySummary -Raw | ConvertFrom-Json)
}} | ConvertTo-Json -Depth 8
"""
            payload = json.loads(self._run_powershell(script))
            self.assertEqual(payload["skip"]["exit_status"], 0)
            self.assertTrue(payload["skip"]["success"])
            self.assertEqual(payload["retry"]["exit_status"], 75)
            self.assertFalse(payload["retry"]["success"])
            self.assertEqual(payload["retry"]["task_key"], "research_intake_cycle_retry")
            self.assertEqual(payload["retry"]["artifact_family"], "openclaw_research_intake_cycle")
            self.assertIsNotNone(payload["retry"]["produced_at_utc"])

    def test_runner_summary_preserves_upstream_dependencies_when_child_summary_adds_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_helper_upstream_") as tmpdir:
            runner_root = Path(tmpdir) / "runner"
            log_path = runner_root / "runner.log"
            stdout_path = runner_root / "child.stdout.json"
            runner_root.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text(
                json.dumps(
                    {
                        "artifact_family": "quant_strategy_proposal_cycle",
                        "contract_version": "quant_discovery_weekly_cycle.v1",
                        "upstream_versions": {
                            "weekly_discovery_screen_budget": 64,
                            "weekly_discovery_full_validation_budget": 32,
                        },
                    }
                ),
                encoding="utf-8",
            )
            script = rf"""
. '{HELPER_PATH}';
$taskEntry = [pscustomobject]@{{
    task_key = 'quant_strategy_proposal_cycle'
    task_name = 'OpenClaw Quant Exploration Daily Full Cycle'
    runner_script = 'scripts\quant_research\run_openclaw_quant_strategy_proposal_cycle_runner.ps1'
    produces_artifact_family = 'quant_strategy_proposal_cycle'
    upstream_dependencies = @('quant_repo_health_guard')
}};
$summaryPath = Write-OpenClawScheduledTaskSummary -RepoRoot '{ROOT}' -TaskEntry $taskEntry -RunnerRoot '{runner_root}' -ExitCode 0 -LogPath '{log_path}' -StdoutPath '{stdout_path}';
Get-Content -LiteralPath $summaryPath -Raw
"""
            payload = json.loads(self._run_powershell(script))
            self.assertEqual(payload["upstream_versions"]["upstream_dependencies"], ["quant_repo_health_guard"])
            self.assertEqual(payload["upstream_versions"]["weekly_discovery_screen_budget"], 64)
            self.assertEqual(payload["upstream_versions"]["weekly_discovery_full_validation_budget"], 32)

    def test_runner_summary_prefers_structured_child_and_failure_summary_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_helper_diagnostics_") as tmpdir:
            runner_root = Path(tmpdir) / "runner"
            log_path = runner_root / "runner.log"
            stdout_path = runner_root / "child.stdout.txt"
            child_summary_path = runner_root / "child.summary.json"
            failure_summary_path = runner_root / "failure.summary.json"
            runner_root.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text("not-json", encoding="utf-8")
            child_summary_path.write_text(
                json.dumps(
                    {
                        "artifact_family": "quant_research_cycle",
                        "contract_version": "quant_research_cycle.v1",
                        "input_watermarks": {"quant_derivatives_sync_produced_at_utc": "2026-04-23T06:36:03Z"},
                    }
                ),
                encoding="utf-8",
            )
            failure_summary_path.write_text(
                json.dumps(
                    {
                        "artifact_family": "quant_research_cycle_failure",
                        "contract_version": "quant_research_cycle.failure.v1",
                        "status": "failed",
                        "error": {"exception_type": "AttributeError", "message": "'DataFrame' object has no attribute 'columns'"},
                    }
                ),
                encoding="utf-8",
            )
            script = rf"""
. '{HELPER_PATH}';
$taskEntry = [pscustomobject]@{{
    task_key = 'quant_research_daily_cycle'
    task_name = 'OpenClaw Quant Monitoring Daily Cycle'
    runner_script = 'scripts\quant_research\run_openclaw_quant_research_daily_cycle_runner.ps1'
    produces_artifact_family = 'quant_research_cycle'
    upstream_dependencies = @('binance_ohlcv_sync', 'quant_derivatives_sync')
}};
$summaryPath = Write-OpenClawScheduledTaskSummary -RepoRoot '{ROOT}' -TaskEntry $taskEntry -RunnerRoot '{runner_root}' -ExitCode 1 -LogPath '{log_path}' -StdoutPath '{stdout_path}' -ChildSummaryPath '{child_summary_path}' -FailureSummaryPath '{failure_summary_path}';
Get-Content -LiteralPath $summaryPath -Raw
"""
            payload = json.loads(self._run_powershell(script))
            self.assertEqual(payload["exit_status"], 1)
            self.assertFalse(payload["success"])
            self.assertEqual(payload["child_summary"]["artifact_family"], "quant_research_cycle")
            self.assertEqual(payload["failure_summary"]["artifact_family"], "quant_research_cycle_failure")
            self.assertEqual(payload["failure_summary"]["error"]["exception_type"], "AttributeError")
            self.assertEqual(payload["child_summary_path"], str(child_summary_path))
            self.assertEqual(payload["failure_summary_path"], str(failure_summary_path))


if __name__ == "__main__":
    unittest.main()
