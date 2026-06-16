from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]


STRATEGY_PROFILES = ("conservative", "balanced", "aggressive")
LIQUIDITY_BUCKETS = ("top_liquidity", "mid_liquidity", "tail_liquidity")
QUANT_UNIVERSE_INPUT_CONTRACT_VERSION = "quant_universe_input.v2"
QUANT_UNIVERSE_DEFINITION_ID = "pit_binance_liquidity_top100"
PIT_SELECTION_METRIC = "rolling_median_quote_volume_usd_30d"
PIT_SELECTION_WINDOW_BARS = 30
TOP_100_LIMIT = 100
PIT_UNIVERSE_ARTIFACT_REQUIRED_FIELDS = (
    "universe_definition_id",
    "universe_contract_version",
    "universe_snapshot_path",
    "universe_selection_policy_hash",
)
QUANT_REQUIRED_FIELDS = (
    "subject",
    "spot_symbol",
    "selection_rank",
    "selection_score",
    "selection_metric",
    "selection_window_start_utc",
    "selection_window_end_utc",
    "rolling_median_quote_volume_usd_30d",
    "rolling_mean_quote_volume_usd_30d",
    "listing_age_days_as_of",
    "first_spot_bar_utc",
    "liquidity_bucket",
    "is_stablecoin",
    "is_pegged_asset",
    "field_provenance",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def portable_path(path: Path | str, *, repo_root: Path | None = None) -> str:
    candidate = Path(path).expanduser().resolve()
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    try:
        return candidate.relative_to(resolved_repo_root).as_posix()
    except ValueError:
        return str(candidate)


def resolve_portable_path(path_ref: str | Path, *, repo_root: Path | None = None) -> Path:
    candidate = Path(path_ref).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    return (resolved_repo_root / candidate).resolve()


def sha256_canonical_json(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def slugify(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "item"


def require_non_empty_string(value: Any, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def require_positive_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return number


def require_positive_float(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive number") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return number


def require_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in {0, 1, "0", "1"}:
        return bool(int(value))
    raise ValueError(f"{field_name} must be a boolean")


def optional_symbol(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def optional_utc_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def normalize_json_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return {str(key): _normalize_json_value(item) for key, item in value.items()}


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, set):
        return [_normalize_json_value(item) for item in sorted(value)]
    return value


def liquidity_bucket_for_rank(rank: int) -> str | None:
    if 1 <= rank <= 20:
        return "top_liquidity"
    if 21 <= rank <= 50:
        return "mid_liquidity"
    if 51 <= rank <= TOP_100_LIMIT:
        return "tail_liquidity"
    return None


def pit_universe_artifact_metadata(payload: dict[str, Any] | None) -> dict[str, str]:
    resolved = dict(payload or {})
    return {
        "universe_definition_id": str(resolved.get("universe_definition_id") or "").strip(),
        "universe_contract_version": str(resolved.get("universe_contract_version") or "").strip(),
        "universe_snapshot_path": str(resolved.get("universe_snapshot_path") or "").strip(),
        "universe_selection_policy_hash": str(resolved.get("universe_selection_policy_hash") or "").strip(),
    }


def pit_universe_artifact_is_valid(payload: dict[str, Any] | None) -> bool:
    metadata = pit_universe_artifact_metadata(payload)
    return (
        metadata["universe_definition_id"] == QUANT_UNIVERSE_DEFINITION_ID
        and metadata["universe_contract_version"] == QUANT_UNIVERSE_INPUT_CONTRACT_VERSION
        and bool(metadata["universe_snapshot_path"])
        and bool(metadata["universe_selection_policy_hash"])
    )


def profile_constraints(strategy_profile: str) -> dict[str, Any]:
    if strategy_profile not in STRATEGY_PROFILES:
        raise ValueError(f"unsupported strategy_profile: {strategy_profile}")
    if strategy_profile == "conservative":
        return {
            "allowed_liquidity_buckets": {"top_liquidity"},
            "spot_only": True,
            "short_allowed": False,
            "long_only": True,
            "max_gross_leverage": 1.0,
            "long_leverage": 1.0,
            "short_leverage": 0.0,
            "max_turnover_per_rebalance": 1.0,
        }
    if strategy_profile == "balanced":
        return {
            "allowed_liquidity_buckets": {"top_liquidity", "mid_liquidity"},
            "spot_only": False,
            "short_allowed": True,
            "long_only": False,
            "max_gross_leverage": 1.5,
            "long_leverage": 1.0,
            "short_leverage": 0.5,
            "max_turnover_per_rebalance": 1.5,
        }
    return {
        "allowed_liquidity_buckets": {"top_liquidity", "mid_liquidity", "tail_liquidity"},
        "spot_only": False,
        "short_allowed": True,
        "long_only": False,
        "max_gross_leverage": 2.5,
        "long_leverage": 1.5,
        "short_leverage": 1.0,
        "max_turnover_per_rebalance": 2.5,
    }


@dataclass(frozen=True, slots=True)
class QuantUniverseCandidate:
    subject: str
    spot_symbol: str
    usdm_symbol: str | None
    selection_rank: int
    selection_score: float
    selection_metric: str
    selection_window_start_utc: str
    selection_window_end_utc: str
    rolling_median_quote_volume_usd_30d: float
    rolling_mean_quote_volume_usd_30d: float
    listing_age_days_as_of: int
    first_spot_bar_utc: str
    first_perp_bar_utc: str | None
    liquidity_bucket: str
    is_stablecoin: bool
    is_pegged_asset: bool
    field_provenance: dict[str, Any]

    @property
    def listing_age_days(self) -> int:
        return self.listing_age_days_as_of

    @property
    def has_perp_as_of(self) -> bool:
        return bool(self.usdm_symbol and self.first_perp_bar_utc)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "QuantUniverseCandidate":
        if not isinstance(payload, dict):
            raise ValueError("candidate must be a JSON object")
        if "market_cap_rank" in payload or "market_cap_usd" in payload or "quote_volume_24h_usd" in payload:
            raise ValueError("legacy quant universe candidate payload detected; rebuild PIT liquidity universe v2 input")
        for field_name in QUANT_REQUIRED_FIELDS:
            if field_name not in payload:
                raise ValueError(f"candidate missing required field: {field_name}")
        selection_rank = require_positive_int(payload.get("selection_rank"), "candidate.selection_rank")
        liquidity_bucket = require_non_empty_string(payload.get("liquidity_bucket"), "candidate.liquidity_bucket")
        expected_bucket = liquidity_bucket_for_rank(selection_rank)
        if liquidity_bucket != expected_bucket:
            raise ValueError(
                "candidate.liquidity_bucket does not match candidate.selection_rank: "
                f"{liquidity_bucket} vs {expected_bucket}"
            )
        selection_metric = require_non_empty_string(payload.get("selection_metric"), "candidate.selection_metric")
        if selection_metric != PIT_SELECTION_METRIC:
            raise ValueError(f"unsupported candidate.selection_metric: {selection_metric}")
        return cls(
            subject=require_non_empty_string(payload.get("subject"), "candidate.subject").upper(),
            spot_symbol=require_non_empty_string(payload.get("spot_symbol"), "candidate.spot_symbol").upper(),
            usdm_symbol=optional_symbol(payload.get("usdm_symbol")),
            selection_rank=selection_rank,
            selection_score=require_positive_float(payload.get("selection_score"), "candidate.selection_score"),
            selection_metric=selection_metric,
            selection_window_start_utc=require_non_empty_string(
                payload.get("selection_window_start_utc"),
                "candidate.selection_window_start_utc",
            ),
            selection_window_end_utc=require_non_empty_string(
                payload.get("selection_window_end_utc"),
                "candidate.selection_window_end_utc",
            ),
            rolling_median_quote_volume_usd_30d=require_positive_float(
                payload.get("rolling_median_quote_volume_usd_30d"),
                "candidate.rolling_median_quote_volume_usd_30d",
            ),
            rolling_mean_quote_volume_usd_30d=require_positive_float(
                payload.get("rolling_mean_quote_volume_usd_30d"),
                "candidate.rolling_mean_quote_volume_usd_30d",
            ),
            listing_age_days_as_of=require_positive_int(
                payload.get("listing_age_days_as_of"),
                "candidate.listing_age_days_as_of",
            ),
            first_spot_bar_utc=require_non_empty_string(payload.get("first_spot_bar_utc"), "candidate.first_spot_bar_utc"),
            first_perp_bar_utc=optional_utc_string(payload.get("first_perp_bar_utc")),
            liquidity_bucket=liquidity_bucket,
            is_stablecoin=require_bool(payload.get("is_stablecoin"), "candidate.is_stablecoin"),
            is_pegged_asset=require_bool(payload.get("is_pegged_asset"), "candidate.is_pegged_asset"),
            field_provenance=normalize_json_mapping(payload.get("field_provenance"), "candidate.field_provenance"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "spot_symbol": self.spot_symbol,
            "usdm_symbol": self.usdm_symbol,
            "selection_rank": self.selection_rank,
            "selection_score": self.selection_score,
            "selection_metric": self.selection_metric,
            "selection_window_start_utc": self.selection_window_start_utc,
            "selection_window_end_utc": self.selection_window_end_utc,
            "rolling_median_quote_volume_usd_30d": self.rolling_median_quote_volume_usd_30d,
            "rolling_mean_quote_volume_usd_30d": self.rolling_mean_quote_volume_usd_30d,
            "listing_age_days_as_of": self.listing_age_days_as_of,
            "first_spot_bar_utc": self.first_spot_bar_utc,
            "first_perp_bar_utc": self.first_perp_bar_utc,
            "liquidity_bucket": self.liquidity_bucket,
            "is_stablecoin": self.is_stablecoin,
            "is_pegged_asset": self.is_pegged_asset,
            "field_provenance": normalize_json_mapping(self.field_provenance, "candidate.field_provenance"),
        }


@dataclass(frozen=True, slots=True)
class QuantUniverseInput:
    as_of: str
    generated_at_utc: str | None
    contract_version: str
    universe_definition_id: str
    selection_policy: dict[str, Any]
    candidate_count_target: int
    candidate_count_effective: int
    top100_complete: bool
    input_provenance: dict[str, Any]
    candidates: tuple[QuantUniverseCandidate, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "QuantUniverseInput":
        if not isinstance(payload, dict):
            raise ValueError("quant universe input must be a JSON object")
        contract_version = require_non_empty_string(payload.get("contract_version"), "contract_version")
        if contract_version != QUANT_UNIVERSE_INPUT_CONTRACT_VERSION:
            raise ValueError(
                "unsupported quant universe input contract_version: "
                f"{contract_version}; expected {QUANT_UNIVERSE_INPUT_CONTRACT_VERSION}"
            )
        universe_definition_id = require_non_empty_string(
            payload.get("universe_definition_id"),
            "universe_definition_id",
        )
        if universe_definition_id != QUANT_UNIVERSE_DEFINITION_ID:
            raise ValueError(
                "unsupported quant universe definition: "
                f"{universe_definition_id}; expected {QUANT_UNIVERSE_DEFINITION_ID}"
            )
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise ValueError("quant universe input must include a non-empty candidates array")
        candidates = tuple(QuantUniverseCandidate.from_payload(item) for item in raw_candidates)
        candidate_count_target = require_positive_int(
            payload.get("candidate_count_target"),
            "candidate_count_target",
        )
        candidate_count_effective = require_positive_int(
            payload.get("candidate_count_effective"),
            "candidate_count_effective",
        )
        if candidate_count_effective != len(candidates):
            raise ValueError(
                "candidate_count_effective does not match candidates length: "
                f"{candidate_count_effective} vs {len(candidates)}"
            )
        return cls(
            as_of=require_non_empty_string(payload.get("as_of"), "as_of"),
            generated_at_utc=str(payload.get("generated_at_utc", "")).strip() or None,
            contract_version=contract_version,
            universe_definition_id=universe_definition_id,
            selection_policy=normalize_json_mapping(payload.get("selection_policy"), "selection_policy"),
            candidate_count_target=candidate_count_target,
            candidate_count_effective=candidate_count_effective,
            top100_complete=bool(payload.get("top100_complete")),
            input_provenance=normalize_json_mapping(payload.get("input_provenance"), "input_provenance"),
            candidates=candidates,
        )

    def selected_candidates(self) -> tuple[QuantUniverseCandidate, ...]:
        ranked = sorted(
            self.candidates,
            key=lambda item: (
                item.selection_rank,
                -float(item.selection_score),
                -float(item.rolling_mean_quote_volume_usd_30d),
                item.subject,
            ),
        )
        if len(ranked) != self.candidate_count_effective:
            raise ValueError(
                "quant universe input candidates length does not match candidate_count_effective: "
                f"{len(ranked)} vs {self.candidate_count_effective}"
            )
        return tuple(ranked[: self.candidate_count_target])

    def filtered_top100(self) -> tuple[QuantUniverseCandidate, ...]:
        raise RuntimeError(
            "quant universe input v1 has been retired; use selected_candidates() with PIT liquidity universe v2 inputs"
        )

    @property
    def selection_policy_hash(self) -> str:
        return sha256_canonical_json(self.selection_policy)

    def to_payload(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "generated_at_utc": self.generated_at_utc,
            "contract_version": self.contract_version,
            "universe_definition_id": self.universe_definition_id,
            "selection_policy": normalize_json_mapping(self.selection_policy, "selection_policy"),
            "candidate_count_target": self.candidate_count_target,
            "candidate_count_effective": self.candidate_count_effective,
            "top100_complete": self.top100_complete,
            "input_provenance": normalize_json_mapping(self.input_provenance, "input_provenance"),
            "candidates": [candidate.to_payload() for candidate in self.selected_candidates()],
        }
