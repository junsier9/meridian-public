from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import re
from typing import Any, Callable

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from scripts.market_data.binance_ohlcv import resolve_external_history_root

from .contracts import (
    PIT_SELECTION_METRIC,
    PIT_SELECTION_WINDOW_BARS,
    QUANT_UNIVERSE_DEFINITION_ID,
    QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
    TOP_100_LIMIT,
    liquidity_bucket_for_rank,
    portable_path,
    utc_now,
    write_json,
)
from .data_readiness import resolve_default_spot_ohlcv_external_root
from .market_data import load_ohlcv_frame


ROOT = Path(__file__).resolve().parents[3]
QUANT_ARTIFACTS_ROOT = ROOT / "artifacts" / "quant_research"
QUANT_INPUT_ROOT = QUANT_ARTIFACTS_ROOT / "_quant_inputs"
DEFAULT_TARGET_CANDIDATE_COUNT = TOP_100_LIMIT
VALID_SUBJECT_PATTERN = re.compile(r"^[A-Z0-9]+$")
VALID_MARKET_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+USDT$")
KNOWN_STABLECOIN_SYMBOLS = frozenset(
    {
        "USDT",
        "USDC",
        "BUSD",
        "FDUSD",
        "TUSD",
        "DAI",
        "USDE",
        "USDS",
        "PYUSD",
        "USDP",
        "GUSD",
        "FRAX",
        "EURS",
        "EURC",
        "LUSD",
        "SUSD",
        "MIM",
    }
)
KNOWN_PEGGED_SYMBOLS = frozenset(
    {
        "WBTC",
        "BTCB",
        "STBTC",
        "LBTC",
        "HBTC",
        "RENBTC",
        "CBBTC",
    }
)


def resolve_spot_ohlcv_root(
    *,
    external_root: Path | None = None,
) -> Path:
    if external_root is not None:
        return external_root.expanduser().resolve()
    resolved = resolve_default_spot_ohlcv_external_root(spot_ohlcv_external_root=None)
    if resolved is None:
        raise FileNotFoundError(
            "CoinAPI spot OHLCV root not found; provide spot_ohlcv_external_root explicitly "
            "before building the PIT liquidity universe"
        )
    return resolved.expanduser().resolve()


def resolve_perp_ohlcv_root(
    *,
    external_root: Path | None = None,
) -> Path:
    return resolve_external_history_root(external_root=external_root)


def _selection_cutoff_end_ms(as_of: str) -> int:
    as_of_date = date.fromisoformat(as_of)
    cutoff_date = as_of_date - timedelta(days=1)
    cutoff = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 23, 59, 59, tzinfo=UTC)
    return int(cutoff.timestamp() * 1000)


