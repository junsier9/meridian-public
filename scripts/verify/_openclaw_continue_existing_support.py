from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.compat.naming import getenv_compat, materialize_env_alias
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.session import FileObjectStore
from enhengclaw.core.signals import Signal
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness

from enhengclaw.integrations.openclaw.attention_allocator import (
    OPENCLAW_ATTENTION_ALLOCATOR_CONTRACT_VERSION,
    main as attention_allocator_main,
    openclaw_attention_allocator_request_from_payload,
)
from enhengclaw.integrations.openclaw.evidence_agent import (
    OPENCLAW_EVIDENCE_AGENT_CONTRACT_VERSION,
    main as evidence_main,
    openclaw_evidence_agent_request_from_payload,
)
from enhengclaw.integrations.openclaw.research_lead import (
    OPENCLAW_RESEARCH_LEAD_CONTRACT_VERSION,
    main as research_lead_main,
    openclaw_research_lead_request_from_payload,
)
from enhengclaw.integrations.openclaw.research_synthesizer import (
    OPENCLAW_RESEARCH_SYNTHESIZER_CONTRACT_VERSION,
    main as research_synthesizer_main,
    openclaw_research_synthesizer_request_from_payload,
)
from enhengclaw.integrations.openclaw.risk_governance_agent import (
    OPENCLAW_RISK_GOVERNANCE_AGENT_CONTRACT_VERSION,
    main as risk_governance_main,
    openclaw_risk_governance_agent_request_from_payload,
)
from enhengclaw.integrations.openclaw.risk_signal_agent import (
    OPENCLAW_RISK_SIGNAL_AGENT_CONTRACT_VERSION,
    main as risk_signal_main,
    openclaw_risk_signal_agent_request_from_payload,
)
from enhengclaw.integrations.openclaw.validation_agent import (
    OPENCLAW_VALIDATION_AGENT_CONTRACT_VERSION,
    main as validation_main,
    openclaw_validation_agent_request_from_payload,
)


OPENCLAW_ENV = "OPENCLAW"
OPENCLAW_BASE_URL_ENV = "OPENCLAW_BASE_URL"
OPENCLAW_MODEL_NAME_ENV = "OPENCLAW_MODEL_NAME"
OPENCLAW_MODEL_TIMEOUT_SECONDS_ENV = "OPENCLAW_MODEL_TIMEOUT_SECONDS"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL_NAME = "gpt-5.4"
DEFAULT_OPENAI_MODEL_TIMEOUT_SECONDS = "30"
GENERIC_AUDIT_WSL = "/root/.openclaw/workspace-meridian-alpha-audit/tools/audit_openclaw_response.sh"


@dataclass(frozen=True, slots=True)
class OpenClawLaneConfig:
    lane_id: str
    module_name: str
    contract_version: str
    text_field_name: str
    fixture_root: Path
    env_prefix: str
    main_callable: Callable[[list[str] | None], int]
    request_loader: Callable[[dict[str, Any]], Any]
    review_gated: bool = False
    live_text_override: str | None = None
    recorded_wsl_smoke: str = ""
    live_wsl_smoke: str = ""
    request_runner_wsl: str = ""


