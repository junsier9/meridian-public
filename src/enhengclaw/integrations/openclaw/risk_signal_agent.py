from __future__ import annotations

from typing import Any

from enhengclaw.integrations.openclaw._continue_existing import (
    OpenClawContinueExistingRequest,
    OpenClawContinueExistingResponse,
    main_for_lane,
    parse_openclaw_continue_existing_request,
    run_openclaw_continue_existing,
)
from enhengclaw.integrations.openclaw._continue_existing_specs import RISK_SIGNAL_AGENT_LANE


OPENCLAW_RISK_SIGNAL_AGENT_CONTRACT_VERSION = RISK_SIGNAL_AGENT_LANE.contract_version


def openclaw_risk_signal_agent_request_from_payload(payload: dict[str, Any]) -> OpenClawContinueExistingRequest:
    return parse_openclaw_continue_existing_request(
        payload,
        contract_version=OPENCLAW_RISK_SIGNAL_AGENT_CONTRACT_VERSION,
        text_field_name=RISK_SIGNAL_AGENT_LANE.text_field_name,
    )


def run_openclaw_risk_signal_agent(request: OpenClawContinueExistingRequest) -> OpenClawContinueExistingResponse:
    return run_openclaw_continue_existing(request, spec=RISK_SIGNAL_AGENT_LANE)


def main(argv: list[str] | None = None) -> int:
    return main_for_lane(
        argv,
        spec=RISK_SIGNAL_AGENT_LANE,
        request_loader=openclaw_risk_signal_agent_request_from_payload,
        runner=run_openclaw_risk_signal_agent,
    )


if __name__ == "__main__":
    raise SystemExit(main())
