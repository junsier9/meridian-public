from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


CONTRACT_VERSION = "hv_balanced_12factor_counterfactual_path_replay.v1"
DEFAULT_T0_UTC = "2026-05-23T06:26:14.033310Z"
DEFAULT_T0_SOURCE = (
    "docs/live_trading/hv_balanced_binance_usdm_pipeline/"
    "mainnet_multiphase_unattended_live_supervisor_authorization_2026_05_23.md"
)
DEFAULT_P10A_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_12factor_candidate"
    / "p10a_pit_safe_live_feature_builder"
)
DEFAULT_P9R_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_dth60_coinglass_candidate"
    / "phase9r_research_to_live_parity"
)
DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "proof_artifacts"
    / "hv_balanced_12factor_candidate"
    / "counterfactual_path_replay"
)
REPLAY_AVAILABILITY_CONTRACT = "counterfactual_provider_close_plus_lag_assumption"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Proof-only counterfactual path replay for the 12-factor h10d "
            "candidate. It answers whether retained live-built features and "
            "research WFO contracts are sufficient to replay what the candidate "
            "would have held from a live t0, without touching timer, supervisor, "
            "executor, orders, fills, live config, or operator state."
        )
    )
    parser.add_argument("--p10a-summary", type=Path, default=None)
    parser.add_argument("--p9r-summary", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--start-t0-utc", default=DEFAULT_T0_UTC)
    parser.add_argument("--t0-source", default=DEFAULT_T0_SOURCE)
    parser.add_argument("--end-decision-utc", default=None)
    parser.add_argument("--availability-lag-seconds", type=int, default=None)
    parser.add_argument("--strict-wfo-window", action="store_true", default=True)
    parser.add_argument("--no-strict-wfo-window", dest="strict_wfo_window", action="store_false")
    parser.add_argument(
        "--allow-latest-wfo-carry-forward",
        action="store_true",
        help=(
            "Diagnostic only. Uses the latest retained WFO weights per phase "
            "when no exact test window covers a live replay date. This is not "
            "research-baseline exact parity."
        ),
    )
    parser.add_argument("--row-sample-limit", type=int, default=200)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def end_of_day_ms(day: date) -> int:
    stamp = datetime.combine(day, time(23, 59, 59, 999000), tzinfo=UTC)
    return int(stamp.timestamp() * 1000)


def replay_decision_ms_for_provider_date(provider_day: date) -> int:
    decision = datetime.combine(provider_day + timedelta(days=1), time(0, 1), tzinfo=UTC)
    return int(decision.timestamp() * 1000)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]] | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False)
        return
    pd.DataFrame(list(rows)).to_csv(path, index=False)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        as_float = float(value)
        return as_float if math.isfinite(as_float) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        return stamp.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_sha256(payload: Any) -> str:
    material = json.dumps(json_safe(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def resolve_repo_path(path_ref: str | Path | None) -> Path:
    if not path_ref:
        return Path()
    path = Path(path_ref)
    if path.is_absolute():
        return path
    return ROOT / path


def latest_summary(parent: Path) -> Path:
    if not parent.exists():
        raise FileNotFoundError(f"artifact parent does not exist: {parent}")
    candidates = [path / "summary.json" for path in parent.iterdir() if (path / "summary.json").exists()]
    if not candidates:
        raise FileNotFoundError(f"no summary.json found under: {parent}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_p10a_summary(path: Path | None) -> Path:
    return resolve_repo_path(path) if path else latest_summary(DEFAULT_P10A_PARENT)


def resolve_p9r_summary(path: Path | None) -> Path:
    return resolve_repo_path(path) if path else latest_summary(DEFAULT_P9R_PARENT)


def artifact_path(summary: dict[str, Any], *keys: str) -> Path:
    for section_name in ("artifacts", "output_files"):
        section = summary.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in keys:
            value = section.get(key)
            if value:
                return resolve_repo_path(value)
    return Path()


def unwrap_research_scorer_contract(raw: dict[str, Any]) -> dict[str, Any]:
    nested = raw.get("research_scorer_contract") if isinstance(raw, dict) else None
    if isinstance(nested, dict) and nested.get("required_feature_columns"):
        return nested
    if isinstance(raw, dict) and raw.get("required_feature_columns"):
        return raw
    panel = raw.get("panel_contract") if isinstance(raw, dict) else None
    if isinstance(panel, dict) and panel.get("required_feature_columns"):
        output = dict(raw)
        output["required_feature_columns"] = list(panel.get("required_feature_columns") or [])
        output["required_feature_count"] = int(panel.get("required_feature_count") or len(output["required_feature_columns"]))
        return output
    return raw if isinstance(raw, dict) else {}


def run_counterfactual_path_replay(
    args: argparse.Namespace,
    *,
    now_fn: Any | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_repo_path(getattr(args, "output_root", None)) if getattr(args, "output_root", None) else DEFAULT_OUTPUT_PARENT / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    p10a_summary_path = resolve_p10a_summary(getattr(args, "p10a_summary", None))
    p9r_summary_path = resolve_p9r_summary(getattr(args, "p9r_summary", None))
    p10a_summary = load_json(p10a_summary_path)
    p9r_summary = load_json(p9r_summary_path)
    p10a_rows_path = artifact_path(p10a_summary, "pit_live_feature_candidate_rows")
    p9r_weights_path = artifact_path(p9r_summary, "wfo_window_factor_weights")
    p9r_windows_path = artifact_path(p9r_summary, "window_row_parity")
    p9r_contract_path = artifact_path(p9r_summary, "research_scorer_contract")

    raw_scorer_contract = (
        load_json(p9r_contract_path)
        if p9r_contract_path.exists()
        else dict(p9r_summary.get("research_scorer_contract") or {})
    )
    scorer_contract = unwrap_research_scorer_contract(raw_scorer_contract)
    required_factors = [str(item) for item in scorer_contract.get("required_feature_columns") or []]
    constraints = dict(scorer_contract.get("profile_constraints") or {})
    construction = dict(scorer_contract.get("portfolio_construction_baseline") or {})
    top_k = int(constraints.get("top_long_count") or construction.get("per_sleeve_long_short_k") or 3)
    bottom_k = int(constraints.get("bottom_short_count") or construction.get("per_sleeve_long_short_k") or 3)
    long_leverage = float(constraints.get("long_leverage") or 0.5)
    short_leverage = float(constraints.get("short_leverage") or 0.5)
    min_replay_symbol_count = int(top_k + bottom_k)
    sleeve_weight = float(construction.get("sleeve_weight") or 0.1)
    phases = [int(item) for item in construction.get("phase_offsets_days") or list(range(10))]
    rebalance_interval_days = int(construction.get("rebalance_interval_days_per_sleeve") or 10)

    t0 = parse_utc(str(getattr(args, "start_t0_utc", DEFAULT_T0_UTC)))
    end_decision = (
        parse_utc(str(getattr(args, "end_decision_utc")))
        if getattr(args, "end_decision_utc", None)
        else parse_utc(str(p10a_summary.get("decision_time_utc") or iso_z(started_at)))
    )
    availability_lag_seconds = (
        int(getattr(args, "availability_lag_seconds"))
        if getattr(args, "availability_lag_seconds", None) is not None
        else int(p10a_summary.get("availability_lag_seconds") or 60)
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if p10a_summary.get("status") != "ready":
        blockers.append("p10a_summary_not_ready")
    if p9r_summary.get("status") != "ready":
        blockers.append("p9r_summary_not_ready")
    if not p10a_rows_path.exists():
        blockers.append("p10a_candidate_rows_missing")
    if not p9r_weights_path.exists():
        blockers.append("p9r_wfo_window_factor_weights_missing")
    if not p9r_windows_path.exists():
        blockers.append("p9r_window_row_parity_missing")
    if not required_factors:
        blockers.append("research_scorer_contract_missing_required_factors")

    rows = load_candidate_rows(p10a_rows_path) if p10a_rows_path.exists() else pd.DataFrame()
    missing_contract_factors = sorted(set(required_factors) - set(rows["factor_id"].astype(str).unique())) if not rows.empty and required_factors else []
    if missing_contract_factors:
        blockers.append("p10a_rows_missing_contract_factors")

    coverage = build_factor_coverage(rows, required_factors=required_factors)
    coverage_path = output_root / "factor_coverage_by_provider_date.csv"
    write_csv(coverage_path, coverage)

    availability_audit = build_availability_replay_audit(
        rows,
        required_factors=required_factors,
        availability_lag_seconds=availability_lag_seconds,
        sample_limit=int(getattr(args, "row_sample_limit", 200) or 200),
    )
    availability_audit_path = output_root / "availability_replay_audit_sample.csv"
    write_csv(availability_audit_path, availability_audit)

    matrix = build_feature_matrix(rows, required_factors=required_factors)
    complete_dates = complete_provider_dates(
        matrix,
        required_factors=required_factors,
        min_symbol_count=min_replay_symbol_count,
    )
    symbols = sorted(matrix["symbol"].astype(str).unique()) if not matrix.empty else []
    phase_starts = load_phase_start_dates(p9r_windows_path, phases=phases) if p9r_windows_path.exists() else {}
    wfo_windows = load_wfo_windows(p9r_weights_path, p9r_windows_path, required_factors=required_factors) if p9r_weights_path.exists() and p9r_windows_path.exists() else []

    t0_provider_day = t0.date() - timedelta(days=1)
    end_provider_day = end_decision.date() - timedelta(days=1)
    replay_days = list(date_range(t0.date(), end_decision.date()))
    replay_provider_days = [day - timedelta(days=1) for day in replay_days]
    relevant_provider_days = [day for day in replay_provider_days if day <= end_provider_day]
    missing_history = summarize_missing_history(
        coverage,
        required_factors=required_factors,
        min_symbol_count=min_replay_symbol_count,
        start_provider_day=min(relevant_provider_days) if relevant_provider_days else t0_provider_day,
        end_provider_day=end_provider_day,
    )
    complete_dates_on_or_before_t0 = [day for day in complete_dates if day <= t0_provider_day]
    if not complete_dates_on_or_before_t0:
        blockers.append("no_complete_12factor_dates_at_or_before_t0_provider_date")
    for factor, count in missing_history["missing_factor_day_counts"].items():
        if int(count) > 0:
            blockers.append(f"factor_history_missing:{factor}")

    wfo_coverage = audit_wfo_coverage(
        wfo_windows=wfo_windows,
        phases=phases,
        provider_days=relevant_provider_days,
        strict=bool(getattr(args, "strict_wfo_window", True)),
        allow_latest_carry_forward=bool(getattr(args, "allow_latest_wfo_carry_forward", False)),
    )
    wfo_coverage_path = output_root / "wfo_window_coverage.csv"
    write_csv(wfo_coverage_path, wfo_coverage)
    frozen_wfo_contract = build_live_period_frozen_wfo_contract(
        wfo_coverage=wfo_coverage,
        p9r_summary_path=p9r_summary_path,
        p9r_summary_sha256=file_sha256(p9r_summary_path),
        strict_wfo_window=bool(getattr(args, "strict_wfo_window", True)),
        allow_latest_carry_forward=bool(getattr(args, "allow_latest_wfo_carry_forward", False)),
        t0=t0,
        end_decision=end_decision,
    )
    frozen_wfo_contract_path = output_root / "live_period_frozen_wfo_contract.json"
    write_json(frozen_wfo_contract_path, frozen_wfo_contract)
    missing_wfo_rows = wfo_coverage.loc[~wfo_coverage["weight_window_found"].astype(bool)] if not wfo_coverage.empty else pd.DataFrame()
    if not missing_wfo_rows.empty:
        blockers.append("wfo_weight_window_missing_for_live_period")
    if bool(getattr(args, "allow_latest_wfo_carry_forward", False)):
        warnings.append("latest_wfo_carry_forward_enabled_diagnostic_not_research_exact")

    path_rows = pd.DataFrame()
    sleeve_rows = pd.DataFrame()
    delta_rows = pd.DataFrame()
    latest_plan: dict[str, Any] = {}
    path_blockers = sorted(set(blockers))
    if not path_blockers:
        try:
            path_rows, sleeve_rows, delta_rows, latest_plan = build_counterfactual_path(
                matrix=matrix,
                required_factors=required_factors,
                symbols=symbols,
                wfo_windows=wfo_windows,
                phases=phases,
                phase_starts=phase_starts,
                t0=t0,
                end_decision=end_decision,
                top_k=top_k,
                bottom_k=bottom_k,
                long_leverage=long_leverage,
                short_leverage=short_leverage,
                sleeve_weight=sleeve_weight,
                rebalance_interval_days=rebalance_interval_days,
                availability_lag_seconds=availability_lag_seconds,
                allow_latest_carry_forward=bool(getattr(args, "allow_latest_wfo_carry_forward", False)),
                min_replay_symbol_count=min_replay_symbol_count,
            )
        except ReplayBlocked as exc:
            path_blockers.extend(exc.blockers)
            blockers.extend(exc.blockers)

    daily_targets_path = output_root / "daily_counterfactual_target_weights.csv"
    sleeve_trace_path = output_root / "sleeve_selection_trace.csv"
    delta_path = output_root / "daily_counterfactual_rebalance_delta.csv"
    latest_plan_path = output_root / "latest_counterfactual_target_plan.json"
    write_csv(daily_targets_path, path_rows)
    write_csv(sleeve_trace_path, sleeve_rows)
    write_csv(delta_path, delta_rows)
    write_json(latest_plan_path, latest_plan or empty_latest_plan(run_id, blockers=sorted(set(blockers))))

    status = "ready" if not blockers else "blocked"
    summary_path = output_root / "summary.json"
    report_path = output_root / "report.md"
    output_files = {
        "summary": str(summary_path),
        "report": str(report_path),
        "factor_coverage_by_provider_date": str(coverage_path),
        "availability_replay_audit_sample": str(availability_audit_path),
        "wfo_window_coverage": str(wfo_coverage_path),
        "live_period_frozen_wfo_contract": str(frozen_wfo_contract_path),
        "daily_counterfactual_target_weights": str(daily_targets_path),
        "sleeve_selection_trace": str(sleeve_trace_path),
        "daily_counterfactual_rebalance_delta": str(delta_path),
        "latest_counterfactual_target_plan": str(latest_plan_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "counterfactual_path_replay_ready": status == "ready",
        "blockers": sorted(set(blockers)),
        "warnings": warnings,
        "question_answered": status == "ready",
        "answer_scope": (
            "exact_counterfactual_candidate_path_from_t0"
            if status == "ready"
            else "blocked_proof_of_missing_inputs_for_exact_counterfactual_path"
        ),
        "proof_only": True,
        "applied_to_live": False,
        "timer_invoked": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
        "candidate_executed": False,
        "orders_submitted": 0,
        "fills_observed": 0,
        "live_config_changed": False,
        "operator_state_changed": False,
        "target_plan_replaced": False,
        "remote_sync_performed": False,
        "t0_utc": iso_z(t0),
        "t0_source": str(getattr(args, "t0_source", DEFAULT_T0_SOURCE)),
        "t0_provider_date_utc": t0_provider_day.isoformat(),
        "end_decision_utc": iso_z(end_decision),
        "end_provider_date_utc": end_provider_day.isoformat(),
        "availability_contract": REPLAY_AVAILABILITY_CONTRACT,
        "availability_lag_seconds": availability_lag_seconds,
        "recorded_available_at_note": (
            "P10A recorded available_at can be collection-time metadata for retained "
            "historical sidecars; replay no-future checks use provider timestamp plus "
            "the explicit lag contract instead."
        ),
        "p10a_summary": str(p10a_summary_path),
        "p10a_summary_sha256": file_sha256(p10a_summary_path),
        "p9r_summary": str(p9r_summary_path),
        "p9r_summary_sha256": file_sha256(p9r_summary_path),
        "research_scorer_contract": str(p9r_contract_path) if p9r_contract_path.exists() else "embedded_in_p9r_summary",
        "required_feature_count": int(len(required_factors)),
        "required_feature_columns": required_factors,
        "symbol_count": int(len(symbols)),
        "complete_12factor_provider_date_count": int(len(complete_dates)),
        "complete_12factor_provider_date_min": min(complete_dates).isoformat() if complete_dates else None,
        "complete_12factor_provider_date_max": max(complete_dates).isoformat() if complete_dates else None,
        "coverage": {
            "min_replay_symbol_count": int(min_replay_symbol_count),
            "missing_factor_day_counts": missing_history["missing_factor_day_counts"],
            "first_complete_provider_date_on_or_after_t0": first_complete_on_or_after(complete_dates, t0_provider_day),
            "complete_dates_on_or_before_t0_count": int(len(complete_dates_on_or_before_t0)),
        },
        "wfo_contract": {
            "strict_wfo_window": bool(getattr(args, "strict_wfo_window", True)),
            "allow_latest_wfo_carry_forward": bool(getattr(args, "allow_latest_wfo_carry_forward", False)),
            "frozen_contract_status": frozen_wfo_contract.get("status"),
            "frozen_contract_mode": frozen_wfo_contract.get("mode"),
            "wfo_window_count": int(len(wfo_windows)),
            "missing_weight_window_count": int(len(missing_wfo_rows)),
            "latest_test_end_utc": latest_test_end(wfo_windows),
        },
        "construction": {
            "target_engine": "multiphase_equal_sleeve",
            "phase_offsets_days": phases,
            "rebalance_interval_days_per_sleeve": rebalance_interval_days,
            "sleeve_weight": sleeve_weight,
            "top_long_count": top_k,
            "bottom_short_count": bottom_k,
            "long_leverage": long_leverage,
            "short_leverage": short_leverage,
            "aggregate_rule": "sum_equal_weight_sleeve_targets",
        },
        "path_result": {
            "daily_target_row_count": int(len(path_rows)),
            "sleeve_trace_row_count": int(len(sleeve_rows)),
            "rebalance_delta_row_count": int(len(delta_rows)),
            "latest_target_plan_sha256": payload_sha256(latest_plan) if latest_plan else None,
            "latest_target_decision_utc": latest_plan.get("decision_time_utc") if latest_plan else None,
        },
        "output_files": output_files,
    }
    write_json(summary_path, summary)
    report_path.write_text(render_report(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


class ReplayBlocked(RuntimeError):
    def __init__(self, blockers: Iterable[str]) -> None:
        super().__init__(", ".join(sorted(set(blockers))))
        self.blockers = sorted(set(blockers))


def load_candidate_rows(path: Path) -> pd.DataFrame:
    rows = pd.read_csv(path)
    if rows.empty:
        return rows
    rows = rows.copy()
    if "factor_id" not in rows.columns and "factor" in rows.columns:
        rows["factor_id"] = rows["factor"].astype(str)
    if "symbol" not in rows.columns and "usdm_symbol" in rows.columns:
        rows["symbol"] = rows["usdm_symbol"].astype(str)
    rows["factor_id"] = rows["factor_id"].astype(str)
    rows["symbol"] = rows["symbol"].astype(str)
    rows["subject"] = rows.get("subject", rows["symbol"]).astype(str)
    rows["provider_timestamp_ms"] = pd.to_numeric(rows["provider_timestamp_ms"], errors="coerce")
    rows["available_at_ms"] = pd.to_numeric(rows.get("available_at_ms"), errors="coerce")
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.dropna(subset=["provider_timestamp_ms"]).copy()
    rows["provider_timestamp_ms"] = rows["provider_timestamp_ms"].astype("int64")
    rows["provider_timestamp_utc"] = pd.to_datetime(rows["provider_timestamp_ms"], unit="ms", utc=True)
    rows["provider_date"] = rows["provider_timestamp_utc"].dt.date
    return rows


def build_factor_coverage(rows: pd.DataFrame, *, required_factors: list[str]) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "provider_date",
                "symbol_count",
                "required_factor_count",
                "complete_factor_count",
                "all_required_factors_complete",
            ]
        )
    symbols = sorted(rows["symbol"].astype(str).unique())
    counts = (
        rows.loc[rows["factor_id"].isin(required_factors)]
        .assign(has_value=lambda frame: pd.to_numeric(frame["value"], errors="coerce").notna())
        .groupby(["provider_date", "factor_id"])["has_value"]
        .sum()
        .unstack(fill_value=0)
    )
    for factor in required_factors:
        if factor not in counts.columns:
            counts[factor] = 0
    counts = counts[required_factors].sort_index()
    output = counts.reset_index()
    output["provider_date"] = output["provider_date"].astype(str)
    output["symbol_count"] = int(len(symbols))
    output["required_factor_count"] = int(len(required_factors))
    output["complete_factor_count"] = counts.ge(len(symbols)).sum(axis=1).to_numpy(dtype="int64")
    output["all_required_factors_complete"] = output["complete_factor_count"].eq(len(required_factors))
    missing_columns = []
    for factor in required_factors:
        missing_column = f"missing_symbols_{factor}"
        output[missing_column] = (len(symbols) - pd.to_numeric(output[factor], errors="coerce").fillna(0)).clip(lower=0)
        missing_columns.append(missing_column)
    output["missing_factor_ids"] = output.apply(
        lambda row: ",".join(
            factor for factor in required_factors if int(row.get(f"missing_symbols_{factor}", 0) or 0) > 0
        ),
        axis=1,
    )
    ordered_columns = [
        "provider_date",
        "symbol_count",
        "required_factor_count",
        "complete_factor_count",
        "all_required_factors_complete",
        "missing_factor_ids",
        *required_factors,
        *missing_columns,
    ]
    return output[ordered_columns]


def build_availability_replay_audit(
    rows: pd.DataFrame,
    *,
    required_factors: list[str],
    availability_lag_seconds: int,
    sample_limit: int,
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    sample = rows.loc[rows["factor_id"].isin(required_factors)].copy()
    sample["replay_assumed_available_at_ms"] = (
        pd.to_numeric(sample["provider_timestamp_ms"], errors="coerce").astype("int64")
        + int(availability_lag_seconds) * 1000
    )
    sample["replay_assumed_available_at_utc"] = pd.to_datetime(
        sample["replay_assumed_available_at_ms"],
        unit="ms",
        utc=True,
    ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    sample["replay_decision_ms"] = sample["provider_date"].map(replay_decision_ms_for_provider_date).astype("int64")
    sample["replay_decision_utc"] = pd.to_datetime(sample["replay_decision_ms"], unit="ms", utc=True).dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    sample["replay_no_future_fill"] = sample["replay_assumed_available_at_ms"].le(sample["replay_decision_ms"])
    sample["replay_exact_provider_date_fresh"] = True
    sample["availability_contract"] = REPLAY_AVAILABILITY_CONTRACT
    columns = [
        "provider_date",
        "symbol",
        "subject",
        "factor_id",
        "provider_timestamp_utc",
        "available_at_ms",
        "replay_assumed_available_at_utc",
        "replay_decision_utc",
        "replay_no_future_fill",
        "replay_exact_provider_date_fresh",
        "availability_contract",
        "value",
    ]
    return sample.sort_values(["provider_date", "factor_id", "symbol"])[columns].head(int(sample_limit))


def build_feature_matrix(rows: pd.DataFrame, *, required_factors: list[str]) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["provider_date", "symbol", "subject", *required_factors])
    core = rows.loc[rows["factor_id"].isin(required_factors)].copy()
    values = core.pivot_table(
        index=["provider_date", "symbol", "subject"],
        columns="factor_id",
        values="value",
        aggfunc="first",
    ).reset_index()
    for factor in required_factors:
        if factor not in values.columns:
            values[factor] = np.nan
    values["provider_date"] = pd.to_datetime(values["provider_date"].astype(str), utc=True).dt.date
    return values[["provider_date", "symbol", "subject", *required_factors]].sort_values(
        ["provider_date", "symbol"]
    )


def complete_provider_dates(
    matrix: pd.DataFrame,
    *,
    required_factors: list[str],
    min_symbol_count: int,
) -> list[date]:
    if matrix.empty:
        return []
    complete = matrix.dropna(subset=required_factors).groupby("provider_date")["symbol"].nunique()
    return sorted(day for day, count in complete.items() if int(count) >= int(min_symbol_count))


def date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def summarize_missing_history(
    coverage: pd.DataFrame,
    *,
    required_factors: list[str],
    min_symbol_count: int,
    start_provider_day: date,
    end_provider_day: date,
) -> dict[str, Any]:
    if coverage.empty:
        return {"missing_factor_day_counts": {factor: 1 for factor in required_factors}}
    working = coverage.copy()
    working["provider_date_obj"] = pd.to_datetime(working["provider_date"], utc=True).dt.date
    window = working.loc[
        working["provider_date_obj"].ge(start_provider_day) & working["provider_date_obj"].le(end_provider_day)
    ].copy()
    missing: dict[str, int] = {}
    expected_days = list(date_range(start_provider_day, end_provider_day))
    present_days = set(window["provider_date_obj"].tolist())
    missing_whole_days = len(set(expected_days) - present_days)
    for factor in required_factors:
        missing[factor] = int(missing_whole_days)
        if factor in window.columns:
            missing[factor] += int(pd.to_numeric(window[factor], errors="coerce").fillna(0).lt(int(min_symbol_count)).sum())
    return {"missing_factor_day_counts": missing}


def first_complete_on_or_after(complete_dates: list[date], day: date) -> str | None:
    later = [item for item in complete_dates if item >= day]
    return min(later).isoformat() if later else None


def load_phase_start_dates(path: Path, *, phases: list[int]) -> dict[int, date]:
    rows = pd.read_csv(path)
    output: dict[int, date] = {}
    if "phase_start_date_utc" in rows.columns:
        for phase, group in rows.groupby("phase_offset_days"):
            values = pd.to_datetime(group["phase_start_date_utc"], utc=True, errors="coerce").dropna()
            if not values.empty:
                output[int(phase)] = values.min().date()
    for phase in phases:
        output.setdefault(int(phase), date(1970, 1, 1) + timedelta(days=int(phase)))
    return output


def load_wfo_windows(path_weights: Path, path_windows: Path, *, required_factors: list[str]) -> list[dict[str, Any]]:
    weights = pd.read_csv(path_weights)
    windows = pd.read_csv(path_windows)
    if "window_id" not in weights.columns:
        return []
    windows_by_id = {
        str(row["window_id"]): row.to_dict()
        for _, row in windows.iterrows()
        if "window_id" in row and pd.notna(row["window_id"])
    }
    output: list[dict[str, Any]] = []
    for window_id, group in weights.groupby("window_id", sort=False):
        first = group.iloc[0].to_dict()
        meta = dict(windows_by_id.get(str(window_id), {}))
        factor_weights = {
            str(row["factor"]): float(row["weight"])
            for _, row in group.iterrows()
            if str(row.get("factor")) in required_factors and pd.notna(row.get("weight"))
        }
        output.append(
            {
                "window_id": str(window_id),
                "phase_offset_days": int(first.get("phase_offset_days", meta.get("phase_offset_days", 0))),
                "train_end_utc": str(first.get("train_end_utc") or meta.get("train_end_utc") or ""),
                "validation_end_utc": str(first.get("validation_end_utc") or meta.get("validation_end_utc") or ""),
                "test_start_utc": str(meta.get("test_start_utc") or ""),
                "test_end_utc": str(meta.get("test_end_utc") or ""),
                "phase_start_date_utc": str(meta.get("phase_start_date_utc") or ""),
                "weights": factor_weights,
                "abs_weight_sum": float(sum(abs(factor_weights.get(factor, 0.0)) for factor in required_factors)),
                "missing_factors": [factor for factor in required_factors if factor not in factor_weights],
            }
        )
    return output


def select_weight_window(
    *,
    wfo_windows: list[dict[str, Any]],
    phase: int,
    provider_day: date,
    allow_latest_carry_forward: bool,
) -> tuple[dict[str, Any] | None, str]:
    phase_windows = [window for window in wfo_windows if int(window.get("phase_offset_days", -1)) == int(phase)]
    exact: list[dict[str, Any]] = []
    for window in phase_windows:
        start = parse_date_or_none(window.get("test_start_utc"))
        end = parse_date_or_none(window.get("test_end_utc"))
        if start and end and start <= provider_day <= end:
            exact.append(window)
    if exact:
        return exact[-1], "exact_test_window"
    if not allow_latest_carry_forward:
        return None, "missing_exact_test_window"
    candidates = [
        window
        for window in phase_windows
        if parse_date_or_none(window.get("validation_end_utc"))
        and parse_date_or_none(window.get("validation_end_utc")) <= provider_day
    ]
    if not candidates:
        return None, "missing_carry_forward_window"
    candidates.sort(key=lambda item: parse_date_or_none(item.get("validation_end_utc")) or date.min)
    return candidates[-1], "latest_wfo_carry_forward_diagnostic"


def parse_date_or_none(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw or raw.lower() == "nan":
        return None
    try:
        return parse_utc(raw).date() if "T" in raw or raw.endswith("Z") else date.fromisoformat(raw[:10])
    except ValueError:
        return None


def audit_wfo_coverage(
    *,
    wfo_windows: list[dict[str, Any]],
    phases: list[int],
    provider_days: list[date],
    strict: bool,
    allow_latest_carry_forward: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for provider_day in provider_days:
        for phase in phases:
            window, source = select_weight_window(
                wfo_windows=wfo_windows,
                phase=phase,
                provider_day=provider_day,
                allow_latest_carry_forward=allow_latest_carry_forward and not strict,
            )
            rows.append(
                {
                    "provider_date": provider_day.isoformat(),
                    "phase_offset_days": int(phase),
                    "weight_window_found": window is not None,
                    "weight_source_status": source,
                    "window_id": window.get("window_id") if window else None,
                    "test_start_utc": window.get("test_start_utc") if window else None,
                    "test_end_utc": window.get("test_end_utc") if window else None,
                    "validation_end_utc": window.get("validation_end_utc") if window else None,
                    "abs_weight_sum": window.get("abs_weight_sum") if window else None,
                    "missing_factor_count": len(window.get("missing_factors") or []) if window else None,
                }
            )
    return pd.DataFrame(rows)


def build_live_period_frozen_wfo_contract(
    *,
    wfo_coverage: pd.DataFrame,
    p9r_summary_path: Path,
    p9r_summary_sha256: str,
    strict_wfo_window: bool,
    allow_latest_carry_forward: bool,
    t0: datetime,
    end_decision: datetime,
) -> dict[str, Any]:
    enabled = (not bool(strict_wfo_window)) and bool(allow_latest_carry_forward)
    rows = []
    if enabled and not wfo_coverage.empty:
        for _, row in wfo_coverage.iterrows():
            rows.append(
                {
                    "provider_date": str(row.get("provider_date")),
                    "phase_offset_days": int(row.get("phase_offset_days")),
                    "window_id": None if pd.isna(row.get("window_id")) else str(row.get("window_id")),
                    "weight_source_status": str(row.get("weight_source_status")),
                    "validation_end_utc": None
                    if pd.isna(row.get("validation_end_utc"))
                    else str(row.get("validation_end_utc")),
                    "test_start_utc": None if pd.isna(row.get("test_start_utc")) else str(row.get("test_start_utc")),
                    "test_end_utc": None if pd.isna(row.get("test_end_utc")) else str(row.get("test_end_utc")),
                }
            )
    missing = int((~wfo_coverage["weight_window_found"].astype(bool)).sum()) if not wfo_coverage.empty else 0
    status = "ready" if enabled and missing == 0 else ("not_enabled" if not enabled else "blocked")
    return {
        "contract_version": "hv_balanced_12factor_live_period_frozen_wfo_contract.v1",
        "status": status,
        "mode": "latest_wfo_carry_forward_frozen_live_period" if enabled else "strict_p9r_test_window_required",
        "enabled": enabled,
        "scope": "proof_artifacts_counterfactual_replay_only",
        "research_exact_parity": False if enabled else None,
        "rule": (
            "For each provider_date and phase, use the latest retained P9R WFO "
            "window with validation_end_utc <= provider_date when no exact P9R "
            "test window covers the live period."
            if enabled
            else "Require exact retained P9R test window coverage for every live provider_date and phase."
        ),
        "p9r_summary": str(p9r_summary_path),
        "p9r_summary_sha256": p9r_summary_sha256,
        "t0_utc": iso_z(t0),
        "end_decision_utc": iso_z(end_decision),
        "row_count": int(len(rows)),
        "missing_weight_window_count": missing,
        "rows": rows,
        "non_authorization": {
            "timer_invoked": False,
            "supervisor_invoked": False,
            "executor_invoked": False,
            "candidate_executed": False,
            "live_config_changed": False,
            "orders_submitted": 0,
            "fills_observed": 0,
        },
    }


def latest_test_end(wfo_windows: list[dict[str, Any]]) -> str | None:
    ends = [parse_date_or_none(window.get("test_end_utc")) for window in wfo_windows]
    ends = [item for item in ends if item is not None]
    return max(ends).isoformat() if ends else None


def is_phase_rebalance_day(provider_day: date, *, phase_start: date, interval_days: int) -> bool:
    delta = (provider_day - phase_start).days
    return delta >= 0 and delta % int(interval_days) == 0


def latest_phase_rebalance_day(
    *,
    complete_dates: set[date],
    provider_upper_day: date,
    phase_start: date,
    interval_days: int,
) -> date | None:
    eligible = [
        day
        for day in complete_dates
        if day <= provider_upper_day
        and is_phase_rebalance_day(day, phase_start=phase_start, interval_days=interval_days)
    ]
    return max(eligible) if eligible else None


def build_counterfactual_path(
    *,
    matrix: pd.DataFrame,
    required_factors: list[str],
    symbols: list[str],
    wfo_windows: list[dict[str, Any]],
    phases: list[int],
    phase_starts: dict[int, date],
    t0: datetime,
    end_decision: datetime,
    top_k: int,
    bottom_k: int,
    long_leverage: float,
    short_leverage: float,
    sleeve_weight: float,
    rebalance_interval_days: int,
    availability_lag_seconds: int,
    allow_latest_carry_forward: bool,
    min_replay_symbol_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    blockers: list[str] = []
    complete_dates = set(
        complete_provider_dates(
            matrix,
            required_factors=required_factors,
            min_symbol_count=min_replay_symbol_count,
        )
    )
    path_rows: list[dict[str, Any]] = []
    sleeve_rows: list[dict[str, Any]] = []
    delta_rows: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}

    for decision_day in date_range(t0.date(), end_decision.date()):
        provider_upper_day = decision_day - timedelta(days=1)
        aggregate = {symbol: 0.0 for symbol in symbols}
        phase_records: list[dict[str, Any]] = []
        for phase in phases:
            phase_start = phase_starts.get(int(phase), date(1970, 1, 1) + timedelta(days=int(phase)))
            rebalance_day = latest_phase_rebalance_day(
                complete_dates=complete_dates,
                provider_upper_day=provider_upper_day,
                phase_start=phase_start,
                interval_days=rebalance_interval_days,
            )
            if rebalance_day is None:
                blockers.append(f"phase_missing_complete_rebalance_history:phase={phase}:asof={provider_upper_day}")
                continue
            window, source = select_weight_window(
                wfo_windows=wfo_windows,
                phase=phase,
                provider_day=rebalance_day,
                allow_latest_carry_forward=allow_latest_carry_forward,
            )
            if window is None:
                blockers.append(f"phase_missing_wfo_weights:phase={phase}:provider_date={rebalance_day}")
                continue
            sleeve = score_and_select_sleeve(
                matrix=matrix,
                provider_day=rebalance_day,
                required_factors=required_factors,
                weights=dict(window["weights"]),
                top_k=top_k,
                bottom_k=bottom_k,
                long_leverage=long_leverage,
                short_leverage=short_leverage,
                sleeve_weight=sleeve_weight,
                min_replay_symbol_count=min_replay_symbol_count,
            )
            for record in sleeve:
                aggregate[str(record["symbol"])] = aggregate.get(str(record["symbol"]), 0.0) + float(
                    record["sleeve_target_weight"]
                )
                sleeve_rows.append(
                    {
                        "decision_date_utc": decision_day.isoformat(),
                        "decision_time_utc": datetime.combine(decision_day, time(0, 1), tzinfo=UTC)
                        .isoformat(timespec="seconds")
                        .replace("+00:00", "Z"),
                        "phase_offset_days": int(phase),
                        "phase_rebalance_provider_date": rebalance_day.isoformat(),
                        "phase_start_date_utc": phase_start.isoformat(),
                        "weight_source_status": source,
                        "window_id": window.get("window_id"),
                        "symbol": record["symbol"],
                        "subject": record["subject"],
                        "score": record["score"],
                        "rank_desc": record["rank_desc"],
                        "raw_sleeve_weight": record["raw_sleeve_weight"],
                        "sleeve_target_weight": record["sleeve_target_weight"],
                    }
                )
            phase_records.append({"phase": int(phase), "provider_date": rebalance_day.isoformat()})
        if blockers:
            continue
        gross = float(sum(abs(value) for value in aggregate.values()))
        net = float(sum(aggregate.values()))
        for symbol in symbols:
            weight = float(aggregate.get(symbol, 0.0))
            path_rows.append(
                {
                    "decision_date_utc": decision_day.isoformat(),
                    "decision_time_utc": datetime.combine(decision_day, time(0, 1), tzinfo=UTC)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z"),
                    "as_of_provider_date_utc": provider_upper_day.isoformat(),
                    "symbol": symbol,
                    "target_weight": weight,
                    "target_gross_weight": gross,
                    "target_net_weight": net,
                    "active_sleeve_count": len(phase_records),
                    "availability_contract": REPLAY_AVAILABILITY_CONTRACT,
                    "availability_lag_seconds": int(availability_lag_seconds),
                }
            )
            delta_rows.append(
                {
                    "decision_date_utc": decision_day.isoformat(),
                    "symbol": symbol,
                    "previous_target_weight": float(previous_weights.get(symbol, 0.0)),
                    "new_target_weight": weight,
                    "delta_weight": weight - float(previous_weights.get(symbol, 0.0)),
                }
            )
        previous_weights = aggregate

    if blockers:
        raise ReplayBlocked(blockers)

    path_df = pd.DataFrame(path_rows)
    sleeve_df = pd.DataFrame(sleeve_rows)
    delta_df = pd.DataFrame(delta_rows)
    latest_day = max(path_df["decision_date_utc"]) if not path_df.empty else None
    latest_positions = []
    if latest_day:
        latest = path_df.loc[path_df["decision_date_utc"].eq(latest_day)].sort_values("symbol")
        latest_positions = [
            {
                "symbol": str(row["symbol"]),
                "target_weight": float(row["target_weight"]),
            }
            for _, row in latest.iterrows()
        ]
    latest_plan = {
        "contract_version": "hv_balanced_12factor_counterfactual_latest_target_plan.v1",
        "decision_date_utc": latest_day,
        "decision_time_utc": (
            datetime.combine(date.fromisoformat(str(latest_day)), time(0, 1), tzinfo=UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
            if latest_day
            else None
        ),
        "target_engine": "multiphase_equal_sleeve",
        "positions": latest_positions,
        "target_gross_weight": float(sum(abs(item["target_weight"]) for item in latest_positions)),
        "target_net_weight": float(sum(item["target_weight"] for item in latest_positions)),
        "orders_submitted": 0,
        "fills_observed": 0,
        "applied_to_live": False,
    }
    return path_df, sleeve_df, delta_df, latest_plan


def score_and_select_sleeve(
    *,
    matrix: pd.DataFrame,
    provider_day: date,
    required_factors: list[str],
    weights: dict[str, float],
    top_k: int,
    bottom_k: int,
    long_leverage: float,
    short_leverage: float,
    sleeve_weight: float,
    min_replay_symbol_count: int,
) -> list[dict[str, Any]]:
    day_frame = matrix.loc[matrix["provider_date"].eq(provider_day)].dropna(subset=required_factors).copy()
    if day_frame.empty:
        raise ReplayBlocked([f"missing_feature_matrix_for_provider_date:{provider_day.isoformat()}"])
    if len(day_frame) < int(min_replay_symbol_count):
        raise ReplayBlocked(
            [
                "insufficient_eligible_symbols_for_provider_date:"
                f"{provider_day.isoformat()}:eligible={len(day_frame)}:required={int(min_replay_symbol_count)}"
            ]
        )
    raw = pd.Series(0.0, index=day_frame.index, dtype="float64")
    for factor in required_factors:
        values = pd.to_numeric(day_frame[factor], errors="coerce")
        std = float(values.std(ddof=0))
        if not math.isfinite(std) or std == 0.0:
            zscore = pd.Series(0.0, index=day_frame.index, dtype="float64")
        else:
            zscore = (values - float(values.mean())) / std
        raw = raw + zscore * float(weights.get(factor, 0.0))
    rank_pct = raw.rank(method="average", pct=True)
    score = np.tanh((rank_pct - 0.5) * 1.80)
    day_frame["score"] = score.astype("float64")
    day_frame["rank_desc"] = day_frame["score"].rank(method="first", ascending=False).astype("int64")
    day_frame = day_frame.sort_values(["score", "symbol"], ascending=[False, True]).reset_index(drop=True)
    records: list[dict[str, Any]] = []
    long_symbols = set(day_frame.head(int(top_k))["symbol"].astype(str).tolist())
    short_symbols = set(day_frame.tail(int(bottom_k))["symbol"].astype(str).tolist())
    for _, row in day_frame.iterrows():
        symbol = str(row["symbol"])
        raw_weight = 0.0
        if symbol in long_symbols:
            raw_weight = float(long_leverage) / float(top_k)
        elif symbol in short_symbols:
            raw_weight = -float(short_leverage) / float(bottom_k)
        records.append(
            {
                "symbol": symbol,
                "subject": str(row.get("subject") or symbol),
                "score": float(row["score"]),
                "rank_desc": int(row["rank_desc"]),
                "raw_sleeve_weight": raw_weight,
                "sleeve_target_weight": raw_weight * float(sleeve_weight),
            }
        )
    return records


def empty_latest_plan(run_id: str, *, blockers: list[str]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_counterfactual_latest_target_plan.v1",
        "run_id": run_id,
        "status": "blocked",
        "blockers": sorted(set(blockers)),
        "positions": [],
        "orders_submitted": 0,
        "fills_observed": 0,
        "applied_to_live": False,
    }


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# 12-Factor Counterfactual Path Replay",
        "",
        f"- status: `{summary['status']}`",
        f"- t0_utc: `{summary['t0_utc']}`",
        f"- end_decision_utc: `{summary['end_decision_utc']}`",
        f"- proof_only: `{summary['proof_only']}`",
        f"- orders_submitted: `{summary['orders_submitted']}`",
        f"- fills_observed: `{summary['fills_observed']}`",
        f"- complete_12factor_provider_date_count: `{summary['complete_12factor_provider_date_count']}`",
        f"- complete_12factor_provider_date_min: `{summary['complete_12factor_provider_date_min']}`",
        f"- complete_12factor_provider_date_max: `{summary['complete_12factor_provider_date_max']}`",
        f"- wfo_latest_test_end_utc: `{summary['wfo_contract']['latest_test_end_utc']}`",
        f"- missing_weight_window_count: `{summary['wfo_contract']['missing_weight_window_count']}`",
        "",
        "## Blockers",
        "",
    ]
    if summary.get("blockers"):
        lines.extend(f"- `{item}`" for item in summary["blockers"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
        ]
    )
    lines.extend(f"- {key}: `{value}`" for key, value in summary.get("output_files", {}).items())
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_counterfactual_path_replay(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
