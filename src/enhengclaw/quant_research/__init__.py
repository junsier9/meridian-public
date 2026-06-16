from __future__ import annotations

from importlib import import_module


__all__ = (
    "run_baseline_alpha_proof",
    "run_baseline_alpha_survival",
    "run_eth_shadow_grid_daily_sample",
    "run_eth_shadow_grid_survival",
    "run_quant_hypothesis_batch_cycle",
    "run_quant_deterministic_daily_sample",
    "run_quantagent_shadow_proposal_cycle",
    "run_quant_research_cycle",
)

_LAZY_EXPORTS = {
    "run_baseline_alpha_proof": (".baseline_alpha_proof", "run_baseline_alpha_proof"),
    "run_baseline_alpha_survival": (".deterministic_survival", "run_baseline_alpha_survival"),
    "run_eth_shadow_grid_daily_sample": (".shadow_proposals", "run_eth_shadow_grid_daily_sample"),
    "run_eth_shadow_grid_survival": (".shadow_proposals", "run_eth_shadow_grid_survival"),
    "run_quant_hypothesis_batch_cycle": (".hypothesis_batch", "run_quant_hypothesis_batch_cycle"),
    "run_quant_deterministic_daily_sample": (".deterministic_survival", "run_quant_deterministic_daily_sample"),
    "run_quantagent_shadow_proposal_cycle": (".shadow_proposals", "run_quantagent_shadow_proposal_cycle"),
    "run_quant_research_cycle": (".lab", "run_quant_research_cycle"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
