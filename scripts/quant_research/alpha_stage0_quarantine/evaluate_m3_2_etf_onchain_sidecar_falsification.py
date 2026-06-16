from __future__ import annotations

import argparse
import json
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="Downcasting object dtype arrays on .fillna",
)

from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_falsification as hardgate  # noqa: E402
from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_stage0 as stage0  # noqa: E402


CONTRACT_VERSION = "m3_2_etf_onchain_sidecar_falsification.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_PARTICIPANT_CONTEXT_PATH = (
    ROOT / "artifacts" / "quant_research" / "coinglass" / "participant_context_1d.csv.gz"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-m3-2-etf-onchain-sidecar-falsification"
)

SIDECAR_CONTEXT_COLUMNS = [
    "total_btc_eth_etf_flow_usd",
    "total_btc_eth_etf_flow_usd_10d_sum",
    "total_btc_eth_etf_flow_usd_z30",
    "btc_etf_flow_usd_z30",
    "eth_etf_flow_usd_z30",
    "exchange_transfer_total_usd_z30",
    "exchange_netflow_type2_minus_type1_usd_z30",
    "whale_transfer_total_usd_z30",
    "whale_net_to_exchange_usd_z30",
    "participant_context_sources",
    "participant_context_pit_policies",
]


@dataclass(frozen=True)
class SidecarBoundarySpec:
    label: str
    parent_label: str
    base_state_column: str
    confirm_state_column: str
    side: str
    action: str
    exposure_mode: str
    interpretation: str
    derived_state_column: str
    pool_size: int = 8
    side_count: int = 3

    def to_boundary_spec(self) -> stage0.BoundarySpec:
        return stage0.BoundarySpec(
            label=self.label,
            side=self.side,
            action=self.action,
            state_column=self.derived_state_column,
            state_threshold=0.75,
            exposure_mode=self.exposure_mode,
            interpretation=self.interpretation,
            pool_size=self.pool_size,
            side_count=self.side_count,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pre-registered M3.2 ETF/on-chain sidecar integration plus strict "
            "fail-closed falsification."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--panel-path", type=Path, default=stage0.DEFAULT_PANEL_PATH)
    parser.add_argument("--participant-context-path", type=Path, default=DEFAULT_PARTICIPANT_CONTEXT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--iterations", type=int, default=hardgate.DEFAULT_RANDOM_ITERATIONS)
    parser.add_argument("--seed", type=int, default=hardgate.DEFAULT_SEED)
    parser.add_argument("--base-replacement-cost-bps", type=float, default=10.0)
    parser.add_argument("--delay-retention-threshold", type=float, default=0.50)
    parser.add_argument(
        "--force-random-controls",
        action="store_true",
        help=(
            "Run random controls even after deterministic hard-gate blockers. "
            "Default fail-closes without random-tail spend once deterministic blockers appear."
        ),
    )
    return parser


def _pre_registered_sidecar_specs() -> list[SidecarBoundarySpec]:
    return [
        SidecarBoundarySpec(
            label="tron_impulse_short_high_beta_rs__cg_etf_10d_inflow_confirm",
            parent_label="tron_impulse_short_high_beta_rs",
            base_state_column="m3_2_tron_flow_impulse_state",
            confirm_state_column="cg_etf_10d_inflow_confirm_state",
            side="short",
            action="replace_high",
            exposure_mode="high_beta_rs",
            derived_state_column="m3_2_tron_flow_impulse_cg_etf_10d_inflow_state",
            interpretation=(
                "TRON stablecoin impulse plus positive 10d BTC/ETH ETF flow: "
                "tests whether the direct short replacement only transmits during ETF-sponsored risk-on."
            ),
        ),
        SidecarBoundarySpec(
            label="tron_heat_short_high_rs__cg_etf_10d_outflow_confirm",
            parent_label="tron_heat_short_high_rs",
            base_state_column="m3_2_tron_speculative_heat_state",
            confirm_state_column="cg_etf_10d_outflow_confirm_state",
            side="short",
            action="replace_high",
            exposure_mode="high_rs",
            derived_state_column="m3_2_tron_heat_cg_etf_10d_outflow_state",
            interpretation=(
                "TRON speculative heat plus negative 10d BTC/ETH ETF flow: "
                "tests a fragile crypto-native heat divergence while ETF flow is not confirming risk-on."
            ),
        ),
        SidecarBoundarySpec(
            label="rebound_long_idio__cg_etf_10d_outflow_confirm",
            parent_label="rebound_long_idio",
            base_state_column="m3_2_reflexive_rebound_state",
            confirm_state_column="cg_etf_10d_outflow_confirm_state",
            side="long",
            action="replace_high",
            exposure_mode="idio",
            derived_state_column="m3_2_rebound_cg_etf_10d_outflow_state",
            interpretation=(
                "Reflexive rebound plus negative 10d BTC/ETH ETF flow: "
                "tests whether rebound replacement is really capitulation context rather than generic M3.2 activity."
            ),
        ),
        SidecarBoundarySpec(
            label="sell_pressure_short_high_beta_rs__cg_participant_risk_off_confirm",
            parent_label="sell_pressure_short_high_beta_rs",
            base_state_column="m3_2_btc_sell_pressure_state",
            confirm_state_column="cg_participant_risk_off_confirm_state",
            side="short",
            action="replace_high",
            exposure_mode="high_beta_rs",
            derived_state_column="m3_2_sell_pressure_cg_participant_risk_off_state",
            interpretation=(
                "BTC sell-pressure plus ETF outflow or whale-to-exchange stress: "
                "tests whether the short replacement needs exogenous participant-risk-off confirmation."
            ),
        ),
    ]


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _state_from_mask(mask: pd.Series, available: pd.Series | None = None) -> pd.Series:
    if available is not None:
        mask = mask & available.fillna(False).astype(bool)
    return mask.fillna(False).astype("float64")


def _read_participant_context(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"participant context sidecar not found: {path}")
    frame = pd.read_csv(path)
    if "date_utc" not in frame.columns:
        raise ValueError(f"participant context sidecar missing date_utc: {path}")
    frame = frame.copy()
    frame["date_utc"] = frame["date_utc"].astype(str)
    keep = ["date_utc", *[column for column in SIDECAR_CONTEXT_COLUMNS if column in frame.columns]]
    return frame[keep].drop_duplicates("date_utc").sort_values("date_utc")


def _merge_participant_context(frame: pd.DataFrame, participant_context_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    context = _read_participant_context(participant_context_path)
    merged = frame.merge(context, on="date_utc", how="left")
    return merged, context


def _build_sidecar_states(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    etf_flow_10d = _numeric(work, "total_btc_eth_etf_flow_usd_10d_sum")
    etf_flow_z30 = _numeric(work, "total_btc_eth_etf_flow_usd_z30")
    whale_to_exchange_z30 = _numeric(work, "whale_net_to_exchange_usd_z30")
    exchange_activity_z30 = _numeric(work, "exchange_transfer_total_usd_z30")

    etf_available = etf_flow_10d.notna()
    whale_available = whale_to_exchange_z30.notna()
    exchange_available = exchange_activity_z30.notna()

    work["cg_etf_context_available"] = etf_available
    work["cg_whale_context_available"] = whale_available
    work["cg_exchange_context_available"] = exchange_available

    work["cg_etf_10d_inflow_confirm_state"] = _state_from_mask(etf_flow_10d.gt(0.0), etf_available)
    work["cg_etf_10d_outflow_confirm_state"] = _state_from_mask(etf_flow_10d.lt(0.0), etf_available)
    work["cg_etf_z30_inflow_shock_state"] = _state_from_mask(etf_flow_z30.ge(1.0), etf_flow_z30.notna())
    work["cg_etf_z30_outflow_shock_state"] = _state_from_mask(etf_flow_z30.le(-1.0), etf_flow_z30.notna())
    work["cg_whale_to_exchange_stress_state"] = _state_from_mask(
        whale_to_exchange_z30.ge(1.0),
        whale_available,
    )
    work["cg_whale_from_exchange_relief_state"] = _state_from_mask(
        whale_to_exchange_z30.le(-1.0),
        whale_available,
    )
    work["cg_exchange_activity_shock_quarantine_state"] = _state_from_mask(
        exchange_activity_z30.ge(1.0),
        exchange_available,
    )
    work["cg_participant_risk_off_confirm_state"] = _state_from_mask(
        etf_flow_10d.lt(0.0) | whale_to_exchange_z30.ge(1.0),
        etf_available | whale_available,
    )
    work["cg_participant_risk_on_confirm_state"] = _state_from_mask(
        etf_flow_10d.gt(0.0) | whale_to_exchange_z30.le(-1.0),
        etf_available | whale_available,
    )
    return work


def _derive_candidate_states(frame: pd.DataFrame, specs: list[SidecarBoundarySpec]) -> pd.DataFrame:
    work = frame.copy()
    for spec in specs:
        base_active = _numeric(work, spec.base_state_column).ge(0.75)
        confirm_active = _numeric(work, spec.confirm_state_column).ge(0.75)
        work[spec.derived_state_column] = _state_from_mask(base_active & confirm_active)
    return work


def _timestamp_level(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop_duplicates("timestamp_ms").sort_values("timestamp_ms").reset_index(drop=True)


def _date_bounds(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or "date_utc" not in frame.columns:
        return {"rows": int(len(frame)), "date_min": None, "date_max": None}
    dates = frame["date_utc"].dropna().astype(str)
    return {
        "rows": int(len(frame)),
        "date_min": dates.min() if len(dates) else None,
        "date_max": dates.max() if len(dates) else None,
    }


def _input_meta(
    frame: pd.DataFrame,
    *,
    participant_context: pd.DataFrame,
    panel_path: Path,
    participant_context_path: Path,
    specs: list[SidecarBoundarySpec],
) -> dict[str, Any]:
    one = _timestamp_level(frame)
    ready = one["m3_2_panel_ready"].fillna(False).astype(bool)
    meta: dict[str, Any] = {
        "panel_path": str(panel_path),
        "participant_context_path": str(participant_context_path),
        "parent_timestamp_count": int(one["timestamp_ms"].nunique()),
        "ready_timestamp_count": int(ready.sum()),
        "participant_context_bounds": _date_bounds(participant_context),
        "parent_bounds": _date_bounds(one),
        "sidecar_policy": {
            "etf": "daily source date plus one-day PIT lag",
            "whale": "event date plus one-day PIT lag with exchange-entity direction heuristic",
            "exchange": "quarantined latest-event feed; tracked but not used in primary confirm states",
        },
    }
    for column in [
        "cg_etf_context_available",
        "cg_whale_context_available",
        "cg_exchange_context_available",
        "cg_etf_10d_inflow_confirm_state",
        "cg_etf_10d_outflow_confirm_state",
        "cg_whale_to_exchange_stress_state",
        "cg_participant_risk_off_confirm_state",
        "cg_participant_risk_on_confirm_state",
        "cg_exchange_activity_shock_quarantine_state",
    ]:
        values = _numeric(one, column)
        meta[column] = {
            "ready_non_null_count": int(values.loc[ready].notna().sum()),
            "ready_active_count": int(values.loc[ready].ge(0.75).sum()),
            "all_active_count": int(values.ge(0.75).sum()),
        }
    for spec in specs:
        parent_active = ready & _numeric(one, spec.base_state_column).ge(0.75)
        derived_active = ready & _numeric(one, spec.derived_state_column).ge(0.75)
        meta[spec.label] = {
            "parent_label": spec.parent_label,
            "base_state_column": spec.base_state_column,
            "confirm_state_column": spec.confirm_state_column,
            "derived_state_column": spec.derived_state_column,
            "parent_ready_active_count": int(parent_active.sum()),
            "derived_ready_active_count": int(derived_active.sum()),
            "derived_fraction_of_parent_active": (
                float(derived_active.sum() / parent_active.sum()) if int(parent_active.sum()) else None
            ),
        }
    return meta


def _stage0_compact(evaluations: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for label, payload in evaluations.items():
        comparison = payload.get("comparison_vs_parent", {})
        change = payload.get("boundary_change", {})
        compact[label] = {
            "verdict": comparison.get("verdict"),
            "delta_active_long_short_mean": comparison.get("delta_active_long_short_mean"),
            "active_timestamp_count": change.get("active_timestamp_count"),
            "long_active_changed_timestamp_fraction": change.get(
                "long_active_changed_timestamp_fraction"
            ),
            "short_active_changed_timestamp_fraction": change.get(
                "short_active_changed_timestamp_fraction"
            ),
        }
    return compact


def _deterministic_falsification(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
    base_replacement_cost_bps: float,
    delay_retention_threshold: float,
) -> dict[str, Any]:
    observed = hardgate._evaluate_locked(frame, spec, target_horizon_bars=target_horizon_bars)
    observed_delta = hardgate._active_delta(observed)
    if observed_delta is None:
        return {
            "label": spec.label,
            "status": "failed",
            "credible_incremental_edge": False,
            "blocker_codes": ["observed_delta_missing"],
            "observed": {
                "comparison_vs_parent": observed.get("comparison_vs_parent", {}),
                "boundary_change": observed.get("boundary_change", {}),
            },
            "tests": {},
        }
    tests = {
        "delayed_activation": hardgate._delay_test(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            observed_delta=observed_delta,
            retention_threshold=delay_retention_threshold,
        ),
        "symbol_holdout": hardgate._symbol_holdout_test(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
        ),
        "liquidity_bucket_consistency": hardgate._side_bucket_edge(
            observed["parent_sides"],
            observed["candidate_sides"],
            spec,
            target_horizon_bars=target_horizon_bars,
        ),
        "two_x_cost_stress": hardgate._cost_stress_test(
            observed,
            base_replacement_cost_bps=base_replacement_cost_bps,
        ),
    }
    blocker_codes = [name + "_failed" for name, payload in tests.items() if not bool(payload.get("passed"))]
    return {
        "label": spec.label,
        "status": "cleared" if not blocker_codes else "failed",
        "credible_incremental_edge": not blocker_codes,
        "blocker_codes": blocker_codes,
        "observed": {
            "comparison_vs_parent": observed["comparison_vs_parent"],
            "boundary_change": observed["boundary_change"],
        },
        "tests": tests,
    }


def _evaluate_strict_gate(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
    iterations: int,
    seed: int,
    base_replacement_cost_bps: float,
    delay_retention_threshold: float,
    force_random_controls: bool,
) -> dict[str, Any]:
    deterministic = _deterministic_falsification(
        frame,
        spec,
        target_horizon_bars=target_horizon_bars,
        base_replacement_cost_bps=base_replacement_cost_bps,
        delay_retention_threshold=delay_retention_threshold,
    )
    deterministic["random_controls_policy"] = (
        "force_random_controls"
        if force_random_controls
        else "run_random_controls_only_after_deterministic_clear"
    )
    deterministic["random_iterations_requested"] = int(iterations)
    if deterministic.get("status") == "cleared" or force_random_controls:
        full = hardgate._evaluate_falsification(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            iterations=int(iterations),
            seed=int(seed),
            base_replacement_cost_bps=base_replacement_cost_bps,
            delay_retention_threshold=delay_retention_threshold,
        )
        full["deterministic_prefilter"] = deterministic
        return full
    deterministic["random_controls_status"] = "skipped_fail_closed_after_deterministic_blockers"
    return deterministic


def _build_decision(
    *,
    stage0_evaluations: dict[str, Any],
    strict_results: dict[str, Any],
) -> dict[str, Any]:
    stage0_positive = [
        label
        for label, payload in stage0_evaluations.items()
        if payload.get("comparison_vs_parent", {}).get("verdict") == "stage0_positive"
    ]
    strict_cleared = [
        label for label, payload in strict_results.items() if payload.get("status") == "cleared"
    ]
    blockers: list[str] = []
    if not stage0_positive:
        blockers.append("no_stage0_positive_sidecar_variants")
    for label in stage0_positive:
        payload = strict_results.get(label)
        if not payload:
            blockers.append(f"{label}_strict_falsification_not_run")
        elif payload.get("status") != "cleared":
            for code in payload.get("blocker_codes", []) or ["strict_falsification_failed"]:
                blockers.append(f"{label}_{code}")
    return {
        "status": "cleared" if strict_cleared else "failed",
        "alpha_rerun_allowed": bool(strict_cleared),
        "manifest_ab_allowed": bool(strict_cleared),
        "stage0_positive_variants": stage0_positive,
        "strict_cleared_variants": strict_cleared,
        "blocker_codes": sorted(set(blockers)),
        "next_action": (
            "open single-lane manifest A/B design only for cleared variants"
            if strict_cleared
            else "fail closed; do not reopen M3.2 with these ETF/on-chain sidecar activation definitions"
        ),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def run(args: argparse.Namespace) -> dict[str, Any]:
    target_horizon_bars = int(args.target_horizon_bars)
    specs = _pre_registered_sidecar_specs()
    frame = stage0._load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        panel_path=Path(args.panel_path),
    )
    frame, participant_context = _merge_participant_context(frame, Path(args.participant_context_path))
    frame = _build_sidecar_states(frame)
    frame = _derive_candidate_states(frame, specs)
    frame = hardgate._with_parent_score(frame)

    boundary_specs = [spec.to_boundary_spec() for spec in specs]
    stage0_evaluations = {
        spec.label: stage0._evaluate(frame, spec=spec, target_horizon_bars=target_horizon_bars)
        for spec in boundary_specs
    }
    strict_results: dict[str, Any] = {}
    for spec in boundary_specs:
        verdict = stage0_evaluations[spec.label]["comparison_vs_parent"].get("verdict")
        if verdict != "stage0_positive":
            strict_results[spec.label] = {
                "label": spec.label,
                "status": "not_run",
                "reason": "stage0_not_positive",
                "blocker_codes": ["stage0_not_positive"],
                "credible_incremental_edge": False,
            }
            continue
        strict_results[spec.label] = _evaluate_strict_gate(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            iterations=max(int(args.iterations), 1),
            seed=int(args.seed),
            base_replacement_cost_bps=float(args.base_replacement_cost_bps),
            delay_retention_threshold=float(args.delay_retention_threshold),
            force_random_controls=bool(args.force_random_controls),
        )

    decision = _build_decision(stage0_evaluations=stage0_evaluations, strict_results=strict_results)
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": target_horizon_bars,
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "random_iterations_requested": max(int(args.iterations), 1),
        "seed": int(args.seed),
        "base_replacement_cost_bps": float(args.base_replacement_cost_bps),
        "delay_retention_threshold": float(args.delay_retention_threshold),
        "force_random_controls": bool(args.force_random_controls),
        "pre_registration": {
            "scope": "only the four direct M3.2 Stage0-positive boundary labels are carried forward",
            "sidecar_thresholds": {
                "etf_10d_inflow": "total_btc_eth_etf_flow_usd_10d_sum > 0",
                "etf_10d_outflow": "total_btc_eth_etf_flow_usd_10d_sum < 0",
                "whale_to_exchange_stress": "whale_net_to_exchange_usd_z30 >= 1",
                "exchange_activity": "tracked as quarantined context, not used in primary confirmations",
            },
            "variants": [
                {
                    "label": spec.label,
                    "parent_label": spec.parent_label,
                    "base_state_column": spec.base_state_column,
                    "confirm_state_column": spec.confirm_state_column,
                    "derived_state_column": spec.derived_state_column,
                    "side": spec.side,
                    "action": spec.action,
                    "exposure_mode": spec.exposure_mode,
                    "interpretation": spec.interpretation,
                }
                for spec in specs
            ],
        },
        "input_meta": _input_meta(
            frame,
            participant_context=participant_context,
            panel_path=Path(args.panel_path),
            participant_context_path=Path(args.participant_context_path),
            specs=specs,
        ),
        "stage0_evaluation": stage0_evaluations,
        "strict_falsification": strict_results,
        "decision": decision,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    output_path = output_dir / "m3_2_etf_onchain_sidecar_falsification.json"
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    print(f"=== Wrote M3.2 ETF/on-chain sidecar falsification report to {output_path}")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "stage0": _stage0_compact(report["stage0_evaluation"]),
                "strict": {
                    label: {
                        "status": payload.get("status"),
                        "blocker_codes": payload.get("blocker_codes"),
                        "random_controls_status": payload.get("random_controls_status"),
                    }
                    for label, payload in report["strict_falsification"].items()
                },
            },
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
