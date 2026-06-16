from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .binance_derivatives import sync_binance_derivatives_history
from .coinglass_derivatives import (
    has_coinglass_api_key,
    sync_coinglass_derivatives_history,
    write_coinglass_derivatives_sync_summary_for_as_of,
)
from .contracts import (
    QuantUniverseCandidate,
    QuantUniverseInput,
    QUANT_UNIVERSE_DEFINITION_ID,
    QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
    read_json,
    utc_now,
    write_json,
)


ROOT = Path(__file__).resolve().parents[3]
QUANT_ARTIFACTS_ROOT = ROOT / "artifacts" / "quant_research"
QUANT_INPUT_ROOT = QUANT_ARTIFACTS_ROOT / "_quant_inputs"
WORKBENCH_ROOT = ROOT / "artifacts" / "research_workbench"
QUANT_UNIVERSE_FALLBACK_MAX_AGE_DAYS = 0


def resolve_quant_input_path(*, as_of: str, quant_input_root: Path) -> Path:
    if not quant_input_root.exists():
        raise FileNotFoundError(f"quant input root not found: {quant_input_root}")
    candidate = (quant_input_root / f"pit-liquidity-top100-{as_of}.quant_universe.json").resolve()
    if not candidate.exists():
        raise FileNotFoundError(
            "point-in-time quant universe input not found for exact as_of date; expected: "
            f"{candidate}"
        )
    payload = QuantUniverseInput.from_payload(read_json(candidate))
    if payload.as_of != as_of:
        raise ValueError(f"quant universe input as_of={payload.as_of} does not match requested as_of={as_of}")
    return candidate


def run_quant_universe_freeze(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    universe_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=resolved_quant_input_root)
    universe_input = QuantUniverseInput.from_payload(read_json(universe_input_path))
    universe_candidates = universe_input.selected_candidates()
    universe_snapshot = build_universe_snapshot(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        input_path=universe_input_path,
        universe_input=universe_input,
        universe_candidates=universe_candidates,
    )
    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": utc_now(),
            "as_of": as_of,
            "source_input_path": str(universe_input_path),
            "source_input_as_of": universe_input.as_of,
            "source_input_age_days": 0,
            "fallback_applied": False,
            "candidate_count": len(universe_candidates),
            "contract_version": universe_input.contract_version,
            "universe_definition_id": universe_input.universe_definition_id,
            "universe_selection_policy_hash": universe_input.selection_policy_hash,
            "universe_snapshot_path": str(universe_snapshot["path"]),
            "input_watermarks": {
                "source_input_generated_at_utc": universe_input.generated_at_utc,
            },
            "upstream_versions": {
                "fallback_max_age_days": QUANT_UNIVERSE_FALLBACK_MAX_AGE_DAYS,
            },
        },
        evidence_family="quant_universe_freeze",
        contract_version="quant_universe_freeze.v2",
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    summary_path = resolved_artifacts_root / "cycles" / as_of / "universe_freeze_summary.json"
    write_json(summary_path, summary)
    summary["universe_freeze_summary_path"] = str(summary_path)
    return summary


def run_quant_derivatives_sync_cycle(
    *,
    as_of: str,
    quant_input_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    mode: str = "refresh",
    intervals: tuple[str, ...] = ("4h", "1d"),
    provider: str = "auto",
    symbols: Iterable[str] | None = None,
) -> dict[str, Any]:
    if provider not in {"auto", "binance", "coinglass"}:
        raise ValueError("provider must be one of: auto, binance, coinglass")
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    universe_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=resolved_quant_input_root)
    universe_input = QuantUniverseInput.from_payload(read_json(universe_input_path))
    universe_candidates = universe_input.selected_candidates()
    active_symbols = sorted(
        {
            str(candidate.usdm_symbol)
            for candidate in universe_candidates
            if candidate.usdm_symbol
        }
    )
    requested_symbols = (
        sorted({str(item).strip().upper() for item in symbols if str(item).strip()})
        if symbols is not None
        else active_symbols
    )
    if not requested_symbols:
        raise ValueError("no derivatives symbols resolved for quant sync cycle")
    resolved_provider = provider
    if resolved_provider == "auto":
        resolved_provider = "coinglass" if has_coinglass_api_key() else "binance"
    if resolved_provider == "coinglass":
        return sync_coinglass_derivatives_history(
            symbols=requested_symbols,
            intervals=intervals,
            mode=mode,
            as_of=as_of,
            external_root=derivatives_external_root,
        )
    return sync_binance_derivatives_history(
        symbols=requested_symbols,
        intervals=intervals,
        mode=mode,
        as_of=as_of,
        external_root=derivatives_external_root,
    )


