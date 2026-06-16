from __future__ import annotations

from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class DocumentationContractTests(unittest.TestCase):
    def test_agents_declares_context_version(self) -> None:
        text = _read("AGENTS.md")

        self.assertIn("Context-Version:", text)
        self.assertIn("`AGENTS.md` is the dense agent startup page", text)
        self.assertIn("`CLAUDE.md` is a legacy compatibility entrypoint", text)

    def test_claude_defers_to_agents(self) -> None:
        text = _read("CLAUDE.md")

        self.assertIn("Compatibility entrypoint", text)
        self.assertIn("`AGENTS.md` is the dense agent startup page", text)
        self.assertIn("must defer to `AGENTS.md`", text)

    def test_readme_declares_document_roles(self) -> None:
        text = _read("README.md")

        self.assertIn("`README.md` is the project and developer entrypoint.", text)
        self.assertIn("`AGENTS.md` is the dense agent startup page", text)
        self.assertIn("`CLAUDE.md` is a legacy compatibility entrypoint", text)
        self.assertIn("`PROJECT_STATE.md` is the canonical truth source", text)
        self.assertIn("`CANONICAL_RUNBOOK.md` is the exact command and failure-routing source.", text)
        self.assertIn("`pyproject.toml` intentionally declares the current clean-install runtime floor", text)
        self.assertIn("The current operator workflow is a single Windows host contract", text)
        self.assertIn("institutional-style dual-track governance", text)
        self.assertIn("`Stage 4: Automated Execution`", text)
        self.assertIn("`config\\project_governance\\project_profile.json`", text)
        self.assertIn("`config\\scheduled_tasks\\manifest.json`", text)
        self.assertIn("`promotion_decision` artifact", text)

    def test_project_instructions_is_redirect_only(self) -> None:
        text = _read("PROJECT_INSTRUCTIONS.md")

        self.assertIn("AGENTS.md", text)
        self.assertIn("CLAUDE.md", text)
        self.assertIn("PROJECT_STATE.md", text)
        self.assertIn("CANONICAL_RUNBOOK.md", text)
        self.assertIn("run_local_integrity_gates.py", text)
        self.assertNotIn("86460.0", text)
        self.assertNotIn("1800.0", text)
        self.assertNotIn("exit code", text.lower())

    def test_agent_docs_define_artifact_vocabulary(self) -> None:
        agents_text = _read("AGENTS.md")
        agent_guide_text = _read("docs/README_FOR_AGENT.md")

        self.assertIn("<ArtifactsRoot>", agents_text)
        self.assertIn("RunArtifactsRoot", agents_text)
        self.assertIn("ObjectArtifactsRoot", agent_guide_text)
        self.assertIn("repo-local `artifacts\\...` paths are examples", agent_guide_text)
        self.assertIn("dual-track Python codebase", agent_guide_text)
        self.assertIn("Current checked-in state is `Stage 4: Automated Execution`", agent_guide_text)
        self.assertIn("`promotion_decision` artifact", agent_guide_text)

    def test_state_and_runbook_keep_distinct_roles(self) -> None:
        state_text = _read("PROJECT_STATE.md")
        runbook_text = _read("CANONICAL_RUNBOOK.md")

        self.assertIn("canonical truth source", state_text)
        self.assertIn("exact command and failure-routing source", runbook_text)
        self.assertIn("## Real-24h Failure Routing", runbook_text)
        self.assertIn("Accepted evidence is freshness-gated.", state_text)
        self.assertIn("run_evidence_freshness_contract.py", runbook_text)

    def test_runtime_ownership_docs_match_machine_contract(self) -> None:
        runtime_contract = json.loads(
            (ROOT / "config" / "project_governance" / "runtime_ownership_contract.json").read_text(encoding="utf-8")
        )
        state_text = _read("PROJECT_STATE.md")
        instructions_text = _read("PROJECT_INSTRUCTIONS.md")
        runbook_text = _read("CANONICAL_RUNBOOK.md")
        agent_text = _read("docs/README_FOR_AGENT.md")
        owner_text = _read("docs/agents/OWNER_AGENT_ARCHITECTURE.md")

        self.assertEqual(runtime_contract["runtime_ownership_phase"], "partial")
        self.assertTrue(runtime_contract["owner_verification_required"])
        self.assertTrue(runtime_contract["owner_verification_enforced_in_boundary_gates"])

        for text in (state_text, instructions_text, runbook_text, agent_text, owner_text):
            self.assertIn("config/project_governance/runtime_ownership_contract.json", text)
        self.assertIn("runtime_ownership_phase = partial", state_text)
        self.assertIn("owner_verification_enforced_in_boundary_gates = true", state_text)
        self.assertIn("runtime_ownership_phase = partial", agent_text)
        self.assertIn("owner_verification_enforced_in_boundary_gates = true", agent_text)
        self.assertIn("runtime ownership phase is `partial`", owner_text)
        self.assertIn("owner_verification_enforced_in_boundary_gates = true", owner_text)


if __name__ == "__main__":
    unittest.main()
