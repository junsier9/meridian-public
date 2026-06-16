from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from unittest.mock import patch

from .common import REPO_ROOT, to_jsonable
from .models import SnapshotDefinition

from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter
from enhengclaw.core.enums import (
    ClaimType,
    Direction,
    EvidenceLevel,
    ObjectType,
    SourceFamily,
    TimeHorizon,
)
from enhengclaw.core.signals import Signal
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.provider_selection import (
    MODE_DEFAULT,
    MODE_INCLUDE_SHADOW,
    MODE_MANUAL_OVERRIDE,
    ProviderRuntimeBinding,
    ProviderSelectionGateway,
)
from enhengclaw.governance.shadow_admission import ShadowAdmissionRunner
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionCorpus, ShadowPromotionRunner
from enhengclaw.health.data_health_monitor import DataHealthMonitor, DataHealthState
from enhengclaw.health.downstream_gate import DownstreamBlockedError, DownstreamGate
from enhengclaw.health.health_rules import HealthRules
from enhengclaw.ingress.live_replay_writer import LiveQuarantineWriter, LiveReplayWriter
from enhengclaw.ingress.shadow_schema import (
    AlchemyRpcSchemaValidator,
    BinanceTradeSchemaValidator,
    SHADOW_SCHEMA_VERSION,
    ValidatedShadowEvent,
)
from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.utils.subject_keys import SubjectKey


FIXED_NOW = datetime(2026, 4, 9, 0, 10, 0, tzinfo=timezone.utc)


def snapshot_definitions(snapshot_types: set[str] | None = None) -> list[SnapshotDefinition]:
    definitions = [
        SnapshotDefinition("provider_selection", "default_runtime__aix__default", _provider_selection_snapshot),
        SnapshotDefinition("runtime_decision", "strong_bullish__aix__create", _runtime_decision_snapshot),
        SnapshotDefinition("shadow_promotion", "shadow_corpus_v1__onchain", _shadow_promotion_snapshot),
        SnapshotDefinition("shadow_admission", "shadow_corpus_v1__filter", _shadow_admission_snapshot),
        SnapshotDefinition("downstream_gate", "binance_stale__btcusdt__runtime", _downstream_gate_snapshot),
        SnapshotDefinition("replay_artifact_schema", "live_replay", _live_replay_artifact_schema_snapshot),
        SnapshotDefinition("replay_artifact_schema", "live_quarantine", _live_quarantine_artifact_schema_snapshot),
        SnapshotDefinition("shadow_schema", "binance.spot.ws", _binance_shadow_schema_snapshot),
        SnapshotDefinition("shadow_schema", "alchemy.eth.rpc__eth_blockNumber", _alchemy_block_number_schema_snapshot),
        SnapshotDefinition("shadow_schema", "alchemy.eth.rpc__eth_getBlockByNumber", _alchemy_get_block_schema_snapshot),
        SnapshotDefinition("health_decision", "binance_healthy__btcusdt__default", _health_decision_binance_healthy_snapshot),
        SnapshotDefinition("health_decision", "binance_stale__btcusdt__default", _health_decision_binance_stale_snapshot),
        SnapshotDefinition("health_decision", "binance_no_ingest__btcusdt__default", _health_decision_no_ingest_snapshot),
        SnapshotDefinition("health_decision", "binance_contamination__btcusdt__default", _health_decision_contamination_snapshot),
        SnapshotDefinition("health_decision", "binance_replay_failure__btcusdt__default", _health_decision_replay_failure_snapshot),
        SnapshotDefinition("health_decision", "alchemy_healthy__eth__default", _health_decision_alchemy_healthy_snapshot),
    ]
    if snapshot_types is None:
        return definitions
    return [definition for definition in definitions if definition.snapshot_type in snapshot_types]


@lru_cache(maxsize=1)
def _shadow_promotion_report() -> Any:
    corpus = ShadowPromotionCorpus(REPO_ROOT / "fixtures" / "shadow_promotion_corpus")
    return ShadowPromotionRunner(corpus).compare_all()


