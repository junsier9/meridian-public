from __future__ import annotations

import argparse
import json
import sys
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

from scripts.quant_research import evaluate_v6_h10d_post_pump_short_replacement as spk_eval  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    _xs_alpha_ontology_v5_h10d_base_raw_score,
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
    xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "quant_spk_non_kline_confirmation_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_THRESHOLD = 0.90


@dataclass(frozen=True)
class ConfirmationSpec:
    label: str
    description: str
    signed_columns: tuple[tuple[str, float], ...]
    require_ready_column: str | None = None


CONFIRMATION_SPECS = [
    ConfirmationSpec(
        label="funding_oi_crowding_top_decile",
        description="Funding/OI/basis crowding plus liquidation concentration.",
        signed_columns=(
            ("funding_zscore_20", 1.0),
            ("oi_change_5", 1.0),
            ("basis_zscore_20", 1.0),
            ("pump_funding_oi_crowding_score_3d", 1.0),
            ("coinglass_liq_intraday_concentration_24h", 1.0),
        ),
    ),
    ConfirmationSpec(
        label="liquidation_cascade_exhaustion_top_decile",
        description="Recent liquidation cascade pressure around the SP-K candidate.",
        signed_columns=(
            ("liq_cascade_max_z_24h", 1.0),
            ("liq_cascade_count_24h_z25", 1.0),
            ("liq_cascade_recency_score_5d", 1.0),
            ("liq_cascade_signed_intensity_24h", 1.0),
            ("coinglass_liq_intraday_concentration_24h", 1.0),
        ),
    ),
    ConfirmationSpec(
        label="taker_orderbook_exhaustion_top_decile",
        description="Taker-buy fade plus bid/depth fragility after the pump.",
        signed_columns=(
            ("taker_net_to_depth_mean_z30", -1.0),
            ("coinglass_taker_net_to_depth_mean_24h", -1.0),
            ("pump_bid_replenishment_failure_score", 1.0),
            ("boundary_fragile_orderbook_score", 1.0),
            ("ob_bid_replenishment_ratio_1d", -1.0),
            ("ob_total_depth_replenishment_ratio_1d", -1.0),
            ("coinglass_orderbook_ask_heavy_share_24h", 1.0),
        ),
    ),
    ConfirmationSpec(
        label="top_trader_fade_retail_chase_top_decile",
        description="Global/retail chase versus top-trader fade and fast top-trader movement.",
        signed_columns=(
            ("top_global_disagreement_1h_30d", 1.0),
            ("top_trader_velocity_1h_abs_24h", 1.0),
            ("top_trader_velocity_1h_signed_24h", -1.0),
            ("coinglass_global_account_long_pct", 1.0),
            ("coinglass_top_trader_long_pct", -1.0),
        ),
    ),
    ConfirmationSpec(
        label="stablecoin_stress_context_top_decile",
        description="Daily stablecoin exchange/whale stress context, only when the sidecar is ready.",
        signed_columns=(
            ("stablecoin_exchange_absorption_score_v1", 1.0),
            ("stablecoin_whale_exchange_stress_score_v1", 1.0),
            ("stablecoin_issuance_ratio_z14", 1.0),
            ("stablecoin_velocity_log_z14", 1.0),
        ),
        require_ready_column="stablecoin_flow_signal_ready",
    ),
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage-0 battery for SP-K canonical-parent short replacement with non-kline "
            "confirmation sidecars. This is a fail-closed diagnostic, not a promotion runner."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--confirmation-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _timestamp_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    grouped = values.groupby(frame["timestamp_ms"])
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0).astype("float64")


def _feature_presence(frame: pd.DataFrame) -> dict[str, Any]:
    columns = sorted(
        {
            column
            for spec in CONFIRMATION_SPECS
            for column, _weight in spec.signed_columns
        }
        | {spec.require_ready_column for spec in CONFIRMATION_SPECS if spec.require_ready_column}
    )
    out: dict[str, Any] = {}
    for column in columns:
        if column not in frame.columns:
            out[column] = {"present": False, "non_null_fraction": 0.0}
            continue
        values = frame[column]
        if values.dtype == "bool":
            non_null = values.notna()
        else:
            non_null = pd.to_numeric(values, errors="coerce").notna()
        out[column] = {
            "present": True,
            "non_null_fraction": float(non_null.mean()) if len(values) else 0.0,
        }
    return out


def _add_confirmation_columns(
    frame: pd.DataFrame,
    *,
    spec: ConfirmationSpec,
    threshold: float,
) -> pd.DataFrame:
    out = frame.copy()
    score = pd.Series(np.zeros(len(out)), index=out.index, dtype="float64")
    present_count = 0
    for column, weight in spec.signed_columns:
        if column not in out.columns:
            continue
        score = score + float(weight) * _timestamp_zscore(out, column)
        present_count += 1
    if present_count:
        score = score / float(present_count)
    else:
        score[:] = np.nan

    ready = pd.Series(True, index=out.index, dtype="bool")
    if spec.require_ready_column:
        if spec.require_ready_column in out.columns:
            ready = out[spec.require_ready_column].fillna(False).astype("bool")
        else:
            ready = pd.Series(False, index=out.index, dtype="bool")

    score_col = f"{spec.label}_score"
    pct_col = f"{spec.label}_pct"
    flag_col = f"{spec.label}_flag"
    veto_col = f"{spec.label}_candidate_veto"
    out[score_col] = score
    out[pct_col] = score.groupby(out["timestamp_ms"]).rank(method="average", pct=True).fillna(0.0)
    out[flag_col] = ready & out[pct_col].ge(float(threshold))
    out[veto_col] = ~out[flag_col].fillna(False).astype("bool")
    return out


