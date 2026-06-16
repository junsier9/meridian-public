from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhengclaw.core.execution_control import TRUST_ROOT_DIR_ENV, load_execution_permit
from scripts.openclaw import _market_observer_live_inputs as live_inputs
from scripts.openclaw import run_market_observer_deployment_gate as operator_gate


def _unlock_trust_root(summary: dict[str, object]) -> None:
    trust_root_dir = Path(str(summary["trust_root_dir"]))
    allowed_signers_path = Path(str(summary["allowed_signers_path"]))
    if trust_root_dir.exists():
        live_inputs.unlock_trust_root_for_publication(trust_root_dir, allowed_signers_path)


class MarketObserverLiveInputsTests(unittest.TestCase):
    def test_split_root_defaults_keep_external_root_in_localappdata_and_trust_root_in_programdata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_paths_") as tmpdir:
            base = Path(tmpdir)
            localappdata = base / "localappdata"
            programdata = base / "programdata"
            env = {
                "LOCALAPPDATA": str(localappdata),
                "PROGRAMDATA": str(programdata),
            }
            external_root = live_inputs.resolve_external_root(external_root=None, base_env=env)
            trust_root = live_inputs.resolve_trust_root_dir(trust_root_dir=None, base_env=env)

            self.assertEqual(external_root, (localappdata / "EnhengClaw" / live_inputs.DEFAULT_EXTERNAL_ROOT_NAME).resolve())
            self.assertEqual(trust_root, (programdata / "EnhengClaw" / "trust").resolve())

    def test_provisioning_creates_split_root_artifacts_and_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_live_inputs_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            summary = live_inputs.provision_market_observer_live_inputs(
                external_root=external_root,
                trust_root_dir=trust_root_dir,
            )
            try:
                self.assertEqual(summary["status"], "success")
                self.assertEqual(summary["trust_root_dir"], str(trust_root_dir.resolve()))
                self.assertEqual(summary["trust_root_mode"], "explicit_trust_root")
                self.assertTrue(summary["trust_root_override_applied"])
                self.assertEqual(summary["trust_root_validation"], "passed")
                self.assertTrue((external_root / "signer" / "execution_signer").exists())
                self.assertTrue((external_root / "permit" / "owner_review.json").exists())
                self.assertTrue((external_root / "permit" / "batch_approval.json").exists())
                self.assertTrue((external_root / "permit" / "execution_permit.json").exists())
                self.assertTrue((trust_root_dir / "allowed_signers").exists())
                self.assertTrue((external_root / "provision_summary.json").exists())
            finally:
                _unlock_trust_root(summary)

    def test_provisioning_default_trust_root_keeps_programdata_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_live_inputs_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            programdata = Path(tmpdir) / "programdata"
            summary = live_inputs.provision_market_observer_live_inputs(
                external_root=external_root,
                base_env={"PROGRAMDATA": str(programdata)},
            )
            try:
                self.assertEqual(summary["trust_root_dir"], str((programdata / "EnhengClaw" / "trust").resolve()))
                self.assertEqual(summary["trust_root_mode"], "readonly_programdata")
                self.assertFalse(summary["trust_root_override_applied"])
                self.assertEqual(summary["trust_root_validation"], "passed")
            finally:
                _unlock_trust_root(summary)

    def test_provisioning_rerun_reuses_signer_and_refreshes_permit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_live_inputs_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            first = live_inputs.provision_market_observer_live_inputs(
                external_root=external_root,
                trust_root_dir=trust_root_dir,
            )
            signer_key = Path(first["signing_private_key_path"]).read_text(encoding="utf-8")
            allowed_signers = Path(first["allowed_signers_path"]).read_text(encoding="utf-8")
            second = live_inputs.provision_market_observer_live_inputs(
                external_root=external_root,
                trust_root_dir=trust_root_dir,
            )
            try:
                self.assertTrue(second["signer_reused"])
                self.assertEqual(Path(second["signing_private_key_path"]).read_text(encoding="utf-8"), signer_key)
                self.assertEqual(Path(second["allowed_signers_path"]).read_text(encoding="utf-8"), allowed_signers)
                self.assertNotEqual(first["permit_id"], second["permit_id"])
                self.assertTrue(second["trust_root_override_applied"])
            finally:
                _unlock_trust_root(second)

    def test_generated_review_artifacts_and_permit_load_without_writable_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_live_inputs_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            summary = live_inputs.provision_market_observer_live_inputs(
                external_root=external_root,
                trust_root_dir=trust_root_dir,
            )
            try:
                owner_review = json.loads(Path(summary["owner_review_path"]).read_text(encoding="utf-8"))
                batch_approval = json.loads(Path(summary["batch_approval_path"]).read_text(encoding="utf-8"))
                self.assertEqual(owner_review["status"], "passed")
                self.assertEqual(owner_review["scope"], "*")
                self.assertTrue(batch_approval["approved"])
                self.assertEqual(batch_approval["batch_id"], "openclaw-market-observer-live")
                self.assertEqual(batch_approval["scope"], "*")

                with patch.dict(
                    os.environ,
                    {
                        TRUST_ROOT_DIR_ENV: summary["trust_root_dir"],
                    },
                    clear=False,
                ):
                    os.environ.pop("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", None)
                    permit = load_execution_permit(Path(summary["permit_path"]))

                self.assertEqual(permit.scope, "*")
                self.assertEqual(list(permit.capabilities), ["runtime.execute"])
                self.assertEqual(list(permit.allowed_operations), ["runtime.*"])
            finally:
                _unlock_trust_root(summary)

    def test_operator_env_resolution_prefers_dedicated_api_key(self) -> None:
        env, meta = live_inputs.resolve_market_observer_operator_env(
            {
                "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "dedicated",
                "OPENCLAW": "openclaw-secret",
            }
        )
        self.assertEqual(env["ENHENGCLAW_MARKET_OBSERVER_API_KEY"], "dedicated")
        self.assertEqual(meta["live_env_mode"], "unified_openclaw_baseline")
        self.assertTrue(meta["openclaw_mapping_used"])
        self.assertFalse(meta["openclaw_mapping_used_by_lane"]["market_observer"])
        self.assertTrue(meta["dedicated_env_preserved_by_lane"]["market_observer"])
        self.assertTrue(meta["openclaw_mapping_used_by_lane"]["evidence_agent"])
        self.assertFalse(meta["trust_root_override_applied"])
        self.assertNotIn("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", env)

    def test_operator_env_resolution_falls_back_to_openclaw(self) -> None:
        env, meta = live_inputs.resolve_market_observer_operator_env({"OPENCLAW": "openclaw-secret"})
        self.assertEqual(env["ENHENGCLAW_MARKET_OBSERVER_API_KEY"], "openclaw-secret")
        self.assertTrue(meta["openclaw_mapping_used"])
        self.assertEqual(env["ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(env["ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME"], "gpt-5.4")
        self.assertEqual(env["ENHENGCLAW_MARKET_OBSERVER_MODEL_TIMEOUT_SECONDS"], "30")
        self.assertEqual(meta["live_env_mode"], "unified_openclaw_baseline")
        self.assertEqual(meta["shared_openclaw_base_url"], "https://api.openai.com/v1")
        self.assertEqual(meta["shared_openclaw_model_name"], "gpt-5.4")
        self.assertEqual(meta["shared_openclaw_model_timeout_seconds"], "30")
        for lane_id, (base_url_name, model_name_name, api_key_name) in live_inputs.openclaw_bundle_live_env_specs().items():
            timeout_name = base_url_name.replace("_BASE_URL", "_TIMEOUT_SECONDS")
            self.assertEqual(env[base_url_name], "https://api.openai.com/v1")
            self.assertEqual(env[model_name_name], "gpt-5.4")
            self.assertEqual(env[timeout_name], "30")
            self.assertEqual(env[api_key_name], "openclaw-secret")
            self.assertTrue(meta["openclaw_mapping_used_by_lane"][lane_id])
            self.assertFalse(meta["dedicated_env_preserved_by_lane"][lane_id])
            self.assertTrue(meta["defaulted_base_url_by_lane"][lane_id])
            self.assertTrue(meta["defaulted_model_name_by_lane"][lane_id])
            self.assertTrue(meta["defaulted_timeout_by_lane"][lane_id])
        self.assertFalse(meta["trust_root_override_applied"])
        self.assertNotIn("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", env)

    def test_operator_env_resolution_applies_shared_openclaw_baseline_overrides(self) -> None:
        env, meta = live_inputs.resolve_market_observer_operator_env(
            {
                "OPENCLAW": "openclaw-secret",
                "OPENCLAW_BASE_URL": "https://example.test/v1",
                "OPENCLAW_MODEL_NAME": "gpt-5.4-mini",
                "OPENCLAW_MODEL_TIMEOUT_SECONDS": "45",
            }
        )

        self.assertEqual(meta["shared_openclaw_base_url"], "https://example.test/v1")
        self.assertEqual(meta["shared_openclaw_model_name"], "gpt-5.4-mini")
        self.assertEqual(meta["shared_openclaw_model_timeout_seconds"], "45")
        for _lane_id, (base_url_name, model_name_name, _api_key_name) in live_inputs.openclaw_bundle_live_env_specs().items():
            timeout_name = base_url_name.replace("_BASE_URL", "_TIMEOUT_SECONDS")
            self.assertEqual(env[base_url_name], "https://example.test/v1")
            self.assertEqual(env[model_name_name], "gpt-5.4-mini")
            self.assertEqual(env[timeout_name], "45")

    def test_operator_env_resolution_fails_closed_without_any_api_key_source(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "all live lanes"):
            live_inputs.resolve_market_observer_operator_env({})

    def test_provisioning_cli_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_live_inputs_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = live_inputs.main(
                    [
                        "--external-root",
                        str(external_root),
                        "--trust-root-dir",
                        str(trust_root_dir),
                    ]
                )
            self.assertEqual(exit_code, 0)
            summary = json.loads((external_root / "provision_summary.json").read_text(encoding="utf-8"))
            try:
                self.assertEqual(summary["status"], "success")
                self.assertEqual(summary["external_root"], str(external_root.resolve()))
                self.assertEqual(summary["trust_root_dir"], str(trust_root_dir.resolve()))
                self.assertEqual(summary["evidence_family"], "openclaw_operator_provisioning")
                self.assertEqual(summary["contract_version"], "openclaw_operator_provisioning.v1")
                self.assertTrue(summary["produced_at_utc"])
            finally:
                _unlock_trust_root(summary)


class MarketObserverOperatorWorkflowTests(unittest.TestCase):
    def test_launcher_fails_closed_when_env_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_operator_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            retain_root = Path(tmpdir) / "retain"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            provision_summary = {
                "permit_path": str(external_root / "permit" / "execution_permit.json"),
                "trust_root_dir": str(trust_root_dir),
                "trust_root_mode": "explicit_trust_root",
                "trust_root_override_applied": True,
                "trust_root_validation": "passed",
                "expires_at_utc": "2026-04-18T00:00:00Z",
            }
            with patch.object(
                operator_gate,
                "_run_provisioning_command",
                return_value={
                    "status": "success",
                    "exit_code": 0,
                    "summary_path": str(external_root / "provision_summary.json"),
                    "summary": provision_summary,
                },
            ), patch.object(operator_gate, "_run_deployment_gate_command") as run_gate:
                result = operator_gate.run_market_observer_deployment_gate(
                    external_root=external_root,
                    retain_root=retain_root,
                    trust_root_dir=trust_root_dir,
                    base_env={},
                )

            run_gate.assert_not_called()
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failing_gate"], "operator_env")
            self.assertEqual(result["failing_stage"], "openclaw_env_mapping")
            self.assertEqual(result["live_env_mode"], "unified_openclaw_baseline")
            self.assertTrue(result["trust_root_override_applied"])
            self.assertEqual(result["trust_root_dir"], str(trust_root_dir))
            summary = json.loads((retain_root / "operator_run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["live_env_mode"], "unified_openclaw_baseline")
            self.assertEqual(summary["evidence_family"], "openclaw_operator_workflow")
            self.assertEqual(summary["contract_version"], "openclaw_operator_workflow.v1")
            self.assertTrue(summary["produced_at_utc"])

    def test_launcher_calls_deployment_gate_with_fresh_paths_and_explicit_trust_root_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="market_observer_operator_") as tmpdir:
            external_root = Path(tmpdir) / "external"
            retain_root = Path(tmpdir) / "retain"
            permit_path = external_root / "permit" / "execution_permit.json"
            trust_root_dir = Path(tmpdir) / "programdata" / "EnhengClaw" / "trust"
            permit_path.parent.mkdir(parents=True, exist_ok=True)
            trust_root_dir.mkdir(parents=True, exist_ok=True)
            permit_path.write_text("{}", encoding="utf-8")
            provision_summary = {
                "permit_path": str(permit_path),
                "trust_root_dir": str(trust_root_dir),
                "trust_root_mode": "explicit_trust_root",
                "trust_root_override_applied": True,
                "trust_root_validation": "passed",
                "expires_at_utc": "2026-04-18T00:00:00Z",
            }

            def deployment_side_effect(*, execution_permit: Path, trust_root_dir: Path, retain_root: Path, env: dict[str, str]) -> dict[str, object]:
                self.assertEqual(execution_permit, permit_path)
                self.assertEqual(trust_root_dir, Path(provision_summary["trust_root_dir"]))
                self.assertEqual(retain_root, retain_root_arg)
                self.assertEqual(env["OPENCLAW"], "openclaw-secret")
                self.assertNotIn("ENHENGCLAW_MARKET_OBSERVER_API_KEY", env)
                self.assertNotIn("ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT", env)
                bundle_summary_path = retain_root / "bundle_summary.json"
                bundle_summary_path.parent.mkdir(parents=True, exist_ok=True)
                bundle_summary_path.write_text(
                    json.dumps(
                        {
                            "status": "success",
                            "failing_gate": None,
                            "failing_stage": None,
                            "live_env_baseline": {
                                "live_env_mode": "unified_openclaw_baseline",
                                "openclaw_mapping_used_by_lane": {"market_observer": True},
                            },
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return {
                    "exit_code": 0,
                    "stdout_path": str(retain_root / "deployment_gate_stdout.log"),
                    "stderr_path": str(retain_root / "deployment_gate_stderr.log"),
                }

            retain_root_arg = retain_root
            with patch.object(
                operator_gate,
                "_run_provisioning_command",
                return_value={
                    "status": "success",
                    "exit_code": 0,
                    "summary_path": str(external_root / "provision_summary.json"),
                    "summary": provision_summary,
                },
            ), patch.object(operator_gate, "_run_deployment_gate_command", side_effect=deployment_side_effect):
                result = operator_gate.run_market_observer_deployment_gate(
                    external_root=external_root,
                    retain_root=retain_root,
                    trust_root_dir=trust_root_dir,
                    base_env={"OPENCLAW": "openclaw-secret"},
                )

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["openclaw_mapping_used"])
            self.assertEqual(result["live_env_mode"], "unified_openclaw_baseline")
            self.assertTrue(result["openclaw_mapping_used_by_lane"]["market_observer"])
            self.assertTrue(result["openclaw_mapping_used_by_lane"]["evidence_agent"])
            self.assertTrue(result["trust_root_override_applied"])
            summary = json.loads((retain_root / "operator_run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["provisioning_summary_path"], str(external_root / "provision_summary.json"))
            self.assertEqual(summary["trust_root_dir"], str(trust_root_dir))
            self.assertEqual(summary["trust_root_mode"], "explicit_trust_root")
            self.assertEqual(summary["trust_root_validation"], "passed")
            self.assertEqual(summary["live_env_mode"], "unified_openclaw_baseline")
            self.assertTrue(summary["openclaw_mapping_used_by_lane"]["risk_signal_agent"])
            self.assertEqual(summary["evidence_family"], "openclaw_operator_workflow")
            self.assertEqual(summary["contract_version"], "openclaw_operator_workflow.v1")
            self.assertTrue(summary["produced_at_utc"])


if __name__ == "__main__":
    unittest.main()
