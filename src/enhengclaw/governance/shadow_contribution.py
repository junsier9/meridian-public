from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from enhengclaw.governance.shadow_admission import ShadowAdmissionReport, ShadowAdmissionRunner, ShadowAdmissionScenario
from enhengclaw.governance.shadow_promotion import (
    RECOMMEND_LIMITED_PARTICIPATE,
    RECOMMEND_REJECT_PROVIDER,
    RECOMMEND_STAY_SHADOW_ONLY,
)


HEALTH_KEEP_SHADOW_ONLY = "keep_shadow_only"
HEALTH_PROBATION = "probation"
HEALTH_CANDIDATE_FOR_REEVALUATION = "candidate_for_re_evaluation"
HEALTH_RETIRE_PROVIDER = "retire_provider"
DEFAULT_OBSERVATION_WINDOW_SCENARIOS = 5


@dataclass(frozen=True, slots=True)
class ContributionLedgerEntry:
    provider_name: str
    category: str
    scenario: str
    subject: str
    scope: str
    candidate_status: str
    shadow_signal_count: int
    accepted_signal_count: int
    rejected_signal_count: int
    rejection_reasons: list[str]
    decision_changed: bool
    risk_state_changed: bool
    thesis_changed: bool
    allocation_changed: bool
    structural_noise: bool
    useful_risk_uplift: bool
    useful_thesis_support: bool
    decision_relevant: bool
    classification_snapshot: str
    recommendation_snapshot: str


@dataclass(frozen=True, slots=True)
class ProviderContributionSummary:
    provider_name: str
    scenario_count: int
    comparable_scenario_count: int
    shadow_signal_count: int
    signal_attempt_count: int
    accepted_signal_count: int
    rejected_signal_count: int
    acceptance_rate: float
    schema_conformance_rate: float
    data_validity_rate: float
    rejection_reason_distribution: dict[str, int]
    structural_noise_rate: float
    useful_risk_uplift_rate: float
    useful_thesis_support_rate: float
    decision_relevance_rate: float
    observation_window_size: int
    observation_window_complete: bool
    classification_snapshot: str
    recommendation_snapshot: str


@dataclass(frozen=True, slots=True)
class ProviderHealthReport:
    provider_name: str
    status: str
    reasons: list[str]


@dataclass(frozen=True, slots=True)
class ContributionLedgerReport:
    provider_name: str
    corpus_root: str
    summary: ProviderContributionSummary
    health: ProviderHealthReport
    entries: list[ContributionLedgerEntry]


