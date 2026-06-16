from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from enhengclaw.adapters.adapters import AdapterBatch
from enhengclaw.ops.drift_inspector import DriftFinding, OnchainDriftInspector, OnchainDriftReport, OnchainDriftSummary
from enhengclaw.core.enums import Direction, ObjectType, RiskState
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSnapshotRunRequest,
    ProviderSnapshotRunner,
    ProviderSourceSpec,
    load_onchain_payload_artifact,
)
from enhengclaw.orchestration.runtime_runner import RuntimeExecutionProfile
from enhengclaw.orchestration.runtime_runner import RuntimeResult


RECOMMEND_STAY_SHADOW_ONLY = "stay_shadow_only"
RECOMMEND_LIMITED_PARTICIPATE = "eligible_for_limited_participate"
RECOMMEND_REJECT_PROVIDER = "reject_provider"
CLASSIFY_NOISE = "noise"
CLASSIFY_ALPHA = "alpha"
CLASSIFY_RISK_AMPLIFIER = "risk_amplifier"


@dataclass(frozen=True, slots=True)
class ReplaySourceSpec:
    replay_root: Path
    scenario: str


@dataclass(frozen=True, slots=True)
class ShadowPromotionCorpusEntry:
    category: str
    scenario: str
    subject: str
    scope: str
    object_type: ObjectType
    baseline_cex: ReplaySourceSpec
    candidate_onchain: ReplaySourceSpec
    manifest_path: Path


class ShadowPromotionCorpus:
    def __init__(self, root: str | Path | None = None) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.root = (
            Path(root)
            if root is not None
            else self.project_root / "fixtures" / "shadow_promotion_corpus"
        )

    def iter_entries(self) -> list[ShadowPromotionCorpusEntry]:
        entries: list[ShadowPromotionCorpusEntry] = []
        if not self.root.exists():
            return entries
        for manifest_path in sorted(self.root.glob("*/*/manifest.json")):
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries.append(self._load_entry(manifest_path, data))
        return entries

    def _load_entry(self, manifest_path: Path, data: dict[str, object]) -> ShadowPromotionCorpusEntry:
        def _spec(section_name: str) -> ReplaySourceSpec:
            section = data.get(section_name)
            if not isinstance(section, dict):
                raise ValueError(f"{manifest_path} missing section '{section_name}'")
            replay_root = section.get("replay_root")
            scenario = section.get("scenario")
            if not isinstance(replay_root, str) or not replay_root.strip():
                raise ValueError(f"{manifest_path} section '{section_name}' missing replay_root")
            if not isinstance(scenario, str) or not scenario.strip():
                raise ValueError(f"{manifest_path} section '{section_name}' missing scenario")
            path = Path(replay_root)
            if not path.is_absolute():
                path = (self.project_root / path).resolve()
            return ReplaySourceSpec(replay_root=path, scenario=scenario)

        category = data.get("category")
        scenario = data.get("scenario")
        subject = data.get("subject")
        scope = data.get("scope")
        object_type = data.get("object_type", ObjectType.ASSET.value)
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"{manifest_path} missing category")
        if not isinstance(scenario, str) or not scenario.strip():
            raise ValueError(f"{manifest_path} missing scenario")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError(f"{manifest_path} missing subject")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError(f"{manifest_path} missing scope")
        return ShadowPromotionCorpusEntry(
            category=category,
            scenario=scenario,
            subject=subject,
            scope=scope,
            object_type=ObjectType(str(object_type)),
            baseline_cex=_spec("baseline_cex"),
            candidate_onchain=_spec("candidate_onchain"),
            manifest_path=manifest_path,
        )


@dataclass(frozen=True, slots=True)
class RuntimeDecisionSnapshot:
    decision: str
    risk_state: str
    processing_state: str
    attention_score: int
    working_primary_thesis_id: str | None
    working_primary_thesis_type: str | None
    working_primary_thesis_status: str | None
    working_primary_direction: str | None
    working_primary_confidence: int | None
    working_opposing_thesis_id: str | None
    working_opposing_thesis_type: str | None
    working_opposing_thesis_status: str | None
    allocation_tier: str | None
    allocation_slot: str | None


