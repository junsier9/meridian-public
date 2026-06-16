from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import email.utils
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import tempfile
from typing import Any
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import websockets

from enhengclaw.agents.definitions._controlled_slice import CONTROLLED_AGENT_SLICE_CONTRACT_VERSION
from enhengclaw.core.execution_control import (
    CAP_CLI_SHADOW_INGEST,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    ExecutionPermit,
    TRUST_ROOT_DIR_ENV,
    default_trust_root_dir,
    list_execution_leases,
    load_execution_permit,
    resolve_allowed_signers_path,
    validate_execution_permit,
)
from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.orchestration.agent_layer_governance import (
    current_controlled_slice_definitions,
    missing_agent_layer_governance_result,
)
from enhengclaw.orchestration.shadow_ingestion_providers import (
    ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND,
    ALCHEMY_EVM_BLOCK_PROVIDER_KIND,
    ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND,
    BINANCE_TRADE_PROVIDER_KIND,
    alchemy_endpoint_url_for_network,
    build_legacy_provider_payloads,
    group_providers_by_family,
    provider_identity,
)
from enhengclaw.orchestration.worker_operations import default_ingestion_audit_root


REAL_24H_DURATION_SECONDS = 24 * 60 * 60
MIN_REAL_24H_DURATION_SECONDS = int(23.5 * 60 * 60)
REAL_24H_MIN_PERMIT_MARGIN_SECONDS = float(REAL_24H_DURATION_SECONDS + 60)
REAL_SHADOW_EVIDENCE_BUNDLE_VERSION = "real-shadow-acceptance.v1"
DEFAULT_MIN_FREE_DISK_MB = 1024
DEFAULT_MAX_TOTAL_LOG_BYTES = 128 * 1024 * 1024
DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS = 30.0
DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS = 10.0
# Shorter or non-real flows may default to 1800 seconds, but the dedicated
# real-24h gate must always clamp to REAL_24H_MIN_PERMIT_MARGIN_SECONDS.
DEFAULT_NON_REAL_PERMIT_MARGIN_SECONDS = 1800.0
_PLACEHOLDER_SECRET_TOKENS = (
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "replace-me",
    "test",
    "xxx",
)


def build_controlled_agent_slices_summary() -> dict[str, Any]:
    slices: list[dict[str, Any]] = []
    for agent in current_controlled_slice_definitions():
        slices.append(
            {
                "agent_id": str(agent["agent_id"]),
                "enabled_under_current_governance": bool(agent.get("enabled_under_current_governance")),
                "slice_mode": str(agent.get("slice_mode", "")),
                "canonical_runtime_boundary": str(agent.get("canonical_runtime_boundary", "")),
                "max_tool_calls": int(agent.get("max_tool_calls", 0)),
                "max_payloads": int(agent.get("max_payloads", 0)),
            }
        )
    return {
        "contract_version": CONTROLLED_AGENT_SLICE_CONTRACT_VERSION,
        "controlled_slice_count": len(slices),
        "verified_slice_ids": [item["agent_id"] for item in slices],
        "enabled_slice_ids": [item["agent_id"] for item in slices if item["enabled_under_current_governance"]],
        "broad_agent_layer_enabled": False,
        "slices": slices,
    }


@dataclass(frozen=True, slots=True)
class BinanceProbeError(Exception):
    failure_category: str
    transport_stage: str
    endpoint: str
    transport: str
    host: str | None
    port: int | None
    path: str
    exception_type: str
    exception_message: str
    exception_repr: str
    exception_chain: list[dict[str, Any]]
    errno: int | None = None
    close_code: int | None = None
    close_reason: str | None = None

    def __str__(self) -> str:
        message = (
            f"{self.failure_category} during {self.transport_stage} "
            f"for {self.transport.upper()} endpoint {self.endpoint}"
        )
        if self.exception_type:
            message = f"{message}: {self.exception_type}"
        if self.exception_message:
            message = f"{message}: {self.exception_message}"
        return message

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "failure_category": self.failure_category,
            "transport_stage": self.transport_stage,
            "endpoint": self.endpoint,
            "transport": self.transport,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "exception_repr": self.exception_repr,
            "exception_chain": self.exception_chain,
        }
        if self.errno is not None:
            payload["errno"] = self.errno
        if self.close_code is not None:
            payload["close_code"] = self.close_code
        if self.close_reason:
            payload["close_reason"] = self.close_reason
        return payload


