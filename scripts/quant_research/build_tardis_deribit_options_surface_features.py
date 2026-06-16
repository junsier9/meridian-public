from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import sys
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission import feature_admission_status  # noqa: E402
from enhengclaw.quant_research.options_surface import (  # noqa: E402
    FACTOR_COLUMNS,
    OPTIONS_SURFACE_FEATURE_PANEL_CONTRACT_VERSION,
    build_options_surface_base_panel,
    build_options_surface_feature_panel,
    finalize_options_surface_feature_panel,
    load_ohlcv_realized_vol_panel,
    summarize_options_surface_feature_panel,
    write_options_surface_feature_panel,
)
from scripts.quant_research.provider_probes.probe_tardis_deribit_options_surface import (  # noqa: E402
    DEFAULT_SAMPLE_DATE,
    CredentialCandidate,
    _check_tardis_api_key_info,
    _dataset_url,
    _iter_csv_rows_from_gzip_file,
    _iter_csv_rows_from_tardis,
    _parse_iso_date,
    _resolve_tardis_key,
)
from scripts.quant_research.provider_leaf_sync_helpers.sync_tardis_deribit_options_chain_history import (  # noqa: E402
    partition_path as raw_store_partition_path,
    resolve_external_root as resolve_raw_store_external_root,
)


