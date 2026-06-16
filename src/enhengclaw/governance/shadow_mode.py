from __future__ import annotations

from dataclasses import dataclass, field

from enhengclaw.adapters.adapters import AdapterBatch, AdapterRequest, SignalAdapter, collect_and_validate_batches, merge_adapter_batches, validate_adapter_batch
from enhengclaw.core.signals import Signal


SHADOW_ONLY = "shadow_only"
PARTICIPATE_IN_RUNTIME = "participate_in_runtime"


@dataclass(slots=True)
class AdapterBinding:
    adapter: SignalAdapter
    mode: str = PARTICIPATE_IN_RUNTIME
    name: str | None = None


@dataclass(slots=True)
class ShadowCollectionResult:
    runtime_batches: list[AdapterBatch] = field(default_factory=list)
    runtime_signals: list[Signal] = field(default_factory=list)
    shadow_batches: list[AdapterBatch] = field(default_factory=list)
    shadow_signals: list[Signal] = field(default_factory=list)


def collect_bound_batches(bindings: list[AdapterBinding], request: AdapterRequest) -> ShadowCollectionResult:
    runtime_adapters = [binding.adapter for binding in bindings if binding.mode == PARTICIPATE_IN_RUNTIME]
    shadow_adapters = [binding.adapter for binding in bindings if binding.mode == SHADOW_ONLY]

    runtime_batches = collect_and_validate_batches(runtime_adapters, request) if runtime_adapters else []
    shadow_batches: list[AdapterBatch] = []
    for adapter in shadow_adapters:
        batch = adapter.collect(request)
        validate_adapter_batch(batch, request)
        shadow_batches.append(batch)

    return ShadowCollectionResult(
        runtime_batches=runtime_batches,
        runtime_signals=merge_adapter_batches(runtime_batches),
        shadow_batches=shadow_batches,
        shadow_signals=merge_adapter_batches(shadow_batches),
    )
