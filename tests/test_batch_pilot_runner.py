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

from enhengclaw.orchestration.batch_pilot_runner import (
    BatchPilotProviderSetup,
    BatchPilotRunner,
)
from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.core.enums import ObjectType
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.orchestration.pilot_runner import (
    PILOT_STATUS_OK,
    PILOT_STATUS_RUNTIME_UNAVAILABLE,
    PilotArtifactPaths,
    PilotRunResult,
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
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSourceSpec,
    expected_provider_payload_path,
    load_cex_payload_artifact,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner
from tests.test_helpers import enter_runtime_worker_class


class _SpyPilotRunner(PilotRunner):
    def __init__(self) -> None:
        super().__init__(archive_root=ROOT / "artifacts" / "spy_batch_runs")
        self.calls: list[str] = []

    def run_once(self, **kwargs):
        self.calls.append(str(kwargs["subject"]))
        run_root = Path(self.archive_root) / f"spy_{kwargs['subject'].lower()}"
        run_root.mkdir(parents=True, exist_ok=True)
        artifact = run_root / "noop.json"
        artifact.write_text("{}", encoding="utf-8")
        return PilotRunResult(
            run_id=f"spy-{kwargs['subject']}",
            status=PILOT_STATUS_OK,
            archive_paths=PilotArtifactPaths(
                run_root=str(run_root),
                raw_payload_dir=str(run_root),
                provider_selection_result=str(artifact),
                normalized_signal_summary=str(artifact),
                runtime_result=str(artifact),
                ops_report=str(artifact),
                warnings_errors=str(artifact),
            ),
            raw_payload_record_paths=[],
            normalized_signal_summary=[],
            selection_result={"allowed_provider_names": ["binance-public-cex"], "rejected_provider_names": [], "rejected": [], "mode": "default"},
            runtime_result={"decision": "monitoring"},
            ops_report={},
            warnings=[],
            errors=[],
        )


class BatchPilotRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        enter_runtime_worker_class(cls, slug="test-batch-pilot-runner")
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
                    object_id="batch-pilot-test-cex",
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

    def _make_setup(
        self,
        *,
        symbol: str,
        scope: str,
        current_cex_status: str = STATUS_ACTIVE,
        current_onchain_status: str = STATUS_SHADOW_ONLY,
        cex_chaos_passed: bool | None = None,
    ) -> BatchPilotProviderSetup:
        if cex_chaos_passed is None:
            cex_chaos_passed = current_cex_status == STATUS_ACTIVE

        provider_inputs = [
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
        provider_sources = [
            self.cex_source,
            ProviderSourceSpec.real_onchain(
                provider_name="real_onchain_provider_shadow",
                mode="replay",
                raw_payload_root=ROOT / "fixtures" / "golden_corpus" / "onchain" / "normal",
            ),
        ]
        portfolio_report = ProviderPortfolioPolicy().evaluate_all(provider_inputs)
        return BatchPilotProviderSetup(
            provider_inputs=provider_inputs,
            portfolio_report=portfolio_report,
            provider_sources=provider_sources,
            scenario="bullish_publish",
            provider_mode="replay",
        )

    def test_batch_runner_does_not_bypass_pilot_runner(self) -> None:
        spy_runner = _SpyPilotRunner()
        runner = BatchPilotRunner(
            pilot_runner=spy_runner,
            setup_factory=lambda symbol, scope, use_live: self._make_setup(symbol=symbol, scope=scope),
            archive_root=ROOT / "artifacts" / "batch_spy_runs",
        )

        result = runner.run_batch(symbols=["AIX", "BTC", "ETH"], scope="spot+perp")

        self.assertEqual(spy_runner.calls, ["AIX", "BTC", "ETH"])
        self.assertEqual(len(result.runs), 3)

    def test_runtime_unavailable_run_does_not_break_other_runs(self) -> None:
        def setup_factory(*, symbol: str, scope: str, use_live: bool) -> BatchPilotProviderSetup:
            if symbol == "BAD":
                return self._make_setup(symbol=symbol, scope=scope, cex_chaos_passed=False)
            return self._make_setup(symbol=symbol, scope=scope)

        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = BatchPilotRunner(setup_factory=setup_factory, archive_root=tmp_dir)
            result = runner.run_batch(symbols=["AIX", "BAD", "ETH"], scope="spot+perp")

        statuses = {entry.symbol: entry.status for entry in result.runs}
        self.assertEqual(statuses["BAD"], PILOT_STATUS_RUNTIME_UNAVAILABLE)
        self.assertEqual(statuses["AIX"], PILOT_STATUS_OK)
        self.assertEqual(statuses["ETH"], PILOT_STATUS_OK)
        self.assertEqual(result.success_count, 2)
        self.assertEqual(result.runtime_unavailable_count, 1)
        self.assertEqual(result.error_count, 0)

    def test_batch_summary_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = BatchPilotRunner(
                setup_factory=lambda symbol, scope, use_live: self._make_setup(symbol=symbol, scope=scope),
                archive_root=tmp_dir,
            )
            result = runner.run_batch(symbols=["AIX", "BTC"], scope="spot+perp")

            summary_path = Path(result.batch_summary_path)
            self.assertTrue(summary_path.exists())
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["batch_id"], result.batch_id)
            self.assertEqual(payload["success_count"], 2)
            self.assertEqual(len(payload["runs"]), 2)
            self.assertTrue(all(item["archive_path"] for item in payload["runs"]))

    def test_retired_provider_is_not_used_as_fallback_in_batch(self) -> None:
        def setup_factory(*, symbol: str, scope: str, use_live: bool) -> BatchPilotProviderSetup:
            return self._make_setup(
                symbol=symbol,
                scope=scope,
                current_cex_status=STATUS_RETIRED,
                current_onchain_status=STATUS_RETIRED,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = BatchPilotRunner(setup_factory=setup_factory, archive_root=tmp_dir)
            result = runner.run_batch(symbols=["AIX"], scope="spot+perp")

        self.assertEqual(result.runtime_unavailable_count, 1)
        self.assertEqual(result.success_count, 0)
        self.assertEqual(result.runs[0].status, PILOT_STATUS_RUNTIME_UNAVAILABLE)
        self.assertIsNone(result.runs[0].decision)


if __name__ == "__main__":
    unittest.main()
