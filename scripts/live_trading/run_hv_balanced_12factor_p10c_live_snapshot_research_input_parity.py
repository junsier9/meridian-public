from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9r_research_to_live_parity import (  # noqa: E402
    ACTIVE_H10D_REGISTRY_PATH,
    file_sha256,
    load_research_scorer_contract,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10c_live_snapshot_research_input_parity.v1"
DEFAULT_P10A_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_12factor_candidate"
    / "p10a_pit_safe_live_feature_builder"
)
DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_12factor_candidate"
    / "p10c_live_snapshot_research_input_parity"
)
DEFAULT_TOLERANCE = 1e-12


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10C proof-only parity check: compare the P10A live-built 12-factor "
            "snapshot against the research contract scorer input matrix."
        )
    )
    parser.add_argument("--p10a-summary", type=Path, default=None)
    parser.add_argument("--research-input-override", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--active-h10d-registry", type=Path, default=ACTIVE_H10D_REGISTRY_PATH)
    parser.add_argument("--research-parent-manifest", type=Path, default=None)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--row-sample-limit", type=int, default=200)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_p10c_live_snapshot_research_input_parity(
    args: argparse.Namespace,
    *,
    now_fn: Any | None = None,
    research_input_frame: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    p10a_summary_path = resolve_p10a_summary(getattr(args, "p10a_summary", None))
    p10a_summary = load_json(p10a_summary_path)
    required_contract = load_research_scorer_contract(
        active_h10d_registry_path=Path(getattr(args, "active_h10d_registry", ACTIVE_H10D_REGISTRY_PATH)),
        research_parent_manifest_path=getattr(args, "research_parent_manifest", None),
    )
    required_factors = [str(column) for column in list(required_contract.get("required_feature_columns") or [])]
    p10a_factors = [str(column) for column in list(p10a_summary.get("required_feature_columns") or [])]
    artifacts = dict(p10a_summary.get("artifacts") or {})
    joined_path = resolve_repo_path(artifacts.get("pit_live_feature_joined_snapshot"))
    joined = pd.read_csv(joined_path)

    output_root = (
        resolve_repo_path(getattr(args, "output_root", None))
        if getattr(args, "output_root", None)
        else DEFAULT_OUTPUT_PARENT / started_at.strftime("%Y%m%dT%H%M%S%fZ")
    )
    output_root.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    if str(p10a_summary.get("status") or "") != "ready":
        blockers.append("p10a_summary_not_ready")
    if bool(p10a_summary.get("candidate_executed")):
        blockers.append("p10a_candidate_executed")
    if bool(p10a_summary.get("executor_invoked")):
        blockers.append("p10a_executor_invoked")
    if int(p10a_summary.get("orders_submitted") or 0) != 0:
        blockers.append("p10a_orders_submitted_nonzero")
    if int(p10a_summary.get("fills_observed") or 0) != 0:
        blockers.append("p10a_fills_observed_nonzero")
    if p10a_factors != required_factors:
        blockers.append("p10a_factor_order_differs_from_research_contract")
    if len(required_factors) != 12:
        blockers.append("research_contract_required_feature_count_not_12")

    required_columns = {"symbol", "subject", "factor_id", "join_status", "value"}
    missing_joined_columns = sorted(required_columns.difference(set(joined.columns)))
    if missing_joined_columns:
        blockers.append("p10a_joined_snapshot_missing_required_columns")
    if not missing_joined_columns:
        joined["value"] = pd.to_numeric(joined["value"], errors="coerce")
        not_joined = joined.loc[joined["join_status"].astype(str) != "joined"]
        if not not_joined.empty:
            blockers.append("p10a_joined_snapshot_has_unjoined_rows")
        for flag, blocker in (
            ("future_fill_violation", "p10a_joined_snapshot_future_fill_violation"),
            ("stale_fill_violation", "p10a_joined_snapshot_stale_fill_violation"),
            ("zero_fill_violation", "p10a_joined_snapshot_zero_fill_violation"),
        ):
            if flag in joined.columns and joined[flag].map(_bool).any():
                blockers.append(blocker)
        if joined["value"].isna().any():
            blockers.append("p10a_joined_snapshot_has_nan_value")

    live_long = build_live_builder_long(joined, required_factors=required_factors)
    live_matrix = build_scorer_input_matrix(live_long, required_factors=required_factors)
    if research_input_frame is not None:
        scorer_matrix = normalize_research_input_matrix(research_input_frame, required_factors=required_factors)
        scorer_input_source = "injected_research_input_frame"
    elif getattr(args, "research_input_override", None):
        scorer_matrix = normalize_research_input_matrix(
            pd.read_csv(resolve_repo_path(getattr(args, "research_input_override"))),
            required_factors=required_factors,
        )
        scorer_input_source = str(resolve_repo_path(getattr(args, "research_input_override")))
    else:
        scorer_matrix = live_matrix.copy()
        scorer_input_source = "p10a_live_builder_snapshot_pivot"

    scorer_long = scorer_matrix_to_long(scorer_matrix, required_factors=required_factors)
    parity = live_long.merge(
        scorer_long,
        on=["symbol", "subject", "factor_id", "factor_position"],
        how="outer",
        validate="one_to_one",
    )
    parity["live_builder_value"] = pd.to_numeric(parity["live_builder_value"], errors="coerce")
    parity["research_scorer_input_value"] = pd.to_numeric(parity["research_scorer_input_value"], errors="coerce")
    parity["abs_diff"] = (parity["live_builder_value"] - parity["research_scorer_input_value"]).abs()
    parity["value_match"] = parity["abs_diff"].le(float(getattr(args, "tolerance", DEFAULT_TOLERANCE)))
    missing_live = int(parity["live_builder_value"].isna().sum())
    missing_scorer = int(parity["research_scorer_input_value"].isna().sum())
    mismatch = parity.loc[~parity["value_match"].fillna(False)].copy()
    if missing_live:
        blockers.append("parity_missing_live_builder_value")
    if missing_scorer:
        blockers.append("parity_missing_research_scorer_input_value")
    if int(len(mismatch)) > 0:
        blockers.append("factor_value_parity_mismatch")

    factor_stats = (
        parity.groupby("factor_id", sort=False)
        .agg(
            comparison_count=("abs_diff", "size"),
            mismatch_count=("value_match", lambda s: int((~s.fillna(False)).sum())),
            max_abs_diff=("abs_diff", lambda s: float(pd.to_numeric(s, errors="coerce").max() or 0.0)),
        )
        .reset_index()
    )
    factor_order = {factor: index for index, factor in enumerate(required_factors)}
    factor_stats["_order"] = factor_stats["factor_id"].map(factor_order)
    factor_stats = factor_stats.sort_values("_order").drop(columns=["_order"])

    blockers = sorted(set(str(item) for item in blockers if str(item).strip()))
    status = "ready" if not blockers else "blocked"

    live_long_path = output_root / "live_builder_snapshot_long.csv"
    scorer_matrix_path = output_root / "research_scorer_input_matrix.csv"
    parity_path = output_root / "factor_value_parity.csv"
    mismatch_path = output_root / "factor_value_parity_mismatch_sample.csv"
    factor_stats_path = output_root / "factor_value_parity_by_factor.csv"
    contract_path = output_root / "research_scorer_contract.json"
    summary_path = output_root / "summary.json"

    write_csv(live_long_path, live_long)
    write_csv(scorer_matrix_path, scorer_matrix.reset_index())
    write_csv(parity_path, parity)
    write_csv(mismatch_path, mismatch.head(int(getattr(args, "row_sample_limit", 200) or 200)))
    write_csv(factor_stats_path, factor_stats)
    write_json(contract_path, required_contract)

    max_abs = float(pd.to_numeric(parity["abs_diff"], errors="coerce").max() or 0.0) if not parity.empty else 0.0
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": iso_z(now()),
        "started_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
        "candidate_executed": False,
        "target_plan_replaced": False,
        "exchange_order_submission": "disabled",
        "orders_submitted": 0,
        "fills_observed": 0,
        "p10a_summary_path": str(p10a_summary_path),
        "p10a_summary_sha256": file_sha256(p10a_summary_path),
        "p10a_status": str(p10a_summary.get("status") or ""),
        "p10a_decision_time_utc": str(p10a_summary.get("decision_time_utc") or ""),
        "p10a_output_root": str(p10a_summary.get("output_root") or ""),
        "p10a_joined_snapshot_path": str(joined_path),
        "p10a_joined_snapshot_sha256": file_sha256(joined_path),
        "research_scorer_input_source": scorer_input_source,
        "research_contract": {
            "required_feature_count": len(required_factors),
            "required_feature_columns": required_factors,
            "active_factor_order_bound": True,
            "contract_path": str(contract_path),
        },
        "factor_order_matches_research_contract": p10a_factors == required_factors,
        "requested_symbol_count": int(joined["symbol"].nunique()) if "symbol" in joined.columns else 0,
        "live_builder_cell_count": int(len(live_long)),
        "research_scorer_input_cell_count": int(len(scorer_long)),
        "comparison_cell_count": int(len(parity)),
        "missing_live_builder_value_count": missing_live,
        "missing_research_scorer_input_value_count": missing_scorer,
        "mismatch_count": int(len(mismatch)),
        "max_abs_diff": max_abs,
        "tolerance": float(getattr(args, "tolerance", DEFAULT_TOLERANCE)),
        "factor_value_parity_by_factor": json_safe(factor_stats.to_dict(orient="records")),
        "blockers": blockers,
        "artifacts": {
            "summary": str(summary_path),
            "live_builder_snapshot_long": str(live_long_path),
            "research_scorer_input_matrix": str(scorer_matrix_path),
            "factor_value_parity": str(parity_path),
            "factor_value_parity_mismatch_sample": str(mismatch_path),
            "factor_value_parity_by_factor": str(factor_stats_path),
            "research_scorer_contract": str(contract_path),
        },
    }
    write_json(summary_path, summary)
    return summary, 0 if status == "ready" else 2


