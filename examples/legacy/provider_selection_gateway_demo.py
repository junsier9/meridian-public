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
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.provider_selection import (
    MODE_DEFAULT,
    MODE_INCLUDE_SHADOW,
    MODE_MANUAL_OVERRIDE,
    ProviderRuntimeBinding,
    ProviderSelectionGateway,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter


def build_portfolio_report():
    corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
    cex_provider = RealCEXProvider(
        RealCEXProviderConfig(mode="replay", raw_payload_dir=corpus.category_root("normal"))
    )
    cex_payload = cex_provider.fetch(
        ProviderRequest(
            object_id="gateway-demo",
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
    return ProviderPortfolioPolicy().evaluate_all(
        [
            ProviderPortfolioInput(
                provider_name="binance-public-cex",
                provider_type="cex",
                current_status=STATUS_ACTIVE,
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
                    passed=True,
                    scenario_count=8,
                    notes=["provider regressions green"],
                ),
            ),
            ProviderPortfolioInput(
                provider_name="real_onchain_provider_shadow",
                provider_type="onchain",
                current_status=STATUS_SHADOW_ONLY,
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
    )


def build_bindings():
    cex_corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
    return [
        ProviderRuntimeBinding(
            provider_name="binance-public-cex",
            provider_type="cex",
            adapter=CEXSnapshotAdapter(
                provider=RealCEXProvider(
                    RealCEXProviderConfig(mode="replay", raw_payload_dir=cex_corpus.category_root("normal"))
                )
            ),
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


def main() -> None:
    portfolio_report = build_portfolio_report()
    bindings = build_bindings()
    gateway = ProviderSelectionGateway()

    default_selection = gateway.select(
        portfolio_report=portfolio_report,
        bindings=bindings,
        mode=MODE_DEFAULT,
    )
    include_shadow_selection = gateway.select(
        portfolio_report=portfolio_report,
        bindings=bindings,
        mode=MODE_INCLUDE_SHADOW,
    )
    manual_override_selection = gateway.select(
        portfolio_report=portfolio_report,
        bindings=bindings,
        mode=MODE_MANUAL_OVERRIDE,
        manual_allowlist=["binance-public-cex", "real_onchain_provider_shadow"],
    )

    def _selection_summary(selection):
        return {
            "mode": selection.mode,
            "allowed_provider_names": selection.allowed_provider_names,
            "rejected_provider_names": selection.rejected_provider_names,
            "rejected": [asdict(item) for item in selection.rejected],
        }

    payload = {
        "portfolio_entries": [asdict(entry) for entry in portfolio_report.entries],
        "default": _selection_summary(default_selection),
        "include_shadow": _selection_summary(include_shadow_selection),
        "manual_override": _selection_summary(manual_override_selection),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="provider-selection-gateway-demo"):
        main()

