from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhengclaw.agents.definitions import (
    ATTENTION_ALLOCATOR_AGENT,
    EVIDENCE_AGENT,
    MARKET_OBSERVER_AGENT,
    RESEARCH_LEAD_AGENT,
    RESEARCH_SYNTHESIZER_AGENT,
    RISK_GOVERNANCE_AGENT,
    RISK_SIGNAL_AGENT,
    VALIDATION_AGENT,
)


MAIN_OWNER_ARCHITECTURE_CONTRACT_VERSION = "main_owner_architecture.v1"
MAIN_OWNER_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "agent_architecture" / "main_owner_manifest.json"
)

_RUNTIME_AGENT_DEFINITIONS = {
    str(agent["agent_id"]): agent
    for agent in (
        MARKET_OBSERVER_AGENT,
        EVIDENCE_AGENT,
        RISK_SIGNAL_AGENT,
        RISK_GOVERNANCE_AGENT,
        VALIDATION_AGENT,
        ATTENTION_ALLOCATOR_AGENT,
        RESEARCH_SYNTHESIZER_AGENT,
        RESEARCH_LEAD_AGENT,
    )
}


@dataclass(frozen=True, slots=True)
class AgentArchitectureValidationResult:
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def load_main_owner_manifest(path: Path | None = None) -> dict[str, Any]:
    resolved = (path or MAIN_OWNER_MANIFEST_PATH).resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("main owner architecture manifest must be a JSON object")
    return payload


def validate_main_owner_manifest(path: Path | None = None) -> AgentArchitectureValidationResult:
    payload = load_main_owner_manifest(path)
    errors: list[str] = []
    contract_version = payload.get("contract_version")
    if contract_version != MAIN_OWNER_ARCHITECTURE_CONTRACT_VERSION:
        errors.append(
            "main owner architecture manifest contract_version must be "
            f"'{MAIN_OWNER_ARCHITECTURE_CONTRACT_VERSION}'"
        )

    owner = payload.get("owner")
    if not isinstance(owner, dict):
        errors.append("main owner architecture manifest must define an 'owner' object")
        return AgentArchitectureValidationResult(errors=tuple(errors))
    public_entrypoint = payload.get("public_entrypoint")
    if not isinstance(public_entrypoint, dict):
        errors.append("main owner architecture manifest must define a 'public_entrypoint' object")
    elif str(public_entrypoint.get("entrypoint", "")).strip() != "enhengclaw.orchestration.runtime.GovernedAgentOrchestrator.run_governed_write":
        errors.append(
            "main owner architecture manifest public_entrypoint.entrypoint must be "
            "'enhengclaw.orchestration.runtime.GovernedAgentOrchestrator.run_governed_write'"
        )

    owner_agent_id = str(owner.get("agent_id", "")).strip()
    if owner_agent_id != "rulebook_owner":
        errors.append("main owner architecture manifest owner.agent_id must be 'rulebook_owner'")
    if owner.get("final_response_owner") is not True:
        errors.append("main owner architecture manifest owner.final_response_owner must be true")
    owner_allowed_tools = [str(item).strip() for item in owner.get("allowed_tools", []) if str(item).strip()]
    artifact_owners = _artifact_owners(payload)

    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        errors.append("main owner architecture manifest must define a non-empty 'agents' list")
        return AgentArchitectureValidationResult(errors=tuple(errors))

    seen_agent_ids: set[str] = set()
    owner_count = 0
    artifact_ids = _artifact_ids(payload)
    for agent in agents:
        if not isinstance(agent, dict):
            errors.append("every manifest agent entry must be an object")
            continue
        agent_id = str(agent.get("agent_id", "")).strip()
        if not agent_id:
            errors.append("every manifest agent entry requires a non-empty agent_id")
            continue
        if agent_id in seen_agent_ids:
            errors.append(f"manifest agent_id is duplicated: {agent_id}")
            continue
        seen_agent_ids.add(agent_id)

        kind = str(agent.get("kind", "")).strip()
        if kind not in {"owner", "delegate"}:
            errors.append(f"manifest agent '{agent_id}' has unsupported kind '{kind}'")
        if kind == "owner":
            owner_count += 1

        if kind == "delegate":
            runtime_agent_id = str(agent.get("runtime_agent_id", "")).strip()
            if runtime_agent_id not in _RUNTIME_AGENT_DEFINITIONS:
                errors.append(
                    f"delegate agent '{agent_id}' references unknown runtime_agent_id '{runtime_agent_id}'"
                )
            if str(agent.get("owner_agent_id", "")).strip() != owner_agent_id:
                errors.append(f"delegate agent '{agent_id}' must point back to owner '{owner_agent_id}'")
            if agent.get("final_response_owner") is not False:
                errors.append(f"delegate agent '{agent_id}' must not own the final response")
            delegate_tools = [str(item).strip() for item in agent.get("allowed_tools", []) if str(item).strip()]
            inspect_tools = [item for item in delegate_tools if ".runtime_session_views.inspect_" in item]
            if inspect_tools:
                errors.append(
                    f"delegate agent '{agent_id}' must not list owner review tools in allowed_tools: {', '.join(sorted(inspect_tools))}"
                )
            required_reviews = agent.get("required_reviews", [])
            if required_reviews:
                if not isinstance(required_reviews, list):
                    errors.append(f"delegate agent '{agent_id}' field required_reviews must be a list")
                else:
                    normalized_required_reviews = [str(item).strip() for item in required_reviews]
                    if any(not item for item in normalized_required_reviews):
                        errors.append(f"delegate agent '{agent_id}' field required_reviews must contain only non-empty strings")
                    missing_from_owner = [
                        item for item in normalized_required_reviews if item not in owner_allowed_tools
                    ]
                    if missing_from_owner:
                        errors.append(
                            f"delegate agent '{agent_id}' required_reviews must be owner tools: {', '.join(sorted(missing_from_owner))}"
                        )

        _validate_agent_lists(agent, "when_to_call", errors)
        _validate_agent_lists(agent, "when_not_to_call", errors)
        _validate_agent_lists(agent, "allowed_tools", errors)
        _validate_agent_lists(agent, "stop_conditions", errors)
        _validate_agent_lists(agent, "reads_artifacts", errors, allowed=artifact_ids)
        _validate_agent_lists(agent, "writes_artifacts", errors, allowed=artifact_ids)
        if kind == "delegate":
            illegal_owner_writes = [
                artifact_id
                for artifact_id in [str(item).strip() for item in agent.get("writes_artifacts", []) if str(item).strip()]
                if artifact_owners.get(artifact_id) == owner_agent_id and artifact_id != "delegate_records"
            ]
            if illegal_owner_writes:
                errors.append(
                    f"delegate agent '{agent_id}' must not declare owner-owned writes: {', '.join(sorted(illegal_owner_writes))}"
                )

        if not str(agent.get("input_schema", "")).strip():
            errors.append(f"agent '{agent_id}' must declare input_schema")
        if not str(agent.get("output_schema", "")).strip():
            errors.append(f"agent '{agent_id}' must declare output_schema")
        if not str(agent.get("failure_fallback", "")).strip():
            errors.append(f"agent '{agent_id}' must declare failure_fallback")

    if owner_count != 1:
        errors.append(f"main owner architecture manifest must declare exactly one owner; observed {owner_count}")

    return AgentArchitectureValidationResult(errors=tuple(errors))