@lru_cache(maxsize=1)
def _shadow_admission_report() -> Any:
    corpus = ShadowPromotionCorpus(REPO_ROOT / "fixtures" / "shadow_promotion_corpus")
    return ShadowAdmissionRunner(corpus=corpus).compare_with_filter()


@lru_cache(maxsize=1)
def _provider_selection_context() -> dict[str, Any]:
    cex_corpus = GoldenReplayCorpus(REPO_ROOT / "fixtures" / "golden_corpus" / "cex")
    promotion = _shadow_promotion_report()
    contribution = ContributionLedger(
        runner=ShadowAdmissionRunner(corpus=ShadowPromotionCorpus(REPO_ROOT / "fixtures" / "shadow_promotion_corpus"))
    ).build()

    cex_provider = RealCEXProvider(
        RealCEXProviderConfig(mode="replay", raw_payload_dir=cex_corpus.category_root("normal"))
    )
    cex_payload = cex_provider.fetch(
        ProviderRequest(
            object_id="freeze-provider-selection",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
        )
    )
    cex_drift = CEXDriftInspector().inspect(cex_payload)
    onchain_error_count = sum(
        1
        for comparison in promotion.comparisons
        if comparison.onchain_drift_status == "error"
    )
    onchain_warning_count = sum(
        1
        for comparison in promotion.comparisons
        if comparison.onchain_drift_status == "warning"
    )
    onchain_status = (
        "error"
        if onchain_error_count > 0
        else "warning"
        if onchain_warning_count > 0
        else "ok"
    )

    portfolio_report = ProviderPortfolioPolicy().evaluate_all(
        [
            ProviderPortfolioInput(
                provider_name="binance-public-cex",
                provider_type="cex",
                current_status=STATUS_ACTIVE,
                contribution_ledger=None,
                promotion_report=None,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="binance-public-cex",
                    status=cex_drift.status,
                    finding_count=len(cex_drift.findings),
                    error_count=sum(1 for finding in cex_drift.findings if finding.severity == "error"),
                    warning_count=sum(1 for finding in cex_drift.findings if finding.severity == "warning"),
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="binance-public-cex",
                    passed=True,
                    scenario_count=8,
                    notes=["provider regressions green"],
                ),
            ),
            ProviderPortfolioInput(
                provider_name="real_onchain_provider_shadow",
                provider_type="onchain",
                current_status=STATUS_SHADOW_ONLY,
                contribution_ledger=contribution,
                promotion_report=promotion,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    status=onchain_status,
                    finding_count=onchain_error_count + onchain_warning_count,
                    error_count=onchain_error_count,
                    warning_count=onchain_warning_count,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    passed=True,
                    scenario_count=5,
                    notes=["shadow/onchain regressions green"],
                ),
            ),
        ]
    )

    bindings = [
        ProviderRuntimeBinding(
            provider_name="binance-public-cex",
            provider_type="cex",
            adapter=CEXSnapshotAdapter(
                provider=RealCEXProvider(
                    RealCEXProviderConfig(mode="replay", raw_payload_dir=cex_corpus.category_root("normal"))
                )
            ),
        ),
        ProviderRuntimeBinding(
            provider_name="real_onchain_provider_shadow",
            provider_type="onchain",
            adapter=OnchainSnapshotAdapter(
                provider=RealOnchainProvider(
                    RealOnchainProviderConfig(
                        mode="replay",
                        raw_payload_dir=REPO_ROOT / "fixtures" / "golden_corpus" / "onchain" / "normal",
                    )
                )
            ),
        ),
    ]

    return {
        "portfolio_report": portfolio_report,
        "bindings": bindings,
    }


def _provider_selection_snapshot() -> dict[str, Any]:
    context = _provider_selection_context()
    selection = ProviderSelectionGateway().select(
        portfolio_report=context["portfolio_report"],
        bindings=context["bindings"],
        mode=MODE_DEFAULT,
    )
    portfolio_report = context["portfolio_report"]
    return {
        "mode": selection.mode,
        "allowed_provider_names": selection.allowed_provider_names,
        "rejected_provider_names": selection.rejected_provider_names,
        "rejected": [
            {
                "provider_name": entry.provider_name,
                "provider_type": entry.provider_type,
                "portfolio_status": entry.portfolio_status,
                "reason": entry.reason,
            }
            for entry in selection.rejected
        ],
        "default_runtime_provider_names": portfolio_report.default_runtime_provider_names,
        "shadow_provider_names": portfolio_report.shadow_provider_names,
        "provider_selection_modes_available": [
            MODE_DEFAULT,
            MODE_INCLUDE_SHADOW,
            MODE_MANUAL_OVERRIDE,
        ],
    }


