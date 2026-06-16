from __future__ import annotations

from dataclasses import dataclass

from enhengclaw.adapters.adapters import AdapterBatch
from enhengclaw.core.enums import ClaimType, ObjectType
from enhengclaw.orchestration.provider_snapshot_runner import ProviderSnapshotRunRequest, ProviderSourceSpec
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.governance.shadow_promotion import (
    ImpactClassification,
    PromotionRecommendation,
    PromotionReport,
    ScenarioComparison,
    SensitivityResult,
    SensitivitySetting,
    ShadowPromotionCorpus,
    ShadowPromotionCorpusEntry,
    ShadowPromotionRunner,
    ShadowSignalPreview,
)
from enhengclaw.core.signals import Signal


@dataclass(frozen=True, slots=True)
class RejectedShadowSignal:
    signal_id: str
    predicate: str
    direction: str
    evidence_level: str
    reasons: list[str]


@dataclass(frozen=True, slots=True)
class ShadowAdmissionContext:
    category: str
    baseline: ScenarioComparison
    sensitivity_fragile: bool
    sensitivity_decision_change_count: int


@dataclass(slots=True)
class ShadowAdmissionResult:
    accepted_signals: list[Signal]
    rejected_signals: list[RejectedShadowSignal]
    rejection_reasons: list[str]


@dataclass(frozen=True, slots=True)
class ShadowAdmissionScenario:
    category: str
    scenario: str
    subject: str
    scope: str
    original: ScenarioComparison
    sensitivity_fragile: bool
    admission: ShadowAdmissionResult
    filtered: ScenarioComparison


@dataclass(frozen=True, slots=True)
class ShadowAdmissionReport:
    corpus_root: str
    before: PromotionReport
    after: PromotionReport
    scenarios: list[ShadowAdmissionScenario]


class ShadowAdmissionFilter:
    def filter_batch(
        self,
        batch: AdapterBatch,
        context: ShadowAdmissionContext,
    ) -> ShadowAdmissionResult:
        accepted: list[Signal] = []
        rejected: list[RejectedShadowSignal] = []
        reason_set: list[str] = []

        for signal in batch.signals:
            reasons: list[str] = []

            if self._is_single_source_flow_without_cross_support(batch, signal, context):
                reasons.append("single_source_onchain_flow_without_cross_support")

            if self._is_structural_noise_without_stable_edge(context):
                reasons.append("structural_change_without_stable_risk_or_thesis_edge")

            if context.sensitivity_fragile:
                reasons.append("decision_fragile_under_sensitivity_rerun")

            if self._is_known_good_structural_noise(context):
                reasons.append("known_good_structural_change_without_stable_edge")

            if reasons:
                rejected.append(
                    RejectedShadowSignal(
                        signal_id=signal.signal_id,
                        predicate=signal.predicate,
                        direction=signal.direction.value,
                        evidence_level=signal.evidence_level.value,
                        reasons=reasons,
                    )
                )
                for reason in reasons:
                    if reason not in reason_set:
                        reason_set.append(reason)
            else:
                accepted.append(signal)

        return ShadowAdmissionResult(
            accepted_signals=accepted,
            rejected_signals=rejected,
            rejection_reasons=reason_set,
        )

    def _is_single_source_flow_without_cross_support(
        self,
        batch: AdapterBatch,
        signal: Signal,
        context: ShadowAdmissionContext,
    ) -> bool:
        diff = context.baseline.diff
        if signal.claim_type != ClaimType.FLOW:
            return False
        if len(batch.signals) != 1:
            return False
        if diff is None:
            return True
        return not any(
            [
                diff.decision_changed,
                diff.risk_changed,
                diff.working_primary_changed,
                diff.working_opposing_changed,
            ]
        )

    def _is_structural_noise_without_stable_edge(self, context: ShadowAdmissionContext) -> bool:
        diff = context.baseline.diff
        if diff is None:
            return False
        return (
            diff.material_change
            and not diff.decision_changed
            and not diff.risk_changed
            and not diff.processing_changed
        )

    def _is_known_good_structural_noise(self, context: ShadowAdmissionContext) -> bool:
        diff = context.baseline.diff
        if diff is None:
            return False
        return (
            context.category == "normal"
            and diff.material_change
            and not diff.decision_changed
            and not diff.risk_changed
        )


