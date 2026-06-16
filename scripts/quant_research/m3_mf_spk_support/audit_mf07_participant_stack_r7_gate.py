from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_eval  # noqa: E402


CONTRACT_VERSION = "mf07_participant_stack_r7_gate.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-r7-mf07-participant-stack-gate"
)
DEFAULT_DAILY_STAGE0 = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-r7-mf07-participant-disagreement-spk-stage0"
    / "mf07_participant_disagreement_spk_stage0.json"
)
DEFAULT_SUBDAY_STAGE0 = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-r7-mf07-subday-participant-pivot-stage0"
    / "mf07_subday_participant_pivot_stage0.json"
)
CAPABILITY_PATH = ROOT / "artifacts" / "quant_research" / "provider_smoke" / "coinglass_capability_matrix.json"


FEATURE_GROUPS = {
    "top_global_position": [
        "coinglass_top_trader_long_pct",
        "coinglass_global_account_long_pct",
        "top_global_disagreement_1h_30d",
        "top_trader_velocity_1h_abs_24h",
    ],
    "taker_flow": [
        "coinglass_taker_buy_volume_24h",
        "coinglass_taker_sell_volume_24h",
        "coinglass_taker_net_volume_24h",
        "coinglass_taker_net_to_depth_mean_24h",
    ],
    "cex_transfer_direction_partial": [
        "stablecoin_flow_signal_ready",
        "stablecoin_exchange_netflow_ratio",
        "stablecoin_exchange_absorption_score_v1",
    ],
    "whale_transfer_direction_partial": [
        "stablecoin_flow_signal_ready",
        "stablecoin_whale_to_exchange_ratio",
        "stablecoin_whale_exchange_stress_score_v1",
    ],
    "etf_flow_regime": [
        "btc_etf_flow",
        "eth_etf_flow",
        "bitcoin_etf_flow",
        "ethereum_etf_flow",
        "coinglass_btc_etf_flow",
        "coinglass_eth_etf_flow",
    ],
}