def _runtime_decision_snapshot() -> dict[str, Any]:
    result = RuntimeOrchestrator().run_new(
        object_id="freeze-runtime-decision",
        object_type=ObjectType.ASSET,
        scope="spot+perp",
        signals=_strong_bullish_signals("freeze-runtime"),
    )
    return _runtime_summary(result)


def _shadow_promotion_snapshot() -> Any:
    return to_jsonable(_shadow_promotion_report())


def _shadow_admission_snapshot() -> Any:
    return to_jsonable(_shadow_admission_report())


def _downstream_gate_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    monitor = DataHealthMonitor()
    monitor.on_ingest_event(subject_key, FIXED_NOW - timedelta(minutes=10))
    gate = DownstreamGate(
        monitor=monitor,
        rules=HealthRules(now_fn=lambda: FIXED_NOW),
    )
    with patch("enhengclaw.health.downstream_gate.utc_now", new=lambda: FIXED_NOW):
        try:
            gate.check(subject_key, consumer="runtime.adapters.create")
        except DownstreamBlockedError as exc:
            return {
                "subject_key": exc.block_result.subject_key.as_stable_string(),
                "consumer": exc.block_result.consumer,
                "status": exc.block_result.status,
                "reason": exc.block_result.reason,
                "blocked_at_utc": exc.block_result.blocked_at_utc,
                "latest_ingest_timestamp_utc": exc.block_result.latest_ingest_timestamp_utc,
            }
    raise AssertionError("expected downstream gate to block the stale subject")


def _live_replay_artifact_schema_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    root = _prepare_probe_root("live_replay")
    writer = LiveReplayWriter(root)
    event = ValidatedShadowEvent(
        subject_key=subject_key,
        provider_id="binance.spot.ws",
        event_type="trade",
        source_timestamp="2026-04-09T00:00:00.000Z",
        raw_payload={"stream": "btcusdt@trade"},
        schema_version=SHADOW_SCHEMA_VERSION,
        event_id="sha256:freeze-live-replay",
    )
    with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: FIXED_NOW):
        result = writer.write(event=event)
    record = _read_first_json_line(Path(result.path))
    return _artifact_schema_snapshot(
        file_kind="live_replay",
        path=result.path,
        record=record,
    )


def _live_quarantine_artifact_schema_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="SOLUSDT", venue="binance", instrument_type="spot")
    root = _prepare_probe_root("live_quarantine")
    writer = LiveQuarantineWriter(root)
    with patch("enhengclaw.ingress.live_replay_writer.utc_now", new=lambda: FIXED_NOW):
        result = writer.write(
            subject_key=subject_key,
            provider_id="binance.spot.ws",
            event_type="trade",
            raw_payload={"stream": "solusdt@trade"},
            reason="schema violation",
            schema_version=SHADOW_SCHEMA_VERSION,
        )
    record = _read_first_json_line(Path(result.path))
    return _artifact_schema_snapshot(
        file_kind="live_quarantine",
        path=result.path,
        record=record,
    )


def _binance_shadow_schema_snapshot() -> dict[str, Any]:
    validator = BinanceTradeSchemaValidator(["BTCUSDT", "ETHUSDT"])
    payload = {
        "stream": "btcusdt@trade",
        "data": {
            "e": "trade",
            "E": 1712534400000,
            "s": "BTCUSDT",
            "t": 123456,
            "p": "68750.10",
            "q": "0.005",
            "T": 1712534400001,
        },
    }
    event = validator.validate(payload)
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "provider_id": validator.provider_id,
        "event_type": validator.event_type,
        "required_fields": ["data", "data.E", "data.e", "data.p", "data.q", "data.s", "data.t"],
        "optional_fields": ["data.T", "stream"],
        "type_constraints": {
            "data.e": "non-empty string == trade",
            "data.E": "integer",
            "data.s": "non-empty string within configured subject set",
            "data.t": "integer",
            "data.p": "numeric-like",
            "data.q": "numeric-like",
            "data.T": "optional integer",
            "stream": "optional lower-case <symbol>@trade string matching data.s",
        },
        "sample_validated_event": _validated_event_snapshot(event),
    }


