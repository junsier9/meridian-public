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

from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_m3_3_event_tape_spk_stage0 as event_stage0,
    evaluate_m3_3_strict_event_state_stage0 as strict_stage0,
)
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "m3_3_mf01_confirmation_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"


@dataclass(frozen=True)
class ConfirmationSpec:
    label: str
    min_quality: float = 2.0
    max_replacements: int = 1
    confirmation_mode: str = "none"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="M3.3 event-state plus MF-01 orderbook confirmation Stage 0 diagnostics."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=event_stage0.DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _specs() -> list[ConfirmationSpec]:
    return [
        ConfirmationSpec(label="q2_event_only_max3", max_replacements=3, confirmation_mode="none"),
        ConfirmationSpec(label="q2_event_only_one", max_replacements=1, confirmation_mode="none"),
        ConfirmationSpec(label="q2_mf01_any_flag_one", max_replacements=1, confirmation_mode="mf01_any_flag"),
        ConfirmationSpec(label="q2_mf01_boundary_flag_one", max_replacements=1, confirmation_mode="mf01_boundary_flag"),
        ConfirmationSpec(label="q2_mf01_combo_negative_one", max_replacements=1, confirmation_mode="mf01_combo_negative"),
    ]


def _bool_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[column].fillna(False).astype(bool)


def _eligible_mask(frame: pd.DataFrame, spec: ConfirmationSpec) -> pd.Series:
    event_mask = strict_stage0._eligible_mask(
        frame,
        min_quality=float(spec.min_quality),
        max_noise_ratio=0.0,
        require_no_hype=True,
    )
    mode = str(spec.confirmation_mode)
    if mode == "none":
        return event_mask
    boundary = _bool_column(frame, "boundary_fragile_orderbook_flag")
    pump_fail = _bool_column(frame, "pump_bid_replenishment_failure_flag")
    combo_negative = pd.to_numeric(
        frame.get("mf01_short_boundary_combo_score", pd.Series(0.0, index=frame.index)),
        errors="coerce",
    ).fillna(0.0).lt(0.0)
    if mode == "mf01_any_flag":
        return event_mask & (boundary | pump_fail | combo_negative)
    if mode == "mf01_boundary_flag":
        return event_mask & boundary
    if mode == "mf01_combo_negative":
        return event_mask & combo_negative
    raise ValueError(f"unknown confirmation mode: {mode}")


