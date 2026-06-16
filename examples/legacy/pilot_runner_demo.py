from __future__ import annotations

import argparse
import json
import os
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
from enhengclaw.orchestration.pilot_runner import PilotRunner
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.provider_selection import MODE_DEFAULT, MODE_INCLUDE_SHADOW, ProviderRuntimeBinding
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.providers.real_cex_provider import RealCEXProvider, RealCEXProviderConfig
from enhengclaw.providers.real_onchain_provider import RealOnchainProvider, RealOnchainProviderConfig
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner
from enhengclaw.adapters.snapshot_adapters import CEXSnapshotAdapter, OnchainSnapshotAdapter


def _build_cex_provider(*, use_live: bool, raw_payload_dir: Path) -> tuple[RealCEXProvider, str, str]:
    if use_live:
        provider = RealCEXProvider(
            RealCEXProviderConfig(
                api_base_url=os.getenv("REAL_CEX_API_BASE_URL", "https://api.binance.com"),
                timeout_seconds=float(os.getenv("REAL_CEX_TIMEOUT", "5")),
                api_key_env_var="REAL_CEX_API_KEY",
                mode="record",
                raw_payload_dir=raw_payload_dir,
            )
        )
        return provider, os.getenv("REAL_CEX_SCENARIO", "live_cex_pilot"), "live_record"

    cex_corpus = GoldenReplayCorpus(ROOT / "fixtures" / "golden_corpus" / "cex")
    provider = RealCEXProvider(
        RealCEXProviderConfig(
            mode="replay",
            raw_payload_dir=cex_corpus.category_root("normal"),
        )
    )
    return provider, "bullish_publish", "replay"


def _build_inputs_and_bindings(
    *,
    subject: str,
    scope: str,
    use_live: bool,
    current_cex_status: str = STATUS_ACTIVE,
    current_onchain_status: str = STATUS_SHADOW_ONLY,
    cex_chaos_passed: bool | None = None,
) -> tuple[list[ProviderPortfolioInput], list[ProviderRuntimeBinding], object, str]:
    record_root = ROOT / "artifacts" / "provider_records" / "cex"
    cex_provider, scenario, provider_mode = _build_cex_provider(use_live=use_live, raw_payload_dir=record_root)
    cex_payload = cex_provider.fetch(
        ProviderRequest(
            object_id="pilot-demo-cex",
            object_type=ObjectType.ASSET,
            subject=subject,
            scope=scope,
            scenario=scenario,
        )
    )
    cex_drift = CEXDriftInspector().inspect(cex_payload)

    contribution = ContributionLedger().build()
    promotion = ShadowPromotionRunner().compare_all()
    onchain_error_count = sum(1 for comparison in promotion.comparisons if comparison.onchain_drift_status == "error")
    onchain_warning_count = sum(
        1 for comparison in promotion.comparisons if comparison.onchain_drift_status == "warning"
    )
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
                notes=["provider regressions green"] if cex_chaos_passed else ["simulated provider unavailable"],
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
    portfolio = ProviderPortfolioPolicy().evaluate_all(inputs)
    return inputs, bindings, portfolio, provider_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a limited live pilot against the default runtime providers.")
    parser.add_argument("--symbol", default=os.getenv("REAL_CEX_SYMBOL", "AIX"))
    parser.add_argument("--scope", default="spot+perp")
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--include-shadow", action="store_true")
    parser.add_argument("--use-live", action="store_true")
    parser.add_argument("--simulate-default-unavailable", action="store_true")
    args = parser.parse_args()

    use_live = args.use_live or os.getenv("ENABLE_REAL_CEX_PROVIDER") == "1"
    selection_mode = MODE_INCLUDE_SHADOW if args.include_shadow else MODE_DEFAULT
    cex_status = STATUS_ACTIVE if not args.simulate_default_unavailable else STATUS_ACTIVE
    cex_chaos_passed = None if not args.simulate_default_unavailable else False

    inputs, bindings, portfolio, provider_mode = _build_inputs_and_bindings(
        subject=args.symbol,
        scope=args.scope,
        use_live=use_live,
        current_cex_status=cex_status,
        current_onchain_status=STATUS_SHADOW_ONLY,
        cex_chaos_passed=cex_chaos_passed,
    )

    runner = PilotRunner(archive_root=args.archive_root)
    result = runner.run_once(
        subject=args.symbol,
        scope=args.scope,
        scenario="live_cex_pilot" if use_live else "bullish_publish",
        provider_inputs=inputs,
        portfolio_report=portfolio,
        provider_bindings=bindings,
        selection_mode=selection_mode,
    )

    payload = {
        "provider_mode": provider_mode,
        "selection_mode": selection_mode,
        "pilot_result": asdict(result),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="pilot-runner-demo"):
        main()

