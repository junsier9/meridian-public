from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterator
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import (
    CAP_PROVIDER_FETCH,
    CAP_PROVIDER_SELECT_INCLUDE_SHADOW,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    CAP_RUNTIME_EXECUTE,
    LEASE_REGISTRY_PATH_ENV,
    MissingExecutionPermitError,
    ExecutionPermit,
    load_execution_permit,
)
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.session import FileObjectStore, RUNTIME_SESSION_ROOT_ENV
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.orchestration.batch_pilot_runner import BatchPilotProviderSetup
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.orchestration.worker_operations import OPERATIONAL_AUDIT_ROOT_ENV
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSourceSpec,
    expected_provider_payload_path,
    load_cex_payload_artifact,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.testing import execution_testbed


@contextmanager
def resolve_demo_execution_permit(
    *,
    scope: str,
    slug: str,
    execution_permit_path: str | None = None,
) -> Iterator[ExecutionPermit]:
    if execution_permit_path is not None:
        yield load_execution_permit(Path(execution_permit_path).resolve())
        return
    with execution_testbed() as bed:
        _, permit = bed.issue_permit(
            slug=slug,
            scope=scope,
            capabilities=[
                CAP_RUNTIME_EXECUTE,
                CAP_PROVIDER_FETCH,
                CAP_PROVIDER_STREAM,
                CAP_PROVIDER_TRANSPORT,
                CAP_PROVIDER_SELECT_INCLUDE_SHADOW,
            ],
            allowed_operations=["*"],
        )
        yield permit


def resolve_governed_demo_artifacts_root(
    *,
    artifacts_root: str | Path | None,
    agent_id: str,
) -> Path:
    if artifacts_root is not None and str(artifacts_root).strip():
        resolved = Path(artifacts_root).resolve()
    else:
        resolved = Path(
            tempfile.mkdtemp(
                prefix=f"ecgd_{agent_id[:12]}_",
                dir=_resolve_governed_demo_temp_root(),
            )
        ).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_governed_demo_temp_root() -> str | None:
    candidates: list[Path] = []
    if os.name == "nt":
        temp_drive = Path(tempfile.gettempdir()).drive or Path.cwd().drive
        if temp_drive:
            candidates.append(Path(f"{temp_drive}\\ecgd"))
    candidates.append(Path(tempfile.gettempdir()) / "ecgd")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(candidate)
    return None


def governed_demo_paths(artifacts_root: str | Path) -> dict[str, Path]:
    root = Path(artifacts_root).resolve()
    return {
        "artifacts_root": root,
        "runtime_sessions": root / "runtime_sessions",
        "replay_log": root / "replay_log",
        "quarantine": root / "quarantine",
        "operational_audit": root / "operational_audit",
        "lease_registry_path": root / "execution_leases.sqlite3",
    }


@contextmanager
def _override_environment(values: dict[str, str]) -> Iterator[None]:
    saved = {key: os.getenv(key) for key in values}
    for key, value in values.items():
        os.environ[key] = value
    try:
        yield
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


@contextmanager
def resolve_governed_demo_execution_permit(
    *,
    scope: str,
    slug: str,
    artifacts_root: str | Path,
    execution_permit_path: str | None = None,
    require_external_permit: bool = False,
) -> Iterator[tuple[ExecutionPermit, dict[str, Path]]]:
    paths = governed_demo_paths(artifacts_root)
    for root in (
        paths["runtime_sessions"],
        paths["replay_log"],
        paths["quarantine"],
        paths["operational_audit"],
    ):
        root.mkdir(parents=True, exist_ok=True)
    env_overrides = {
        RUNTIME_SESSION_ROOT_ENV: str(paths["runtime_sessions"]),
        OPERATIONAL_AUDIT_ROOT_ENV: str(paths["operational_audit"]),
        LEASE_REGISTRY_PATH_ENV: str(paths["lease_registry_path"]),
    }
    if execution_permit_path is not None:
        with _override_environment(env_overrides):
            yield load_execution_permit(Path(execution_permit_path).resolve()), paths
        return
    if require_external_permit:
        raise MissingExecutionPermitError(
            "governed-agent ingress demo requires --execution-permit when --require-external-permit is set"
        )
    with execution_testbed() as bed:
        _, permit = bed.issue_permit(
            slug=slug,
            scope=scope,
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
        )
        with _override_environment(env_overrides):
            yield permit, paths


