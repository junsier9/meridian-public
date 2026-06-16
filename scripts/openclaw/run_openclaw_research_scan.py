from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.openclaw.run_openclaw_research_cycle import (
    ASSET_BUCKETS,
    DEFAULT_SCOPE,
    KNOWN_GAP_CATEGORIES,
    ResearchCyclePainLog,
    STRATEGY_PROFILES,
    _coerce_bool,
    _require_non_empty_string,
    _read_json_file,
    _write_json_file,
    load_thesis_profiles,
)
from scripts.market_data.binance_ohlcv import (
    build_ohlcv_context,
    load_symbol_catalog,
    resolve_market_symbols,
    write_ohlcv_context_bundle,
)
from enhengclaw.utils.research_workbench_queues import all_pending_snapshot_roots, incoming_queue_root, STRUCTURAL_QUEUE

WORKBENCH_ROOT = ROOT / "artifacts" / "research_workbench"
SCAN_INPUT_ROOT = WORKBENCH_ROOT / "_scan_inputs"
SCAN_RUN_ROOT = WORKBENCH_ROOT / "_scan_runs"
INCOMING_ROOT = incoming_queue_root(workbench_root=WORKBENCH_ROOT, source=STRUCTURAL_QUEUE)
MAX_SNAPSHOTS_PER_SCAN = 3
MIN_THESIS_TARGET = 5
FULL_THESIS_TARGET = 8


@dataclass(frozen=True, slots=True)
class MarketScanCandidate:
    subject: str
    market_cap_rank: int
    structure_clarity_score: float
    liquidity_score: float
    catalyst_score: float
    risk_boundary_score: float
    volatility_score: float
    observation: str
    evidence: str
    risk: str
    next_step: str
    scope: str = DEFAULT_SCOPE
    spot_symbol: str | None = None
    usdm_symbol: str | None = None
    is_stablecoin: bool = False
    is_pegged_asset: bool = False
    pain_log: ResearchCyclePainLog | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MarketScanCandidate":
        if not isinstance(payload, dict):
            raise ValueError("candidate must be a JSON object")
        return cls(
            subject=_require_non_empty_string(payload.get("subject"), "candidate.subject"),
            market_cap_rank=_require_positive_int(payload.get("market_cap_rank"), "candidate.market_cap_rank"),
            structure_clarity_score=_require_score(payload.get("structure_clarity_score"), "candidate.structure_clarity_score"),
            liquidity_score=_require_score(payload.get("liquidity_score"), "candidate.liquidity_score"),
            catalyst_score=_require_score(payload.get("catalyst_score"), "candidate.catalyst_score"),
            risk_boundary_score=_require_score(payload.get("risk_boundary_score"), "candidate.risk_boundary_score"),
            volatility_score=_require_score(payload.get("volatility_score"), "candidate.volatility_score"),
            observation=_require_non_empty_string(payload.get("observation"), "candidate.observation"),
            evidence=_require_non_empty_string(payload.get("evidence"), "candidate.evidence"),
            risk=_require_non_empty_string(payload.get("risk"), "candidate.risk"),
            next_step=_require_non_empty_string(payload.get("next_step"), "candidate.next_step"),
            scope=str(payload.get("scope", DEFAULT_SCOPE)).strip() or DEFAULT_SCOPE,
            spot_symbol=_optional_symbol(payload.get("spot_symbol")),
            usdm_symbol=_optional_symbol(payload.get("usdm_symbol")),
            is_stablecoin=_coerce_bool(payload.get("is_stablecoin", False)),
            is_pegged_asset=_coerce_bool(payload.get("is_pegged_asset", False)),
            pain_log=ResearchCyclePainLog.from_payload(payload.get("pain_log")),
        )

    @property
    def selection_score(self) -> float:
        return round(
            (self.structure_clarity_score * 0.35)
            + (self.liquidity_score * 0.25)
            + (self.catalyst_score * 0.20)
            + (self.risk_boundary_score * 0.20),
            3,
        )


