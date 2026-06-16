from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "scripts" / "remote_runner_service_migration"
SYSTEMD = PACKAGE / "systemd"
CONFIG = PACKAGE / "config" / "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml"


class RemoteRunnerServiceMigrationPackageTests(unittest.TestCase):
    def test_expected_package_files_exist(self) -> None:
        expected = [
            PACKAGE / "README.md",
            PACKAGE / "CHECKLIST.md",
            PACKAGE / "REVIEW_SUMMARY.md",
            PACKAGE / "PACKAGE_SHA256SUMS.txt",
            PACKAGE / "precheck_remote_readonly.sh",
            PACKAGE / "verify_disabled_meridian_units.sh",
            PACKAGE / "rollback_meridian_units_dry_run.sh",
            CONFIG,
            SYSTEMD / "meridian-alpha-mainnet-supervisor-live.service",
            SYSTEMD / "meridian-alpha-mainnet-supervisor-live.timer",
            SYSTEMD / "meridian-alpha-mainnet-health-monitor.service",
            SYSTEMD / "meridian-alpha-mainnet-health-monitor.timer",
            SYSTEMD / "meridian-alpha-mainnet-unattended-daily-policy.service",
            SYSTEMD / "meridian-alpha-mainnet-unattended-daily-policy.timer",
        ]
        for path in expected:
            with self.subTest(path=path):
                self.assertTrue(path.exists(), path)

    def test_precheck_and_verify_scripts_are_read_only(self) -> None:
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
        for script_name in ["precheck_remote_readonly.sh", "verify_disabled_meridian_units.sh"]:
            text = (PACKAGE / script_name).read_text(encoding="utf-8")
            with self.subTest(script=script_name):
                for token in prohibited:
                    self.assertNotIn(token, text)

    def test_rollback_script_is_dry_run_guarded(self) -> None:
        text = (PACKAGE / "rollback_meridian_units_dry_run.sh").read_text(encoding="utf-8")
        self.assertIn('EXECUTE=0', text)
        self.assertIn("ROLLBACK_MERIDIAN_REMOTE_RUNNER_SERVICE_NAMES", text)
        self.assertIn("refusing execute mode without --confirm", text)

    def test_meridian_unit_drafts_do_not_reference_legacy_runner_or_units(self) -> None:
        for path in SYSTEMD.iterdir():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("Meridian Alpha", text)
                self.assertNotIn("/root/enhengclaw_live_runner", text)
                self.assertNotIn("enhengclaw-mainnet-", text)
                if path.suffix == ".timer":
                    self.assertIn("Unit=meridian-alpha-mainnet-", text)

    def test_meridian_config_changes_only_remote_runner_identity_surfaces(self) -> None:
        text = CONFIG.read_text(encoding="utf-8")
        self.assertIn("/root/meridian_alpha_live_runner/repo", text)
        self.assertIn("/root/meridian_alpha_live_runner/bin/with-live-env", text)
        self.assertIn("/root/meridian_alpha_live_runner/venv/bin/python", text)
        self.assertIn("systemd_timer_name: meridian-alpha-mainnet-supervisor-live.timer", text)
        self.assertIn("trading_enabled: false", text)
        self.assertNotIn("/root/enhengclaw_live_runner", text)
        self.assertNotIn("systemd_timer_name: enhengclaw-mainnet-supervisor-live.timer", text)

    def test_package_docs_preserve_evidence_and_timer_overlap_boundaries(self) -> None:
        combined = "\n".join(
            [
                (PACKAGE / "README.md").read_text(encoding="utf-8"),
                (PACKAGE / "CHECKLIST.md").read_text(encoding="utf-8"),
            ]
        )
        self.assertIn("Do not run legacy and Meridian live-capable supervisor timers concurrently.", combined)
        self.assertIn("Do not update `PROJECT_STATE.md` or accepted evidence", combined)
        self.assertIn("do not migrate secrets", combined.lower())

    def test_hash_manifest_matches_package_files_except_itself(self) -> None:
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
            if path.is_file() and path.name != "PACKAGE_SHA256SUMS.txt"
        }
        self.assertEqual(manifest_entries, package_files)

    def test_disabled_verifier_checks_only_meridian_units_for_legacy_names(self) -> None:
        text = (PACKAGE / "verify_disabled_meridian_units.sh").read_text(encoding="utf-8")
        self.assertIn('path="$UNIT_DIR/$unit"', text)
        self.assertNotIn('grep -RInE \'/root/enhengclaw_live_runner|enhengclaw-mainnet-\' "$UNIT_DIR"', text)


if __name__ == "__main__":
    unittest.main()