OPENCLAW_LANE_CONFIGS: tuple[OpenClawLaneConfig, ...] = (
    OpenClawLaneConfig(
        lane_id="evidence_agent",
        module_name="enhengclaw.integrations.openclaw.evidence_agent",
        contract_version=OPENCLAW_EVIDENCE_AGENT_CONTRACT_VERSION,
        text_field_name="evidence_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "evidence_agent",
        env_prefix="ENHENGCLAW_EVIDENCE_AGENT_MODEL",
        main_callable=evidence_main,
        request_loader=openclaw_evidence_agent_request_from_payload,
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_evidence_agent_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_evidence_agent_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_evidence_agent_request.sh",
    ),
    OpenClawLaneConfig(
        lane_id="risk_signal_agent",
        module_name="enhengclaw.integrations.openclaw.risk_signal_agent",
        contract_version=OPENCLAW_RISK_SIGNAL_AGENT_CONTRACT_VERSION,
        text_field_name="risk_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "risk_signal_agent",
        env_prefix="ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL",
        main_callable=risk_signal_main,
        request_loader=openclaw_risk_signal_agent_request_from_payload,
        live_text_override=(
            "facts=AIX lost the prior spot breakout structure while perp pressure moved against the setup after the "
            "existing supportive flow claims; interpretation=this creates a fresh invalidation risk for the current "
            "monitoring object; uncertainty=the risk still needs next-cycle confirmation and host review before any "
            "workflow decision changes."
        ),
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_risk_signal_agent_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_risk_signal_agent_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_risk_signal_agent_request.sh",
    ),
    OpenClawLaneConfig(
        lane_id="attention_allocator",
        module_name="enhengclaw.integrations.openclaw.attention_allocator",
        contract_version=OPENCLAW_ATTENTION_ALLOCATOR_CONTRACT_VERSION,
        text_field_name="attention_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "attention_allocator",
        env_prefix="ENHENGCLAW_ATTENTION_ALLOCATOR_MODEL",
        main_callable=attention_allocator_main,
        request_loader=openclaw_attention_allocator_request_from_payload,
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_attention_allocator_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_attention_allocator_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_attention_allocator_request.sh",
    ),
    OpenClawLaneConfig(
        lane_id="research_synthesizer",
        module_name="enhengclaw.integrations.openclaw.research_synthesizer",
        contract_version=OPENCLAW_RESEARCH_SYNTHESIZER_CONTRACT_VERSION,
        text_field_name="synthesis_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "research_synthesizer",
        env_prefix="ENHENGCLAW_RESEARCH_SYNTHESIZER_MODEL",
        main_callable=research_synthesizer_main,
        request_loader=openclaw_research_synthesizer_request_from_payload,
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_research_synthesizer_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_research_synthesizer_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_research_synthesizer_request.sh",
    ),
    OpenClawLaneConfig(
        lane_id="research_lead",
        module_name="enhengclaw.integrations.openclaw.research_lead",
        contract_version=OPENCLAW_RESEARCH_LEAD_CONTRACT_VERSION,
        text_field_name="directive_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "research_lead",
        env_prefix="ENHENGCLAW_RESEARCH_LEAD_MODEL",
        main_callable=research_lead_main,
        request_loader=openclaw_research_lead_request_from_payload,
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_research_lead_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_research_lead_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_research_lead_request.sh",
    ),
    OpenClawLaneConfig(
        lane_id="risk_governance_agent",
        module_name="enhengclaw.integrations.openclaw.risk_governance_agent",
        contract_version=OPENCLAW_RISK_GOVERNANCE_AGENT_CONTRACT_VERSION,
        text_field_name="governance_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "risk_governance_agent",
        env_prefix="ENHENGCLAW_RISK_GOVERNANCE_AGENT_MODEL",
        main_callable=risk_governance_main,
        request_loader=openclaw_risk_governance_agent_request_from_payload,
        review_gated=True,
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_risk_governance_agent_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_risk_governance_agent_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_risk_governance_agent_request.sh",
    ),
    OpenClawLaneConfig(
        lane_id="validation_agent",
        module_name="enhengclaw.integrations.openclaw.validation_agent",
        contract_version=OPENCLAW_VALIDATION_AGENT_CONTRACT_VERSION,
        text_field_name="validation_text",
        fixture_root=ROOT / "fixtures" / "agent_golden" / "validation_agent",
        env_prefix="ENHENGCLAW_VALIDATION_AGENT_MODEL",
        main_callable=validation_main,
        request_loader=openclaw_validation_agent_request_from_payload,
        review_gated=True,
        live_text_override=(
            "Publish must remain blocked because the object is still in monitoring, the publish gate is not legal "
            "yet, and the validation blocker remains unresolved."
        ),
        recorded_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_validation_agent_recorded.sh",
        live_wsl_smoke="/root/.openclaw/workspace-meridian-alpha-main/tools/smoke_validation_agent_live.sh",
        request_runner_wsl="/root/.openclaw/workspace-meridian-alpha-main/tools/run_validation_agent_request.sh",
    ),
)