PARTICIPANT_SIDECAR_BY_GROUP = {
    "cex_transfer_direction_partial": "coinglass_onchain_exchange_transfers",
    "whale_transfer_direction_partial": "coinglass_whale_transfers",
    "etf_flow_regime": "coinglass_etf_daily_state",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "R-7 MF-07 participant-stack admission gate. This combines fresh MF-07 "
            "Stage0 reports with full-stack data availability before any alpha rerun."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--daily-stage0-report", type=Path, default=DEFAULT_DAILY_STAGE0)
    parser.add_argument("--subday-stage0-report", type=Path, default=DEFAULT_SUBDAY_STAGE0)
    parser.add_argument("--capability-path", type=Path, default=CAPABILITY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-feature-coverage", type=float, default=0.90)
    parser.add_argument("--min-changed-timestamp-fraction", type=float, default=0.05)
    parser.add_argument("--min-edge-vs-raw-spk", type=float, default=0.0005)
    return parser


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return out


def _feature_group_coverage(
    frame: pd.DataFrame,
    *,
    groups: dict[str, list[str]] = FEATURE_GROUPS,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for group, columns in groups.items():
        present = [column for column in columns if column in frame.columns]
        missing = [column for column in columns if column not in frame.columns]
        column_coverage: dict[str, float] = {}
        for column in present:
            values = frame[column]
            if values.dtype == bool:
                coverage = float(values.notna().mean())
            else:
                coverage = float(pd.to_numeric(values, errors="coerce").notna().mean())
            column_coverage[column] = coverage
        min_coverage = min(column_coverage.values()) if column_coverage else 0.0
        out[group] = {
            "required_columns": columns,
            "present_columns": present,
            "missing_columns": missing,
            "present_fraction": float(len(present) / max(len(columns), 1)),
            "min_non_null_coverage": float(min_coverage),
            "column_coverage": column_coverage,
        }
    return out


def _stage0_admission_summary(
    report: dict[str, Any],
    *,
    min_changed_timestamp_fraction: float,
    min_edge_vs_raw_spk: float,
) -> dict[str, Any]:
    evaluations = dict(report.get("evaluation") or {})
    target_horizon_bars = int(report.get("target_horizon_bars") or 10)
    kept: list[dict[str, Any]] = []
    ranked: list[dict[str, Any]] = []
    for label, payload in evaluations.items():
        if label == "spk_raw":
            continue
        vs_raw = dict(payload.get("vs_spk_raw") or {})
        selection = dict(payload.get("selection_vs_spk_raw") or {})
        edge = _safe_float(vs_raw.get(f"short_basket_edge_vs_baseline_{target_horizon_bars}d"))
        changed = _safe_float(selection.get("changed_timestamp_fraction")) or 0.0
        entered_edge = _safe_float(selection.get(f"entered_edge_vs_exited_{target_horizon_bars}d"))
        passed = (
            edge is not None
            and edge >= float(min_edge_vs_raw_spk)
            and changed >= float(min_changed_timestamp_fraction)
            and entered_edge is not None
            and entered_edge > 0.0
        )
        item = {
            "label": label,
            "edge_vs_raw_spk": edge,
            "changed_timestamp_fraction": changed,
            "entered_edge_vs_exited": entered_edge,
            "vs_raw_verdict": vs_raw.get("verdict"),
            "admission_pass": passed,
        }
        ranked.append(item)
        if passed:
            kept.append(item)
    ranked.sort(key=lambda item: (item.get("edge_vs_raw_spk") is not None, item.get("edge_vs_raw_spk") or -999), reverse=True)
    return {
        "target_horizon_bars": target_horizon_bars,
        "kept_variant_count": int(len(kept)),
        "kept_variants": kept,
        "top_ranked_variants": ranked[:5],
    }


def _market_history_root() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history"


def _sidecar_presence() -> dict[str, Any]:
    market_root = _market_history_root()
    coinglass_extended = market_root / "coinglass_extended"
    symbol_dirs = [path for path in coinglass_extended.glob("*USDT")] if coinglass_extended.exists() else []
    candidates = {
        "coinglass_extended_1h_participant": coinglass_extended,
        "coinglass_etf_daily_state": ROOT / "artifacts" / "quant_research" / "coinglass" / "etf_daily_state_1d.csv.gz",
        "coinglass_onchain_exchange_transfers": ROOT
        / "artifacts"
        / "quant_research"
        / "coinglass"
        / "exchange_transfers_1d.csv.gz",
        "coinglass_whale_transfers": ROOT / "artifacts" / "quant_research" / "coinglass" / "whale_transfers_1d.csv.gz",
    }
    out = {key: _sidecar_file_status(path) for key, path in candidates.items()}
    out["coinglass_extended_1h_participant"]["symbol_dir_count"] = int(len(symbol_dirs))
    return out


def _sidecar_file_status(path: Path) -> dict[str, Any]:
    status: dict[str, Any] = {"path": str(path), "exists": bool(path.exists())}
    if not path.exists() or not path.is_file():
        return status
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - defensive report metadata only.
        status["read_error"] = str(exc)
        return status
    status["row_count"] = int(len(frame))
    status["column_count"] = int(len(frame.columns))
    status["columns"] = [str(column) for column in frame.columns[:40]]
    if "date_utc" in frame.columns and len(frame) > 0:
        status["first_date_utc"] = str(frame["date_utc"].min())
        status["last_date_utc"] = str(frame["date_utc"].max())
    return status


def _capability_family_status(capability: dict[str, Any]) -> dict[str, Any]:
    endpoints = list(capability.get("endpoints") or [])
    wanted = {
        "etf": [],
        "onchain": [],
        "participant_or_flow": [],
    }
    for endpoint in endpoints:
        family = str(endpoint.get("family") or "")
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        if family == "etf":
            wanted["etf"].append(endpoint)
        if family == "onchain":
            wanted["onchain"].append(endpoint)
        if endpoint_id in {
            "futures_global_long_short_account_ratio",
            "futures_top_long_short_position_ratio",
            "futures_taker_buy_sell_volume",
            "spot_taker_buy_sell_volume",
        }:
            wanted["participant_or_flow"].append(endpoint)
    return {
        key: {
            "endpoint_count": int(len(items)),
            "success_count": int(sum(1 for item in items if item.get("status") == "success")),
            "available_endpoint_ids": [str(item.get("endpoint_id")) for item in items if item.get("status") == "success"],
        }
        for key, items in wanted.items()
    }


def _decision(
    *,
    daily_admission: dict[str, Any],
    subday_admission: dict[str, Any],
    feature_coverage: dict[str, Any],
    sidecars: dict[str, Any],
    min_feature_coverage: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    if int(daily_admission.get("kept_variant_count") or 0) <= 0:
        blockers.append("daily_top_global_mf07_no_stage0_survivor")
    if int(subday_admission.get("kept_variant_count") or 0) <= 0:
        blockers.append("subday_participant_pivot_no_stage0_survivor")

    # Top/global and taker-flow availability is still reported, but the hard
    # R-7 2.0 blocker is the missing exogenous participant stack. The current
    # top/global and sub-day pivot forms already have fresh Stage0 rejection.
    required_groups = [
        "cex_transfer_direction_partial",
        "whale_transfer_direction_partial",
        "etf_flow_regime",
    ]
    for group in required_groups:
        entry = dict(feature_coverage.get(group) or {})
        sidecar_key = PARTICIPANT_SIDECAR_BY_GROUP[group]
        sidecar_exists = bool(dict(sidecars.get(sidecar_key) or {}).get("exists"))
        if sidecar_exists and (
            entry.get("missing_columns")
            or float(entry.get("min_non_null_coverage") or 0.0) < float(min_feature_coverage)
        ):
            blockers.append(f"{group}_sidecar_not_integrated_into_feature_panel")
            continue
        if entry.get("missing_columns"):
            blockers.append(f"{group}_missing_required_columns")
        if float(entry.get("min_non_null_coverage") or 0.0) < float(min_feature_coverage):
            blockers.append(f"{group}_coverage_below_threshold")

    if not dict(sidecars.get("coinglass_etf_daily_state") or {}).get("exists"):
        blockers.append("missing_pit_etf_daily_sidecar")
    if not dict(sidecars.get("coinglass_onchain_exchange_transfers") or {}).get("exists"):
        blockers.append("missing_pit_exchange_transfer_sidecar")
    if not dict(sidecars.get("coinglass_whale_transfers") or {}).get("exists"):
        blockers.append("missing_pit_whale_transfer_sidecar")

    return {
        "stage0_status": "r7_rejected_current_forms_full_stack_blocked",
        "alpha_rerun_allowed": False,
        "manifest_ab_allowed": False,
        "blocker_codes": sorted(set(blockers)),
        "next_action": (
            "Do not spend another manifest slot on MF-07 top/global or 1h pivot flags. "
            "R-7 can reopen only after the PIT ETF/on-chain participant sidecars are "
            "integrated into a pre-registered transition definition that beats raw SP-K."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_report = _load_json(args.daily_stage0_report.resolve())
    subday_report = _load_json(args.subday_stage0_report.resolve())
    feature_path = v5_eval.base_eval._features_artifact_path(str(args.as_of))
    features = pd.read_csv(feature_path)
    feature_coverage = _feature_group_coverage(features)
    capability = _load_json(args.capability_path.resolve()) if args.capability_path.exists() else {}
    sidecars = _sidecar_presence()

    daily_admission = _stage0_admission_summary(
        daily_report,
        min_changed_timestamp_fraction=args.min_changed_timestamp_fraction,
        min_edge_vs_raw_spk=args.min_edge_vs_raw_spk,
    )
    subday_admission = _stage0_admission_summary(
        subday_report,
        min_changed_timestamp_fraction=args.min_changed_timestamp_fraction,
        min_edge_vs_raw_spk=args.min_edge_vs_raw_spk,
    )
    decision = _decision(
        daily_admission=daily_admission,
        subday_admission=subday_admission,
        feature_coverage=feature_coverage,
        sidecars=sidecars,
        min_feature_coverage=args.min_feature_coverage,
    )

    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": _now_utc(),
        "as_of": str(args.as_of),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "question": "Can R-7 MF-07 participant disagreement 2.0 reopen alpha validation now?",
        "input_reports": {
            "daily_stage0": str(args.daily_stage0_report.resolve()),
            "subday_stage0": str(args.subday_stage0_report.resolve()),
        },
        "features_artifact": str(feature_path),
        "feature_rows": int(len(features)),
        "feature_subject_count": int(features["subject"].astype(str).nunique()) if "subject" in features.columns else None,
        "feature_coverage": feature_coverage,
        "sidecar_presence": sidecars,
        "capability_family_status": _capability_family_status(capability),
        "daily_stage0_admission": daily_admission,
        "subday_stage0_admission": subday_admission,
        "decision": decision,
        "thresholds": {
            "min_feature_coverage": float(args.min_feature_coverage),
            "min_changed_timestamp_fraction": float(args.min_changed_timestamp_fraction),
            "min_edge_vs_raw_spk": float(args.min_edge_vs_raw_spk),
        },
    }
    report_path = output_dir / "mf07_participant_stack_r7_gate.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "decision": decision}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
