from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_VERSION = "quant_m3_1_options_surface_v2_loss_state_alignment.v1"
DEFAULT_AS_OF = "2026-06-15-full-backfill-20230401-20260613"
BASELINE_LABEL = "baseline_no_options_surface_overlay"
V1_PRECURSOR_LABEL = "m3_1_options_surface_signed_gamma_put_skew_throttle_v1"
V2_CANDIDATE_LABEL = "m3_1_options_surface_loss_state_confirmed_throttle_v2"

DEFAULT_V1_OUTPUT_SUBDIR = "m3_1_options_surface_overlay_v1_ablation"
DEFAULT_OUTPUT_SUBDIR = "m3_1_options_surface_overlay_v2_loss_state_alignment"

MIN_TRIGGERED_COUNT = 16
MIN_TRIGGERED_BASELINE_LOSS_FRACTION = 0.60
MIN_LOSS_FRACTION_LIFT = 0.10
MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION = 0.40
MAX_TRIGGERED_BASELINE_NET_RETURN_SUM = 0.0

WINDOW_KEY = ("phase_offset_days", "window_index", "test_start_utc", "test_end_utc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run only the M3.1 v2 Stage A loss-state alignment diagnostic using "
            "retained v1 precursor trigger artifacts. This does not run a v2 "
            "throttle ablation."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--v1-output-root", type=Path, default=None)
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


def load_csv(path: Path, *, required_columns: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise RuntimeError(f"{path} missing required columns: {missing}")
    return frame


def normalise_windows(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["phase_offset_days"] = pd.to_numeric(working["phase_offset_days"], errors="coerce").astype("Int64")
    working["window_index"] = pd.to_numeric(working["window_index"], errors="coerce").astype("Int64")
    for column in ("net_return", "overlay_triggered_decision_count", "vol_stress_trigger_count", "gamma_expiry_trigger_count"):
        working[column] = pd.to_numeric(working[column], errors="coerce")
    for column in ("test_start_utc", "test_end_utc"):
        working[column] = working[column].astype(str)
    return working


def duplicate_keys(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame.duplicated(list(WINDOW_KEY), keep=False), list(WINDOW_KEY)].copy()


def key_set(frame: pd.DataFrame) -> set[tuple[Any, ...]]:
    return set(map(tuple, frame.loc[:, list(WINDOW_KEY)].itertuples(index=False, name=None)))


def pct(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def blocker_if_fraction(
    *,
    value: float | None,
    threshold: float,
    below_name: str,
) -> str | None:
    if value is None or value < threshold - 1e-12:
        return below_name
    return None


def build_loss_alignment(
    *,
    windows: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_columns = [
        *WINDOW_KEY,
        "label",
        "kind",
        "net_return",
        "overlay_triggered_decision_count",
        "vol_stress_trigger_count",
        "gamma_expiry_trigger_count",
    ]
    baseline = windows.loc[windows["label"].eq(BASELINE_LABEL), required_columns].copy()
    candidate = windows.loc[windows["label"].eq(V1_PRECURSOR_LABEL), required_columns].copy()
    blockers: list[str] = []

    baseline_duplicates = duplicate_keys(baseline)
    candidate_duplicates = duplicate_keys(candidate)
    if not baseline_duplicates.empty or not candidate_duplicates.empty:
        blockers.append("loss_state_join_key_missing_or_duplicated")

    baseline_keys = key_set(baseline)
    candidate_keys = key_set(candidate)
    if baseline_keys != candidate_keys:
        blockers.append("loss_state_calendar_mismatch")

    joined = candidate.merge(
        baseline.loc[:, [*WINDOW_KEY, "net_return", "kind"]].rename(
            columns={
                "net_return": "baseline_net_return",
                "kind": "baseline_kind",
            }
        ),
        on=list(WINDOW_KEY),
        how="left",
        indicator=True,
    )
    joined = joined.rename(
        columns={
            "net_return": "v1_candidate_net_return",
            "kind": "v1_candidate_kind",
        }
    )
    missing_join_count = int(joined["_merge"].ne("both").sum())
    if missing_join_count:
        blockers.append("loss_state_join_key_missing_or_duplicated")

    joined["baseline_loss_window"] = joined["baseline_net_return"].lt(0)
    joined["baseline_positive_window"] = joined["baseline_net_return"].gt(0)
    joined["baseline_zero_window"] = joined["baseline_net_return"].eq(0)
    joined["precursor_triggered"] = joined["overlay_triggered_decision_count"].fillna(0).gt(0)
    joined["v1_delta_vs_baseline"] = joined["v1_candidate_net_return"] - joined["baseline_net_return"]
    joined["loss_state_join_status"] = joined["_merge"].astype(str)
    joined = joined.drop(columns=["_merge"])

    all_window_count = int(baseline.shape[0])
    all_loss_count = int(pd.to_numeric(baseline["net_return"], errors="coerce").lt(0).sum())
    all_loss_fraction = pct(all_loss_count, all_window_count)

    triggered = joined.loc[joined["precursor_triggered"]].copy()
    triggered_window_count = int(triggered.shape[0])
    triggered_decision_count = int(triggered["overlay_triggered_decision_count"].fillna(0).sum())
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
        blockers.append("loss_state_proof_trigger_count_below_min_16")
    fraction_blocker = blocker_if_fraction(
        value=triggered_baseline_loss_fraction,
        threshold=MIN_TRIGGERED_BASELINE_LOSS_FRACTION,
        below_name="triggered_baseline_loss_fraction_below_0_60",
    )
    if fraction_blocker:
        blockers.append(fraction_blocker)
    lift_blocker = blocker_if_fraction(
        value=loss_fraction_lift,
        threshold=MIN_LOSS_FRACTION_LIFT,
        below_name="loss_fraction_lift_below_0_10",
    )
    if lift_blocker:
        blockers.append(lift_blocker)
    if (
        triggered_baseline_positive_fraction is None
        or triggered_baseline_positive_fraction > MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION + 1e-12
    ):
        blockers.append("triggered_baseline_positive_fraction_above_0_40")
    if triggered_baseline_net_return_sum > MAX_TRIGGERED_BASELINE_NET_RETURN_SUM + 1e-12:
        blockers.append("triggered_baseline_net_return_sum_positive")

    metrics = {
        "all_window_count": all_window_count,
        "all_baseline_loss_count": all_loss_count,
        "all_window_baseline_loss_fraction": all_loss_fraction,
        "triggered_window_count": triggered_window_count,
        "triggered_decision_count": triggered_decision_count,
        "triggered_baseline_loss_count": triggered_baseline_loss_count,
        "triggered_baseline_loss_fraction": triggered_baseline_loss_fraction,
        "triggered_baseline_positive_count": triggered_baseline_positive_count,
        "triggered_baseline_positive_fraction": triggered_baseline_positive_fraction,
        "triggered_baseline_zero_count": triggered_baseline_zero_count,
        "triggered_baseline_net_return_sum": triggered_baseline_net_return_sum,
        "loss_fraction_lift": loss_fraction_lift,
        "vol_stress_trigger_count": int(triggered["vol_stress_trigger_count"].fillna(0).sum()),
        "signed_gamma_expiry_trigger_count": int(triggered["gamma_expiry_trigger_count"].fillna(0).sum()),
        "missing_join_count": missing_join_count,
        "baseline_duplicate_key_count": int(baseline_duplicates.shape[0]),
        "candidate_duplicate_key_count": int(candidate_duplicates.shape[0]),
    }
    return joined.sort_values(list(WINDOW_KEY)).reset_index(drop=True), {
        "blockers": sorted(set(blockers), key=blockers.index),
        "metrics": metrics,
        "stage_a_loss_state_proof_allowed": not blockers,
        "stage_b_return_ablation_allowed": not blockers,
    }


def build_daily_inputs(period_returns: pd.DataFrame) -> pd.DataFrame:
    baseline_daily = period_returns.loc[period_returns["candidate_label"].eq(BASELINE_LABEL)].copy()
    selected = [
        column
        for column in (
            "candidate_label",
            "window_index",
            "timestamp_ms",
            "timestamp_utc",
            "net_period_return",
            "gross_return_before_costs",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "turnover",
            "capacity_breach_count",
            "overlay_kind",
        )
        if column in baseline_daily.columns
    ]
    out = baseline_daily.loc[:, selected].copy()
    out["source_role"] = "baseline_daily_input_snapshot"
    out["stage_a_decision_input_used"] = False
    out["input_limitation"] = "v1_period_returns_file_has_window_index_only_no_phase_offset"
    return out


def render_markdown(path: Path, payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    lines = [
        "# M3.1 Options Surface v2 Loss-State Alignment",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Contract: `{payload['contract_version']}`",
        f"- Stage A allowed: `{payload['stage_a_loss_state_proof_allowed']}`",
        f"- Stage B return ablation allowed: `{payload['stage_b_return_ablation_allowed']}`",
        f"- Blockers: `{payload['blockers']}`",
        "",
        "## Metrics",
        "",
        f"- triggered windows: `{metrics['triggered_window_count']}`",
        f"- triggered decisions: `{metrics['triggered_decision_count']}`",
        f"- triggered baseline-loss fraction: `{metrics['triggered_baseline_loss_fraction']}`",
        f"- triggered baseline-positive fraction: `{metrics['triggered_baseline_positive_fraction']}`",
        f"- triggered baseline net-return sum: `{metrics['triggered_baseline_net_return_sum']}`",
        f"- all-window baseline-loss fraction: `{metrics['all_window_baseline_loss_fraction']}`",
        f"- loss-fraction lift: `{metrics['loss_fraction_lift']}`",
        f"- vol-put stress trigger count: `{metrics['vol_stress_trigger_count']}`",
        f"- signed-gamma expiry trigger count: `{metrics['signed_gamma_expiry_trigger_count']}`",
        "",
        "## Gates",
        "",
        f"- `triggered_window_count >= {MIN_TRIGGERED_COUNT}`",
        f"- `triggered_baseline_loss_fraction >= {MIN_TRIGGERED_BASELINE_LOSS_FRACTION}`",
        f"- `loss_fraction_lift >= {MIN_LOSS_FRACTION_LIFT}`",
        f"- `triggered_baseline_positive_fraction <= {MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION}`",
        f"- `triggered_baseline_net_return_sum <= {MAX_TRIGGERED_BASELINE_NET_RETURN_SUM}`",
        "",
        "## Boundary",
        "",
        "- Stage A diagnostic only.",
        "- No v2 throttle ablation was run.",
        "- No active registry, manifest, score-layer, live, timer, scheduler, or remote-runner mutation.",
        "",
        "## Artifacts",
        "",
    ]
    for key, value in sorted(payload["artifacts"].items()):
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    period_returns_path = v1_root / "overlay_period_returns_long.csv"
    summary_path = v1_root / "summary.json"
    required_window_columns = {
        "label",
        "kind",
        "phase_offset_days",
        "window_index",
        "test_start_utc",
        "test_end_utc",
        "net_return",
        "overlay_triggered_decision_count",
        "vol_stress_trigger_count",
        "gamma_expiry_trigger_count",
    }
    required_period_columns = {
        "candidate_label",
        "window_index",
        "timestamp_ms",
        "timestamp_utc",
        "net_period_return",
    }
    windows = normalise_windows(load_csv(windows_path, required_columns=required_window_columns))
    period_returns = load_csv(period_returns_path, required_columns=required_period_columns)

    alignment_windows, decision = build_loss_alignment(windows=windows)
    daily_inputs = build_daily_inputs(period_returns)

    alignment_windows_path = output_root / "loss_state_alignment_windows.csv"
    daily_inputs_path = output_root / "loss_state_alignment_daily_inputs.csv"
    summary_json_path = output_root / "loss_state_alignment_summary.json"
    summary_md_path = output_root / "loss_state_alignment_summary.md"
    alignment_windows.to_csv(alignment_windows_path, index=False)
    daily_inputs.to_csv(daily_inputs_path, index=False)

    payload = {
        "contract_version": CONTRACT_VERSION,
        "status": "computed" if decision["stage_a_loss_state_proof_allowed"] else "computed_failed_stage_a",
        "generated_at_utc": utc_now(),
        "as_of": str(args.as_of),
        "predecessor_candidate_label": V1_PRECURSOR_LABEL,
        "candidate_label": V2_CANDIDATE_LABEL,
        "baseline_variant_label": BASELINE_LABEL,
        "diagnostic_scope": "stage_a_loss_state_alignment_only",
        "stage_a_loss_state_proof_allowed": decision["stage_a_loss_state_proof_allowed"],
        "stage_b_return_ablation_allowed": decision["stage_b_return_ablation_allowed"],
        "research_watch_state_allowed": False,
        "eligible_for_research_watch_review": False,
        "score_layer_admission_allowed": False,
        "active_manifest_mutation_authorized": False,
        "v1_admission_policy_mutation_authorized": False,
        "live_or_timer_overlay_activation_authorized": False,
        "remote_runner_use_authorized": False,
        "blockers": decision["blockers"],
        "stage_a_gates": {
            "loss_state_proof_triggered_count_min": MIN_TRIGGERED_COUNT,
            "triggered_baseline_loss_fraction_min": MIN_TRIGGERED_BASELINE_LOSS_FRACTION,
            "loss_fraction_lift_min": MIN_LOSS_FRACTION_LIFT,
            "triggered_baseline_positive_fraction_max": MAX_TRIGGERED_BASELINE_POSITIVE_FRACTION,
            "triggered_baseline_net_return_sum_max": MAX_TRIGGERED_BASELINE_NET_RETURN_SUM,
        },
        "metrics": decision["metrics"],
        "input_audit": {
            "v1_output_root": str(v1_root),
            "v1_overlay_windows_csv": str(windows_path),
            "v1_overlay_windows_sha256": sha256_file(windows_path),
            "v1_overlay_period_returns_long_csv": str(period_returns_path),
            "v1_overlay_period_returns_long_sha256": sha256_file(period_returns_path),
            "v1_summary_json": str(summary_path) if summary_path.exists() else None,
            "v1_summary_sha256": sha256_file(summary_path) if summary_path.exists() else None,
            "window_key": list(WINDOW_KEY),
            "daily_input_limitation": "overlay_period_returns_long.csv has window_index only, so Stage A proof uses overlay_windows.csv phase/window/test keys.",
        },
        "artifacts": {
            "loss_state_alignment_summary_json": str(summary_json_path),
            "loss_state_alignment_summary_md": str(summary_md_path),
            "loss_state_alignment_windows_csv": str(alignment_windows_path),
            "loss_state_alignment_daily_inputs_csv": str(daily_inputs_path),
        },
    }
    write_json(summary_json_path, payload)
    render_markdown(summary_md_path, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "stage_a_loss_state_proof_allowed": payload["stage_a_loss_state_proof_allowed"],
                "stage_b_return_ablation_allowed": payload["stage_b_return_ablation_allowed"],
                "blockers": payload["blockers"],
                "metrics": payload["metrics"],
                "summary_json": str(summary_json_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