def manifest_agent_ids(path: Path | None = None) -> list[str]:
    payload = load_main_owner_manifest(path)
    agents = payload.get("agents", [])
    return [str(agent["agent_id"]) for agent in agents if isinstance(agent, dict) and "agent_id" in agent]


def delegate_runtime_agent_ids(path: Path | None = None) -> list[str]:
    payload = load_main_owner_manifest(path)
    delegate_ids: list[str] = []
    for agent in payload.get("agents", []):
        if not isinstance(agent, dict):
            continue
        if str(agent.get("kind", "")).strip() != "delegate":
            continue
        runtime_agent_id = str(agent.get("runtime_agent_id", "")).strip()
        if runtime_agent_id:
            delegate_ids.append(runtime_agent_id)
    return delegate_ids


def owner_agent_id(path: Path | None = None) -> str:
    payload = load_main_owner_manifest(path)
    owner = payload.get("owner")
    if not isinstance(owner, dict):
        raise ValueError("main owner architecture manifest is missing owner")
    agent_id = str(owner.get("agent_id", "")).strip()
    if not agent_id:
        raise ValueError("main owner architecture manifest owner.agent_id must be non-empty")
    return agent_id


def delegate_contract_for_runtime_agent_id(
    runtime_agent_id: str,
    path: Path | None = None,
) -> dict[str, Any]:
    payload = load_main_owner_manifest(path)
    for agent in payload.get("agents", []):
        if not isinstance(agent, dict):
            continue
        if str(agent.get("kind", "")).strip() != "delegate":
            continue
        if str(agent.get("runtime_agent_id", "")).strip() == runtime_agent_id:
            return agent
    raise KeyError(f"unknown runtime agent id in main owner manifest: {runtime_agent_id}")


def required_reviews_for_runtime_agent_id(
    runtime_agent_id: str,
    path: Path | None = None,
) -> list[str]:
    contract = delegate_contract_for_runtime_agent_id(runtime_agent_id, path)
    return [str(item).strip() for item in contract.get("required_reviews", []) if str(item).strip()]


def _artifact_ids(payload: dict[str, Any]) -> set[str]:
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        return set()
    return {
        str(item.get("artifact_id", "")).strip()
        for item in artifacts
        if isinstance(item, dict) and str(item.get("artifact_id", "")).strip()
    }


def _artifact_owners(payload: dict[str, Any]) -> dict[str, str]:
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        return {}
    owners: dict[str, str] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("artifact_id", "")).strip()
        owner_agent_id = str(item.get("owner_agent_id", "")).strip()
        if artifact_id and owner_agent_id:
            owners[artifact_id] = owner_agent_id
    return owners


def _validate_agent_lists(
    agent: dict[str, Any],
    field: str,
    errors: list[str],
    *,
    allowed: set[str] | None = None,
) -> None:
    agent_id = str(agent.get("agent_id", "<unknown>")).strip()
    value = agent.get(field)
    if not isinstance(value, list) or not value:
        errors.append(f"agent '{agent_id}' must declare a non-empty list for {field}")
        return
    normalized = [str(item).strip() for item in value]
    if any(not item for item in normalized):
        errors.append(f"agent '{agent_id}' field {field} must contain only non-empty strings")
        return
    if len(set(normalized)) != len(normalized):
        errors.append(f"agent '{agent_id}' field {field} must not contain duplicates")
        return
    if allowed is not None:
        unknown = [item for item in normalized if item not in allowed]
        if unknown:
            errors.append(
                f"agent '{agent_id}' field {field} references unknown artifacts: {', '.join(sorted(unknown))}"
            )