@dataclass(frozen=True, slots=True)
class PreflightConfig:
    execution_permit_path: Path
    artifacts_root: Path
    soak_root: Path
    audit_root: Path
    duration_seconds: int
    simulation_profile: str
    binance_websocket_url: str
    alchemy_endpoint_url: str
    alchemy_include_block_details: bool
    clock_reference_url: str
    min_free_disk_mb: int
    max_total_log_bytes: int
    clock_skew_threshold_seconds: float
    provider_probe_timeout_seconds: float
    min_permit_margin_seconds: float
    require_explicit_real_permit: bool
    providers: tuple[dict[str, Any], ...]


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def ensure_text(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_jsonl(path: Path, records: list[dict[str, Any]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records or []:
        lines.append(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def path_is_under(path: Path, root: Path) -> bool:
    path_text = os.path.normcase(str(path.resolve()))
    root_text = os.path.normcase(str(root.resolve())).rstrip("\\/")
    return path_text == root_text or path_text.startswith(root_text + os.sep)


def effective_alchemy_endpoint_url(endpoint_url: str | None = None) -> str:
    return alchemy_endpoint_url_for_network("eth-mainnet", endpoint_url)


def run_real_24h_preflight_only(
    *,
    repo_root: Path,
    execution_permit_path: Path,
    artifacts_root: Path,
    label: str,
    duration_seconds: int = REAL_24H_DURATION_SECONDS,
    binance_websocket_url: str = "wss://stream.binance.com:9443/ws",
    alchemy_endpoint_url: str | None = None,
    clock_reference_url: str = "https://api.binance.com/api/v3/time",
    min_free_disk_mb: int = DEFAULT_MIN_FREE_DISK_MB,
    max_total_log_bytes: int = DEFAULT_MAX_TOTAL_LOG_BYTES,
    clock_skew_threshold_seconds: float = DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
    provider_probe_timeout_seconds: float = DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
    min_permit_margin_seconds: float = REAL_24H_MIN_PERMIT_MARGIN_SECONDS,
    trust_root_dir: Path | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    execution_permit_path = Path(execution_permit_path).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    evidence_root = artifacts_root / "preflight_only" / label
    run_root = evidence_root / "run_artifacts"
    audit_root = default_ingestion_audit_root(run_root)
    run_config_path = evidence_root / "run_config.json"
    preflight_path = evidence_root / "preflight_result.json"
    provider_health_path = evidence_root / "provider_health_snapshot.json"
    assertions_path = evidence_root / "preflight_assertions.json"
    alchemy_endpoint = effective_alchemy_endpoint_url(alchemy_endpoint_url)
    providers = tuple(
        build_legacy_provider_payloads(
            binance_websocket_url=binance_websocket_url,
            binance_receive_timeout_seconds=20.0,
            binance_initial_backoff_seconds=1.0,
            binance_max_backoff_seconds=5.0,
            binance_max_reconnect_attempts=None,
            alchemy_poll_interval_seconds=5.0,
            alchemy_request_timeout_seconds=10.0,
            alchemy_initial_backoff_seconds=1.0,
            alchemy_max_backoff_seconds=20.0,
            alchemy_max_retry_attempts=5,
            alchemy_degraded_after_failures=3,
            disable_eth_get_block_by_number=False,
            alchemy_endpoint_url=alchemy_endpoint,
        )
    )

    run_config = {
        "acceptance_profile": "real_24h_preflight_only",
        "simulation_profile": "real",
        "duration_seconds": duration_seconds,
        "execution_permit": str(execution_permit_path),
        "explicit_execution_permit_supplied": True,
        "binance_websocket_url": binance_websocket_url,
        "alchemy_endpoint_url": alchemy_endpoint,
        "clock_reference_url": clock_reference_url,
        "min_free_disk_mb": min_free_disk_mb,
        "max_total_log_bytes": max_total_log_bytes,
        "clock_skew_threshold_seconds": clock_skew_threshold_seconds,
        "provider_probe_timeout_seconds": provider_probe_timeout_seconds,
        "min_permit_margin_seconds": min_permit_margin_seconds,
        "providers": list(providers),
    }
    write_json(
        run_config_path,
        with_evidence_metadata(
            run_config,
            evidence_family="real_24h_preflight",
            contract_version="real_24h_preflight.v1",
        ),
    )

    trust_root_env = None if trust_root_dir is None else str(Path(trust_root_dir).resolve())
    previous_trust_root_dir = os.environ.get(TRUST_ROOT_DIR_ENV)
    if trust_root_env is None:
        os.environ.pop(TRUST_ROOT_DIR_ENV, None)
    else:
        os.environ[TRUST_ROOT_DIR_ENV] = trust_root_env

    try:
        preflight = run_preflight(
            PreflightConfig(
                execution_permit_path=execution_permit_path,
                artifacts_root=run_root,
                soak_root=evidence_root,
                audit_root=audit_root,
                duration_seconds=duration_seconds,
                simulation_profile="real",
                binance_websocket_url=binance_websocket_url,
                alchemy_endpoint_url=alchemy_endpoint,
                alchemy_include_block_details=True,
                clock_reference_url=clock_reference_url,
                min_free_disk_mb=min_free_disk_mb,
                max_total_log_bytes=max_total_log_bytes,
                clock_skew_threshold_seconds=clock_skew_threshold_seconds,
                provider_probe_timeout_seconds=provider_probe_timeout_seconds,
                min_permit_margin_seconds=min_permit_margin_seconds,
                require_explicit_real_permit=True,
                providers=providers,
            )
        )
        write_json(
            preflight_path,
            with_evidence_metadata(
                preflight,
                evidence_family="real_24h_preflight",
                contract_version="real_24h_preflight.v1",
            ),
        )

        provider_health = build_provider_health_snapshot(
            artifacts_root=run_root,
            shadow_summary={"subjects": {}, "stability": {}},
            run_root=None,
            preflight=preflight,
        )
        write_json(
            provider_health_path,
            with_evidence_metadata(
                provider_health,
                evidence_family="real_24h_preflight",
                contract_version="real_24h_preflight.v1",
            ),
        )

        trust_root_candidate = (Path(os.getenv(TRUST_ROOT_DIR_ENV) or default_trust_root_dir()).resolve() / "allowed_signers").resolve()
        trust_root_path_exists = trust_root_candidate.exists()
        trust_root_path_outside_repo = not path_is_under(trust_root_candidate, repo_root)
        trust_root_path_not_temp = not path_is_under(trust_root_candidate, temp_root)
        trust_root_code_validation_ok = False
        trust_root_error = None
        try:
            resolved_allowed_signers = resolve_allowed_signers_path().resolve()
            trust_root_code_validation_ok = (
                os.path.normcase(str(resolved_allowed_signers)) == os.path.normcase(str(trust_root_candidate))
            )
        except Exception as exc:  # noqa: BLE001
            trust_root_error = str(exc)
    finally:
        if previous_trust_root_dir is None:
            os.environ.pop(TRUST_ROOT_DIR_ENV, None)
        else:
            os.environ[TRUST_ROOT_DIR_ENV] = previous_trust_root_dir

    permit_minimum_required_seconds = preflight.get("checks", {}).get("permit", {}).get("minimum_required_seconds")
    assertions = {
        "execution_permit_path_exists": execution_permit_path.exists(),
        "explicit_execution_permit_supplied": True,
        "execution_permit_path_outside_repo": not path_is_under(execution_permit_path, repo_root),
        "execution_permit_path_not_temp": not path_is_under(execution_permit_path, temp_root),
        "permit_minimum_margin_seconds_ok": permit_minimum_required_seconds == min_permit_margin_seconds,
        "trust_root_ok": (
            trust_root_path_exists
            and trust_root_path_outside_repo
            and trust_root_path_not_temp
            and trust_root_code_validation_ok
        ),
        "binance_preflight_passed": preflight.get("checks", {}).get("provider_binance", {}).get("status") == "passed",
        "alchemy_preflight_passed": preflight.get("checks", {}).get("provider_alchemy", {}).get("status") == "passed",
        "run_config_min_permit_margin_seconds_ok": run_config["min_permit_margin_seconds"] == min_permit_margin_seconds,
        "preflight_minimum_required_seconds_ok": permit_minimum_required_seconds == min_permit_margin_seconds,
        "key_evidence_files_exist": False,
        "preflight_status_passed": preflight.get("status") == "passed",
    }
    payload = {
        "all_green": False,
        "assertions": assertions,
        "details": {
            "execution_permit_path": str(execution_permit_path),
            "trust_root_candidate_path": str(trust_root_candidate),
            "trust_root_path_exists": trust_root_path_exists,
            "trust_root_path_outside_repo": trust_root_path_outside_repo,
            "trust_root_path_not_temp": trust_root_path_not_temp,
            "trust_root_code_validation_ok": trust_root_code_validation_ok,
            "trust_root_error": trust_root_error,
            "min_permit_margin_seconds": min_permit_margin_seconds,
            "permit_minimum_required_seconds": permit_minimum_required_seconds,
            "run_config_path": str(run_config_path),
            "preflight_result_path": str(preflight_path),
            "provider_health_snapshot_path": str(provider_health_path),
        },
    }
    write_json(
        assertions_path,
        with_evidence_metadata(
            payload,
            evidence_family="real_24h_preflight",
            contract_version="real_24h_preflight.v1",
        ),
    )

    required_files = [
        run_config_path,
        preflight_path,
        provider_health_path,
        assertions_path,
    ]
    payload["assertions"]["key_evidence_files_exist"] = all(path.exists() for path in required_files)
    payload["all_green"] = (
        payload["assertions"]["preflight_status_passed"] is True
        and all(payload["assertions"].values())
    )
    write_json(
        assertions_path,
        with_evidence_metadata(
            payload,
            evidence_family="real_24h_preflight",
            contract_version="real_24h_preflight.v1",
        ),
    )

    return {
        "status": "passed" if payload["all_green"] else "failed",
        "evidence_root": str(evidence_root.resolve()),
        "preflight_status": preflight.get("status"),
        "run_config_path": str(run_config_path.resolve()),
        "preflight_result_path": str(preflight_path.resolve()),
        "provider_health_snapshot_path": str(provider_health_path.resolve()),
        "preflight_assertions_path": str(assertions_path.resolve()),
        "all_green": payload["all_green"],
        "assertions": payload["assertions"],
        "details": payload["details"],
    }


def evaluate_real_24h_rerun_verdict(
    *,
    artifacts_root: Path,
    rerun_label: str,
    preflight_label: str | None = None,
) -> dict[str, Any]:
    artifacts_root = Path(artifacts_root).resolve()
    if preflight_label is not None and rerun_label == preflight_label:
        raise ValueError("rerun label must differ from preflight label")

    evidence_dir = (artifacts_root / "soak_runs" / rerun_label).resolve()
    preflight_only_root = (artifacts_root / "preflight_only").resolve()
    if path_is_under(evidence_dir, preflight_only_root):
        raise ValueError(f"invalid evidence dir: {evidence_dir}")

    allowed_paths = {
        "go_no_go": evidence_dir / "go_no_go.json",
        "soak_summary": evidence_dir / "soak_summary.json",
        "provider_health_snapshot": evidence_dir / "provider_health_snapshot.json",
        "audit_record": evidence_dir / "audit_record.json",
    }
    missing_paths = [str(path) for path in allowed_paths.values() if not path.exists()]
    if missing_paths:
        raise FileNotFoundError(f"missing rerun verdict evidence: {missing_paths}")

    go_no_go = load_json(allowed_paths["go_no_go"])
    soak_summary = load_json(allowed_paths["soak_summary"])
    provider_health_snapshot = load_json(allowed_paths["provider_health_snapshot"])
    audit_record = load_json(allowed_paths["audit_record"])

    expected_slice_ids = build_controlled_agent_slices_summary().get("enabled_slice_ids", [])
    agent_layer_governance = dict(go_no_go.get("agent_layer_governance", {}))
    conditions = {
        "ready_for_real_24h_shadow": go_no_go.get("READY_FOR_REAL_24H_SHADOW") is True,
        "ready_for_broad_agent_layer": go_no_go.get("READY_FOR_BROAD_AGENT_LAYER") is True,
        "agent_layer_governance_blockers_empty": list(agent_layer_governance.get("blockers", [])) == [],
        "broad_blockers_empty": list(go_no_go.get("broad_blockers", [])) == [],
        "current_controlled_slice_ids_match": list(agent_layer_governance.get("current_controlled_slice_ids", [])) == expected_slice_ids,
        "registered_pending_promotion_controlled_slice_ids_empty": list(
            agent_layer_governance.get("registered_pending_promotion_controlled_slice_ids", [])
        ) == [],
        "hard_failures_empty": list(go_no_go.get("hard_failures", [])) == [],
        "soft_failures_empty": list(go_no_go.get("soft_failures", [])) == [],
        "audit_status_completed": audit_record.get("status") == "completed",
        "soak_violations_empty": list(soak_summary.get("violations", [])) == [],
    }
    failures: list[str] = []
    if not conditions["ready_for_real_24h_shadow"]:
        failures.append("READY_FOR_REAL_24H_SHADOW is not true")
    if not conditions["ready_for_broad_agent_layer"]:
        failures.append("READY_FOR_BROAD_AGENT_LAYER is not true")
    if not conditions["agent_layer_governance_blockers_empty"]:
        failures.append("agent_layer_governance.blockers is not empty")
    if not conditions["broad_blockers_empty"]:
        failures.append("broad_blockers is not empty")
    if not conditions["current_controlled_slice_ids_match"]:
        failures.append("current_controlled_slice_ids does not match the shipped 8-slice list")
    if not conditions["registered_pending_promotion_controlled_slice_ids_empty"]:
        failures.append("registered_pending_promotion_controlled_slice_ids is not empty")
    if not conditions["hard_failures_empty"]:
        failures.append("hard_failures is not empty")
    if not conditions["soft_failures_empty"]:
        failures.append("soft_failures is not empty")
    if not conditions["audit_status_completed"]:
        failures.append("audit_record.status is not completed")
    if not conditions["soak_violations_empty"]:
        failures.append("soak_summary.violations is not empty")

    return {
        "status": "passed" if not failures else "failed",
        "evidence_dir": str(evidence_dir),
        "allowed_evidence_paths": {key: str(path.resolve()) for key, path in allowed_paths.items()},
        "conditions": conditions,
        "failures": failures,
        "READY_FOR_REAL_24H_SHADOW": go_no_go.get("READY_FOR_REAL_24H_SHADOW"),
        "READY_FOR_AGENT_LAYER": go_no_go.get("READY_FOR_AGENT_LAYER"),
        "READY_FOR_BROAD_AGENT_LAYER": go_no_go.get("READY_FOR_BROAD_AGENT_LAYER"),
        "agent_layer_governance_status": agent_layer_governance.get("status"),
        "agent_layer_governance_blockers": list(agent_layer_governance.get("blockers", [])),
        "broad_blockers": list(go_no_go.get("broad_blockers", [])),
        "hard_failures": list(go_no_go.get("hard_failures", [])),
        "soft_failures": list(go_no_go.get("soft_failures", [])),
        "audit_status": audit_record.get("status"),
        "soak_violations": list(soak_summary.get("violations", [])),
        "current_controlled_slice_ids": list(agent_layer_governance.get("current_controlled_slice_ids", [])),
        "expected_current_controlled_slice_ids": expected_slice_ids,
        "registered_pending_promotion_controlled_slice_ids": list(
            agent_layer_governance.get("registered_pending_promotion_controlled_slice_ids", [])
        ),
        "provider_health_snapshot_present": bool(provider_health_snapshot),
    }


def copy_or_placeholder(source: Path | None, target: Path, *, default_text: str = "") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source is not None and source.exists():
        shutil.copyfile(source, target)
        return
    target.write_text(default_text, encoding="utf-8")


def artifacts_root_isolated(path: Path, *, allowed_entries: set[str] | None = None) -> tuple[bool, list[str]]:
    if not path.exists():
        return True, []
    allowed = allowed_entries or set()
    unexpected = [item.name for item in path.iterdir() if item.name not in allowed]
    if not unexpected:
        return True, []
    return False, unexpected


def build_rejection_root(base_root: Path, *, label: str) -> Path:
    return (base_root / "rejected_runs" / f"{label}-{utc_now().strftime('%Y%m%dT%H%M%SZ')}").resolve()


def run_preflight(config: PreflightConfig) -> dict[str, Any]:
    started_at = utc_now()
    checks: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    explicit_real_permit_missing = (
        config.require_explicit_real_permit
        and config.simulation_profile == "real"
        and not config.execution_permit_path.exists()
    )

    if explicit_real_permit_missing:
        failures.append("real-provider 24h acceptance requires an explicit execution permit path")
        checks["permit"] = {
            "status": "failed",
            "message": "explicit execution permit path is required for real-provider acceptance",
        }
    else:
        try:
            permit = load_execution_permit(config.execution_permit_path)
            _validate_preflight_permit(permit, config=config, started_at=started_at)
            checks["permit"] = _permit_check_payload(permit, config=config, started_at=started_at)
            if checks["permit"]["status"] != "passed":
                failures.append(str(checks["permit"]["message"]))
        except Exception as exc:  # noqa: BLE001 - exact preflight failure matters
            failures.append(f"execution permit validation failed: {exc}")
            checks["permit"] = {
                "status": "failed",
                "message": str(exc),
            }

    try:
        allowed_signers = resolve_allowed_signers_path()
        allowed_signers.read_text(encoding="utf-8")
        checks["trust_root"] = {
            "status": "passed",
            "message": "trust root is readable",
            "allowed_signers_path": str(allowed_signers),
        }
    except Exception as exc:  # noqa: BLE001
        failures.append(f"trust root preflight failed: {exc}")
        checks["trust_root"] = {
            "status": "failed",
            "message": str(exc),
        }

    try:
        disk = shutil.disk_usage(config.soak_root if config.soak_root.exists() else config.soak_root.parent)
        free_mb = disk.free / (1024 * 1024)
        status = "passed" if free_mb >= config.min_free_disk_mb else "failed"
        if status != "passed":
            failures.append(
                f"free disk {free_mb:.1f} MiB is below threshold {config.min_free_disk_mb} MiB"
            )
        checks["disk_space"] = {
            "status": status,
            "free_bytes": disk.free,
            "free_mb": round(free_mb, 2),
            "required_free_mb": config.min_free_disk_mb,
        }
    except Exception as exc:  # noqa: BLE001
        failures.append(f"disk usage preflight failed: {exc}")
        checks["disk_space"] = {
            "status": "failed",
            "message": str(exc),
        }

    try:
        targets = [config.soak_root, config.audit_root]
        probes: list[str] = []
        for target in targets:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / ".preflight-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            probes.append(str(target))
        checks["log_dir_writable"] = {
            "status": "passed",
            "targets": probes,
        }
    except Exception as exc:  # noqa: BLE001
        failures.append(f"log/artifact directory writability preflight failed: {exc}")
        checks["log_dir_writable"] = {
            "status": "failed",
            "message": str(exc),
        }

    artifacts_isolated, artifacts_entries = artifacts_root_isolated(
        config.artifacts_root,
        allowed_entries={"operational_audit"},
    )
    soak_isolated, soak_entries = artifacts_root_isolated(
        config.soak_root,
        allowed_entries={"run_config.json", "run_artifacts"},
    )
    if artifacts_isolated and soak_isolated:
        checks["artifacts_isolation"] = {
            "status": "passed",
            "artifacts_root": str(config.artifacts_root),
            "soak_root": str(config.soak_root),
        }
    else:
        failures.append("artifacts root isolation check failed")
        checks["artifacts_isolation"] = {
            "status": "failed",
            "artifacts_root": str(config.artifacts_root),
            "soak_root": str(config.soak_root),
            "artifacts_root_entries": artifacts_entries,
            "soak_root_entries": soak_entries,
        }

    clock_check = probe_clock_reference(
        config.clock_reference_url,
        timeout_seconds=config.provider_probe_timeout_seconds,
        skew_threshold_seconds=config.clock_skew_threshold_seconds,
    )
    if clock_check.get("status") != "passed" and config.simulation_profile != "real":
        clock_check = {
            **clock_check,
            "status": "warning",
            "message": f"{clock_check.get('message', 'clock sync preflight failed')} (non-blocking for synthetic profile)",
        }
    checks["clock_sync"] = clock_check
    if clock_check.get("status") == "failed":
        failures.append(str(clock_check.get("message", "clock sync preflight failed")))

    provider_groups = group_providers_by_family(list(config.providers))

    binance_details: dict[str, dict[str, Any]] = {}
    for provider in provider_groups["binance"]:
        provider_check = probe_binance_preflight(
            websocket_url=str(provider["websocket_url"]),
            timeout_seconds=config.provider_probe_timeout_seconds,
            api_key_env_var="BINANCE_API_KEY",
        )
        provider_check = _apply_non_real_provider_probe_policy(
            provider_check,
            simulation_profile=config.simulation_profile,
            default_message="Binance provider preflight failed",
        )
        identity = provider_identity(provider)
        binance_details[identity] = {
            **provider_check,
            "provider_kind": provider["kind"],
            "provider_id": provider["provider_id"],
            "subject_key": provider["subject_key"],
            "symbol": provider["symbol"],
        }
        if provider_check.get("status") == "failed":
            failures.append(str(provider_check.get("message", f"Binance provider preflight failed for {identity}")))
    checks["provider_binance"] = _aggregate_provider_family_checks(
        list(binance_details.values()),
        family_name="Binance",
    )
    checks["provider_binance_details"] = binance_details

    alchemy_details: dict[str, dict[str, Any]] = {}
    for provider in provider_groups["alchemy"]:
        if provider["kind"] == ALCHEMY_EVM_BLOCK_PROVIDER_KIND:
            provider_check = probe_alchemy_preflight(
                endpoint_url=alchemy_endpoint_url_for_network(
                    provider["network"],
                    provider.get("endpoint_url"),
                ),
                timeout_seconds=config.provider_probe_timeout_seconds,
                include_block_details=bool(provider["include_block_details"]),
                api_key_env_var="ALCHEMY_API_KEY",
            )
        elif provider["kind"] == ALCHEMY_BITCOIN_BLOCK_PROVIDER_KIND:
            provider_check = probe_alchemy_bitcoin_preflight(
                endpoint_url=alchemy_endpoint_url_for_network(
                    provider["network"],
                    provider.get("endpoint_url"),
                ),
                timeout_seconds=config.provider_probe_timeout_seconds,
                include_block_details=bool(provider["include_block_details"]),
                api_key_env_var="ALCHEMY_API_KEY",
            )
        elif provider["kind"] == ALCHEMY_SOLANA_BLOCK_PROVIDER_KIND:
            provider_check = probe_alchemy_solana_preflight(
                endpoint_url=alchemy_endpoint_url_for_network(
                    provider["network"],
                    provider.get("endpoint_url"),
                ),
                timeout_seconds=config.provider_probe_timeout_seconds,
                include_block_details=bool(provider["include_block_details"]),
                api_key_env_var="ALCHEMY_API_KEY",
                commitment=str(provider["commitment"]),
                encoding=str(provider["encoding"]),
                transaction_details=str(provider["transaction_details"]),
            )
        else:
            raise ValueError(f"unsupported provider kind '{provider['kind']}'")
        provider_check = _apply_non_real_provider_probe_policy(
            provider_check,
            simulation_profile=config.simulation_profile,
            default_message="Alchemy provider preflight failed",
        )
        identity = provider_identity(provider)
        alchemy_details[identity] = {
            **provider_check,
            "provider_kind": provider["kind"],
            "provider_id": provider["provider_id"],
            "subject_key": provider["subject_key"],
            "symbol": provider["symbol"],
            "network": provider["network"],
        }
        if provider_check.get("status") == "failed":
            failures.append(str(provider_check.get("message", f"Alchemy provider preflight failed for {identity}")))
    checks["provider_alchemy"] = _aggregate_provider_family_checks(
        list(alchemy_details.values()),
        family_name="Alchemy",
    )
    checks["provider_alchemy_details"] = alchemy_details

    return {
        "started_at_utc": format_utc(started_at),
        "ended_at_utc": format_utc(utc_now()),
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "checks": checks,
    }


def probe_clock_reference(
    url: str,
    *,
    timeout_seconds: float,
    skew_threshold_seconds: float,
) -> dict[str, Any]:
    try:
        request = urllib_request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            headers = dict(response.headers.items())
        reference_time = None
        source = None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and "serverTime" in payload:
            reference_time = datetime.fromtimestamp(float(payload["serverTime"]) / 1000.0, tz=UTC)
            source = "json.serverTime"
        elif "Date" in headers:
            reference_time = email.utils.parsedate_to_datetime(headers["Date"]).astimezone(UTC)
            source = "http.date"
        if reference_time is None:
            return {
                "status": "failed",
                "message": f"clock reference {url} did not expose a usable timestamp",
            }
        local_time = utc_now()
        skew_seconds = abs((local_time - reference_time).total_seconds())
        status = "passed" if skew_seconds <= skew_threshold_seconds else "failed"
        return {
            "status": status,
            "url": url,
            "source": source,
            "local_time_utc": format_utc(local_time),
            "reference_time_utc": format_utc(reference_time),
            "clock_skew_seconds": round(skew_seconds, 3),
            "threshold_seconds": skew_threshold_seconds,
            "message": (
                "clock skew is within threshold"
                if status == "passed"
                else f"clock skew {skew_seconds:.3f}s exceeds threshold {skew_threshold_seconds:.3f}s"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "message": f"clock reference probe failed for {url}: {exc}",
        }


def probe_binance_preflight(
    *,
    websocket_url: str,
    timeout_seconds: float,
    api_key_env_var: str,
) -> dict[str, Any]:
    secret_check = inspect_provider_secret(os.getenv(api_key_env_var), endpoint_url=websocket_url)
    if secret_check["status"] != "passed":
        return {
            "status": "failed",
            "minimum_permission_model": "public_stream_only",
            "credential_check": secret_check,
            "message": f"{api_key_env_var} check failed: {secret_check['message']}",
        }
    try:
        probe = asyncio.run(_probe_binance_websocket(websocket_url, timeout_seconds=timeout_seconds))
    except BinanceProbeError as exc:
        failure = exc.to_payload()
        return {
            "status": "failed",
            "minimum_permission_model": "public_stream_only",
            "credential_check": secret_check,
            "message": f"Binance websocket probe failed: {exc}",
            **failure,
        }
    except Exception as exc:  # noqa: BLE001
        failure = _build_binance_probe_error(exc, websocket_url=websocket_url, transport_stage="connect").to_payload()
        return {
            "status": "failed",
            "minimum_permission_model": "public_stream_only",
            "credential_check": secret_check,
            "message": (
                "Binance websocket probe failed: "
                f"{failure['failure_category']} during {failure['transport_stage']} "
                f"for {failure['transport'].upper()} endpoint {failure['endpoint']}: "
                f"{failure['exception_type']}: {failure['exception_message']}"
            ),
            **failure,
        }
    return {
        "status": "passed",
        "minimum_permission_model": "public_stream_only",
        "credential_check": secret_check,
        "message": "Binance websocket probe succeeded",
        **probe,
    }


async def _probe_binance_websocket(websocket_url: str, *, timeout_seconds: float) -> dict[str, Any]:
    metadata = _binance_endpoint_metadata(websocket_url)
    transport_stage = "connect"
    try:
        async with websockets.connect(
            websocket_url,
            ping_interval=None,
            ping_timeout=None,
            open_timeout=timeout_seconds,
            close_timeout=min(timeout_seconds, 5.0),
        ) as websocket:
            transport_stage = "subscribe_send"
            await websocket.send(
                json.dumps(
                    {
                        "method": "SUBSCRIBE",
                        "params": ["btcusdt@trade"],
                        "id": 1,
                    },
                    separators=(",", ":"),
                )
            )
            acknowledged = False
            deadline = asyncio.get_running_loop().time() + timeout_seconds
            while True:
                transport_stage = "data_wait" if acknowledged else "subscription_ack_wait"
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError(
                        f"timed out waiting for Binance websocket probe data from {websocket_url}"
                    )
                raw_message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                transport_stage = "payload_parse"
                payload = json.loads(raw_message)
                if isinstance(payload, dict) and payload.get("result") is None and "id" in payload:
                    acknowledged = True
                    continue
                if (
                    isinstance(payload, dict)
                    and payload.get("stream") == "btcusdt@trade"
                    and isinstance(payload.get("data"), dict)
                ):
                    return {
                        **metadata,
                        "subscription_acknowledged": acknowledged,
                        "sample_stream": payload.get("stream"),
                        "sample_symbol": payload["data"].get("s"),
                    }
                if (
                    isinstance(payload, dict)
                    and payload.get("e") == "trade"
                    and str(payload.get("s", "")).upper() == "BTCUSDT"
                ):
                    return {
                        **metadata,
                        "subscription_acknowledged": acknowledged,
                        "sample_stream": "btcusdt@trade",
                        "sample_symbol": payload.get("s"),
                    }
    except BinanceProbeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _build_binance_probe_error(
            exc,
            websocket_url=websocket_url,
            transport_stage=transport_stage,
        ) from exc


def probe_alchemy_preflight(
    *,
    endpoint_url: str,
    timeout_seconds: float,
    include_block_details: bool,
    api_key_env_var: str,
) -> dict[str, Any]:
    secret_check = inspect_provider_secret(os.getenv(api_key_env_var), endpoint_url=endpoint_url)
    if secret_check["status"] != "passed":
        return {
            "status": "failed",
            "minimum_permission_model": "read_only_rpc",
            "credential_check": secret_check,
            "message": f"{api_key_env_var} check failed: {secret_check['message']}",
        }
    try:
        block_payload = _alchemy_rpc(
            endpoint_url,
            {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
            timeout_seconds=timeout_seconds,
        )
        block_number = str(block_payload["result"])
        detail_ok = None
        if include_block_details:
            detail_payload = _alchemy_rpc(
                endpoint_url,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "eth_getBlockByNumber",
                    "params": [block_number, False],
                },
                timeout_seconds=timeout_seconds,
            )
            detail_ok = isinstance(detail_payload, dict) and detail_payload.get("result") is not None
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "minimum_permission_model": "read_only_rpc",
            "credential_check": secret_check,
            "message": f"Alchemy RPC probe failed: {exc}",
        }
    return {
        "status": "passed",
        "minimum_permission_model": "read_only_rpc",
        "credential_check": secret_check,
        "message": "Alchemy RPC probe succeeded",
        "endpoint": endpoint_url,
        "block_number": block_number,
        "block_detail_probe": detail_ok,
    }


def probe_alchemy_bitcoin_preflight(
    *,
    endpoint_url: str,
    timeout_seconds: float,
    include_block_details: bool,
    api_key_env_var: str,
) -> dict[str, Any]:
    secret_check = inspect_provider_secret(os.getenv(api_key_env_var), endpoint_url=endpoint_url)
    if secret_check["status"] != "passed":
        return {
            "status": "failed",
            "minimum_permission_model": "read_only_rpc",
            "credential_check": secret_check,
            "message": f"{api_key_env_var} check failed: {secret_check['message']}",
        }
    try:
        height_payload = _alchemy_rpc(
            endpoint_url,
            {"jsonrpc": "2.0", "id": 1, "method": "getblockcount", "params": []},
            timeout_seconds=timeout_seconds,
        )
        height = int(height_payload["result"])
        detail_ok = None
        block_hash = None
        if include_block_details:
            hash_payload = _alchemy_rpc(
                endpoint_url,
                {"jsonrpc": "2.0", "id": 2, "method": "getblockhash", "params": [height]},
                timeout_seconds=timeout_seconds,
            )
            block_hash = str(hash_payload["result"])
            detail_payload = _alchemy_rpc(
                endpoint_url,
                {"jsonrpc": "2.0", "id": 3, "method": "getblock", "params": [block_hash, 1]},
                timeout_seconds=timeout_seconds,
            )
            detail_ok = isinstance(detail_payload, dict) and detail_payload.get("result") is not None
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "minimum_permission_model": "read_only_rpc",
            "credential_check": secret_check,
            "message": f"Alchemy Bitcoin RPC probe failed: {exc}",
        }
    return {
        "status": "passed",
        "minimum_permission_model": "read_only_rpc",
        "credential_check": secret_check,
        "message": "Alchemy Bitcoin RPC probe succeeded",
        "endpoint": endpoint_url,
        "height": height,
        "block_hash": block_hash,
        "block_detail_probe": detail_ok,
    }


def probe_alchemy_solana_preflight(
    *,
    endpoint_url: str,
    timeout_seconds: float,
    include_block_details: bool,
    api_key_env_var: str,
    commitment: str,
    encoding: str,
    transaction_details: str,
) -> dict[str, Any]:
    secret_check = inspect_provider_secret(os.getenv(api_key_env_var), endpoint_url=endpoint_url)
    if secret_check["status"] != "passed":
        return {
            "status": "failed",
            "minimum_permission_model": "read_only_rpc",
            "credential_check": secret_check,
            "message": f"{api_key_env_var} check failed: {secret_check['message']}",
        }
    try:
        slot_payload = _alchemy_rpc(
            endpoint_url,
            {"jsonrpc": "2.0", "id": 1, "method": "getSlot", "params": [{"commitment": commitment}]},
            timeout_seconds=timeout_seconds,
        )
        slot = int(slot_payload["result"])
        detail_ok = None
        detail_slot = None
        if include_block_details:
            for candidate_slot in range(slot, max(-1, slot - 5), -1):
                try:
                    detail_payload = _alchemy_rpc(
                        endpoint_url,
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "getBlock",
                            "params": [
                                candidate_slot,
                                {
                                    "commitment": commitment,
                                    "encoding": encoding,
                                    "transactionDetails": transaction_details,
                                },
                            ],
                        },
                        timeout_seconds=timeout_seconds,
                    )
                except ValueError as exc:
                    if _is_solana_skipped_slot_error(exc):
                        detail_slot = candidate_slot
                        continue
                    raise
                detail_slot = candidate_slot
                if isinstance(detail_payload, dict) and detail_payload.get("result") is not None:
                    detail_ok = True
                    break
            if detail_ok is None:
                detail_ok = False
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "minimum_permission_model": "read_only_rpc",
            "credential_check": secret_check,
            "message": f"Alchemy Solana RPC probe failed: {exc}",
        }
    return {
        "status": "passed",
        "minimum_permission_model": "read_only_rpc",
        "credential_check": secret_check,
        "message": "Alchemy Solana RPC probe succeeded",
        "endpoint": endpoint_url,
        "slot": slot,
        "block_detail_probe": detail_ok,
        "block_detail_probe_slot": detail_slot,
    }


def _is_solana_skipped_slot_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "slot" in message and ("skipped" in message or "ledger jump to recent snapshot" in message)


def _alchemy_rpc(endpoint_url: str, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    request = urllib_request.Request(
        endpoint_url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Alchemy RPC probe returned a non-object payload")
    if "error" in parsed:
        raise ValueError(f"Alchemy RPC probe returned an error: {parsed['error']}")
    return parsed


def _apply_non_real_provider_probe_policy(
    provider_check: dict[str, Any],
    *,
    simulation_profile: str,
    default_message: str,
) -> dict[str, Any]:
    if provider_check.get("status") != "passed" and simulation_profile != "real":
        return {
            **provider_check,
            "status": "warning",
            "message": f"{provider_check.get('message', default_message)} (non-blocking for synthetic profile)",
        }
    return provider_check


def _aggregate_provider_family_checks(
    provider_checks: list[dict[str, Any]],
    *,
    family_name: str,
) -> dict[str, Any]:
    if not provider_checks:
        return {
            "status": "passed",
            "message": f"no {family_name} providers configured",
            "minimum_permission_model": None,
            "provider_count": 0,
        }
    statuses = [str(item.get("status", "failed")) for item in provider_checks]
    if any(status == "failed" for status in statuses):
        status = "failed"
    elif any(status == "warning" for status in statuses):
        status = "warning"
    else:
        status = "passed"
    messages = [str(item.get("message", "")).strip() for item in provider_checks if str(item.get("message", "")).strip()]
    minimum_permission_model = next(
        (
            item.get("minimum_permission_model")
            for item in provider_checks
            if item.get("minimum_permission_model") is not None
        ),
        None,
    )
    return {
        "status": status,
        "message": (
            f"{family_name} provider preflight succeeded"
            if status == "passed"
            else "; ".join(messages) or f"{family_name} provider preflight did not succeed"
        ),
        "minimum_permission_model": minimum_permission_model,
        "provider_count": len(provider_checks),
        "provider_status_counts": _count_values(provider_checks, "status"),
    }


def inspect_provider_secret(secret: str | None, *, endpoint_url: str) -> dict[str, Any]:
    if secret is None or not secret.strip():
        return {
            "status": "failed",
            "message": "credential is missing",
            "credential_present": False,
            "placeholder_detected": False,
            "local_endpoint_override": _is_local_endpoint(endpoint_url),
        }
    normalized = secret.strip().lower()
    local_endpoint_override = _is_local_endpoint(endpoint_url)
    placeholder_detected = any(token in normalized for token in _PLACEHOLDER_SECRET_TOKENS)
    if placeholder_detected and not local_endpoint_override:
        return {
            "status": "failed",
            "message": "credential looks like a placeholder",
            "credential_present": True,
            "placeholder_detected": True,
            "local_endpoint_override": False,
        }
    return {
        "status": "passed",
        "message": "credential exists",
        "credential_present": True,
        "placeholder_detected": placeholder_detected,
        "local_endpoint_override": local_endpoint_override,
    }


def build_provider_health_snapshot(
    *,
    artifacts_root: Path,
    shadow_summary: dict[str, Any],
    run_root: Path | None,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    health_records = _read_jsonl_tree(artifacts_root / "health_events")
    downstream_records = _read_jsonl_tree(artifacts_root / "downstream_blocks")
    subjects = dict(shadow_summary.get("subjects", {}))
    stability = dict(shadow_summary.get("stability", {}))
    provider_checks = {
        "binance": preflight.get("checks", {}).get("provider_binance", {}),
        "binance_details": preflight.get("checks", {}).get("provider_binance_details", {}),
        "alchemy": preflight.get("checks", {}).get("provider_alchemy", {}),
        "alchemy_details": preflight.get("checks", {}).get("provider_alchemy_details", {}),
    }
    return {
        "generated_at_utc": format_utc(utc_now()),
        "preflight_provider_checks": provider_checks,
        "provider_anomaly_stats": {
            "binance_reconnect_count": int(stability.get("binance_reconnect_count", 0)),
            "alchemy_retry_count": int(stability.get("alchemy_retry_count", 0)),
            "provider_degraded_count": int(stability.get("provider_degraded_count", 0)),
            "provider_recovered_count": int(stability.get("provider_recovered_count", 0)),
            "health_event_count": len(health_records),
            "downstream_block_count": len(downstream_records),
        },
        "credential_minimum_permission_models": {
            "binance": provider_checks["binance"].get("minimum_permission_model"),
            "alchemy": provider_checks["alchemy"].get("minimum_permission_model"),
        },
        "stability": stability,
        "subjects": {
            subject_key: {
                "event_count": subject_summary.get("event_count", 0),
                "latest_ingest_timestamp_utc": subject_summary.get("latest_ingest_timestamp_utc"),
                "missing_hours": subject_summary.get("missing_hours", []),
                "parse_error_count": subject_summary.get("parse_error_count", 0),
                "contamination_count": subject_summary.get("contamination_count", 0),
                "event_type_counts": subject_summary.get("event_type_counts", {}),
            }
            for subject_key, subject_summary in subjects.items()
        },
        "health_event_count": len(health_records),
        "health_events_by_status": _count_values(health_records, "to_status"),
        "downstream_block_count": len(downstream_records),
        "downstream_block_reasons": _count_values(downstream_records, "reason"),
        "run_root": None if run_root is None else str(run_root),
    }


def build_interruption_failure_evidence(
    *,
    preflight: dict[str, Any],
    audit_record: dict[str, Any],
    events_path: Path | None,
    exit_status: dict[str, Any],
) -> dict[str, Any]:
    events = [] if events_path is None else _read_jsonl_file(events_path)
    event_counts = _count_values(events, "event")
    interesting_events = [
        record
        for record in events
        if str(record.get("event", "")).startswith("lease.")
        or str(record.get("event", "")).startswith("worker.")
        or str(record.get("event", "")) in {"controller.worker_exit", "controller.worker_spawn_failed", "lease.cleanup"}
    ]
    active_leases = list_execution_leases(status="active")
    lease_id = audit_record.get("lease_id")
    related_active_leases = [
        lease
        for lease in active_leases
        if lease_id is not None and str(lease.get("lease_id")) == str(lease_id)
    ]
    return {
        "generated_at_utc": format_utc(utc_now()),
        "preflight_failures": list(preflight.get("failures", [])),
        "worker_status": audit_record.get("status"),
        "failure_category": audit_record.get("failure_category"),
        "interruption_reason": audit_record.get("interruption_reason"),
        "exit_code": exit_status.get("exit_code"),
        "lease_id": lease_id,
        "lease_event_counts": {
            "lease_acquired": int(event_counts.get("lease.acquired", 0)),
            "lease_heartbeat": int(event_counts.get("lease.heartbeat", 0)),
            "lease_heartbeat_failed": int(event_counts.get("lease.heartbeat_failed", 0)),
            "lease_released": int(event_counts.get("lease.released", 0)),
            "lease_cleanup": int(event_counts.get("lease.cleanup", 0)),
        },
        "interesting_event_count": len(interesting_events),
        "interesting_events": interesting_events,
        "active_leases_after_run": related_active_leases,
    }


def build_lease_lifecycle_summary(
    *,
    audit_record: dict[str, Any],
    events_path: Path | None,
    interruption_evidence: dict[str, Any],
) -> dict[str, Any]:
    events = [] if events_path is None else _read_jsonl_file(events_path)
    event_counts = _count_values(events, "event")
    release_status_counts = _count_values(
        [record for record in events if str(record.get("event")) == "lease.released"],
        "release_status",
    )
    cleanup_reason_counts = _count_values(
        [record for record in events if str(record.get("event")) == "lease.cleanup"],
        "cleanup_reason",
    )
    return {
        "worker_status": audit_record.get("status"),
        "failure_category": audit_record.get("failure_category"),
        "interruption_reason": audit_record.get("interruption_reason"),
        "lease_id": audit_record.get("lease_id"),
        "lease_acquired_count": int(event_counts.get("lease.acquired", 0)),
        "lease_heartbeat_count": int(event_counts.get("lease.heartbeat", 0)),
        "lease_heartbeat_failed_count": int(event_counts.get("lease.heartbeat_failed", 0)),
        "lease_released_count": int(event_counts.get("lease.released", 0)),
        "lease_cleanup_count": int(event_counts.get("lease.cleanup", 0)),
        "task_lock_reclaimed_count": int(event_counts.get("task_lock.reclaimed", 0)),
        "worker_interrupted_count": int(event_counts.get("worker.interrupted", 0)),
        "worker_failed_count": int(event_counts.get("worker.failed", 0)),
        "controller_worker_exit_count": int(event_counts.get("controller.worker_exit", 0)),
        "release_status_counts": release_status_counts,
        "cleanup_reason_counts": cleanup_reason_counts,
        "active_leases_after_run": len(interruption_evidence.get("active_leases_after_run", [])),
    }


def build_go_no_go(
    *,
    summary: dict[str, Any],
    require_real_24h: bool,
    agent_layer_governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hard_failures: list[str] = []
    soft_failures: list[str] = []
    controlled_agent_slices = dict(summary.get("controlled_agent_slices") or build_controlled_agent_slices_summary())
    governance = dict(agent_layer_governance or summary.get("agent_layer_governance") or {})
    if not governance:
        governance = missing_agent_layer_governance_result()
    agent_layer_blockers = [
        str(item.get("message", "")).strip()
        for item in governance.get("blockers", [])
        if isinstance(item, dict) and str(item.get("message", "")).strip()
    ]
    broad_blockers = [
        str(item.get("message", "")).strip()
        for item in governance.get("broad_blockers", [])
        if isinstance(item, dict) and str(item.get("message", "")).strip()
    ]
    agent_layer_governance_enabled = bool(governance.get("agent_layer_governance_enabled"))
    broad_agent_layer_ready = bool(governance.get("broad_agent_layer_ready"))
    broad_agent_layer_enabled = bool(governance.get("broad_agent_layer_enabled"))

    preflight = dict(summary.get("preflight", {}))
    shadow = dict(summary.get("shadow", {}))
    audit = dict(summary.get("audit", {}))
    run = dict(shadow.get("run", {}))
    quality = dict(shadow.get("quality", {}))
    security = dict(shadow.get("security", {}))
    provider_health = dict(summary.get("provider_health_snapshot", {}))
    interruption = dict(summary.get("interruption_failure_evidence", {}))
    lease_lifecycle = dict(summary.get("lease_lifecycle", {}))
    evidence_artifacts = dict(summary.get("evidence_artifacts", {}))
    run_config = dict(summary.get("run_config", {}))

    if run_config.get("evidence_bundle_version") != REAL_SHADOW_EVIDENCE_BUNDLE_VERSION:
        hard_failures.append(
            "evidence bundle version is missing or unexpected; real-provider acceptance evidence is incomplete"
        )

    for key, path_value in evidence_artifacts.items():
        if not path_value:
            hard_failures.append(f"evidence artifact path is missing for {key}")
            continue
        if not Path(str(path_value)).exists():
            hard_failures.append(f"evidence artifact is missing: {key} -> {path_value}")

    if preflight.get("status") != "passed":
        soft_failures.extend(str(item) for item in preflight.get("failures", []))
    if run.get("run_completed") is not True:
        hard_failures.append("shadow run did not complete")
    if run.get("exit_code") != 0:
        hard_failures.append(f"shadow controller exited with code {run.get('exit_code')}")
    audit_record = dict(audit.get("audit_record", {}))
    if audit_record.get("status") != "completed":
        hard_failures.append(f"worker audit status is {audit_record.get('status')}")
    event_counts = dict(audit.get("event_counts", {}))
    if event_counts.get("lease.acquired", 0) < 1:
        hard_failures.append("worker audit is missing lease.acquired evidence")
    if event_counts.get("lease.heartbeat", 0) < 1:
        hard_failures.append("worker audit is missing lease.heartbeat evidence")
    if event_counts.get("lease.released", 0) < 1:
        hard_failures.append("worker audit is missing lease.released evidence")
    if quality.get("cross_subject_contamination_count") != 0:
        hard_failures.append("cross-subject contamination was detected")
    if quality.get("replay_parse_error_count") != 0:
        hard_failures.append("replay parse errors were detected")
    if quality.get("replay_write_failure_count") != 0:
        hard_failures.append("replay write failures were detected")
    if security.get("key_leakage_detected") is True:
        hard_failures.append("secret leakage was detected in logs")
    if security.get("unredacted_alchemy_endpoint_detected") is True:
        hard_failures.append("an unredacted Alchemy endpoint was detected in logs")
    if interruption.get("active_leases_after_run"):
        hard_failures.append("active lease remained after run termination")
    if int(lease_lifecycle.get("lease_acquired_count", 0)) < 1:
        hard_failures.append("lease lifecycle evidence is missing lease acquisition")
    if int(lease_lifecycle.get("lease_released_count", 0)) < 1 and not interruption.get("active_leases_after_run"):
        hard_failures.append("lease lifecycle evidence is missing lease release")

    total_log_bytes = 0
    for key in (
        "controller_stdout_log",
        "controller_stderr_log",
        "worker_stdout_log",
        "worker_stderr_log",
    ):
        path_value = evidence_artifacts.get(key)
        if path_value and Path(path_value).exists():
            total_log_bytes += Path(path_value).stat().st_size
    configured_log_limit = int(run_config.get("max_total_log_bytes", DEFAULT_MAX_TOTAL_LOG_BYTES))
    if total_log_bytes > configured_log_limit:
        soft_failures.append(
            f"combined controller/worker logs reached {total_log_bytes} bytes, above threshold {configured_log_limit}"
        )

    for subject_key, subject_summary in dict(shadow.get("subjects", {})).items():
        if int(subject_summary.get("event_count", 0)) <= 0:
            hard_failures.append(f"subject {subject_key} has no replay events")

    if require_real_24h:
        if run_config.get("simulation_profile") != "real":
            soft_failures.append("simulation profile is not real")
        configured_duration = int(run_config.get("duration_seconds", 0))
        if configured_duration < REAL_24H_DURATION_SECONDS:
            soft_failures.append(
                f"configured soak duration {configured_duration}s is below the required 24h window"
            )
        actual_seconds = _runtime_seconds(run.get("started_at_utc"), run.get("ended_at_utc"))
        if actual_seconds is None or actual_seconds < MIN_REAL_24H_DURATION_SECONDS:
            soft_failures.append(
                "completed runtime window is shorter than the minimum 23.5h evidence threshold"
            )

    if provider_health.get("preflight_provider_checks", {}).get("binance", {}).get("status") != "passed":
        soft_failures.append("Binance provider preflight did not succeed")
    if provider_health.get("preflight_provider_checks", {}).get("alchemy", {}).get("status") != "passed":
        soft_failures.append("Alchemy provider preflight did not succeed")
    if (
        provider_health.get("preflight_provider_checks", {}).get("binance", {}).get("minimum_permission_model")
        != "public_stream_only"
    ):
        hard_failures.append("Binance credential minimum-permission evidence is missing or unexpected")
    if (
        provider_health.get("preflight_provider_checks", {}).get("alchemy", {}).get("minimum_permission_model")
        != "read_only_rpc"
    ):
        hard_failures.append("Alchemy credential minimum-permission evidence is missing or unexpected")
    if (
        int(provider_health.get("provider_anomaly_stats", {}).get("provider_degraded_count", 0))
        > int(provider_health.get("provider_anomaly_stats", {}).get("provider_recovered_count", 0))
        and run.get("run_completed") is True
    ):
        soft_failures.append("provider degraded state was observed without a matching recovery event")

    ready_for_real = not hard_failures and not soft_failures
    ready_for_agent = ready_for_real and agent_layer_governance_enabled and not agent_layer_blockers
    ready_for_broad = ready_for_real and broad_agent_layer_ready and not broad_blockers
    return {
        "evaluated_at_utc": format_utc(utc_now()),
        "hard_failures": hard_failures,
        "soft_failures": soft_failures,
        "agent_layer_blockers": agent_layer_blockers,
        "agent_layer_governance": governance,
        "agent_layer_governance_enabled": agent_layer_governance_enabled,
        "broad_blockers": broad_blockers,
        "broad_agent_layer_ready": broad_agent_layer_ready,
        "broad_agent_layer_enabled": broad_agent_layer_enabled,
        "READY_FOR_REAL_24H_SHADOW": ready_for_real,
        "READY_FOR_AGENT_LAYER": ready_for_agent,
        "READY_FOR_BROAD_AGENT_LAYER": ready_for_broad,
        "controlled_agent_slices": controlled_agent_slices,
    }


def render_postmortem(summary: dict[str, Any]) -> str:
    shadow = dict(summary.get("shadow", {}))
    run = dict(shadow.get("run", {}))
    quality = dict(shadow.get("quality", {}))
    security = dict(shadow.get("security", {}))
    stability = dict(shadow.get("stability", {}))
    provider_health = dict(summary.get("provider_health_snapshot", {}))
    interruption = dict(summary.get("interruption_failure_evidence", {}))
    lease_lifecycle = dict(summary.get("lease_lifecycle", {}))
    go_no_go = dict(summary.get("go_no_go", {}))
    agent_layer_governance = dict(summary.get("agent_layer_governance", {}))
    controlled_agent_slices = dict(summary.get("controlled_agent_slices", {}))
    binance_preflight = dict(provider_health.get("preflight_provider_checks", {}).get("binance", {}))
    unresolved_risks = (
        list(go_no_go.get("soft_failures", []))
        + list(go_no_go.get("agent_layer_blockers", []))
        + list(go_no_go.get("broad_blockers", []))
    )

    lines = [
        "# Shadow Acceptance Postmortem",
        "",
        "## Run Window",
        f"- started_at_utc: {run.get('started_at_utc')}",
        f"- ended_at_utc: {run.get('ended_at_utc')}",
        f"- exit_code: {run.get('exit_code')}",
        f"- run_completed: {run.get('run_completed')}",
        "",
        "## Provider Anomalies",
        f"- binance_reconnect_count: {stability.get('binance_reconnect_count', 0)}",
        f"- binance_subscription_ack_count: {stability.get('binance_subscription_ack_count', 0)}",
        f"- binance_reconnect_count_by_symbol: {stability.get('binance_reconnect_count_by_symbol', {})}",
        f"- binance_subscription_ack_count_by_symbol: {stability.get('binance_subscription_ack_count_by_symbol', {})}",
        f"- binance_receive_timeout_count_by_symbol: {stability.get('binance_receive_timeout_count_by_symbol', {})}",
        f"- binance_watchdog_receive_gap_count_by_symbol: {stability.get('binance_watchdog_receive_gap_count_by_symbol', {})}",
        f"- binance_watchdog_source_age_count_by_symbol: {stability.get('binance_watchdog_source_age_count_by_symbol', {})}",
        f"- alchemy_retry_count: {stability.get('alchemy_retry_count', 0)}",
        f"- provider_degraded_count: {stability.get('provider_degraded_count', 0)}",
        f"- provider_recovered_count: {stability.get('provider_recovered_count', 0)}",
        "",
        "## Lease / Interruption",
        f"- worker_status: {interruption.get('worker_status')}",
        f"- failure_category: {interruption.get('failure_category')}",
        f"- interruption_reason: {interruption.get('interruption_reason')}",
        f"- interesting_event_count: {interruption.get('interesting_event_count', 0)}",
        f"- active_leases_after_run: {len(interruption.get('active_leases_after_run', []))}",
        f"- lease_acquired_count: {lease_lifecycle.get('lease_acquired_count', 0)}",
        f"- lease_heartbeat_count: {lease_lifecycle.get('lease_heartbeat_count', 0)}",
        f"- lease_heartbeat_failed_count: {lease_lifecycle.get('lease_heartbeat_failed_count', 0)}",
        f"- lease_released_count: {lease_lifecycle.get('lease_released_count', 0)}",
        f"- lease_cleanup_count: {lease_lifecycle.get('lease_cleanup_count', 0)}",
        f"- task_lock_reclaimed_count: {lease_lifecycle.get('task_lock_reclaimed_count', 0)}",
        "",
        "## Replay / Quarantine Consistency",
        f"- quarantine_count: {quality.get('quarantine_count', 0)}",
        f"- replay_parse_error_count: {quality.get('replay_parse_error_count', 0)}",
        f"- replay_write_failure_count: {quality.get('replay_write_failure_count', 0)}",
        f"- cross_subject_contamination_count: {quality.get('cross_subject_contamination_count', 0)}",
        f"- downstream_block_count: {provider_health.get('downstream_block_count', 0)}",
        "",
        "## Provider Health Snapshot",
        f"- binance_minimum_permission_model: {provider_health.get('credential_minimum_permission_models', {}).get('binance')}",
        f"- alchemy_minimum_permission_model: {provider_health.get('credential_minimum_permission_models', {}).get('alchemy')}",
        f"- binance_preflight_status: {binance_preflight.get('status')}",
        f"- binance_failure_category: {binance_preflight.get('failure_category')}",
        f"- binance_transport_stage: {binance_preflight.get('transport_stage')}",
        f"- binance_transport: {binance_preflight.get('transport')}",
        f"- binance_endpoint: {binance_preflight.get('endpoint')}",
        f"- binance_exception_type: {binance_preflight.get('exception_type')}",
        f"- health_event_count: {provider_health.get('health_event_count', 0)}",
        f"- provider_degraded_count: {provider_health.get('provider_anomaly_stats', {}).get('provider_degraded_count', 0)}",
        f"- provider_recovered_count: {provider_health.get('provider_anomaly_stats', {}).get('provider_recovered_count', 0)}",
        "",
        "## Controlled Agent Slices",
        f"- contract_version: {controlled_agent_slices.get('contract_version')}",
        f"- controlled_slice_count: {controlled_agent_slices.get('controlled_slice_count')}",
        f"- enabled_slice_ids: {controlled_agent_slices.get('enabled_slice_ids')}",
        f"- broad_agent_layer_enabled: {controlled_agent_slices.get('broad_agent_layer_enabled')}",
        "",
        "## Agent Layer Governance",
        f"- status: {agent_layer_governance.get('status')}",
        f"- manifest_path: {agent_layer_governance.get('manifest_path')}",
        f"- governed_slice_registry_path: {agent_layer_governance.get('governed_slice_registry_path')}",
        f"- contract_version: {agent_layer_governance.get('contract_version')}",
        f"- governed_slice_registry_contract_version: {agent_layer_governance.get('governed_slice_registry_contract_version')}",
        f"- promotion_contract_version: {agent_layer_governance.get('promotion_contract_version')}",
        f"- current_controlled_slice_ids: {agent_layer_governance.get('current_controlled_slice_ids')}",
        f"- promotion_eligible_controlled_slice_ids: {agent_layer_governance.get('promotion_eligible_controlled_slice_ids')}",
        f"- admitted_controlled_slice_ids: {agent_layer_governance.get('admitted_controlled_slice_ids')}",
        f"- registered_pending_promotion_controlled_slice_ids: {agent_layer_governance.get('registered_pending_promotion_controlled_slice_ids')}",
        f"- allowed_controlled_slice_ids: {agent_layer_governance.get('allowed_controlled_slice_ids')}",
        f"- broad_agent_layer_ready: {agent_layer_governance.get('broad_agent_layer_ready')}",
        f"- broad_agent_layer_enabled: {agent_layer_governance.get('broad_agent_layer_enabled')}",
        f"- broad_blocker_count: {len(agent_layer_governance.get('broad_blockers', []))}",
        f"- blocker_count: {len(agent_layer_governance.get('blockers', []))}",
        "",
        "## Log Leak Check",
        f"- key_leakage_detected: {security.get('key_leakage_detected')}",
        f"- unredacted_alchemy_endpoint_detected: {security.get('unredacted_alchemy_endpoint_detected')}",
        "",
        "## Go / No-Go",
        f"- READY_FOR_REAL_24H_SHADOW: {go_no_go.get('READY_FOR_REAL_24H_SHADOW')}",
        f"- READY_FOR_AGENT_LAYER: {go_no_go.get('READY_FOR_AGENT_LAYER')}",
        f"- READY_FOR_BROAD_AGENT_LAYER: {go_no_go.get('READY_FOR_BROAD_AGENT_LAYER')}",
        f"- agent_layer_governance_enabled: {go_no_go.get('agent_layer_governance_enabled')}",
        f"- broad_agent_layer_ready: {go_no_go.get('broad_agent_layer_ready')}",
        f"- broad_agent_layer_enabled: {go_no_go.get('broad_agent_layer_enabled')}",
        f"- hard_failures: {len(go_no_go.get('hard_failures', []))}",
        f"- soft_failures: {len(go_no_go.get('soft_failures', []))}",
        "",
        "## Unresolved Risks",
    ]
    if unresolved_risks:
        lines.extend(f"- {risk}" for risk in unresolved_risks)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _validate_preflight_permit(
    permit: ExecutionPermit,
    *,
    config: PreflightConfig,
    started_at: datetime,
) -> None:
    validate_execution_permit(
        permit,
        operation="cli.shadow_ingest.run",
        required_capabilities={CAP_CLI_SHADOW_INGEST, CAP_PROVIDER_STREAM, CAP_PROVIDER_TRANSPORT},
        requested_scope="shadow_ingestion",
    )
    remaining_seconds = max(
        0.0,
        (permit.expires_at_utc.astimezone(UTC) - started_at).total_seconds(),
    )
    if remaining_seconds < _required_permit_margin_seconds(config):
        raise ValueError(
            f"execution permit expires too soon for the requested soak window: {remaining_seconds:.1f}s remaining"
        )


def _permit_check_payload(
    permit: ExecutionPermit,
    *,
    config: PreflightConfig,
    started_at: datetime,
) -> dict[str, Any]:
    remaining_seconds = max(
        0.0,
        (permit.expires_at_utc.astimezone(UTC) - started_at).total_seconds(),
    )
    return {
        "status": "passed",
        "message": "execution permit is valid",
        "permit_id": permit.permit_id,
        "expires_at_utc": format_utc(permit.expires_at_utc),
        "seconds_until_expiry": remaining_seconds,
        "minimum_required_seconds": _required_permit_margin_seconds(config),
    }


def _read_jsonl_tree(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not root.exists():
        return records
    for path in sorted(root.rglob("*.jsonl")):
        records.extend(_read_jsonl_file(path))
    return records


def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _count_values(records: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get(field_name, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _runtime_seconds(started_at: object, ended_at: object) -> float | None:
    start = _parse_utc(started_at)
    end = _parse_utc(ended_at)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _is_local_endpoint(url: str) -> bool:
    try:
        parsed = urllib_parse.urlparse(url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def _required_permit_margin_seconds(config: PreflightConfig) -> float:
    # Keep the real-24h floor isolated from shorter-run defaults so the
    # non-real 1800-second margin never leaks back into the 24h acceptance path.
    if config.simulation_profile == "real" and config.duration_seconds >= REAL_24H_DURATION_SECONDS:
        return max(config.min_permit_margin_seconds, REAL_24H_MIN_PERMIT_MARGIN_SECONDS)
    return max(config.min_permit_margin_seconds, float(config.duration_seconds) + 60.0)


def _binance_endpoint_metadata(websocket_url: str) -> dict[str, Any]:
    try:
        parsed = urllib_parse.urlparse(websocket_url)
    except ValueError:
        return {
            "endpoint": websocket_url,
            "transport": "unknown",
            "host": None,
            "port": None,
            "path": "",
        }
    default_port = 443 if parsed.scheme == "wss" else 80 if parsed.scheme == "ws" else None
    return {
        "endpoint": websocket_url,
        "transport": parsed.scheme or "unknown",
        "host": parsed.hostname,
        "port": parsed.port or default_port,
        "path": parsed.path or "/",
    }


def _build_binance_probe_error(
    exc: BaseException,
    *,
    websocket_url: str,
    transport_stage: str,
) -> BinanceProbeError:
    if isinstance(exc, BinanceProbeError):
        return exc
    metadata = _binance_endpoint_metadata(websocket_url)
    failure_category = _classify_binance_probe_exception(exc)
    exception_type = type(exc).__name__
    exception_message = str(exc) or repr(exc)
    exception_repr = repr(exc)
    errno = getattr(exc, "errno", None)
    close_code = getattr(exc, "code", None)
    close_reason = getattr(exc, "reason", None)
    return BinanceProbeError(
        failure_category=failure_category,
        transport_stage=transport_stage,
        endpoint=str(metadata["endpoint"]),
        transport=str(metadata["transport"]),
        host=metadata["host"],
        port=metadata["port"],
        path=str(metadata["path"]),
        exception_type=exception_type,
        exception_message=exception_message,
        exception_repr=exception_repr,
        exception_chain=_exception_chain(exc),
        errno=errno if isinstance(errno, int) else None,
        close_code=close_code if isinstance(close_code, int) else None,
        close_reason=close_reason if isinstance(close_reason, str) and close_reason else None,
    )


def _classify_binance_probe_exception(exc: BaseException) -> str:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "payload_parse"
    if isinstance(exc, websockets.exceptions.InvalidURI):
        return "invalid_uri"
    if isinstance(exc, socket.gaierror):
        return "dns_resolution"
    if isinstance(exc, ssl.SSLError):
        return "tls_handshake"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(exc, ConnectionResetError):
        return "connection_reset"
    if isinstance(exc, websockets.exceptions.InvalidHandshake):
        return "websocket_handshake"
    if isinstance(exc, websockets.exceptions.ConnectionClosed):
        return "websocket_closed"
    if isinstance(exc, OSError):
        return "transport_os_error"
    return "unexpected_error"


def _exception_chain(exc: BaseException) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        record: dict[str, Any] = {
            "exception_type": type(current).__name__,
            "exception_message": str(current) or repr(current),
            "exception_repr": repr(current),
        }
        errno = getattr(current, "errno", None)
        if isinstance(errno, int):
            record["errno"] = errno
        close_code = getattr(current, "code", None)
        if isinstance(close_code, int):
            record["close_code"] = close_code
        close_reason = getattr(current, "reason", None)
        if isinstance(close_reason, str) and close_reason:
            record["close_reason"] = close_reason
        records.append(record)
        current = current.__cause__ or current.__context__
    return records
