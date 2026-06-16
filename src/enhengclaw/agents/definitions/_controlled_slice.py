from __future__ import annotations

from pathlib import Path
from typing import Mapping


CONTROLLED_AGENT_SLICE_CONTRACT_VERSION = "controlled_agent_slice.v1"
CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION = "controlled_agent_slice_promotion.v1"
PROMOTION_READY_CONTROLLED_SLICE_STATUS = "promotion_ready_governed_slice"
_PROMOTION_ELIGIBLE_STATUSES = frozenset(
    {
        "governed_agent_slice",
        PROMOTION_READY_CONTROLLED_SLICE_STATUS,
    }
)
_PROMOTION_ELIGIBLE_SLICE_MODES = frozenset(
    {
        "create_new_object",
        "continue_existing_object",
    }
)
_OPERATOR_REVIEW_SURFACE_DEMO = "rulebook_agent_review_demo"
_OPERATOR_REVIEW_SURFACE_FIELDS = frozenset(
    {
        "surface_type",
        "schema",
        "tool",
        "demo",
    }
)


def build_governed_writable_slice(
    *,
    agent_id: str,
    description: str,
    prompt_path: Path,
    schema_entrypoint: str,
    tool_entrypoint: str,
    slice_mode: str,
    canonical_runtime_boundary: str,
    operator_review_surface: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return _build_promotion_grade_controlled_slice(
        agent_id=agent_id,
        description=description,
        prompt_path=prompt_path,
        schema_entrypoint=schema_entrypoint,
        tool_entrypoint=tool_entrypoint,
        slice_mode=slice_mode,
        canonical_runtime_boundary=canonical_runtime_boundary,
        operator_review_surface=operator_review_surface,
        status="governed_agent_slice",
        enabled_under_current_governance=True,
        promotion_state="promoted",
    )


def build_promotion_ready_writable_slice(
    *,
    agent_id: str,
    description: str,
    prompt_path: Path,
    schema_entrypoint: str,
    tool_entrypoint: str,
    slice_mode: str,
    canonical_runtime_boundary: str,
    operator_review_surface: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return _build_promotion_grade_controlled_slice(
        agent_id=agent_id,
        description=description,
        prompt_path=prompt_path,
        schema_entrypoint=schema_entrypoint,
        tool_entrypoint=tool_entrypoint,
        slice_mode=slice_mode,
        canonical_runtime_boundary=canonical_runtime_boundary,
        operator_review_surface=operator_review_surface,
        status=PROMOTION_READY_CONTROLLED_SLICE_STATUS,
        enabled_under_current_governance=False,
        promotion_state="admission_ready",
    )


def build_operator_review_surface(
    *,
    schema_entrypoint: str,
    tool_entrypoint: str,
    demo: str = _OPERATOR_REVIEW_SURFACE_DEMO,
) -> dict[str, str]:
    return {
        "surface_type": "readonly_review",
        "schema": schema_entrypoint,
        "tool": tool_entrypoint,
        "demo": demo,
    }


def is_promotion_eligible_controlled_slice(agent: Mapping[str, object]) -> bool:
    status = str(agent.get("status", "")).strip()
    if status not in _PROMOTION_ELIGIBLE_STATUSES:
        return False
    if str(agent.get("contract_version", "")).strip() != CONTROLLED_AGENT_SLICE_CONTRACT_VERSION:
        return False
    if (
        str(agent.get("promotion_contract_version", "")).strip()
        != CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION
    ):
        return False
    if agent.get("registry_admission_eligible") is not True:
        return False
    if agent.get("writes_to_runtime") is not True:
        return False
    if type(agent.get("reads_from_runtime")) is not bool:
        return False
    if type(agent.get("enabled_under_current_governance")) is not bool:
        return False
    if str(agent.get("slice_mode", "")).strip() not in _PROMOTION_ELIGIBLE_SLICE_MODES:
        return False
    if not str(agent.get("prompt_path", "")).strip():
        return False
    if not str(agent.get("schema", "")).strip():
        return False
    if not str(agent.get("tool", "")).strip():
        return False
    if not str(agent.get("canonical_runtime_boundary", "")).strip():
        return False
    if agent.get("max_tool_calls") != 1:
        return False
    if agent.get("max_payloads") != 1:
        return False
    if str(agent.get("promotion_verification_surface", "")).strip() != "canonical_verify_surface":
        return False
    operator_review_surface = agent.get("operator_review_surface")
    if operator_review_surface is not None and not _is_valid_operator_review_surface(operator_review_surface):
        return False
    promotion_state = str(agent.get("promotion_state", "")).strip()
    if status == "governed_agent_slice":
        return promotion_state == "promoted"
    if status == PROMOTION_READY_CONTROLLED_SLICE_STATUS:
        return promotion_state == "admission_ready"
    return False


def _build_promotion_grade_controlled_slice(
    *,
    agent_id: str,
    description: str,
    prompt_path: Path,
    schema_entrypoint: str,
    tool_entrypoint: str,
    slice_mode: str,
    canonical_runtime_boundary: str,
    operator_review_surface: Mapping[str, object] | None,
    status: str,
    enabled_under_current_governance: bool,
    promotion_state: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_id": agent_id,
        "status": status,
        "description": description,
        "prompt_path": str(prompt_path),
        "schema": schema_entrypoint,
        "tool": tool_entrypoint,
        "reads_from_runtime": False,
        "writes_to_runtime": True,
        "enabled_under_current_governance": enabled_under_current_governance,
        "contract_version": CONTROLLED_AGENT_SLICE_CONTRACT_VERSION,
        "promotion_contract_version": CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
        "promotion_state": promotion_state,
        "promotion_verification_surface": "canonical_verify_surface",
        "registry_admission_eligible": True,
        "slice_mode": slice_mode,
        "canonical_runtime_boundary": canonical_runtime_boundary,
        "max_tool_calls": 1,
        "max_payloads": 1,
    }
    if operator_review_surface is not None:
        payload["operator_review_surface"] = dict(operator_review_surface)
    return payload


def _is_valid_operator_review_surface(surface: object) -> bool:
    if not isinstance(surface, Mapping):
        return False
    unknown_fields = set(surface) - _OPERATOR_REVIEW_SURFACE_FIELDS
    if unknown_fields:
        return False
    if str(surface.get("surface_type", "")).strip() != "readonly_review":
        return False
    if not str(surface.get("schema", "")).strip():
        return False
    if not str(surface.get("tool", "")).strip():
        return False
    if str(surface.get("demo", "")).strip() != _OPERATOR_REVIEW_SURFACE_DEMO:
        return False
    return True
