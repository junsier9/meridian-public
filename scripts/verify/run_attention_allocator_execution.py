from __future__ import annotations

from _pending_slice_execution_verify import ROOT, main_for_slice


SUCCESS_INPUT = ROOT / "fixtures" / "agent_golden" / "attention_allocator" / "success" / "input.json"


def main(argv: list[str] | None = None) -> int:
    return main_for_slice(
        argv=argv,
        slug="attention-allocator-execution",
        description="Verify the raw-input attention_allocator execution slice now that the public path is promoted.",
        unit_target="tests.test_pending_slice_execution.AttentionAllocatorExecutionTests",
        acceptance_target="tests.acceptance.test_pending_slice_execution_path.AttentionAllocatorExecutionPathTests",
        pending_target="tests.acceptance.test_attention_allocator_pending",
        fixture_input=SUCCESS_INPUT,
        command_name="attention_allocator",
        text_flag="--attention-text",
        text_key="attention_text",
        required_env=(
            "ENHENGCLAW_ATTENTION_ALLOCATOR_MODEL_BASE_URL",
            "ENHENGCLAW_ATTENTION_ALLOCATOR_MODEL_NAME",
            "ENHENGCLAW_ATTENTION_ALLOCATOR_API_KEY",
        ),
        public_acceptance_label="promoted public acceptance",
        expected_live_run_state="FINALIZED",
        expect_public_runtime_session=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
