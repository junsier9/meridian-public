from __future__ import annotations

from datetime import datetime, timezone

from enhengclaw.adapters.adapters import AdapterBatch, AdapterRequest, SignalAdapter
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, SourceFamily, TimeHorizon
from enhengclaw.core.signals import Signal
from enhengclaw.domain.identity.subject_key import SubjectKey


class _BaseMockAdapter(SignalAdapter):
    provider_name: str
    subject_instrument_type: str = "mock"

    def _subject_key(self, request: AdapterRequest) -> SubjectKey:
        return SubjectKey.from_request(
            request,
            default_venue=self.provider_name,
            default_instrument_type=self.subject_instrument_type,
        )

    def _batch(self, request: AdapterRequest, signals: list[Signal]) -> AdapterBatch:
        subject_key = self._subject_key(request)
        return AdapterBatch(
            adapter_name=self.adapter_name,
            source_family=self.source_family,
            source_metadata={
                "provider": self.provider_name,
                "scenario": request.scenario,
                "subject_key": subject_key.as_path_fragment(),
            },
            retrieval_timestamp=datetime.now(timezone.utc),
            signals=signals,
        )

    def _signal(
        self,
        request: AdapterRequest,
        suffix: str,
        predicate: str,
        value: str,
        claim_type: ClaimType,
        direction: Direction,
        evidence_level: EvidenceLevel,
        confidence_hint: int,
        *,
        time_horizon: TimeHorizon | None = None,
        fresh: bool = True,
    ) -> Signal:
        subject_key = self._subject_key(request)
        return Signal(
            signal_id=f"{request.object_id}:{subject_key.as_path_fragment()}:{self.adapter_name}:{suffix}",
            object_type=request.object_type,
            subject=request.subject,
            predicate=predicate,
            value=value,
            claim_type=claim_type,
            direction=direction,
            source_family=self.source_family,
            evidence_level=evidence_level,
            confidence_hint=confidence_hint,
            scope=request.scope,
            time_horizon=request.time_horizon if time_horizon is None else time_horizon,
            fresh=fresh,
        )


class MockCEXMarketAdapter(_BaseMockAdapter):
    adapter_name = "mock_cex_market"
    provider_name = "mock-cex"
    source_family = SourceFamily.CEX
    subject_instrument_type = "mock_cex"

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        scenario_map = {
            "bullish_publish": [
                self._signal(
                    request,
                    "spot_breakout",
                    "spot_breakout",
                    "spot volume expansion with price strength",
                    ClaimType.MEASUREMENT,
                    Direction.BULLISH,
                    EvidenceLevel.E4,
                    82,
                ),
                self._signal(
                    request,
                    "market_structure",
                    "market_structure_support",
                    "spot is leading perps with constructive structure",
                    ClaimType.MARKET_STRUCTURE,
                    Direction.BULLISH,
                    EvidenceLevel.E4,
                    75,
                ),
            ],
            "restricted_monitoring": [
                self._signal(
                    request,
                    "spot_breakout",
                    "spot_breakout",
                    "spot volume remains strong",
                    ClaimType.MEASUREMENT,
                    Direction.BULLISH,
                    EvidenceLevel.E4,
                    80,
                ),
                self._signal(
                    request,
                    "funding_risk",
                    "funding_risk",
                    "funding and OI are elevated",
                    ClaimType.RISK_FLAG,
                    Direction.RISK,
                    EvidenceLevel.E3,
                    62,
                    time_horizon=TimeHorizon.SHORT,
                ),
            ],
            "blocked_risk": [],
        }
        return self._batch(request, scenario_map.get(request.scenario, []))


class MockOnchainFlowAdapter(_BaseMockAdapter):
    adapter_name = "mock_onchain_flow"
    provider_name = "mock-onchain"
    source_family = SourceFamily.ONCHAIN
    subject_instrument_type = "mock_onchain"

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        scenario_map = {
            "bullish_publish": [
                self._signal(
                    request,
                    "wallet_buy",
                    "wallet_buy",
                    "smart money wallets are net buying",
                    ClaimType.FLOW,
                    Direction.BULLISH,
                    EvidenceLevel.E4,
                    78,
                )
            ],
            "restricted_monitoring": [
                self._signal(
                    request,
                    "wallet_buy",
                    "wallet_buy",
                    "a subset of smart money wallets remain net buyers",
                    ClaimType.FLOW,
                    Direction.BULLISH,
                    EvidenceLevel.E4,
                    72,
                )
            ],
            "blocked_risk": [],
        }
        return self._batch(request, scenario_map.get(request.scenario, []))


class MockSafetyRiskAdapter(_BaseMockAdapter):
    adapter_name = "mock_safety_risk"
    provider_name = "mock-safety"
    source_family = SourceFamily.SAFETY
    subject_instrument_type = "mock_safety"

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        scenario_map = {
            "bullish_publish": [
                self._signal(
                    request,
                    "overheating_risk",
                    "overheating_risk",
                    "funding is elevated and leverage is building",
                    ClaimType.RISK_FLAG,
                    Direction.RISK,
                    EvidenceLevel.E3,
                    66,
                    time_horizon=TimeHorizon.SHORT,
                )
            ],
            "restricted_monitoring": [
                self._signal(
                    request,
                    "bridge_risk",
                    "bridge_risk",
                    "bridge governance activity is unusual and unresolved",
                    ClaimType.RISK_FLAG,
                    Direction.RISK,
                    EvidenceLevel.E4,
                    68,
                    time_horizon=TimeHorizon.SHORT,
                )
            ],
            "blocked_risk": [
                self._signal(
                    request,
                    "critical_exploit",
                    "critical_exploit",
                    "high-confidence exploit evidence has been detected",
                    ClaimType.INVALIDATION,
                    Direction.INVALIDATING,
                    EvidenceLevel.E5,
                    90,
                    time_horizon=TimeHorizon.SHORT,
                )
            ],
        }
        return self._batch(request, scenario_map.get(request.scenario, []))


class MockInfoflowAdapter(_BaseMockAdapter):
    adapter_name = "mock_infoflow"
    provider_name = "mock-infoflow"
    source_family = SourceFamily.INFOFLOW
    subject_instrument_type = "mock_infoflow"

    def collect(self, request: AdapterRequest) -> AdapterBatch:
        scenario_map = {
            "bullish_publish": [
                self._signal(
                    request,
                    "narrative",
                    "narrative_rotation",
                    "narrative chatter supports follow-through interest",
                    ClaimType.CAUSAL,
                    Direction.BULLISH,
                    EvidenceLevel.E2,
                    42,
                )
            ],
            "restricted_monitoring": [
                self._signal(
                    request,
                    "uncertainty",
                    "risk_chatter",
                    "mixed chatter suggests unresolved bridge concerns",
                    ClaimType.CAUSAL,
                    Direction.NEUTRAL,
                    EvidenceLevel.E2,
                    38,
                )
            ],
            "blocked_risk": [
                self._signal(
                    request,
                    "official_chatter",
                    "incident_chatter",
                    "high attention chatter confirms incident awareness",
                    ClaimType.FACT,
                    Direction.RISK,
                    EvidenceLevel.E3,
                    70,
                    time_horizon=TimeHorizon.SHORT,
                )
            ],
        }
        return self._batch(request, scenario_map.get(request.scenario, []))