def _make_confirmed_scorer(veto_column: str):
    def _scorer(local_frame: pd.DataFrame) -> pd.Series:
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            local_frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            candidate_veto_column=veto_column,
        )

    return _scorer


def _short_basket_summary(
    frame: pd.DataFrame,
    *,
    scorer,
    target_horizon_bars: int,
    flag_column: str | None = None,
) -> dict[str, Any]:
    scored = frame.copy()
    scored["score"] = scorer(scored)
    rows: list[dict[str, Any]] = []
    for _timestamp, group in scored.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values("score", ascending=False).tail(min(3, len(group))).copy()
        rows.extend(shorts.to_dict("records"))
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "empty"}
    h_col = f"forward_{target_horizon_bars}d_log_return"
    horizon = pd.to_numeric(basket.get(h_col), errors="coerce").dropna()
    one = pd.to_numeric(basket.get("forward_1d_log_return"), errors="coerce").dropna()
    out = {
        "status": "ok",
        "n_short_rows": int(len(basket)),
        "next_horizon_mean": float(horizon.mean()) if len(horizon) else None,
        "next_horizon_negative_fraction": float((horizon < 0).mean()) if len(horizon) else None,
        "next_1d_mean": float(one.mean()) if len(one) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((one > 0.05).mean()) if len(one) else None,
        "mid_liquidity_short_fraction": float(basket["liquidity_bucket"].astype(str).eq("mid_liquidity").mean())
        if "liquidity_bucket" in basket.columns
        else None,
    }
    if flag_column and flag_column in basket.columns:
        out["confirmation_flag_fraction"] = float(basket[flag_column].fillna(False).astype("bool").mean())
    return out


