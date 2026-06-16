from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
AS_OF = "2026-05-04"

SUMMARY_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_backfill_summary.json"
OVERLAP_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_overlap_validation.json"
HORIZON_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_history_horizon_probe_2026-05-04.json"
CAPABILITY_PATH = ROOT / "artifacts" / "quant_research" / "provider_smoke" / "coinglass_capability_matrix.json"
UNIVERSE_PATH = ROOT / "artifacts" / "quant_research" / "_quant_inputs" / "pit-liquidity-top100-2026-05-04.quant_universe.json"
STRICT_CONCORDANCE_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_strict_concordance_2026-05-04.json"
QUARANTINE_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_concordance_quarantine_2026-05-04.json"
OI_AUDIT_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_oi_provenance_audit_2026-05-04.json"
OI_SIDECAR_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_oi_provenance_sidecar_sync_2026-05-04.json"
OI_COMPILER_INTEGRATION_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_oi_compiler_integration_2026-05-04.json"
DATASET_FEATURE_SMOKE_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_dataset_feature_smoke_2026-05-04.json"
SPOT_1D_QUARANTINE_SMOKE_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_spot_1d_quarantine_smoke_2026-05-04.json"
H10D_PARENT_REBASELINE_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_h10d_parent_rebaseline_2026-05-04.json"
H10D_PARENT_DRIFT_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_h10d_parent_drift_2026-05-06.json"
H10D_PARENT_STRICT_CYCLE_PROBE_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_h10d_parent_strict_cycle_probe_2026-05-06.json"
H10D_PARENT_FROZEN_RESET_STRICT_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_h10d_parent_frozen_reset_strict_2026-05-06.json"

JSON_OUT = ROOT / "artifacts" / "quant_research" / "coinglass" / "coinglass_coverage_reset_2026-05-04.json"
REPORT_OUT = ROOT / "artifacts" / "quant_research" / "reports" / "coinglass_coverage_reset_2026-05-04.md"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_has_perp(candidate: dict[str, Any]) -> bool:
    return bool(candidate.get("usdm_symbol") and candidate.get("first_perp_bar_utc"))


def _symbol_set(items: list[dict[str, Any]], key: str = "symbol") -> set[str]:
    return {str(item[key]) for item in items if item.get(key)}


def _pct(numerator: int | float, denominator: int | float) -> str:
    if not denominator:
        return "n/a"
    return f"{(float(numerator) / float(denominator)):.2%}"


