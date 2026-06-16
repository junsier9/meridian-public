from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_PROBATION,
    STATUS_RETIRED,
    STATUS_SHADOW_DEGRADED,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.shadow_contribution import (
    ContributionLedgerReport,
    HEALTH_CANDIDATE_FOR_REEVALUATION,
    HEALTH_KEEP_SHADOW_ONLY,
    ProviderContributionSummary,
    ProviderHealthReport,
)
from enhengclaw.governance.shadow_promotion import (
    CLASSIFY_ALPHA,
    CLASSIFY_NOISE,
    ImpactClassification,
    PromotionMetrics,
    PromotionRecommendation,
    PromotionReport,
    RECOMMEND_LIMITED_PARTICIPATE,
    RECOMMEND_STAY_SHADOW_ONLY,
    ShadowPromotionRunner,
)
from tests.test_helpers import enter_runtime_worker_class


class ProviderPortfolioPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from enhengclaw.governance.shadow_contribution import ContributionLedger

        enter_runtime_worker_class(cls, slug="test-provider-portfolio")
        cls._shadow_inputs = (
            ContributionLedger().build(),
            ShadowPromotionRunner().compare_all(),
        )

    def _shadow_report_inputs(self) -> tuple[ContributionLedgerReport, PromotionReport]:
        return self._shadow_inputs

    def _good_contribution_report(self) -> ContributionLedgerReport:
        return ContributionLedgerReport(
            provider_name="candidate-shadow-provider",
            corpus_root=str(ROOT / "fixtures" / "shadow_promotion_corpus"),
            summary=ProviderContributionSummary(
                provider_name="candidate-shadow-provider",
                scenario_count=4,
                comparable_scenario_count=4,
                shadow_signal_count=4,
                signal_attempt_count=4,
                accepted_signal_count=3,
                rejected_signal_count=1,
                acceptance_rate=0.75,
                schema_conformance_rate=1.0,
                data_validity_rate=1.0,
                rejection_reason_distribution={"single_source_onchain_flow_without_cross_support": 1},
                structural_noise_rate=0.0,
                useful_risk_uplift_rate=0.25,
                useful_thesis_support_rate=0.5,
                decision_relevance_rate=0.25,
                observation_window_size=4,
                observation_window_complete=True,
                classification_snapshot=CLASSIFY_ALPHA,
                recommendation_snapshot=RECOMMEND_LIMITED_PARTICIPATE,
            ),
            health=ProviderHealthReport(
                provider_name="candidate-shadow-provider",
                status=HEALTH_CANDIDATE_FOR_REEVALUATION,
                reasons=["shadow corpus shows stable accepted contribution"],
            ),
            entries=[],
        )

    def _good_promotion_report(self) -> PromotionReport:
        metrics = PromotionMetrics(
            total_scenarios=4,
            comparable_scenarios=4,
            candidate_rejected_count=0,
            decision_change_rate=0.0,
            material_change_rate=0.25,
            publish_to_monitoring_count=0,
            monitoring_to_blocked_count=0,
            publish_to_blocked_count=0,
            risk_state_uplift_frequency=0.25,
            thesis_replacement_frequency=0.25,
            no_op_consistency_rate=0.75,
            known_bad_rejection_rate=1.0,
            known_bad_accepted_count=0,
            positive_edge_risk_uplift_count=1,
            risk_bias_rate=0.0,
            bullish_bias_rate=0.5,
            thesis_flip_rate=0.25,
            no_op_structural_change_rate=0.0,
        )
        return PromotionReport(
            corpus_root=str(ROOT / "fixtures" / "shadow_promotion_corpus"),
            scenario_count=4,
            comparisons=[],
            metrics=metrics,
            sensitivity=[],
            classification=ImpactClassification(CLASSIFY_ALPHA, ["stable positive contribution"]),
            recommendation=PromotionRecommendation(
                RECOMMEND_LIMITED_PARTICIPATE,
                ["positive edge corpus produced safe uplifts"],
            ),
        )

    def test_retired_provider_is_not_default_selected_by_runtime(self) -> None:
        ledger, promotion = self._shadow_report_inputs()
        policy = ProviderPortfolioPolicy()
        report = policy.evaluate_all(
            [
                ProviderPortfolioInput(
                    provider_name="real_onchain_provider_shadow",
                    provider_type="onchain",
                    current_status=STATUS_SHADOW_ONLY,
                    contribution_ledger=ledger,
                    promotion_report=promotion,
                    drift_snapshot=ProviderDriftSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        status="warning",
                        finding_count=1,
                        error_count=0,
                        warning_count=1,
                    ),
                    chaos_snapshot=ProviderChaosSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        passed=True,
                        scenario_count=5,
                        notes=["shadow regressions green"],
                    ),
                )
            ]
        )

        self.assertEqual(report.default_runtime_provider_names, [])
        self.assertEqual(report.entries[0].portfolio_status, STATUS_SHADOW_DEGRADED)

    def test_active_provider_is_not_affected_by_retired_provider(self) -> None:
        ledger, promotion = self._shadow_report_inputs()
        policy = ProviderPortfolioPolicy()
        report = policy.evaluate_all(
            [
                ProviderPortfolioInput(
                    provider_name="binance-public-cex",
                    provider_type="cex",
                    current_status=STATUS_ACTIVE,
                    contribution_ledger=None,
                    promotion_report=None,
                    drift_snapshot=ProviderDriftSnapshot(
                        provider_name="binance-public-cex",
                        status="ok",
                        finding_count=0,
                        error_count=0,
                        warning_count=0,
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
                    contribution_ledger=ledger,
                    promotion_report=promotion,
                    drift_snapshot=ProviderDriftSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        status="warning",
                        finding_count=1,
                        error_count=0,
                        warning_count=1,
                    ),
                    chaos_snapshot=ProviderChaosSnapshot(
                        provider_name="real_onchain_provider_shadow",
                        passed=True,
                        scenario_count=5,
                        notes=["shadow regressions green"],
                    ),
                ),
            ]
        )

        entries = {entry.provider_name: entry for entry in report.entries}
        self.assertEqual(entries["binance-public-cex"].portfolio_status, STATUS_PRODUCTION)
        self.assertEqual(entries["real_onchain_provider_shadow"].portfolio_status, STATUS_SHADOW_DEGRADED)
        self.assertEqual(report.default_runtime_provider_names, ["binance-public-cex"])

    def test_policy_keeps_zero_accepted_shadow_provider_under_observation(self) -> None:
        ledger, promotion = self._shadow_report_inputs()
        policy = ProviderPortfolioPolicy()
        entry = policy.evaluate_provider(
            ProviderPortfolioInput(
                provider_name="real_onchain_provider_shadow",
                provider_type="onchain",
                current_status=STATUS_SHADOW_ONLY,
                contribution_ledger=ledger,
                promotion_report=promotion,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    status="warning",
                    finding_count=1,
                    error_count=0,
                    warning_count=1,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    passed=True,
                    scenario_count=5,
                    notes=["shadow regressions green"],
                ),
            )
        )

        self.assertIn(ledger.health.status, {HEALTH_KEEP_SHADOW_ONLY, "probation"})
        self.assertEqual(promotion.recommendation.recommendation, RECOMMEND_STAY_SHADOW_ONLY)
        self.assertEqual(entry.portfolio_status, STATUS_SHADOW_DEGRADED)
        self.assertTrue(entry.status_changed)
        self.assertIn("degraded", entry.reasons[0])

    def test_retired_provider_requires_explicit_reevaluation_and_does_not_auto_revive(self) -> None:
        policy = ProviderPortfolioPolicy()
        provider = ProviderPortfolioInput(
            provider_name="candidate-shadow-provider",
            provider_type="onchain",
            current_status=STATUS_RETIRED,
            contribution_ledger=self._good_contribution_report(),
            promotion_report=self._good_promotion_report(),
            drift_snapshot=ProviderDriftSnapshot(
                provider_name="candidate-shadow-provider",
                status="ok",
                finding_count=0,
                error_count=0,
                warning_count=0,
            ),
            chaos_snapshot=ProviderChaosSnapshot(
                provider_name="candidate-shadow-provider",
                passed=True,
                scenario_count=6,
                notes=["synthetic shadow regressions green"],
            ),
            last_evaluated_corpus_version="v1",
            last_evaluated_adapter_version="a1",
            candidate_corpus_version="v1",
            candidate_adapter_version="a1",
        )
        entry = policy.evaluate_provider(provider)
        self.assertEqual(entry.portfolio_status, STATUS_RETIRED)
        self.assertIn("explicit reevaluation", entry.reasons[0])

    def test_explicit_new_corpus_and_positive_metrics_can_move_shadow_provider_to_probation(self) -> None:
        policy = ProviderPortfolioPolicy()
        entry = policy.evaluate_provider(
            ProviderPortfolioInput(
                provider_name="candidate-shadow-provider",
                provider_type="onchain",
                current_status=STATUS_RETIRED,
                contribution_ledger=self._good_contribution_report(),
                promotion_report=self._good_promotion_report(),
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="candidate-shadow-provider",
                    status="ok",
                    finding_count=0,
                    error_count=0,
                    warning_count=0,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="candidate-shadow-provider",
                    passed=True,
                    scenario_count=6,
                    notes=["synthetic shadow regressions green"],
                ),
                reevaluation_requested=True,
                last_evaluated_corpus_version="v1",
                last_evaluated_adapter_version="a1",
                candidate_corpus_version="v2",
                candidate_adapter_version="a1",
            )
        )

        self.assertEqual(entry.portfolio_status, STATUS_PROBATION)
        self.assertIn("positive", entry.reasons[0])

    def test_incomplete_observation_window_cannot_promote_provider(self) -> None:
        policy = ProviderPortfolioPolicy()
        incomplete_summary = ProviderContributionSummary(
            provider_name="candidate-shadow-provider",
            scenario_count=2,
            comparable_scenario_count=2,
            shadow_signal_count=3,
            signal_attempt_count=3,
            accepted_signal_count=2,
            rejected_signal_count=1,
            acceptance_rate=0.6667,
            schema_conformance_rate=1.0,
            data_validity_rate=1.0,
            rejection_reason_distribution={},
            structural_noise_rate=0.0,
            useful_risk_uplift_rate=0.0,
            useful_thesis_support_rate=0.5,
            decision_relevance_rate=0.0,
            observation_window_size=5,
            observation_window_complete=False,
            classification_snapshot=CLASSIFY_ALPHA,
            recommendation_snapshot=RECOMMEND_LIMITED_PARTICIPATE,
        )
        entry = policy.evaluate_provider(
            ProviderPortfolioInput(
                provider_name="candidate-shadow-provider",
                provider_type="onchain",
                current_status=STATUS_SHADOW_ONLY,
                contribution_ledger=ContributionLedgerReport(
                    provider_name="candidate-shadow-provider",
                    corpus_root=str(ROOT / "fixtures" / "shadow_promotion_corpus"),
                    summary=incomplete_summary,
                    health=ProviderHealthReport(
                        provider_name="candidate-shadow-provider",
                        status=HEALTH_KEEP_SHADOW_ONLY,
                        reasons=["window still open"],
                    ),
                    entries=[],
                ),
                promotion_report=self._good_promotion_report(),
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="candidate-shadow-provider",
                    status="ok",
                    finding_count=0,
                    error_count=0,
                    warning_count=0,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="candidate-shadow-provider",
                    passed=True,
                    scenario_count=2,
                    notes=["window incomplete"],
                ),
            )
        )
        self.assertEqual(entry.portfolio_status, STATUS_SHADOW_ONLY)
        self.assertIn("observation window", entry.reasons[0])

    def test_candidate_can_promote_to_production_after_full_window(self) -> None:
        policy = ProviderPortfolioPolicy()
        entry = policy.evaluate_provider(
            ProviderPortfolioInput(
                provider_name="candidate-shadow-provider",
                provider_type="onchain",
                current_status=STATUS_CANDIDATE,
                contribution_ledger=self._good_contribution_report(),
                promotion_report=self._good_promotion_report(),
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="candidate-shadow-provider",
                    status="ok",
                    finding_count=0,
                    error_count=0,
                    warning_count=0,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="candidate-shadow-provider",
                    passed=True,
                    scenario_count=6,
                    notes=["synthetic shadow regressions green"],
                ),
            )
        )
        self.assertEqual(entry.portfolio_status, STATUS_PRODUCTION)
        self.assertIn("completed the observation window", entry.reasons[0])


if __name__ == "__main__":
    unittest.main()
