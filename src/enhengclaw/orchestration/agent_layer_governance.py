from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhengclaw.agents import definitions as agent_definitions_module
from enhengclaw.agents.definitions._controlled_slice import (
    CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
    is_promotion_eligible_controlled_slice,
)


AGENT_LAYER_GOVERNANCE_CONTRACT_VERSION = "agent_layer_governance.v2"
GOVERNED_SLICE_REGISTRY_CONTRACT_VERSION = "governed_slice_registry.v1"
AGENT_LAYER_GOVERNANCE_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "agent_layer_governance" / "manifest.json"
)
GOVERNED_SLICE_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "agent_layer_governance" / "governed_slice_registry.json"
)
_ALLOWED_MANIFEST_FIELDS = frozenset(
    {
        "contract_version",
        "agent_layer_governance_enabled",
        "allowed_controlled_slice_ids",
        "broad_agent_layer_enabled",
    }
)
_ALLOWED_GOVERNED_SLICE_REGISTRY_FIELDS = frozenset(
    {
        "contract_version",
        "admitted_controlled_slice_ids",
    }
)


@dataclass(frozen=True, slots=True)
class GovernanceBlocker:
    code: str
    message: str

    def to_payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


def all_agent_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    seen_agent_ids: set[str] = set()
    for export_name in getattr(agent_definitions_module, "__all__", ()):
        candidate = getattr(agent_definitions_module, export_name, None)
        if not isinstance(candidate, dict):
            continue
        agent_id = str(candidate.get("agent_id", "")).strip()
        if not agent_id or agent_id in seen_agent_ids:
            continue
        definitions.append(candidate)
        seen_agent_ids.add(agent_id)
    return definitions


def all_agent_ids() -> list[str]:
    return [str(agent["agent_id"]) for agent in all_agent_definitions()]


def controlled_slice_candidate_ids() -> list[str]:
    return promotion_eligible_controlled_slice_ids()


def promotion_eligible_controlled_slice_definitions() -> list[dict[str, Any]]:
    slices: list[dict[str, Any]] = []
    for agent in all_agent_definitions():
        if not is_promotion_eligible_controlled_slice(agent):
            continue
        slices.append(agent)
    return sorted(slices, key=_controlled_slice_sort_key)


def promotion_eligible_controlled_slice_ids() -> list[str]:
    return [str(agent["agent_id"]) for agent in promotion_eligible_controlled_slice_definitions()]


def current_controlled_slice_definitions() -> list[dict[str, Any]]:
    slices: list[dict[str, Any]] = []
    for agent in all_agent_definitions():
        if str(agent.get("status", "")).strip() != "governed_agent_slice":
            continue
        slices.append(agent)
    return sorted(slices, key=_controlled_slice_sort_key)


def current_controlled_slice_ids() -> list[str]:
    return [str(agent["agent_id"]) for agent in current_controlled_slice_definitions()]