def build_payload() -> dict[str, Any]:
    summary = _load(SUMMARY_PATH)
    overlap = _load(OVERLAP_PATH)
    horizon = _load(HORIZON_PATH)
    capability = _load(CAPABILITY_PATH)
    universe = _load(UNIVERSE_PATH)
    strict_concordance = _load(STRICT_CONCORDANCE_PATH) if STRICT_CONCORDANCE_PATH.exists() else None
    quarantine = _load(QUARANTINE_PATH) if QUARANTINE_PATH.exists() else None
    oi_audit = _load(OI_AUDIT_PATH) if OI_AUDIT_PATH.exists() else None
    oi_sidecar = _load(OI_SIDECAR_PATH) if OI_SIDECAR_PATH.exists() else None
    oi_compiler_integration = (
        _load(OI_COMPILER_INTEGRATION_PATH) if OI_COMPILER_INTEGRATION_PATH.exists() else None
    )
    dataset_feature_smoke = _load(DATASET_FEATURE_SMOKE_PATH) if DATASET_FEATURE_SMOKE_PATH.exists() else None
    spot_1d_quarantine_smoke = (
        _load(SPOT_1D_QUARANTINE_SMOKE_PATH) if SPOT_1D_QUARANTINE_SMOKE_PATH.exists() else None
    )
    h10d_parent_rebaseline = (
        _load(H10D_PARENT_REBASELINE_PATH) if H10D_PARENT_REBASELINE_PATH.exists() else None
    )
    h10d_parent_drift = _load(H10D_PARENT_DRIFT_PATH) if H10D_PARENT_DRIFT_PATH.exists() else None
    h10d_parent_strict_cycle_probe = (
        _load(H10D_PARENT_STRICT_CYCLE_PROBE_PATH) if H10D_PARENT_STRICT_CYCLE_PROBE_PATH.exists() else None
    )
    h10d_parent_frozen_reset_strict = (
        _load(H10D_PARENT_FROZEN_RESET_STRICT_PATH) if H10D_PARENT_FROZEN_RESET_STRICT_PATH.exists() else None
    )

    candidates = list(universe.get("candidates") or [])
    sync_results = list(summary.get("sync_results") or [])
    overlap_results = list(overlap.get("results") or [])
    horizon_results = list(horizon.get("results") or [])

    full_symbols = [str(item.get("spot_symbol") or item.get("symbol")) for item in candidates]
    full_symbols = [symbol for symbol in full_symbols if symbol]
    executable_symbols = [
        str(item.get("spot_symbol") or item.get("symbol"))
        for item in candidates
        if _candidate_has_perp(dict(item))
    ]
    top_mid_executable_symbols = [
        str(item.get("spot_symbol") or item.get("symbol"))
        for item in candidates
        if item.get("liquidity_bucket") in {"top_liquidity", "mid_liquidity"} and _candidate_has_perp(dict(item))
    ]

    synced_symbols = _symbol_set(sync_results)
    success_symbols = {str(item["symbol"]) for item in sync_results if item.get("status") == "success"}
    short_listing_symbols = [
        str(item["symbol"])
        for item in sync_results
        if int(item.get("requested_expected_rows") or 0) < 24 * 180
    ]
    gap_symbols = [
        {
            "symbol": str(item["symbol"]),
            "gap_count": int(item.get("gap_count") or 0),
            "requested_completeness": item.get("requested_completeness"),
        }
        for item in sync_results
        if int(item.get("gap_count") or 0) > 0
    ]
    lowest_completeness = sorted(
        [
            {
                "symbol": str(item["symbol"]),
                "status": item.get("status"),
                "requested_expected_rows": item.get("requested_expected_rows"),
                "requested_observed_rows": item.get("requested_observed_rows"),
                "requested_completeness": item.get("requested_completeness"),
                "gap_count": item.get("gap_count"),
            }
            for item in sync_results
        ],
        key=lambda item: float(item.get("requested_completeness") or 0.0),
    )[:12]

    missing_executable_perp = [
        str(item.get("spot_symbol") or item.get("symbol"))
        for item in candidates
        if not _candidate_has_perp(dict(item))
    ]

    horizon_counts: dict[str, dict[str, int]] = {}
    for scope_name, symbols in {
        "full_99": set(full_symbols),
        "all_executable_perp": set(executable_symbols),
        "top_mid_executable_perp": set(top_mid_executable_symbols),
    }.items():
        scoped = [item for item in horizon_results if str(item.get("symbol")) in symbols]
        horizon_counts[scope_name] = {
            "symbol_count": len(scoped),
            "d720_available_count": sum(1 for item in scoped if int(item.get("d720_rows") or 0) > 0),
            "d700_available_count": sum(1 for item in scoped if int(item.get("d700_rows") or 0) > 0),
            "d365_available_count": sum(1 for item in scoped if int(item.get("d365_rows") or 0) > 0),
            "d180_available_count": sum(1 for item in scoped if int(item.get("d180_rows") or 0) > 0),
        }

    status_counts = Counter(str(item.get("status")) for item in overlap_results)
    live_check_symbol_counts = Counter()
    live_fail_symbols: list[dict[str, Any]] = []
    for item in overlap_results:
        checks = list(item.get("live_binance_checks") or [])
        pass_count = sum(1 for check in checks if check.get("status") == "pass")
        fail_count = sum(1 for check in checks if check.get("status") == "fail")
        if checks and fail_count == 0:
            live_check_symbol_counts["all_live_samples_pass"] += 1
        elif checks and pass_count > 0 and fail_count > 0:
            live_check_symbol_counts["mixed_live_samples"] += 1
        elif checks and pass_count == 0 and fail_count > 0:
            live_check_symbol_counts["all_live_samples_fail"] += 1
        max_rel = max(
            (float(check["rel_diff"]) for check in checks if check.get("rel_diff") is not None),
            default=None,
        )
        if fail_count:
            live_fail_symbols.append(
                {
                    "symbol": item.get("symbol"),
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "max_live_rel_diff": max_rel,
                }
            )
    live_fail_symbols.sort(key=lambda item: float(item.get("max_live_rel_diff") or 0.0), reverse=True)

    endpoint_counts = dict(capability.get("classification_counts") or {})

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "as_of": AS_OF,
        "inputs": {
            "summary_path": str(SUMMARY_PATH),
            "overlap_path": str(OVERLAP_PATH),
            "horizon_path": str(HORIZON_PATH),
            "capability_path": str(CAPABILITY_PATH),
            "universe_path": str(UNIVERSE_PATH),
            "strict_concordance_path": str(STRICT_CONCORDANCE_PATH) if strict_concordance else None,
            "quarantine_path": str(QUARANTINE_PATH) if quarantine else None,
            "oi_audit_path": str(OI_AUDIT_PATH) if oi_audit else None,
            "oi_sidecar_path": str(OI_SIDECAR_PATH) if oi_sidecar else None,
            "oi_compiler_integration_path": str(OI_COMPILER_INTEGRATION_PATH)
            if oi_compiler_integration
            else None,
            "dataset_feature_smoke_path": str(DATASET_FEATURE_SMOKE_PATH) if dataset_feature_smoke else None,
            "spot_1d_quarantine_smoke_path": str(SPOT_1D_QUARANTINE_SMOKE_PATH)
            if spot_1d_quarantine_smoke
            else None,
            "h10d_parent_rebaseline_path": str(H10D_PARENT_REBASELINE_PATH)
            if h10d_parent_rebaseline
            else None,
            "h10d_parent_drift_path": str(H10D_PARENT_DRIFT_PATH) if h10d_parent_drift else None,
            "h10d_parent_strict_cycle_probe_path": str(H10D_PARENT_STRICT_CYCLE_PROBE_PATH)
            if h10d_parent_strict_cycle_probe
            else None,
            "h10d_parent_frozen_reset_strict_path": str(H10D_PARENT_FROZEN_RESET_STRICT_PATH)
            if h10d_parent_frozen_reset_strict
            else None,
        },
        "full_panel": {
            "candidate_count": len(full_symbols),
            "coinglass_spot_1h_180d_success_count": len(success_symbols & set(full_symbols)),
            "coinglass_spot_1h_180d_synced_count": len(synced_symbols & set(full_symbols)),
            "min_requested_completeness": summary.get("min_requested_completeness"),
            "missing_spot_symbols_after_reset": sorted(set(full_symbols) - success_symbols),
        },
        "strategy_scopes": {
            "all_executable_perp": {
                "candidate_count": len(executable_symbols),
                "spot_success_count": len(success_symbols & set(executable_symbols)),
                "coverage_pct": _pct(len(success_symbols & set(executable_symbols)), len(executable_symbols)),
            },
            "top_mid_executable_perp": {
                "candidate_count": len(top_mid_executable_symbols),
                "spot_success_count": len(success_symbols & set(top_mid_executable_symbols)),
                "coverage_pct": _pct(len(success_symbols & set(top_mid_executable_symbols)), len(top_mid_executable_symbols)),
            },
        },
        "horizon_probe_counts": horizon_counts,
        "symbol_failure_reasons": {
            "true_listing_too_short": short_listing_symbols,
            "missing_spot_after_reset": sorted(set(full_symbols) - success_symbols),
            "missing_executable_perp": missing_executable_perp,
            "alias_or_multiplier_unresolved": "pending CG-2 derivatives/OI mapping",
            "derivatives_field_missing": "pending CG-2 derivatives/OI mapping",
            "provider_conflict_or_concordance_risk": live_fail_symbols,
            "spot_gap_symbols": gap_symbols,
        },
        "provider_concordance": {
            "status_counts": dict(status_counts),
            "live_check_symbol_counts": dict(live_check_symbol_counts),
            "local_overlap_symbol_count": overlap.get("overlap_symbol_count"),
            "local_fail_symbol_count": overlap.get("fail_symbol_count"),
            "material_rel_diff_threshold": overlap.get("material_rel_diff_threshold"),
            "top_live_fail_symbols": live_fail_symbols[:20],
            "strict_ohlc": None
            if strict_concordance is None
            else {
                "status_counts": strict_concordance.get("status_counts"),
                "pass_symbol_count": strict_concordance.get("pass_symbol_count"),
                "fail_symbol_count": strict_concordance.get("fail_symbol_count"),
                "exclude_tail_hours": strict_concordance.get("exclude_tail_hours"),
                "rel_threshold": strict_concordance.get("rel_threshold"),
                "top_fail_symbols": [
                    {
                        "symbol": item.get("symbol"),
                        "material_diff_count": item.get("material_diff_count"),
                        "max_rel_diff": item.get("max_rel_diff"),
                    }
                    for item in sorted(
                        list(strict_concordance.get("results") or []),
                        key=lambda entry: float(entry.get("max_rel_diff") or 0.0),
                        reverse=True,
                    )[:20]
                    if item.get("status") != "pass"
                ],
            },
        },
        "spot_price_policy": {
            "canonical_ohlc_source": "binance_spot_ohlcv",
            "coinglass_spot_ohlc_policy": "quarantined_not_canonical",
            "quarantine_counts": None if quarantine is None else quarantine.get("classification_counts"),
        },
        "oi_provenance": {
            "native_oi_symbol_count": None
            if oi_audit is None
            else int((oi_audit.get("provenance_counts") or {}).get("native_usd_preferred", 0) or 0),
            "derived_oi_symbol_count": None
            if oi_audit is None
            else int((oi_audit.get("provenance_counts") or {}).get("derived_usd_required", 0) or 0),
            "missing_oi_symbol_count": None
            if oi_audit is None
            else int((oi_audit.get("provenance_counts") or {}).get("missing_oi", 0) or 0),
            "status": (
                "native_usd_sidecar_synced_formula_warnings"
                if oi_sidecar
                else "availability_audit_pass_sidecar_sync_pending"
                if oi_audit
                else "blocked_pending_CG2"
            ),
            "canonical_price_source_for_derivation": None
            if oi_audit is None
            else oi_audit.get("canonical_price_source_for_derivation"),
            "native_oi_policy": None if oi_audit is None else oi_audit.get("native_oi_policy"),
            "derived_oi_policy": None if oi_audit is None else oi_audit.get("derived_oi_policy"),
            "derived_native_formula_counts": None
            if oi_audit is None
            else oi_audit.get("derived_native_formula_counts"),
            "formula_fail_symbols": []
            if oi_audit is None
            else [
                item.get("symbol")
                for item in list(oi_audit.get("results") or [])
                if (item.get("derived_native_formula_check") or {}).get("status") == "fail"
            ],
            "sidecar_data_success_count": None if oi_sidecar is None else oi_sidecar.get("data_success_count"),
            "sidecar_formula_clean_count": None if oi_sidecar is None else oi_sidecar.get("formula_clean_count"),
            "sidecar_formula_warning_count": None if oi_sidecar is None else oi_sidecar.get("formula_warning_count"),
            "sidecar_error_count": None if oi_sidecar is None else oi_sidecar.get("error_count"),
            "sidecar_formula_fail_symbol_count": None
            if oi_sidecar is None
            else len(list(oi_sidecar.get("formula_fail_symbols") or [])),
            "compiler_integration_status": None
            if oi_compiler_integration is None
            else oi_compiler_integration.get("status"),
            "compiler_integration_interval_summary": None
            if oi_compiler_integration is None
            else oi_compiler_integration.get("interval_summary"),
            "compiler_integration_policy": None
            if oi_compiler_integration is None
            else oi_compiler_integration.get("integration_policy"),
        },
        "dataset_feature_smoke": _summarize_dataset_feature_smoke(dataset_feature_smoke),
        "spot_1d_quarantine_smoke": _summarize_dataset_feature_smoke(spot_1d_quarantine_smoke),
        "h10d_parent_rebaseline": _summarize_h10d_parent_rebaseline(h10d_parent_rebaseline),
        "h10d_parent_drift": _summarize_h10d_parent_drift(h10d_parent_drift),
        "h10d_parent_strict_cycle_probe": _summarize_h10d_parent_strict_cycle_probe(
            h10d_parent_strict_cycle_probe
        ),
        "h10d_parent_frozen_reset_strict": _summarize_h10d_parent_frozen_reset_strict(
            h10d_parent_frozen_reset_strict
        ),
        "endpoint_classification_counts": endpoint_counts,
        "decision": {
            "spot_coverage_reset": "pass_for_full_99_1h_180d",
            "provider_concordance": "fail_closed_on_strict_ohlc_concordance"
            if strict_concordance and int(strict_concordance.get("fail_symbol_count") or 0) > 0
            else "fail_closed_pending_tail_bar_and_provider_definition_audit",
            "alpha_rerun_allowed": False,
            "next_required_stage": (
                "R-1 frozen reset strict validation failed closed on the same reset feature matrix: fast-reject passed and the h10d validation contract passed, but the alpha experiment card is no-go. Promotion remains blocked; inspect cost/delay stress, liquidity bucket consistency, symbol holdout, and legacy-only effective blockers before any optimization."
                if h10d_parent_frozen_reset_strict
                and str(h10d_parent_frozen_reset_strict.get("status") or "").startswith(
                    "fail_closed_frozen_reset_strict_validation"
                )
                else
                "R-1 frozen reset strict validation passed on the same reset feature matrix. Next run overlay-ablation/falsification sidecars plus the promotion guard; provider concordance still keeps alpha promotion blocked until strict OHLC trust clears."
                if h10d_parent_frozen_reset_strict
                and str(h10d_parent_frozen_reset_strict.get("status") or "").startswith(
                    "pass_frozen_reset_strict_validation"
                )
                else
                "R-1 strict cycle probe failed closed because the fresh strict cycle rebuilt a different and shorter feature matrix than the passing reset stage replay. Next align strict validation to the frozen reset feature matrix, or rebuild the reset matrix from a documented canonical Binance OHLC root with the same history span before interpreting parent alpha drift."
                if h10d_parent_strict_cycle_probe
                and str(h10d_parent_strict_cycle_probe.get("status") or "").startswith(
                    "fail_closed_strict_cycle_input_matrix_drift"
                )
                else
                "R-1 2026-05-04 reset official fast-reject replay passed on the non-overwriting reset root. Next run strict validation, falsification, overlay-ablation sidecars, and promotion guard using Binance-canonical OHLC plus native USD OI; alpha promotion remains blocked until those gates pass."
                if h10d_parent_drift
                and str(h10d_parent_drift.get("status") or "").startswith(
                    "pass_2026_05_04_reset_official_fast_reject_replayed"
                )
                else
                "R-1 2026-04-29 parent fast-reject is reproduced, but the 2026-05-04 reset official replay aborted after backtests_ready before walk_forward_ready/official_fast_reject_written. Debug that replay abort and rerun before R-2 or any strict/promotion gate."
                if h10d_parent_drift
                and str(h10d_parent_drift.get("status") or "").startswith(
                    "fail_closed_2026_05_04_official_fast_reject_replay_incomplete"
                )
                else
                "R-1 2026-04-29 h10d parent fast-reject is reproduced on a non-overwriting replay root. Next run the same official fast-reject replay for the 2026-05-04 reset root, then run strict validation/falsification only if that reset replay passes."
                if h10d_parent_drift
                and "reset_rebaseline_pending" in str(h10d_parent_drift.get("status") or "")
                else
                "R-1 parent drift audit found a reproducibility break: the historical 2026-04-29 fast-reject pass points at a mutable feature artifact whose current manifest was produced after the report. Freeze immutable feature-matrix/hash sidecars and rerun official fast-reject on a non-overwriting artifact root before R-2 intraday feasibility or any alpha promotion."
                if h10d_parent_drift
                and str(h10d_parent_drift.get("status") or "").startswith("fail_closed")
                else "R-1 canonical parent rebaseline failed pre-strict on Binance-canonical OHLC plus native USD OI sidecar; do not run alpha promotion. Next diagnose parent/universe drift and only then proceed to R-2 intraday feasibility."
                if h10d_parent_rebaseline
                and str(h10d_parent_rebaseline.get("status") or "").startswith("fail_closed")
                else "Canonical Binance daily-lane coverage is repaired; CoinGlass spot 1h/4h/1d remains quarantine-only, so the next work is a non-promotion alpha diagnostic or strict falsification run using Binance OHLC plus native USD OI sidecar"
            ),
        },
        "lowest_completeness_symbols": lowest_completeness,
    }
    return payload


