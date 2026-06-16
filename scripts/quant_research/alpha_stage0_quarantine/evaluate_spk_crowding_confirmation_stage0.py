from __future__ import annotations

import argparse
import json
import sys
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


CONTRACT_VERSION = "quant_spk_crowding_confirmation_stage0.v1"
DEFAULT_AS_OF = "2026-05-02"
CROWDING_COLUMNS = [
    "funding_zscore_20",
    "oi_change_5",
    "basis_zscore_20",
    "pump_funding_oi_crowding_score_3d",
    "coinglass_liq_intraday_concentration_24h",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage-0 diagnostic for SP-K + extreme Funding/OI crowding confirmation. "
            "The rule only allows SP-K short-slot replacements when the replacement "
            "candidate is in the top crowding quantile for the timestamp."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--crowding-quantile", type=float, default=0.90)
    parser.add_argument("--output-path", type=Path, default=None)
    return parser


def _timestamp_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    grouped = values.groupby(frame["timestamp_ms"])
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _add_crowding_confirmation(frame: pd.DataFrame, *, crowding_quantile: float) -> pd.DataFrame:
    out = frame.copy()
    score = pd.Series(np.zeros(len(out)), index=out.index, dtype="float64")
    for column in CROWDING_COLUMNS:
        score = score + _timestamp_zscore(out, column)
    out["funding_oi_crowded_squeeze_score_v1"] = score / float(len(CROWDING_COLUMNS))
    out["funding_oi_crowding_pct"] = (
        out["funding_oi_crowded_squeeze_score_v1"]
        .groupby(out["timestamp_ms"])
        .rank(method="average", pct=True)
        .fillna(0.0)
    )
    out["spk_crowding_confirmation_missing_flag"] = (
        out["funding_oi_crowding_pct"] < float(crowding_quantile)
    )
    return out


def _spk_crowding_confirmed_score(frame: pd.DataFrame) -> pd.Series:
    prepared = _add_crowding_confirmation(frame, crowding_quantile=0.90)
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        prepared,
        base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="spk_crowding_confirmation_missing_flag",
    )


def _feature_presence(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        col: {
            "present": col in frame.columns,
            "non_null_fraction": float(pd.to_numeric(frame[col], errors="coerce").notna().mean())
            if col in frame.columns and len(frame)
            else 0.0,
        }
        for col in CROWDING_COLUMNS
    }


def _short_basket_summary(
    frame: pd.DataFrame,
    *,
    scorer,
    target_horizon_bars: int,
) -> dict[str, Any]:
    scored = _add_crowding_confirmation(frame, crowding_quantile=0.90)
    scored["score"] = scorer(scored)
    rows: list[dict[str, Any]] = []
    for _, group in scored.groupby("timestamp_ms"):
        shorts = group.sort_values("score", ascending=False).tail(min(3, len(group))).copy()
        rows.extend(shorts.to_dict("records"))
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "empty"}
    h_col = f"forward_{target_horizon_bars}d_log_return"
    fwd = pd.to_numeric(basket[h_col], errors="coerce").dropna()
    crowding = pd.to_numeric(basket["funding_oi_crowding_pct"], errors="coerce").dropna()
    return {
        "status": "ok",
        "n_short_rows": int(len(basket)),
        "next_horizon_mean": float(fwd.mean()) if len(fwd) else 0.0,
        "next_horizon_negative_fraction": float((fwd < 0).mean()) if len(fwd) else 0.0,
        "crowding_pct_mean": float(crowding.mean()) if len(crowding) else 0.0,
        "crowding_pct_ge_090_fraction": float((crowding >= 0.90).mean()) if len(crowding) else 0.0,
        "mid_liquidity_short_fraction": float(
            basket["liquidity_bucket"].astype(str).eq("mid_liquidity").mean()
        )
        if "liquidity_bucket" in basket.columns
        else 0.0,
    }