def missing_agent_layer_governance_result(
    *,
    manifest_path: Path | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    resolved_manifest_path = _resolve_manifest_path(manifest_path)
    resolved_registry_path = _resolve_registry_path(registry_path)
    current_slice_ids = current_controlled_slice_ids()
    promotion_eligible_slice_ids = promotion_eligible_controlled_slice_ids()
    agent_ids = all_agent_ids()
    return _build_result(
        status="blocked",
        manifest_path=resolved_manifest_path,
        registry_path=resolved_registry_path,
        contract_version=None,
        registry_contract_version=None,
        allowed_controlled_slice_ids=[],
        admitted_controlled_slice_ids=[],
        current_controlled_slice_ids=current_slice_ids,
        promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
        broad_agent_layer_requested=False,
        broad_blockers=[
            GovernanceBlocker(
                code="broad_governance_evaluation_missing",
                message="broad agent-layer readiness cannot be evaluated because governance evaluation is missing",
            )
        ],
        blockers=[
            GovernanceBlocker(
                code="governance_evaluation_missing",
                message="agent-layer governance evaluation is missing",
            )
        ],
        agent_ids=agent_ids,
    )


def evaluate_agent_layer_governance(
    *,
    manifest_path: Path | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    resolved_manifest_path = _resolve_manifest_path(manifest_path)
    resolved_registry_path = _resolve_registry_path(registry_path)
    current_slice_ids = current_controlled_slice_ids()
    promotion_eligible_slice_ids = promotion_eligible_controlled_slice_ids()
    agent_ids = all_agent_ids()
    registry = _evaluate_governed_slice_registry(
        registry_path=resolved_registry_path,
        current_controlled_slice_ids=current_slice_ids,
        promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
    )

    if not resolved_manifest_path.exists():
        blockers = [
            *registry["blockers"],
            GovernanceBlocker(
                code="manifest_missing",
                message=f"agent-layer governance manifest is missing: {resolved_manifest_path}",
            ),
        ]
        return _build_result(
            status="blocked",
            manifest_path=resolved_manifest_path,
            registry_path=resolved_registry_path,
            contract_version=None,
            registry_contract_version=registry["contract_version"],
            allowed_controlled_slice_ids=[],
            admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
            current_controlled_slice_ids=current_slice_ids,
            promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
            broad_agent_layer_requested=False,
            broad_blockers=_build_broad_blockers(
                agent_ids=agent_ids,
                promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
                current_controlled_slice_ids=current_slice_ids,
                admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
                allowed_controlled_slice_ids=[],
                governance_inputs_ready=False,
                registry_ready=registry["ready"],
            ),
            blockers=blockers,
            agent_ids=agent_ids,
        )

    try:
        raw_payload = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        blockers = [
            *registry["blockers"],
            GovernanceBlocker(
                code="manifest_invalid_json",
                message=f"agent-layer governance manifest is not valid JSON: {exc.msg}",
            ),
        ]
        return _build_result(
            status="blocked",
            manifest_path=resolved_manifest_path,
            registry_path=resolved_registry_path,
            contract_version=None,
            registry_contract_version=registry["contract_version"],
            allowed_controlled_slice_ids=[],
            admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
            current_controlled_slice_ids=current_slice_ids,
            promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
            broad_agent_layer_requested=False,
            broad_blockers=_build_broad_blockers(
                agent_ids=agent_ids,
                promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
                current_controlled_slice_ids=current_slice_ids,
                admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
                allowed_controlled_slice_ids=[],
                governance_inputs_ready=False,
                registry_ready=registry["ready"],
            ),
            blockers=blockers,
            agent_ids=agent_ids,
        )

    if not isinstance(raw_payload, dict):
        blockers = [
            *registry["blockers"],
            GovernanceBlocker(
                code="manifest_not_object",
                message="agent-layer governance manifest must be a JSON object",
            ),
        ]
        return _build_result(
            status="blocked",
            manifest_path=resolved_manifest_path,
            registry_path=resolved_registry_path,
            contract_version=None,
            registry_contract_version=registry["contract_version"],
            allowed_controlled_slice_ids=[],
            admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
            current_controlled_slice_ids=current_slice_ids,
            promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
            broad_agent_layer_requested=False,
            broad_blockers=_build_broad_blockers(
                agent_ids=agent_ids,
                promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
                current_controlled_slice_ids=current_slice_ids,
                admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
                allowed_controlled_slice_ids=[],
                governance_inputs_ready=False,
                registry_ready=registry["ready"],
            ),
            blockers=blockers,
            agent_ids=agent_ids,
        )

    blockers: list[GovernanceBlocker] = list(registry["blockers"])
    unknown_fields = sorted(set(raw_payload) - _ALLOWED_MANIFEST_FIELDS)
    if unknown_fields:
        blockers.append(
            GovernanceBlocker(
                code="manifest_unknown_fields",
                message=(
                    "agent-layer governance manifest contains unknown fields: "
                    + ", ".join(unknown_fields)
                ),
            )
        )

    contract_version = raw_payload.get("contract_version")
    if not isinstance(contract_version, str):
        blockers.append(
            GovernanceBlocker(
                code="contract_version_type_error",
                message="agent-layer governance field 'contract_version' must be a string",
            )
        )
    elif contract_version != AGENT_LAYER_GOVERNANCE_CONTRACT_VERSION:
        blockers.append(
            GovernanceBlocker(
                code="contract_version_mismatch",
                message=(
                    "agent-layer governance contract_version must be "
                    f"'{AGENT_LAYER_GOVERNANCE_CONTRACT_VERSION}'"
                ),
            )
        )

    requested_enable = raw_payload.get("agent_layer_governance_enabled")
    if type(requested_enable) is not bool:
        blockers.append(
            GovernanceBlocker(
                code="agent_layer_governance_enabled_type_error",
                message="agent-layer governance field 'agent_layer_governance_enabled' must be a boolean",
            )
        )

    broad_agent_layer_requested = raw_payload.get("broad_agent_layer_enabled")
    if type(broad_agent_layer_requested) is not bool:
        blockers.append(
            GovernanceBlocker(
                code="broad_agent_layer_enabled_type_error",
                message="agent-layer governance field 'broad_agent_layer_enabled' must be a boolean",
            )
        )
        broad_agent_layer_requested = False

    allowed_controlled_slice_ids = raw_payload.get("allowed_controlled_slice_ids")
    normalized_allowed_slice_ids: list[str] = []
    if not isinstance(allowed_controlled_slice_ids, list):
        blockers.append(
            GovernanceBlocker(
                code="allowed_controlled_slice_ids_type_error",
                message="agent-layer governance field 'allowed_controlled_slice_ids' must be a list of non-empty strings",
            )
        )
    else:
        normalized_allowed_slice_ids = [str(item).strip() for item in allowed_controlled_slice_ids]
        if any(not isinstance(item, str) or not item.strip() for item in allowed_controlled_slice_ids):
            blockers.append(
                GovernanceBlocker(
                    code="allowed_controlled_slice_ids_item_type_error",
                    message="agent-layer governance field 'allowed_controlled_slice_ids' must contain only non-empty strings",
                )
            )
        elif len(set(normalized_allowed_slice_ids)) != len(normalized_allowed_slice_ids):
            blockers.append(
                GovernanceBlocker(
                    code="allowed_controlled_slice_ids_duplicate",
                    message="agent-layer governance allowed_controlled_slice_ids contains duplicate slice ids",
                )
            )
        else:
            if registry["ready"]:
                not_admitted_slice_ids = [
                    slice_id
                    for slice_id in normalized_allowed_slice_ids
                    if slice_id not in set(registry["admitted_controlled_slice_ids"])
                ]
                if not_admitted_slice_ids:
                    blockers.append(
                        GovernanceBlocker(
                            code="allowed_controlled_slice_ids_out_of_scope",
                            message=(
                                "agent-layer governance allowed_controlled_slice_ids includes slice ids that are not "
                                "admitted by the governed-slice registry: "
                                + ", ".join(not_admitted_slice_ids)
                            ),
                        )
                    )
            missing_current_slice_ids = [
                slice_id
                for slice_id in current_slice_ids
                if slice_id not in set(normalized_allowed_slice_ids)
            ]
            if missing_current_slice_ids:
                blockers.append(
                    GovernanceBlocker(
                        code="allowed_controlled_slice_ids_mismatch",
                        message=(
                            "agent-layer governance allowed_controlled_slice_ids must include all currently shipped "
                            "governed slice ids: "
                            + ", ".join(missing_current_slice_ids)
                        ),
                    )
                )

    governance_inputs_ready = not blockers
    broad_blockers = _build_broad_blockers(
        agent_ids=agent_ids,
        promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
        current_controlled_slice_ids=current_slice_ids,
        admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
        allowed_controlled_slice_ids=normalized_allowed_slice_ids,
        governance_inputs_ready=governance_inputs_ready,
        registry_ready=registry["ready"],
    )

    if broad_agent_layer_requested is True and requested_enable is not True:
        blockers.append(
            GovernanceBlocker(
                code="broad_agent_layer_requires_agent_layer_governance_enabled",
                message="broad agent layer cannot be enabled unless agent_layer_governance_enabled is true",
            )
        )
    if broad_agent_layer_requested is True and broad_blockers:
        blockers.append(
            GovernanceBlocker(
                code="broad_agent_layer_not_ready",
                message="broad agent layer was requested before broad-readiness blockers were cleared",
            )
        )

    if blockers:
        return _build_result(
            status="blocked",
            manifest_path=resolved_manifest_path,
            registry_path=resolved_registry_path,
            contract_version=contract_version if isinstance(contract_version, str) else None,
            registry_contract_version=registry["contract_version"],
            allowed_controlled_slice_ids=normalized_allowed_slice_ids,
            admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
            current_controlled_slice_ids=current_slice_ids,
            promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
            broad_agent_layer_requested=bool(broad_agent_layer_requested),
            broad_blockers=broad_blockers,
            blockers=blockers,
            agent_ids=agent_ids,
        )

    return _build_result(
        status="enabled" if requested_enable else "disabled",
        manifest_path=resolved_manifest_path,
        registry_path=resolved_registry_path,
        contract_version=contract_version,
        registry_contract_version=registry["contract_version"],
        allowed_controlled_slice_ids=normalized_allowed_slice_ids,
        admitted_controlled_slice_ids=registry["admitted_controlled_slice_ids"],
        current_controlled_slice_ids=current_slice_ids,
        promotion_eligible_controlled_slice_ids=promotion_eligible_slice_ids,
        broad_agent_layer_requested=bool(broad_agent_layer_requested),
        broad_blockers=broad_blockers,
        blockers=[],
        agent_ids=agent_ids,
    )


def _evaluate_governed_slice_registry(
    *,
    registry_path: Path,
    current_controlled_slice_ids: list[str],
    promotion_eligible_controlled_slice_ids: list[str],
) -> dict[str, Any]:
    if not registry_path.exists():
        return {
            "ready": False,
            "contract_version": None,
            "admitted_controlled_slice_ids": [],
            "blockers": [
                GovernanceBlocker(
                    code="governed_slice_registry_missing",
                    message=f"governed-slice registry is missing: {registry_path}",
                )
            ],
        }

    try:
        raw_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ready": False,
            "contract_version": None,
            "admitted_controlled_slice_ids": [],
            "blockers": [
                GovernanceBlocker(
                    code="governed_slice_registry_invalid_json",
                    message=f"governed-slice registry is not valid JSON: {exc.msg}",
                )
            ],
        }

    if not isinstance(raw_payload, dict):
        return {
            "ready": False,
            "contract_version": None,
            "admitted_controlled_slice_ids": [],
            "blockers": [
                GovernanceBlocker(
                    code="governed_slice_registry_not_object",
                    message="governed-slice registry must be a JSON object",
                )
            ],
        }

    blockers: list[GovernanceBlocker] = []
    unknown_fields = sorted(set(raw_payload) - _ALLOWED_GOVERNED_SLICE_REGISTRY_FIELDS)
    if unknown_fields:
        blockers.append(
            GovernanceBlocker(
                code="governed_slice_registry_unknown_fields",
                message="governed-slice registry contains unknown fields: " + ", ".join(unknown_fields),
            )
        )

    contract_version = raw_payload.get("contract_version")
    if not isinstance(contract_version, str):
        blockers.append(
            GovernanceBlocker(
                code="governed_slice_registry_contract_version_type_error",
                message="governed-slice registry field 'contract_version' must be a string",
            )
        )
    elif contract_version != GOVERNED_SLICE_REGISTRY_CONTRACT_VERSION:
        blockers.append(
            GovernanceBlocker(
                code="governed_slice_registry_contract_version_mismatch",
                message=(
                    "governed-slice registry contract_version must be "
                    f"'{GOVERNED_SLICE_REGISTRY_CONTRACT_VERSION}'"
                ),
            )
        )

    admitted_controlled_slice_ids = raw_payload.get("admitted_controlled_slice_ids")
    normalized_admitted_slice_ids: list[str] = []
    if not isinstance(admitted_controlled_slice_ids, list):
        blockers.append(
            GovernanceBlocker(
                code="admitted_controlled_slice_ids_type_error",
                message="governed-slice registry field 'admitted_controlled_slice_ids' must be a list of non-empty strings",
            )
        )
    else:
        normalized_admitted_slice_ids = [str(item).strip() for item in admitted_controlled_slice_ids]
        if any(not isinstance(item, str) or not item.strip() for item in admitted_controlled_slice_ids):
            blockers.append(
                GovernanceBlocker(
                    code="admitted_controlled_slice_ids_item_type_error",
                    message="governed-slice registry field 'admitted_controlled_slice_ids' must contain only non-empty strings",
                )
            )
        elif len(set(normalized_admitted_slice_ids)) != len(normalized_admitted_slice_ids):
            blockers.append(
                GovernanceBlocker(
                    code="admitted_controlled_slice_ids_duplicate",
                    message="governed-slice registry admitted_controlled_slice_ids contains duplicate slice ids",
                )
            )
        else:
            promotion_eligible_slice_id_set = set(promotion_eligible_controlled_slice_ids)
            out_of_scope_slice_ids = [
                slice_id
                for slice_id in normalized_admitted_slice_ids
                if slice_id not in promotion_eligible_slice_id_set
            ]
            if out_of_scope_slice_ids:
                blockers.append(
                    GovernanceBlocker(
                        code="admitted_controlled_slice_ids_out_of_scope",
                        message=(
                            "governed-slice registry admitted_controlled_slice_ids includes slice ids that do not "
                            "satisfy the promotion-grade governed-slice contract: "
                            + ", ".join(out_of_scope_slice_ids)
                        ),
                    )
                )
            missing_current_slice_ids = [
                slice_id
                for slice_id in current_controlled_slice_ids
                if slice_id not in set(normalized_admitted_slice_ids)
            ]
            if missing_current_slice_ids:
                blockers.append(
                    GovernanceBlocker(
                        code="current_controlled_slice_ids_not_admitted",
                        message=(
                            "governed-slice registry must admit all currently shipped governed slice ids: "
                            + ", ".join(missing_current_slice_ids)
                        ),
                    )
                )

    return {
        "ready": not blockers,
        "contract_version": contract_version if isinstance(contract_version, str) else None,
        "admitted_controlled_slice_ids": normalized_admitted_slice_ids,
        "blockers": blockers,
    }


def _build_broad_blockers(
    *,
    agent_ids: list[str],
    promotion_eligible_controlled_slice_ids: list[str],
    current_controlled_slice_ids: list[str],
    admitted_controlled_slice_ids: list[str],
    allowed_controlled_slice_ids: list[str],
    governance_inputs_ready: bool,
    registry_ready: bool,
) -> list[GovernanceBlocker]:
    blockers: list[GovernanceBlocker] = []
    if not governance_inputs_ready:
        blockers.append(
            GovernanceBlocker(
                code="broad_governance_inputs_not_ready",
                message="broad-readiness requires a structurally valid manifest and registry evaluation",
            )
        )
    promotion_eligible_set = set(promotion_eligible_controlled_slice_ids)
    non_promotion_eligible_agent_ids = [
        agent_id for agent_id in agent_ids if agent_id not in promotion_eligible_set
    ]
    if non_promotion_eligible_agent_ids:
        blockers.append(
            GovernanceBlocker(
                code="broad_non_promotion_eligible_agents",
                message=(
                    "broad-readiness requires every exported agent definition to satisfy the promotion-grade "
                    "governed-slice contract: "
                    + ", ".join(non_promotion_eligible_agent_ids)
                ),
            )
        )
    if not registry_ready:
        blockers.append(
            GovernanceBlocker(
                code="broad_governed_slice_registry_not_ready",
                message="broad-readiness requires a valid governed-slice registry evaluation",
            )
        )
    else:
        admitted_slice_id_set = set(admitted_controlled_slice_ids)
        missing_registry_ids = [
            slice_id
            for slice_id in promotion_eligible_controlled_slice_ids
            if slice_id not in admitted_slice_id_set
        ]
        extra_registry_ids = [
            slice_id for slice_id in admitted_controlled_slice_ids if slice_id not in promotion_eligible_set
        ]
        if missing_registry_ids or extra_registry_ids:
            details: list[str] = []
            if missing_registry_ids:
                details.append("missing: " + ", ".join(missing_registry_ids))
            if extra_registry_ids:
                details.append("extra: " + ", ".join(extra_registry_ids))
            blockers.append(
                GovernanceBlocker(
                    code="broad_registry_exact_match_required",
                    message=(
                        "broad-readiness requires the governed-slice registry to exactly match the promotion-eligible "
                        "controlled slice ids (" + "; ".join(details) + ")"
                    ),
                )
            )

    allowed_slice_id_set = set(allowed_controlled_slice_ids)
    missing_current_slice_ids = [
        slice_id for slice_id in current_controlled_slice_ids if slice_id not in allowed_slice_id_set
    ]
    if missing_current_slice_ids:
        blockers.append(
            GovernanceBlocker(
                code="broad_allowed_controlled_slice_ids_not_ready",
                message=(
                    "broad-readiness requires the manifest to continue allowing all currently shipped governed "
                    "slice ids: " + ", ".join(missing_current_slice_ids)
                ),
            )
        )
    return blockers


def _build_result(
    *,
    status: str,
    manifest_path: Path,
    registry_path: Path,
    contract_version: str | None,
    registry_contract_version: str | None,
    allowed_controlled_slice_ids: list[str],
    admitted_controlled_slice_ids: list[str],
    current_controlled_slice_ids: list[str],
    promotion_eligible_controlled_slice_ids: list[str],
    broad_agent_layer_requested: bool,
    broad_blockers: list[GovernanceBlocker],
    blockers: list[GovernanceBlocker],
    agent_ids: list[str],
) -> dict[str, Any]:
    payload_blockers = [item.to_payload() for item in blockers]
    payload_broad_blockers = [item.to_payload() for item in broad_blockers]
    governance_enabled = status == "enabled" and not payload_blockers
    broad_agent_layer_ready = not payload_broad_blockers
    broad_agent_layer_enabled = (
        governance_enabled
        and broad_agent_layer_requested
        and broad_agent_layer_ready
    )
    current_slice_id_set = set(current_controlled_slice_ids)
    registered_pending_promotion_controlled_slice_ids = [
        slice_id for slice_id in admitted_controlled_slice_ids if slice_id not in current_slice_id_set
    ]
    return {
        "status": status,
        "manifest_path": str(manifest_path),
        "governed_slice_registry_path": str(registry_path),
        "contract_version": contract_version,
        "governed_slice_registry_contract_version": registry_contract_version,
        "promotion_contract_version": CONTROLLED_AGENT_SLICE_PROMOTION_CONTRACT_VERSION,
        "agent_layer_governance_enabled": governance_enabled,
        "allowed_controlled_slice_ids": allowed_controlled_slice_ids,
        "admitted_controlled_slice_ids": admitted_controlled_slice_ids,
        "expected_controlled_slice_ids": list(current_controlled_slice_ids),
        "current_controlled_slice_ids": list(current_controlled_slice_ids),
        "promotion_eligible_controlled_slice_ids": list(promotion_eligible_controlled_slice_ids),
        "candidate_controlled_slice_ids": list(promotion_eligible_controlled_slice_ids),
        "registered_pending_promotion_controlled_slice_ids": registered_pending_promotion_controlled_slice_ids,
        "all_agent_ids": list(agent_ids),
        "broad_agent_layer_ready": broad_agent_layer_ready,
        "broad_agent_layer_requested": broad_agent_layer_requested,
        "broad_agent_layer_enabled": broad_agent_layer_enabled,
        "broad_blockers": payload_broad_blockers,
        "blockers": payload_blockers,
    }


def _resolve_manifest_path(manifest_path: Path | None) -> Path:
    return (manifest_path or AGENT_LAYER_GOVERNANCE_MANIFEST_PATH).resolve()


def _resolve_registry_path(registry_path: Path | None) -> Path:
    return (registry_path or GOVERNED_SLICE_REGISTRY_PATH).resolve()


def _controlled_slice_sort_key(agent: dict[str, Any]) -> tuple[int, str]:
    slice_mode = str(agent.get("slice_mode", "")).strip()
    if slice_mode == "create_new_object":
        rank = 0
    elif slice_mode == "continue_existing_object":
        rank = 1
    else:
        rank = 2
    return (rank, str(agent.get("agent_id", "")).strip())
