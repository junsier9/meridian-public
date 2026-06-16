from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.core.enums import ObjectType
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.orchestration.pilot_runner import (
    PILOT_STATUS_OK,
    PILOT_STATUS_RUNTIME_UNAVAILABLE,
    PilotRunner,
)
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.provider_selection import ProviderSelectionGateway
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSourceSpec,
    expected_provider_payload_path,
    load_cex_payload_artifact,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.ops.runtime_ops import RuntimeOpsReporter
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner
from enhengclaw.utils.subject_keys import SubjectKey
from tests.test_helpers import enter_runtime_worker_class


class _SpySelectionGateway(ProviderSelectionGateway):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def select(self, **kwargs):
        self.calls.append(str(kwargs.get("mode", "default")))
        return super().select(**kwargs)


class PilotRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        enter_runtime_worker_class(cls, slug="test-pilot-runner")
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
                    object_id="pilot-test-cex",
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

    def test_pilot_runner_uses_provider_selection_gateway(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources()
        gateway = _SpySelectionGateway()
        runtime = RuntimeOrchestrator(selection_gateway=gateway)
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = PilotRunner(
                runtime=runtime,
                ops_reporter=RuntimeOpsReporter(gateway),
                archive_root=tmp_dir,
            )

            result = runner.run_once(
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                provider_inputs=inputs,
                portfolio_report=portfolio,
                provider_sources=sources,
            )

        self.assertGreaterEqual(len(gateway.calls), 1)
        self.assertEqual(gateway.calls[0], "default")
        self.assertEqual(result.selection_result["allowed_provider_names"], ["binance-public-cex"])

    def test_default_provider_unavailable_fails_closed(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources(
            current_cex_status=STATUS_ACTIVE,
            cex_chaos_passed=False,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = PilotRunner(archive_root=tmp_dir)
            result = runner.run_once(
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                provider_inputs=inputs,
                portfolio_report=portfolio,
                provider_sources=sources,
            )

        self.assertEqual(result.status, PILOT_STATUS_RUNTIME_UNAVAILABLE)
        self.assertIsNone(result.runtime_result)
        self.assertEqual(result.selection_result["allowed_provider_names"], [])
        self.assertTrue(any("fail closed" in warning for warning in result.warnings))

    def test_retired_provider_is_not_used_as_automatic_fallback(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources(
            current_cex_status=STATUS_RETIRED,
            current_onchain_status=STATUS_RETIRED,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = PilotRunner(archive_root=tmp_dir)
            result = runner.run_once(
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                provider_inputs=inputs,
                portfolio_report=portfolio,
                provider_sources=sources,
            )

        self.assertEqual(result.status, PILOT_STATUS_RUNTIME_UNAVAILABLE)
        self.assertEqual(result.raw_payload_record_paths, [])
        self.assertEqual(result.selection_result["allowed_provider_names"], [])
        self.assertCountEqual(
            result.selection_result["rejected_provider_names"],
            ["binance-public-cex", "real_onchain_provider_shadow"],
        )

    def test_run_artifacts_are_fully_written(self) -> None:
        inputs, sources, portfolio = self._build_inputs_and_sources()
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = PilotRunner(archive_root=tmp_dir)
            result = runner.run_once(
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                provider_inputs=inputs,
                portfolio_report=portfolio,
                provider_sources=sources,
            )

            self.assertEqual(result.status, PILOT_STATUS_OK)
            self.assertEqual(len(result.raw_payload_record_paths), 1)

            run_root = Path(result.archive_paths.run_root)
            self.assertTrue(run_root.exists())
            self.assertTrue(Path(result.archive_paths.raw_payload_dir).exists())
            self.assertTrue(Path(result.archive_paths.provider_selection_result).exists())
            self.assertTrue(Path(result.archive_paths.normalized_signal_summary).exists())
            self.assertIsNotNone(result.archive_paths.runtime_result)
            self.assertTrue(Path(result.archive_paths.runtime_result).exists())
            self.assertTrue(Path(result.archive_paths.ops_report).exists())
            self.assertTrue(Path(result.archive_paths.warnings_errors).exists())
            self.assertTrue(Path(result.raw_payload_record_paths[0]).exists())
            self.assertIn(
                SubjectKey.build(symbol="AIX", venue="runtime", instrument_type="research_object").as_path_fragment(),
                str(run_root),
            )
            self.assertIn(
                SubjectKey.build(symbol="AIX", venue="binance-public-cex", instrument_type="cex").as_path_fragment(),
                result.raw_payload_record_paths[0],
            )

            with Path(result.archive_paths.runtime_result).open("r", encoding="utf-8") as handle:
                runtime_payload = json.load(handle)
            self.assertIn("decision", runtime_payload)
            self.assertIn("research_object", runtime_payload)


if __name__ == "__main__":
    unittest.main()
