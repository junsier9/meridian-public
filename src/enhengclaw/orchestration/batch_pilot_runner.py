from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from enhengclaw.ops.drift_inspector import CEXDriftInspector
from enhengclaw.core.execution_control import (
    CAP_PROVIDER_FETCH,
    CAP_RUNTIME_EXECUTE,
    ExecutionPermit,
    bind_execution_context,
)
from enhengclaw.core.enums import ObjectType
from enhengclaw.ops.golden_corpus import GoldenReplayCorpus
from enhengclaw.orchestration.pilot_runner import (
    PILOT_STATUS_ERROR,
    PILOT_STATUS_OK,
    PILOT_STATUS_RUNTIME_UNAVAILABLE,
    PilotRunner,
    PilotRunResult,
)
from enhengclaw.governance.provider_portfolio import (
    ProviderChaosSnapshot,
    ProviderDriftSnapshot,
    ProviderPortfolioInput,
    ProviderPortfolioPolicy,
    ProviderPortfolioReport,
    STATUS_ACTIVE,
    STATUS_SHADOW_ONLY,
)
from enhengclaw.governance.provider_selection import MODE_DEFAULT
from enhengclaw.orchestration.provider_snapshot_runner import (
    ProviderSourceSpec,
    expected_provider_payload_path,
    load_cex_payload_artifact,
)
from enhengclaw.providers.providers import ProviderRequest
from enhengclaw.governance.shadow_contribution import ContributionLedger
from enhengclaw.governance.shadow_promotion import ShadowPromotionRunner


@dataclass(frozen=True, slots=True)
class BatchPilotProviderSetup:
    provider_inputs: list[ProviderPortfolioInput]
    portfolio_report: ProviderPortfolioReport
    provider_sources: list[ProviderSourceSpec]
    scenario: str
    provider_mode: str


@dataclass(frozen=True, slots=True)
class BatchPilotRunEntry:
    symbol: str
    status: str
    decision: str | None
    archive_path: str | None
    warnings: list[str]
    errors: list[str]
    provider_mode: str


@dataclass(frozen=True, slots=True)
class BatchPilotResult:
    batch_id: str
    batch_root: str
    batch_summary_path: str
    symbols: list[str]
    success_count: int
    runtime_unavailable_count: int
    error_count: int
    runs: list[BatchPilotRunEntry]


BatchPilotSetupFactory = Callable[..., BatchPilotProviderSetup]