def _select_rows(
    frame: pd.DataFrame,
    *,
    spec: ConfirmationSpec,
    target_horizon_bars: int,
    pool_size: int = 8,
    short_count: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    work = frame.copy()
    if "parent_score" not in work.columns:
        work["parent_score"] = xs_alpha_ontology_v5_score(work)
    work["event_eligible"] = strict_stage0._eligible_mask(
        work,
        min_quality=float(spec.min_quality),
        max_noise_ratio=0.0,
        require_no_hype=True,
    )
    work["confirmed_eligible"] = _eligible_mask(work, spec)
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "parent_score",
        "event_eligible",
        "confirmed_eligible",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
        "m3_3_event_state_hype_pressure_v1",
        "boundary_fragile_orderbook_flag",
        "pump_bid_replenishment_failure_flag",
        "boundary_fragile_orderbook_score",
        "pump_bid_replenishment_failure_score",
        "mf01_short_boundary_combo_score",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = [column for column in keep if column in work.columns]
    parent_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    total = 0
    event_timestamps = 0
    confirmed_timestamps = 0
    changed = 0
    for _, group in work.groupby("timestamp_ms", sort=False):
        total += 1
        ordered = group.sort_values("parent_score", ascending=False).copy()
        if len(ordered) <= short_count:
            continue
        parent_shorts = ordered.tail(short_count).copy()
        tail_pool = ordered.tail(min(pool_size, len(ordered))).copy()
        event_pool = tail_pool.loc[tail_pool["event_eligible"]].copy()
        confirmed_pool = tail_pool.loc[tail_pool["confirmed_eligible"]].copy()
        if not event_pool.empty:
            event_timestamps += 1
        if not confirmed_pool.empty:
            confirmed_timestamps += 1
        selected = parent_shorts.copy()
        if not confirmed_pool.empty and int(spec.max_replacements) > 0:
            parent_subjects = set(parent_shorts["subject"].astype(str))
            entrants = confirmed_pool.loc[
                ~confirmed_pool["subject"].astype(str).isin(parent_subjects)
            ].sort_values(
                ["m3_3_event_state_short_quality_v1", "mf01_short_boundary_combo_score", "parent_score"],
                ascending=[False, True, True],
            ).head(int(spec.max_replacements))
            if not entrants.empty:
                keep_parent = parent_shorts.sort_values("parent_score", ascending=True).head(
                    max(short_count - len(entrants), 0)
                )
                selected = pd.concat([entrants, keep_parent], axis=0).head(short_count)
        parent_subjects = set(parent_shorts["subject"].astype(str))
        selected_subjects = set(selected["subject"].astype(str))
        if parent_subjects != selected_subjects:
            changed += 1
        parent_rows.extend(parent_shorts[keep].to_dict("records"))
        selected_rows.extend(selected[keep].to_dict("records"))
        entered_rows.extend(selected.loc[~selected["subject"].astype(str).isin(parent_subjects), keep].to_dict("records"))
        exited_rows.extend(parent_shorts.loc[~parent_shorts["subject"].astype(str).isin(selected_subjects), keep].to_dict("records"))
    meta = {
        "timestamp_count": int(total),
        "event_eligible_timestamp_count": int(event_timestamps),
        "confirmed_eligible_timestamp_count": int(confirmed_timestamps),
        "changed_timestamp_count": int(changed),
        "event_eligible_timestamp_fraction": float(event_timestamps / max(total, 1)),
        "confirmed_eligible_timestamp_fraction": float(confirmed_timestamps / max(total, 1)),
        "changed_timestamp_fraction": float(changed / max(total, 1)),
    }
    return (
        pd.DataFrame(parent_rows),
        pd.DataFrame(selected_rows),
        pd.DataFrame(entered_rows),
        pd.DataFrame(exited_rows),
        meta,
    )


def _bucket_summary(rows: pd.DataFrame, *, target_horizon_bars: int, column: str) -> list[dict[str, Any]]:
    if rows.empty or column not in rows.columns:
        return []
    hcol = f"forward_{target_horizon_bars}d_log_return"
    out: list[dict[str, Any]] = []
    for value, group in rows.groupby(column, dropna=False):
        returns = pd.to_numeric(group[hcol], errors="coerce").dropna()
        out.append(
            {
                column: str(value),
                "row_count": int(len(group)),
                "subject_count": int(group["subject"].astype(str).nunique()) if "subject" in group.columns else None,
                f"next_{target_horizon_bars}d_mean": float(returns.mean()) if len(returns) else None,
                f"next_{target_horizon_bars}d_negative_fraction": float((returns < 0.0).mean()) if len(returns) else None,
            }
        )
    return sorted(out, key=lambda item: str(item[column]))


def _summarize(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    summary = strict_stage0._summarize(rows, target_horizon_bars=target_horizon_bars)
    if rows.empty:
        return summary
    for column in (
        "event_eligible",
        "confirmed_eligible",
        "boundary_fragile_orderbook_flag",
        "pump_bid_replenishment_failure_flag",
    ):
        if column in rows.columns:
            summary[f"{column}_fraction"] = float(rows[column].fillna(False).astype(bool).mean())
    if "mf01_short_boundary_combo_score" in rows.columns:
        combo = pd.to_numeric(rows["mf01_short_boundary_combo_score"], errors="coerce").fillna(0.0)
        summary["mf01_combo_negative_fraction"] = float((combo < 0.0).mean())
        summary["mean_mf01_combo_score"] = float(combo.mean())
    summary["by_liquidity_bucket"] = _bucket_summary(
        rows,
        target_horizon_bars=target_horizon_bars,
        column="liquidity_bucket",
    )
    summary["by_subject"] = _bucket_summary(
        rows,
        target_horizon_bars=target_horizon_bars,
        column="subject",
    )
    return summary


def _edge_vs_parent(
    *,
    selected_summary: dict[str, Any],
    parent_summary: dict[str, Any],
    target_horizon_bars: int,
) -> float | None:
    field = f"next_{target_horizon_bars}d_mean"
    if selected_summary.get(field) is None or parent_summary.get(field) is None:
        return None
    return float(parent_summary[field]) - float(selected_summary[field])


def _evaluate(frame: pd.DataFrame, *, spec: ConfirmationSpec, target_horizon_bars: int) -> dict[str, Any]:
    parent, selected, entered, exited, meta = _select_rows(
        frame,
        spec=spec,
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = _summarize(parent, target_horizon_bars=target_horizon_bars)
    selected_summary = _summarize(selected, target_horizon_bars=target_horizon_bars)
    entered_summary = _summarize(entered, target_horizon_bars=target_horizon_bars)
    exited_summary = _summarize(exited, target_horizon_bars=target_horizon_bars)
    entered_minus_exited = strict_stage0._compare(
        candidate=entered_summary,
        baseline=exited_summary,
        target_horizon_bars=target_horizon_bars,
    )
    edge = _edge_vs_parent(
        selected_summary=selected_summary,
        parent_summary=parent_summary,
        target_horizon_bars=target_horizon_bars,
    )
    hfield = f"next_{target_horizon_bars}d_mean"
    return {
        "label": spec.label,
        "spec": {
            "min_quality": float(spec.min_quality),
            "max_replacements": int(spec.max_replacements),
            "confirmation_mode": spec.confirmation_mode,
        },
        "timestamp_activity": meta,
        "parent_short_summary": parent_summary,
        "selected_summary": selected_summary,
        "selected_vs_parent": strict_stage0._compare(
            candidate=selected_summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "edge_vs_parent_mean_return": edge,
        "entered": entered_summary,
        "exited": exited_summary,
        "entered_minus_exited": entered_minus_exited,
        "stage0_scorecard": {
            "stage0_passed": bool(
                edge is not None
                and float(edge) > 0.0005
                and entered_summary.get(hfield) is not None
                and float(entered_summary[hfield]) < 0.0
                and entered_minus_exited.get(f"delta_{hfield}") is not None
                and float(entered_minus_exited[f"delta_{hfield}"]) < 0.0
                and float(meta["changed_timestamp_fraction"]) >= 0.02
            ),
            "edge_vs_parent_mean_return": edge,
            "entered_next_h_mean": entered_summary.get(hfield),
            "entered_minus_exited_next_h_delta": entered_minus_exited.get(f"delta_{hfield}"),
        },
        "rows": {"selected": selected, "entered": entered, "exited": exited},
    }


def _strip_rows(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("rows", None)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    target_horizon_bars = int(args.target_horizon_bars)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-3-mf01-confirmation-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = strict_stage0._load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=0,
    )
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    evaluations: dict[str, Any] = {}
    row_artifacts: dict[str, dict[str, str]] = {}
    for spec in _specs():
        result = _evaluate(frame, spec=spec, target_horizon_bars=target_horizon_bars)
        row_artifacts[spec.label] = {}
        for row_name in ("selected", "entered", "exited"):
            path = output_dir / f"{spec.label}_{row_name}.csv"
            result["rows"][row_name].to_csv(path, index=False)
            row_artifacts[spec.label][row_name] = str(path)
        evaluations[spec.label] = _strip_rows(result)
    ranked = sorted(
        (
            {
                "label": label,
                **dict(payload.get("stage0_scorecard") or {}),
                "changed_timestamp_fraction": dict(payload.get("timestamp_activity") or {}).get("changed_timestamp_fraction"),
                "entered_row_count": dict(payload.get("entered") or {}).get("row_count"),
                "entered_subject_count": dict(payload.get("entered") or {}).get("subject_count"),
                "entered_confirmed_fraction": dict(payload.get("entered") or {}).get("confirmed_eligible_fraction"),
                "entered_boundary_fragile_fraction": dict(payload.get("entered") or {}).get("boundary_fragile_orderbook_flag_fraction"),
                "entered_pump_bid_fail_fraction": dict(payload.get("entered") or {}).get("pump_bid_replenishment_failure_flag_fraction"),
            }
            for label, payload in evaluations.items()
        ),
        key=lambda item: (
            bool(item.get("stage0_passed")),
            float(item.get("edge_vs_parent_mean_return") or -999.0),
            float(item.get("entered_next_h_mean") or 999.0) * -1.0,
        ),
        reverse=True,
    )
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": target_horizon_bars,
        "event_lookback_days": int(args.event_lookback_days),
        "news_artifact": str(args.news_artifact),
        "status_scope": "diagnostic_only_m3_3_mf01_confirmation",
        "row_artifacts": row_artifacts,
        "ranked_variants": ranked,
        "evaluation": evaluations,
        "decision": {
            "promote_to_manifest_ab": False,
            "reason": "MF-01 confirmation must improve event-only q2 before a formal manifest A/B is justified.",
        },
    }
    report_path = output_dir / "m3_3_mf01_confirmation_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 + MF-01 confirmation Stage 0 report to {report_path}")
    print(json.dumps({"ranked_variants": ranked}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
