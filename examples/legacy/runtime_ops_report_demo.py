from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
from enhengclaw.governance.provider_selection import ProviderRuntimeBinding
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.ops.runtime_ops import RuntimeOpsReporter
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter


def _current_shadow_inputs(
    current_cex_status: str = STATUS_ACTIVE,
    current_onchain_status: str = STATUS_SHADOW_ONLY,
    *,
    cex_chaos_passed: bool | None = None,
):
    cex_corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
    cex_provider = RealCEXProvider(
        RealCEXProviderConfig(mode="replay", raw_payload_dir=cex_corpus.category_root("normal"))
    )
    cex_payload = cex_provider.fetch(
        ProviderRequest(
            object_id="ops-report-cex",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
        )
    )
    cex_drift = CEXDriftInspector().inspect(cex_payload)

    contribution = ContributionLedger().build()
    promotion = ShadowPromotionRunner().compare_all()
    onchain_error_count = sum(1 for comparison in promotion.comparisons if comparison.onchain_drift_status == "error")
    onchain_warning_count = sum(1 for comparison in promotion.comparisons if comparison.onchain_drift_status == "warning")
    onchain_status = "error" if onchain_error_count > 0 else "warning" if onchain_warning_count > 0 else "ok"

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
                status=cex_drift.status,
                finding_count=len(cex_drift.findings),
                error_count=sum(1 for finding in cex_drift.findings if finding.severity == "error"),
                warning_count=sum(1 for finding in cex_drift.findings if finding.severity == "warning"),
            ),
            chaos_snapshot=ProviderChaosSnapshot(
                provider_name="binance-public-cex",
                passed=cex_chaos_passed,
                scenario_count=8,
                notes=["provider regressions green"] if cex_chaos_passed else ["simulated provider outage / policy demotion"],
            ),
        ),
        ProviderPortfolioInput(
            provider_name="real_onchain_provider_shadow",
            provider_type="onchain",
            current_status=current_onchain_status,
            contribution_ledger=contribution,
            promotion_report=promotion,
            drift_snapshot=ProviderDriftSnapshot(
                provider_name="real_onchain_provider_shadow",
                status=onchain_status,
                finding_count=onchain_error_count + onchain_warning_count,
                error_count=onchain_error_count,
                warning_count=onchain_warning_count,
            ),
            chaos_snapshot=ProviderChaosSnapshot(
                provider_name="real_onchain_provider_shadow",
                passed=True,
                scenario_count=5,
                notes=["shadow/onchain regressions green"],
            ),
        ),
    ]

    bindings = [
        ProviderRuntimeBinding(
            provider_name="binance-public-cex",
            provider_type="cex",
            adapter=CEXSnapshotAdapter(provider=cex_provider),
        ),
        ProviderRuntimeBinding(
            provider_name="real_onchain_provider_shadow",
            provider_type="onchain",
            adapter=OnchainSnapshotAdapter(
                provider=RealOnchainProvider(
                    RealOnchainProviderConfig(
                        mode="replay",
                        raw_payload_dir=ROOT / "fixtures" / "golden_corpus" / "onchain" / "normal",
                    )
                )
            ),
        ),
    ]
    return inputs, bindings


def _ops_payload(inputs, bindings):
    portfolio = ProviderPortfolioPolicy().evaluate_all(inputs)
    report = RuntimeOpsReporter().build(
        provider_inputs=inputs,
        portfolio_report=portfolio,
        bindings=bindings,
    )
    return {
        "portfolio": {
            "default_runtime_provider_names": portfolio.default_runtime_provider_names,
            "shadow_provider_names": portfolio.shadow_provider_names,
            "entries": [asdict(entry) for entry in portfolio.entries],
        },
        "ops_report": asdict(report),
    }


def main() -> None:
    normal_inputs, normal_bindings = _current_shadow_inputs()
    default_unavailable_inputs, default_unavailable_bindings = _current_shadow_inputs(
        current_cex_status=STATUS_ACTIVE,
        cex_chaos_passed=False,
    )
    debug_only_inputs, debug_only_bindings = _current_shadow_inputs(
        current_cex_status=STATUS_RETIRED,
        current_onchain_status=STATUS_RETIRED,
    )

    payload = {
        "normal_runtime": _ops_payload(normal_inputs, normal_bindings),
        "default_provider_unavailable": _ops_payload(default_unavailable_inputs, default_unavailable_bindings),
        "retired_provider_only_debug_override": _ops_payload(debug_only_inputs, debug_only_bindings),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="runtime-ops-report-demo"):
        main()