def _summarize_dataset_feature_smoke(smoke: dict[str, Any] | None) -> dict[str, Any] | None:
    if smoke is None:
        return None
    return {
        "status": smoke.get("status"),
        "alpha_rerun_allowed": smoke.get("alpha_rerun_allowed"),
        "alpha_blockers": smoke.get("alpha_blockers"),
        "canonical_input_policy": smoke.get("canonical_input_policy"),
        "dataset_summaries": [
            {
                "dataset_id": item.get("dataset_id"),
                "dataset_profile": item.get("dataset_profile"),
                "row_count": item.get("row_count"),
                "subject_count": item.get("subject_count"),
                "dataset_lane_eligible": item.get("dataset_lane_eligible"),
                "data_gap_blockers": item.get("data_gap_blockers"),
                "missing_spot_symbols_by_interval": {
                    str(interval): len(list(symbols or []))
                    for interval, symbols in dict(item.get("missing_spot_symbols_by_interval") or {}).items()
                },
                "oi_native_usd_row_count": (item.get("oi_sidecar") or {}).get("native_usd_row_count"),
                "bad_oi_policy_row_count": item.get("bad_oi_policy_row_count"),
                "sidecar_fingerprint_families": (item.get("research_dataset") or {}).get(
                    "sidecar_fingerprint_families"
                ),
            }
            for item in list(smoke.get("dataset_summaries") or [])
        ],
        "feature_summaries": [
            {
                "feature_set_id": item.get("feature_set_id"),
                "dataset_profile": item.get("dataset_profile"),
                "row_count": item.get("row_count"),
                "numeric_feature_count": item.get("numeric_feature_count"),
                "target_horizon_bars": item.get("target_horizon_bars"),
                "oi_ready_fraction": (
                    ((item.get("derivatives_feature_quality") or {}).get("oi_change_5") or {}).get(
                        "row_ready_fraction"
                    )
                ),
                "oi_subject_ready_count": (
                    ((item.get("derivatives_feature_quality") or {}).get("oi_change_5") or {}).get(
                        "subject_ready_count"
                    )
                ),
            }
            for item in list(smoke.get("feature_summaries") or [])
        ],
    }


