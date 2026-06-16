from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.openclaw import provision_meridian_programdata_trust_root as meridian_trust
from scripts.openclaw._market_observer_live_inputs import unlock_trust_root_for_publication


PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMeridianAlphaDisabledTrustRootProof test-key"


class MeridianProgramDataTrustRootProofTests(unittest.TestCase):
    def test_plan_only_does_not_create_target_trust_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="meridian_trust_plan_", ignore_cleanup_errors=True) as tmpdir:
            root = Path(tmpdir)
            public_key_path = root / "execution_signer.pub"
            public_key_path.write_text(PUBLIC_KEY, encoding="utf-8")
            target = root / "ProgramData" / "MeridianAlpha" / "trust"

            summary = meridian_trust.provision_meridian_programdata_trust_root(
                target_trust_root=target,
                public_key_path=public_key_path,
            )

            self.assertEqual(summary["status"], "planned")
            self.assertFalse(summary["apply"])
            self.assertFalse(target.exists())
            self.assertTrue(summary["disabled_by_default"])
            self.assertFalse(summary["accepted_evidence_paths_updated"])
            self.assertFalse(summary["scheduled_tasks_updated"])
            self.assertFalse(summary["persistent_environment_changed"])

    def test_apply_publishes_disabled_trust_root_and_keeps_boundaries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="meridian_trust_apply_", ignore_cleanup_errors=True) as tmpdir:
            root = Path(tmpdir)
            public_key_path = root / "execution_signer.pub"
            public_key_path.write_text(PUBLIC_KEY, encoding="utf-8")
            target = root / "ProgramData" / "MeridianAlpha" / "trust"
            summary_root = root / "summary"
            allowed_signers_path = target / "allowed_signers"

            try:
                summary = meridian_trust.provision_meridian_programdata_trust_root(
                    target_trust_root=target,
                    public_key_path=public_key_path,
                    summary_root=summary_root,
                    apply=True,
                    confirm_boundary=meridian_trust.CONFIRM_BOUNDARY,
                )

                self.assertEqual(summary["status"], "success")
                self.assertEqual(summary["trust_root_mode"], "explicit_trust_root")
                self.assertTrue(summary["trust_root_override_applied"])
                self.assertEqual(summary["trust_root_validation"]["status"], "passed")
                self.assertEqual(summary["trust_root_validation"]["validated_with_env"], "MERIDIAN_ALPHA_TRUST_ROOT_DIR")
                self.assertEqual(summary["trust_root_validation"]["permit_validation"], "skipped")
                self.assertTrue(allowed_signers_path.exists())
                self.assertIn(PUBLIC_KEY, allowed_signers_path.read_text(encoding="utf-8"))
                self.assertTrue(summary["disabled_by_default"])
                self.assertFalse(summary["default_trust_root_changed"])
                self.assertFalse(summary["accepted_evidence_paths_updated"])
                self.assertFalse(summary["project_state_updated"])
                written_summary = json.loads(
                    (summary_root / "meridian_programdata_trust_root_proof_summary.json").read_text(encoding="utf-8")
                )
                self.assertEqual(written_summary["status"], "success")
            finally:
                if target.exists():
                    unlock_trust_root_for_publication(target, allowed_signers_path)


if __name__ == "__main__":
    unittest.main()
