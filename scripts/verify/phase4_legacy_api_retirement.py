from __future__ import annotations

"""Retired controller APIs must stay blocked while the canonical provider/snapshot lane remains green."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import CAP_PROVIDER_FETCH, CAP_RUNTIME_EXECUTE
from enhengclaw.core.enums import ObjectType
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
)
from enhengclaw.governance.provider_selection import MODE_DEFAULT, ProviderRuntimeBinding
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSnapshotRunRequest,
    ProviderSnapshotRunner,
    ProviderSourceSpec,
)
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator
from enhengclaw.testing.execution_testbed import execution_testbed


def main() -> int:
    with execution_testbed() as bed:
        _, permit = bed.issue_permit(
            slug="phase4",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        runtime = RuntimeOrchestrator(execution_permit=permit)
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
                        status="ok",
                        finding_count=0,
                        error_count=0,
                        warning_count=0,
                    ),
                    chaos_snapshot=ProviderChaosSnapshot(
                        provider_name="binance-public-cex",
                        passed=True,
                        scenario_count=1,
                        notes=["green"],
                    ),
                )
            ]
        )
        provider_bindings = [
            ProviderRuntimeBinding(
                provider_name="binance-public-cex",
                provider_type="cex",
                adapter=object(),
            )
        ]
        controller_calls = [
            lambda: runtime.collect_adapter_batches(
                object_id="legacy-adapter-collect",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                adapters=[],
            ),
            lambda: runtime.run_new_from_adapters(
                object_id="legacy-adapter-run",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                adapters=[],
            ),
            lambda: runtime.collect_provider_batches(
                object_id="legacy-provider-collect",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                portfolio_report=portfolio_report,
                provider_bindings=provider_bindings,
            ),
            lambda: runtime.run_new_from_provider_bindings(
                object_id="legacy-provider-run",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                portfolio_report=portfolio_report,
                provider_bindings=provider_bindings,
                selection_mode=MODE_DEFAULT,
            ),
        ]
        for call in controller_calls:
            try:
                call()
            except RuntimeBoundaryError:
                continue
            raise AssertionError("legacy controller API remained callable")

        snapshot_runner = ProviderSnapshotRunner(runtime=runtime)
        canonical_result = snapshot_runner.run_once(
            ProviderSnapshotRunRequest(
                object_id="canonical-provider-snapshot",
                object_type=ObjectType.ASSET,
                subject="AIX",
                scope="spot+perp",
                scenario="bullish_publish",
                source_specs=[
                    ProviderSourceSpec.real_cex(
                        provider_name="binance-public-cex",
                        mode="replay",
                        raw_payload_root=ROOT / "fixtures" / "golden_corpus" / "cex" / "normal",
                    )
                ],
            ),
            execution_permit=permit,
        )
        if canonical_result.runtime_result.research_object.object_id != "canonical-provider-snapshot":
            raise AssertionError("canonical provider/snapshot lane did not return the expected runtime result")
        if not canonical_result.source_artifact_paths.get("binance-public-cex"):
            raise AssertionError("canonical provider/snapshot lane did not surface a raw payload artifact path")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
