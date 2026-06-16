from __future__ import annotations

from dataclasses import dataclass

from enhengclaw.governance.shadow_contribution import (
    ContributionLedgerReport,
    HEALTH_RETIRE_PROVIDER,
)
from enhengclaw.governance.shadow_promotion import (
    PromotionReport,
    RECOMMEND_LIMITED_PARTICIPATE,
    RECOMMEND_REJECT_PROVIDER,
    RECOMMEND_STAY_SHADOW_ONLY,
)


STATUS_SHADOW_ACTIVE = "shadow_active"
STATUS_SHADOW_DEGRADED = "shadow_degraded"
STATUS_CANDIDATE = "candidate"
STATUS_PRODUCTION = "production"
STATUS_RETIRED = "retired"

# Backward-compatible aliases for older demos/tests.
STATUS_ACTIVE = STATUS_PRODUCTION
STATUS_SHADOW_ONLY = STATUS_SHADOW_ACTIVE
STATUS_PROBATION = STATUS_CANDIDATE


@dataclass(frozen=True, slots=True)
class ProviderDriftSnapshot:
    provider_name: str
    status: str
    finding_count: int
    error_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class ProviderChaosSnapshot:
    provider_name: str
    passed: bool
    scenario_count: int
    notes: list[str]


@dataclass(frozen=True, slots=True)
class ProviderPortfolioInput:
    provider_name: str
    provider_type: str
    current_status: str
    contribution_ledger: ContributionLedgerReport | None
    promotion_report: PromotionReport | None
    drift_snapshot: ProviderDriftSnapshot
    chaos_snapshot: ProviderChaosSnapshot
    reevaluation_requested: bool = False
    last_evaluated_corpus_version: str | None = None
    last_evaluated_adapter_version: str | None = None
    candidate_corpus_version: str | None = None
    candidate_adapter_version: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderPortfolioEntry:
    provider_name: str
    provider_type: str
    current_status: str
    portfolio_status: str
    status_changed: bool
    reasons: list[str]
    recommended_action: str


@dataclass(frozen=True, slots=True)
class ProviderPortfolioReport:
    entries: list[ProviderPortfolioEntry]
    default_runtime_provider_names: list[str]
    shadow_provider_names: list[str]


