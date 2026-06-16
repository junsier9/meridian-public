from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT, SRC

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.testing import execution_testbed
from scripts.verify import _openclaw_continue_existing_live as live_helper
from scripts.verify import _openclaw_live_readiness_bundle as bundle_helper
from scripts.verify import run_openclaw_review_gated_live_readiness as review_gated_bundle
from scripts.verify._openclaw_continue_existing_support import (
    lane_config,
    load_fixture,
    required_live_env_names,
    resolve_lane_live_env,
)


class ContinueExistingLiveHelperTests(unittest.TestCase):
    def test_live_smoke_requires_execution_permit(self) -> None:
        with patch.object(live_helper, "run_continue_existing_recorded_gate") as recorded_gate, contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(io.StringIO()):
            exit_code = live_helper.main(lane_id="evidence_agent", argv=["--live-smoke"])
        self.assertEqual(exit_code, 2)
        recorded_gate.assert_not_called()

    def test_live_smoke_missing_env_fails_closed_and_retains_evidence(self) -> None:
        config = lane_config("evidence_agent")
        fixture = load_fixture(config, "success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug="openclaw-evidence-agent-live-smoke-missing-env",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            retain_root = Path(tmpdir) / "retain"
            with patch.dict(
                os.environ,
                {
                    "OPENCLAW": "",
                    "ENHENGCLAW_EVIDENCE_AGENT_MODEL_BASE_URL": "",
                    "ENHENGCLAW_EVIDENCE_AGENT_MODEL_NAME": "",
                    "ENHENGCLAW_EVIDENCE_AGENT_API_KEY": "",
                },
                clear=False,
            ), patch.object(live_helper, "run_continue_existing_recorded_gate") as recorded_gate:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exit_code = live_helper.main(
                        lane_id="evidence_agent",
                        argv=[
                            "--live-smoke",
                            "--execution-permit",
                            str(permit_path),
                            "--retain-root",
                            str(retain_root),
                        ],
                    )

            self.assertEqual(exit_code, 1)
            recorded_gate.assert_not_called()
            summary = json.loads((retain_root / "live_smoke_summary.json").read_text(encoding="utf-8"))
            snapshot = json.loads((retain_root / "failure_snapshot.json").read_text(encoding="utf-8"))
            host_response = json.loads((retain_root / "host_live" / "response.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["overall_status"], "failed")
            self.assertEqual(summary["stages"]["live_preflight"]["status"], "failed")
            self.assertEqual(snapshot["stage_label"], "live env preflight")
            self.assertFalse(snapshot["required_live_env"]["ENHENGCLAW_EVIDENCE_AGENT_API_KEY"])
            self.assertEqual(host_response["status"], "failed")
            self.assertIn("ENHENGCLAW_EVIDENCE_AGENT_API_KEY", host_response["error"])

    def test_resolve_lane_live_env_applies_shared_openclaw_baseline_overrides(self) -> None:
        config = lane_config("evidence_agent")
        env, meta = resolve_lane_live_env(
            config,
            base_env={
                "OPENCLAW": "test-key",
                "OPENCLAW_BASE_URL": "https://example.test/v1",
                "OPENCLAW_MODEL_NAME": "gpt-5.4-mini",
                "OPENCLAW_MODEL_TIMEOUT_SECONDS": "45",
            },
        )

        base_url_name, model_name_name, api_key_name = meta["required_live_env"]
        self.assertEqual(env[base_url_name], "https://example.test/v1")
        self.assertEqual(env[model_name_name], "gpt-5.4-mini")
        self.assertEqual(env[api_key_name], "test-key")
        self.assertEqual(env[meta["timeout_env_name"]], "45")
        self.assertEqual(meta["shared_openclaw_base_url"], "https://example.test/v1")
        self.assertEqual(meta["shared_openclaw_model_name"], "gpt-5.4-mini")
        self.assertEqual(meta["shared_openclaw_model_timeout_seconds"], "45")

    def test_resolve_lane_live_env_uses_slice_backend_api_key_name(self) -> None:
        config = lane_config("risk_signal_agent")
        env, meta = resolve_lane_live_env(
            config,
            base_env={
                "OPENCLAW": "test-key",
                "OPENCLAW_BASE_URL": "https://example.test/v1",
                "OPENCLAW_MODEL_NAME": "gpt-5.4-mini",
            },
        )

        _base_url_name, _model_name_name, api_key_name = required_live_env_names(config)
        self.assertEqual(api_key_name, "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_API_KEY")
        self.assertEqual(env[api_key_name], "test-key")
        self.assertTrue(meta["openclaw_mapping_used"])

    def test_prepare_live_context_seeds_existing_object_outside_adapter(self) -> None:
        config = lane_config("evidence_agent")
        fixture = load_fixture(config, "success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                "OPENCLAW": "test-key",
                "ENHENGCLAW_EVIDENCE_AGENT_MODEL_BASE_URL": "https://api.openai.com/v1",
                "ENHENGCLAW_EVIDENCE_AGENT_MODEL_NAME": "gpt-5.4",
            },
            clear=False,
        ):
            permit_path, _ = bed.issue_permit(
                slug="openclaw-evidence-agent-live-seed",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            env, env_meta = resolve_lane_live_env(config)
            context = live_helper._prepare_live_context(
                config=config,
                execution_permit_path=Path(permit_path),
                trust_root_dir=None,
                env=env,
                retain_root=Path(tmpdir) / "retain",
                env_meta=env_meta,
            )
            seed_context = json.loads(Path(context["paths"]["seed_context_path"]).read_text(encoding="utf-8"))
            host_runtime_root = Path(seed_context["host_runtime_session_root"])
            wsl_runtime_root = Path(seed_context["wsl_runtime_session_root"])
            self.assertTrue(any(host_runtime_root.rglob("*.json")))
            self.assertTrue(any(wsl_runtime_root.rglob("*.json")))
            self.assertEqual(seed_context["object_id"], fixture["object_id"])
            self.assertEqual(
                list(context["summary"]["stages"].keys()),
                [
                    "live_preflight",
                    "recorded_gate",
                    "host_live_adapter_smoke",
                    "workspace_live_smoke",
                    "workspace_live_audit",
                ],
            )
            host_request = json.loads(Path(context["paths"]["host_request_path"]).read_text(encoding="utf-8"))
            self.assertEqual(host_request["compiler_backend"], "live")
            self.assertEqual(host_request["object_id"], fixture["object_id"])

    def test_live_request_applies_validation_override_text(self) -> None:
        config = lane_config("validation_agent")
        fixture = load_fixture(config, "success")
        with execution_testbed() as bed, tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                "OPENCLAW": "test-key",
                "ENHENGCLAW_VALIDATION_AGENT_MODEL_BASE_URL": "https://api.openai.com/v1",
                "ENHENGCLAW_VALIDATION_AGENT_MODEL_NAME": "gpt-5.4",
            },
            clear=False,
        ):
            permit_path, _ = bed.issue_permit(
                slug="openclaw-validation-agent-live-override",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            env, env_meta = resolve_lane_live_env(config)
            context = live_helper._prepare_live_context(
                config=config,
                execution_permit_path=Path(permit_path),
                trust_root_dir=None,
                env=env,
                retain_root=Path(tmpdir) / "retain",
                env_meta=env_meta,
            )
            host_request = json.loads(Path(context["paths"]["host_request_path"]).read_text(encoding="utf-8"))
            self.assertEqual(host_request["compiler_backend"], "live")
            self.assertEqual(host_request["validation_text"], config.live_text_override)


class ContinueExistingLiveBundleTests(unittest.TestCase):
    def test_bundle_env_preserves_review_override_passthrough(self) -> None:
        env = bundle_helper._build_env(
            base_env={
                "OPENCLAW": "test-key",
                "ENHENGCLAW_TEST_REVIEW_OVERRIDE": '{"validation_review":{"gate_status":"pass","review_name":"validation_review"}}',
            }
        )
        self.assertEqual(env["OPENCLAW"], "test-key")
        self.assertIn("ENHENGCLAW_TEST_REVIEW_OVERRIDE", env)

    def test_bundle_failure_records_failing_lane_and_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_continue_existing_live_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            permit_path = Path(tmpdir) / "permit.json"
            permit_path.write_text("{}", encoding="utf-8")

            def side_effect(*, lane_id: str, execution_permit: Path, trust_root_dir: Path | None, retain_root: Path, env):
                return {
                    "lane_id": lane_id,
                    "status": "failed" if lane_id == "evidence_agent" else "passed",
                    "exit_code": 1 if lane_id == "evidence_agent" else 0,
                    "stdout_path": str(retain_root / "stdout.log"),
                    "stderr_path": str(retain_root / "stderr.log"),
                    "result_path": str(retain_root / "result.json"),
                    "summary_path": str(retain_root / "live_smoke_summary.json"),
                    "live_summary": {"stages": {"live_preflight": {"label": "live env preflight", "status": "failed"}}},
                    "failing_stage": "live env preflight",
                    "evidence_root": str(retain_root),
                }

            with patch.object(bundle_helper, "_run_lane_live_gate", side_effect=side_effect):
                result = bundle_helper.run_live_readiness_bundle(
                    bundle_id="bundle",
                    bundle_label="bundle",
                    lane_ids=("evidence_agent", "risk_signal_agent"),
                    execution_permit=permit_path,
                    retain_root=retain_root,
                )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failing_lane"], "evidence_agent")
            self.assertEqual(result["failing_stage"], "live env preflight")
            summary = json.loads((retain_root / "bundle_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["lane_results"]["evidence_agent"]["failing_stage"], "live env preflight")

    def test_review_gated_bundle_injects_success_path_review_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openclaw_review_gated_live_") as tmpdir:
            retain_root = Path(tmpdir) / "retain"
            permit_path = Path(tmpdir) / "permit.json"
            permit_path.write_text("{}", encoding="utf-8")
            observed: dict[str, object] = {}

            def fake_run_live_readiness_bundle(**kwargs):
                observed.update(kwargs)
                return {
                    "status": "success",
                    "retain_root": str(retain_root),
                    "failing_lane": None,
                    "failing_stage": None,
                    "exit_code": 0,
                }

            with patch.object(review_gated_bundle, "run_live_readiness_bundle", side_effect=fake_run_live_readiness_bundle):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exit_code = review_gated_bundle.main(
                        [
                            "--execution-permit",
                            str(permit_path),
                            "--retain-root",
                            str(retain_root),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            base_env = observed["base_env"]
            self.assertIsInstance(base_env, dict)
            override = json.loads(str(base_env["ENHENGCLAW_TEST_REVIEW_OVERRIDE"]))
            self.assertEqual(override["risk_governance_review"]["gate_status"], "pass")
            self.assertEqual(override["validation_review"]["gate_status"], "pass")


if __name__ == "__main__":
    unittest.main()