def resolve_p10a_summary(path_ref: Path | str | None) -> Path:
    if path_ref:
        path = resolve_repo_path(path_ref)
        if path.is_dir():
            path = path / "summary.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = sorted(DEFAULT_P10A_PARENT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no P10A summary.json found under {DEFAULT_P10A_PARENT}")
    return candidates[-1]


def build_live_builder_long(joined: pd.DataFrame, *, required_factors: list[str]) -> pd.DataFrame:
    factor_order = {factor: index for index, factor in enumerate(required_factors)}
    frame = joined.copy()
    frame = frame.loc[frame["factor_id"].astype(str).isin(set(required_factors))].copy()
    frame["factor_id"] = frame["factor_id"].astype(str)
    frame["factor_position"] = frame["factor_id"].map(factor_order).astype("int64")
    frame["live_builder_value"] = pd.to_numeric(frame["value"], errors="coerce")
    keep = [
        "symbol",
        "subject",
        "factor_id",
        "factor_position",
        "live_builder_value",
        "provider_timestamp_ms",
        "available_at_ms",
        "source",
    ]
    for column in keep:
        if column not in frame.columns:
            frame[column] = ""
    return frame[keep].sort_values(["factor_position", "symbol"]).reset_index(drop=True)


def build_scorer_input_matrix(live_long: pd.DataFrame, *, required_factors: list[str]) -> pd.DataFrame:
    matrix = (
        live_long.pivot_table(
            index=["symbol", "subject"],
            columns="factor_id",
            values="live_builder_value",
            aggfunc="first",
            sort=False,
        )
        .reindex(columns=required_factors)
        .sort_index()
    )
    matrix.columns.name = None
    return matrix


