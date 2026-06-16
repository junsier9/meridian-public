from __future__ import annotations

from _pending_slice_execution_verify import ROOT, main_for_slice


SUCCESS_INPUT = ROOT / "fixtures" / "agent_golden" / "research_lead" / "success" / "input.json"


def main(argv: list[str] | None = None) -> int:
    return main_for_slice(
        argv=argv,
        slug="research-lead-execution",
        description="Verify the raw-input research_lead execution slice now that the public path is promoted.",
        unit_target="tests.test_pending_slice_execution.ResearchLeadExecutionTests",
        acceptance_target="tests.acceptance.test_pending_slice_execution_path.ResearchLeadExecutionPathTests",
        pending_target="tests.acceptance.test_research_lead_pending",
        fixture_input=SUCCESS_INPUT,
        command_name="research_lead",
        text_flag="--directive-text",
        text_key="directive_text",
        required_env=(
            "ENHENGCLAW_RESEARCH_LEAD_MODEL_BASE_URL",
            "ENHENGCLAW_RESEARCH_LEAD_MODEL_NAME",
            "ENHENGCLAW_RESEARCH_LEAD_API_KEY",
        ),
        public_acceptance_label="promoted public acceptance",
        expected_live_run_state="FINALIZED",
        expect_public_runtime_session=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
