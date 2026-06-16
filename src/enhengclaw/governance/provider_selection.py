from __future__ import annotations

from dataclasses import dataclass, field
from enhengclaw.adapters.adapters import SignalAdapter
from enhengclaw.core.execution_control import (
    CAP_PROVIDER_SELECT_INCLUDE_SHADOW,
    CAP_PROVIDER_SELECT_MANUAL_OVERRIDE,
    CAP_PROVIDER_SELECT_RETIRED_OVERRIDE,
    current_execution_capabilities,
)
from enhengclaw.governance.provider_portfolio import (
    ProviderPortfolioEntry,
    ProviderPortfolioReport,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    STATUS_SHADOW_ACTIVE,
    STATUS_SHADOW_DEGRADED,
)


MODE_DEFAULT = "default"
MODE_INCLUDE_SHADOW = "include_shadow"
MODE_MANUAL_OVERRIDE = "manual_override"


@dataclass(frozen=True, slots=True)
class ProviderRuntimeBinding:
    provider_name: str
    provider_type: str
    adapter: SignalAdapter


@dataclass(frozen=True, slots=True)
class ProviderSelectionDecision:
    provider_name: str
    provider_type: str
    requested: bool
    allowed: bool
    portfolio_status: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ProviderSelectionResult:
    mode: str
    allowed_provider_names: list[str]
    rejected_provider_names: list[str]
    allowed_bindings: list[object]
    rejected: list[ProviderSelectionDecision] = field(default_factory=list)

    @property
    def allowed_sources(self) -> list[object]:
        return list(self.allowed_bindings)


class ProviderSelectionError(RuntimeError):
    def __init__(self, message: str, selection_result: ProviderSelectionResult) -> None:
        super().__init__(message)
        self.selection_result = selection_result


