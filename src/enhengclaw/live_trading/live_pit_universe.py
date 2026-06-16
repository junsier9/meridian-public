"""live_pit_universe — resolve + apply the FROZEN, PIT-safe rolling top-N-by-quote-volume
live universe (DEFAULT-OFF), aligning the live path with the research selector
``apply_point_in_time_rolling_universe``.

Design contract (owner, 2026-06-10):
  * DEFAULT-OFF, BYTE-FOR-BYTE. The live selector is gated on a NEW explicit key
    ``universe_policy.live_selection_mode`` (default ``"fixed"``). It is deliberately
    NOT the research-provenance ``selection_mode`` field — that field already reads
    ``"rolling_quote_volume"`` in the pinned frozen config, and honouring it would
    silently flip live behaviour. With the new key absent/``"fixed"`` this module never
    re-marks the panel and the live universe stays the existing per-day cross-sectional
    top-N (i.e. the hand-pinned set) exactly.
  * PIT-SAFE, NO SURVIVORSHIP. The heavy lifting is the research
    ``apply_point_in_time_rolling_universe`` (trailing-window median quote volume +
    coverage gate + ``as_of`` cutoff). Candidates come ONLY from a hash-pinned
    operator allowlist (``universe_policy.candidate_symbols``); there is no dynamic
    exchange discovery, so a de-listed/added symbol cannot leak in.
  * SINGLE ALLOWLIST. ``candidate_symbols`` IS the operator-admitted set — to trade a new
    symbol the operator edits the hash-pinned frozen config (its re-pin is the operational
    gate). At runtime, any active ``usdm_symbol`` outside that allowlist fails closed
    (``new_symbol_not_admitted:<SYM>``) as defence-in-depth.
  * ANTI-CHURN HYSTERESIS, PANEL-INTERNAL. A deterministic carry-forward band is applied
    across the panel's OWN daily timestamps — no cross-run state, fully reproducible from
    ``(panel, as_of, policy)``. An incumbent is retained while it is still eligible and
    ranks within ``top_n + hysteresis_band``; final membership is still exactly ``top_n``.
  * SIZE INVARIANT (q90 coupling). With ``top_n == 20`` the active set cardinality is fixed
    at 20 (membership rolls), so the dth60 overlay q90 thresholds stay valid. The decision
    row is hard-asserted ``size == top_n`` else fail closed (``active_size_not_<top_n>``).
  * DETERMINISTIC + BINDABLE. The resolved universe is captured in ``live_universe.json``
    with a canonical ``universe_binding`` digest the executor can re-check against drift.

This module performs NO scoring and submits NO orders. It only resolves + marks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from enhengclaw.quant_research.binance_canonical_h10d import apply_point_in_time_rolling_universe
from enhengclaw.quant_research.contracts import write_json


UNIVERSE_POLICY_KEY = "universe_policy"
LIVE_SELECTION_MODE_KEY = "live_selection_mode"
LIVE_UNIVERSE_ARTIFACT = "live_universe.json"
LIVE_UNIVERSE_SCHEMA = "live_pit_universe.v1"
UNIVERSE_CHANGE_LOG_ARTIFACT = "universe_change_log.json"
UNIVERSE_CHANGE_LOG_SCHEMA = "live_pit_universe_change_log.v1"
PIT_SELECTION_RULE = "binance_perp_pit_rolling_quote_volume_hysteresis"

MODE_FIXED = "fixed"
MODE_PIT_ROLLING = "pit_rolling"

DEFAULT_TOP_N = 20
DEFAULT_COVERAGE_THRESHOLD = 0.85
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_HYSTERESIS_BAND = 0  # 0 => exactly the research pure-top-N selection (no churn band)

_REQUIRED_PANEL_COLUMNS = ("timestamp_ms", "subject", "usdm_symbol", "perp_close", "perp_quote_volume_usd")


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def universe_policy_config(frozen_config: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(frozen_config or {}).get(UNIVERSE_POLICY_KEY) or {})


def live_selection_mode(frozen_config: dict[str, Any]) -> str:
    """The live universe selector mode. ONLY an explicit ``pit_rolling`` opts in; anything
    else (incl. absent, or the research ``selection_mode`` value) resolves to ``fixed``."""
    raw = str(universe_policy_config(frozen_config).get(LIVE_SELECTION_MODE_KEY) or MODE_FIXED).strip().lower()
    return MODE_PIT_ROLLING if raw == MODE_PIT_ROLLING else MODE_FIXED


@dataclass(frozen=True)
class UniversePolicyResolution:
    """Immutable verdict for the live universe selector. ``status`` is the only branch."""

    status: str  # "fixed" | "pit_rolling" | "blocked"
    mode: str
    blockers: list[str] = field(default_factory=list)
    top_n: int = DEFAULT_TOP_N
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    hysteresis_band: int = DEFAULT_HYSTERESIS_BAND
    candidate_symbols: list[str] = field(default_factory=list)  # sorted; == admitted set
    churn_gate: dict[str, Any] = field(default_factory=dict)
    policy_binding: str | None = None

    @property
    def is_fixed(self) -> bool:
        return self.status == MODE_FIXED

    @property
    def is_pit_rolling(self) -> bool:
        return self.status == MODE_PIT_ROLLING

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    def to_artifact(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "blockers": list(self.blockers),
            "top_n": self.top_n,
            "coverage_threshold": self.coverage_threshold,
            "lookback_days": self.lookback_days,
            "hysteresis_band": self.hysteresis_band,
            "candidate_symbols": list(self.candidate_symbols),
            "churn_gate": dict(self.churn_gate),
            "policy_binding": self.policy_binding,
        }


def resolve_live_universe_policy(frozen_config: dict[str, Any]) -> UniversePolicyResolution:
    """Resolve (and, when armed, validate) the live universe policy from the FROZEN config.

    Default-off: ``fixed`` returns immediately with no validation and no side effects, so the
    baseline per-day selection path is untouched. ``pit_rolling`` is fail-closed: any invalid
    parameter or an allowlist too small to fill ``top_n`` yields ``blocked`` with blockers.
    """
    mode = live_selection_mode(frozen_config)
    if mode == MODE_FIXED:
        return UniversePolicyResolution(status=MODE_FIXED, mode=MODE_FIXED)

    blockers: list[str] = []
    cfg = universe_policy_config(frozen_config)
    top_n = _parse_int_field(cfg, "top_n", DEFAULT_TOP_N, blockers)
    coverage_threshold = _parse_float_field(cfg, "coverage_threshold", DEFAULT_COVERAGE_THRESHOLD, blockers)
    lookback_days = _parse_int_field(cfg, "lookback_days", DEFAULT_LOOKBACK_DAYS, blockers)
    hysteresis_band = _parse_int_field(cfg, "hysteresis_band", DEFAULT_HYSTERESIS_BAND, blockers)
    candidate_symbols = _parse_candidate_symbols(cfg.get("candidate_symbols"), blockers)
    churn_gate = _parse_churn_gate(
        cfg.get("churn_gate"),
        blockers,
        candidate_symbols=candidate_symbols,
        top_n=top_n,
    )

    if top_n <= 0:
        blockers.append(f"universe_top_n_not_positive:{top_n}")
    if not (0.0 < coverage_threshold <= 1.0):
        blockers.append(f"universe_coverage_threshold_out_of_range:{coverage_threshold}")
    if lookback_days < 1:
        blockers.append(f"universe_lookback_days_not_positive:{lookback_days}")
    if hysteresis_band < 0:
        blockers.append(f"universe_hysteresis_band_negative:{hysteresis_band}")
    if not candidate_symbols:
        blockers.append("universe_candidate_symbols_missing")
    elif len(candidate_symbols) < max(top_n, 1):
        blockers.append(f"universe_candidate_symbols_below_top_n:{len(candidate_symbols)}<{top_n}")
    not_usdt = [symbol for symbol in candidate_symbols if not symbol.endswith("USDT")]
    if not_usdt:
        blockers.append("universe_candidate_symbols_not_usdt_perp:" + ",".join(sorted(not_usdt)))

    if blockers:
        return UniversePolicyResolution(
            status="blocked",
            mode=MODE_PIT_ROLLING,
            blockers=sorted(set(blockers)),
            top_n=top_n,
            coverage_threshold=coverage_threshold,
            lookback_days=lookback_days,
            hysteresis_band=hysteresis_band,
            candidate_symbols=candidate_symbols,
            churn_gate=churn_gate,
        )

    policy_binding = _canonical_sha256(
        {
            "live_selection_mode": MODE_PIT_ROLLING,
            "top_n": top_n,
            "coverage_threshold": coverage_threshold,
            "lookback_days": lookback_days,
            "hysteresis_band": hysteresis_band,
            "candidate_symbols": list(candidate_symbols),
            "churn_gate": dict(churn_gate),
        }
    )
    return UniversePolicyResolution(
        status=MODE_PIT_ROLLING,
        mode=MODE_PIT_ROLLING,
        blockers=[],
        top_n=top_n,
        coverage_threshold=coverage_threshold,
        lookback_days=lookback_days,
        hysteresis_band=hysteresis_band,
        candidate_symbols=candidate_symbols,
        churn_gate=churn_gate,
        policy_binding=policy_binding,
    )


@dataclass(frozen=True)
class LivePitUniverseResult:
    """Marked panel + fail-closed blockers + deterministic ``live_universe.json`` artifact."""

    panel: pd.DataFrame
    blockers: list[str]
    artifact: dict[str, Any]


def apply_live_pit_universe(
    panel: pd.DataFrame,
    *,
    resolution: UniversePolicyResolution,
    as_of: str | None = None,
    decision_time_ms: int | None = None,
) -> LivePitUniverseResult:
    """Re-mark ``universe_active`` / ``universe_rank`` / ``liquidity_bucket`` on the candidate
    panel using the research PIT rolling selector + a panel-internal hysteresis pass, then
    fail-closed gate the decision-row universe on size + admission.

    The marking is applied to EVERY timestamp (pandas time-rolling is causal, so each row's
    membership uses only data at-or-before that row) — so whatever decision/phase row a runner
    later scores has a correct, PIT-safe ``universe_active``. The size / new-symbol gate and
    ``live_universe.json`` binding are anchored at ``decision_time_ms`` when supplied (the row
    the runner actually scores), else the latest closed bar (== the runner's decision row for
    the default ``--as-of now`` path).
    """
    if not resolution.is_pit_rolling:
        # Should not be called for fixed/blocked; defend anyway with a no-op + blocker.
        return LivePitUniverseResult(panel=panel, blockers=["pit_universe_resolution_not_armed"], artifact={})

    missing_columns = [column for column in _REQUIRED_PANEL_COLUMNS if column not in panel.columns]
    if panel.empty or missing_columns:
        blockers = (
            ["pit_universe_empty_panel"] if panel.empty else [f"pit_universe_panel_missing_columns:{','.join(missing_columns)}"]
        )
        return LivePitUniverseResult(panel=panel, blockers=blockers, artifact=_blocked_artifact(resolution, blockers))

    timestamps = pd.to_numeric(panel["timestamp_ms"], errors="coerce").dropna()
    if timestamps.empty:
        blockers = ["pit_universe_no_timestamps"]
        return LivePitUniverseResult(panel=panel, blockers=blockers, artifact=_blocked_artifact(resolution, blockers))
    resolved_as_of = as_of or datetime.fromtimestamp(int(timestamps.max()) / 1000, tz=UTC).date().isoformat()

    ranked, _summary = apply_point_in_time_rolling_universe(
        panel,
        as_of=resolved_as_of,
        top_n=resolution.top_n,
        coverage_threshold=resolution.coverage_threshold,
        lookback_days=resolution.lookback_days,
    )
    if ranked.empty or "universe_coverage_ratio_lookback" not in ranked.columns:
        # Degenerate (no eligible rows anywhere). Keep the original panel but force no active
        # universe so downstream cannot silently score on a stale per-day marking.
        out = panel.copy()
        out["universe_active"] = False
        out["universe_rank"] = np.nan
        out["liquidity_bucket"] = "not_in_universe"
        blockers = ["pit_universe_no_eligible_rows"]
        return LivePitUniverseResult(panel=out, blockers=blockers, artifact=_blocked_artifact(resolution, blockers))

    marked = _apply_panel_internal_hysteresis(
        ranked,
        top_n=resolution.top_n,
        coverage_threshold=resolution.coverage_threshold,
        hysteresis_band=resolution.hysteresis_band,
    )

    marked_ts = pd.to_numeric(marked["timestamp_ms"], errors="coerce")
    latest_ts = int(marked_ts.max())
    # Gate at the row the runner actually scores when known; the latest bar is the equal default.
    if decision_time_ms is not None and bool(marked_ts.eq(int(decision_time_ms)).any()):
        decision_ts = int(decision_time_ms)
    else:
        decision_ts = latest_ts
    decision_rows = marked.loc[marked_ts.eq(decision_ts)]
    active_rows = decision_rows.loc[decision_rows["universe_active"].astype(bool)].copy()
    active_symbols = sorted(str(symbol) for symbol in active_rows["usdm_symbol"].tolist())

    admitted = set(resolution.candidate_symbols)
    blockers: list[str] = []
    not_admitted = sorted(symbol for symbol in active_symbols if symbol not in admitted)
    for symbol in not_admitted:
        blockers.append(f"new_symbol_not_admitted:{symbol}")
    if len(active_symbols) != resolution.top_n:
        blockers.append(f"active_size_not_{resolution.top_n}:{len(active_symbols)}")

    artifact = _build_live_universe_artifact(
        resolution=resolution,
        resolved_as_of=resolved_as_of,
        decision_ts=decision_ts,
        active_rows=active_rows,
        active_symbols=active_symbols,
        blockers=blockers,
    )
    return LivePitUniverseResult(panel=marked, blockers=sorted(set(blockers)), artifact=artifact)


def _apply_panel_internal_hysteresis(
    ranked: pd.DataFrame,
    *,
    top_n: int,
    coverage_threshold: float,
    hysteresis_band: int,
) -> pd.DataFrame:
    """Walk the panel's daily timestamps ascending, carrying membership forward with a band.

    Deterministic + PIT-safe: ``prev_active`` resets to empty at the first timestamp and only
    ever depends on strictly-earlier timestamps. An incumbent still eligible and ranked within
    ``top_n + band`` is retained; remaining slots fill with the best-ranked challengers, so the
    final membership is exactly ``min(eligible_count, top_n)`` per timestamp. ``band == 0``
    reproduces the research pure-top-N selection.
    """
    out = ranked.copy()
    coverage = pd.to_numeric(out.get("universe_coverage_ratio_lookback"), errors="coerce")
    median_qv = pd.to_numeric(out.get("universe_median_quote_volume_usd_lookback"), errors="coerce")
    out["_pit_eligible"] = coverage.ge(float(coverage_threshold)) & median_qv.gt(0.0)
    out["_pit_mqv"] = median_qv

    active = pd.Series(False, index=out.index)
    rank = pd.Series(np.nan, index=out.index)
    prev_active: set[str] = set()
    resolved_top_n = max(int(top_n), 0)
    resolved_band = max(int(hysteresis_band), 0)

    for ts in sorted(int(value) for value in out["timestamp_ms"].dropna().unique()):
        group = out.loc[pd.to_numeric(out["timestamp_ms"], errors="coerce").eq(ts)]
        eligible = group.loc[group["_pit_eligible"]]
        if eligible.empty or resolved_top_n <= 0:
            prev_active = set()
            continue
        ordered = eligible.sort_values(["_pit_mqv", "subject"], ascending=[False, True])
        ordered_subjects = [str(subject) for subject in ordered["subject"].tolist()]
        index_by_subject = {str(subject): idx for subject, idx in zip(ordered["subject"], ordered.index)}
        rank_position = {subject: position for position, subject in enumerate(ordered_subjects, start=1)}

        selected: list[str] = [
            subject
            for subject in ordered_subjects
            if subject in prev_active and rank_position[subject] <= resolved_top_n + resolved_band
        ][:resolved_top_n]
        selected_set = set(selected)
        for subject in ordered_subjects:
            if len(selected) >= resolved_top_n:
                break
            if subject not in selected_set:
                selected.append(subject)
                selected_set.add(subject)

        final_order = [subject for subject in ordered_subjects if subject in selected_set]
        for position, subject in enumerate(final_order, start=1):
            row_index = index_by_subject[subject]
            active.loc[row_index] = True
            rank.loc[row_index] = float(position)
        prev_active = selected_set

    out["universe_active"] = active.to_numpy(dtype=bool)
    out["universe_rank"] = rank.to_numpy(dtype="float64")
    resolved_rank = pd.to_numeric(out["universe_rank"], errors="coerce")
    out["liquidity_bucket"] = np.where(
        resolved_rank.le(10),
        "top_liquidity",
        np.where(resolved_rank.notna(), "mid_liquidity", "not_in_universe"),
    )
    out["universe_selection_rule"] = PIT_SELECTION_RULE
    out.drop(columns=["_pit_eligible", "_pit_mqv"], errors="ignore", inplace=True)
    return out


def _build_live_universe_artifact(
    *,
    resolution: UniversePolicyResolution,
    resolved_as_of: str,
    decision_ts: int,
    active_rows: pd.DataFrame,
    active_symbols: list[str],
    blockers: list[str],
) -> dict[str, Any]:
    rank_by_symbol = {
        str(row["usdm_symbol"]): int(row["universe_rank"])
        for _, row in active_rows.iterrows()
        if pd.notna(row.get("universe_rank"))
    }
    bucket_by_symbol = {str(row["usdm_symbol"]): str(row.get("liquidity_bucket")) for _, row in active_rows.iterrows()}
    coverage_by_symbol = {
        str(row["usdm_symbol"]): _opt_float(row.get("universe_coverage_ratio_lookback"))
        for _, row in active_rows.iterrows()
    }
    median_qv_by_symbol = {
        str(row["usdm_symbol"]): _opt_float(row.get("universe_median_quote_volume_usd_lookback"))
        for _, row in active_rows.iterrows()
    }
    decision_date = datetime.fromtimestamp(int(decision_ts) / 1000, tz=UTC).date().isoformat()
    universe_binding = _canonical_sha256(
        {
            "live_selection_mode": MODE_PIT_ROLLING,
            "decision_time_ms": int(decision_ts),
            "top_n": resolution.top_n,
            "coverage_threshold": resolution.coverage_threshold,
            "lookback_days": resolution.lookback_days,
            "hysteresis_band": resolution.hysteresis_band,
            "candidate_symbols": sorted(resolution.candidate_symbols),
            "active_symbols": list(active_symbols),
            "active_universe_rank": rank_by_symbol,
        }
    )
    return {
        "schema": LIVE_UNIVERSE_SCHEMA,
        "status": "blocked" if blockers else "ok",
        "live_selection_mode": MODE_PIT_ROLLING,
        "selection_rule": PIT_SELECTION_RULE,
        "as_of": resolved_as_of,
        "decision_time_ms": int(decision_ts),
        "decision_date_utc": decision_date,
        "top_n": resolution.top_n,
        "coverage_threshold": resolution.coverage_threshold,
        "lookback_days": resolution.lookback_days,
        "hysteresis_band": resolution.hysteresis_band,
        "candidate_symbols": sorted(resolution.candidate_symbols),
        "candidate_symbols_sha256": _canonical_sha256(sorted(resolution.candidate_symbols)),
        "churn_gate": dict(resolution.churn_gate),
        "active_symbols": list(active_symbols),
        "active_count": len(active_symbols),
        "active_universe_rank": rank_by_symbol,
        "active_liquidity_bucket": bucket_by_symbol,
        "active_coverage_ratio": coverage_by_symbol,
        "active_median_quote_volume_usd": median_qv_by_symbol,
        "size_invariant_ok": len(active_symbols) == resolution.top_n,
        "policy_binding": resolution.policy_binding,
        "blockers": sorted(set(blockers)),
        "universe_binding": universe_binding,
    }


def _blocked_artifact(resolution: UniversePolicyResolution, blockers: list[str]) -> dict[str, Any]:
    return {
        "schema": LIVE_UNIVERSE_SCHEMA,
        "status": "blocked",
        "live_selection_mode": MODE_PIT_ROLLING,
        "top_n": resolution.top_n,
        "coverage_threshold": resolution.coverage_threshold,
        "lookback_days": resolution.lookback_days,
        "hysteresis_band": resolution.hysteresis_band,
        "candidate_symbols": sorted(resolution.candidate_symbols),
        "churn_gate": dict(resolution.churn_gate),
        "policy_binding": resolution.policy_binding,
        "blockers": sorted(set(blockers)),
    }


def _parse_candidate_symbols(raw: Any, blockers: list[str]) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        blockers.append("universe_candidate_symbols_must_be_yaml_list")
        return []
    try:
        items = list(raw)
    except TypeError:
        blockers.append("universe_candidate_symbols_must_be_yaml_list")
        return []
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        symbol = str(item).strip().upper()
        if not symbol:
            continue
        if symbol in seen:
            blockers.append(f"universe_candidate_symbols_duplicate:{symbol}")
            continue
        seen.add(symbol)
        output.append(symbol)
    return sorted(output)


def _parse_reference_symbols(raw: Any, *, field_name: str, blockers: list[str]) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        blockers.append(f"{field_name}_must_be_yaml_list")
        return []
    try:
        items = list(raw)
    except TypeError:
        blockers.append(f"{field_name}_must_be_yaml_list")
        return []
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        symbol = str(item).strip().upper()
        if not symbol:
            continue
        if symbol in seen:
            blockers.append(f"{field_name}_duplicate:{symbol}")
            continue
        seen.add(symbol)
        output.append(symbol)
    return sorted(output)


def _parse_int_field(cfg: dict[str, Any], key: str, default: int, blockers: list[str]) -> int:
    value = cfg.get(key)
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return int(default)
        if isinstance(value, bool):
            raise TypeError("bool is not an int policy value")
        parsed = int(value)
    except (TypeError, ValueError):
        blockers.append(f"universe_{key}_invalid:{value}")
        return int(default)
    if str(parsed) != str(value).strip() if isinstance(value, str) else False:
        blockers.append(f"universe_{key}_invalid:{value}")
    return parsed


def _parse_float_field(cfg: dict[str, Any], key: str, default: float, blockers: list[str]) -> float:
    value = cfg.get(key)
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return float(default)
        if isinstance(value, bool):
            raise TypeError("bool is not a float policy value")
        parsed = float(value)
    except (TypeError, ValueError):
        blockers.append(f"universe_{key}_invalid:{value}")
        return float(default)
    if not np.isfinite(parsed):
        blockers.append(f"universe_{key}_not_finite:{value}")
        return float(default)
    return parsed


def _parse_bool_field(raw: Any, *, field_name: str, blockers: list[str]) -> bool:
    if isinstance(raw, bool):
        return bool(raw)
    if raw is None:
        return False
    blockers.append(f"{field_name}_must_be_bool")
    return False


def _parse_nonnegative_int(raw: Any, *, field_name: str, blockers: list[str]) -> int | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        if isinstance(raw, bool):
            raise TypeError("bool is not an int policy value")
        parsed = int(raw)
    except (TypeError, ValueError):
        blockers.append(f"{field_name}_invalid:{raw}")
        return None
    if parsed < 0:
        blockers.append(f"{field_name}_negative:{parsed}")
        return None
    return parsed


def _parse_nonnegative_float(raw: Any, *, field_name: str, blockers: list[str]) -> float | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        if isinstance(raw, bool):
            raise TypeError("bool is not a float policy value")
        parsed = float(raw)
    except (TypeError, ValueError):
        blockers.append(f"{field_name}_invalid:{raw}")
        return None
    if not np.isfinite(parsed):
        blockers.append(f"{field_name}_not_finite:{raw}")
        return None
    if parsed < 0.0:
        blockers.append(f"{field_name}_negative:{parsed}")
        return None
    return parsed


def _parse_churn_gate(
    raw: Any,
    blockers: list[str],
    *,
    candidate_symbols: list[str],
    top_n: int,
) -> dict[str, Any]:
    if raw is None:
        return {"enabled": False}
    if not isinstance(raw, dict):
        blockers.append("universe_churn_gate_must_be_mapping")
        return {"enabled": False}
    enabled = _parse_bool_field(raw.get("enabled"), field_name="universe_churn_gate_enabled", blockers=blockers)
    gate: dict[str, Any] = {"enabled": enabled}
    if not enabled:
        return gate

    for key in ("max_entered_count", "max_exited_count", "max_churn_count"):
        parsed = _parse_nonnegative_int(
            raw.get(key),
            field_name=f"universe_churn_gate_{key}",
            blockers=blockers,
        )
        if parsed is not None:
            gate[key] = parsed
    max_ratio = _parse_nonnegative_float(
        raw.get("max_churn_ratio"),
        field_name="universe_churn_gate_max_churn_ratio",
        blockers=blockers,
    )
    if max_ratio is not None:
        gate["max_churn_ratio"] = max_ratio

    if not any(key in gate for key in ("max_entered_count", "max_exited_count", "max_churn_count", "max_churn_ratio")):
        blockers.append("universe_churn_gate_missing_thresholds")

    reference_symbols = _parse_reference_symbols(
        raw.get("bootstrap_reference_symbols"),
        field_name="universe_churn_gate_bootstrap_reference_symbols",
        blockers=blockers,
    )
    if reference_symbols:
        if len(reference_symbols) != max(top_n, 0):
            blockers.append(f"universe_churn_gate_bootstrap_reference_size_not_top_n:{len(reference_symbols)}!={top_n}")
        missing = sorted(set(reference_symbols) - set(candidate_symbols))
        if missing:
            blockers.append("universe_churn_gate_bootstrap_reference_not_candidate:" + ",".join(missing))
        not_usdt = [symbol for symbol in reference_symbols if not symbol.endswith("USDT")]
        if not_usdt:
            blockers.append("universe_churn_gate_bootstrap_reference_not_usdt:" + ",".join(sorted(not_usdt)))
    gate["bootstrap_reference_symbols"] = reference_symbols
    return gate


def _opt_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def build_universe_change_log(
    *, current: dict[str, Any], prior: dict[str, Any] | None
) -> dict[str, Any]:
    """PURE day-over-day audit diff of two ``live_universe.json`` artifacts.

    READ-ONLY traceability ONLY: this is never fed back into universe selection. The selection
    stays panel-internal + deterministic (reproducible from ``(panel, as_of, policy)`` alone),
    so feeding a cross-run change log back in would break that guarantee. It reports which
    admitted symbols entered / exited / were retained between the prior recorded decision and the
    current one, plus a churn ratio, so unexpected membership turnover (feed instability, a
    borderline allowlist, hysteresis behaviour) is auditable after the fact. Drift PREVENTION is a
    separate property handled by binding ``live_universe.json`` into ``plan_hash`` at submit; this
    record is the human-readable view, not the enforcement.
    """
    current = dict(current or {})
    cur_active = sorted(str(symbol) for symbol in (current.get("active_symbols") or []))
    cur_set = set(cur_active)
    base: dict[str, Any] = {
        "schema": UNIVERSE_CHANGE_LOG_SCHEMA,
        "decision_time_ms": current.get("decision_time_ms"),
        "decision_date_utc": current.get("decision_date_utc"),
        "current_status": str(current.get("status") or ""),
        "current_active_count": len(cur_active),
        "current_active_symbols": list(cur_active),
        "current_universe_binding": current.get("universe_binding"),
    }
    if not prior:
        # First recorded universe (no prior run): everything currently active is an entry.
        base.update(
            {
                "has_prior": False,
                "prior_decision_time_ms": None,
                "prior_decision_date_utc": None,
                "prior_status": None,
                "prior_active_count": 0,
                "prior_universe_binding": None,
                "entered": list(cur_active),
                "exited": [],
                "retained": [],
                "entered_count": len(cur_active),
                "exited_count": 0,
                "retained_count": 0,
                "churn_count": len(cur_active),
                "churn_ratio": 1.0 if cur_active else 0.0,
                "binding_changed": bool(cur_active),
            }
        )
        return base
    prior = dict(prior or {})
    prior_active = sorted(str(symbol) for symbol in (prior.get("active_symbols") or []))
    prior_set = set(prior_active)
    entered = sorted(cur_set - prior_set)
    exited = sorted(prior_set - cur_set)
    retained = sorted(cur_set & prior_set)
    denom = max(len(cur_active), 1)
    cur_binding = current.get("universe_binding")
    prior_binding = prior.get("universe_binding")
    base.update(
        {
            "has_prior": True,
            "prior_decision_time_ms": prior.get("decision_time_ms"),
            "prior_decision_date_utc": prior.get("decision_date_utc"),
            "prior_status": str(prior.get("status") or ""),
            "prior_active_count": len(prior_active),
            "prior_universe_binding": prior_binding,
            "entered": entered,
            "exited": exited,
            "retained": retained,
            "entered_count": len(entered),
            "exited_count": len(exited),
            "retained_count": len(retained),
            "churn_count": len(entered) + len(exited),
            "churn_ratio": float(len(entered) + len(exited)) / float(denom),
            "binding_changed": bool(cur_binding != prior_binding),
        }
    )
    return base


def evaluate_universe_churn_gate(
    *,
    current: dict[str, Any],
    prior: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate the owner-approved runtime churn gate against a prior universe artifact.

    The selector itself remains deterministic and panel-internal. This gate only inspects the
    selected ``live_universe.json`` artifact and fails closed when membership turnover exceeds
    the owner-approved thresholds. If there is no prior artifact yet, an explicit
    ``bootstrap_reference_symbols`` list is required in the live config; otherwise the first
    expanded run is blocked instead of silently treating "no prior" as unlimited churn.
    """
    current = dict(current or {})
    gate = dict(current.get("churn_gate") or {})
    if gate.get("enabled") is not True:
        return {
            "schema": "live_pit_universe_churn_gate.v1",
            "status": "disabled",
            "enabled": False,
            "blockers": [],
        }

    reference_source = "prior_live_universe_artifact"
    reference = prior
    if not reference:
        reference_symbols = sorted(str(symbol) for symbol in (gate.get("bootstrap_reference_symbols") or []))
        reference_source = "bootstrap_reference_symbols"
        if not reference_symbols:
            return {
                "schema": "live_pit_universe_churn_gate.v1",
                "status": "blocked",
                "enabled": True,
                "reference_source": "missing",
                "blockers": ["universe_churn_gate_missing_prior_or_bootstrap_reference"],
            }
        reference = {
            "status": "bootstrap_reference",
            "decision_time_ms": None,
            "decision_date_utc": None,
            "active_symbols": reference_symbols,
            "universe_binding": _canonical_sha256(
                {
                    "bootstrap_reference_symbols": reference_symbols,
                }
            ),
        }

    change_log = build_universe_change_log(current=current, prior=reference)
    blockers: list[str] = []
    entered_count = int(change_log.get("entered_count") or 0)
    exited_count = int(change_log.get("exited_count") or 0)
    churn_count = int(change_log.get("churn_count") or 0)
    churn_ratio = float(change_log.get("churn_ratio") or 0.0)

    thresholds = {
        key: gate.get(key)
        for key in ("max_entered_count", "max_exited_count", "max_churn_count", "max_churn_ratio")
        if gate.get(key) is not None
    }
    max_entered = gate.get("max_entered_count")
    if max_entered is not None and entered_count > int(max_entered):
        blockers.append(f"universe_churn_entered_count_exceeds_max:{entered_count}>{int(max_entered)}")
    max_exited = gate.get("max_exited_count")
    if max_exited is not None and exited_count > int(max_exited):
        blockers.append(f"universe_churn_exited_count_exceeds_max:{exited_count}>{int(max_exited)}")
    max_churn = gate.get("max_churn_count")
    if max_churn is not None and churn_count > int(max_churn):
        blockers.append(f"universe_churn_count_exceeds_max:{churn_count}>{int(max_churn)}")
    max_ratio = gate.get("max_churn_ratio")
    if max_ratio is not None and churn_ratio > float(max_ratio) + 1e-12:
        blockers.append(f"universe_churn_ratio_exceeds_max:{churn_ratio:.6f}>{float(max_ratio):.6f}")

    return {
        "schema": "live_pit_universe_churn_gate.v1",
        "status": "passed" if not blockers else "blocked",
        "enabled": True,
        "reference_source": reference_source,
        "thresholds": thresholds,
        "entered": list(change_log.get("entered") or []),
        "exited": list(change_log.get("exited") or []),
        "retained": list(change_log.get("retained") or []),
        "entered_count": entered_count,
        "exited_count": exited_count,
        "churn_count": churn_count,
        "churn_ratio": churn_ratio,
        "blockers": sorted(set(blockers)),
    }