def _summarize_h10d_parent_rebaseline(audit: dict[str, Any] | None) -> dict[str, Any] | None:
    if audit is None:
        return None
    return {
        "status": audit.get("status"),
        "decision": audit.get("decision"),
        "alpha_rerun_allowed": audit.get("alpha_rerun_allowed"),
        "promotion_allowed": audit.get("promotion_allowed"),
        "candidate_id": audit.get("candidate_id"),
        "feature_set_id": audit.get("feature_set_id"),
        "feature_rows": audit.get("feature_rows"),
        "feature_subject_count": audit.get("feature_subject_count"),
        "selected_feature_count": audit.get("selected_feature_count"),
        "universe_filter": audit.get("universe_filter"),
        "universe_filtered_rows": audit.get("universe_filtered_rows"),
        "universe_filtered_subject_count": audit.get("universe_filtered_subject_count"),
        "execution_filtered_rows": audit.get("execution_filtered_rows"),
        "execution_filtered_subject_count": audit.get("execution_filtered_subject_count"),
        "split_row_counts": audit.get("split_row_counts"),
        "validation_metrics": audit.get("validation_metrics"),
        "test_metrics": audit.get("test_metrics"),
        "factor_evidence_lite": audit.get("factor_evidence_lite"),
        "blocker_codes": audit.get("blocker_codes"),
        "full_walk_forward_status": audit.get("full_walk_forward_status"),
        "canonical_input_policy": audit.get("canonical_input_policy"),
    }


def _summarize_h10d_parent_drift(audit: dict[str, Any] | None) -> dict[str, Any] | None:
    if audit is None:
        return None
    historical = dict(audit.get("historical_report") or {})
    manifest = dict(audit.get("referenced_feature_manifest_current_state") or {})
    interpretation = dict(audit.get("interpretation") or {})
    reproducibility_break = dict(audit.get("reproducibility_break") or {})
    return {
        "status": audit.get("status"),
        "decision": audit.get("decision"),
        "alpha_rerun_allowed": audit.get("alpha_rerun_allowed"),
        "promotion_allowed": audit.get("promotion_allowed"),
        "historical_fast_reject_produced_at_utc": historical.get("produced_at_utc"),
        "current_feature_manifest_produced_at_utc": manifest.get("produced_at_utc"),
        "feature_matrix_sha256": manifest.get("feature_matrix_sha256"),
        "feature_hash": manifest.get("feature_hash"),
        "artifact_overwritten_after_report": reproducibility_break.get("artifact_overwritten_after_report"),
        "overwrite_lag_minutes": reproducibility_break.get("overwrite_lag_minutes"),
        "primary_blocker": interpretation.get("primary_blocker"),
        "provenance_observation": interpretation.get("provenance_observation"),
        "secondary_observation": interpretation.get("secondary_observation"),
        "next_gate": interpretation.get("next_gate"),
        "metric_deltas": audit.get("metric_deltas"),
        "subject_drift": audit.get("subject_drift"),
        "immutable_replay": audit.get("immutable_replay"),
        "reset_official_stage_audit": audit.get("reset_official_stage_audit"),
        "historical_metrics": historical.get("metrics"),
        "reference_replay_metrics": (audit.get("reference_replay_current_artifact") or {}).get("metrics"),
        "reset_replay_metrics": (audit.get("reset_replay_current_artifact") or {}).get("metrics"),
    }


def _summarize_h10d_parent_strict_cycle_probe(audit: dict[str, Any] | None) -> dict[str, Any] | None:
    if audit is None:
        return None
    interpretation = dict(audit.get("interpretation") or {})
    stage = dict(audit.get("stage_replay") or {})
    fresh = dict(audit.get("fresh_strict_cycle") or {})
    return {
        "status": audit.get("status"),
        "decision": audit.get("decision"),
        "alpha_rerun_allowed": audit.get("alpha_rerun_allowed"),
        "promotion_allowed": audit.get("promotion_allowed"),
        "primary_blocker": interpretation.get("primary_blocker"),
        "next_gate": interpretation.get("next_gate"),
        "diff": audit.get("diff"),
        "stage_fast_reject": stage.get("fast_reject"),
        "fresh_fast_reject": fresh.get("fast_reject"),
        "fresh_batch_summary": fresh.get("batch_summary"),
    }