def write_quant_derivatives_sync_summary_for_as_of(
    *,
    as_of: str,
    symbols: Iterable[str],
    intervals: tuple[str, ...] = ("4h", "1d"),
    derivatives_external_root: Path | None = None,
    provider: str = "auto",
) -> tuple[dict[str, Any], Path]:
    if provider not in {"auto", "binance", "coinglass"}:
        raise ValueError("provider must be one of: auto, binance, coinglass")
    resolved_provider = provider
    if resolved_provider == "auto":
        resolved_provider = "coinglass" if has_coinglass_api_key() else "binance"
    if resolved_provider == "coinglass":
        return write_coinglass_derivatives_sync_summary_for_as_of(
            as_of=as_of,
            symbols=symbols,
            intervals=intervals,
            external_root=derivatives_external_root,
        )
    from .binance_derivatives import write_derivatives_sync_summary_for_as_of

    return write_derivatives_sync_summary_for_as_of(
        as_of=as_of,
        symbols=symbols,
        intervals=intervals,
        external_root=derivatives_external_root,
    )


def load_quant_universe_snapshot(*, as_of: str, artifacts_root: Path) -> dict[str, Any]:
    path = artifacts_root / "universe" / as_of / "universe_snapshot.json"
    if not path.exists():
        raise FileNotFoundError(f"frozen quant universe snapshot not found: {path}")
    payload = read_json(path)
    payload["path"] = str(path)
    return payload


def build_universe_snapshot(
    *,
    as_of: str,
    artifacts_root: Path,
    input_path: Path,
    universe_input: QuantUniverseInput,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> dict[str, Any]:
    universe_root = artifacts_root / "universe" / as_of
    universe_root.mkdir(parents=True, exist_ok=True)
    selection_policy_hash = universe_input.selection_policy_hash
    snapshot = with_evidence_metadata(
        {
            "generated_at_utc": utc_now(),
            "status": "success",
            "success": True,
            "as_of": as_of,
            "contract_version": "quant_universe_snapshot.v2",
            "universe_contract_version": universe_input.contract_version,
            "universe_definition_id": universe_input.universe_definition_id,
            "source_input_path": str(input_path),
            "source_input_as_of": universe_input.as_of,
            "source_input_age_days": 0,
            "candidate_count": len(universe_candidates),
            "selection_policy": universe_input.selection_policy,
            "universe_selection_policy_hash": selection_policy_hash,
            "input_provenance": universe_input.input_provenance,
            "candidates": [
                {
                    **candidate.to_payload(),
                    "membership_reason": (
                        f"selected_rank_{candidate.selection_rank}_of_{universe_input.candidate_count_effective}"
                        f"_by_{candidate.selection_metric}"
                    ),
                    "ranking_window": {
                        "start_utc": candidate.selection_window_start_utc,
                        "end_utc": candidate.selection_window_end_utc,
                        "metric": candidate.selection_metric,
                        "score": candidate.selection_score,
                    },
                    "selection_policy_hash": selection_policy_hash,
                }
                for candidate in universe_candidates
            ],
            "input_watermarks": {
                "source_input_generated_at_utc": universe_input.generated_at_utc,
            },
            "upstream_versions": {
                "quant_universe_input_contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
                "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
            },
        },
        evidence_family="quant_universe_snapshot",
        contract_version="quant_universe_snapshot.v2",
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    path = universe_root / "universe_snapshot.json"
    write_json(path, snapshot)
    snapshot["path"] = str(path)
    return snapshot