def find_prior_live_universe_artifact(*, run_root: Path, run_id: str) -> dict[str, Any] | None:
    """Locate the most recent PRIOR run's ``live_universe.json`` for the change-log diff.

    Runs are sibling directories under ``run_root.parent``; ``run_id`` is timestamp-prefixed, so
    lexicographic ordering is chronological and the largest sibling name strictly less than
    ``run_id`` is the immediately preceding run. Fully defensive: any filesystem/parse error (or
    no prior run) yields ``None`` — a missing audit baseline must never break the live plan run.
    The result is diffed for traceability only and is NEVER fed back into universe selection.
    """
    try:
        parent = Path(run_root).parent
        if not parent.exists():
            return None
        prior_names = sorted(
            child.name
            for child in parent.iterdir()
            if child.is_dir()
            and child.name < str(run_id)
            and (child / LIVE_UNIVERSE_ARTIFACT).is_file()
        )
        if not prior_names:
            return None
        artifact_path = parent / prior_names[-1] / LIVE_UNIVERSE_ARTIFACT
        return dict(json.loads(artifact_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def write_universe_change_log(
    *, run_root: Path, run_id: str, live_universe: dict[str, Any]
) -> None:
    """Best-effort, read-only universe change-log writer. NEVER raises and NEVER touches the
    decision blockers — the audit trail must never break OR alter a live plan run. Any failure
    (disk full, permission denied, serialisation, a prior-artifact read error) silently leaves no
    change-log. The universe SELECTION and the drift guard (``live_universe.json`` bound into
    ``plan_hash``) are entirely unaffected; this is purely the human-readable traceability view.
    """
    try:
        write_json(
            run_root / UNIVERSE_CHANGE_LOG_ARTIFACT,
            build_universe_change_log(
                current=live_universe,
                prior=find_prior_live_universe_artifact(run_root=run_root, run_id=run_id),
            ),
        )
    except Exception:
        # Audit-only: a change-log failure must never propagate into the plan run.
        return