class ContributionLedger:
    def __init__(
        self,
        runner: ShadowAdmissionRunner | None = None,
        *,
        provider_name: str = "real_onchain_provider_shadow",
        observation_window_size: int = DEFAULT_OBSERVATION_WINDOW_SCENARIOS,
    ) -> None:
        self.runner = runner or ShadowAdmissionRunner()
        self.provider_name = provider_name
        self.observation_window_size = observation_window_size

    def build(self) -> ContributionLedgerReport:
        return self.build_from_report(self.runner.compare_with_filter())

    def build_from_report(self, report: ShadowAdmissionReport) -> ContributionLedgerReport:
        entries = [self._entry_from_scenario(scenario, report) for scenario in report.scenarios]
        summary = self._build_summary(entries, report)
        health = self._build_health(summary)
        return ContributionLedgerReport(
            provider_name=self.provider_name,
            corpus_root=report.corpus_root,
            summary=summary,
            health=health,
            entries=entries,
        )

    def _entry_from_scenario(
        self,
        scenario: ShadowAdmissionScenario,
        report: ShadowAdmissionReport,
    ) -> ContributionLedgerEntry:
        original_diff = scenario.original.diff
        filtered_diff = scenario.filtered.diff
        shadow_signal_count = 0 if scenario.original.shadow_preview is None else scenario.original.shadow_preview.signal_count
        accepted_signal_count = len(scenario.admission.accepted_signals)
        rejected_signal_count = len(scenario.admission.rejected_signals)
        if scenario.original.candidate_status == "rejected" and rejected_signal_count == 0:
            rejection_reasons = ["candidate_batch_rejected"]
        else:
            rejection_reasons = list(scenario.admission.rejection_reasons)

        thesis_changed = False
        decision_changed = False
        risk_state_changed = False
        allocation_changed = False
        decision_relevant = False
        useful_risk_uplift = False
        useful_thesis_support = False

        if filtered_diff is not None:
            decision_changed = filtered_diff.decision_changed
            risk_state_changed = filtered_diff.risk_changed
            allocation_changed = filtered_diff.allocation_changed
            thesis_changed = (
                filtered_diff.thesis_change_type != "none"
                or filtered_diff.working_primary_changed
                or filtered_diff.working_opposing_changed
            )
            decision_relevant = decision_changed
            useful_risk_uplift = (
                accepted_signal_count > 0
                and filtered_diff.risk_changed
                and filtered_diff.risk_state_change_direction == "up"
                and scenario.filtered.candidate_if_enabled is not None
                and scenario.filtered.candidate_if_enabled.decision != "publish"
            )
            useful_thesis_support = (
                accepted_signal_count > 0
                and thesis_changed
                and not decision_changed
                and not risk_state_changed
            )

        structural_noise = False
        if original_diff is not None:
            structural_noise = (
                original_diff.material_change
                and not original_diff.decision_changed
                and not original_diff.risk_changed
                and not original_diff.processing_changed
            )

        return ContributionLedgerEntry(
            provider_name=self.provider_name,
            category=scenario.category,
            scenario=scenario.scenario,
            subject=scenario.subject,
            scope=scenario.scope,
            candidate_status=scenario.original.candidate_status,
            shadow_signal_count=shadow_signal_count,
            accepted_signal_count=accepted_signal_count,
            rejected_signal_count=rejected_signal_count,
            rejection_reasons=rejection_reasons,
            decision_changed=decision_changed,
            risk_state_changed=risk_state_changed,
            thesis_changed=thesis_changed,
            allocation_changed=allocation_changed,
            structural_noise=structural_noise,
            useful_risk_uplift=useful_risk_uplift,
            useful_thesis_support=useful_thesis_support,
            decision_relevant=decision_relevant,
            classification_snapshot=report.after.classification.classification,
            recommendation_snapshot=report.after.recommendation.recommendation,
        )

    def _build_summary(
        self,
        entries: list[ContributionLedgerEntry],
        report: ShadowAdmissionReport,
    ) -> ProviderContributionSummary:
        comparable_entries = [entry for entry in entries if entry.candidate_status == "ok"]
        total_shadow_signals = sum(entry.shadow_signal_count for entry in entries)
        signal_attempt_count = total_shadow_signals
        total_accepted = sum(entry.accepted_signal_count for entry in entries)
        total_rejected = sum(entry.rejected_signal_count for entry in entries)

        reasons = Counter[str]()
        for entry in entries:
            reasons.update(entry.rejection_reasons)

        comparable_count = len(comparable_entries)
        structural_noise_count = sum(1 for entry in comparable_entries if entry.structural_noise)
        useful_risk_uplift_count = sum(1 for entry in comparable_entries if entry.useful_risk_uplift)
        useful_thesis_support_count = sum(1 for entry in comparable_entries if entry.useful_thesis_support)
        decision_relevant_count = sum(1 for entry in comparable_entries if entry.decision_relevant)
        schema_conformance_rate = self._safe_rate(comparable_count, len(entries))
        data_validity_rate = self._safe_rate(total_accepted + total_rejected, signal_attempt_count)
        observation_window_complete = len(entries) >= self.observation_window_size

        return ProviderContributionSummary(
            provider_name=self.provider_name,
            scenario_count=len(entries),
            comparable_scenario_count=comparable_count,
            shadow_signal_count=total_shadow_signals,
            signal_attempt_count=signal_attempt_count,
            accepted_signal_count=total_accepted,
            rejected_signal_count=total_rejected,
            acceptance_rate=self._safe_rate(total_accepted, total_shadow_signals),
            schema_conformance_rate=schema_conformance_rate,
            data_validity_rate=data_validity_rate,
            rejection_reason_distribution=dict(sorted(reasons.items())),
            structural_noise_rate=self._safe_rate(structural_noise_count, comparable_count),
            useful_risk_uplift_rate=self._safe_rate(useful_risk_uplift_count, comparable_count),
            useful_thesis_support_rate=self._safe_rate(useful_thesis_support_count, comparable_count),
            decision_relevance_rate=self._safe_rate(decision_relevant_count, comparable_count),
            observation_window_size=self.observation_window_size,
            observation_window_complete=observation_window_complete,
            classification_snapshot=report.after.classification.classification,
            recommendation_snapshot=report.after.recommendation.recommendation,
        )

    def _build_health(self, summary: ProviderContributionSummary) -> ProviderHealthReport:
        reasons: list[str] = []
        if not summary.observation_window_complete:
            if summary.schema_conformance_rate < 0.5 or summary.data_validity_rate < 0.5:
                reasons.append("provider is still inside the observation window with degraded schema or data validity")
                return ProviderHealthReport(self.provider_name, HEALTH_PROBATION, reasons)
            reasons.append("provider remains under observation until the shadow window is complete")
            return ProviderHealthReport(self.provider_name, HEALTH_KEEP_SHADOW_ONLY, reasons)

        if (
            summary.recommendation_snapshot == RECOMMEND_REJECT_PROVIDER
            and summary.schema_conformance_rate < 0.5
        ):
            reasons.append("promotion policy already rejects the provider on the filtered corpus")
            return ProviderHealthReport(self.provider_name, HEALTH_RETIRE_PROVIDER, reasons)

        if (
            summary.recommendation_snapshot == RECOMMEND_LIMITED_PARTICIPATE
            and summary.structural_noise_rate <= 0.25
            and summary.acceptance_rate >= 0.5
            and summary.schema_conformance_rate >= 0.8
            and summary.data_validity_rate >= 0.8
        ):
            reasons.append("filtered corpus shows stable accepted contribution with low structural noise")
            return ProviderHealthReport(self.provider_name, HEALTH_CANDIDATE_FOR_REEVALUATION, reasons)

        if (
            summary.structural_noise_rate > 0.5
            or summary.acceptance_rate < 0.25
            or summary.schema_conformance_rate < 0.8
            or summary.data_validity_rate < 0.8
        ):
            reasons.append("provider still produces noisy or low-quality shadow observations across the full window")
            return ProviderHealthReport(self.provider_name, HEALTH_PROBATION, reasons)

        reasons.append("provider remains admissible in shadow mode but lacks enough stable decision value")
        return ProviderHealthReport(self.provider_name, HEALTH_KEEP_SHADOW_ONLY, reasons)

    def _safe_rate(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)