def _utc_from_ms(timestamp_ms: int | float | None) -> str | None:
    if timestamp_ms in {None, ""}:
        return None
    try:
        normalized = int(timestamp_ms)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(normalized / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _has_valid_subject(value: str) -> bool:
    normalized = str(value).strip().upper()
    return bool(normalized) and bool(VALID_SUBJECT_PATTERN.fullmatch(normalized))


def _has_valid_market_symbol(value: str | None) -> bool:
    if value is None:
        return True
    normalized = str(value).strip().upper()
    return bool(normalized) and bool(VALID_MARKET_SYMBOL_PATTERN.fullmatch(normalized))


def _is_stablecoin(symbol: str) -> bool:
    return str(symbol).strip().upper() in KNOWN_STABLECOIN_SYMBOLS


def _is_pegged_asset(symbol: str) -> bool:
    return str(symbol).strip().upper() in KNOWN_PEGGED_SYMBOLS


def _discover_spot_symbols(*, external_root: Path) -> list[str]:
    spot_root = external_root / "spot"
    if not spot_root.exists():
        return []
    symbols = {
        path.parent.parent.name.upper()
        for path in spot_root.glob("*/1d/manifest.json")
    }
    if symbols:
        return sorted(symbols)
    return sorted(
        path.name.upper()
        for path in spot_root.iterdir()
        if path.is_dir() and (path / "1d").exists()
    )


def _subject_from_spot_symbol(symbol: str) -> str | None:
    normalized = str(symbol).strip().upper()
    if not normalized.endswith("USDT") or len(normalized) <= 4:
        return None
    subject = normalized[:-4]
    return subject if _has_valid_subject(subject) else None


def _manifest_path(*, external_root: Path, market_type: str, symbol: str, interval: str) -> Path:
    return external_root / market_type / symbol / interval / "manifest.json"


def _partition_paths_for_window(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
    interval: str,
    open_time_values: list[int],
) -> list[str]:
    roots = external_root / market_type / symbol / interval
    partitions = {
        portable_path(roots / f"{datetime.fromtimestamp(value / 1000, tz=UTC):%Y-%m}.csv.gz", repo_root=ROOT)
        for value in open_time_values
    }
    return sorted(partitions)


def _first_local_bar_utc(
    *,
    external_root: Path,
    market_type: str,
    symbol: str,
) -> str | None:
    for interval in ("1d", "4h", "1h"):
        frame = load_ohlcv_frame(
            symbol=symbol,
            market_type=market_type,
            interval=interval,
            external_root=external_root,
            end_time_ms=int(datetime(2100, 1, 1, tzinfo=UTC).timestamp() * 1000),
        )
        if frame.empty:
            continue
        return _utc_from_ms(frame["open_time_ms"].min())
    return None


def _listing_age_days_as_of(*, as_of: str, first_spot_bar_utc: str) -> int:
    first_date = datetime.fromisoformat(first_spot_bar_utc.replace("Z", "+00:00")).date()
    as_of_date = date.fromisoformat(as_of)
    return max((as_of_date - first_date).days, 1)


def _selection_policy() -> dict[str, Any]:
    return {
        "contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
        "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
        "selection_market_type": "spot",
        "selection_interval": "1d",
        "selection_metric": PIT_SELECTION_METRIC,
        "selection_window_bars": PIT_SELECTION_WINDOW_BARS,
        "selection_cutoff_rule": "as_of_uses_fully_closed_bars_through_d_minus_1",
        "tie_breakers": [
            "rolling_mean_quote_volume_usd_30d_desc",
            "subject_asc",
        ],
        "eligibility_requirements": [
            "valid_subject_symbol",
            "valid_spot_symbol",
            "non_stablecoin",
            "non_pegged_asset",
            "local_spot_1d_history_present",
            "minimum_30_closed_spot_1d_bars",
        ],
        "target_candidate_count": DEFAULT_TARGET_CANDIDATE_COUNT,
    }


def run_quant_universe_input_producer(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    perp_ohlcv_external_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    coingecko_http_get_json_fn: Callable[[str], Any] | None = None,
    binance_http_get_json_fn: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    del coingecko_http_get_json_fn
    del binance_http_get_json_fn
    if ohlcv_external_root is not None:
        raise ValueError(
            "single-root ohlcv_external_root has been retired; use "
            "spot_ohlcv_external_root and perp_ohlcv_external_root"
        )
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_spot_root = resolve_spot_ohlcv_root(external_root=spot_ohlcv_external_root)
    resolved_perp_root = resolve_perp_ohlcv_root(external_root=perp_ohlcv_external_root)
    selection_end_ms = _selection_cutoff_end_ms(as_of)
    selection_policy = _selection_policy()

    candidates: list[dict[str, Any]] = []
    exclusion_counts: dict[str, int] = {}
    discovered_spot_symbols = _discover_spot_symbols(external_root=resolved_spot_root)

    for spot_symbol in discovered_spot_symbols:
        subject = _subject_from_spot_symbol(spot_symbol)
        if not subject:
            exclusion_counts["invalid_subject_or_symbol"] = exclusion_counts.get("invalid_subject_or_symbol", 0) + 1
            continue
        if _is_stablecoin(subject):
            exclusion_counts["stablecoin"] = exclusion_counts.get("stablecoin", 0) + 1
            continue
        if _is_pegged_asset(subject):
            exclusion_counts["pegged_asset"] = exclusion_counts.get("pegged_asset", 0) + 1
            continue
        if not _has_valid_market_symbol(spot_symbol):
            exclusion_counts["invalid_spot_symbol"] = exclusion_counts.get("invalid_spot_symbol", 0) + 1
            continue
        spot_frame = load_ohlcv_frame(
            symbol=spot_symbol,
            market_type="spot",
            interval="1d",
            external_root=resolved_spot_root,
            end_time_ms=selection_end_ms,
        )
        if spot_frame.empty:
            exclusion_counts["missing_spot_history"] = exclusion_counts.get("missing_spot_history", 0) + 1
            continue
        if len(spot_frame) < PIT_SELECTION_WINDOW_BARS:
            exclusion_counts["insufficient_spot_1d_bars"] = exclusion_counts.get("insufficient_spot_1d_bars", 0) + 1
            continue
        window = spot_frame.sort_values("open_time_ms").tail(PIT_SELECTION_WINDOW_BARS).copy()
        if window["quote_volume"].isna().all():
            exclusion_counts["missing_quote_volume"] = exclusion_counts.get("missing_quote_volume", 0) + 1
            continue
        window_quote_volume = [float(value) for value in window["quote_volume"].fillna(0.0).tolist()]
        selection_score = float(window["quote_volume"].median())
        rolling_mean = float(window["quote_volume"].mean())
        if selection_score <= 0.0 or rolling_mean <= 0.0:
            exclusion_counts["non_positive_quote_volume"] = exclusion_counts.get("non_positive_quote_volume", 0) + 1
            continue
        first_spot_bar_utc = _utc_from_ms(int(spot_frame["open_time_ms"].min()))
        if first_spot_bar_utc is None:
            exclusion_counts["missing_first_spot_bar"] = exclusion_counts.get("missing_first_spot_bar", 0) + 1
            continue
        perp_symbol = f"{subject}USDT"
        first_perp_bar_utc = _first_local_bar_utc(
            external_root=resolved_perp_root,
            market_type="usdm_perp",
            symbol=perp_symbol,
        )
        usdm_symbol = perp_symbol if first_perp_bar_utc else None
        field_provenance = {
            "subject": {
                "source": "local_spot_history",
                "derivation": "spot_symbol_without_usdt_suffix",
                "spot_symbol": spot_symbol,
            },
            "spot_symbol": {
                "source": "local_spot_history",
                "market_type": "spot",
                "interval": "1d",
                "manifest_path": portable_path(
                    _manifest_path(external_root=resolved_spot_root, market_type="spot", symbol=spot_symbol, interval="1d"),
                    repo_root=ROOT,
                ),
            },
            "selection_metric": {
                "source": "local_spot_history",
                "column": "quote_volume",
                "market_type": "spot",
                "interval": "1d",
                "aggregation": "median_30d",
                "window_partition_paths": _partition_paths_for_window(
                    external_root=resolved_spot_root,
                    market_type="spot",
                    symbol=spot_symbol,
                    interval="1d",
                    open_time_values=[int(value) for value in window["open_time_ms"].tolist()],
                ),
            },
            "rolling_mean_quote_volume_usd_30d": {
                "source": "local_spot_history",
                "column": "quote_volume",
                "market_type": "spot",
                "interval": "1d",
                "aggregation": "mean_30d",
            },
            "listing_age_days_as_of": {
                "source": "local_spot_history",
                "field": "open_time_ms",
                "market_type": "spot",
                "interval": "1d",
            },
            "first_spot_bar_utc": {
                "source": "local_spot_history",
                "market_type": "spot",
                "interval": "1d",
            },
            "usdm_symbol": {
                "source": "local_perp_history",
                "market_type": "usdm_perp",
                "interval_preference": ["1d", "4h", "1h"],
                "symbol": usdm_symbol,
                "present_as_of": bool(usdm_symbol),
            },
            "first_perp_bar_utc": {
                "source": "local_perp_history",
                "market_type": "usdm_perp",
                "interval_preference": ["1d", "4h", "1h"],
                "symbol": usdm_symbol,
                "present_as_of": bool(first_perp_bar_utc),
            },
        }
        if usdm_symbol:
            field_provenance["usdm_symbol"]["manifest_path"] = portable_path(
                _manifest_path(external_root=resolved_perp_root, market_type="usdm_perp", symbol=usdm_symbol, interval="1d"),
                repo_root=ROOT,
            )
        candidates.append(
            {
                "subject": subject,
                "spot_symbol": spot_symbol,
                "usdm_symbol": usdm_symbol,
                "selection_rank": 0,
                "selection_score": selection_score,
                "selection_metric": PIT_SELECTION_METRIC,
                "selection_window_start_utc": _utc_from_ms(int(window["open_time_ms"].min())),
                "selection_window_end_utc": _utc_from_ms(int(window["close_time_ms"].max())),
                "rolling_median_quote_volume_usd_30d": selection_score,
                "rolling_mean_quote_volume_usd_30d": rolling_mean,
                "listing_age_days_as_of": _listing_age_days_as_of(as_of=as_of, first_spot_bar_utc=first_spot_bar_utc),
                "first_spot_bar_utc": first_spot_bar_utc,
                "first_perp_bar_utc": first_perp_bar_utc,
                "liquidity_bucket": None,
                "is_stablecoin": False,
                "is_pegged_asset": False,
                "field_provenance": field_provenance,
            }
        )

    ranked_candidates = sorted(
        candidates,
        key=lambda item: (
            -float(item["selection_score"]),
            -float(item["rolling_mean_quote_volume_usd_30d"]),
            str(item["subject"]),
        ),
    )[:DEFAULT_TARGET_CANDIDATE_COUNT]
    for index, candidate in enumerate(ranked_candidates, start=1):
        candidate["selection_rank"] = index
        candidate["liquidity_bucket"] = liquidity_bucket_for_rank(index)

    if not ranked_candidates:
        raise RuntimeError(
            "no PIT liquidity universe candidates were produced from local history; "
            f"checked spot_root={resolved_spot_root}"
        )

    payload = {
        "as_of": as_of,
        "generated_at_utc": utc_now(),
        "contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
        "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
        "selection_policy": selection_policy,
        "candidate_count_target": DEFAULT_TARGET_CANDIDATE_COUNT,
        "candidate_count_effective": len(ranked_candidates),
        "top100_complete": len(ranked_candidates) >= DEFAULT_TARGET_CANDIDATE_COUNT,
        "input_provenance": {
            "mode": "offline_local_history_only",
            "selection_end_utc": _utc_from_ms(selection_end_ms),
            "spot_history_root": portable_path(resolved_spot_root, repo_root=ROOT),
            "perp_history_root": portable_path(resolved_perp_root, repo_root=ROOT),
            "spot_history_provider": "coinapi",
            "perp_history_provider": "binance",
            "spot_symbol_count_discovered": len(discovered_spot_symbols),
            "legacy_http_inputs_ignored": True,
        },
        "candidates": ranked_candidates,
    }
    quant_input_path = resolved_quant_input_root / f"pit-liquidity-top100-{as_of}.quant_universe.json"
    write_json(quant_input_path, payload)

    summary = with_evidence_metadata(
        {
            "status": "success",
            "success": True,
            "generated_at_utc": utc_now(),
            "as_of": as_of,
            "quant_input_path": str(quant_input_path),
            "contract_version": QUANT_UNIVERSE_INPUT_CONTRACT_VERSION,
            "universe_definition_id": QUANT_UNIVERSE_DEFINITION_ID,
            "target_candidate_count": DEFAULT_TARGET_CANDIDATE_COUNT,
            "candidate_count": len(ranked_candidates),
            "top100_complete": len(ranked_candidates) >= DEFAULT_TARGET_CANDIDATE_COUNT,
            "candidates_with_perp_count": sum(1 for item in ranked_candidates if item.get("usdm_symbol")),
            "excluded_count": sum(exclusion_counts.values()),
            "exclusion_counts": exclusion_counts,
            "sample_subjects": [item["subject"] for item in ranked_candidates[:10]],
            "input_watermarks": {
                "selection_end_utc": _utc_from_ms(selection_end_ms),
                "spot_history_root": portable_path(resolved_spot_root, repo_root=ROOT),
                "perp_history_root": portable_path(resolved_perp_root, repo_root=ROOT),
                "spot_symbol_count_discovered": len(discovered_spot_symbols),
                "spot_candidate_count_scored": len(candidates),
            },
            "upstream_versions": {
                "selection_metric": PIT_SELECTION_METRIC,
                "selection_window_bars": PIT_SELECTION_WINDOW_BARS,
                "target_candidate_count": DEFAULT_TARGET_CANDIDATE_COUNT,
            },
        },
        evidence_family="quant_universe_input_producer",
        contract_version="quant_universe_input_producer.v3",
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    summary_path = resolved_artifacts_root / "cycles" / as_of / "quant_universe_input_producer_summary.json"
    write_json(summary_path, summary)
    summary["quant_universe_input_producer_summary_path"] = str(summary_path)
    return summary