def _alchemy_block_number_schema_snapshot() -> dict[str, Any]:
    validator = AlchemyRpcSchemaValidator()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": "0x10",
    }
    event = validator.validate(method="eth_blockNumber", payload=payload, expected_id=1)
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "provider_id": validator.provider_id,
        "event_type": "eth_blockNumber",
        "required_fields": ["id", "jsonrpc", "result"],
        "optional_fields": [],
        "type_constraints": {
            "jsonrpc": "non-empty string == 2.0",
            "id": "non-null scalar",
            "result": "hex quantity string",
        },
        "sample_validated_event": _validated_event_snapshot(event),
    }


def _alchemy_get_block_schema_snapshot() -> dict[str, Any]:
    validator = AlchemyRpcSchemaValidator()
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "number": "0x10",
            "timestamp": "0x6612e080",
        },
    }
    event = validator.validate(method="eth_getBlockByNumber", payload=payload, expected_id=2)
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "provider_id": validator.provider_id,
        "event_type": "eth_getBlockByNumber",
        "required_fields": ["id", "jsonrpc", "result", "result.number", "result.timestamp"],
        "optional_fields": [],
        "type_constraints": {
            "jsonrpc": "non-empty string == 2.0",
            "id": "non-null scalar",
            "result": "object",
            "result.number": "hex quantity string",
            "result.timestamp": "hex quantity string",
        },
        "sample_validated_event": _validated_event_snapshot(event),
    }


def _health_decision_binance_healthy_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    state = DataHealthState(
        subject_key=subject_key,
        latest_ingest_timestamp_utc=FIXED_NOW - timedelta(seconds=60),
        last_gap_seconds=10.0,
    )
    return _health_snapshot(state)


def _health_decision_binance_stale_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    state = DataHealthState(
        subject_key=subject_key,
        latest_ingest_timestamp_utc=FIXED_NOW - timedelta(minutes=10),
        last_gap_seconds=10.0,
    )
    return _health_snapshot(state)


def _health_decision_no_ingest_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    return _health_snapshot(DataHealthState(subject_key=subject_key))


def _health_decision_contamination_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    state = DataHealthState(
        subject_key=subject_key,
        latest_ingest_timestamp_utc=FIXED_NOW - timedelta(seconds=30),
        contamination=True,
        contamination_reason="cross-subject contamination",
    )
    return _health_snapshot(state)


def _health_decision_replay_failure_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="BTCUSDT", venue="binance", instrument_type="spot")
    state = DataHealthState(
        subject_key=subject_key,
        latest_ingest_timestamp_utc=FIXED_NOW - timedelta(seconds=30),
        replay_write_failure=True,
        replay_write_failure_reason="live replay write failed: disk full",
    )
    return _health_snapshot(state)


def _health_decision_alchemy_healthy_snapshot() -> dict[str, Any]:
    subject_key = SubjectKey.build(symbol="ETH", venue="alchemy", instrument_type="onchain")
    state = DataHealthState(
        subject_key=subject_key,
        latest_ingest_timestamp_utc=FIXED_NOW - timedelta(minutes=5),
        last_gap_seconds=0.0,
    )
    return _health_snapshot(state)


