from __future__ import annotations

from typing import Any

from enhengclaw.integrations.openclaw._continue_existing import (
    OpenClawContinueExistingRequest,
    OpenClawContinueExistingResponse,
    main_for_lane,
    parse_openclaw_continue_existing_request,
    run_openclaw_continue_existing,
)
from enhengclaw.integrations.openclaw._continue_existing_specs import ATTENTION_ALLOCATOR_LANE


OPENCLAW_ATTENTION_ALLOCATOR_CONTRACT_VERSION = ATTENTION_ALLOCATOR_LANE.contract_version


def openclaw_attention_allocator_request_from_payload(payload: dict[str, Any]) -> OpenClawContinueExistingRequest:
    return parse_openclaw_continue_existing_request(
        payload,
        contract_version=OPENCLAW_ATTENTION_ALLOCATOR_CONTRACT_VERSION,
        text_field_name=ATTENTION_ALLOCATOR_LANE.text_field_name,
    )


def run_openclaw_attention_allocator(request: OpenClawContinueExistingRequest) -> OpenClawContinueExistingResponse:
    return run_openclaw_continue_existing(request, spec=ATTENTION_ALLOCATOR_LANE)


def main(argv: list[str] | None = None) -> int:
    return main_for_lane(
        argv,
        spec=ATTENTION_ALLOCATOR_LANE,
        request_loader=openclaw_attention_allocator_request_from_payload,
        runner=run_openclaw_attention_allocator,
    )


if __name__ == "__main__":
    raise SystemExit(main())
