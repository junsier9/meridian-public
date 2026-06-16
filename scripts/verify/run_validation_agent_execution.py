from __future__ import annotations

from _pending_slice_execution_verify import ROOT, main_for_slice


SUCCESS_INPUT = ROOT / "fixtures" / "agent_golden" / "validation_agent" / "success" / "input.json"


def main(argv: list[str] | None = None) -> int:
    return main_for_slice(
        argv=argv,
        slug="validation-execution",
        description="Verify the raw-input validation_agent execution slice now that the public path is promoted with required review gating.",
        unit_target="tests.test_pending_slice_execution.ValidationExecutionTests",
        acceptance_target="tests.acceptance.test_pending_slice_execution_path.ValidationExecutionPathTests",
        pending_target="tests.acceptance.test_validation_agent_pending",
        fixture_input=SUCCESS_INPUT,
        command_name="validation_agent",
        text_flag="--validation-text",
        text_key="validation_text",
        required_env=(
            "ENHENGCLAW_VALIDATION_AGENT_MODEL_BASE_URL",
            "ENHENGCLAW_VALIDATION_AGENT_MODEL_NAME",
            "ENHENGCLAW_VALIDATION_AGENT_API_KEY",
        ),
        public_acceptance_label="promoted public acceptance",
        expected_live_run_state="FINALIZED",
        expect_public_runtime_session=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
