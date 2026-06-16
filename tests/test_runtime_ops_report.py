from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.core.enums import ObjectType
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSnapshotRunRequest,
    ProviderSnapshotRunner,
    ProviderSourceSpec,
    expected_provider_payload_path,
    load_cex_payload_artifact,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.ops.runtime_ops import RuntimeOpsReporter
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner
from tests.test_helpers import enter_runtime_worker_class


class RuntimeOpsReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        enter_runtime_worker_class(cls, slug="test-runtime-ops-report")
        cls.cex_corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
        cls.cex_source = ProviderSourceSpec.real_cex(
            provider_name="binance-public-cex",
            mode="replay",
            raw_payload_root=cls.cex_corpus.category_root("normal"),
        )
        cls.cex_payload = load_cex_payload_artifact(
            expected_provider_payload_path(
                cls.cex_source,
                ProviderRequest(
                    object_id="ops-test-cex",
                    object_type=ObjectType.ASSET,
                    subject="AIX",
                    scope="spot+perp",
                    scenario="bullish_publish",
                ),
            )
        )
        cls.cex_drift = CEXDriftInspector().inspect(cls.cex_payload)
        cls.contribution = ContributionLedger().build()
        cls.promotion = ShadowPromotionRunner().compare_all()
        cls.onchain_error_count = sum(
            1 for comparison in cls.promotion.comparisons if comparison.onchain_drift_status == "error"
        )
        cls.onchain_warning_count = sum(
            1 for comparison in cls.promotion.comparisons if comparison.onchain_drift_status == "warning"
        )
        cls.onchain_status = (
            "error"
            if cls.onchain_error_count > 0
            else "warning" if cls.onchain_warning_count > 0 else "ok"
        )

    def _build_inputs_and_sources(
        self,
        *,
        current_cex_status: str = STATUS_ACTIVE,
        current_onchain_status: str = STATUS_SHADOW_ONLY,
        cex_chaos_passed: bool | None = None,
    ):
        if cex_chaos_passed is None:
            cex_chaos_passed = current_cex_status == STATUS_ACTIVE

        inputs = [
            ProviderPortfolioInput(
                provider_name="binance-public-cex",
                provider_type="cex",
                current_status=current_cex_status,
                contribution_ledger=None,
                promotion_report=None,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="binance-public-cex",
                    status=self.cex_drift.status,
                    finding_count=len(self.cex_drift.findings),
                    error_count=sum(1 for finding in self.cex_drift.findings if finding.severity == "error"),
                    warning_count=sum(1 for finding in self.cex_drift.findings if finding.severity == "warning"),
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="binance-public-cex",
                    passed=cex_chaos_passed,
                    scenario_count=8,
                    notes=["provider regressions green"] if cex_chaos_passed else ["simulated provider unavailable"],
                ),
            ),
            ProviderPortfolioInput(
                provider_name="real_onchain_provider_shadow",
                provider_type="onchain",
                current_status=current_onchain_status,
                contribution_ledger=self.contribution,
                promotion_report=self.promotion,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    status=self.onchain_status,
                    finding_count=self.onchain_error_count + self.onchain_warning_count,
                    error_count=self.onchain_error_count,
                    warning_count=self.onchain_warning_count,
                ),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    passed=True,
                    scenario_count=5,
                    notes=["shadow/onchain regressions green"],
                ),
            ),
        ]
        sources = [
            self.cex_source,
            ProviderSourceSpec.real_onchain(
                provider_name="real_onchain_provider_shadow",
                mode="replay",
                raw_payload_root=ROOT / "fixtures" / "golden_corpus" / "onchain" / "normal",
            ),
        ]
        portfolio = ProviderPortfolioPolicy().evaluate_all(inputs)
        return inputs, sources, portfolio

    def test_ops_report_does_not_change_runtime_behavior(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources()
        snapshot_runner = ProviderSnapshotRunner(runtime=RuntimeOrchestrator())

        before = snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id="ops-runtime-before",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                source_specs=[sources[0]],
            )
        )
        report = RuntimeOpsReporter().build(
            provider_inputs=inputs,
            portfolio_report=portfolio,
            sources=sources,
        )
        after = snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id="ops-runtime-after",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                source_specs=[sources[0]],
            )
        )

        self.assertTrue(report.runbook.default_runtime_can_run)
        self.assertEqual(list(before.source_artifact_paths.keys()), list(after.source_artifact_paths.keys()))
        self.assertEqual(before.runtime_result.decision.decision, after.runtime_result.decision.decision)
        self.assertEqual(before.runtime_result.research_object.processing_state, after.runtime_result.research_object.processing_state)

    def test_default_runtime_unavailable_is_explicitly_marked_unusable(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources(
            current_cex_status=STATUS_ACTIVE,
            current_onchain_status=STATUS_SHADOW_ONLY,
            cex_chaos_passed=False,
        )
        report = RuntimeOpsReporter().build(
            provider_inputs=inputs,
            portfolio_report=portfolio,
            sources=sources,
        )

        self.assertFalse(report.runbook.default_runtime_can_run)
        self.assertFalse(report.runbook.runtime_available)
        self.assertIn("fail closed", report.runbook.warnings[0])
        self.assertIn("include_shadow", report.runbook.fallback)

    def test_retired_provider_is_not_silently_selected_as_fallback(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources(
            current_cex_status=STATUS_RETIRED,
            current_onchain_status=STATUS_RETIRED,
        )
        report = RuntimeOpsReporter().build(
            provider_inputs=inputs,
            portfolio_report=portfolio,
            sources=sources,
        )

        default_preview = next(item for item in report.selection_previews if item.mode == "default")
        include_shadow_preview = next(item for item in report.selection_previews if item.mode == "include_shadow")
        self.assertEqual(default_preview.allowed_provider_names, [])
        self.assertEqual(include_shadow_preview.allowed_provider_names, [])
        self.assertIn("real_onchain_provider_shadow", [item.provider_name for item in report.runbook.blocked_providers])

    def test_debug_override_is_clearly_marked_non_normal_operation(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources(
            current_cex_status=STATUS_RETIRED,
            current_onchain_status=STATUS_RETIRED,
        )
        report = RuntimeOpsReporter().build(
            provider_inputs=inputs,
            portfolio_report=portfolio,
            sources=sources,
        )

        debug_preview = next(
            item
            for item in report.selection_previews
            if item.mode == "manual_override" and item.requires_capability_override
        )
        self.assertTrue(report.runbook.retired_override_required)
        self.assertIn("retired-provider override", report.runbook.warnings[-1])
        self.assertIn("real_onchain_provider_shadow", debug_preview.allowed_provider_names)


if __name__ == "__main__":
    unittest.main()