def _verdict(
    *,
    variant_vs_parent: dict[str, Any],
    spk_vs_parent: dict[str, Any],
    variant_vs_spk: dict[str, Any],
    short_basket_summary: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    entered_key = f"entered_next_{target_horizon_bars}d_mean"
    exited_key = f"exited_next_{target_horizon_bars}d_mean"
    variant_entered = variant_vs_parent.get(entered_key)
    spk_entered = spk_vs_parent.get(entered_key)
    variant_exited = variant_vs_parent.get(exited_key)
    variant_replacements = int(variant_vs_parent.get("total_replacements") or 0)
    spk_replacements = int(spk_vs_parent.get("total_replacements") or 0)
    variant_basket = short_basket_summary.get("variant", {})
    spk_basket = short_basket_summary.get("spk", {})
    variant_squeeze = variant_vs_parent.get("entered_next_1d_squeeze_gt_5pct_fraction")
    spk_squeeze = spk_vs_parent.get("entered_next_1d_squeeze_gt_5pct_fraction")

    checks = {
        "variant_has_replacements": variant_replacements >= 50,
        "variant_less_active_than_spk": variant_replacements < spk_replacements,
        "variant_differs_from_spk": int(variant_vs_spk.get("total_replacements") or 0) > 0,
        "variant_entered_shorts_negative_h10d": variant_entered is not None and float(variant_entered) < 0.0,
        "variant_entered_beats_spk_entered_h10d": (
            variant_entered is not None and spk_entered is not None and float(variant_entered) < float(spk_entered)
        ),
        "variant_entered_beats_parent_exited_h10d": (
            variant_entered is not None and variant_exited is not None and float(variant_entered) < float(variant_exited)
        ),
        "variant_short_basket_beats_spk_h10d": (
            variant_basket.get("next_horizon_mean") is not None
            and spk_basket.get("next_horizon_mean") is not None
            and float(variant_basket["next_horizon_mean"]) <= float(spk_basket["next_horizon_mean"])
        ),
        "variant_squeeze_not_worse_than_spk": (
            variant_squeeze is not None and spk_squeeze is not None and float(variant_squeeze) <= float(spk_squeeze)
        ),
    }
    passed = sum(1 for value in checks.values() if value)
    critical = (
        checks["variant_has_replacements"]
        and checks["variant_entered_beats_spk_entered_h10d"]
        and checks["variant_short_basket_beats_spk_h10d"]
        and checks["variant_squeeze_not_worse_than_spk"]
    )
    if passed >= 7 and critical:
        label = "stage0_keep_for_strict_falsification"
    elif passed >= 4:
        label = "stage0_watch"
    else:
        label = "stage0_reject"
    return {
        "label": label,
        "passed_check_count": int(passed),
        "total_check_count": int(len(checks)),
        "checks": checks,
    }


def _evaluate_variant(
    frame: pd.DataFrame,
    *,
    spec: ConfirmationSpec,
    threshold: float,
    target_horizon_bars: int,
    spk_parent_selection: dict[str, Any],
    spk_short_basket: dict[str, Any],
) -> dict[str, Any]:
    prepared = _add_confirmation_columns(frame, spec=spec, threshold=threshold)
    veto_col = f"{spec.label}_candidate_veto"
    flag_col = f"{spec.label}_flag"
    scorer = _make_confirmed_scorer(veto_col)
    parent_vs_variant = spk_eval._selection_change_diagnostic(  # noqa: SLF001
        frame=prepared,
        baseline_scorer=xs_alpha_ontology_v5_score,
        candidate_scorer=scorer,
        long_count=3,
        short_count=3,
        target_horizon_bars=target_horizon_bars,
    )
    spk_vs_variant = spk_eval._selection_change_diagnostic(  # noqa: SLF001
        frame=prepared,
        baseline_scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        candidate_scorer=scorer,
        long_count=3,
        short_count=3,
        target_horizon_bars=target_horizon_bars,
    )
    variant_short_basket = _short_basket_summary(
        prepared,
        scorer=scorer,
        target_horizon_bars=target_horizon_bars,
        flag_column=flag_col,
    )
    short_baskets = {
        "spk": spk_short_basket,
        "variant": variant_short_basket,
    }
    return {
        "description": spec.description,
        "signed_columns": [{"column": column, "weight": weight} for column, weight in spec.signed_columns],
        "require_ready_column": spec.require_ready_column,
        "confirmation_threshold": float(threshold),
        "confirmed_row_fraction": float(prepared[flag_col].fillna(False).astype("bool").mean()),
        "confirmed_timestamp_fraction": float(
            prepared.groupby("timestamp_ms")[flag_col].any().fillna(False).astype("bool").mean()
        ),
        "parent_vs_variant_selection": parent_vs_variant,
        "spk_vs_variant_selection": spk_vs_variant,
        "short_basket_summary": short_baskets,
        "verdict": _verdict(
            variant_vs_parent=parent_vs_variant,
            spk_vs_parent=spk_parent_selection,
            variant_vs_spk=spk_vs_variant,
            short_basket_summary=short_baskets,
            target_horizon_bars=target_horizon_bars,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    target_horizon_bars = int(args.target_horizon_bars)
    threshold = float(args.confirmation_threshold)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{as_of}-spk-non-kline-confirmation-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "spk_non_kline_confirmation_stage0.json"

    frame = spk_eval._build_risk_frame(  # noqa: SLF001
        spk_eval._features_artifact_path(as_of),  # noqa: SLF001
        target_horizon_bars=target_horizon_bars,
    )
    parent_vs_spk = spk_eval._selection_change_diagnostic(  # noqa: SLF001
        frame=frame,
        baseline_scorer=xs_alpha_ontology_v5_score,
        candidate_scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        long_count=3,
        short_count=3,
        target_horizon_bars=target_horizon_bars,
    )
    spk_short_basket = _short_basket_summary(
        frame,
        scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        target_horizon_bars=target_horizon_bars,
    )
    results = {
        spec.label: _evaluate_variant(
            frame,
            spec=spec,
            threshold=threshold,
            target_horizon_bars=target_horizon_bars,
            spk_parent_selection=parent_vs_spk,
            spk_short_basket=spk_short_basket,
        )
        for spec in CONFIRMATION_SPECS
    }
    kept = [
        label
        for label, payload in results.items()
        if payload.get("verdict", {}).get("label") == "stage0_keep_for_strict_falsification"
    ]
    report = {
        "artifact_family": "quant_spk_non_kline_confirmation_stage0",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": target_horizon_bars,
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "baseline_spk_variant": "xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1",
        "confirmation_threshold": threshold,
        "features_artifact": str(spk_eval._features_artifact_path(as_of)),  # noqa: SLF001
        "feature_presence": _feature_presence(frame),
        "parent_vs_spk_selection": parent_vs_spk,
        "spk_short_basket_summary": spk_short_basket,
        "kept_for_strict_falsification": kept,
        "status": "stage0_keep" if kept else "stage0_no_kept_variants",
        "results": results,
    }
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote SP-K non-kline confirmation report to {output_path}")
    print(
        json.dumps(
            {
                label: {
                    "verdict": payload["verdict"]["label"],
                    "passed": payload["verdict"]["passed_check_count"],
                    "total_replacements": payload["parent_vs_variant_selection"].get("total_replacements"),
                    f"entered_next_{target_horizon_bars}d_mean": payload["parent_vs_variant_selection"].get(
                        f"entered_next_{target_horizon_bars}d_mean"
                    ),
                    "entered_next_1d_squeeze_gt_5pct_fraction": payload["parent_vs_variant_selection"].get(
                        "entered_next_1d_squeeze_gt_5pct_fraction"
                    ),
                }
                for label, payload in results.items()
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
