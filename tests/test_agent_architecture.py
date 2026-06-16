from __future__ import annotations

import unittest

from enhengclaw.agents.architecture import (
    MAIN_OWNER_ARCHITECTURE_CONTRACT_VERSION,
    delegate_contract_for_runtime_agent_id,
    delegate_runtime_agent_ids,
    load_main_owner_manifest,
    manifest_agent_ids,
    owner_agent_id,
    required_reviews_for_runtime_agent_id,
    validate_main_owner_manifest,
)


class AgentArchitectureContractTests(unittest.TestCase):
    def test_main_owner_manifest_is_valid(self) -> None:
        result = validate_main_owner_manifest()
        self.assertTrue(result.ok, msg="\n".join(result.errors))

    def test_main_owner_manifest_declares_expected_owner_delegate_ids_and_entrypoint(self) -> None:
        payload = load_main_owner_manifest()
        self.assertEqual(payload["contract_version"], MAIN_OWNER_ARCHITECTURE_CONTRACT_VERSION)
        self.assertEqual(owner_agent_id(), "rulebook_owner")
        self.assertEqual(
            payload["public_entrypoint"]["entrypoint"],
            "enhengclaw.orchestration.runtime.GovernedAgentOrchestrator.run_governed_write",
        )
        self.assertEqual(
            delegate_runtime_agent_ids(),
            [
                "market_observer",
                "evidence_agent",
                "risk_signal_agent",
                "risk_governance_agent",
                "validation_agent",
                "attention_allocator",
                "research_synthesizer",
                "research_lead",
            ],
        )
        self.assertIn("rulebook_owner", manifest_agent_ids())

    def test_manifest_declares_required_reviews_only_for_fail_closed_delegates(self) -> None:
        self.assertEqual(
            required_reviews_for_runtime_agent_id("risk_governance_agent"),
            ["enhengclaw.agents.tools.runtime_session_views.inspect_risk_governance_review"],
        )
        self.assertEqual(
            required_reviews_for_runtime_agent_id("validation_agent"),
            ["enhengclaw.agents.tools.runtime_session_views.inspect_validation_review"],
        )
        research_lead_contract = delegate_contract_for_runtime_agent_id("research_lead")
        self.assertNotIn("required_reviews", research_lead_contract)

    def test_manifest_enforces_owner_only_artifact_writes_and_capability_artifact(self) -> None:
        payload = load_main_owner_manifest()
        artifacts = {item["artifact_id"]: item for item in payload["artifacts"]}
        self.assertIn("capabilities", artifacts)
        self.assertEqual(artifacts["capabilities"]["writers"], ["rulebook_owner"])
        for runtime_agent_id in delegate_runtime_agent_ids():
            contract = delegate_contract_for_runtime_agent_id(runtime_agent_id)
            self.assertEqual(contract["writes_artifacts"], ["delegate_records"])

    def test_optional_review_surfaces_are_not_exposed_as_delegate_tools(self) -> None:
        for runtime_agent_id in ("attention_allocator", "research_synthesizer", "research_lead"):
            contract = delegate_contract_for_runtime_agent_id(runtime_agent_id)
            tool_names = tuple(str(item) for item in contract.get("allowed_tools", ()))
            self.assertTrue(tool_names)
            self.assertTrue(all(".runtime_session_views.inspect_" not in item for item in tool_names))


if __name__ == "__main__":
    unittest.main()