def _runtime_summary(result: Any) -> dict[str, Any]:
    thesis_index = {thesis.thesis_id: thesis for thesis in result.theses}
    primary = thesis_index.get(result.research_object.working_primary_thesis_id)
    opposing = thesis_index.get(result.research_object.working_opposing_thesis_id)
    allocation = result.resource_allocation
    return {
        "decision": result.decision.decision,
        "reasons": list(result.decision.reasons),
        "processing_state": result.research_object.processing_state.value,
        "risk_state": result.research_object.risk_state.value,
        "attention_score": result.research_object.attention_score,
        "working_primary_thesis_id": result.research_object.working_primary_thesis_id,
        "working_primary_thesis_type": None if primary is None else primary.thesis_type.value,
        "working_primary_thesis_status": None if primary is None else primary.status.value,
        "working_primary_direction": None if primary is None else primary.direction.value,
        "working_primary_confidence": None if primary is None else primary.confidence,
        "working_opposing_thesis_id": result.research_object.working_opposing_thesis_id,
        "working_opposing_thesis_type": None if opposing is None else opposing.thesis_type.value,
        "working_opposing_thesis_status": None if opposing is None else opposing.status.value,
        "allocation": None
        if allocation is None
        else {
            "tier": allocation.tier.value,
            "slot": allocation.slot_type.value,
        },
        "step_log": [
            {
                "cycle": step.cycle,
                "step": step.step,
                "status": step.status,
                "processing_state_before": step.processing_state_before,
                "processing_state_after": step.processing_state_after,
                "details": to_jsonable(step.details),
            }
            for step in result.steps
        ],
    }


def _strong_bullish_signals(prefix: str) -> list[Signal]:
    return [
        _make_signal(
            f"{prefix}-1",
            subject="AIX",
            predicate="spot_breakout",
            value="spot volume expansion",
            claim_type=ClaimType.MEASUREMENT,
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=82,
        ),
        _make_signal(
            f"{prefix}-2",
            subject="AIX",
            predicate="smart_money_accumulation",
            value="wallets net buying",
            claim_type=ClaimType.FLOW,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=78,
        ),
        _make_signal(
            f"{prefix}-3",
            subject="AIX",
            predicate="structure_support",
            value="spot leads perps",
            claim_type=ClaimType.MARKET_STRUCTURE,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ANALYTICS,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=75,
        ),
    ]


def _make_signal(
    signal_id: str,
    *,
    subject: str,
    predicate: str,
    value: str,
    claim_type: ClaimType,
    direction: Direction,
    source_family: SourceFamily,
    evidence_level: EvidenceLevel,
    confidence_hint: int,
) -> Signal:
    return Signal(
        signal_id=signal_id,
        object_type=ObjectType.ASSET,
        subject=subject,
        predicate=predicate,
        value=value,
        claim_type=claim_type,
        direction=direction,
        source_family=source_family,
        evidence_level=evidence_level,
        confidence_hint=confidence_hint,
        scope="spot+perp",
        time_horizon=TimeHorizon.INTRADAY,
        fresh=True,
    )


def _artifact_schema_snapshot(*, file_kind: str, path: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_kind": file_kind,
        "extension": Path(path).suffix,
        "path": path,
        "required_keys": sorted(record.keys()),
        "optional_keys": [],
        "value_types": {key: _value_type(value) for key, value in sorted(record.items())},
    }


def _validated_event_snapshot(event: ValidatedShadowEvent) -> dict[str, Any]:
    return {
        "subject_key": event.subject_key.as_stable_string(),
        "provider_id": event.provider_id,
        "event_type": event.event_type,
        "source_timestamp": event.source_timestamp,
        "schema_version": event.schema_version,
        "event_id": event.event_id,
    }


def _health_snapshot(state: DataHealthState) -> dict[str, Any]:
    decision = HealthRules(now_fn=lambda: FIXED_NOW).evaluate(state)
    return {
        "input_state": {
            "subject_key": state.subject_key.as_stable_string(),
            "latest_ingest_timestamp_utc": state.latest_ingest_timestamp_utc,
            "last_gap_seconds": state.last_gap_seconds,
            "latest_source_timestamp_utc": state.latest_source_timestamp_utc,
            "contamination": state.contamination,
            "contamination_reason": state.contamination_reason,
            "replay_write_failure": state.replay_write_failure,
            "replay_write_failure_reason": state.replay_write_failure_reason,
        },
        "action": decision.action,
        "status": decision.status,
        "reason": decision.reason,
    }


def _read_first_json_line(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"snapshot source file is empty: {path}")
    return json.loads(lines[0])


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _prepare_probe_root(name: str) -> Path:
    root = REPO_ROOT / "artifacts" / "refactor_freeze" / "_probe" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    return root
