from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from scripts.quant_research.provider_probes.probe_tardis_deribit_options_surface import (
    _normalize_tardis_key_value,
    analyze_options_chain_rows,
    main,
)


FIELDNAMES = [
    "exchange",
    "symbol",
    "timestamp",
    "local_timestamp",
    "type",
    "strike_price",
    "expiration",
    "open_interest",
    "last_price",
    "bid_price",
    "bid_amount",
    "bid_iv",
    "ask_price",
    "ask_amount",
    "ask_iv",
    "mark_price",
    "mark_iv",
    "underlying_index",
    "underlying_price",
    "delta",
    "gamma",
    "vega",
    "theta",
    "rho",
]


def _row(symbol: str, option_type: str, delta: float, expiration: int) -> dict[str, object]:
    under = symbol.split("-", 1)[0]
    return {
        "exchange": "deribit",
        "symbol": symbol,
        "timestamp": 1_717_200_000_000_000,
        "local_timestamp": 1_717_200_001_000_000,
        "type": option_type,
        "strike_price": 65000 if under == "BTC" else 3500,
        "expiration": expiration,
        "open_interest": 12.5,
        "last_price": 0.02,
        "bid_price": 0.019,
        "bid_amount": 1.0,
        "bid_iv": 62.0,
        "ask_price": 0.021,
        "ask_amount": 1.5,
        "ask_iv": 64.0,
        "mark_price": 0.02,
        "mark_iv": 63.0,
        "underlying_index": f"SYN.{under}-28JUN24",
        "underlying_price": 66000 if under == "BTC" else 3600,
        "delta": delta,
        "gamma": 0.0002,
        "vega": 1.2,
        "theta": -0.4,
        "rho": 0.01,
    }


def _fixture_rows() -> list[dict[str, object]]:
    return [
        _row("BTC-28JUN24-65000-C", "call", 0.25, 1_719_532_800_000_000),
        _row("BTC-28JUN24-65000-P", "put", -0.25, 1_719_532_800_000_000),
        _row("BTC-26JUL24-65000-C", "call", 0.50, 1_721_952_000_000_000),
        _row("BTC-30AUG24-65000-P", "put", -0.50, 1_724_976_000_000_000),
        _row("ETH-28JUN24-3500-C", "call", 0.25, 1_719_532_800_000_000),
        _row("ETH-28JUN24-3500-P", "put", -0.25, 1_719_532_800_000_000),
        _row("ETH-26JUL24-3500-C", "call", 0.50, 1_721_952_000_000_000),
        _row("ETH-30AUG24-3500-P", "put", -0.50, 1_724_976_000_000_000),
    ]


def _write_gzip_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_analyze_options_chain_rows_marks_f56_to_f60_constructible() -> None:
    rows = [{key: str(value) for key, value in row.items()} for row in _fixture_rows()]

    report = analyze_options_chain_rows(rows, required_underlyings=["BTC", "ETH"])

    assert report["schema_ready"] is True
    assert report["phase0_ready"] is True
    for feature in (
        "F56_25d_skew_residual",
        "F57_iv_rv_spread",
        "F58_iv_term_slope",
        "F59_dealer_gamma_proxy",
        "F60_vanna_charm_window",
    ):
        assert report["feature_constructability"][feature]["constructible_from_sample"] is True


def test_tardis_key_normalization_removes_common_copy_artifacts() -> None:
    normalized, mode = _normalize_tardis_key_value('  "Bearer abc\n123"  ')

    assert normalized == "abc123"
    assert mode == "strip_outer_quotes+remove_bearer_prefix+remove_embedded_whitespace"


def test_probe_writes_fixture_report_without_requiring_network_or_key(tmp_path: Path) -> None:
    fixture_path = tmp_path / "OPTIONS.csv.gz"
    _write_gzip_csv(fixture_path, _fixture_rows())
    output_dir = tmp_path / "reports"

    exit_code = main(
        [
            "--as-of",
            "2026-06-13",
            "--input-csv-gz",
            str(fixture_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    report_path = output_dir / "2026-06-13" / "m3_1_tardis_deribit_options_surface_probe.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["contract_version"] == "quant_m3_1_tardis_deribit_options_surface_probe.v1"
    assert payload["probe_mode"] == "local_fixture"
    assert payload["phase0_decision"]["raw_sample_retained"] is False
    assert payload["phase0_decision"]["m3_1_tardis_options_surface_phase0_ready"] is True
    assert payload["phase0_decision"]["feature_builder_allowed"] is True