PROBE_REPORT_NAME = "m3_1_tardis_deribit_options_surface_probe.json"
BUILDER_REPORT_NAME = "m3_1_tardis_deribit_options_surface_builder.json"
ADMISSION_AUDIT_REPORT_NAME = "m3_1_tardis_deribit_options_surface_admission_manifest_audit.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build M3.1 F56-F60 Deribit options-surface features from bounded "
            "Tardis options_chain daily pulls and join formal 30d OHLCV RV."
        )
    )
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--sample-date", default=DEFAULT_SAMPLE_DATE, type=_parse_iso_date)
    parser.add_argument("--from-date", type=_parse_iso_date, default=None)
    parser.add_argument("--to-date", type=_parse_iso_date, default=None)
    parser.add_argument("--max-rows", type=int, default=150_000, help="Maximum options_chain rows per day.")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--rv-window-days", type=int, default=30)
    parser.add_argument("--rv-market-type", default="spot")
    parser.add_argument("--rv-interval", default="1d")
    parser.add_argument(
        "--required-underlyings",
        nargs="+",
        default=["BTC", "ETH"],
        help="Underlying set required before the build report can turn green.",
    )
    parser.add_argument(
        "--input-csv-gz",
        type=Path,
        help="Local gzipped options_chain CSV fixture; skips network but still requires a green probe report.",
    )
    parser.add_argument(
        "--input-raw-store-root",
        type=Path,
        default=None,
        help=(
            "External Tardis historical raw store root containing "
            "raw/deribit/options_chain/YYYY/MM/DD/OPTIONS.csv.gz partitions; skips network."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "options_surface",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    parser.add_argument(
        "--probe-report",
        type=Path,
        default=None,
        help="Explicit green Phase 0 probe report path. Defaults to report-dir/as-of.",
    )
    parser.add_argument(
        "--active-h10d-registry",
        type=Path,
        default=ROOT / "config" / "quant_research" / "active_h10d_registry.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_rows <= 0:
        raise SystemExit("--max-rows must be positive")
    if args.input_csv_gz and args.input_raw_store_root:
        raise SystemExit("--input-csv-gz and --input-raw-store-root are mutually exclusive")

    as_of = str(args.as_of)
    date_range = _resolve_date_range(args)
    sample_date = date_range[-1].isoformat()
    required_underlyings = [value.upper() for value in args.required_underlyings]
    probe_report_path = args.probe_report or args.report_dir / as_of / PROBE_REPORT_NAME
    output_path = args.output_dir / as_of / "tardis_deribit_options_surface_features.csv"
    report_path = args.report_dir / as_of / BUILDER_REPORT_NAME
    audit_report_path = args.report_dir / as_of / ADMISSION_AUDIT_REPORT_NAME

    probe_gate = _read_green_probe_gate(probe_report_path)
    mode = "local_fixture" if args.input_csv_gz else "local_raw_store" if args.input_raw_store_root else "online"
    auth_check: dict[str, object] | None = None
    credential_debug: dict[str, object] | None = None
    per_day_inputs: list[dict[str, object]] = []

    try:
        rv_panel = load_ohlcv_realized_vol_panel(
            external_root=args.ohlcv_external_root,
            required_underlyings=required_underlyings,
            market_type=args.rv_market_type,
            interval=args.rv_interval,
            rv_window_days=args.rv_window_days,
        )

        if args.input_csv_gz:
            rows, probe_input = _iter_csv_rows_from_gzip_file(args.input_csv_gz, args.max_rows)
            per_day_inputs.append(_probe_input_payload(probe_input, sample_date=sample_date))
            panel = build_options_surface_feature_panel(
                rows,
                required_underlyings=required_underlyings,
                realized_vol_panel=rv_panel,
            )
        elif args.input_raw_store_root:
            raw_store_root = resolve_raw_store_external_root(args.input_raw_store_root)
            daily_panels = _build_daily_panels_from_raw_store(
                raw_store_root=raw_store_root,
                date_range=date_range,
                max_rows=args.max_rows,
                required_underlyings=required_underlyings,
                per_day_inputs=per_day_inputs,
            )
            base_panel = _concat_daily_panels(daily_panels)
            panel = finalize_options_surface_feature_panel(
                base_panel,
                realized_vol_panel=rv_panel,
            )
            panel.attrs.update(base_panel.attrs)
        else:
            api_key, credential_debug, credential_candidates = _resolve_tardis_key()
            api_key, auth_check = _select_accepted_tardis_key(
                api_key=api_key,
                credential_candidates=credential_candidates,
                timeout_seconds=args.timeout_seconds,
            )
            daily_panels: list[pd.DataFrame] = []
            for current_date in date_range:
                current_sample_date = current_date.isoformat()
                rows, probe_input = _iter_csv_rows_from_tardis(
                    api_key=api_key,
                    sample_date=current_sample_date,
                    max_rows=args.max_rows,
                    timeout_seconds=args.timeout_seconds,
                )
                per_day_inputs.append(_probe_input_payload(probe_input, sample_date=current_sample_date))
                daily_panel = build_options_surface_base_panel(
                    rows,
                    required_underlyings=required_underlyings,
                )
                daily_panel["_source_sample_date"] = current_sample_date
                daily_panels.append(daily_panel)
            base_panel = _concat_daily_panels(daily_panels)
            panel = finalize_options_surface_feature_panel(
                base_panel,
                realized_vol_panel=rv_panel,
            )
            panel.attrs.update(base_panel.attrs)

        written_path = write_options_surface_feature_panel(panel, output_path=output_path)
        summary = summarize_options_surface_feature_panel(
            panel,
            required_underlyings=required_underlyings,
            output_path=written_path,
            input_rows_read=sum(int(item.get("rows_read") or 0) for item in per_day_inputs),
        )
        audit = _build_admission_manifest_audit(
            panel=panel,
            audit_report_path=audit_report_path,
            active_h10d_registry=args.active_h10d_registry,
            output_path=written_path,
        )
        summary.update(
            {
                "generated_at_utc": _now_utc(),
                "builder_mode": mode,
                "contract_version": OPTIONS_SURFACE_FEATURE_PANEL_CONTRACT_VERSION,
                "probe_gate": probe_gate,
                "input": {
                    "source": (
                        "local_fixture"
                        if args.input_csv_gz
                        else "local_raw_store_date_range"
                        if args.input_raw_store_root
                        else "tardis_dataset_date_range"
                    ),
                    "date_start": date_range[0].isoformat(),
                    "date_end": date_range[-1].isoformat(),
                    "date_count": len(date_range),
                    "max_rows_per_day": args.max_rows,
                    "rows_read": sum(int(item.get("rows_read") or 0) for item in per_day_inputs),
                    "raw_store_root": (
                        str(resolve_raw_store_external_root(args.input_raw_store_root))
                        if args.input_raw_store_root
                        else None
                    ),
                    "per_day": per_day_inputs,
                },
                "realized_vol_input": _summarize_rv_panel(rv_panel),
                "panel_deduplication": panel.attrs.get(
                    "panel_deduplication",
                    {
                        "duplicate_subject_date_rows_removed": 0,
                        "duplicate_subject_date_rows_seen": 0,
                    },
                ),
                "admission_manifest_audit_path": str(audit_report_path),
                "admission_manifest_audit": audit["decision"],
                "auth_check": auth_check,
                "credential_debug": _sanitize_credential_debug(credential_debug),
                "phase1_decision": {
                    "feature_builder_ran": True,
                    "raw_sample_retained": False,
                    "manifest_mutation_authorized": False,
                    "all_required_subjects_latest_ready": summary["feature_readiness"][
                        "all_required_subjects_latest_ready"
                    ],
                },
            }
        )
        _write_json(audit_report_path, audit)
        _write_json(report_path, summary)
        print(str(written_path))
        return 0 if summary["feature_readiness"]["all_required_subjects_latest_ready"] else 1
    except Exception as exc:  # noqa: BLE001
        failure = {
            "generated_at_utc": _now_utc(),
            "contract_version": OPTIONS_SURFACE_FEATURE_PANEL_CONTRACT_VERSION,
            "builder_mode": mode,
            "probe_gate": probe_gate,
            "input": {
                "source": "builder_exception",
                "url": _dataset_url(sample_date),
                "http_status": None,
                "date_start": date_range[0].isoformat(),
                "date_end": date_range[-1].isoformat(),
                "rows_read": sum(int(item.get("rows_read") or 0) for item in per_day_inputs),
            },
            "auth_check": auth_check,
            "credential_debug": _sanitize_credential_debug(credential_debug),
            "phase1_decision": {
                "feature_builder_ran": False,
                "raw_sample_retained": False,
                "manifest_mutation_authorized": False,
                "all_required_subjects_latest_ready": False,
                "builder_exception": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
        }
        _write_json(report_path, failure)
        print(f"options-surface builder failed closed; report written to {report_path}")
        return 1


def _read_green_probe_gate(path: Path) -> dict[str, object]:
    if not path.exists():
        raise RuntimeError(f"green Tardis Phase 0 probe report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    decision = payload.get("phase0_decision", {})
    checks = {
        "probe_report_path": str(path),
        "contract_version": payload.get("contract_version"),
        "authenticated_key_accepted": bool(decision.get("authenticated_key_accepted")),
        "feature_builder_allowed": bool(decision.get("feature_builder_allowed")),
        "m3_1_tardis_options_surface_phase0_ready": bool(
            decision.get("m3_1_tardis_options_surface_phase0_ready")
        ),
        "raw_sample_retained": bool(decision.get("raw_sample_retained")),
        "manifest_mutation_authorized": bool(decision.get("manifest_mutation_authorized")),
    }
    if not (
        checks["authenticated_key_accepted"]
        and checks["feature_builder_allowed"]
        and checks["m3_1_tardis_options_surface_phase0_ready"]
        and checks["raw_sample_retained"] is False
        and checks["manifest_mutation_authorized"] is False
    ):
        raise RuntimeError(f"Tardis Phase 0 probe report is not green: {path}")
    return checks


def _resolve_date_range(args: argparse.Namespace) -> list[date]:
    start = args.from_date or args.sample_date
    end = args.to_date or args.sample_date
    if end < start:
        raise SystemExit("--to-date must be >= --from-date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _concat_daily_panels(panels: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [panel for panel in panels if panel is not None and not panel.empty]
    if not non_empty:
        raise RuntimeError("No daily options-surface panels were built")
    combined = pd.concat(non_empty, ignore_index=True)
    duplicate_mask = combined.duplicated(subset=["subject", "date_utc"], keep=False)
    sort_columns = ["date_utc", "subject"]
    if "_source_sample_date" in combined.columns:
        sort_columns.append("_source_sample_date")
    combined = combined.sort_values(sort_columns).reset_index(drop=True)
    deduped = (
        combined.drop_duplicates(subset=["subject", "date_utc"], keep="last")
        .drop(columns=["_source_sample_date"], errors="ignore")
        .sort_values(["date_utc", "subject"])
        .reset_index(drop=True)
    )
    deduped.attrs["panel_deduplication"] = {
        "duplicate_subject_date_rows_seen": int(duplicate_mask.sum()),
        "duplicate_subject_date_rows_removed": int(combined.shape[0] - deduped.shape[0]),
        "key": ["subject", "date_utc"],
        "policy": "keep_latest_source_sample_date",
    }
    return deduped


def _build_daily_panels_from_raw_store(
    *,
    raw_store_root: Path,
    date_range: list[date],
    max_rows: int,
    required_underlyings: list[str],
    per_day_inputs: list[dict[str, object]],
) -> list[pd.DataFrame]:
    missing = [
        raw_store_partition_path(external_root=raw_store_root, current_date=current_date)
        for current_date in date_range
        if not raw_store_partition_path(external_root=raw_store_root, current_date=current_date).exists()
    ]
    if missing:
        preview = [str(path) for path in missing[:10]]
        raise RuntimeError(
            "local raw store is missing options_chain partitions: "
            f"{preview} plus {max(len(missing) - len(preview), 0)} more"
        )

    daily_panels: list[pd.DataFrame] = []
    for current_date in date_range:
        current_sample_date = current_date.isoformat()
        path = raw_store_partition_path(external_root=raw_store_root, current_date=current_date)
        rows, probe_input = _iter_csv_rows_from_gzip_file(path, max_rows)
        per_day_inputs.append(
            {
                **_probe_input_payload(probe_input, sample_date=current_sample_date),
                "source": "local_raw_store",
                "path": str(path),
            }
        )
        daily_panel = build_options_surface_base_panel(
            rows,
            required_underlyings=required_underlyings,
        )
        daily_panel["_source_sample_date"] = current_sample_date
        daily_panels.append(daily_panel)
    return daily_panels


def _probe_input_payload(probe_input: object, *, sample_date: str) -> dict[str, object]:
    return {
        "source": probe_input.source,
        "url": probe_input.url or _dataset_url(sample_date),
        "http_status": probe_input.http_status,
        "sample_date": sample_date,
        "rows_read": probe_input.rows_read,
    }


def _summarize_rv_panel(panel: pd.DataFrame) -> dict[str, object]:
    if panel.empty:
        return {
            "source": "canonical_spot_ohlcv",
            "row_count": 0,
            "subjects": [],
            "ready_rows": 0,
        }
    ready = pd.to_numeric(panel["realized_vol_30d_ohlcv"], errors="coerce").notna()
    return {
        "source": "canonical_spot_ohlcv",
        "row_count": int(panel.shape[0]),
        "subjects": sorted(panel["subject"].astype(str).unique().tolist()),
        "start_date_utc": str(panel["date_utc"].min()),
        "end_date_utc": str(panel["date_utc"].max()),
        "ready_rows": int(ready.sum()),
        "rv_window_days": _first_non_null(panel, "realized_vol_ohlcv_window_days"),
        "market_type": _first_non_null(panel, "realized_vol_ohlcv_market_type"),
        "interval": _first_non_null(panel, "realized_vol_ohlcv_interval"),
    }


def _build_admission_manifest_audit(
    *,
    panel: pd.DataFrame,
    audit_report_path: Path,
    active_h10d_registry: Path,
    output_path: Path,
) -> dict[str, object]:
    registry_payload: dict[str, object] = {}
    manifest_payload: dict[str, object] = {}
    manifest_path: Path | None = None
    if active_h10d_registry.exists():
        registry_payload = json.loads(active_h10d_registry.read_text(encoding="utf-8"))
        canonical_parent = registry_payload.get("canonical_parent")
        raw_manifest = canonical_parent.get("manifest_path") if isinstance(canonical_parent, dict) else None
        if raw_manifest:
            manifest_path = (ROOT / str(raw_manifest)).resolve()
    if manifest_path is not None and manifest_path.exists():
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    candidate_columns = list(FACTOR_COLUMNS)
    admission_status = {column: feature_admission_status(column) for column in candidate_columns}
    rejected_by_v1 = [column for column, status in admission_status.items() if status != "admitted"]
    active_required = _active_required_feature_columns(manifest_payload)
    absent_from_active_manifest = [column for column in candidate_columns if column not in active_required]
    ready_counts = {
        column: int(panel[column].fillna(False).astype(bool).sum())
        for column in ("f56_ready", "f57_ready", "f58_ready", "f59_ready", "f60_ready")
        if column in panel.columns
    }
    blockers = []
    if rejected_by_v1:
        blockers.append("feature_admission_v1_rejects_candidate_columns")
    if absent_from_active_manifest:
        blockers.append("active_h10d_manifest_does_not_reference_f56_f60")
    blockers.extend(
        [
            "feature_admission_v2_empirical_gates_not_run",
            "candidate_scope_is_btc_eth_t2_context_not_cross_sectional_top20_score_component",
        ]
    )
    decision = {
        "audit_status": "blocked_for_manifest_admission",
        "manifest_mutation_authorized": False,
        "admission_to_active_manifest_allowed": False,
        "blockers": blockers,
        "next_allowed_step": "run_preregistered_factor_report_card_or_overlay_context_audit_before_manifest_change",
    }
    canonical_parent = registry_payload.get("canonical_parent")
    return {
        "contract_version": "quant_m3_1_options_surface_admission_manifest_audit.v1",
        "generated_at_utc": _now_utc(),
        "options_surface_panel_path": str(output_path),
        "audit_report_path": str(audit_report_path),
        "candidate_feature_columns": candidate_columns,
        "feature_admission_v1": {
            "status_by_column": admission_status,
            "rejected_columns": rejected_by_v1,
            "recommended_policy_changes_if_owner_approved": [
                "add iv_ prefix or exact F56/F57/F58 columns",
                "add dealer_gamma_ prefix or exact F59 column",
                "add vanna_charm_ prefix or exact F60 column",
            ],
        },
        "active_h10d_registry": {
            "path": str(active_h10d_registry),
            "canonical_parent_label": canonical_parent.get("label") if isinstance(canonical_parent, dict) else None,
            "manifest_path": str(manifest_path) if manifest_path is not None else None,
        },
        "active_manifest": {
            "contract_version": manifest_payload.get("contract_version"),
            "required_feature_columns": active_required,
            "candidate_columns_absent": absent_from_active_manifest,
        },
        "panel_readiness": {
            "row_count": int(panel.shape[0]),
            "date_start": str(panel["date_utc"].min()) if not panel.empty else None,
            "date_end": str(panel["date_utc"].max()) if not panel.empty else None,
            "subjects": sorted(panel["subject"].astype(str).unique().tolist()) if not panel.empty else [],
            "ready_counts": ready_counts,
        },
        "decision": decision,
    }


def _active_required_feature_columns(manifest_payload: dict[str, object]) -> list[str]:
    entries = manifest_payload.get("entries") if isinstance(manifest_payload, dict) else []
    out: list[str] = []
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for column in entry.get("required_feature_columns") or []:
            value = str(column).strip()
            if value and value not in out:
                out.append(value)
    return out


def _select_accepted_tardis_key(
    *,
    api_key: str | None,
    credential_candidates: list[CredentialCandidate],
    timeout_seconds: float,
) -> tuple[str, dict[str, object]]:
    if not api_key or not credential_candidates:
        raise RuntimeError("Tardis API key missing; rerun the Phase 0 probe before builder")
    for candidate in credential_candidates:
        candidate_check = _check_tardis_api_key_info(
            api_key=candidate.value,
            timeout_seconds=timeout_seconds,
        )
        candidate_check["env_var"] = candidate.env_var
        candidate_check["scope"] = candidate.scope
        candidate_check["value_length"] = len(candidate.value)
        candidate_check["normalization"] = candidate.normalization
        if candidate_check.get("accepted"):
            return candidate.value, candidate_check
    raise RuntimeError("Tardis api-key-info rejected all available key candidates")


def _sanitize_credential_debug(debug: dict[str, object] | None) -> dict[str, object] | None:
    if debug is None:
        return None
    return {
        key: value
        for key, value in debug.items()
        if key
        in {"checked_env_vars", "selected_env_var", "selected_scope", "selected_value_length", "candidate_count"}
    }


def _first_non_null(frame: pd.DataFrame, column: str) -> object:
    if column not in frame.columns:
        return None
    values = frame[column].dropna()
    if values.empty:
        return None
    value = values.iloc[0]
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