def build_governed_demo_runtime(
    *,
    artifacts_root: str | Path,
    execution_permit: ExecutionPermit,
) -> RuntimeOrchestrator:
    paths = governed_demo_paths(artifacts_root)
    return RuntimeOrchestrator(
        store=FileObjectStore(paths["runtime_sessions"]),
        agent_ingress_firewall=AgentIngressFirewall(
            quarantine_buffer=QuarantineBuffer(paths["quarantine"]),
            replayable_input_log=ReplayableInputLog(paths["replay_log"]),
        ),
        execution_permit=execution_permit,
    )


def governed_demo_session_path(*, artifacts_root: str | Path, object_id: str) -> Path:
    paths = governed_demo_paths(artifacts_root)
    return paths["runtime_sessions"] / f"{quote(object_id, safe='._-')}.json"


def build_demo_batch_setup(
    *,
    symbol: str,
    scope: str,
    use_live: bool,
    include_shadow: bool,
) -> BatchPilotProviderSetup:
    if use_live:
        provider_mode = "live_record"
        scenario = "live_cex_pilot"
        cex_source = ProviderSourceSpec.real_cex(
            provider_name="binance-public-cex",
            mode="record",
            api_base_url="https://api.binance.com",
            timeout_seconds=5.0,
            api_key_env_var="REAL_CEX_API_KEY",
            raw_payload_root=ROOT / "artifacts" / "provider_records" / "cex",
        )
        cex_drift_status = "ok"
        cex_drift_findings = 0
        cex_drift_errors = 0
        cex_drift_warnings = 0
    else:
        provider_mode = "replay"
        scenario = "bullish_publish"
        cex_corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
        cex_source = ProviderSourceSpec.real_cex(
            provider_name="binance-public-cex",
            mode="replay",
            raw_payload_root=cex_corpus.category_root("normal"),
        )
        cex_payload_path = expected_provider_payload_path(
            cex_source,
            ProviderRequest(
                object_id=f"demo-{symbol.lower()}",
                object_type=ObjectType.ASSET,
                subject=symbol,
                scope=scope,
                scenario=scenario,
            ),
        )
        if cex_payload_path is None:
            raise ValueError("demo replay source did not resolve to a payload artifact path")
        cex_drift = CEXDriftInspector().inspect(load_cex_payload_artifact(cex_payload_path))
        cex_drift_status = cex_drift.status
        cex_drift_findings = len(cex_drift.findings)
        cex_drift_errors = sum(1 for finding in cex_drift.findings if finding.severity == "error")
        cex_drift_warnings = sum(1 for finding in cex_drift.findings if finding.severity == "warning")

    provider_inputs = [
        ProviderPortfolioInput(
            provider_name="binance-public-cex",
            provider_type="cex",
            current_status=STATUS_ACTIVE,
            contribution_ledger=None,
            promotion_report=None,
            drift_snapshot=ProviderDriftSnapshot(
                provider_name="binance-public-cex",
                status=cex_drift_status,
                finding_count=cex_drift_findings,
                error_count=cex_drift_errors,
                warning_count=cex_drift_warnings,
            ),
            chaos_snapshot=ProviderChaosSnapshot(
                provider_name="binance-public-cex",
                passed=True,
                scenario_count=1,
                notes=["demo baseline provider is healthy"],
            ),
        )
    ]
    provider_sources = [cex_source]

    if include_shadow:
        provider_inputs.append(
            ProviderPortfolioInput(
                provider_name="real_onchain_provider_shadow",
                provider_type="onchain",
                current_status=STATUS_SHADOW_ONLY,
                contribution_ledger=None,
                promotion_report=None,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    status="ok",
                    finding_count=0,
                    error_count=0,
                    warning_count=0,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    passed=True,
                    scenario_count=1,
                    notes=["demo shadow provider remains observation-only"],
                ),
            )
        )
        provider_sources.append(
            ProviderSourceSpec.real_onchain(
                provider_name="real_onchain_provider_shadow",
                mode="replay",
                raw_payload_root=ROOT / "fixtures" / "golden_corpus" / "onchain" / "normal",
            )
        )

    portfolio_report = ProviderPortfolioPolicy().evaluate_all(provider_inputs)
    return BatchPilotProviderSetup(
        provider_inputs=provider_inputs,
        portfolio_report=portfolio_report,
        provider_sources=provider_sources,
        scenario=scenario,
        provider_mode=provider_mode,
    )