class ProviderSelectionGateway:
    def select(
        self,
        *,
        portfolio_report: ProviderPortfolioReport,
        bindings: list[object] | None = None,
        sources: list[object] | None = None,
        mode: str = MODE_DEFAULT,
        manual_allowlist: list[str] | None = None,
    ) -> ProviderSelectionResult:
        candidates = self._normalize_candidates(bindings=bindings, sources=sources)
        return self._select_impl(
            portfolio_report=portfolio_report,
            bindings=candidates,
            mode=mode,
            manual_allowlist=manual_allowlist,
            capabilities=current_execution_capabilities(),
        )

    def preview(
        self,
        *,
        portfolio_report: ProviderPortfolioReport,
        bindings: list[object] | None = None,
        sources: list[object] | None = None,
        mode: str = MODE_DEFAULT,
        manual_allowlist: list[str] | None = None,
        capabilities: set[str] | None = None,
    ) -> ProviderSelectionResult:
        candidates = self._normalize_candidates(bindings=bindings, sources=sources)
        return self._select_impl(
            portfolio_report=portfolio_report,
            bindings=candidates,
            mode=mode,
            manual_allowlist=manual_allowlist,
            capabilities=set() if capabilities is None else set(capabilities),
        )

    def _select_impl(
        self,
        *,
        portfolio_report: ProviderPortfolioReport,
        bindings: list[object],
        mode: str,
        manual_allowlist: list[str] | None,
        capabilities: set[str],
    ) -> ProviderSelectionResult:
        if mode not in {MODE_DEFAULT, MODE_INCLUDE_SHADOW, MODE_MANUAL_OVERRIDE}:
            raise ValueError(f"unsupported provider selection mode: {mode}")
        if mode == MODE_MANUAL_OVERRIDE and not manual_allowlist:
            raise ValueError("manual_override mode requires a non-empty manual_allowlist")

        entry_map = {entry.provider_name: entry for entry in portfolio_report.entries}
        allowset = set(manual_allowlist or [])
        allowed_bindings: list[object] = []
        rejected: list[ProviderSelectionDecision] = []

        for binding in bindings:
            provider_name = self._provider_name(binding)
            entry = entry_map.get(provider_name)
            status = None if entry is None else entry.portfolio_status
            allowed, reason = self._decide(
                binding=binding,
                entry=entry,
                mode=mode,
                allowset=allowset,
                capabilities=capabilities,
                portfolio_report=portfolio_report,
            )
            if allowed:
                allowed_bindings.append(binding)
            else:
                rejected.append(
                    ProviderSelectionDecision(
                        provider_name=provider_name,
                        provider_type=self._provider_type(binding),
                        requested=mode != MODE_DEFAULT or provider_name in portfolio_report.default_runtime_provider_names,
                        allowed=False,
                        portfolio_status=status,
                        reason=reason,
                    )
                )

        return ProviderSelectionResult(
            mode=mode,
            allowed_provider_names=[self._provider_name(binding) for binding in allowed_bindings],
            rejected_provider_names=[decision.provider_name for decision in rejected],
            allowed_bindings=allowed_bindings,
            rejected=rejected,
        )

    def _decide(
        self,
        *,
        binding: object,
        entry: ProviderPortfolioEntry | None,
        mode: str,
        allowset: set[str],
        capabilities: set[str],
        portfolio_report: ProviderPortfolioReport,
    ) -> tuple[bool, str]:
        if entry is None:
            return False, "provider is missing from portfolio report"

        status = entry.portfolio_status
        provider_name = self._provider_name(binding)

        if status == STATUS_RETIRED:
            if (
                mode == MODE_MANUAL_OVERRIDE
                and provider_name in allowset
                and CAP_PROVIDER_SELECT_MANUAL_OVERRIDE in capabilities
                and CAP_PROVIDER_SELECT_RETIRED_OVERRIDE in capabilities
            ):
                return True, "retired provider explicitly enabled by execution permit capability"
            return False, "retired providers are not selectable"

        if mode == MODE_DEFAULT:
            if provider_name in portfolio_report.default_runtime_provider_names:
                return True, "provider is in default runtime allowlist"
            return False, "provider is not in default runtime allowlist"

        if mode == MODE_INCLUDE_SHADOW:
            if CAP_PROVIDER_SELECT_INCLUDE_SHADOW not in capabilities:
                return False, "include_shadow mode requires execution permit capability"
            if status in {STATUS_PRODUCTION, STATUS_CANDIDATE, STATUS_SHADOW_ACTIVE, STATUS_SHADOW_DEGRADED}:
                return True, f"provider status '{status}' is allowed in include_shadow mode"
            return False, f"provider status '{status}' is not allowed in include_shadow mode"

        if mode == MODE_MANUAL_OVERRIDE:
            if CAP_PROVIDER_SELECT_MANUAL_OVERRIDE not in capabilities:
                return False, "manual_override mode requires execution permit capability"
            if provider_name not in allowset:
                return False, "provider is not in manual override allowlist"
            if status in {STATUS_PRODUCTION, STATUS_CANDIDATE, STATUS_SHADOW_ACTIVE, STATUS_SHADOW_DEGRADED}:
                return True, f"provider status '{status}' is allowed by manual override"
            return False, f"provider status '{status}' is not allowed by manual override"

        return False, "unsupported mode"

    def _normalize_candidates(
        self,
        *,
        bindings: list[object] | None,
        sources: list[object] | None,
    ) -> list[object]:
        if sources is not None:
            return list(sources)
        return [] if bindings is None else list(bindings)

    def _provider_name(self, binding: object) -> str:
        provider_name = getattr(binding, "provider_name", None)
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("provider selection candidates must expose a non-empty provider_name")
        return provider_name

    def _provider_type(self, binding: object) -> str:
        provider_type = getattr(binding, "provider_type", None)
        if not isinstance(provider_type, str) or not provider_type.strip():
            raise ValueError("provider selection candidates must expose a non-empty provider_type")
        return provider_type
