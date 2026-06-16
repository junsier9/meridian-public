from __future__ import annotations

from _pending_slice_execution_verify import ROOT, main_for_slice


SUCCESS_INPUT = ROOT / "fixtures" / "agent_golden" / "risk_governance_agent" / "success" / "input.json"


def main(argv: list[str] | None = None) -> int:
    return main_for_slice(
        argv=argv,
        slug="risk-governance-execution",
        description="Verify the raw-input risk_governance_agent execution slice now that the public path is promoted with required review gating.",
        unit_target="tests.test_pending_slice_execution.RiskGovernanceExecutionTests",
        acceptance_target="tests.acceptance.test_pending_slice_execution_path.RiskGovernanceExecutionPathTests",
        pending_target="tests.acceptance.test_risk_governance_agent_pending",
        fixture_input=SUCCESS_INPUT,
        command_name="risk_governance_agent",
        text_flag="--governance-text",
        text_key="governance_text",
        required_env=(
            "ENHENGCLAW_RISK_GOVERNANCE_AGENT_MODEL_BASE_URL",
            "ENHENGCLAW_RISK_GOVERNANCE_AGENT_MODEL_NAME",
            "ENHENGCLAW_RISK_GOVERNANCE_AGENT_API_KEY",
        ),
        public_acceptance_label="promoted public acceptance",
        expected_live_run_state="FINALIZED",
        expect_public_runtime_session=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
