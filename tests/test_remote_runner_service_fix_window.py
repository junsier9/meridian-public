from __future__ import annotations

import hashlib
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "scripts" / "remote_runner_service_fix_window"
DROPINS = PACKAGE / "systemd-dropins"
CONFIG = (
    PACKAGE
    / "config"
    / "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml"
)
POSITION_REFERENCE_APPLY = PACKAGE / "apply_meridian_position_reference_equivalent.py"
PROOF_DRIVER_CHECKS = PACKAGE / "proof_driver_checks.py"


class RemoteRunnerServiceFixWindowTests(unittest.TestCase):
    def test_expected_fix_window_files_exist(self) -> None:
        expected = [
            PACKAGE / "README.md",
            PACKAGE / "CHECKLIST.md",
            PACKAGE / "REVIEW_SUMMARY.md",
            PACKAGE / "PACKAGE_SHA256SUMS.txt",
            PACKAGE / "precheck_meridian_path_resolution_readonly.sh",
            PACKAGE / "verify_meridian_path_dropins.sh",
            PACKAGE / "rollback_meridian_path_dropins_dry_run.sh",
            POSITION_REFERENCE_APPLY,
            PROOF_DRIVER_CHECKS,
            CONFIG,
            DROPINS / "meridian-alpha-mainnet-supervisor-live.service.d" / "10-meridian-path.conf",
            DROPINS / "meridian-alpha-mainnet-health-monitor.service.d" / "10-meridian-path.conf",
        ]
        for path in expected:
            with self.subTest(path=path):
                self.assertTrue(path.exists(), path)

    def test_service_dropins_force_meridian_python_and_absolute_config_paths(self) -> None:
        for path in sorted(DROPINS.rglob("*.conf")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("ExecStart=\n", text)
                self.assertIn("/root/meridian_alpha_live_runner/bin/with-live-env", text)
                self.assertIn("/usr/bin/env", text)
                self.assertIn("PYTHONPATH=/root/meridian_alpha_live_runner/repo/src", text)
                self.assertIn("VIRTUAL_ENV=/root/meridian_alpha_live_runner/venv", text)
                self.assertIn("/root/meridian_alpha_live_runner/venv/bin/python", text)
                self.assertIn("/root/meridian_alpha_live_runner/repo/scripts/live_trading/", text)
                self.assertIn(
                    "/root/meridian_alpha_live_runner/repo/config/live_trading/"
                    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_"
                    "meridian_handoff_observation.yaml",
                    text,
                )
                self.assertNotIn("/root/enhengclaw_live_runner", text)
                self.assertNotIn(" python scripts/", text)
                self.assertNotIn("--config config/", text)

    def test_handoff_observation_config_is_no_live_delta_and_meridian_routed(self) -> None:
        text = CONFIG.read_text(encoding="utf-8")
        self.assertIn("repo_root: /root/meridian_alpha_live_runner/repo", text)
        self.assertIn("env_wrapper: /root/meridian_alpha_live_runner/bin/with-live-env", text)
        self.assertIn("python_path: /root/meridian_alpha_live_runner/venv/bin/python", text)
        self.assertIn("systemd_timer_name: meridian-alpha-mainnet-supervisor-live.timer", text)
        self.assertIn("recent_run_count: 1", text)
        self.assertIn("trading_enabled: false", text)
        self.assertIn("allow_live_delta_when_armed: false", text)
        self.assertIn("allow_multiphase_live_delta: false", text)
        self.assertIn("no_order_expected: true", text)
        self.assertIn("auto_rearm_live_delta: false", text)
        self.assertNotIn("/root/enhengclaw_live_runner", text)
        self.assertNotIn("systemd_timer_name: enhengclaw-mainnet-supervisor-live.timer", text)

    def test_acceptance_docs_reject_operator_paused_success_semantics(self) -> None:
        combined = "\n".join(
            [
                (PACKAGE / "README.md").read_text(encoding="utf-8"),
                (PACKAGE / "REVIEW_SUMMARY.md").read_text(encoding="utf-8"),
                (PACKAGE / "CHECKLIST.md").read_text(encoding="utf-8"),
            ]
        )
        self.assertIn("operator_paused=false", combined)
        self.assertIn("live_delta_armed=false", combined)
        self.assertIn("auto-rearm is disabled", combined)
        self.assertIn("no-live-delta observation", combined)
        self.assertNotIn("Operator pause remains true after both cycles", combined)

    def test_read_only_scripts_do_not_change_systemd_or_filesystem_state(self) -> None:
        prohibited = [
            "systemctl enable",
            "systemctl disable",
            "systemctl start",
            "systemctl stop",
            "systemctl restart",
            "systemctl daemon-reload",
            "install -m",
            " cp ",
            " rm ",
            " mv ",
        ]
        for script_name in [
            "precheck_meridian_path_resolution_readonly.sh",
            "verify_meridian_path_dropins.sh",
        ]:
            text = (PACKAGE / script_name).read_text(encoding="utf-8")
            with self.subTest(script=script_name):
                for token in prohibited:
                    self.assertNotIn(token, text)

    def test_rollback_script_is_dry_run_guarded(self) -> None:
        text = (PACKAGE / "rollback_meridian_path_dropins_dry_run.sh").read_text(encoding="utf-8")
        self.assertIn("EXECUTE=0", text)
        self.assertIn("ROLLBACK_MERIDIAN_PATH_FIX_WINDOW=confirm-remove-dropins", text)
        self.assertIn("refusing execute mode", text)

    def test_position_reference_apply_driver_preserves_zero_values(self) -> None:
        spec = importlib.util.spec_from_file_location("position_reference_apply", POSITION_REFERENCE_APPLY)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.int_field({"open_order_count": 0}, "open_order_count"), 0)
        self.assertEqual(module.int_field({"orders_submitted": 0}, "orders_submitted"), 0)
        text = POSITION_REFERENCE_APPLY.read_text(encoding="utf-8")
        self.assertNotIn('summary.get("open_order_count") or -1', text)
        self.assertNotIn('summary.get("orders_submitted") or -1', text)

    def test_proof_driver_health_timer_check_uses_nested_summary_shape(self) -> None:
        spec = importlib.util.spec_from_file_location("proof_driver_checks", PROOF_DRIVER_CHECKS)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        summary = {
            "status": "mainnet_health_monitor_passed",
            "critical_alert_count": 0,
            "no_order_expected": False,
            "live_delta_armed_after": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "systemd_timer_name": "wrong-top-level-name.timer",
            "systemd_timer_status": {
                "status": "ok",
                "timer_name": "meridian-alpha-mainnet-supervisor-live.timer",
            },
            "supervisor_runs": [
                {
                    "open_order_count": 0,
                    "orders_submitted": 4,
                    "fill_count": 4,
                }
            ],
        }

        self.assertEqual(module.int_field({"open_order_count": 0}, "open_order_count", default=-1), 0)
        self.assertEqual(module.health_timer_name(summary), "meridian-alpha-mainnet-supervisor-live.timer")
        checks = module.build_post_arm_health_checks(summary)
        self.assertTrue(all(checks.values()), checks)

        text = PROOF_DRIVER_CHECKS.read_text(encoding="utf-8")
        self.assertIn('timer_status.get("timer_name")', text)
        self.assertNotIn('summary.get("systemd_timer_name") ==', text)

    def test_proof_driver_prearm_baseline_accepts_disarmed_no_order_health(self) -> None:
        spec = importlib.util.spec_from_file_location("proof_driver_checks", PROOF_DRIVER_CHECKS)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        summary = {
            "status": "mainnet_health_monitor_passed",
            "critical_alert_count": 0,
            "no_order_expected": True,
            "live_delta_armed_after": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "systemd_timer_status": {
                "status": "ok",
                "timer_name": "meridian-alpha-mainnet-supervisor-live.timer",
            },
            "supervisor_runs": [
                {
                    "open_order_count": 0,
                    "orders_submitted": 0,
                    "fill_count": 0,
                }
            ],
        }

        checks = module.build_prearm_baseline_health_checks(summary)
        self.assertTrue(all(checks.values()), checks)

    def test_hash_manifest_matches_fix_package_files_except_itself(self) -> None:
        manifest_path = PACKAGE / "PACKAGE_SHA256SUMS.txt"
        manifest_entries: dict[str, str] = {}
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            digest, path = line.split(maxsplit=1)
            manifest_entries[path] = digest

        package_files = {
            str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(PACKAGE.rglob("*"))
            if path.is_file()
            and path.name != "PACKAGE_SHA256SUMS.txt"
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        }
        self.assertEqual(manifest_entries, package_files)


if __name__ == "__main__":
    unittest.main()