def _summarize_h10d_parent_frozen_reset_strict(audit: dict[str, Any] | None) -> dict[str, Any] | None:
    if audit is None:
        return None
    frozen = dict(audit.get("frozen_feature_matrix") or {})
    strict_result = dict(audit.get("strict_result") or {})
    experiment = dict(audit.get("experiment") or {})
    quality = dict(audit.get("reconstructed_quality_check") or {})
    return {
        "status": audit.get("status"),
        "decision": audit.get("decision"),
        "alpha_rerun_allowed": audit.get("alpha_rerun_allowed"),
        "promotion_allowed": audit.get("promotion_allowed"),
        "feature_set_id": frozen.get("feature_set_id"),
        "feature_rows": frozen.get("feature_rows"),
        "feature_subject_count": frozen.get("feature_subject_count"),
        "feature_hash": frozen.get("feature_hash"),
        "feature_matrix_sha256": frozen.get("feature_matrix_sha256"),
        "dataset_fingerprint": frozen.get("dataset_fingerprint"),
        "derivatives_quality_matches_manifest": quality.get("derivatives_quality_matches_manifest"),
        "strict_validation_passed": strict_result.get("strict_validation_passed"),
        "validation_contract_status": strict_result.get("validation_contract_status"),
        "falsification_status": strict_result.get("falsification_status"),
        "statistical_falsification_status": strict_result.get("statistical_falsification_status"),
        "alpha_experiment_card_status": strict_result.get("alpha_experiment_card_status"),
        "alpha_experiment_card_go_no_go": strict_result.get("alpha_experiment_card_go_no_go"),
        "alpha_experiment_card_blocker_codes": strict_result.get("alpha_experiment_card_blocker_codes"),
        "credible_research_evidence": strict_result.get("credible_research_evidence"),
        "validation_metrics": experiment.get("validation_metrics"),
        "test_metrics": experiment.get("test_metrics"),
        "strict_result_path": strict_result.get("path"),
        "next_gate": audit.get("next_gate"),
    }


def _fmt_list(items: list[Any], *, max_items: int = 20) -> str:
    if not items:
        return "none"
    shown = [str(item) for item in items[:max_items]]
    suffix = "" if len(items) <= max_items else f" ... +{len(items) - max_items} more"
    return ", ".join(shown) + suffix