@dataclass(frozen=True, slots=True)
class ShadowSignalPreview:
    adapter_name: str
    signal_count: int
    signal_ids: list[str]
    predicates: list[str]
    directions: list[str]
    evidence_levels: list[str]


@dataclass(frozen=True, slots=True)
class DecisionDiff:
    thesis_change_type: str
    primary_direction_delta: str | None
    primary_confidence_delta: int | None
    risk_state_change_direction: str
    decision_delta: str | None
    risk_state_delta: str | None
    processing_state_delta: str | None
    working_primary_delta: str | None
    working_opposing_delta: str | None
    attention_delta: int
    allocation_delta: str | None
    decision_changed: bool
    risk_changed: bool
    processing_changed: bool
    working_primary_changed: bool
    working_opposing_changed: bool
    allocation_changed: bool
    material_change: bool


@dataclass(frozen=True, slots=True)
class ScenarioComparison:
    category: str
    scenario: str
    subject: str
    scope: str
    manifest_path: str
    baseline: RuntimeDecisionSnapshot
    official_shadow_decision_unchanged: bool
    onchain_drift_status: str
    onchain_drift_summary: dict[str, object]
    shadow_preview: ShadowSignalPreview | None
    candidate_status: str
    candidate_error: str | None
    candidate_if_enabled: RuntimeDecisionSnapshot | None
    diff: DecisionDiff | None


@dataclass(frozen=True, slots=True)
class PromotionMetrics:
    total_scenarios: int
    comparable_scenarios: int
    candidate_rejected_count: int
    decision_change_rate: float
    material_change_rate: float
    publish_to_monitoring_count: int
    monitoring_to_blocked_count: int
    publish_to_blocked_count: int
    risk_state_uplift_frequency: float
    thesis_replacement_frequency: float
    no_op_consistency_rate: float
    known_bad_rejection_rate: float
    known_bad_accepted_count: int
    positive_edge_risk_uplift_count: int
    risk_bias_rate: float
    bullish_bias_rate: float
    thesis_flip_rate: float
    no_op_structural_change_rate: float


@dataclass(frozen=True, slots=True)
class SensitivitySetting:
    name: str
    attention_threshold: int
    extra_risk_penalty: int = 0


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    setting_name: str
    attention_threshold: int
    extra_risk_penalty: int
    comparable_scenarios: int
    decision_change_rate: float
    risk_bias_rate: float
    bullish_bias_rate: float
    sudden_rise: bool


@dataclass(frozen=True, slots=True)
class ImpactClassification:
    classification: str
    reasons: list[str]


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    max_material_change_rate: float = 0.60
    max_decision_change_rate: float = 0.20
    min_noop_consistency_rate: float = 0.40
    min_positive_edge_risk_uplifts: int = 1


@dataclass(frozen=True, slots=True)
class PromotionRecommendation:
    recommendation: str
    reasons: list[str]


@dataclass(frozen=True, slots=True)
class PromotionReport:
    corpus_root: str
    scenario_count: int
    comparisons: list[ScenarioComparison]
    metrics: PromotionMetrics
    sensitivity: list[SensitivityResult]
    classification: ImpactClassification
    recommendation: PromotionRecommendation


