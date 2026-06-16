from __future__ import annotations

from dataclasses import dataclass

from enhengclaw.core.execution_control import (
    CAP_PROVIDER_SELECT_INCLUDE_SHADOW,
    CAP_PROVIDER_SELECT_MANUAL_OVERRIDE,
    CAP_PROVIDER_SELECT_RETIRED_OVERRIDE,
)
from enhengclaw.governance.provider_portfolio import ProviderPortfolioInput, ProviderPortfolioReport
from enhengclaw.governance.provider_selection import (
    MODE_DEFAULT,
    MODE_INCLUDE_SHADOW,
    MODE_MANUAL_OVERRIDE,
    ProviderSelectionGateway,
    ProviderSelectionResult,
)


@dataclass(frozen=True, slots=True)
class OpsProviderStatus:
    provider_name: str
    provider_type: str
    current_status: str
    portfolio_status: str
    latest_drift_status: str
    latest_chaos_regression_status: str
    reasons: list[str]
    recommended_action: str


@dataclass(frozen=True, slots=True)
class BlockedProviderSummary:
    provider_name: str
    provider_type: str
    portfolio_status: str
    reason: str


@dataclass(frozen=True, slots=True)
class RuntimeSelectionModePreview:
    mode: str
    allowed_provider_names: list[str]
    rejected_provider_names: list[str]
    requires_capability_override: bool = False


@dataclass(frozen=True, slots=True)
class RunbookSummary:
    default_runtime_can_run: bool
    runtime_available: bool
    fallback: str
    retired_override_required: bool
    warnings: list[str]
    blocked_providers: list[BlockedProviderSummary]


@dataclass(frozen=True, slots=True)
class RuntimeOpsReport:
    active_providers: list[str]
    shadow_providers: list[str]
    retired_providers: list[str]
    default_runtime_provider_names: list[str]
    provider_selection_modes_available: list[str]
    providers: list[OpsProviderStatus]
    selection_previews: list[RuntimeSelectionModePreview]
    runbook: RunbookSummary