def render_report(payload: dict[str, Any]) -> str:
    full = payload["full_panel"]
    scopes = payload["strategy_scopes"]
    decision = payload["decision"]
    reasons = payload["symbol_failure_reasons"]
    concordance = payload["provider_concordance"]
    horizon = payload["horizon_probe_counts"]
    oi = payload["oi_provenance"]
    spot_price_policy = payload["spot_price_policy"]
    dataset_smoke = payload.get("dataset_feature_smoke")
    spot_quarantine_smoke = payload.get("spot_1d_quarantine_smoke")
    h10d_parent_rebaseline = payload.get("h10d_parent_rebaseline")
    h10d_parent_drift = payload.get("h10d_parent_drift")
    h10d_parent_strict_cycle_probe = payload.get("h10d_parent_strict_cycle_probe")
    h10d_parent_frozen_reset_strict = payload.get("h10d_parent_frozen_reset_strict")

    lines = [
        "# CoinGlass Coverage Reset 2026-05-04",
        "",
        f"`Generated at UTC: {payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Spot coverage reset: `{decision['spot_coverage_reset']}`.",
        f"- Provider concordance: `{decision['provider_concordance']}`.",
        f"- Canonical spot OHLC source: `{spot_price_policy['canonical_ohlc_source']}`.",
        f"- CoinGlass spot OHLC policy: `{spot_price_policy['coinglass_spot_ohlc_policy']}`.",
        f"- R-1 h10d parent rebaseline: `{None if h10d_parent_rebaseline is None else h10d_parent_rebaseline.get('status')}`.",
        f"- R-1 h10d parent drift audit: `{None if h10d_parent_drift is None else h10d_parent_drift.get('status')}`.",
        f"- R-1 h10d strict cycle probe: `{None if h10d_parent_strict_cycle_probe is None else h10d_parent_strict_cycle_probe.get('status')}`.",
        f"- R-1 h10d frozen reset strict: `{None if h10d_parent_frozen_reset_strict is None else h10d_parent_frozen_reset_strict.get('status')}`.",
        f"- Alpha rerun allowed: `{decision['alpha_rerun_allowed']}`.",
        f"- Next required stage: `{decision['next_required_stage']}`.",
        "",
        "## Coverage",
        "",
        "| scope | before reset | after reset | note |",
        "| --- | ---: | ---: | --- |",
        (
            f"| full 99 spot 1h/180d | CG-0 only; no canonical full cache | "
            f"{full['coinglass_spot_1h_180d_success_count']} / {full['candidate_count']} | "
            f"min requested completeness `{full['min_requested_completeness']}` |"
        ),
        (
            "| all executable perp spot 1h/180d | not canonically reset | "
            f"{scopes['all_executable_perp']['spot_success_count']} / {scopes['all_executable_perp']['candidate_count']} "
            f"({scopes['all_executable_perp']['coverage_pct']}) | spot leg only |"
        ),
        (
            "| top/mid executable perp spot 1h/180d | prior narrow run only | "
            f"{scopes['top_mid_executable_perp']['spot_success_count']} / {scopes['top_mid_executable_perp']['candidate_count']} "
            f"({scopes['top_mid_executable_perp']['coverage_pct']}) | spot leg only |"
        ),
        "",
        "## Horizon Probe",
        "",
        "| scope | symbols | 720d | 700d | 365d | 180d |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scope_name, item in horizon.items():
        lines.append(
            f"| {scope_name} | {item['symbol_count']} | {item['d720_available_count']} | "
            f"{item['d700_available_count']} | {item['d365_available_count']} | {item['d180_available_count']} |"
        )
    lines.extend(
        [
            "",
            "720d remains rejected as a canonical horizon because the live spot history probe returned zero exact 720d hits across the scoped panel. 180d/listing-aware is the only coverage reset accepted in this report.",
            "",
            "## Provider Concordance",
            "",
            f"- Local overlap symbols: `{concordance['local_overlap_symbol_count']}`.",
            f"- Local hard fail symbols: `{concordance['local_fail_symbol_count']}`.",
            f"- Status counts: `{concordance['status_counts']}`.",
            f"- Live sample symbol buckets: `{concordance['live_check_symbol_counts']}`.",
            f"- Material relative-diff threshold: `{concordance['material_rel_diff_threshold']}`.",
            "",
            "The local Binance cache is too sparse to prove full-panel concordance. Live Binance samples confirm many early/mid history points, but trailing samples show broad small close-price divergence and a few material conflicts. Treat this as a provider-definition/tail-bar audit blocker, not as alpha evidence.",
            "",
            "Top live concordance risks:",
            "",
            "| symbol | pass checks | fail checks | max live rel diff |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in concordance["top_live_fail_symbols"][:12]:
        lines.append(
            f"| {item['symbol']} | {item['pass_count']} | {item['fail_count']} | {item['max_live_rel_diff']} |"
        )
    if not concordance["top_live_fail_symbols"]:
        lines.append("| none | 0 | 0 | 0 |")
    strict = concordance.get("strict_ohlc")
    if strict:
        lines.extend(
            [
                "",
                "Strict OHLC concordance after full Binance baseline:",
                "",
                f"- Pass symbols: `{strict['pass_symbol_count']}`.",
                f"- Fail symbols: `{strict['fail_symbol_count']}`.",
                f"- Excluded tail hours: `{strict['exclude_tail_hours']}`.",
                f"- Relative threshold: `{strict['rel_threshold']}`.",
                f"- Status counts: `{strict['status_counts']}`.",
                "",
                "| symbol | material diffs | max rel diff |",
                "| --- | ---: | ---: |",
            ]
        )
        for item in strict["top_fail_symbols"][:12]:
            lines.append(f"| {item['symbol']} | {item['material_diff_count']} | {item['max_rel_diff']} |")
    if spot_price_policy.get("quarantine_counts"):
        lines.extend(
            [
                "",
                f"Spot quarantine counts: `{spot_price_policy['quarantine_counts']}`.",
                "Binance spot OHLC remains canonical for all price/return/volatility/label calculations.",
            ]
        )
    lines.extend(
        [
            "",
            "## Failure Reasons",
            "",
            f"- True listing too short: `{_fmt_list(reasons['true_listing_too_short'])}`.",
            f"- Missing spot after reset: `{_fmt_list(reasons['missing_spot_after_reset'])}`.",
            f"- Missing executable perp: `{_fmt_list(reasons['missing_executable_perp'])}`.",
            f"- Spot gap symbols: `{_fmt_list([item['symbol'] for item in reasons['spot_gap_symbols']])}`.",
            f"- Alias or multiplier unresolved: `{reasons['alias_or_multiplier_unresolved']}`.",
            f"- Derivatives field missing: `{reasons['derivatives_field_missing']}`.",
            "",
            "## OI Provenance",
            "",
            f"- Native OI symbol count: `{oi['native_oi_symbol_count']}`.",
            f"- Derived OI symbol count: `{oi['derived_oi_symbol_count']}`.",
            f"- Missing OI symbol count: `{oi['missing_oi_symbol_count']}`.",
            f"- Status: `{oi['status']}`.",
            f"- Native OI policy: `{oi['native_oi_policy']}`.",
            f"- Derived OI policy: `{oi['derived_oi_policy']}`.",
            f"- Canonical price source for derivation: `{oi['canonical_price_source_for_derivation']}`.",
            f"- Derived/native formula counts: `{oi['derived_native_formula_counts']}`.",
            f"- Formula fail symbols: `{_fmt_list(oi['formula_fail_symbols'])}`.",
            f"- 180d sidecar data-written symbols: `{oi['sidecar_data_success_count']}`.",
            f"- 180d sidecar formula-clean symbols: `{oi['sidecar_formula_clean_count']}`.",
            f"- 180d sidecar formula-warning symbols: `{oi['sidecar_formula_warning_count']}`.",
            f"- 180d sidecar error symbols: `{oi['sidecar_error_count']}`.",
            f"- 180d sidecar formula-fail symbol count: `{oi['sidecar_formula_fail_symbol_count']}`.",
            f"- Compiler integration status: `{oi['compiler_integration_status']}`.",
            "",
            "Compiler integration interval summary:",
            "",
            "| interval | symbols | symbols with native USD OI | native rows | selected OI rows | bad policy | formula-fail-row symbols |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for interval, item in dict(oi.get("compiler_integration_interval_summary") or {}).items():
        lines.append(
            f"| {interval} | {item['symbol_count']} | {item['symbols_with_native_usd_oi']} | "
            f"{item['total_native_usd_rows']} | {item['total_selected_oi_value_rows']} | "
            f"{item['bad_selected_policy_count']} | {item['symbols_with_formula_fail_rows']} |"
        )
    if not oi.get("compiler_integration_interval_summary"):
        lines.append("| none | 0 | 0 | 0 | 0 | 0 | 0 |")
    lines.append("")
    if dataset_smoke:
        lines.extend(
            [
                "## Dataset Feature Smoke",
                "",
                f"- Status: `{dataset_smoke['status']}`.",
                f"- Alpha rerun allowed: `{dataset_smoke['alpha_rerun_allowed']}`.",
                f"- Alpha blockers: `{_fmt_list(list(dataset_smoke.get('alpha_blockers') or []))}`.",
                f"- CoinGlass spot OHLC consumed: `{dict(dataset_smoke.get('canonical_input_policy') or {}).get('coinglass_spot_ohlc_consumed')}`.",
                "",
                "| dataset | profile | rows | subjects | lane eligible | data blockers | native OI rows | bad OI policy | sidecar families |",
                "| --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |",
            ]
        )
        for item in list(dataset_smoke.get("dataset_summaries") or []):
            lines.append(
                f"| {item['dataset_id']} | {item['dataset_profile']} | {item['row_count']} | "
                f"{item['subject_count']} | {item['dataset_lane_eligible']} | "
                f"{_fmt_list(list(item.get('data_gap_blockers') or []), max_items=3)} | "
                f"{item['oi_native_usd_row_count']} | {item['bad_oi_policy_row_count']} | "
                f"{_fmt_list(list(item.get('sidecar_fingerprint_families') or []), max_items=8)} |"
            )
        lines.extend(
            [
                "",
                "| feature set | profile | rows | numeric features | horizon | OI ready frac | OI subject ready |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in list(dataset_smoke.get("feature_summaries") or []):
            lines.append(
                f"| {item['feature_set_id']} | {item['dataset_profile']} | {item['row_count']} | "
                f"{item['numeric_feature_count']} | {item['target_horizon_bars']} | "
                f"{item['oi_ready_fraction']} | {item['oi_subject_ready_count']} |"
            )
        lines.append("")
    if spot_quarantine_smoke:
        input_policy = dict(spot_quarantine_smoke.get("canonical_input_policy") or {})
        lines.extend(
            [
                "## CoinGlass Spot Quarantine Smoke",
                "",
                f"- Status: `{spot_quarantine_smoke['status']}`.",
                f"- Alpha rerun allowed: `{spot_quarantine_smoke['alpha_rerun_allowed']}`.",
                f"- Alpha blockers: `{_fmt_list(list(spot_quarantine_smoke.get('alpha_blockers') or []))}`.",
                f"- Spot OHLC source: `{input_policy.get('spot_ohlc_source')}`.",
                f"- Spot OHLC trust status: `{input_policy.get('spot_ohlc_trust_status')}`.",
                f"- Quarantine reason: `{input_policy.get('quarantine_reason')}`.",
                "",
                "| dataset | profile | rows | subjects | lane eligible | data blockers | missing spot intervals | native OI rows |",
                "| --- | --- | ---: | ---: | --- | --- | --- | ---: |",
            ]
        )
        for item in list(spot_quarantine_smoke.get("dataset_summaries") or []):
            missing_counts = dict(item.get("missing_spot_symbols_by_interval") or {})
            missing_text = ", ".join(f"{key}:{value}" for key, value in sorted(missing_counts.items())) or "none"
            lines.append(
                f"| {item['dataset_id']} | {item['dataset_profile']} | {item['row_count']} | "
                f"{item['subject_count']} | {item['dataset_lane_eligible']} | "
                f"{_fmt_list(list(item.get('data_gap_blockers') or []), max_items=3)} | "
                f"{missing_text} | {item['oi_native_usd_row_count']} |"
            )
        lines.extend(
            [
                "",
                "| feature set | profile | rows | numeric features | horizon | OI ready frac | OI subject ready |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in list(spot_quarantine_smoke.get("feature_summaries") or []):
            lines.append(
                f"| {item['feature_set_id']} | {item['dataset_profile']} | {item['row_count']} | "
                f"{item['numeric_feature_count']} | {item['target_horizon_bars']} | "
                f"{item['oi_ready_fraction']} | {item['oi_subject_ready_count']} |"
            )
        lines.append("")
    if h10d_parent_rebaseline:
        validation_metrics = dict(h10d_parent_rebaseline.get("validation_metrics") or {})
        test_metrics = dict(h10d_parent_rebaseline.get("test_metrics") or {})
        factor_lite = dict(h10d_parent_rebaseline.get("factor_evidence_lite") or {})
        lines.extend(
            [
                "## H10D Parent Rebaseline",
                "",
                f"- Status: `{h10d_parent_rebaseline['status']}`.",
                f"- Decision: `{h10d_parent_rebaseline['decision']}`.",
                f"- Candidate: `{h10d_parent_rebaseline['candidate_id']}`.",
                f"- Feature set: `{h10d_parent_rebaseline['feature_set_id']}`.",
                f"- CoinGlass spot OHLC consumed: `{dict(h10d_parent_rebaseline.get('canonical_input_policy') or {}).get('coinglass_spot_ohlc_consumed')}`.",
                f"- Feature rows / subjects: `{h10d_parent_rebaseline['feature_rows']}` / `{h10d_parent_rebaseline['feature_subject_count']}`.",
                f"- Universe filtered rows / subjects: `{h10d_parent_rebaseline['universe_filtered_rows']}` / `{h10d_parent_rebaseline['universe_filtered_subject_count']}`.",
                f"- Execution filtered rows / subjects: `{h10d_parent_rebaseline['execution_filtered_rows']}` / `{h10d_parent_rebaseline['execution_filtered_subject_count']}`.",
                f"- Split row counts: `{h10d_parent_rebaseline.get('split_row_counts')}`.",
                f"- Blockers: `{_fmt_list(list(h10d_parent_rebaseline.get('blocker_codes') or []))}`.",
                f"- Full walk-forward status: `{h10d_parent_rebaseline.get('full_walk_forward_status')}`.",
                "",
                "| slice | net return | sharpe | max drawdown | trades | rebalances | data blockers |",
                "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
                (
                    f"| validation | {validation_metrics.get('net_return')} | {validation_metrics.get('sharpe')} | "
                    f"{validation_metrics.get('max_drawdown')} | {validation_metrics.get('trade_count')} | "
                    f"{validation_metrics.get('rebalance_count')} | {_fmt_list(list(validation_metrics.get('data_gap_blockers') or []), max_items=3)} |"
                ),
                (
                    f"| test | {test_metrics.get('net_return')} | {test_metrics.get('sharpe')} | "
                    f"{test_metrics.get('max_drawdown')} | {test_metrics.get('trade_count')} | "
                    f"{test_metrics.get('rebalance_count')} | {_fmt_list(list(test_metrics.get('data_gap_blockers') or []), max_items=3)} |"
                ),
                "",
                "Factor evidence lite:",
                "",
                f"- passed: `{factor_lite.get('passed')}`",
                f"- rank_ic_mean: `{factor_lite.get('rank_ic_mean')}`",
                f"- rank_ic_positive_rate: `{factor_lite.get('rank_ic_positive_rate')}`",
                f"- top_minus_bottom_return: `{factor_lite.get('top_minus_bottom_return')}`",
                f"- positive_regime_count: `{factor_lite.get('positive_regime_count')}`",
                "",
            ]
        )
    if h10d_parent_drift:
        historical_metrics = dict(h10d_parent_drift.get("historical_metrics") or {})
        reference_metrics = dict(h10d_parent_drift.get("reference_replay_metrics") or {})
        reset_metrics = dict(h10d_parent_drift.get("reset_replay_metrics") or {})
        immutable_replay = dict(h10d_parent_drift.get("immutable_replay") or {})
        immutable_metrics = dict(immutable_replay.get("metrics") or {})
        reset_stage = dict(h10d_parent_drift.get("reset_official_stage_audit") or {})
        reset_stage_metrics = dict(reset_stage.get("metrics") or {})
        subject_drift = dict(h10d_parent_drift.get("subject_drift") or {})
        deltas = dict(h10d_parent_drift.get("metric_deltas") or {})
        reference_delta = dict(deltas.get("reference_replay_minus_historical_fast_reject") or {})
        reset_delta = dict(deltas.get("reset_replay_minus_reference_replay") or {})
        metric_rows = [
            ("historical fast-reject", historical_metrics),
            ("2026-04-29 current replay", reference_metrics),
            ("2026-05-04 current replay", reset_metrics),
        ]
        lines.extend(
            [
                "## H10D Parent Drift Audit",
                "",
                f"- Status: `{h10d_parent_drift['status']}`.",
                f"- Decision: `{h10d_parent_drift['decision']}`.",
                f"- Primary blocker: `{h10d_parent_drift['primary_blocker']}`.",
                f"- Provenance observation: `{h10d_parent_drift.get('provenance_observation')}`.",
                f"- Historical fast-reject produced_at_utc: `{h10d_parent_drift['historical_fast_reject_produced_at_utc']}`.",
                f"- Current referenced feature manifest produced_at_utc: `{h10d_parent_drift['current_feature_manifest_produced_at_utc']}`.",
                f"- Artifact overwritten after report: `{h10d_parent_drift['artifact_overwritten_after_report']}`.",
                f"- Overwrite lag minutes: `{h10d_parent_drift['overwrite_lag_minutes']}`.",
                f"- Feature matrix sha256: `{h10d_parent_drift['feature_matrix_sha256']}`.",
                f"- Feature hash: `{h10d_parent_drift['feature_hash']}`.",
                f"- Same current replay subject set: `{subject_drift.get('same_subject_set')}`.",
                f"- Subject intersection count: `{subject_drift.get('intersection_count')}`.",
                f"- Secondary observation: `{h10d_parent_drift['secondary_observation']}`.",
                f"- Next gate: `{h10d_parent_drift['next_gate']}`.",
                f"- Immutable replay status: `{immutable_replay.get('stage_audit_status')}`.",
                f"- Immutable replay metrics match historical: `{immutable_replay.get('metrics_match_historical')}`.",
                f"- Immutable replay fast-reject reproduced: `{immutable_replay.get('fast_reject_reproduced')}`.",
                f"- Immutable replay validation net/sharpe: `{dict(immutable_metrics.get('validation') or {}).get('net_return')}` / `{dict(immutable_metrics.get('validation') or {}).get('sharpe')}`.",
                f"- Immutable replay fast-reject report: `{immutable_replay.get('official_fast_reject_report_path')}`.",
                f"- 2026-05-04 reset official replay status: `{reset_stage.get('status')}`.",
                f"- 2026-05-04 reset official replay last stage: `{reset_stage.get('last_stage')}`.",
                f"- 2026-05-04 reset official fast-reject passed: `{reset_stage_metrics.get('fast_reject_passed')}`.",
                f"- 2026-05-04 reset validation net/sharpe: `{dict(reset_stage_metrics.get('validation') or {}).get('net_return')}` / `{dict(reset_stage_metrics.get('validation') or {}).get('sharpe')}`.",
                f"- 2026-05-04 reset test net/sharpe: `{dict(reset_stage_metrics.get('test') or {}).get('net_return')}` / `{dict(reset_stage_metrics.get('test') or {}).get('sharpe')}`.",
                "",
                "| run | status | validation net | validation sharpe | test net | test sharpe | blockers |",
                "| --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row_name, metrics in metric_rows:
            validation = dict(metrics.get("validation") or {})
            test = dict(metrics.get("test") or {})
            lines.append(
                f"| {row_name} | {metrics.get('status')} | {validation.get('net_return')} | "
                f"{validation.get('sharpe')} | {test.get('net_return')} | {test.get('sharpe')} | "
                f"{_fmt_list(list(metrics.get('blocker_codes') or []), max_items=4)} |"
            )
        lines.extend(
            [
                "",
                "Metric deltas:",
                "",
                f"- 2026-04-29 current replay minus historical fast-reject: `{reference_delta}`.",
                f"- 2026-05-04 current replay minus 2026-04-29 current replay: `{reset_delta}`.",
                "",
            ]
        )
    if h10d_parent_strict_cycle_probe:
        diff = dict(h10d_parent_strict_cycle_probe.get("diff") or {})
        stage_fast = dict(h10d_parent_strict_cycle_probe.get("stage_fast_reject") or {})
        fresh_fast = dict(h10d_parent_strict_cycle_probe.get("fresh_fast_reject") or {})
        lines.extend(
            [
                "## H10D Parent Strict Cycle Probe",
                "",
                f"- Status: `{h10d_parent_strict_cycle_probe['status']}`.",
                f"- Decision: `{h10d_parent_strict_cycle_probe['decision']}`.",
                f"- Primary blocker: `{h10d_parent_strict_cycle_probe['primary_blocker']}`.",
                f"- Next gate: `{h10d_parent_strict_cycle_probe['next_gate']}`.",
                f"- Stage replay fast-reject passed: `{stage_fast.get('fast_reject_passed')}`.",
                f"- Fresh strict cycle fast-reject passed: `{fresh_fast.get('fast_reject_passed')}`.",
                f"- Fresh strict blockers: `{_fmt_list(list(fresh_fast.get('blocker_codes') or []))}`.",
                f"- Feature row delta fresh-minus-stage: `{diff.get('feature_row_delta_fresh_minus_stage')}`.",
                f"- Dataset row delta fresh-minus-stage: `{diff.get('dataset_row_delta_fresh_minus_stage')}`.",
                f"- Same feature hash: `{diff.get('same_feature_hash')}`.",
                f"- Stage dataset min timestamp: `{diff.get('stage_dataset_min_timestamp_utc')}`.",
                f"- Fresh dataset min timestamp: `{diff.get('fresh_dataset_min_timestamp_utc')}`.",
                "",
            ]
        )
    if h10d_parent_frozen_reset_strict:
        lines.extend(
            [
                "## H10D Parent Frozen Reset Strict",
                "",
                f"- Status: `{h10d_parent_frozen_reset_strict['status']}`.",
                f"- Decision: `{h10d_parent_frozen_reset_strict['decision']}`.",
                f"- Feature set: `{h10d_parent_frozen_reset_strict['feature_set_id']}`.",
                f"- Feature rows / subjects: `{h10d_parent_frozen_reset_strict['feature_rows']}` / `{h10d_parent_frozen_reset_strict['feature_subject_count']}`.",
                f"- Feature hash: `{h10d_parent_frozen_reset_strict['feature_hash']}`.",
                f"- Feature matrix sha256: `{h10d_parent_frozen_reset_strict['feature_matrix_sha256']}`.",
                f"- Dataset fingerprint: `{h10d_parent_frozen_reset_strict['dataset_fingerprint']}`.",
                f"- Derivatives quality matches manifest: `{h10d_parent_frozen_reset_strict['derivatives_quality_matches_manifest']}`.",
                f"- Strict validation passed: `{h10d_parent_frozen_reset_strict['strict_validation_passed']}`.",
                f"- Validation contract status: `{h10d_parent_frozen_reset_strict['validation_contract_status']}`.",
                f"- Falsification status: `{h10d_parent_frozen_reset_strict['falsification_status']}`.",
                f"- Statistical falsification status: `{h10d_parent_frozen_reset_strict['statistical_falsification_status']}`.",
                f"- Alpha experiment card status: `{h10d_parent_frozen_reset_strict['alpha_experiment_card_status']}`.",
                f"- Alpha experiment card go/no-go: `{h10d_parent_frozen_reset_strict['alpha_experiment_card_go_no_go']}`.",
                f"- Alpha experiment card blockers: `{_fmt_list(list(h10d_parent_frozen_reset_strict.get('alpha_experiment_card_blocker_codes') or []))}`.",
                f"- Credible research evidence: `{h10d_parent_frozen_reset_strict['credible_research_evidence']}`.",
                f"- Validation metrics: `{h10d_parent_frozen_reset_strict.get('validation_metrics')}`.",
                f"- Test metrics: `{h10d_parent_frozen_reset_strict.get('test_metrics')}`.",
                f"- Strict result path: `{h10d_parent_frozen_reset_strict.get('strict_result_path')}`.",
                f"- Next gate: `{h10d_parent_frozen_reset_strict.get('next_gate')}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Lowest Completeness",
            "",
            "| symbol | status | expected | observed | completeness | gaps |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["lowest_completeness_symbols"]:
        lines.append(
            f"| {item['symbol']} | {item['status']} | {item['requested_expected_rows']} | "
            f"{item['requested_observed_rows']} | {item['requested_completeness']} | {item['gap_count']} |"
        )
    lines.extend(
        [
            "",
            "## Stop Rule",
            "",
            "Do not promote alpha on this reset alone. The compiler now sees native USD OI sidecars, and Binance-canonical inputs can build both the 1h intraday lane and the daily 4h/1d lane after the Binance baseline repair. CoinGlass spot 1h/4h/1d can also build both lanes, but only as quarantined diagnostics because strict spot OHLC provider concordance still fails. R-1 follow-up has now cleared the 2026-04-29 reproduction check and the 2026-05-04 reset official fast-reject replay; frozen reset strict validation used the same reset feature matrix and still failed closed on the alpha experiment card. Derived OI remains quarantine metadata unless a symbol-level waiver later clears the native/derived mismatch.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    payload = build_payload()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_OUT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"json": str(JSON_OUT), "report": str(REPORT_OUT), "decision": payload["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
