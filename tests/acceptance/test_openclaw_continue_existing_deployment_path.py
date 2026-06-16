from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from enhengclaw.testing import execution_testbed

from tests.openclaw_lane_support import (
    OPENCLAW_LANE_CONFIGS,
    build_request_payload,
    load_fixture,
    run_lane_module,
    seed_existing_object,
    tempdir,
    transcript_path,
)


class OpenClawContinueExistingDeploymentAcceptanceTests(unittest.TestCase):
    def test_recorded_success_finalizes_governed_runtime_from_openclaw_request(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            with self.subTest(lane=config.lane_id):
                payload = self._run_case(config, "success")
                self.assertEqual(payload["status"], "success")
                self.assertEqual(payload["execution_status"], "success")
                self.assertEqual(payload["run_state"], "FINALIZED")
                self.assertTrue(payload["accepted_signal_ids"])

    def test_recorded_blocked_returns_blocked_without_runtime_mutation(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            with self.subTest(lane=config.lane_id):
                payload = self._run_case(config, "blocked")
                self.assertEqual(payload["status"], "blocked")
                self.assertEqual(payload["execution_status"], "blocked")
                self.assertEqual(payload["run_state"], "BLOCKED")

    def test_recorded_quarantine_returns_quarantine_without_runtime_mutation(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            with self.subTest(lane=config.lane_id):
                payload = self._run_case(config, "quarantine")
                self.assertEqual(payload["status"], "quarantine")
                self.assertEqual(payload["execution_status"], "quarantine")
                self.assertEqual(payload["run_state"], "BLOCKED")
                self.assertTrue(any(path.endswith("quarantine.json") for path in payload["compiler_artifact_paths"]))

    def test_review_gated_block_returns_blocked(self) -> None:
        override = {
            "risk_governance_review": {
                "review_name": "risk_governance_review",
                "gate_status": "block",
                "reasons": ["forced block for OpenClaw deployment-path review gate acceptance"],
            },
            "validation_review": {
                "review_name": "validation_review",
                "gate_status": "block",
                "reasons": ["forced block for OpenClaw deployment-path review gate acceptance"],
            },
        }
        for lane_id in ("risk_governance_agent", "validation_agent"):
            config = next(item for item in OPENCLAW_LANE_CONFIGS if item.lane_id == lane_id)
            with self.subTest(lane=config.lane_id):
                payload = self._run_case(
                    config,
                    "success",
                    env_extra={"ENHENGCLAW_TEST_REVIEW_OVERRIDE": json.dumps(override)},
                    expected_exit_code=0,
                )
                self.assertEqual(payload["status"], "blocked")
                self.assertEqual(payload["execution_status"], "success")
                self.assertEqual(payload["run_state"], "BLOCKED")

    def test_review_gated_invalid_payload_returns_failed(self) -> None:
        override = {
            "risk_governance_review": {
                "gate_status": "pass",
                "reasons": ["missing review_name should fail closed"],
            },
            "validation_review": {
                "error": "forced validation inspect failure from OpenClaw acceptance",
            },
        }
        cases = (
            ("risk_governance_agent", {"ENHENGCLAW_TEST_REVIEW_OVERRIDE": json.dumps(override)}),
            ("validation_agent", {"ENHENGCLAW_TEST_REVIEW_OVERRIDE": json.dumps(override)}),
        )
        for lane_id, env_extra in cases:
            config = next(item for item in OPENCLAW_LANE_CONFIGS if item.lane_id == lane_id)
            with self.subTest(lane=config.lane_id):
                payload = self._run_case(config, "success", env_extra=env_extra, expected_exit_code=1)
                self.assertEqual(payload["status"], "failed")
                self.assertEqual(payload["run_state"], "FAILED")
                self.assertIsNotNone(payload["error"])

    def _run_case(
        self,
        config,
        name: str,
        *,
        env_extra: dict[str, str] | None = None,
        expected_exit_code: int = 0,
    ) -> dict[str, object]:
        fixture = load_fixture(config, name)
        with execution_testbed() as bed, tempdir("oca_") as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug=f"openclaw-{config.lane_id}-{name}",
                scope=str(fixture["scope"]),
                capabilities=["runtime.execute"],
                allowed_operations=["runtime.*"],
            )
            artifacts_root = Path(tmpdir) / "a"
            seed_existing_object(
                artifacts_root=artifacts_root,
                object_id=str(fixture["object_id"]),
                scope=str(fixture["scope"]),
                subject=str(fixture["subject"]),
            )
            completed, _, response_path = run_lane_module(
                config,
                request_payload=build_request_payload(
                    config,
                    fixture,
                    execution_permit_path=permit_path,
                    compiler_backend="recorded",
                    recorded_transcript_path=transcript_path(config, name),
                    artifacts_root=artifacts_root,
                ),
                tmpdir=tmpdir,
                env_extra=env_extra,
            )
            self.assertEqual(
                completed.returncode,
                expected_exit_code,
                msg=f"adapter exit mismatch for {config.lane_id}:{name}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            payload = json.loads(response_path.read_text(encoding="utf-8"))
            for artifact_path in payload["compiler_artifact_paths"]:
                self.assertTrue(Path(artifact_path).exists(), msg=f"missing artifact: {artifact_path}")
            if payload["runtime_session_path"] is not None:
                self.assertTrue(Path(payload["runtime_session_path"]).exists())
            if payload["final_output_path"] is not None:
                self.assertTrue(Path(payload["final_output_path"]).exists())
            return payload


if __name__ == "__main__":
    unittest.main()
