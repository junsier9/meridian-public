from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from enhengclaw.testing import execution_testbed

from tests.openclaw_lane_support import (
    OPENCLAW_LANE_CONFIGS,
    build_request_payload,
    load_fixture,
    required_live_env_names,
    seed_existing_object,
    tempdir,
)


EXPECTED_RESPONSE_KEYS = {
    "accepted_signal_ids",
    "artifacts_root",
    "blocked_reason",
    "compiler_artifact_paths",
    "contract_version",
    "error",
    "execution_status",
    "final_output_path",
    "owner_run_id",
    "quarantine_reason",
    "run_state",
    "runtime_session_path",
    "spec_version",
    "status",
}


class OpenClawContinueExistingAdapterTests(unittest.TestCase):
    def test_request_contract_requires_non_empty_execution_permit_path(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            with self.subTest(lane=config.lane_id):
                with self.assertRaisesRegex(Exception, "execution_permit_path"):
                    config.request_loader(
                        {
                            "contract_version": config.contract_version,
                            "subject": fixture["subject"],
                            "scope": fixture["scope"],
                            "object_id": fixture["object_id"],
                            config.text_field_name: fixture[config.text_field_name],
                            "execution_permit_path": "",
                        }
                    )

    def test_recorded_backend_requires_recorded_transcript_path(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            with self.subTest(lane=config.lane_id):
                with self.assertRaisesRegex(ValueError, "recorded_transcript_path"):
                    config.request_loader(
                        {
                            "contract_version": config.contract_version,
                            "subject": fixture["subject"],
                            "scope": fixture["scope"],
                            "object_id": fixture["object_id"],
                            config.text_field_name: fixture[config.text_field_name],
                            "execution_permit_path": "C:/tmp/permit.json",
                            "input_id": f"{fixture['case_id']}:1",
                            "compiler_backend": "recorded",
                        }
                    )

    def test_recorded_backend_requires_input_id(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            with self.subTest(lane=config.lane_id):
                with self.assertRaisesRegex(ValueError, "input_id"):
                    config.request_loader(
                        {
                            "contract_version": config.contract_version,
                            "subject": fixture["subject"],
                            "scope": fixture["scope"],
                            "object_id": fixture["object_id"],
                            config.text_field_name: fixture[config.text_field_name],
                            "execution_permit_path": "C:/tmp/permit.json",
                            "compiler_backend": "recorded",
                            "recorded_transcript_path": str(config.fixture_root / "success" / "model_transcript.json"),
                        }
                    )

    def test_skip_seed_is_rejected_on_resume_only_boundary(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            with self.subTest(lane=config.lane_id):
                with self.assertRaisesRegex(ValueError, "skip_seed"):
                    config.request_loader(
                        {
                            "contract_version": config.contract_version,
                            "subject": fixture["subject"],
                            "scope": fixture["scope"],
                            "object_id": fixture["object_id"],
                            config.text_field_name: fixture[config.text_field_name],
                            "execution_permit_path": "C:/tmp/permit.json",
                            "skip_seed": True,
                        }
                    )

    def test_live_backend_missing_env_fails_closed(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            with self.subTest(lane=config.lane_id):
                with execution_testbed() as bed, tempdir("ocl_") as tmpdir:
                    permit_path, _ = bed.issue_permit(
                        slug=f"openclaw-{config.lane_id}-live-missing-env",
                        scope=str(fixture["scope"]),
                        capabilities=["runtime.execute"],
                        allowed_operations=["runtime.*"],
                    )
                    response_path = Path(tmpdir) / "response.json"
                    request_path = Path(tmpdir) / "request.json"
                    request_path.write_text(
                        json.dumps(
                            build_request_payload(
                                config,
                                fixture,
                                execution_permit_path=permit_path,
                                compiler_backend="live",
                                artifacts_root=Path(tmpdir) / "a",
                            ),
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    base_url_name, model_name_name, api_key_name = required_live_env_names(config)
                    cleared_env = {
                        base_url_name: "",
                        model_name_name: "",
                        api_key_name: "",
                    }
                    with patch.dict(os.environ, cleared_env, clear=False):
                        exit_code = config.main_callable(["--request", str(request_path), "--response", str(response_path)])
                    payload = json.loads(response_path.read_text(encoding="utf-8"))
                    self.assertEqual(exit_code, 1)
                    self.assertEqual(payload["status"], "failed")
                    self.assertEqual(payload["run_state"], "FAILED")
                    self.assertIn(f"{config.env_prefix}_BASE_URL", payload["error"])

    def test_recorded_success_response_shape_is_fixed(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            transcript = config.fixture_root / "success" / "model_transcript.json"
            with self.subTest(lane=config.lane_id):
                with execution_testbed() as bed, tempdir("ocs_") as tmpdir:
                    permit_path, _ = bed.issue_permit(
                        slug=f"openclaw-{config.lane_id}-shape",
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
                    request_path = Path(tmpdir) / "request.json"
                    response_path = Path(tmpdir) / "response.json"
                    request_path.write_text(
                        json.dumps(
                            build_request_payload(
                                config,
                                fixture,
                                execution_permit_path=permit_path,
                                compiler_backend="recorded",
                                recorded_transcript_path=transcript,
                                artifacts_root=artifacts_root,
                            ),
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    exit_code = config.main_callable(["--request", str(request_path), "--response", str(response_path)])
                    payload = json.loads(response_path.read_text(encoding="utf-8"))
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(set(payload), EXPECTED_RESPONSE_KEYS)
                    self.assertEqual(payload["contract_version"], config.contract_version)
                    self.assertEqual(payload["status"], "success")
                    self.assertEqual(payload["execution_status"], "success")
                    self.assertEqual(payload["run_state"], "FINALIZED")
                    self.assertTrue(payload["compiler_artifact_paths"])
                    self.assertTrue(Path(payload["final_output_path"]).exists())
                    self.assertTrue(Path(payload["runtime_session_path"]).exists())

    def test_missing_existing_object_returns_structured_blocked(self) -> None:
        for config in OPENCLAW_LANE_CONFIGS:
            fixture = load_fixture(config, "success")
            transcript = config.fixture_root / "success" / "model_transcript.json"
            with self.subTest(lane=config.lane_id):
                with execution_testbed() as bed, tempdir("ocm_") as tmpdir:
                    permit_path, _ = bed.issue_permit(
                        slug=f"openclaw-{config.lane_id}-missing-object",
                        scope=str(fixture["scope"]),
                        capabilities=["runtime.execute"],
                        allowed_operations=["runtime.*"],
                    )
                    response_path = Path(tmpdir) / "response.json"
                    request_path = Path(tmpdir) / "request.json"
                    request_path.write_text(
                        json.dumps(
                            build_request_payload(
                                config,
                                fixture,
                                execution_permit_path=permit_path,
                                compiler_backend="recorded",
                                recorded_transcript_path=transcript,
                                artifacts_root=Path(tmpdir) / "a",
                            ),
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    exit_code = config.main_callable(["--request", str(request_path), "--response", str(response_path)])
                    payload = json.loads(response_path.read_text(encoding="utf-8"))
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(payload["status"], "blocked")
                    self.assertEqual(payload["execution_status"], "blocked")
                    self.assertEqual(payload["run_state"], "BLOCKED")
                    self.assertIsNone(payload["runtime_session_path"])
                    self.assertIn("missing existing object context", payload["blocked_reason"])

    @unittest.skipUnless(os.name == "nt", "Windows legacy path boundary only applies on Windows")
    def test_recorded_success_can_write_long_response_path(self) -> None:
        config = next(item for item in OPENCLAW_LANE_CONFIGS if item.lane_id == "risk_signal_agent")
        fixture = load_fixture(config, "success")
        transcript = config.fixture_root / "success" / "model_transcript.json"
        with execution_testbed() as bed, tempdir("ocl_long_") as tmpdir:
            permit_path, _ = bed.issue_permit(
                slug="openclaw-risk-signal-long-response-path",
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
            request_path = Path(tmpdir) / "request.json"
            response_filename = "response.json"
            while len(str(Path(tmpdir) / response_filename)) < 260:
                response_filename = f"r{response_filename}"
            response_path = Path(tmpdir) / response_filename
            request_path.write_text(
                json.dumps(
                    build_request_payload(
                        config,
                        fixture,
                        execution_permit_path=permit_path,
                        compiler_backend="recorded",
                        recorded_transcript_path=transcript,
                        artifacts_root=artifacts_root,
                    ),
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            try:
                exit_code = config.main_callable(["--request", str(request_path), "--response", str(response_path)])
                payload = json.loads(_read_any_path_text(response_path))
                self.assertEqual(exit_code, 0)
                self.assertEqual(payload["status"], "success")
                self.assertEqual(payload["execution_status"], "success")
            finally:
                _remove_any_path(response_path)


def _read_any_path_text(path: Path) -> str:
    with open(_normalize_any_path(path), "r", encoding="utf-8") as handle:
        return handle.read()


def _remove_any_path(path: Path) -> None:
    normalized = _normalize_any_path(path)
    if os.path.exists(normalized):
        os.remove(normalized)


def _normalize_any_path(path: Path) -> str:
    normalized = os.path.abspath(os.path.normpath(str(path)))
    if os.name == "nt" and not normalized.startswith("\\\\?\\"):
        if normalized.startswith("\\\\"):
            normalized = "\\\\?\\UNC\\" + normalized[2:]
        else:
            normalized = "\\\\?\\" + normalized
    return normalized


if __name__ == "__main__":
    unittest.main()
