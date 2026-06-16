from __future__ import annotations

from pathlib import Path

from _pending_slice_execution_verify import ROOT, main_for_slice


SUCCESS_INPUT = ROOT / "fixtures" / "agent_golden" / "risk_signal_agent" / "success" / "input.json"


def main(argv: list[str] | None = None) -> int:
    return main_for_slice(
        argv=argv,
        slug="risk-signal-execution",
        description="Verify the raw-input risk_signal_agent execution slice, including its promoted public governed path.",
        unit_target="tests.test_pending_slice_execution.RiskSignalExecutionTests",
        acceptance_target="tests.acceptance.test_pending_slice_execution_path.RiskSignalExecutionPathTests",
        pending_target="tests.acceptance.test_risk_signal_agent_pending",
        fixture_input=SUCCESS_INPUT,
        command_name="risk_signal_agent",
        text_flag="--risk-text",
        text_key="risk_text",
        required_env=(
            "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_BASE_URL",
            "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_NAME",
            "ENHENGCLAW_RISK_SIGNAL_AGENT_API_KEY",
        ),
        public_acceptance_label="promoted public acceptance",
        expected_live_run_state="FINALIZED",
        expect_public_runtime_session=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