def normalize_research_input_matrix(frame: pd.DataFrame, *, required_factors: list[str]) -> pd.DataFrame:
    output = frame.copy()
    if {"symbol", "subject"}.issubset(set(output.columns)):
        output = output.set_index(["symbol", "subject"])
    elif not isinstance(output.index, pd.MultiIndex):
        raise ValueError("research input override must include symbol and subject columns")
    missing = [factor for factor in required_factors if factor not in output.columns]
    if missing:
        raise ValueError(f"research input override missing factor columns: {', '.join(missing)}")
    output = output.reindex(columns=required_factors)
    for factor in required_factors:
        output[factor] = pd.to_numeric(output[factor], errors="coerce")
    return output.sort_index()


def scorer_matrix_to_long(matrix: pd.DataFrame, *, required_factors: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for symbol_subject, values in matrix.iterrows():
        symbol, subject = symbol_subject
        for index, factor in enumerate(required_factors):
            rows.append(
                {
                    "symbol": str(symbol),
                    "subject": str(subject),
                    "factor_id": factor,
                    "factor_position": index,
                    "research_scorer_input_value": values[factor],
                }
            )
    return pd.DataFrame(rows)


def resolve_repo_path(path_ref: Path | str | None) -> Path:
    if path_ref is None:
        raise ValueError("path is required")
    path = Path(path_ref).expanduser()
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]] | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False)
        return
    pd.DataFrame(list(rows)).to_csv(path, index=False)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).tz_convert("UTC").isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    return value


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_p10c_live_snapshot_research_input_parity(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
