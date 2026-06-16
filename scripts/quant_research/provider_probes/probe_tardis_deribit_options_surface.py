"""Read-only Tardis Deribit options-surface Phase 0 probe.

The probe verifies whether the configured Tardis CSV dataset access can support
the M3.1 options-surface feature family before any feature builder or h10d
manifest work is allowed.

It streams a bounded sample from:
  https://datasets.tardis.dev/v1/deribit/options_chain/YYYY/MM/DD/OPTIONS.csv.gz

No raw vendor rows are retained by default. The output is a local coverage and
schema report only.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CONTRACT_VERSION = "quant_m3_1_tardis_deribit_options_surface_probe.v1"
DATASET_BASE_URL = "https://datasets.tardis.dev/v1"
API_BASE_URL = "https://api.tardis.dev/v1"
DEFAULT_SAMPLE_DATE = "2026-05-15"
DEFAULT_ENV_NAMES = (
    "Tardis_api_key",
    "TARDIS_API_KEY",
    "TARDIS_API",
    "TARDIS_DEV_API_KEY",
    "Tardis_API_KEY",
)
REQUIRED_COLUMNS = {
    "exchange",
    "symbol",
    "timestamp",
    "local_timestamp",
    "type",
    "strike_price",
    "expiration",
    "open_interest",
    "mark_iv",
    "underlying_index",
    "underlying_price",
    "delta",
    "gamma",
}
FEATURE_REQUIREMENTS = {
    "F56_25d_skew_residual": {
        "columns": {"symbol", "type", "expiration", "strike_price", "mark_iv", "delta"},
        "sample_check": "near_25_delta_put_and_call",
    },
    "F57_iv_rv_spread": {
        "columns": {"symbol", "expiration", "mark_iv", "delta", "underlying_price"},
        "sample_check": "atm_iv_available",
        "external_dependency": "realized volatility from existing OHLCV panel",
    },
    "F58_iv_term_slope": {
        "columns": {"symbol", "expiration", "mark_iv", "delta", "underlying_price"},
        "sample_check": "atm_iv_multiple_expiries",
    },
    "F59_dealer_gamma_proxy": {
        "columns": {
            "symbol",
            "type",
            "expiration",
            "strike_price",
            "open_interest",
            "underlying_price",
            "gamma",
        },
        "sample_check": "oi_and_gamma_available",
    },
    "F60_vanna_charm_window": {
        "columns": {"symbol", "expiration", "strike_price", "open_interest", "underlying_price"},
        "sample_check": "atm_oi_and_expiry_available",
    },
}


@dataclass(frozen=True)
class ProbeInput:
    source: str
    url: str | None
    http_status: int | None
    sample_date: str
    rows_read: int


@dataclass(frozen=True)
class CredentialCandidate:
    env_var: str
    scope: str
    value: str
    normalization: str


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD date, got {value!r}") from exc


def _dataset_url(sample_date: str) -> str:
    parsed = _parse_iso_date(sample_date)
    return (
        f"{DATASET_BASE_URL}/deribit/options_chain/"
        f"{parsed:%Y/%m/%d}/OPTIONS.csv.gz"
    )


def _resolve_tardis_key(
    env_names: Iterable[str] = DEFAULT_ENV_NAMES,
) -> tuple[str | None, dict, list[CredentialCandidate]]:
    checked: dict[str, str] = {}
    candidates: list[CredentialCandidate] = []
    for name in env_names:
        scoped_values = _read_scoped_environment_values(name)
        checked[name] = (
            ",".join(f"set:{scope}" for scope, _value in scoped_values)
            if scoped_values
            else "missing"
        )
        for scope, value in scoped_values:
            normalized_value, normalization = _normalize_tardis_key_value(value)
            if normalized_value:
                candidates.append(
                    CredentialCandidate(
                        env_var=name,
                        scope=scope,
                        value=normalized_value,
                        normalization=normalization,
                    )
                )
    selected = candidates[0] if candidates else None
    return (selected.value if selected else None), {
        "checked_env_vars": checked,
        "selected_env_var": selected.env_var if selected else None,
        "selected_scope": selected.scope if selected else None,
        "selected_value_length": len(selected.value) if selected else None,
        "candidate_count": len(candidates),
        "candidate_readback": [
            {
                "env_var": candidate.env_var,
                "scope": candidate.scope,
                "value_length": len(candidate.value),
                "normalization": candidate.normalization,
            }
            for candidate in candidates
        ],
    }, candidates


def _normalize_tardis_key_value(value: str) -> tuple[str, str]:
    normalized = value.strip()
    steps: list[str] = []
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {"'", '"'}
    ):
        normalized = normalized[1:-1].strip()
        steps.append("strip_outer_quotes")
    for prefix in ("Bearer ", "bearer "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            steps.append("remove_bearer_prefix")
            break
    for literal_escape in ("\\n", "\\r", "\\t"):
        if literal_escape in normalized:
            normalized = normalized.replace(literal_escape, "")
            steps.append("remove_literal_escape_whitespace")
    if any(ch.isspace() for ch in normalized):
        collapsed = "".join(normalized.split())
        if collapsed != normalized:
            normalized = collapsed
            steps.append("remove_embedded_whitespace")
    return normalized, "+".join(steps) if steps else "raw_strip"


def _read_scoped_environment_values(name: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    process_value = os.environ.get(name, "").strip()
    if process_value:
        values.append(("process", process_value))
    if os.name != "nt":
        return values
    try:
        import winreg
    except ImportError:
        return values

    locations = (
        ("user", winreg.HKEY_CURRENT_USER, "Environment"),
        (
            "machine",
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    for scope, root_key, subkey in locations:
        try:
            with winreg.OpenKey(root_key, subkey) as handle:
                value, _value_type = winreg.QueryValueEx(handle, name)
        except OSError:
            continue
        text = str(value).strip()
        if text:
            values.append((scope, text))
    return values


def _check_tardis_api_key_info(*, api_key: str, timeout_seconds: float) -> dict[str, object]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for online Tardis probe") from exc

    url = f"{API_BASE_URL}/api-key-info"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_seconds,
    )
    payload: dict[str, object] = {
        "endpoint": url,
        "status_code": response.status_code,
        "accepted": response.status_code == 200,
    }
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.status_code == 200 and isinstance(body, dict):
        payload["top_level_keys"] = sorted(str(key) for key in body.keys())
    elif response.text:
        payload["body_excerpt"] = response.text[:500]
    return payload


def _iter_csv_rows_from_gzip_file(path: Path, max_rows: int) -> tuple[list[dict[str, str]], ProbeInput]:
    with gzip.open(path, mode="rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= max_rows:
                break
    return rows, ProbeInput(
        source="local_fixture",
        url=None,
        http_status=None,
        sample_date="fixture",
        rows_read=len(rows),
    )


def _iter_csv_rows_from_tardis(
    *,
    api_key: str,
    sample_date: str,
    max_rows: int,
    timeout_seconds: float,
) -> tuple[list[dict[str, str]], ProbeInput]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is required for online Tardis probe") from exc

    url = _dataset_url(sample_date)
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers, stream=True, timeout=timeout_seconds)
    if response.status_code != 200:
        excerpt = response.text[:500] if response.text else ""
        raise RuntimeError(
            f"Tardis dataset request failed: status={response.status_code} body_excerpt={excerpt!r}"
        )

    response.raw.decode_content = False
    rows: list[dict[str, str]] = []
    with gzip.GzipFile(fileobj=response.raw) as gzip_handle:
        text_handle = io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="")
        reader = csv.DictReader(text_handle)
        for row in reader:
            rows.append(row)
            if len(rows) >= max_rows:
                break
    response.close()
    return rows, ProbeInput(
        source="tardis_dataset",
        url=url,
        http_status=response.status_code,
        sample_date=sample_date,
        rows_read=len(rows),
    )


def _non_empty(value: object) -> bool:
    return value is not None and str(value).strip() not in {"", "nan", "NaN", "None"}


def _to_float(value: object) -> float | None:
    if not _non_empty(value):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _to_int(value: object) -> int | None:
    if not _non_empty(value):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def _underlying_from_row(row: dict[str, str]) -> str:
    underlying_index = str(row.get("underlying_index", "")).upper()
    if "BTC" in underlying_index:
        return "BTC"
    if "ETH" in underlying_index:
        return "ETH"
    symbol = str(row.get("symbol", "")).upper()
    if symbol.startswith("BTC-"):
        return "BTC"
    if symbol.startswith("ETH-"):
        return "ETH"
    return "UNKNOWN"


def _coverage_ratio(rows: list[dict[str, str]], column: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if _non_empty(row.get(column))) / len(rows)


def _timestamp_range(rows: list[dict[str, str]], column: str) -> dict[str, str | None]:
    values = [_to_int(row.get(column)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return {"min_utc": None, "max_utc": None}
    return {
        "min_utc": datetime.fromtimestamp(min(values) / 1_000_000, tz=UTC).isoformat(),
        "max_utc": datetime.fromtimestamp(max(values) / 1_000_000, tz=UTC).isoformat(),
    }


def _rows_by_underlying(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_underlying_from_row(row)].append(row)
    return dict(grouped)


def _near_delta_rows(rows: list[dict[str, str]], lower: float, upper: float) -> list[dict[str, str]]:
    result = []
    for row in rows:
        delta = _to_float(row.get("delta"))
        if delta is None:
            continue
        if lower <= abs(delta) <= upper and _non_empty(row.get("mark_iv")):
            result.append(row)
    return result


def _atm_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return _near_delta_rows(rows, 0.40, 0.60)


def _sample_checks(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    grouped = _rows_by_underlying(rows)
    checks: dict[str, dict[str, object]] = {}
    for underlying, group in grouped.items():
        if underlying == "UNKNOWN":
            continue
        near_25 = _near_delta_rows(group, 0.15, 0.35)
        atm = _atm_rows(group)
        near_25_types = {str(row.get("type", "")).strip().lower() for row in near_25}
        atm_expiries = {
            str(row.get("expiration"))
            for row in atm
            if _non_empty(row.get("expiration"))
        }
        oi_gamma_rows = [
            row
            for row in group
            if _non_empty(row.get("open_interest")) and _non_empty(row.get("gamma"))
        ]
        atm_oi_rows = [
            row
            for row in atm
            if _non_empty(row.get("open_interest")) and _non_empty(row.get("strike_price"))
        ]
        checks[underlying] = {
            "rows": len(group),
            "near_25_delta_rows": len(near_25),
            "near_25_delta_has_put": "put" in near_25_types,
            "near_25_delta_has_call": "call" in near_25_types,
            "atm_rows": len(atm),
            "atm_expiry_count": len(atm_expiries),
            "oi_gamma_rows": len(oi_gamma_rows),
            "atm_oi_rows": len(atm_oi_rows),
        }
    return checks


def _feature_constructability(
    *,
    columns: set[str],
    rows: list[dict[str, str]],
    required_underlyings: list[str],
) -> dict[str, dict[str, object]]:
    checks = _sample_checks(rows)
    feature_status: dict[str, dict[str, object]] = {}
    for feature_id, spec in FEATURE_REQUIREMENTS.items():
        required_columns = set(spec["columns"])
        missing_columns = sorted(required_columns - columns)
        per_underlying: dict[str, bool] = {}
        for underlying in required_underlyings:
            item = checks.get(underlying, {})
            if spec["sample_check"] == "near_25_delta_put_and_call":
                ok = bool(
                    item.get("near_25_delta_has_put")
                    and item.get("near_25_delta_has_call")
                )
            elif spec["sample_check"] == "atm_iv_available":
                ok = int(item.get("atm_rows", 0)) > 0
            elif spec["sample_check"] == "atm_iv_multiple_expiries":
                ok = int(item.get("atm_expiry_count", 0)) >= 2
            elif spec["sample_check"] == "oi_and_gamma_available":
                ok = int(item.get("oi_gamma_rows", 0)) > 0
            elif spec["sample_check"] == "atm_oi_and_expiry_available":
                ok = int(item.get("atm_oi_rows", 0)) > 0
            else:
                ok = False
            per_underlying[underlying] = ok
        feature_status[feature_id] = {
            "required_columns": sorted(required_columns),
            "missing_columns": missing_columns,
            "sample_check": spec["sample_check"],
            "external_dependency": spec.get("external_dependency"),
            "per_underlying_ready": per_underlying,
            "constructible_from_sample": not missing_columns and all(per_underlying.values()),
        }
    return feature_status


def analyze_options_chain_rows(
    rows: list[dict[str, str]],
    *,
    required_underlyings: list[str],
) -> dict[str, object]:
    columns = set(rows[0].keys()) if rows else set()
    column_coverage = {
        column: {
            "present": column in columns,
            "non_empty_ratio": _coverage_ratio(rows, column) if column in columns else 0.0,
        }
        for column in sorted(REQUIRED_COLUMNS | columns)
    }
    underlyings = Counter(_underlying_from_row(row) for row in rows)
    expiries_by_underlying = {}
    for underlying, group in _rows_by_underlying(rows).items():
        expiries_by_underlying[underlying] = len(
            {
                str(row.get("expiration"))
                for row in group
                if _non_empty(row.get("expiration"))
            }
        )

    feature_status = _feature_constructability(
        columns=columns,
        rows=rows,
        required_underlyings=required_underlyings,
    )
    missing_required_columns = sorted(REQUIRED_COLUMNS - columns)
    required_underlying_counts = {
        underlying: int(underlyings.get(underlying, 0))
        for underlying in required_underlyings
    }
    schema_ready = not missing_required_columns
    sample_required_underlyings_ready = all(
        count > 0 for count in required_underlying_counts.values()
    )
    all_features_constructible = all(
        bool(payload["constructible_from_sample"])
        for payload in feature_status.values()
    )
    phase0_ready = bool(
        rows
        and schema_ready
        and sample_required_underlyings_ready
        and all_features_constructible
    )
    return {
        "rows_sampled": len(rows),
        "schema_ready": schema_ready,
        "missing_required_columns": missing_required_columns,
        "timestamp_range": _timestamp_range(rows, "timestamp"),
        "local_timestamp_range": _timestamp_range(rows, "local_timestamp"),
        "underlying_row_counts": dict(sorted(underlyings.items())),
        "required_underlying_row_counts": required_underlying_counts,
        "expiries_by_underlying": expiries_by_underlying,
        "column_coverage": column_coverage,
        "sample_checks_by_underlying": _sample_checks(rows),
        "feature_constructability": feature_status,
        "phase0_ready": phase0_ready,
        "feature_builder_allowed": phase0_ready,
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _build_report(
    *,
    as_of: str,
    probe_input: ProbeInput,
    credential_debug: dict[str, object],
    analysis: dict[str, object],
    mode: str,
    auth_check: dict[str, object] | None = None,
    auth_candidate_checks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    authenticated_key_accepted = (
        bool(auth_check.get("accepted")) if auth_check is not None else None
    )
    feature_builder_allowed = bool(analysis.get("feature_builder_allowed"))
    if mode == "online":
        feature_builder_allowed = feature_builder_allowed and bool(authenticated_key_accepted)
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "as_of": as_of,
        "probe_mode": mode,
        "provider": "Tardis.dev",
        "exchange": "deribit",
        "data_type": "options_chain",
        "grouped_symbol": "OPTIONS",
        "source_boundary": "read_only_dataset_stream_sample_no_raw_vendor_rows_retained",
        "credential_readback": credential_debug,
        "auth_check": auth_check,
        "auth_candidate_checks": auth_candidate_checks or [],
        "input": {
            "source": probe_input.source,
            "url": probe_input.url,
            "http_status": probe_input.http_status,
            "sample_date": probe_input.sample_date,
            "rows_read": probe_input.rows_read,
        },
        "analysis": analysis,
        "phase0_decision": {
            "provider_data_accessed": probe_input.source in {"tardis_dataset", "local_fixture"},
            "provider_side_effects": "none_expected_read_only_http_get",
            "raw_sample_retained": False,
            "manifest_mutation_authorized": False,
            "authenticated_key_accepted": authenticated_key_accepted,
            "feature_builder_allowed": feature_builder_allowed,
            "m3_1_tardis_options_surface_phase0_ready": feature_builder_allowed,
            "next_allowed_step": (
                "options_surface_feature_builder_preregistration"
                if feature_builder_allowed
                else "fix_tardis_access_or_schema_coverage_before_feature_builder"
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe Tardis Deribit options_chain coverage for M3.1 F56-F60."
    )
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--sample-date", default=DEFAULT_SAMPLE_DATE, type=_parse_iso_date)
    parser.add_argument("--max-rows", type=int, default=50_000)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--required-underlyings",
        nargs="+",
        default=["BTC", "ETH"],
        help="Underlying set required before Phase 0 can pass.",
    )
    parser.add_argument(
        "--input-csv-gz",
        type=Path,
        help="Local gzipped options_chain CSV fixture; skips network and API-key requirement.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Write a specs-only failed report without making network calls.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    if args.max_rows <= 0:
        raise SystemExit("--max-rows must be positive")

    sample_date = args.sample_date.isoformat()
    required_underlyings = [value.upper() for value in args.required_underlyings]
    api_key, credential_debug, credential_candidates = _resolve_tardis_key()
    mode = "offline" if args.offline else "local_fixture" if args.input_csv_gz else "online"
    out_path = args.output_dir / args.as_of / "m3_1_tardis_deribit_options_surface_probe.json"
    auth_check: dict[str, object] | None = None
    auth_candidate_checks: list[dict[str, object]] = []

    try:
        if args.input_csv_gz:
            rows, probe_input = _iter_csv_rows_from_gzip_file(args.input_csv_gz, args.max_rows)
        elif args.offline:
            rows = []
            probe_input = ProbeInput(
                source="offline_specs_only",
                url=_dataset_url(sample_date),
                http_status=None,
                sample_date=sample_date,
                rows_read=0,
            )
        else:
            if not api_key:
                rows = []
                probe_input = ProbeInput(
                    source="missing_credentials",
                    url=_dataset_url(sample_date),
                    http_status=None,
                    sample_date=sample_date,
                    rows_read=0,
                )
                analysis = analyze_options_chain_rows(rows, required_underlyings=required_underlyings)
                report = _build_report(
                    as_of=args.as_of,
                    probe_input=probe_input,
                    credential_debug=credential_debug,
                    analysis=analysis,
                    mode=mode,
                    auth_check=auth_check,
                    auth_candidate_checks=auth_candidate_checks,
                )
                report["phase0_decision"]["credential_blocker"] = "Tardis API key missing"
                _write_report(out_path, report)
                print(f"missing Tardis API key; report written to {out_path}")
                return 1
            accepted_candidate: CredentialCandidate | None = None
            for candidate in credential_candidates:
                candidate_check = _check_tardis_api_key_info(
                    api_key=candidate.value,
                    timeout_seconds=args.timeout_seconds,
                )
                candidate_check["env_var"] = candidate.env_var
                candidate_check["scope"] = candidate.scope
                candidate_check["value_length"] = len(candidate.value)
                candidate_check["normalization"] = candidate.normalization
                auth_candidate_checks.append(candidate_check)
                if candidate_check.get("accepted"):
                    auth_check = candidate_check
                    accepted_candidate = candidate
                    break
            if accepted_candidate is not None:
                api_key = accepted_candidate.value
                credential_debug["selected_env_var"] = accepted_candidate.env_var
                credential_debug["selected_scope"] = accepted_candidate.scope
                credential_debug["selected_value_length"] = len(accepted_candidate.value)
            elif auth_candidate_checks:
                auth_check = auth_candidate_checks[0]
            if not auth_check.get("accepted"):
                rows = []
                probe_input = ProbeInput(
                    source="auth_check_failed",
                    url=_dataset_url(sample_date),
                    http_status=None,
                    sample_date=sample_date,
                    rows_read=0,
                )
                analysis = analyze_options_chain_rows(rows, required_underlyings=required_underlyings)
                report = _build_report(
                    as_of=args.as_of,
                    probe_input=probe_input,
                    credential_debug=credential_debug,
                    analysis=analysis,
                    mode=mode,
                    auth_check=auth_check,
                    auth_candidate_checks=auth_candidate_checks,
                )
                report["phase0_decision"]["credential_blocker"] = "Tardis api-key-info rejected key"
                _write_report(out_path, report)
                print(f"Tardis API key rejected; report written to {out_path}")
                return 1
            rows, probe_input = _iter_csv_rows_from_tardis(
                api_key=api_key,
                sample_date=sample_date,
                max_rows=args.max_rows,
                timeout_seconds=args.timeout_seconds,
            )
    except Exception as exc:  # noqa: BLE001
        rows = []
        probe_input = ProbeInput(
            source="probe_exception",
            url=_dataset_url(sample_date),
            http_status=None,
            sample_date=sample_date,
            rows_read=0,
        )
        analysis = analyze_options_chain_rows(rows, required_underlyings=required_underlyings)
        report = _build_report(
            as_of=args.as_of,
            probe_input=probe_input,
            credential_debug=credential_debug,
            analysis=analysis,
            mode=mode,
            auth_check=auth_check,
            auth_candidate_checks=auth_candidate_checks,
        )
        report["phase0_decision"]["probe_exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        _write_report(out_path, report)
        print(f"probe failed closed; report written to {out_path}")
        return 1

    analysis = analyze_options_chain_rows(rows, required_underlyings=required_underlyings)
    report = _build_report(
        as_of=args.as_of,
        probe_input=probe_input,
        credential_debug=credential_debug,
        analysis=analysis,
        mode=mode,
        auth_check=auth_check,
        auth_candidate_checks=auth_candidate_checks,
    )
    _write_report(out_path, report)

    print("=== Tardis Deribit options surface Phase 0 probe ===")
    print(f"  mode: {mode}")
    print(f"  sample_date: {probe_input.sample_date}")
    print(f"  rows_sampled: {analysis['rows_sampled']}")
    print(f"  schema_ready: {analysis['schema_ready']}")
    print(f"  phase0_ready: {analysis['phase0_ready']}")
    print(f"  feature_builder_allowed: {analysis['feature_builder_allowed']}")
    print(f"  report: {out_path}")
    return 0 if analysis["phase0_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
