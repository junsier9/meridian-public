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
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner


def _cex_drift_snapshot() -> ProviderDriftSnapshot:
    corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
    provider = RealCEXProvider(
        RealCEXProviderConfig(mode="replay", raw_payload_dir=corpus.category_root("normal"))
    )
    payload = provider.fetch(
        ProviderRequest(
            object_id="portfolio-cex",
            object_type=ObjectType.ASSET,
            subject="AIX",
            scope="spot+perp",
            scenario="bullish_publish",
        )
    )
    report = CEXDriftInspector().inspect(payload)
    error_count = sum(1 for finding in report.findings if finding.severity == "error")
    warning_count = sum(1 for finding in report.findings if finding.severity == "warning")
    return ProviderDriftSnapshot(
        provider_name="binance-public-cex",
        status=report.status,
        finding_count=len(report.findings),
        error_count=error_count,
        warning_count=warning_count,
    )


def _onchain_drift_snapshot() -> ProviderDriftSnapshot:
    report = ShadowPromotionRunner().compare_all()
    error_count = sum(1 for comparison in report.comparisons if comparison.onchain_drift_status == "error")
    warning_count = sum(1 for comparison in report.comparisons if comparison.onchain_drift_status == "warning")
    status = "error" if error_count > 0 else "warning" if warning_count > 0 else "ok"
    return ProviderDriftSnapshot(
        provider_name="real_onchain_provider_shadow",
        status=status,
        finding_count=error_count + warning_count,
        error_count=error_count,
        warning_count=warning_count,
    )


def main() -> None:
    contribution = ContributionLedger().build()
    promotion = ShadowPromotionRunner().compare_all()
    policy = ProviderPortfolioPolicy()
    report = policy.evaluate_all(
        [
            ProviderPortfolioInput(
                provider_name="binance-public-cex",
                provider_type="cex",
                current_status=STATUS_ACTIVE,
                contribution_ledger=None,
                promotion_report=None,
                drift_snapshot=_cex_drift_snapshot(),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="binance-public-cex",
                    passed=True,
                    scenario_count=8,
                    notes=["provider chaos regression suite is green"],
                ),
            ),
            ProviderPortfolioInput(
                provider_name="real_onchain_provider_shadow",
                provider_type="onchain",
                current_status=STATUS_SHADOW_ONLY,
                contribution_ledger=contribution,
                promotion_report=promotion,
                drift_snapshot=_onchain_drift_snapshot(),
                chaos_snapshot=ProviderChaosSnapshot(
                    provider_name="real_onchain_provider_shadow",
                    passed=True,
                    scenario_count=5,
                    notes=["shadow/onchain chaos regression suite is green"],
                ),
            ),
        ]
    )
    payload = {
        "default_runtime_provider_names": report.default_runtime_provider_names,
        "shadow_provider_names": report.shadow_provider_names,
        "entries": [asdict(entry) for entry in report.entries],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="provider-portfolio-demo"):
        main()