class ProviderPortfolioPolicy:
    def __init__(
        self,
        *,
        probation_decision_drift_threshold: float = 0.20,
        low_structural_noise_threshold: float = 0.25,
        min_schema_conformance_rate: float = 0.80,
        min_data_validity_rate: float = 0.80,
        min_candidate_acceptance_rate: float = 0.50,
    ) -> None:
        self.probation_decision_drift_threshold = probation_decision_drift_threshold
        self.low_structural_noise_threshold = low_structural_noise_threshold
        self.min_schema_conformance_rate = min_schema_conformance_rate
        self.min_data_validity_rate = min_data_validity_rate
        self.min_candidate_acceptance_rate = min_candidate_acceptance_rate

    def evaluate_all(self, providers: list[ProviderPortfolioInput]) -> ProviderPortfolioReport:
        entries = [self.evaluate_provider(provider) for provider in providers]
        default_runtime_provider_names = [
            entry.provider_name for entry in entries if entry.portfolio_status == STATUS_PRODUCTION
        ]
        shadow_provider_names = [
            entry.provider_name
            for entry in entries
            if entry.portfolio_status in {STATUS_SHADOW_ACTIVE, STATUS_SHADOW_DEGRADED, STATUS_CANDIDATE}
        ]
        return ProviderPortfolioReport(
            entries=entries,
            default_runtime_provider_names=default_runtime_provider_names,
            shadow_provider_names=shadow_provider_names,
        )

    def evaluate_provider(self, provider: ProviderPortfolioInput) -> ProviderPortfolioEntry:
        reasons: list[str] = []
        promotion = provider.promotion_report.recommendation.recommendation if provider.promotion_report is not None else None
        decision_change_rate = (
            provider.promotion_report.metrics.decision_change_rate if provider.promotion_report is not None else 0.0
        )
        summary = None if provider.contribution_ledger is None else provider.contribution_ledger.summary
        structural_noise_rate = 0.0 if summary is None else summary.structural_noise_rate
        acceptance_rate = 0.0 if summary is None else summary.acceptance_rate
        signal_attempt_count = 0 if summary is None else summary.signal_attempt_count
        schema_conformance_rate = 0.0 if summary is None else summary.schema_conformance_rate
        data_validity_rate = 0.0 if summary is None else summary.data_validity_rate
        observation_window_complete = False if summary is None else summary.observation_window_complete
        drift_error = provider.drift_snapshot.status == "error"
        low_structural_noise = structural_noise_rate <= self.low_structural_noise_threshold
        reevaluation_allowed = self._reevaluation_allowed(provider)
        quality_degraded = (
            schema_conformance_rate < self.min_schema_conformance_rate
            or data_validity_rate < self.min_data_validity_rate
        )
        candidate_ready = (
            low_structural_noise
            and acceptance_rate >= self.min_candidate_acceptance_rate
            and schema_conformance_rate >= self.min_schema_conformance_rate
            and data_validity_rate >= self.min_data_validity_rate
            and provider.chaos_snapshot.passed
            and not drift_error
        )
        fully_rejected = (
            promotion == RECOMMEND_REJECT_PROVIDER
            and observation_window_complete
            and signal_attempt_count > 0
            and schema_conformance_rate < self.min_schema_conformance_rate
        )

        if provider.current_status == STATUS_PRODUCTION:
            if not provider.chaos_snapshot.passed:
                reasons.append("chaos regression is not passing for the active provider")
                return self._entry(
                    provider,
                    STATUS_SHADOW_DEGRADED,
                    reasons,
                    "remove from default runtime and keep the provider in degraded shadow observation",
                )
            if drift_error:
                reasons.append("drift inspector reports provider payload errors")
                return self._entry(
                    provider,
                    STATUS_SHADOW_DEGRADED,
                    reasons,
                    "remove from default runtime and keep the provider in degraded shadow observation",
                )
            reasons.append("provider remains the stable default runtime source")
            return self._entry(provider, STATUS_PRODUCTION, reasons, "keep participating in runtime by default")

        if provider.current_status == STATUS_RETIRED and not reevaluation_allowed:
            reasons.append("retired providers require explicit reevaluation with a new corpus or adapter version")
            return self._entry(provider, STATUS_RETIRED, reasons, "do not select by default; require explicit reevaluation request")

        if not observation_window_complete:
            if drift_error:
                reasons.append("provider drift summary is already degraded before the observation window completed")
                return self._entry(
                    provider,
                    STATUS_SHADOW_DEGRADED,
                    reasons,
                    "keep observing in shadow and block promotion until schema drift is resolved",
                )
            if not provider.chaos_snapshot.passed:
                reasons.append("provider chaos regression is not passing during the observation window")
                return self._entry(
                    provider,
                    STATUS_SHADOW_DEGRADED,
                    reasons,
                    "keep observing in shadow and block promotion until chaos regressions pass",
                )
            reasons.append("provider remains inside the observation window and cannot change lifecycle stage yet")
            return self._entry(
                provider,
                STATUS_SHADOW_ACTIVE,
                reasons,
                "continue shadow observation until the full evaluation window is complete",
            )

        if fully_rejected or provider.contribution_ledger is not None and provider.contribution_ledger.health.status == HEALTH_RETIRE_PROVIDER:
            reasons.append("promotion policy rejects the provider on the current corpus")
            return self._entry(provider, STATUS_RETIRED, reasons, "retire provider and block default runtime selection")

        if drift_error:
            reasons.append("provider drift summary still reports payload errors")
            return self._entry(provider, STATUS_SHADOW_DEGRADED, reasons, "remain in degraded shadow mode until drift is clean")

        if not provider.chaos_snapshot.passed:
            reasons.append("provider chaos regression is not passing")
            return self._entry(provider, STATUS_SHADOW_DEGRADED, reasons, "remain in degraded shadow mode until chaos regressions pass")

        if quality_degraded or structural_noise_rate > 0.5:
            reasons.append("provider shadow metrics remain degraded after the full observation window")
            return self._entry(
                provider,
                STATUS_SHADOW_DEGRADED,
                reasons,
                "stay in degraded shadow mode and gather cleaner samples before any promotion",
            )

        if provider.current_status == STATUS_CANDIDATE:
            if decision_change_rate > self.probation_decision_drift_threshold:
                reasons.append("candidate provider exceeds the allowed decision drift threshold")
                return self._entry(
                    provider,
                    STATUS_SHADOW_DEGRADED,
                    reasons,
                    "demote to degraded shadow mode and reopen the observation window",
                )
            if candidate_ready and promotion == RECOMMEND_LIMITED_PARTICIPATE:
                reasons.append("candidate provider completed the observation window with stable promotion metrics")
                return self._entry(provider, STATUS_PRODUCTION, reasons, "promote into the default production runtime")
            reasons.append("candidate provider completed the window but still lacks enough evidence for production")
            return self._entry(provider, STATUS_CANDIDATE, reasons, "keep the provider in candidate evaluation")

        if candidate_ready and promotion == RECOMMEND_LIMITED_PARTICIPATE:
            reasons.append("promotion report is positive and the observation window quality metrics are stable")
            return self._entry(provider, STATUS_CANDIDATE, reasons, "promote into candidate stage and continue limited observation")

        reasons.append("provider may continue in non-participating observation mode")
        return self._entry(provider, STATUS_SHADOW_ACTIVE, reasons, "continue shadow observation without promoting the provider")

    def _entry(
        self,
        provider: ProviderPortfolioInput,
        status: str,
        reasons: list[str],
        action: str,
    ) -> ProviderPortfolioEntry:
        return ProviderPortfolioEntry(
            provider_name=provider.provider_name,
            provider_type=provider.provider_type,
            current_status=provider.current_status,
            portfolio_status=status,
            status_changed=status != provider.current_status,
            reasons=reasons,
            recommended_action=action,
        )

    def _reevaluation_allowed(self, provider: ProviderPortfolioInput) -> bool:
        if not provider.reevaluation_requested:
            return False
        corpus_changed = (
            provider.candidate_corpus_version is not None
            and provider.candidate_corpus_version != provider.last_evaluated_corpus_version
        )
        adapter_changed = (
            provider.candidate_adapter_version is not None
            and provider.candidate_adapter_version != provider.last_evaluated_adapter_version
        )
        return corpus_changed or adapter_changed