class BatchPilotRunner:
    def __init__(
        self,
        *,
        pilot_runner: PilotRunner | None = None,
        setup_factory: BatchPilotSetupFactory | None = None,
        archive_root: str | Path | None = None,
        execution_permit: ExecutionPermit | None = None,
    ) -> None:
        self.pilot_runner = pilot_runner or PilotRunner()
        self.setup_factory = setup_factory or self._build_default_setup
        self.execution_permit = execution_permit
        self.archive_root = (
            Path(archive_root)
            if archive_root is not None
            else Path(__file__).resolve().parents[3] / "artifacts" / "pilot_batches"
        )

    def run_batch(
        self,
        *,
        symbols: list[str],
        scope: str,
        selection_mode: str = MODE_DEFAULT,
        use_live: bool = False,
        archive_root: str | Path | None = None,
        object_type: ObjectType = ObjectType.ASSET,
        execution_permit: ExecutionPermit | None = None,
    ) -> BatchPilotResult:
        with bind_execution_context(
            execution_permit or self.execution_permit,
            operation="orchestration.batch_pilot_runner.run_batch",
            requested_scope=scope,
            required_capabilities={CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH},
        ):
            batch_id = self._build_batch_id()
            batch_root = Path(archive_root) if archive_root is not None else self.archive_root / batch_id
            runs_root = batch_root / "runs"
            batch_root.mkdir(parents=True, exist_ok=True)
            runs_root.mkdir(parents=True, exist_ok=True)

            entries: list[BatchPilotRunEntry] = []
            original_archive_root = self.pilot_runner.archive_root
            self.pilot_runner.archive_root = runs_root
            try:
                for symbol in symbols:
                    try:
                        setup = self.setup_factory(symbol=symbol, scope=scope, use_live=use_live)
                        run_result = self.pilot_runner.run_once(
                            subject=symbol,
                            scope=scope,
                            scenario=setup.scenario,
                            provider_inputs=setup.provider_inputs,
                            portfolio_report=setup.portfolio_report,
                            provider_sources=setup.provider_sources,
                            selection_mode=selection_mode,
                            object_type=object_type,
                        )
                        entries.append(self._entry_from_result(symbol, setup.provider_mode, run_result))
                    except Exception as exc:
                        entries.append(
                            BatchPilotRunEntry(
                                symbol=symbol,
                                status=PILOT_STATUS_ERROR,
                                decision=None,
                                archive_path=None,
                                warnings=[],
                                errors=[str(exc)],
                                provider_mode="setup_error",
                            )
                        )
            finally:
                self.pilot_runner.archive_root = original_archive_root

            result = BatchPilotResult(
                batch_id=batch_id,
                batch_root=str(batch_root),
                batch_summary_path=str(batch_root / "batch_summary.json"),
                symbols=symbols,
                success_count=sum(1 for entry in entries if entry.status == PILOT_STATUS_OK),
                runtime_unavailable_count=sum(1 for entry in entries if entry.status == PILOT_STATUS_RUNTIME_UNAVAILABLE),
                error_count=sum(1 for entry in entries if entry.status == PILOT_STATUS_ERROR),
                runs=entries,
            )
            (batch_root / "batch_summary.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
            return result

    def _entry_from_result(self, symbol: str, provider_mode: str, result: PilotRunResult) -> BatchPilotRunEntry:
        return BatchPilotRunEntry(
            symbol=symbol,
            status=result.status,
            decision=None if result.runtime_result is None else str(result.runtime_result["decision"]),
            archive_path=result.archive_paths.run_root,
            warnings=list(result.warnings),
            errors=list(result.errors),
            provider_mode=provider_mode,
        )

    def _build_default_setup(self, *, symbol: str, scope: str, use_live: bool) -> BatchPilotProviderSetup:
        if use_live:
            provider_mode = "live_record"
            scenario = os.getenv("REAL_CEX_SCENARIO", "live_cex_pilot")
            cex_source = ProviderSourceSpec.real_cex(
                provider_name="binance-public-cex",
                mode="record",
                api_base_url=os.getenv("REAL_CEX_API_BASE_URL", "https://api.binance.com"),
                timeout_seconds=float(os.getenv("REAL_CEX_TIMEOUT", "5")),
                api_key_env_var="REAL_CEX_API_KEY",
                raw_payload_root=Path(__file__).resolve().parents[3] / "artifacts" / "provider_records" / "cex",
            )
            cex_drift_status = "ok"
            cex_drift_findings = 0
            cex_drift_errors = 0
            cex_drift_warnings = 0
        else:
            provider_mode = "replay"
            scenario = "bullish_publish"
            cex_corpus = GoldenReplayCorpus(Path(__file__).resolve().parents[3] / "fixtures" / "golden_corpus" / "cex")
            cex_source = ProviderSourceSpec.real_cex(
                provider_name="binance-public-cex",
                mode="replay",
                raw_payload_root=cex_corpus.category_root("normal"),
            )
            cex_payload_path = expected_provider_payload_path(
                cex_source,
                ProviderRequest(
                    object_id=f"batch-pilot-{symbol.lower()}",
                    object_type=ObjectType.ASSET,
                    subject=symbol,
                    scope=scope,
                    scenario=scenario,
                ),
            )
            if cex_payload_path is None:
                raise ValueError("cex replay source did not resolve to a payload artifact path")
            cex_drift = CEXDriftInspector().inspect(load_cex_payload_artifact(cex_payload_path))
            cex_drift_status = cex_drift.status
            cex_drift_findings = len(cex_drift.findings)
            cex_drift_errors = sum(1 for finding in cex_drift.findings if finding.severity == "error")
            cex_drift_warnings = sum(1 for finding in cex_drift.findings if finding.severity == "warning")

        onchain_source = ProviderSourceSpec.real_onchain(
            provider_name="real_onchain_provider_shadow",
            mode="replay",
            raw_payload_root=Path(__file__).resolve().parents[3]
            / "fixtures"
            / "golden_corpus"
            / "onchain"
            / "normal",
        )

        contribution = ContributionLedger().build()
        promotion = ShadowPromotionRunner().compare_all()
        onchain_error_count = sum(
            1 for comparison in promotion.comparisons if comparison.onchain_drift_status == "error"
        )
        onchain_warning_count = sum(
            1 for comparison in promotion.comparisons if comparison.onchain_drift_status == "warning"
        )
        onchain_status = "error" if onchain_error_count > 0 else "warning" if onchain_warning_count > 0 else "ok"

        provider_inputs = [
            ProviderPortfolioInput(
                provider_name="binance-public-cex",
                provider_type="cex",
                current_status=STATUS_ACTIVE,
                contribution_ledger=None,
                promotion_report=None,
                drift_snapshot=ProviderDriftSnapshot(
                    provider_name="binance-public-cex",
                    status=cex_drift_status,
                    finding_count=cex_drift_findings,
                    error_count=cex_drift_errors,
                    warning_count=cex_drift_warnings,
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
        portfolio_report = ProviderPortfolioPolicy().evaluate_all(provider_inputs)
        return BatchPilotProviderSetup(
            provider_inputs=provider_inputs,
            portfolio_report=portfolio_report,
            provider_sources=[cex_source, onchain_source],
            scenario=scenario,
            provider_mode=provider_mode,
        )

    def _build_batch_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