@dataclass(frozen=True, slots=True)
class MarketScanPayload:
    scan_id: str
    scan_date: str
    candidates: tuple[MarketScanCandidate, ...]
    generated_at_utc: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MarketScanPayload":
        if not isinstance(payload, dict):
            raise ValueError("market scan payload must be a JSON object")
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise ValueError("candidates must be a non-empty JSON array")
        return cls(
            scan_id=_require_non_empty_string(payload.get("scan_id"), "scan_id"),
            scan_date=_require_non_empty_string(payload.get("scan_date"), "scan_date"),
            generated_at_utc=str(payload.get("generated_at_utc", "")).strip() or None,
            candidates=tuple(MarketScanCandidate.from_payload(item) for item in raw_candidates),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select 1-3 research-worthy assets from one market scan input and emit normalized cycle snapshots."
    )
    parser.add_argument("--market-scan", type=Path, required=True, help="Path to one normalized market-scan JSON input.")
    parser.add_argument(
        "--workbench-root",
        type=Path,
        default=WORKBENCH_ROOT,
        help="Research workbench root. Defaults to artifacts\\research_workbench.",
    )
    parser.add_argument(
        "--incoming-root",
        type=Path,
        default=None,
        help="Snapshot output root. Defaults to artifacts\\research_workbench\\_incoming_structural.",
    )
    parser.add_argument(
        "--max-snapshots",
        type=int,
        default=MAX_SNAPSHOTS_PER_SCAN,
        help="Maximum snapshots to emit for one scan. Defaults to 3.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_openclaw_research_scan(
            market_scan_path=args.market_scan,
            workbench_root=args.workbench_root,
            incoming_root=args.incoming_root,
            max_snapshots=args.max_snapshots,
        )
    except Exception as exc:
        print(str(exc))
        return 1
    print(f"[openclaw-research-scan] scan_summary={result['scan_summary_path']}")
    print(f"[openclaw-research-scan] status={result['status']}")
    print(f"[openclaw-research-scan] selected_snapshot_count={result['selected_snapshot_count']}")
    return 0


def run_openclaw_research_scan(
    *,
    market_scan_path: Path,
    workbench_root: Path,
    incoming_root: Path | None = None,
    max_snapshots: int = MAX_SNAPSHOTS_PER_SCAN,
) -> dict[str, Any]:
    if max_snapshots <= 0:
        raise ValueError("max_snapshots must be positive")
    payload = MarketScanPayload.from_payload(_read_json_file(market_scan_path))
    resolved_workbench_root = workbench_root.expanduser().resolve()
    resolved_incoming_root = (
        incoming_root.expanduser().resolve()
        if incoming_root is not None
        else incoming_queue_root(workbench_root=resolved_workbench_root, source=STRUCTURAL_QUEUE).resolve()
    )
    scan_root = (resolved_workbench_root / "_scan_runs" / payload.scan_id).resolve()
    if scan_root.exists():
        raise FileExistsError(f"research scan already exists: {payload.scan_id}")
    scan_root.mkdir(parents=True, exist_ok=False)
    normalized_input_path = scan_root / "market_scan.normalized.json"
    _write_json_file(normalized_input_path, _market_scan_to_payload(payload))

    thesis_records = load_existing_thesis_records(workbench_root=resolved_workbench_root)
    covered_buckets = {
        str(record.get("asset_bucket"))
        for record in thesis_records
        if str(record.get("asset_bucket", "")).strip() in ASSET_BUCKETS
    }
    seeding_phase = len(thesis_records) < MIN_THESIS_TARGET
    unconsumed_snapshot_count = count_unconsumed_snapshots(
        workbench_root=resolved_workbench_root,
        incoming_root=resolved_incoming_root,
    )
    available_slots = max(0, min(max_snapshots, MAX_SNAPSHOTS_PER_SCAN) - unconsumed_snapshot_count)

    selected, filtered_counts = select_candidates_for_scan(
        payload=payload,
        thesis_records=thesis_records,
        scan_date=payload.scan_date,
        available_slots=available_slots,
        covered_buckets=covered_buckets,
        workbench_root=resolved_workbench_root,
        incoming_root=resolved_incoming_root,
        scan_root=scan_root,
    )
    summary = {
        "status": "success",
        "scan_id": payload.scan_id,
        "scan_date": payload.scan_date,
        "generated_at_utc": payload.generated_at_utc,
        "market_scan_path": str(market_scan_path.resolve()),
        "normalized_scan_path": str(normalized_input_path),
        "scan_root": str(scan_root),
        "workbench_root": str(resolved_workbench_root),
        "incoming_root": str(resolved_incoming_root),
        "source": STRUCTURAL_QUEUE,
        "candidate_count": len(payload.candidates),
        "unconsumed_snapshot_count_before_scan": unconsumed_snapshot_count,
        "available_snapshot_slots": available_slots,
        "seeding_phase": seeding_phase,
        "current_thesis_count": len(thesis_records),
        "target_thesis_count": FULL_THESIS_TARGET,
        "covered_asset_buckets_before_scan": sorted(covered_buckets),
        "missing_asset_buckets_before_scan": [bucket for bucket in ASSET_BUCKETS if bucket not in covered_buckets],
        "filtered_candidate_counts": filtered_counts,
        "selected_snapshot_count": len(selected),
        "selected_snapshots": selected,
    }
    scan_summary_path = scan_root / "scan_summary.json"
    _write_json_file(scan_summary_path, summary)
    summary["scan_summary_path"] = str(scan_summary_path)
    return summary


