from __future__ import annotations

from typing import Any

from enhengclaw.integrations.openclaw._continue_existing import (
    OpenClawContinueExistingRequest,
    OpenClawContinueExistingResponse,
    main_for_lane,
    parse_openclaw_continue_existing_request,
    run_openclaw_continue_existing,
)
from enhengclaw.integrations.openclaw._continue_existing_specs import RESEARCH_SYNTHESIZER_LANE


OPENCLAW_RESEARCH_SYNTHESIZER_CONTRACT_VERSION = RESEARCH_SYNTHESIZER_LANE.contract_version


def openclaw_research_synthesizer_request_from_payload(payload: dict[str, Any]) -> OpenClawContinueExistingRequest:
    return parse_openclaw_continue_existing_request(
        payload,
        contract_version=OPENCLAW_RESEARCH_SYNTHESIZER_CONTRACT_VERSION,
        text_field_name=RESEARCH_SYNTHESIZER_LANE.text_field_name,
    )


def run_openclaw_research_synthesizer(request: OpenClawContinueExistingRequest) -> OpenClawContinueExistingResponse:
    return run_openclaw_continue_existing(request, spec=RESEARCH_SYNTHESIZER_LANE)


def main(argv: list[str] | None = None) -> int:
    return main_for_lane(
        argv,
        spec=RESEARCH_SYNTHESIZER_LANE,
        request_loader=openclaw_research_synthesizer_request_from_payload,
        runner=run_openclaw_research_synthesizer,
    )


if __name__ == "__main__":
    raise SystemExit(main())
