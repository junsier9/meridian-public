from __future__ import annotations

from typing import Any

from enhengclaw.integrations.openclaw._continue_existing import (
    OpenClawContinueExistingRequest,
    OpenClawContinueExistingResponse,
    main_for_lane,
    parse_openclaw_continue_existing_request,
    run_openclaw_continue_existing,
)
from enhengclaw.integrations.openclaw._continue_existing_specs import EVIDENCE_AGENT_LANE


OPENCLAW_EVIDENCE_AGENT_CONTRACT_VERSION = EVIDENCE_AGENT_LANE.contract_version


def openclaw_evidence_agent_request_from_payload(payload: dict[str, Any]) -> OpenClawContinueExistingRequest:
    return parse_openclaw_continue_existing_request(
        payload,
        contract_version=OPENCLAW_EVIDENCE_AGENT_CONTRACT_VERSION,
        text_field_name=EVIDENCE_AGENT_LANE.text_field_name,
    )


def run_openclaw_evidence_agent(request: OpenClawContinueExistingRequest) -> OpenClawContinueExistingResponse:
    return run_openclaw_continue_existing(request, spec=EVIDENCE_AGENT_LANE)


def main(argv: list[str] | None = None) -> int:
    return main_for_lane(
        argv,
        spec=EVIDENCE_AGENT_LANE,
        request_loader=openclaw_evidence_agent_request_from_payload,
        runner=run_openclaw_evidence_agent,
    )


if __name__ == "__main__":
    raise SystemExit(main())