class RuntimeOpsReporter:
    def __init__(self, gateway: ProviderSelectionGateway | None = None) -> None:
        self.gateway = gateway or ProviderSelectionGateway()

    def build(
        self,
        *,
        provider_inputs: list[ProviderPortfolioInput],
        portfolio_report: ProviderPortfolioReport,
        sources: list[object] | None = None,
        bindings: list[object] | None = None,
    ) -> RuntimeOpsReport:
        candidates = [] if sources is None else list(sources)
        if bindings is not None:
            candidates = list(bindings) if not candidates else candidates
        input_map = {provider.provider_name: provider for provider in provider_inputs}
        providers = [
            self._provider_status(entry, input_map[entry.provider_name])
            for entry in portfolio_report.entries
            if entry.provider_name in input_map
        ]

        allowlist = [getattr(binding, "provider_name", "") for binding in candidates]
        default_selection = self.gateway.preview(
            portfolio_report=portfolio_report,
            sources=candidates,
            mode=MODE_DEFAULT,
        )
        include_shadow_selection = self.gateway.preview(
            portfolio_report=portfolio_report,
            sources=candidates,
            mode=MODE_INCLUDE_SHADOW,
            capabilities={CAP_PROVIDER_SELECT_INCLUDE_SHADOW},
        )
        manual_override_selection = self.gateway.preview(
            portfolio_report=portfolio_report,
            sources=candidates,
            mode=MODE_MANUAL_OVERRIDE,
            manual_allowlist=allowlist,
            capabilities={CAP_PROVIDER_SELECT_MANUAL_OVERRIDE},
        )
        retired_override_selection = self.gateway.preview(
            portfolio_report=portfolio_report,
            sources=candidates,
            mode=MODE_MANUAL_OVERRIDE,
            manual_allowlist=allowlist,
            capabilities={CAP_PROVIDER_SELECT_MANUAL_OVERRIDE, CAP_PROVIDER_SELECT_RETIRED_OVERRIDE},
        )

        active_providers = [entry.provider_name for entry in portfolio_report.entries if entry.portfolio_status == "production"]
        shadow_providers = [
            entry.provider_name
            for entry in portfolio_report.entries
            if entry.portfolio_status in {"shadow_active", "shadow_degraded", "candidate"}
        ]
        retired_providers = [entry.provider_name for entry in portfolio_report.entries if entry.portfolio_status == "retired"]

        selection_previews = [
            self._selection_preview(default_selection),
            self._selection_preview(include_shadow_selection),
            self._selection_preview(manual_override_selection),
            self._selection_preview(retired_override_selection, requires_capability_override=True),
        ]
        runbook = self._build_runbook(
            portfolio_report=portfolio_report,
            include_shadow_selection=include_shadow_selection,
            default_selection=default_selection,
            retired_override_selection=retired_override_selection,
        )

        return RuntimeOpsReport(
            active_providers=active_providers,
            shadow_providers=shadow_providers,
            retired_providers=retired_providers,
            default_runtime_provider_names=portfolio_report.default_runtime_provider_names,
            provider_selection_modes_available=[MODE_DEFAULT, MODE_INCLUDE_SHADOW, MODE_MANUAL_OVERRIDE],
            providers=providers,
            selection_previews=selection_previews,
            runbook=runbook,
        )

    def _provider_status(self, portfolio_entry, provider_input: ProviderPortfolioInput) -> OpsProviderStatus:
        return OpsProviderStatus(
            provider_name=portfolio_entry.provider_name,
            provider_type=portfolio_entry.provider_type,
            current_status=portfolio_entry.current_status,
            portfolio_status=portfolio_entry.portfolio_status,
            latest_drift_status=provider_input.drift_snapshot.status,
            latest_chaos_regression_status="passed" if provider_input.chaos_snapshot.passed else "failed",
            reasons=portfolio_entry.reasons,
            recommended_action=portfolio_entry.recommended_action,
        )

    def _selection_preview(
        self,
        selection: ProviderSelectionResult,
        *,
        requires_capability_override: bool = False,
    ) -> RuntimeSelectionModePreview:
        return RuntimeSelectionModePreview(
            mode=selection.mode,
            allowed_provider_names=selection.allowed_provider_names,
            rejected_provider_names=selection.rejected_provider_names,
            requires_capability_override=requires_capability_override,
        )

    def _build_runbook(
        self,
        *,
        portfolio_report: ProviderPortfolioReport,
        default_selection: ProviderSelectionResult,
        include_shadow_selection: ProviderSelectionResult,
        retired_override_selection: ProviderSelectionResult,
    ) -> RunbookSummary:
        default_runtime_can_run = bool(default_selection.allowed_provider_names)
        runtime_available = default_runtime_can_run
        blocked_providers = [
            BlockedProviderSummary(
                provider_name=decision.provider_name,
                provider_type=decision.provider_type,
                portfolio_status=decision.portfolio_status or "unknown",
                reason=decision.reason,
            )
            for decision in include_shadow_selection.rejected
        ]

        warnings: list[str] = []
        if not default_runtime_can_run:
            warnings.append("default runtime has no selectable providers; fail closed")

        retired_override_required = (
            not default_runtime_can_run
            and not include_shadow_selection.allowed_provider_names
            and bool(retired_override_selection.allowed_provider_names)
        )
        if retired_override_required:
            warnings.append("only a retired-provider override capability can produce a runnable provider set")

        if default_runtime_can_run:
            fallback = "default runtime is available; include_shadow remains an explicit operator mode"
        elif include_shadow_selection.allowed_provider_names:
            fallback = "operator may rerun in include_shadow mode; default runtime remains unavailable"
        elif retired_override_required:
            fallback = "only manual_override with an explicit retired-provider capability can run; this is non-normal operation"
        else:
            fallback = "no non-default fallback exists; runtime unavailable"

        return RunbookSummary(
            default_runtime_can_run=default_runtime_can_run,
            runtime_available=runtime_available,
            fallback=fallback,
            retired_override_required=retired_override_required,
            warnings=warnings,
            blocked_providers=blocked_providers,
        )
