from __future__ import annotations

import pandas as pd

from scripts.quant_research.audit_mf05_venue_local_data_gate import (
    _compare_symbol,
    _decision,
    _summarize_sidecar,
)


def test_mf05_venue_gate_compare_symbol_computes_pct_diffs() -> None:
    native = pd.DataFrame(
        {
            "open_time_ms": [1, 2],
            "close": [100.0, 200.0],
            "quote_volume": [1000.0, 2000.0],
        }
    )
    coinapi = pd.DataFrame(
        {
            "open_time_ms": [1, 2],
            "close": [101.0, 198.0],
            "quote_volume": [900.0, 2500.0],
        }
    )

    actual = _compare_symbol(native, coinapi)

    assert actual["close_abs_pct_diff"].round(2).tolist() == [0.01, 0.01]
    assert actual["quote_volume_abs_pct_diff"].tolist() == [0.1, 0.25]


def test_mf05_venue_gate_decision_blocks_pre_concordance() -> None:
    sidecar = pd.DataFrame(
        {
            "subject": ["BTC", "ETH"],
            "timestamp_ms": [1, 2],
            "observed_venue_count": [1, 3],
            "data_trust_status": ["pre_concordance", "pre_concordance"],
            "research_validation_status": ["not_started", "not_started"],
        }
    )
    summary = _summarize_sidecar(sidecar)

    decision = _decision(
        sidecar_summary=summary,
        binance_concordance={"passed": False},
        native_multivenue={
            "okx_native": {"exists": False, "role": "native_concordance_source"},
            "coinapi_okex": {"exists": True, "role": "sidecar_input_source"},
        },
    )

    assert decision["alpha_rerun_allowed"] is False
    assert "sidecar_rows_pre_concordance" in decision["blocker_codes"]
    assert "missing_native_okx_bybit_coinbase_concordance_sources" in decision["blocker_codes"]