class ShadowAdmissionRunner:
    def __init__(
        self,
        corpus: ShadowPromotionCorpus | None = None,
        *,
        filter_: ShadowAdmissionFilter | None = None,
        runner: ShadowPromotionRunner | None = None,
    ) -> None:
        self.runner = runner or ShadowPromotionRunner(corpus or ShadowPromotionCorpus())
        self.filter = filter_ or ShadowAdmissionFilter()

    def compare_with_filter(self) -> ShadowAdmissionReport:
        before = self.runner.compare_all()
        comparison_index = {(comparison.category, comparison.scenario): comparison for comparison in before.comparisons}
        scenarios: list[ShadowAdmissionScenario] = []
        for entry in self.runner.corpus.iter_entries():
            original = comparison_index[(entry.category, entry.scenario)]
            scenarios.append(self._admit_entry(entry, original))

        filtered_comparisons = [scenario.filtered for scenario in scenarios]
        filtered_metrics = self.runner.compute_metrics(filtered_comparisons)
        filtered_sensitivity = self._run_filtered_sensitivity(scenarios)
        filtered_classification = self.runner.classify_impact(filtered_metrics, filtered_sensitivity)
        filtered_recommendation = self.runner.evaluate_promotion(filtered_metrics)
        after = PromotionReport(
            corpus_root=before.corpus_root,
            scenario_count=len(filtered_comparisons),
            comparisons=filtered_comparisons,
            metrics=filtered_metrics,
            sensitivity=filtered_sensitivity,
            classification=filtered_classification,
            recommendation=filtered_recommendation,
        )
        return ShadowAdmissionReport(
            corpus_root=before.corpus_root,
            before=before,
            after=after,
            scenarios=scenarios,
        )

    def _admit_entry(
        self,
        entry: ShadowPromotionCorpusEntry,
        original: ScenarioComparison,
    ) -> ShadowAdmissionScenario:
        if original.candidate_status != "ok":
            admission = ShadowAdmissionResult(accepted_signals=[], rejected_signals=[], rejection_reasons=[])
            return ShadowAdmissionScenario(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                original=original,
                sensitivity_fragile=False,
                admission=admission,
                filtered=original,
            )

        baseline_batch = self._collect_baseline_batch(entry, object_id=f"shadow-admission:{entry.category}:{entry.scenario}")
        shadow_batch = self._collect_shadow_batch(entry, object_id=f"shadow-admission:{entry.category}:{entry.scenario}")
        sensitivity_fragile, decision_change_count = self._sensitivity_fragility(entry)
        context = ShadowAdmissionContext(
            category=entry.category,
            baseline=original,
            sensitivity_fragile=sensitivity_fragile,
            sensitivity_decision_change_count=decision_change_count,
        )
        admission = self.filter.filter_batch(shadow_batch, context)
        filtered = self._build_filtered_comparison(entry, original, baseline_batch, admission.accepted_signals)
        return ShadowAdmissionScenario(
            category=entry.category,
            scenario=entry.scenario,
            subject=entry.subject,
            scope=entry.scope,
            original=original,
            sensitivity_fragile=sensitivity_fragile,
            admission=admission,
            filtered=filtered,
        )

    def _build_filtered_comparison(
        self,
        entry: ShadowPromotionCorpusEntry,
        original: ScenarioComparison,
        baseline_batch: AdapterBatch,
        accepted_signals: list[Signal],
        setting: SensitivitySetting | None = None,
    ) -> ScenarioComparison:
        object_id = f"shadow-admission:{entry.category}:{entry.scenario}"
        execution_profile = self.runner._execution_profile(setting)  # type: ignore[attr-defined]
        orchestrator = RuntimeOrchestrator()
        baseline_result = orchestrator.run_new(
            object_id=f"{object_id}:baseline",
            object_type=entry.object_type,
            scope=entry.scope,
            signals=baseline_batch.signals,
            execution_profile=execution_profile,
        )
        baseline_summary = self.runner._summarize_runtime_result(baseline_result)  # type: ignore[attr-defined]
        if accepted_signals:
            candidate_result = orchestrator.run_new(
                object_id=f"{object_id}:candidate",
                object_type=entry.object_type,
                scope=entry.scope,
                signals=list(baseline_batch.signals) + accepted_signals,
                execution_profile=execution_profile,
            )
            candidate_summary = self.runner._summarize_runtime_result(candidate_result)  # type: ignore[attr-defined]
            diff = self.runner._diff_runtime_summaries(baseline_summary, candidate_summary)  # type: ignore[attr-defined]
            preview = self._preview_accepted_signals(accepted_signals)
            return ScenarioComparison(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                manifest_path=str(entry.manifest_path),
                baseline=baseline_summary,
                official_shadow_decision_unchanged=True,
                onchain_drift_status=original.onchain_drift_status,
                onchain_drift_summary=original.onchain_drift_summary,
                shadow_preview=preview,
                candidate_status="ok",
                candidate_error=None,
                candidate_if_enabled=candidate_summary,
                diff=diff,
            )
        return ScenarioComparison(
            category=entry.category,
            scenario=entry.scenario,
            subject=entry.subject,
            scope=entry.scope,
            manifest_path=str(entry.manifest_path),
            baseline=baseline_summary,
            official_shadow_decision_unchanged=True,
            onchain_drift_status=original.onchain_drift_status,
            onchain_drift_summary=original.onchain_drift_summary,
            shadow_preview=None,
            candidate_status="ok",
            candidate_error=None,
            candidate_if_enabled=baseline_summary,
            diff=self.runner._diff_runtime_summaries(baseline_summary, baseline_summary),  # type: ignore[attr-defined]
        )

    def _run_filtered_sensitivity(self, scenarios: list[ShadowAdmissionScenario]) -> list[SensitivityResult]:
        results: list[SensitivityResult] = []
        base_after_comparisons = [scenario.filtered for scenario in scenarios]
        base_metrics = self.runner.compute_metrics(base_after_comparisons)
        for setting in self.runner.sensitivity_settings:
            filtered_comparisons: list[ScenarioComparison] = []
            for scenario in scenarios:
                entry = next(
                    entry
                    for entry in self.runner.corpus.iter_entries()
                    if entry.category == scenario.category and entry.scenario == scenario.scenario
                )
                if scenario.original.candidate_status != "ok":
                    filtered_comparisons.append(scenario.original)
                    continue
                baseline_batch = self._collect_baseline_batch(entry, object_id=f"sensitivity-filtered:{setting.name}:{entry.category}:{entry.scenario}")
                filtered_comparisons.append(
                    self._build_filtered_comparison(
                        entry,
                        scenario.original,
                        baseline_batch,
                        scenario.admission.accepted_signals,
                        setting=setting,
                    )
                )
            metrics = self.runner.compute_metrics(filtered_comparisons)
            sudden_rise = metrics.decision_change_rate > base_metrics.decision_change_rate + 0.25
            results.append(
                SensitivityResult(
                    setting_name=setting.name,
                    attention_threshold=setting.attention_threshold,
                    extra_risk_penalty=setting.extra_risk_penalty,
                    comparable_scenarios=metrics.comparable_scenarios,
                    decision_change_rate=metrics.decision_change_rate,
                    risk_bias_rate=metrics.risk_bias_rate,
                    bullish_bias_rate=metrics.bullish_bias_rate,
                    sudden_rise=sudden_rise,
                )
            )
        return results

    def _sensitivity_fragility(self, entry: ShadowPromotionCorpusEntry) -> tuple[bool, int]:
        decision_change_count = 0
        raw = self.runner.compare_entry(entry)
        base_decision = None if raw.candidate_if_enabled is None else raw.candidate_if_enabled.decision
        for setting in self.runner.sensitivity_settings:
            comparison = self.runner._compare_entry_with_sensitivity(entry, setting)  # type: ignore[attr-defined]
            candidate_decision = None if comparison.candidate_if_enabled is None else comparison.candidate_if_enabled.decision
            if candidate_decision != base_decision:
                decision_change_count += 1
        return decision_change_count > 0, decision_change_count

    def _collect_baseline_batch(self, entry: ShadowPromotionCorpusEntry, *, object_id: str) -> AdapterBatch:
        result = self.runner.snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id=object_id,
                object_type=entry.object_type,
                subject=entry.subject,
                scope=entry.scope,
                scenario=entry.baseline_cex.scenario,
                source_specs=[
                    ProviderSourceSpec.real_cex(
                        provider_name="binance-public-cex",
                        mode="replay",
                        scenario=entry.baseline_cex.scenario,
                        raw_payload_root=entry.baseline_cex.replay_root,
                    )
                ],
            )
        )
        return result.adapter_batches[0]

    def _collect_shadow_batch(self, entry: ShadowPromotionCorpusEntry, *, object_id: str) -> AdapterBatch:
        result = self.runner.snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id=object_id,
                object_type=entry.object_type,
                subject=entry.subject,
                scope=entry.scope,
                scenario=entry.candidate_onchain.scenario,
                source_specs=[
                    ProviderSourceSpec.real_onchain(
                        provider_name="real_onchain_provider_shadow",
                        mode="replay",
                        scenario=entry.candidate_onchain.scenario,
                        raw_payload_root=entry.candidate_onchain.replay_root,
                    )
                ],
            )
        )
        return result.adapter_batches[0]

    def _preview_accepted_signals(self, signals: list[Signal]) -> ShadowSignalPreview | None:
        if not signals:
            return None
        return ShadowSignalPreview(
            adapter_name="filtered_shadow_onchain",
            signal_count=len(signals),
            signal_ids=[signal.signal_id for signal in signals],
            predicates=[signal.predicate for signal in signals],
            directions=[signal.direction.value for signal in signals],
            evidence_levels=[signal.evidence_level.value for signal in signals],
        )
