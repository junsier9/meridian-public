from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhengclaw.agents.execution.evidence_agent import OpenAICompatibleEvidenceAgentBackend
from enhengclaw.agents.execution.market_observer import OpenAICompatibleMarketObserverBackend
from enhengclaw.compat.naming import env_aliases, getenv_compat
from enhengclaw.core.session import FileObjectStore
from scripts.openclaw._market_observer_live_inputs import resolve_openclaw_bundle_operator_env


class ProjectIdentityCompatibilityTests(unittest.TestCase):
    def test_meridian_alpha_import_aliases_existing_package_modules(self) -> None:
        legacy = importlib.import_module("enhengclaw.core.execution_control")
        alias = importlib.import_module("meridian_alpha.core.execution_control")

        self.assertIs(alias, legacy)
        self.assertEqual(importlib.import_module("meridian_alpha").__version__, "0.1.0")

    def test_meridian_alpha_module_entrypoint_supports_python_m(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "meridian_alpha.integrations.openclaw.market_observer",
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Run the OpenClaw deployment adapter", completed.stdout)

    def test_env_aliases_prefer_meridian_alpha_and_fallback_to_enhengclaw(self) -> None:
        self.assertEqual(
            env_aliases("ENHENGCLAW_EXECUTION_PERMIT_PATH"),
            ("MERIDIAN_ALPHA_EXECUTION_PERMIT_PATH", "ENHENGCLAW_EXECUTION_PERMIT_PATH"),
        )
        env = {
            "MERIDIAN_ALPHA_EXECUTION_PERMIT_PATH": "new-permit.json",
            "ENHENGCLAW_EXECUTION_PERMIT_PATH": "old-permit.json",
        }
        self.assertEqual(getenv_compat("ENHENGCLAW_EXECUTION_PERMIT_PATH", env=env), "new-permit.json")
        self.assertEqual(
            getenv_compat(
                "ENHENGCLAW_EXECUTION_PERMIT_PATH",
                env={"ENHENGCLAW_EXECUTION_PERMIT_PATH": "old-permit.json"},
            ),
            "old-permit.json",
        )

    def test_runtime_session_root_accepts_meridian_alpha_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_root = Path(tmpdir) / "sessions"
            with mock.patch.dict(
                os.environ,
                {
                    "MERIDIAN_ALPHA_RUNTIME_SESSION_ROOT": str(session_root),
                    "ENHENGCLAW_RUNTIME_SESSION_ROOT": str(Path(tmpdir) / "legacy-sessions"),
                },
                clear=False,
            ):
                store = FileObjectStore()

        self.assertEqual(store.root, session_root.resolve())

    def test_live_backends_accept_meridian_alpha_env_prefix(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "MERIDIAN_ALPHA_MARKET_OBSERVER_MODEL_BASE_URL": "https://example.test/v1",
                "MERIDIAN_ALPHA_MARKET_OBSERVER_MODEL_NAME": "model-a",
                "MERIDIAN_ALPHA_MARKET_OBSERVER_API_KEY": "key-a",
                "MERIDIAN_ALPHA_EVIDENCE_AGENT_MODEL_BASE_URL": "https://example.test/v1",
                "MERIDIAN_ALPHA_EVIDENCE_AGENT_MODEL_NAME": "model-b",
                "MERIDIAN_ALPHA_EVIDENCE_AGENT_API_KEY": "key-b",
            },
            clear=True,
        ):
            market_backend = OpenAICompatibleMarketObserverBackend.from_env()
            evidence_backend = OpenAICompatibleEvidenceAgentBackend.from_env()

        self.assertEqual(market_backend.model_name, "model-a")
        self.assertEqual(evidence_backend.api_key, "key-b")

    def test_openclaw_operator_env_materializes_new_and_legacy_aliases(self) -> None:
        env, metadata = resolve_openclaw_bundle_operator_env(
            {
                "OPENCLAW": "shared-openclaw-key",
                "MERIDIAN_ALPHA_MARKET_OBSERVER_API_KEY": "dedicated-market-key",
            },
            fail_closed=True,
        )

        self.assertEqual(env["MERIDIAN_ALPHA_MARKET_OBSERVER_API_KEY"], "dedicated-market-key")
        self.assertEqual(env["ENHENGCLAW_MARKET_OBSERVER_API_KEY"], "dedicated-market-key")
        self.assertEqual(env["MERIDIAN_ALPHA_EVIDENCE_AGENT_API_KEY"], "shared-openclaw-key")
        self.assertEqual(env["ENHENGCLAW_EVIDENCE_AGENT_API_KEY"], "shared-openclaw-key")
        self.assertFalse(metadata["openclaw_mapping_used_by_lane"]["market_observer"])
        self.assertTrue(metadata["openclaw_mapping_used_by_lane"]["evidence_agent"])


if __name__ == "__main__":
    unittest.main()