def lane_config(lane_id: str) -> OpenClawLaneConfig:
    for config in OPENCLAW_LANE_CONFIGS:
        if config.lane_id == lane_id:
            return config
    raise KeyError(f"Unknown OpenClaw lane config: {lane_id}")


def lane_ids(*, review_gated: bool | None = None) -> tuple[str, ...]:
    if review_gated is None:
        return tuple(config.lane_id for config in OPENCLAW_LANE_CONFIGS)
    return tuple(config.lane_id for config in OPENCLAW_LANE_CONFIGS if config.review_gated is review_gated)


def load_fixture(config: OpenClawLaneConfig, name: str) -> dict[str, object]:
    return json.loads((config.fixture_root / name / "input.json").read_text(encoding="utf-8"))


def transcript_path(config: OpenClawLaneConfig, name: str) -> Path:
    return config.fixture_root / name / "model_transcript.json"


def build_request_payload(
    config: OpenClawLaneConfig,
    fixture: dict[str, object],
    *,
    execution_permit_path: str | Path,
    compiler_backend: str = "recorded",
    recorded_transcript_path: str | Path | None = None,
    artifacts_root: str | Path | None = None,
    include_input_id: bool = True,
    input_id: str | None = None,
    apply_live_overrides: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": config.contract_version,
        "subject": fixture["subject"],
        "scope": fixture["scope"],
        "object_id": fixture["object_id"],
        config.text_field_name: fixture[config.text_field_name],
        "execution_permit_path": str(execution_permit_path),
        "compiler_backend": compiler_backend,
    }
    if include_input_id:
        payload["input_id"] = input_id or f"{fixture['case_id']}:1"
    if artifacts_root is not None:
        payload["artifacts_root"] = str(artifacts_root)
    if recorded_transcript_path is not None:
        payload["recorded_transcript_path"] = str(recorded_transcript_path)
    if apply_live_overrides and config.live_text_override:
        payload[config.text_field_name] = config.live_text_override
    return payload


def build_pythonpath_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(ROOT), str(SRC)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra:
        env.update(extra)
    return env


def required_live_env_names(config: OpenClawLaneConfig) -> tuple[str, str, str]:
    return (
        f"{config.env_prefix}_BASE_URL",
        f"{config.env_prefix}_NAME",
        backend_api_key_env_name(config),
    )


def backend_api_key_env_name(config: OpenClawLaneConfig) -> str:
    if config.lane_id == "evidence_agent":
        return legacy_api_key_env_name(config)
    return f"{config.env_prefix}_API_KEY"


def legacy_api_key_env_name(config: OpenClawLaneConfig) -> str:
    return f"{config.env_prefix.removesuffix('_MODEL')}_API_KEY"


def api_key_env_candidates(config: OpenClawLaneConfig) -> tuple[str, ...]:
    names = [backend_api_key_env_name(config)]
    legacy_name = legacy_api_key_env_name(config)
    if legacy_name not in names:
        names.append(legacy_name)
    return tuple(names)


def resolve_lane_live_env(
    config: OpenClawLaneConfig,
    *,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, object]]:
    env = build_pythonpath_env(extra=None if base_env is None else dict(base_env))
    base_url_name, model_name_name, api_key_name = required_live_env_names(config)
    timeout_name = base_url_name.replace("_BASE_URL", "_TIMEOUT_SECONDS")
    shared_base_url = str(env.get(OPENCLAW_BASE_URL_ENV, "")).strip() or DEFAULT_OPENAI_BASE_URL
    shared_model_name = str(env.get(OPENCLAW_MODEL_NAME_ENV, "")).strip() or DEFAULT_OPENAI_MODEL_NAME
    shared_timeout_seconds = (
        str(env.get(OPENCLAW_MODEL_TIMEOUT_SECONDS_ENV, "")).strip() or DEFAULT_OPENAI_MODEL_TIMEOUT_SECONDS
    )
    mapping_used = False
    base_url_value = str(getenv_compat(base_url_name, "", env=env) or "").strip()
    model_name_value = str(getenv_compat(model_name_name, "", env=env) or "").strip()
    timeout_value = str(getenv_compat(timeout_name, "", env=env) or "").strip()
    api_key_value = ""
    for candidate_name in api_key_env_candidates(config):
        api_key_value = str(getenv_compat(candidate_name, "", env=env) or "").strip()
        if api_key_value:
            break
    materialize_env_alias(env, base_url_name, base_url_value or shared_base_url)
    materialize_env_alias(env, model_name_name, model_name_value or shared_model_name)
    materialize_env_alias(env, timeout_name, timeout_value or shared_timeout_seconds)
    if api_key_value:
        materialize_env_alias(env, api_key_name, api_key_value)
    else:
        openclaw_key = str(env.get(OPENCLAW_ENV, "")).strip()
        if openclaw_key:
            materialize_env_alias(env, api_key_name, openclaw_key)
            mapping_used = True
    return env, {
        "openclaw_mapping_used": mapping_used,
        "required_live_env": required_live_env_names(config),
        "timeout_env_name": timeout_name,
        "shared_openclaw_base_url": shared_base_url,
        "shared_openclaw_model_name": shared_model_name,
        "shared_openclaw_model_timeout_seconds": shared_timeout_seconds,
    }