class ShadowPromotionRunner:
    def __init__(
        self,
        corpus: ShadowPromotionCorpus | None = None,
        *,
        policy: PromotionPolicy | None = None,
        snapshot_runner: ProviderSnapshotRunner | None = None,
    ) -> None:
        self.corpus = corpus or ShadowPromotionCorpus()
        self.policy = policy or PromotionPolicy()
        self.snapshot_runner = snapshot_runner or ProviderSnapshotRunner()
        self.onchain_drift_inspector = OnchainDriftInspector()
        self.sensitivity_settings = [
            SensitivitySetting(name="relaxed_attention_threshold", attention_threshold=65, extra_risk_penalty=0),
            SensitivitySetting(name="extra_risk_penalty", attention_threshold=70, extra_risk_penalty=4),
        ]

    def compare_all(self) -> PromotionReport:
        entries = self.corpus.iter_entries()
        comparisons = [self.compare_entry(entry) for entry in entries]
        metrics = self.compute_metrics(comparisons)
        sensitivity = self.run_sensitivity(entries, base_decision_change_rate=metrics.decision_change_rate)
        classification = self.classify_impact(metrics, sensitivity)
        recommendation = self.evaluate_promotion(metrics)
        return PromotionReport(
            corpus_root=str(self.corpus.root),
            scenario_count=len(comparisons),
            comparisons=comparisons,
            metrics=metrics,
            sensitivity=sensitivity,
            classification=classification,
            recommendation=recommendation,
        )

    def compare_entry(self, entry: ShadowPromotionCorpusEntry) -> ScenarioComparison:
        object_id = f"shadow-promotion:{entry.category}:{entry.scenario}"
        baseline_source = ProviderSourceSpec.real_cex(
            provider_name="binance-public-cex",
            mode="replay",
            scenario=entry.baseline_cex.scenario,
            raw_payload_root=entry.baseline_cex.replay_root,
        )
        onchain_source = ProviderSourceSpec.real_onchain(
            provider_name="real_onchain_provider_shadow",
            mode="replay",
            scenario=entry.candidate_onchain.scenario,
            raw_payload_root=entry.candidate_onchain.replay_root,
        )
        baseline_run = self.snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id=object_id,
                object_type=entry.object_type,
                subject=entry.subject,
                scope=entry.scope,
                scenario=entry.baseline_cex.scenario,
                source_specs=[baseline_source],
            )
        )
        baseline_batch = baseline_run.adapter_batches[0]
        baseline_summary = self._summarize_runtime_result(baseline_run.runtime_result)

        try:
            onchain_path = self.snapshot_runner.run_once(
                ProviderSnapshotRunRequest(
                    object_id=f"{object_id}:shadow-preview",
                    object_type=entry.object_type,
                    subject=entry.subject,
                    scope=entry.scope,
                    scenario=entry.candidate_onchain.scenario,
                    source_specs=[onchain_source],
                )
            ).source_artifact_paths.get(onchain_source.provider_name)
            if onchain_path is None:
                raise ValueError("onchain source lane did not produce a raw payload artifact")
            onchain_payload = load_onchain_payload_artifact(onchain_path)
            drift_report = self.onchain_drift_inspector.inspect(onchain_payload)
        except Exception as exc:
            drift_report = OnchainDriftReport(
                status="error",
                summary=OnchainDriftSummary(
                    row_keys=[],
                    row_count=0,
                    raw_http_present=False,
                    metadata_provider_matches=False,
                    metadata_record_count_matches=False,
                    metadata_timestamp_matches=False,
                ),
                findings=[DriftFinding("error", "provider_fetch_failed", str(exc))],
            )
            return ScenarioComparison(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                manifest_path=str(entry.manifest_path),
                baseline=baseline_summary,
                official_shadow_decision_unchanged=True,
                onchain_drift_status=drift_report.status,
                onchain_drift_summary=self._drift_summary_dict(drift_report),
                shadow_preview=None,
                candidate_status="rejected",
                candidate_error=str(exc),
                candidate_if_enabled=None,
                diff=None,
            )

        try:
            candidate_run = self.snapshot_runner.run_once(
                ProviderSnapshotRunRequest(
                    object_id=object_id,
                    object_type=entry.object_type,
                    subject=entry.subject,
                    scope=entry.scope,
                    scenario=entry.candidate_onchain.scenario,
                    source_specs=[baseline_source, onchain_source],
                )
            )
            shadow_batch = candidate_run.adapter_batches[-1]
            candidate_summary = self._summarize_runtime_result(candidate_run.runtime_result)
            diff = self._diff_runtime_summaries(baseline_summary, candidate_summary)
            return ScenarioComparison(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                manifest_path=str(entry.manifest_path),
                baseline=baseline_summary,
                official_shadow_decision_unchanged=True,
                onchain_drift_status=drift_report.status,
                onchain_drift_summary=self._drift_summary_dict(drift_report),
                shadow_preview=self._shadow_preview(shadow_batch),
                candidate_status="ok",
                candidate_error=None,
                candidate_if_enabled=candidate_summary,
                diff=diff,
            )
        except Exception as exc:
            return ScenarioComparison(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                manifest_path=str(entry.manifest_path),
                baseline=baseline_summary,
                official_shadow_decision_unchanged=True,
                onchain_drift_status=drift_report.status,
                onchain_drift_summary=self._drift_summary_dict(drift_report),
                shadow_preview=None,
                candidate_status="rejected",
                candidate_error=str(exc),
                candidate_if_enabled=None,
                diff=None,
            )

    def compute_metrics(self, comparisons: list[ScenarioComparison]) -> PromotionMetrics:
        comparable = [comparison for comparison in comparisons if comparison.candidate_status == "ok" and comparison.diff is not None]
        known_bad = [comparison for comparison in comparisons if comparison.category == "known_bad"]
        decision_changes = sum(1 for comparison in comparable if comparison.diff and comparison.diff.decision_changed)
        material_changes = sum(1 for comparison in comparable if comparison.diff and comparison.diff.material_change)
        publish_to_monitoring = sum(
            1
            for comparison in comparable
            if comparison.baseline.decision == "publish" and comparison.candidate_if_enabled and comparison.candidate_if_enabled.decision == "monitoring"
        )
        monitoring_to_blocked = sum(
            1
            for comparison in comparable
            if comparison.baseline.decision == "monitoring" and comparison.candidate_if_enabled and comparison.candidate_if_enabled.decision == "blocked"
        )
        publish_to_blocked = sum(
            1
            for comparison in comparable
            if comparison.baseline.decision == "publish" and comparison.candidate_if_enabled and comparison.candidate_if_enabled.decision == "blocked"
        )
        risk_uplifts = sum(
            1
            for comparison in comparable
            if comparison.candidate_if_enabled and self._risk_rank(comparison.candidate_if_enabled.risk_state) > self._risk_rank(comparison.baseline.risk_state)
        )
        thesis_replacements = sum(
            1
            for comparison in comparable
            if comparison.diff and (comparison.diff.working_primary_changed or comparison.diff.working_opposing_changed)
        )
        no_ops = sum(1 for comparison in comparable if comparison.diff and not comparison.diff.material_change)
        known_bad_rejections = sum(1 for comparison in known_bad if comparison.candidate_status == "rejected")
        known_bad_accepted = sum(1 for comparison in known_bad if comparison.candidate_status == "ok")
        positive_edge_risk_uplifts = sum(
            1
            for comparison in comparable
            if comparison.category in {"edge", "known_bad"}
            and comparison.candidate_if_enabled is not None
            and self._risk_rank(comparison.candidate_if_enabled.risk_state) > self._risk_rank(comparison.baseline.risk_state)
            and comparison.candidate_if_enabled.decision != "publish"
        )
        risk_bias_count = sum(
            1
            for comparison in comparable
            if comparison.diff and comparison.diff.risk_state_change_direction == "up"
        )
        bullish_bias_count = sum(
            1
            for comparison in comparable
            if comparison.diff and comparison.diff.primary_direction_delta is not None and comparison.diff.primary_direction_delta.endswith("->bullish")
        )
        thesis_flip_count = sum(
            1
            for comparison in comparable
            if comparison.diff and comparison.diff.working_primary_changed
        )
        no_op_structural_count = sum(
            1
            for comparison in comparable
            if comparison.diff
            and not comparison.diff.decision_changed
            and not comparison.diff.risk_changed
            and not comparison.diff.processing_changed
            and (comparison.diff.working_primary_changed or comparison.diff.working_opposing_changed or comparison.diff.allocation_changed)
        )
        comparable_count = len(comparable)
        known_bad_count = len(known_bad)
        return PromotionMetrics(
            total_scenarios=len(comparisons),
            comparable_scenarios=comparable_count,
            candidate_rejected_count=sum(1 for comparison in comparisons if comparison.candidate_status == "rejected"),
            decision_change_rate=self._safe_rate(decision_changes, comparable_count),
            material_change_rate=self._safe_rate(material_changes, comparable_count),
            publish_to_monitoring_count=publish_to_monitoring,
            monitoring_to_blocked_count=monitoring_to_blocked,
            publish_to_blocked_count=publish_to_blocked,
            risk_state_uplift_frequency=self._safe_rate(risk_uplifts, comparable_count),
            thesis_replacement_frequency=self._safe_rate(thesis_replacements, comparable_count),
            no_op_consistency_rate=self._safe_rate(no_ops, comparable_count),
            known_bad_rejection_rate=self._safe_rate(known_bad_rejections, known_bad_count),
            known_bad_accepted_count=known_bad_accepted,
            positive_edge_risk_uplift_count=positive_edge_risk_uplifts,
            risk_bias_rate=self._safe_rate(risk_bias_count, comparable_count),
            bullish_bias_rate=self._safe_rate(bullish_bias_count, comparable_count),
            thesis_flip_rate=self._safe_rate(thesis_flip_count, comparable_count),
            no_op_structural_change_rate=self._safe_rate(no_op_structural_count, comparable_count),
        )

    def run_sensitivity(
        self,
        entries: list[ShadowPromotionCorpusEntry],
        *,
        base_decision_change_rate: float,
    ) -> list[SensitivityResult]:
        results: list[SensitivityResult] = []
        for setting in self.sensitivity_settings:
            comparisons: list[ScenarioComparison] = []
            for entry in entries:
                comparisons.append(self._compare_entry_with_sensitivity(entry, setting))
            metrics = self.compute_metrics(comparisons)
            sudden_rise = metrics.decision_change_rate > base_decision_change_rate + 0.25
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

    def classify_impact(
        self,
        metrics: PromotionMetrics,
        sensitivity: list[SensitivityResult],
    ) -> ImpactClassification:
        reasons: list[str] = []
        if metrics.risk_bias_rate >= 0.25 or any(result.risk_bias_rate >= 0.25 for result in sensitivity):
            reasons.append("candidate frequently uplifts risk_state under baseline or sensitivity runs")
            return ImpactClassification(CLASSIFY_RISK_AMPLIFIER, reasons)
        if (
            metrics.bullish_bias_rate >= 0.5
            and metrics.no_op_structural_change_rate <= 0.25
            and all(not result.sudden_rise for result in sensitivity)
        ):
            reasons.append("candidate consistently strengthens bullish thesis without unstable sensitivity spikes")
            return ImpactClassification(CLASSIFY_ALPHA, reasons)
        reasons.append("candidate mostly changes structure/attention without stable decision edge or risk uplift")
        return ImpactClassification(CLASSIFY_NOISE, reasons)

    def evaluate_promotion(self, metrics: PromotionMetrics) -> PromotionRecommendation:
        reasons: list[str] = []
        if metrics.known_bad_accepted_count > 0:
            reasons.append("known-bad corpus payloads were accepted into candidate comparison")
            return PromotionRecommendation(RECOMMEND_REJECT_PROVIDER, reasons)
        if metrics.publish_to_monitoring_count > 0 or metrics.publish_to_blocked_count > 0:
            reasons.append("known-good publishable baselines were regressed by the candidate provider")
            return PromotionRecommendation(RECOMMEND_REJECT_PROVIDER, reasons)
        if metrics.material_change_rate > self.policy.max_material_change_rate:
            reasons.append(
                f"material change rate {metrics.material_change_rate:.2f} exceeds threshold {self.policy.max_material_change_rate:.2f}"
            )
            return PromotionRecommendation(RECOMMEND_STAY_SHADOW_ONLY, reasons)
        if metrics.decision_change_rate > self.policy.max_decision_change_rate:
            reasons.append(
                f"decision change rate {metrics.decision_change_rate:.2f} exceeds threshold {self.policy.max_decision_change_rate:.2f}"
            )
            return PromotionRecommendation(RECOMMEND_STAY_SHADOW_ONLY, reasons)
        if metrics.no_op_consistency_rate < self.policy.min_noop_consistency_rate:
            reasons.append(
                f"no-op consistency rate {metrics.no_op_consistency_rate:.2f} is below threshold {self.policy.min_noop_consistency_rate:.2f}"
            )
            return PromotionRecommendation(RECOMMEND_STAY_SHADOW_ONLY, reasons)
        if metrics.positive_edge_risk_uplift_count >= self.policy.min_positive_edge_risk_uplifts:
            reasons.append("edge/known-bad corpus produced safe risk uplifts without mispublish")
            return PromotionRecommendation(RECOMMEND_LIMITED_PARTICIPATE, reasons)
        reasons.append("candidate remains stable but lacks enough positive corpus evidence for promotion")
        return PromotionRecommendation(RECOMMEND_STAY_SHADOW_ONLY, reasons)

    def _summarize_runtime_result(self, result: RuntimeResult) -> RuntimeDecisionSnapshot:
        thesis_index = {thesis.thesis_id: thesis for thesis in result.theses}
        primary = thesis_index.get(result.research_object.working_primary_thesis_id)
        opposing = thesis_index.get(result.research_object.working_opposing_thesis_id)
        allocation = result.resource_allocation
        return RuntimeDecisionSnapshot(
            decision=result.decision.decision,
            risk_state=result.research_object.risk_state.value,
            processing_state=result.research_object.processing_state.value,
            attention_score=result.research_object.attention_score,
            working_primary_thesis_id=result.research_object.working_primary_thesis_id,
            working_primary_thesis_type=None if primary is None else primary.thesis_type.value,
            working_primary_thesis_status=None if primary is None else primary.status.value,
            working_primary_direction=None if primary is None else primary.direction.value,
            working_primary_confidence=None if primary is None else primary.confidence,
            working_opposing_thesis_id=result.research_object.working_opposing_thesis_id,
            working_opposing_thesis_type=None if opposing is None else opposing.thesis_type.value,
            working_opposing_thesis_status=None if opposing is None else opposing.status.value,
            allocation_tier=None if allocation is None else allocation.tier.value,
            allocation_slot=None if allocation is None else allocation.slot_type.value,
        )

    def _shadow_preview(self, batch: AdapterBatch) -> ShadowSignalPreview:
        return ShadowSignalPreview(
            adapter_name=batch.adapter_name,
            signal_count=len(batch.signals),
            signal_ids=[signal.signal_id for signal in batch.signals],
            predicates=[signal.predicate for signal in batch.signals],
            directions=[signal.direction.value for signal in batch.signals],
            evidence_levels=[signal.evidence_level.value for signal in batch.signals],
        )

    def _drift_summary_dict(self, report: OnchainDriftReport) -> dict[str, object]:
        summary = asdict(report.summary)
        summary["finding_count"] = len(report.findings)
        return summary

    def _diff_runtime_summaries(
        self,
        baseline: RuntimeDecisionSnapshot,
        candidate: RuntimeDecisionSnapshot,
    ) -> DecisionDiff:
        primary_direction_delta = None if baseline.working_primary_direction == candidate.working_primary_direction else f"{baseline.working_primary_direction or 'none'}->{candidate.working_primary_direction or 'none'}"
        primary_confidence_delta = None
        if baseline.working_primary_confidence != candidate.working_primary_confidence:
            left = 0 if baseline.working_primary_confidence is None else baseline.working_primary_confidence
            right = 0 if candidate.working_primary_confidence is None else candidate.working_primary_confidence
            primary_confidence_delta = right - left
        decision_delta = None if baseline.decision == candidate.decision else f"{baseline.decision}->{candidate.decision}"
        risk_delta = None if baseline.risk_state == candidate.risk_state else f"{baseline.risk_state}->{candidate.risk_state}"
        processing_delta = (
            None if baseline.processing_state == candidate.processing_state else f"{baseline.processing_state}->{candidate.processing_state}"
        )
        primary_delta = self._thesis_delta(
            baseline.working_primary_thesis_id,
            baseline.working_primary_thesis_type,
            baseline.working_primary_thesis_status,
            candidate.working_primary_thesis_id,
            candidate.working_primary_thesis_type,
            candidate.working_primary_thesis_status,
        )
        opposing_delta = self._thesis_delta(
            baseline.working_opposing_thesis_id,
            baseline.working_opposing_thesis_type,
            baseline.working_opposing_thesis_status,
            candidate.working_opposing_thesis_id,
            candidate.working_opposing_thesis_type,
            candidate.working_opposing_thesis_status,
        )
        allocation_left = f"{baseline.allocation_tier}:{baseline.allocation_slot}"
        allocation_right = f"{candidate.allocation_tier}:{candidate.allocation_slot}"
        allocation_delta = None if allocation_left == allocation_right else f"{allocation_left}->{allocation_right}"
        risk_state_change_direction = self._risk_change_direction(baseline.risk_state, candidate.risk_state)
        thesis_change_type = self._thesis_change_type(
            baseline,
            candidate,
            primary_delta,
            primary_direction_delta,
            primary_confidence_delta,
        )
        decision_changed = decision_delta is not None
        risk_changed = risk_delta is not None
        processing_changed = processing_delta is not None
        working_primary_changed = primary_delta is not None
        working_opposing_changed = opposing_delta is not None
        allocation_changed = allocation_delta is not None
        material_change = any(
            [
                decision_changed,
                risk_changed,
                processing_changed,
                working_primary_changed,
                working_opposing_changed,
                allocation_changed,
            ]
        )
        return DecisionDiff(
            thesis_change_type=thesis_change_type,
            primary_direction_delta=primary_direction_delta,
            primary_confidence_delta=primary_confidence_delta,
            risk_state_change_direction=risk_state_change_direction,
            decision_delta=decision_delta,
            risk_state_delta=risk_delta,
            processing_state_delta=processing_delta,
            working_primary_delta=primary_delta,
            working_opposing_delta=opposing_delta,
            attention_delta=candidate.attention_score - baseline.attention_score,
            allocation_delta=allocation_delta,
            decision_changed=decision_changed,
            risk_changed=risk_changed,
            processing_changed=processing_changed,
            working_primary_changed=working_primary_changed,
            working_opposing_changed=working_opposing_changed,
            allocation_changed=allocation_changed,
            material_change=material_change,
        )

    def _thesis_delta(
        self,
        before_id: str | None,
        before_type: str | None,
        before_status: str | None,
        after_id: str | None,
        after_type: str | None,
        after_status: str | None,
    ) -> str | None:
        left = self._thesis_signature(before_id, before_type, before_status)
        right = self._thesis_signature(after_id, after_type, after_status)
        if left == right:
            return None
        return f"{left}->{right}"

    def _thesis_signature(self, thesis_id: str | None, thesis_type: str | None, thesis_status: str | None) -> str:
        return f"{thesis_id or 'none'}|{thesis_type or 'none'}|{thesis_status or 'none'}"

    def _thesis_change_type(
        self,
        baseline: RuntimeDecisionSnapshot,
        candidate: RuntimeDecisionSnapshot,
        primary_delta: str | None,
        primary_direction_delta: str | None,
        primary_confidence_delta: int | None,
    ) -> str:
        if primary_delta is None and primary_direction_delta is None and primary_confidence_delta is None:
            return "none"
        if baseline.working_primary_thesis_id is None and candidate.working_primary_thesis_id is not None:
            return "primary_created"
        if baseline.working_primary_thesis_id is not None and candidate.working_primary_thesis_id is None:
            return "primary_removed"
        if primary_delta is not None and baseline.working_primary_thesis_id != candidate.working_primary_thesis_id:
            return "primary_replaced"
        if primary_direction_delta is not None:
            return "direction_shift"
        if primary_confidence_delta is not None:
            return "confidence_shift"
        return "structural_shift"

    def _risk_change_direction(self, before: str, after: str) -> str:
        left = self._risk_rank(before)
        right = self._risk_rank(after)
        if right > left:
            return "up"
        if right < left:
            return "down"
        return "unchanged"

    def _execution_profile(self, setting: SensitivitySetting | None = None) -> RuntimeExecutionProfile | None:
        if setting is None:
            return None
        return RuntimeExecutionProfile(
            attention_threshold=setting.attention_threshold,
            extra_risk_penalty=setting.extra_risk_penalty,
        )

    def _compare_entry_with_sensitivity(
        self,
        entry: ShadowPromotionCorpusEntry,
        setting: SensitivitySetting,
    ) -> ScenarioComparison:
        object_id = f"sensitivity:{setting.name}:{entry.category}:{entry.scenario}"
        execution_profile = self._execution_profile(setting)
        baseline_source = ProviderSourceSpec.real_cex(
            provider_name="binance-public-cex",
            mode="replay",
            scenario=entry.baseline_cex.scenario,
            raw_payload_root=entry.baseline_cex.replay_root,
        )
        onchain_source = ProviderSourceSpec.real_onchain(
            provider_name="real_onchain_provider_shadow",
            mode="replay",
            scenario=entry.candidate_onchain.scenario,
            raw_payload_root=entry.candidate_onchain.replay_root,
        )
        baseline_run = self.snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id=object_id,
                object_type=entry.object_type,
                subject=entry.subject,
                scope=entry.scope,
                scenario=entry.baseline_cex.scenario,
                source_specs=[baseline_source],
                execution_profile=execution_profile,
            )
        )
        baseline_batch = baseline_run.adapter_batches[0]
        baseline_summary = self._summarize_runtime_result(baseline_run.runtime_result)

        try:
            preview_run = self.snapshot_runner.run_once(
                ProviderSnapshotRunRequest(
                    object_id=f"{object_id}:shadow-preview",
                    object_type=entry.object_type,
                    subject=entry.subject,
                    scope=entry.scope,
                    scenario=entry.candidate_onchain.scenario,
                    source_specs=[onchain_source],
                    execution_profile=execution_profile,
                )
            )
            onchain_path = preview_run.source_artifact_paths.get(onchain_source.provider_name)
            if onchain_path is None:
                raise ValueError("onchain source lane did not produce a raw payload artifact")
            onchain_payload = load_onchain_payload_artifact(onchain_path)
            drift_report = self.onchain_drift_inspector.inspect(onchain_payload)
            candidate_run = self.snapshot_runner.run_once(
                ProviderSnapshotRunRequest(
                    object_id=object_id,
                    object_type=entry.object_type,
                    subject=entry.subject,
                    scope=entry.scope,
                    scenario=entry.candidate_onchain.scenario,
                    source_specs=[baseline_source, onchain_source],
                    execution_profile=execution_profile,
                )
            )
            shadow_batch = candidate_run.adapter_batches[-1]
            candidate_summary = self._summarize_runtime_result(candidate_run.runtime_result)
            diff = self._diff_runtime_summaries(baseline_summary, candidate_summary)
            return ScenarioComparison(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                manifest_path=str(entry.manifest_path),
                baseline=baseline_summary,
                official_shadow_decision_unchanged=True,
                onchain_drift_status=drift_report.status,
                onchain_drift_summary=self._drift_summary_dict(drift_report),
                shadow_preview=self._shadow_preview(shadow_batch),
                candidate_status="ok",
                candidate_error=None,
                candidate_if_enabled=candidate_summary,
                diff=diff,
            )
        except Exception as exc:
            return ScenarioComparison(
                category=entry.category,
                scenario=entry.scenario,
                subject=entry.subject,
                scope=entry.scope,
                manifest_path=str(entry.manifest_path),
                baseline=baseline_summary,
                official_shadow_decision_unchanged=True,
                onchain_drift_status="error",
                onchain_drift_summary={},
                shadow_preview=None,
                candidate_status="rejected",
                candidate_error=str(exc),
                candidate_if_enabled=None,
                diff=None,
            )

    def _risk_rank(self, risk_state: str) -> int:
        return {
            RiskState.NORMAL.value: 0,
            RiskState.CAUTION.value: 1,
            RiskState.RESTRICTED.value: 2,
            RiskState.BLOCKED.value: 3,
        }[risk_state]

    def _safe_rate(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)