def _verdict(
    *,
    spk_vs_confirmed: dict[str, Any],
    spk_parent_selection: dict[str, Any],
    confirmed_parent_selection: dict[str, Any],
    short_basket_summary: dict[str, Any],
) -> dict[str, Any]:
    confirmed_entered = confirmed_parent_selection.get("entered_next_10d_mean")
    spk_entered = spk_parent_selection.get("entered_next_10d_mean")
    confirmed_replacements = int(confirmed_parent_selection.get("total_replacements") or 0)
    spk_basket = short_basket_summary.get("spk", {})
    confirmed_basket = short_basket_summary.get("spk_crowding_confirmed", {})
    checks = {
        "confirmed_has_replacements": confirmed_replacements >= 50,
        "confirmed_less_active_than_spk": confirmed_replacements
        < int(spk_parent_selection.get("total_replacements") or 0),
        "confirmed_entered_shorts_negative_h10d": confirmed_entered is not None and float(confirmed_entered) < 0,
        "confirmed_entered_beats_spk_entered_h10d": (
            confirmed_entered is not None
            and spk_entered is not None
            and float(confirmed_entered) < float(spk_entered)
        ),
        "confirmed_differs_from_spk": int(spk_vs_confirmed.get("total_replacements") or 0) > 0,
        "parent_delta_positive_h10d": (
            confirmed_parent_selection.get("entered_next_10d_mean") is not None
            and confirmed_parent_selection.get("exited_next_10d_mean") is not None
            and float(confirmed_parent_selection["entered_next_10d_mean"])
            < float(confirmed_parent_selection["exited_next_10d_mean"])
        ),
        "confirmed_short_basket_beats_spk_h10d": (
            confirmed_basket.get("next_horizon_mean") is not None
            and spk_basket.get("next_horizon_mean") is not None
            and float(confirmed_basket["next_horizon_mean"]) <= float(spk_basket["next_horizon_mean"])
        ),
    }
    passed = sum(1 for value in checks.values() if value)
    if (
        passed >= 6
        and checks["confirmed_entered_beats_spk_entered_h10d"]
        and checks["confirmed_short_basket_beats_spk_h10d"]
    ):
        label = "stage0_keep_for_manifest"
    elif passed >= 3:
        label = "stage0_watch"
    else:
        label = "stage0_reject"
    return {"label": label, "passed_check_count": passed, "total_check_count": len(checks), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    target_horizon_bars = int(args.target_horizon_bars)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "spk_crowding_confirmation_stage0.json")

    frame = spk_eval._build_risk_frame(  # noqa: SLF001
        spk_eval._features_artifact_path(as_of),  # noqa: SLF001
        target_horizon_bars=target_horizon_bars,
    )
    frame = _add_crowding_confirmation(frame, crowding_quantile=float(args.crowding_quantile))

    def confirmed_scorer(local_frame: pd.DataFrame) -> pd.Series:
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            local_frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            candidate_veto_column="spk_crowding_confirmation_missing_flag",
        )

    parent_vs_spk = spk_eval._selection_change_diagnostic(  # noqa: SLF001
        frame=frame,
        baseline_scorer=xs_alpha_ontology_v5_score,
        candidate_scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        long_count=3,
        short_count=3,
        target_horizon_bars=target_horizon_bars,
    )
    parent_vs_confirmed = spk_eval._selection_change_diagnostic(  # noqa: SLF001
        frame=frame,
        baseline_scorer=xs_alpha_ontology_v5_score,
        candidate_scorer=confirmed_scorer,
        long_count=3,
        short_count=3,
        target_horizon_bars=target_horizon_bars,
    )
    spk_vs_confirmed = spk_eval._selection_change_diagnostic(  # noqa: SLF001
        frame=frame,
        baseline_scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        candidate_scorer=confirmed_scorer,
        long_count=3,
        short_count=3,
        target_horizon_bars=target_horizon_bars,
    )

    short_basket_summary = {
        "parent": _short_basket_summary(
            frame,
            scorer=xs_alpha_ontology_v5_score,
            target_horizon_bars=target_horizon_bars,
        ),
        "spk": _short_basket_summary(
            frame,
            scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
            target_horizon_bars=target_horizon_bars,
        ),
        "spk_crowding_confirmed": _short_basket_summary(
            frame,
            scorer=confirmed_scorer,
            target_horizon_bars=target_horizon_bars,
        ),
    }
    payload = {
        "artifact_family": "quant_spk_crowding_confirmation_stage0",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": target_horizon_bars,
        "features_artifact": str(spk_eval._features_artifact_path(as_of)),  # noqa: SLF001
        "crowding_quantile": float(args.crowding_quantile),
        "crowding_columns": CROWDING_COLUMNS,
        "feature_presence": _feature_presence(frame),
        "parent_vs_spk_selection": parent_vs_spk,
        "parent_vs_spk_crowding_confirmed_selection": parent_vs_confirmed,
        "spk_vs_spk_crowding_confirmed_selection": spk_vs_confirmed,
        "short_basket_summary": short_basket_summary,
        "verdict": _verdict(
            spk_vs_confirmed=spk_vs_confirmed,
            spk_parent_selection=parent_vs_spk,
            confirmed_parent_selection=parent_vs_confirmed,
            short_basket_summary=short_basket_summary,
        ),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
