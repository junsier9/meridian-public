from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_helpers import ROOT, SRC

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.definitions.research_lead import RESEARCH_LEAD_AGENT
from enhengclaw.agents.tools.runtime_session_views import inspect_research_lead_directive
from enhengclaw.core.session import FileObjectStore
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator


DEMO = ROOT / "examples" / "rulebook_agent_review_demo.py"


def pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


class ResearchLeadReviewDemoAcceptanceTests(unittest.TestCase):
    def _run_demo(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DEMO), *args],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=pythonpath_env(),
        )

    def test_definition_exposes_pending_writable_and_readonly_review_surface(self) -> None:
        self.assertEqual(RESEARCH_LEAD_AGENT["status"], "promotion_ready_governed_slice")
        self.assertFalse(RESEARCH_LEAD_AGENT["enabled_under_current_governance"])
        self.assertTrue(RESEARCH_LEAD_AGENT["writes_to_runtime"])
        review_surface = dict(RESEARCH_LEAD_AGENT.get("operator_review_surface", {}))
        self.assertEqual(review_surface.get("surface_type"), "readonly_review")
        self.assertEqual(review_surface.get("demo"), "rulebook_agent_review_demo")
        self.assertTrue(Path(RESEARCH_LEAD_AGENT["prompt_path"]).exists())

    def test_public_demo_matches_direct_tool_output_without_mutating_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            completed = self._run_demo(
                "research_lead",
                "--artifacts-root",
                tmpdir,
                "--object-id",
                "research-lead-aix",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["agent_id"], "research_lead")
            self.assertEqual(payload["status"], "promotion_ready_governed_slice")
            self.assertEqual(payload["review_surface"], "research_lead_directive")
            self.assertFalse(payload["session_mutated"])

            session_path = Path(payload["session_path"])
            before = session_path.read_text(encoding="utf-8")
            runtime = RuntimeOrchestrator(store=FileObjectStore(Path(tmpdir) / "runtime_sessions"))
            direct_review = inspect_research_lead_directive(runtime=runtime, object_id="research-lead-aix")
            after = session_path.read_text(encoding="utf-8")

            self.assertEqual(before, after)
            self.assertEqual(payload["review"], json.loads(json.dumps(asdict(direct_review))))


if __name__ == "__main__":
    unittest.main()
