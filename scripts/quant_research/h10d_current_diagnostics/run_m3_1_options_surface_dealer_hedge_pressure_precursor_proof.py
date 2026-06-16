from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_VERSION = "quant_m3_1_options_surface_dealer_hedge_pressure_precursor_proof.v1"
DEFAULT_AS_OF = "2026-06-15-full-backfill-20230401-20260613"
BASELINE_LABEL = "baseline_no_options_surface_overlay"
PRECURSOR_LABEL = "m3_1_options_surface_dealer_hedge_pressure_transition_precursor_v0"
DEFAULT_V1_OUTPUT_SUBDIR = "m3_1_options_surface_overlay_v1_ablation"
DEFAULT_OUTPUT_SUBDIR = "m3_1_options_surface_dealer_hedge_pressure_transition_precursor_v0_proof"
DEFAULT_FEATURE_PANEL = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91"
    / "features.csv.gz"
)
DEFAULT_PREREG_DOC = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "m3_1_options_surface_new_precursor_dealer_hedge_pressure_transition_preregistration_2026_06_15.md"
)

REQUIRED_SUBJECTS = ("BTC", "ETH")
WINDOW_KEY = ("phase_offset_days", "window_index", "test_start_utc", "test_end_utc")

MIN_TRIGGERED_COUNT = 16
MIN_TRIGGERED_BASELINE_LOSS_FRACTION = 0.60
MIN_LOSS_FRACTION_LIFT = 0.10
MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION = 0.40
MAX_TRIGGERED_BASELINE_NET_RETURN_SUM = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M3.1 dealer hedge-pressure transition precursor-only "
            "loss-state proof. This writes retained proof artifacts only and "
            "does not run a trading action, multiplier, overlay, or Stage B ablation."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--v1-output-root", type=Path, default=None)
    parser.add_argument("--feature-panel", type=Path, default=DEFAULT_FEATURE_PANEL)
    parser.add_argument("--preregistration-doc", type=Path, default=DEFAULT_PREREG_DOC)
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def finite_float(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def median_float(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return finite_float(values.median())


def pct(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def normalise_subject(value: Any) -> str:
    text = str(value or "").strip().upper()
    for suffix in ("USDT", "USD", "-PERP", "PERP"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def load_csv(path: Path, *, required_columns: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, low_memory=False)
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise RuntimeError(f"{path} missing required columns: {missing}")
    return frame


def to_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce").dt.date


def build_options_context(path: Path) -> pd.DataFrame:
    required = {
        "decision_date_utc",
        "required_subject_count",
        "top2_iv_term_slope_min",
        "top2_iv_25d_skew_residual_median",
        "top2_signed_dealer_gamma_median",
        "top2_vanna_charm_max",
    }
    frame = load_csv(path, required_columns=required).copy()
    frame["context_date"] = to_date_series(frame["decision_date_utc"])
    numeric_columns = [
        "required_subject_count",
        "top2_iv_term_slope_min",
        "top2_iv_25d_skew_residual_median",
        "top2_signed_dealer_gamma_median",
        "top2_vanna_charm_max",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["options_ready"] = (
        frame["context_date"].notna()
        & frame["required_subject_count"].ge(len(REQUIRED_SUBJECTS))
        & frame[
            [
                "top2_iv_term_slope_min",
                "top2_iv_25d_skew_residual_median",
                "top2_signed_dealer_gamma_median",
                "top2_vanna_charm_max",
            ]
        ]
        .notna()
        .all(axis=1)
    )
    return frame.sort_values("context_date").reset_index(drop=True)


def build_tape_context(path: Path) -> pd.DataFrame:
    required = {
        "date_utc",
        "subject",
        "return_1",
        "momentum_5",
        "basis_velocity_3d",
        "perp_quote_volume_usd",
    }
    optional_taker = {"coinglass_taker_net_volume_24h", "coinglass_taker_imbalance_5d_sum"}
    frame = load_csv(path, required_columns=required).copy()
    if not optional_taker.intersection(frame.columns):
        raise RuntimeError(
            f"{path} missing taker pressure column: one of {sorted(optional_taker)} is required"
        )
    frame["subject"] = frame["subject"].map(normalise_subject)
    frame = frame.loc[frame["subject"].isin(REQUIRED_SUBJECTS)].copy()
    frame["context_date"] = to_date_series(frame["date_utc"])
    numeric_columns = [
        "return_1",
        "momentum_5",
        "basis_velocity_3d",
        "perp_quote_volume_usd",
        *[column for column in optional_taker if column in frame.columns],
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    taker_column = (
        "coinglass_taker_net_volume_24h"
        if "coinglass_taker_net_volume_24h" in frame.columns
        else "coinglass_taker_imbalance_5d_sum"
    )

    rows: list[dict[str, Any]] = []
    for context_date, group in frame.sort_values(["context_date", "subject"]).groupby("context_date"):
        subject_rows = group.drop_duplicates("subject", keep="last").set_index("subject")
        required_values = subject_rows.reindex(REQUIRED_SUBJECTS)
        required_subject_count = int(sum(subject in subject_rows.index for subject in REQUIRED_SUBJECTS))
        tape_ready = bool(
            required_subject_count == len(REQUIRED_SUBJECTS)
            and required_values[
                [
                    "return_1",
                    "momentum_5",
                    "basis_velocity_3d",
                    "perp_quote_volume_usd",
                    taker_column,
                ]
            ]
            .notna()
            .to_numpy()
            .all()
        )
        rows.append(
            {
                "context_date": context_date,
                "required_subject_count": required_subject_count,
                "tape_ready": tape_ready,
                "top2_return_1_median": median_float(required_values["return_1"]),
                "top2_momentum_5_median": median_float(required_values["momentum_5"]),
                "top2_basis_velocity_3d_median": median_float(required_values["basis_velocity_3d"]),
                "top2_taker_pressure_median": median_float(required_values[taker_column]),
                "top2_perp_quote_volume_usd_median": median_float(required_values["perp_quote_volume_usd"]),
                "taker_pressure_source_column": taker_column,
            }
        )
    return pd.DataFrame(rows).sort_values("context_date").reset_index(drop=True)


def normalise_windows(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["phase_offset_days"] = pd.to_numeric(working["phase_offset_days"], errors="coerce").astype("Int64")
    working["window_index"] = pd.to_numeric(working["window_index"], errors="coerce").astype("Int64")
    working["net_return"] = pd.to_numeric(working["net_return"], errors="coerce")
    for column in ("test_start_utc", "test_end_utc"):
        working[column] = working[column].astype(str)
    working["test_start_date"] = to_date_series(working["test_start_utc"])
    return working


def latest_ready_rows_before(frame: pd.DataFrame, *, target_date: Any, ready_column: str, count: int) -> pd.DataFrame:
    eligible = frame.loc[frame["context_date"].lt(target_date) & frame[ready_column].fillna(False)].copy()
    return eligible.tail(count)


def duplicate_keys(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame.duplicated(list(WINDOW_KEY), keep=False), list(WINDOW_KEY)].copy()


def evaluate_precursor(
    *,
    window: pd.Series,
    options_context: pd.DataFrame,
    tape_context: pd.DataFrame,
) -> dict[str, Any]:
    target_date = window["test_start_date"]
    base: dict[str, Any] = {
        "phase_offset_days": int(window["phase_offset_days"]),
        "window_index": int(window["window_index"]),
        "test_start_utc": window["test_start_utc"],
        "test_end_utc": window["test_end_utc"],
        "baseline_net_return": finite_float(window["net_return"]),
        "baseline_loss_window": bool(float(window["net_return"]) < 0),
        "baseline_positive_window": bool(float(window["net_return"]) > 0),
        "baseline_zero_window": bool(float(window["net_return"]) == 0),
        "precursor_label": PRECURSOR_LABEL,
        "precursor_triggered": False,
        "options_transition": False,
        "gamma_crossed_negative": False,
        "gamma_more_negative_two_days": False,
        "expiry_pressure_context": False,
        "vanna_charm_rising": False,
        "skew_rising_term_flattening": False,
        "tape_confirmation": False,
        "price_path_family_confirmed": False,
        "derivatives_pressure_family_confirmed": False,
        "perp_volume_expansion_confirmed": False,
        "failure_reason": "",
    }
    if pd.isna(target_date):
        base["failure_reason"] = "missing_test_start_date"
        return base

    option_rows = latest_ready_rows_before(
        options_context,
        target_date=target_date,
        ready_column="options_ready",
        count=3,
    )
    if option_rows.shape[0] < 3:
        base["failure_reason"] = "insufficient_prior_options_context"
        return base
    opt_prev2, opt_prev1, opt_cur = [row for _, row in option_rows.iterrows()]
    gamma_prev2 = finite_float(opt_prev2["top2_signed_dealer_gamma_median"])
    gamma_prev1 = finite_float(opt_prev1["top2_signed_dealer_gamma_median"])
    gamma_cur = finite_float(opt_cur["top2_signed_dealer_gamma_median"])
    vanna_prev1 = finite_float(opt_prev1["top2_vanna_charm_max"])
    vanna_cur = finite_float(opt_cur["top2_vanna_charm_max"])
    skew_prev1 = finite_float(opt_prev1["top2_iv_25d_skew_residual_median"])
    skew_cur = finite_float(opt_cur["top2_iv_25d_skew_residual_median"])
    term_prev1 = finite_float(opt_prev1["top2_iv_term_slope_min"])
    term_cur = finite_float(opt_cur["top2_iv_term_slope_min"])
    if any(
        value is None
        for value in (
            gamma_prev2,
            gamma_prev1,
            gamma_cur,
            vanna_prev1,
            vanna_cur,
            skew_prev1,
            skew_cur,
            term_prev1,
            term_cur,
        )
    ):
        base["failure_reason"] = "incomplete_prior_options_context"
        return base

    gamma_crossed_negative = bool(gamma_prev1 >= 0 and gamma_cur < 0)
    gamma_more_negative_two_days = bool(gamma_cur < gamma_prev1 and gamma_prev1 < gamma_prev2)
    options_transition = gamma_crossed_negative or gamma_more_negative_two_days
    vanna_charm_rising = bool(vanna_cur > vanna_prev1)
    skew_rising_term_flattening = bool(skew_cur > skew_prev1 and abs(term_cur) < abs(term_prev1))
    expiry_pressure_context = vanna_charm_rising or skew_rising_term_flattening

    tape_rows = latest_ready_rows_before(
        tape_context,
        target_date=target_date,
        ready_column="tape_ready",
        count=2,
    )
    if tape_rows.empty:
        base["failure_reason"] = "missing_prior_tape_context"
        return base
    tape_cur = tape_rows.iloc[-1]
    tape_prev = tape_rows.iloc[-2] if tape_rows.shape[0] >= 2 else None
    ret = finite_float(tape_cur["top2_return_1_median"])
    momentum = finite_float(tape_cur["top2_momentum_5_median"])
    basis_velocity = finite_float(tape_cur["top2_basis_velocity_3d_median"])
    taker_pressure = finite_float(tape_cur["top2_taker_pressure_median"])
    perp_volume = finite_float(tape_cur["top2_perp_quote_volume_usd_median"])
    prev_perp_volume = finite_float(tape_prev["top2_perp_quote_volume_usd_median"]) if tape_prev is not None else None
    if any(value is None for value in (ret, momentum, basis_velocity, taker_pressure, perp_volume)):
        base["failure_reason"] = "incomplete_prior_tape_context"
        return base
    price_path_family_confirmed = bool(ret < 0 or momentum < 0)
    perp_volume_expansion_confirmed = bool(prev_perp_volume is not None and perp_volume > prev_perp_volume)
    derivatives_pressure_family_confirmed = bool(
        basis_velocity <= 0 or taker_pressure <= 0 or perp_volume_expansion_confirmed
    )
    tape_confirmation = price_path_family_confirmed and derivatives_pressure_family_confirmed
    precursor_triggered = bool(options_transition and expiry_pressure_context and tape_confirmation)

    base.update(
        {
            "options_transition": options_transition,
            "gamma_crossed_negative": gamma_crossed_negative,
            "gamma_more_negative_two_days": gamma_more_negative_two_days,
            "expiry_pressure_context": expiry_pressure_context,
            "vanna_charm_rising": vanna_charm_rising,
            "skew_rising_term_flattening": skew_rising_term_flattening,
            "tape_confirmation": tape_confirmation,
            "price_path_family_confirmed": price_path_family_confirmed,
            "derivatives_pressure_family_confirmed": derivatives_pressure_family_confirmed,
            "perp_volume_expansion_confirmed": perp_volume_expansion_confirmed,
            "precursor_triggered": precursor_triggered,
            "options_context_date": str(opt_cur["context_date"]),
            "options_context_prev_date": str(opt_prev1["context_date"]),
            "options_context_prev2_date": str(opt_prev2["context_date"]),
            "top2_signed_dealer_gamma_prev2": gamma_prev2,
            "top2_signed_dealer_gamma_prev": gamma_prev1,
            "top2_signed_dealer_gamma_current": gamma_cur,
            "top2_vanna_charm_prev": vanna_prev1,
            "top2_vanna_charm_current": vanna_cur,
            "top2_iv_25d_skew_residual_prev": skew_prev1,
            "top2_iv_25d_skew_residual_current": skew_cur,
            "top2_iv_term_slope_prev": term_prev1,
            "top2_iv_term_slope_current": term_cur,
            "tape_context_date": str(tape_cur["context_date"]),
            "tape_context_prev_date": str(tape_prev["context_date"]) if tape_prev is not None else None,
            "top2_return_1_median": ret,
            "top2_momentum_5_median": momentum,
            "top2_basis_velocity_3d_median": basis_velocity,
            "top2_taker_pressure_median": taker_pressure,
            "top2_perp_quote_volume_usd_median": perp_volume,
            "top2_perp_quote_volume_usd_prev": prev_perp_volume,
            "taker_pressure_source_column": str(tape_cur["taker_pressure_source_column"]),
            "failure_reason": "triggered" if precursor_triggered else "conditions_not_met",
        }
    )
    return base


def build_alignment(
    *,
    windows: pd.DataFrame,
    options_context: pd.DataFrame,
    tape_context: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    baseline = windows.loc[windows["label"].eq(BASELINE_LABEL)].copy()
    blockers: list[str] = []
    duplicate_count = int(duplicate_keys(baseline).shape[0])
    if duplicate_count:
        blockers.append("join_key_duplicate_count_nonzero")
    records = [
        evaluate_precursor(window=row, options_context=options_context, tape_context=tape_context)
        for _, row in baseline.iterrows()
    ]
    alignment = pd.DataFrame(records).sort_values(list(WINDOW_KEY)).reset_index(drop=True)
    missing_join_count = 0
    all_window_count = int(alignment.shape[0])
    all_loss_count = int(alignment["baseline_loss_window"].sum())
    all_loss_fraction = pct(all_loss_count, all_window_count)
    triggered = alignment.loc[alignment["precursor_triggered"]].copy()
    triggered_window_count = int(triggered.shape[0])
    triggered_decision_count = triggered_window_count
    triggered_baseline_loss_count = int(triggered["baseline_loss_window"].sum())
    triggered_baseline_positive_count = int(triggered["baseline_positive_window"].sum())
    triggered_baseline_zero_count = int(triggered["baseline_zero_window"].sum())
    triggered_baseline_loss_fraction = pct(triggered_baseline_loss_count, triggered_window_count)
    triggered_baseline_positive_fraction = pct(triggered_baseline_positive_count, triggered_window_count)
    triggered_baseline_net_return_sum = float(triggered["baseline_net_return"].fillna(0.0).sum())
    loss_fraction_lift = (
        None
        if triggered_baseline_loss_fraction is None or all_loss_fraction is None
        else float(triggered_baseline_loss_fraction - all_loss_fraction)
    )

    if triggered_window_count < MIN_TRIGGERED_COUNT:
        blockers.append("precursor_trigger_count_below_min_16")
    if triggered_baseline_loss_fraction is None or triggered_baseline_loss_fraction < MIN_TRIGGERED_BASELINE_LOSS_FRACTION - 1e-12:
        blockers.append("triggered_baseline_loss_fraction_below_0_60")
    if loss_fraction_lift is None or loss_fraction_lift < MIN_LOSS_FRACTION_LIFT - 1e-12:
        blockers.append("loss_fraction_lift_below_0_10")
    if (
        triggered_baseline_positive_fraction is None
        or triggered_baseline_positive_fraction > MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION + 1e-12
    ):
        blockers.append("triggered_baseline_positive_fraction_above_0_40")
    if triggered_baseline_net_return_sum > MAX_TRIGGERED_BASELINE_NET_RETURN_SUM + 1e-12:
        blockers.append("triggered_baseline_net_return_sum_positive")
    if duplicate_count != 0:
        blockers.append("join_key_duplicate_count_nonzero")
    if missing_join_count != 0:
        blockers.append("missing_join_count_nonzero")

    metrics = {
        "all_window_count": all_window_count,
        "all_baseline_loss_count": all_loss_count,
        "all_window_baseline_loss_fraction": all_loss_fraction,
        "precursor_triggered_window_count": triggered_window_count,
        "precursor_triggered_decision_count": triggered_decision_count,
        "triggered_baseline_loss_count": triggered_baseline_loss_count,
        "triggered_baseline_loss_fraction": triggered_baseline_loss_fraction,
        "triggered_baseline_positive_count": triggered_baseline_positive_count,
        "triggered_baseline_positive_fraction": triggered_baseline_positive_fraction,
        "triggered_baseline_zero_count": triggered_baseline_zero_count,
        "triggered_baseline_net_return_sum": triggered_baseline_net_return_sum,
        "loss_fraction_lift": loss_fraction_lift,
        "options_transition_count": int(alignment["options_transition"].sum()),
        "expiry_pressure_context_count": int(alignment["expiry_pressure_context"].sum()),
        "tape_confirmation_count": int(alignment["tape_confirmation"].sum()),
        "price_path_family_count": int(alignment["price_path_family_confirmed"].sum()),
        "derivatives_pressure_family_count": int(alignment["derivatives_pressure_family_confirmed"].sum()),
        "join_key_duplicate_count": duplicate_count,
        "missing_join_count": missing_join_count,
    }
    allowed = not blockers
    return alignment, {
        "blockers": sorted(set(blockers), key=blockers.index),
        "metrics": metrics,
        "loss_state_proof_allowed": allowed,
        "stage_b_return_ablation_allowed": False,
    }


def precursor_definition_payload() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "precursor_label": PRECURSOR_LABEL,
        "status": "precursor_only_no_trading_action",
        "rules": {
            "options_transition": (
                "top2 signed dealer gamma crosses from non-negative to negative OR "
                "becomes more negative for two consecutive PIT-safe daily observations"
            ),
            "expiry_pressure_context": (
                "top2 vanna/charm rises OR top2 put-skew residual rises while "
                "absolute term slope flattens"
            ),
            "tape_confirmation": (
                "price-path family confirms downside pressure AND derivatives-pressure "
                "family confirms downside pressure before the decision window"
            ),
            "precursor_triggered": "options_transition AND expiry_pressure_context AND tape_confirmation",
        },
        "non_actions": [
            "no portfolio target multiplier",
            "no exposure reduction",
            "no long/short replacement",
            "no score-layer admission",
            "no manifest mutation",
            "no paper-shadow use",
            "no live timer scheduler or remote-runner use",
            "no Stage B return ablation",
        ],
        "proof_gates": {
            "triggered_window_count_min": MIN_TRIGGERED_COUNT,
            "triggered_baseline_loss_fraction_min": MIN_TRIGGERED_BASELINE_LOSS_FRACTION,
            "loss_fraction_lift_min": MIN_LOSS_FRACTION_LIFT,
            "triggered_baseline_positive_fraction_max": MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION,
            "triggered_baseline_net_return_sum_max": MAX_TRIGGERED_BASELINE_NET_RETURN_SUM,
            "join_key_duplicate_count": 0,
            "missing_join_count": 0,
        },
    }


def main() -> int:
    args = parse_args()
    v1_root = args.v1_output_root
    if v1_root is None:
        v1_root = (
            ROOT
            / "artifacts"
            / "quant_research"
            / "factor_reports"
            / str(args.as_of)
            / DEFAULT_V1_OUTPUT_SUBDIR
        )
    output_root = args.output_root
    if output_root is None:
        output_root = (
            ROOT
            / "artifacts"
            / "quant_research"
            / "factor_reports"
            / str(args.as_of)
            / DEFAULT_OUTPUT_SUBDIR
        )
    output_root.mkdir(parents=True, exist_ok=True)

    windows_path = v1_root / "overlay_windows.csv"
    options_context_path = v1_root / "options_top2_context_daily.csv"
    required_window_columns = {
        "label",
        "phase_offset_days",
        "window_index",
        "test_start_utc",
        "test_end_utc",
        "net_return",
    }
    windows = normalise_windows(load_csv(windows_path, required_columns=required_window_columns))
    options_context = build_options_context(options_context_path)
    tape_context = build_tape_context(args.feature_panel)
    alignment, decision = build_alignment(
        windows=windows,
        options_context=options_context,
        tape_context=tape_context,
    )

    definition_path = output_root / "precursor_definition.json"
    alignment_path = output_root / "precursor_loss_state_alignment_windows.csv"
    summary_path = output_root / "precursor_loss_state_alignment_summary.json"
    audit_path = output_root / "precursor_input_audit.json"

    definition = precursor_definition_payload()
    write_json(definition_path, definition)
    alignment.to_csv(alignment_path, index=False)

    input_audit = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "preregistration_doc": str(args.preregistration_doc),
        "preregistration_doc_sha256": sha256_file(args.preregistration_doc)
        if args.preregistration_doc.exists()
        else None,
        "inputs": {
            "v1_output_root": str(v1_root),
            "overlay_windows_csv": str(windows_path),
            "overlay_windows_sha256": sha256_file(windows_path),
            "options_top2_context_daily_csv": str(options_context_path),
            "options_top2_context_daily_sha256": sha256_file(options_context_path),
            "feature_panel": str(args.feature_panel),
            "feature_panel_sha256": sha256_file(args.feature_panel),
        },
        "pit_policy": {
            "window_key": list(WINDOW_KEY),
            "decision_timestamp": "test_start_utc",
            "options_context_policy": "latest three ready daily top2 options observations strictly before test_start_utc",
            "tape_context_policy": "latest one or two ready BTC/ETH spot/perp feature observations strictly before test_start_utc",
        },
    }
    write_json(audit_path, input_audit)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": "computed" if decision["loss_state_proof_allowed"] else "computed_failed_loss_state_proof",
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "precursor_label": PRECURSOR_LABEL,
        "diagnostic_scope": "precursor_only_loss_state_proof",
        "loss_state_proof_allowed": decision["loss_state_proof_allowed"],
        "stage_b_return_ablation_allowed": False,
        "research_watch_state_allowed": False,
        "eligible_for_research_watch_review": False,
        "score_layer_admission_allowed": False,
        "active_manifest_mutation_authorized": False,
        "paper_shadow_use_authorized": False,
        "live_or_timer_overlay_activation_authorized": False,
        "remote_runner_use_authorized": False,
        "trading_action_authorized": False,
        "portfolio_multiplier_defined": False,
        "blockers": decision["blockers"],
        "metrics": decision["metrics"],
        "artifacts": {
            "precursor_definition_json": str(definition_path),
            "precursor_loss_state_alignment_summary_json": str(summary_path),
            "precursor_loss_state_alignment_windows_csv": str(alignment_path),
            "precursor_input_audit_json": str(audit_path),
        },
        "input_audit": input_audit,
    }
    write_json(summary_path, summary)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "loss_state_proof_allowed": summary["loss_state_proof_allowed"],
                "stage_b_return_ablation_allowed": summary["stage_b_return_ablation_allowed"],
                "trading_action_authorized": summary["trading_action_authorized"],
                "blockers": summary["blockers"],
                "metrics": summary["metrics"],
                "summary_json": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