def select_candidates_for_scan(
    *,
    payload: MarketScanPayload,
    thesis_records: list[dict[str, Any]],
    scan_date: str,
    available_slots: int,
    covered_buckets: set[str],
    workbench_root: Path,
    incoming_root: Path,
    scan_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    filtered_counts = {
        "stablecoin_or_pegged": 0,
        "out_of_rank_scope": 0,
        "daily_cycle_limit": 0,
        "duplicate_subject": 0,
        "no_available_slot": 0,
    }
    if available_slots <= 0:
        filtered_counts["no_available_slot"] = len(payload.candidates)
        return [], filtered_counts

    candidate_rows: list[dict[str, Any]] = []
    for candidate in payload.candidates:
        if candidate.is_stablecoin or candidate.is_pegged_asset:
            filtered_counts["stablecoin_or_pegged"] += 1
            continue
        asset_bucket = asset_bucket_for_rank(candidate.market_cap_rank)
        if asset_bucket is None:
            filtered_counts["out_of_rank_scope"] += 1
            continue
        strategy_profile = strategy_profile_for_candidate(candidate=candidate, asset_bucket=asset_bucket)
        thesis_record = match_existing_thesis(
            thesis_records=thesis_records,
            subject=candidate.subject,
            strategy_profile=strategy_profile,
            asset_bucket=asset_bucket,
        )
        object_id = (
            str(thesis_record["object_id"])
            if thesis_record is not None
            else build_new_object_id(
                subject=candidate.subject,
                strategy_profile=strategy_profile,
                scan_date=payload.scan_date,
                workbench_root=workbench_root,
            )
        )
        if count_daily_activity(
            workbench_root=workbench_root,
            incoming_root=incoming_root,
            object_id=object_id,
            cycle_date=scan_date,
        ) >= 2:
            filtered_counts["daily_cycle_limit"] += 1
            continue
        candidate_rows.append(
            {
                "subject": candidate.subject,
                "candidate": candidate,
                "object_id": object_id,
                "asset_bucket": asset_bucket,
                "strategy_profile": strategy_profile,
                "selection_score": candidate.selection_score,
            }
        )

    deduped_by_subject: dict[str, dict[str, Any]] = {}
    for row in sorted(
        candidate_rows,
        key=lambda item: (
            float(item["selection_score"]),
            -int(item["candidate"].market_cap_rank),
            str(item["subject"]),
        ),
        reverse=True,
    ):
        subject_key = str(row["subject"]).upper()
        if subject_key in deduped_by_subject:
            filtered_counts["duplicate_subject"] += 1
            continue
        deduped_by_subject[subject_key] = row
    eligible_rows = list(deduped_by_subject.values())

    selected_rows: list[dict[str, Any]] = []
    missing_buckets = [bucket for bucket in ASSET_BUCKETS if bucket not in covered_buckets]
    prioritized_rows: list[dict[str, Any]] = []
    for bucket in missing_buckets:
        bucket_rows = [row for row in eligible_rows if row["asset_bucket"] == bucket and row not in prioritized_rows]
        if not bucket_rows:
            continue
        prioritized_rows.append(max(bucket_rows, key=lambda item: float(item["selection_score"])))
    prioritized_rows.sort(key=lambda item: float(item["selection_score"]), reverse=True)
    for row in prioritized_rows:
        if len(selected_rows) >= available_slots:
            break
        selected_rows.append(row)

    for row in sorted(eligible_rows, key=lambda item: float(item["selection_score"]), reverse=True):
        if row in selected_rows:
            continue
        if len(selected_rows) >= available_slots:
            break
        selected_rows.append(row)

    selected_snapshots: list[dict[str, Any]] = []
    symbol_catalog = load_symbol_catalog()
    context_root = scan_root / "ohlcv_context"
    for row in selected_rows:
        candidate = row["candidate"]
        cycle_id = build_cycle_id(object_id=str(row["object_id"]), scan_id=payload.scan_id)
        cycle_id = ensure_unique_cycle_id(
            cycle_id=cycle_id,
            object_id=str(row["object_id"]),
            workbench_root=workbench_root,
            incoming_root=incoming_root,
        )
        market_symbols, history_coverage, context_ref = build_candidate_history_bundle(
            candidate=candidate,
            cycle_id=cycle_id,
            context_root=context_root,
            symbol_catalog=symbol_catalog,
        )
        snapshot_payload = {
            "cycle_id": cycle_id,
            "cycle_date": payload.scan_date,
            "object_id": str(row["object_id"]),
            "subject": candidate.subject,
            "scope": candidate.scope,
            "strategy_profile": str(row["strategy_profile"]),
            "asset_bucket": str(row["asset_bucket"]),
            "market_symbols": market_symbols,
            "history_coverage": history_coverage,
            "ohlcv_context_ref": context_ref,
            "observation": candidate.observation,
            "evidence": candidate.evidence,
            "risk": candidate.risk,
            "next_step": candidate.next_step,
            "source": STRUCTURAL_QUEUE,
            "export_priority": row["selection_score"],
            "published_to_intake": True,
        }
        if candidate.pain_log is not None:
            snapshot_payload["pain_log"] = candidate.pain_log.to_payload()
        snapshot_path = incoming_root / f"{cycle_id}.snapshot.json"
        _write_json_file(snapshot_path, snapshot_payload)
        selected_snapshots.append(
            {
                "subject": candidate.subject,
                "object_id": str(row["object_id"]),
                "cycle_id": cycle_id,
                "strategy_profile": str(row["strategy_profile"]),
                "asset_bucket": str(row["asset_bucket"]),
                "market_cap_rank": candidate.market_cap_rank,
                "selection_score": row["selection_score"],
                "market_symbols": market_symbols,
                "history_coverage": history_coverage,
                "ohlcv_context_ref": context_ref,
                "snapshot_path": str(snapshot_path.resolve()),
            }
        )

    return selected_snapshots, filtered_counts


def load_existing_thesis_records(*, workbench_root: Path) -> list[dict[str, Any]]:
    profile_records = load_thesis_profiles(workbench_root=workbench_root)
    records_by_object = {str(record["object_id"]): dict(record) for record in profile_records}
    if not workbench_root.exists():
        return []
    for thesis_dir in sorted(workbench_root.iterdir()):
        if not thesis_dir.is_dir() or thesis_dir.name.startswith("_"):
            continue
        if thesis_dir.name in records_by_object:
            continue
        latest_summary = load_latest_cycle_summary(thesis_dir=thesis_dir)
        if latest_summary is None:
            continue
        records_by_object[thesis_dir.name] = {
            "object_id": thesis_dir.name,
            "subject": latest_summary.get("subject"),
            "scope": latest_summary.get("scope", DEFAULT_SCOPE),
            "strategy_profile": latest_summary.get("strategy_profile"),
            "asset_bucket": latest_summary.get("asset_bucket"),
            "updated_at_utc": latest_summary.get("generated_at_utc"),
        }
    return list(records_by_object.values())


def load_latest_cycle_summary(*, thesis_dir: Path) -> dict[str, Any] | None:
    cycle_paths = sorted(thesis_dir.glob("cycles/*/cycle_summary.json"))
    if not cycle_paths:
        return None
    return _read_json_file(cycle_paths[-1])


def asset_bucket_for_rank(rank: int) -> str | None:
    if 1 <= rank <= 20:
        return "large_cap"
    if 21 <= rank <= 100:
        return "mid_cap"
    if 101 <= rank <= 300:
        return "small_cap"
    return None


def strategy_profile_for_candidate(*, candidate: MarketScanCandidate, asset_bucket: str) -> str:
    if (
        asset_bucket == "large_cap"
        and candidate.liquidity_score >= 75
        and candidate.structure_clarity_score >= 70
        and candidate.risk_boundary_score >= 70
        and candidate.volatility_score <= 60
    ):
        return "conservative"
    if asset_bucket == "small_cap" or candidate.volatility_score >= 75 or candidate.catalyst_score >= 80:
        return "aggressive"
    return "balanced"


def match_existing_thesis(
    *,
    thesis_records: list[dict[str, Any]],
    subject: str,
    strategy_profile: str,
    asset_bucket: str,
) -> dict[str, Any] | None:
    normalized_subject = subject.upper()
    exact_matches = [
        record
        for record in thesis_records
        if str(record.get("subject", "")).upper() == normalized_subject
        and str(record.get("strategy_profile", "")).strip() == strategy_profile
        and str(record.get("asset_bucket", "")).strip() == asset_bucket
    ]
    if exact_matches:
        return sorted(exact_matches, key=lambda item: str(item.get("updated_at_utc", "")), reverse=True)[0]
    legacy_matches = [
        record
        for record in thesis_records
        if str(record.get("subject", "")).upper() == normalized_subject
        and not str(record.get("strategy_profile", "")).strip()
        and not str(record.get("asset_bucket", "")).strip()
    ]
    if legacy_matches:
        return sorted(legacy_matches, key=lambda item: str(item.get("updated_at_utc", "")), reverse=True)[0]
    return None


def build_new_object_id(*, subject: str, strategy_profile: str, scan_date: str, workbench_root: Path) -> str:
    base = f"{_slugify(subject)}-{strategy_profile}-{scan_date.replace('-', '')}"
    candidate = base
    suffix = 2
    while (workbench_root / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def build_cycle_id(*, object_id: str, scan_id: str) -> str:
    return f"{object_id}-{_slugify(scan_id)}"


def ensure_unique_cycle_id(*, cycle_id: str, object_id: str, workbench_root: Path, incoming_root: Path) -> str:
    candidate = cycle_id
    suffix = 2
    while (
        (workbench_root / object_id / "cycles" / candidate / "cycle_summary.json").exists()
        or (incoming_root / f"{candidate}.snapshot.json").exists()
    ):
        candidate = f"{cycle_id}-{suffix}"
        suffix += 1
    return candidate


def count_unconsumed_snapshots(*, workbench_root: Path, incoming_root: Path) -> int:
    if not incoming_root.exists():
        return 0
    count = 0
    for snapshot_path in incoming_root.glob("*.snapshot.json"):
        if not is_snapshot_consumed(snapshot_path=snapshot_path, workbench_root=workbench_root):
            count += 1
    return count


def is_snapshot_consumed(*, snapshot_path: Path, workbench_root: Path) -> bool:
    payload = _read_json_file(snapshot_path)
    object_id = _require_non_empty_string(payload.get("object_id"), "object_id")
    cycle_id = _require_non_empty_string(payload.get("cycle_id"), "cycle_id")
    return (workbench_root / object_id / "cycles" / cycle_id / "cycle_summary.json").exists()


def count_daily_activity(*, workbench_root: Path, incoming_root: Path, object_id: str, cycle_date: str) -> int:
    completed = 0
    thesis_root = workbench_root / object_id / "cycles"
    if thesis_root.exists():
        for summary_path in thesis_root.glob("*/cycle_summary.json"):
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            if str(payload.get("cycle_date", "")).strip() == cycle_date:
                completed += 1
    pending = 0
    queue_roots = {incoming_root.resolve()}
    queue_roots.update(path.resolve() for path in all_pending_snapshot_roots(workbench_root=workbench_root))
    for queue_root in queue_roots:
        if not queue_root.exists():
            continue
        for snapshot_path in queue_root.glob("*.snapshot.json"):
            payload = _read_json_file(snapshot_path)
            if (
                str(payload.get("object_id", "")).strip() == object_id
                and str(payload.get("cycle_date", "")).strip() == cycle_date
                and not is_snapshot_consumed(snapshot_path=snapshot_path, workbench_root=workbench_root)
            ):
                pending += 1
    return completed + pending


def _market_scan_to_payload(payload: MarketScanPayload) -> dict[str, Any]:
    return {
        "scan_id": payload.scan_id,
        "scan_date": payload.scan_date,
        "generated_at_utc": payload.generated_at_utc,
        "candidates": [
            {
                "subject": candidate.subject,
                "market_cap_rank": candidate.market_cap_rank,
                "scope": candidate.scope,
                "structure_clarity_score": candidate.structure_clarity_score,
                "liquidity_score": candidate.liquidity_score,
                "catalyst_score": candidate.catalyst_score,
                "risk_boundary_score": candidate.risk_boundary_score,
                "volatility_score": candidate.volatility_score,
                "observation": candidate.observation,
                "evidence": candidate.evidence,
                "risk": candidate.risk,
                "next_step": candidate.next_step,
                "spot_symbol": candidate.spot_symbol,
                "usdm_symbol": candidate.usdm_symbol,
                "is_stablecoin": candidate.is_stablecoin,
                "is_pegged_asset": candidate.is_pegged_asset,
                "pain_log": None if candidate.pain_log is None else candidate.pain_log.to_payload(),
            }
            for candidate in payload.candidates
        ],
    }


def build_candidate_history_bundle(
    *,
    candidate: MarketScanCandidate,
    cycle_id: str,
    context_root: Path,
    symbol_catalog: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    market_symbols = resolve_market_symbols(
        subject=candidate.subject,
        scope=candidate.scope,
        symbol_catalog=symbol_catalog,
        spot_symbol=candidate.spot_symbol,
        usdm_symbol=candidate.usdm_symbol,
    )
    context = build_ohlcv_context(
        market_symbols=market_symbols,
        scope=candidate.scope,
    )
    context_json_path = context_root / f"{cycle_id}.ohlcv_context.json"
    context_md_path = context_root / f"{cycle_id}.ohlcv_context.md"
    write_ohlcv_context_bundle(
        context=context,
        json_path=context_json_path,
        markdown_path=context_md_path,
    )
    return market_symbols, context["history_coverage"], str(context_json_path.resolve())


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower())
    normalized = normalized.strip("-")
    return normalized or "scan"


def _require_positive_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return number


def _require_score(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a numeric score between 0 and 100") from exc
    if number < 0 or number > 100:
        raise ValueError(f"{field_name} must be between 0 and 100")
    return number


def _optional_symbol(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


if __name__ == "__main__":
    raise SystemExit(main())