def run_lane_module(
    config: OpenClawLaneConfig,
    *,
    request_payload: dict[str, object],
    tmpdir: str | Path,
    env_extra: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    tmpdir_path = Path(tmpdir)
    request_path = tmpdir_path / "request.json"
    response_path = tmpdir_path / "response.json"
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            config.module_name,
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=ROOT,
        env=build_pythonpath_env(env_extra),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, request_path, response_path


def seed_existing_object(*, artifacts_root: str | Path, object_id: str, scope: str, subject: str) -> None:
    runtime = RuntimeOrchestrator(
        store=FileObjectStore(Path(artifacts_root) / "runtime_sessions"),
        agent_ingress_firewall=AgentIngressFirewall(
            quarantine_buffer=QuarantineBuffer(Path(artifacts_root) / "quarantine"),
            replayable_input_log=ReplayableInputLog(Path(artifacts_root) / "replay_log"),
        ),
    )
    with runtime_worker_harness(slug=f"openclaw-seed-{object_id}", scope=scope):
        runtime.run_new(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope=scope,
            signals=_seed_signals(object_id, subject, scope),
        )


def tempdir(prefix: str) -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix, dir=_short_temp_root())


def _seed_signals(object_id: str, subject: str, scope: str) -> list[Signal]:
    return [
        Signal(
            signal_id=f"{object_id}:seed:1",
            object_type=ObjectType.ASSET,
            subject=subject,
            predicate="spot_breakout",
            value=f"{subject} spot structure remains constructive",
            claim_type=ClaimType.MEASUREMENT,
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=82,
            scope=scope,
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            signal_id=f"{object_id}:seed:2",
            object_type=ObjectType.ASSET,
            subject=subject,
            predicate="wallet_buy",
            value=f"{subject} still shows supportive flow from large buyers",
            claim_type=ClaimType.FLOW,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=78,
            scope=scope,
            time_horizon=TimeHorizon.INTRADAY,
        ),
    ]


def _short_temp_root() -> str | None:
    candidates: list[Path] = []
    if os.name == "nt":
        temp_drive = Path(tempfile.gettempdir()).drive or Path.cwd().drive
        if temp_drive:
            candidates.append(Path(f"{temp_drive}\\e"))
    candidates.append(Path(tempfile.gettempdir()) / "e")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(candidate)
    return None


__all__ = [
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_OPENAI_MODEL_NAME",
    "GENERIC_AUDIT_WSL",
    "OPENCLAW_ENV",
    "OPENCLAW_LANE_CONFIGS",
    "OpenClawLaneConfig",
    "ROOT",
    "SRC",
    "api_key_env_candidates",
    "backend_api_key_env_name",
    "build_pythonpath_env",
    "build_request_payload",
    "lane_config",
    "lane_ids",
    "legacy_api_key_env_name",
    "load_fixture",
    "required_live_env_names",
    "resolve_lane_live_env",
    "run_lane_module",
    "seed_existing_object",
    "tempdir",
    "transcript_path",
]
