from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import TRUST_ROOT_DIR_ENV
from enhengclaw.integrations.openclaw._continue_existing import OpenClawContinueExistingRequest
from enhengclaw.integrations.openclaw._continue_existing_specs import (
    EVIDENCE_AGENT_LANE,
    RESEARCH_LEAD_LANE,
    RESEARCH_SYNTHESIZER_LANE,
    RISK_SIGNAL_AGENT_LANE,
)
from enhengclaw.integrations.openclaw.market_observer import (
    OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
    OpenClawMarketObserverRequest,
    governed_runtime_session_path,
)
from scripts.openclaw._market_observer_live_inputs import _utc_now
from scripts.openclaw._research_workbench_inputs import (
    provision_openclaw_research_inputs,
    resolve_openclaw_research_operator_env,
)
from scripts.market_data.binance_ohlcv import (
    build_ohlcv_context,
    build_ohlcv_context_text,
    load_ohlcv_context_from_ref,
    load_symbol_catalog,
    resolve_market_symbols,
    write_ohlcv_context_bundle,
)


DEFAULT_SCOPE = "spot+perp"
STRATEGY_PROFILES = ("conservative", "balanced", "aggressive")
ASSET_BUCKETS = ("large_cap", "mid_cap", "small_cap")
API_LABELS = {
    "ohlcv_history": "行情历史 API",
    "onchain_timeseries": "链上数据 API",
    "structured_news_archive": "资讯归档 API",
}
KNOWN_GAP_CATEGORIES = ("ohlcv_history", "onchain_timeseries", "structured_news_archive", "other")
API_LABELS = {
    "ohlcv_history": "行情历史 API",
    "onchain_timeseries": "链上数据 API",
    "structured_news_archive": "资讯归档 API",
}
PAIN_LOG_HEADERS = (
    "object_id",
    "subject",
    "cycle_date",
    "cycle_id",
    "strategy_profile",
    "asset_bucket",
    "gap_category",
    "blocking",
    "missing_question",
    "notes",
    "candidate_api_type",
)


@dataclass(frozen=True, slots=True)
class ResearchCyclePainLog:
    gap_category: str
    blocking: bool
    missing_question: str
    notes: str

    @classmethod
    def from_payload(cls, payload: Any) -> "ResearchCyclePainLog | None":
        if payload is None or payload == "":
            return None
        if not isinstance(payload, dict):
            raise ValueError("pain_log must be a JSON object when present")
        gap_category = str(payload.get("gap_category", "")).strip()
        if not gap_category:
            return None
        if gap_category not in KNOWN_GAP_CATEGORIES:
            raise ValueError(f"pain_log.gap_category must be one of: {', '.join(KNOWN_GAP_CATEGORIES)}")
        missing_question = _require_non_empty_string(payload.get("missing_question"), "pain_log.missing_question")
        notes = _require_non_empty_string(payload.get("notes"), "pain_log.notes")
        blocking = _coerce_bool(payload.get("blocking"))
        return cls(
            gap_category=gap_category,
            blocking=blocking,
            missing_question=missing_question,
            notes=notes,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "gap_category": self.gap_category,
            "blocking": self.blocking,
            "missing_question": self.missing_question,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ResearchCycleSnapshot:
    cycle_id: str
    cycle_date: str
    object_id: str
    subject: str
    scope: str
    strategy_profile: str
    asset_bucket: str
    market_symbols: dict[str, Any] | None
    history_coverage: dict[str, Any] | None
    ohlcv_context_ref: str | None
    observation: str
    evidence: str
    risk: str
    next_step: str
    pain_log: ResearchCyclePainLog | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ResearchCycleSnapshot":
        if not isinstance(payload, dict):
            raise ValueError("snapshot payload must be a JSON object")
        return cls(
            cycle_id=_require_non_empty_string(payload.get("cycle_id"), "cycle_id"),
            cycle_date=_require_non_empty_string(payload.get("cycle_date"), "cycle_date"),
            object_id=_require_non_empty_string(payload.get("object_id"), "object_id"),
            subject=_require_non_empty_string(payload.get("subject"), "subject"),
            scope=str(payload.get("scope", DEFAULT_SCOPE)).strip() or DEFAULT_SCOPE,
            strategy_profile=_require_enum_string(payload.get("strategy_profile"), "strategy_profile", STRATEGY_PROFILES),
            asset_bucket=_require_enum_string(payload.get("asset_bucket"), "asset_bucket", ASSET_BUCKETS),
            market_symbols=_coerce_optional_dict(payload.get("market_symbols"), "market_symbols"),
            history_coverage=_coerce_optional_dict(payload.get("history_coverage"), "history_coverage"),
            ohlcv_context_ref=_optional_string(payload.get("ohlcv_context_ref")),
            observation=_require_non_empty_string(payload.get("observation"), "observation"),
            evidence=_require_non_empty_string(payload.get("evidence"), "evidence"),
            risk=_require_non_empty_string(payload.get("risk"), "risk"),
            next_step=_require_non_empty_string(payload.get("next_step"), "next_step"),
            pain_log=ResearchCyclePainLog.from_payload(payload.get("pain_log")),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "cycle_id": self.cycle_id,
            "cycle_date": self.cycle_date,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "strategy_profile": self.strategy_profile,
            "asset_bucket": self.asset_bucket,
            "market_symbols": self.market_symbols,
            "history_coverage": self.history_coverage,
            "ohlcv_context_ref": self.ohlcv_context_ref,
            "observation": self.observation,
            "evidence": self.evidence,
            "risk": self.risk,
            "next_step": self.next_step,
        }
        if self.pain_log is not None:
            payload["pain_log"] = self.pain_log.to_payload()
        return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one scheduler-safe external OpenClaw research cycle against the governed thesis workbench."
    )
    parser.add_argument("--snapshot", type=Path, required=True, help="Path to the normalized snapshot JSON for one cycle.")
    parser.add_argument(
        "--workbench-root",
        type=Path,
        default=ROOT / "artifacts" / "research_workbench",
        help="Research workbench root. Defaults to artifacts\\research_workbench.",
    )
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help="External provisioning root. Defaults to %%LOCALAPPDATA%%\\EnhengClaw\\openclaw_research_workbench.",
    )
    parser.add_argument(
        "--trust-root-dir",
        type=Path,
        default=None,
        help="Read-only trust root for permit validation. Defaults to C:\\ProgramData\\EnhengClaw\\trust.",
    )
    parser.add_argument(
        "--compiler-backend",
        choices=("live", "deterministic"),
        default="live",
        help="Compiler backend for the research cycle. Defaults to live.",
    )
    parser.add_argument(
        "--expires-after-hours",
        type=int,
        default=24,
        help="Permit lifetime in hours. Defaults to 24.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_openclaw_research_cycle(
            snapshot_path=args.snapshot,
            workbench_root=args.workbench_root,
            external_root=args.external_root,
            trust_root_dir=args.trust_root_dir,
            compiler_backend=args.compiler_backend,
            expires_after_hours=args.expires_after_hours,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"[openclaw-research-cycle] cycle_summary={result['cycle_summary_path']}")
    print(f"[openclaw-research-cycle] status={result['status']}")
    reminder = result.get("api_reminder")
    if isinstance(reminder, dict) and reminder.get("reminder_triggered"):
        print(f"[openclaw-research-cycle] api_reminder={reminder.get('recommended_api_label')}")
    return 0 if result["status"] == "success" else 1


def run_openclaw_research_cycle(
    *,
    snapshot_path: Path,
    workbench_root: Path,
    external_root: Path | None = None,
    trust_root_dir: Path | None = None,
    compiler_backend: str = "live",
    expires_after_hours: int = 24,
    base_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if compiler_backend not in {"live", "deterministic"}:
        raise ValueError("compiler_backend must be one of: live, deterministic")
    snapshot_payload = _read_json_file(snapshot_path)
    snapshot = ResearchCycleSnapshot.from_payload(snapshot_payload)
    resolved_workbench_root = workbench_root.expanduser().resolve()
    thesis_root = (resolved_workbench_root / snapshot.object_id).resolve()
    cycle_root = thesis_root / "cycles" / snapshot.cycle_id
    if cycle_root.exists():
        raise FileExistsError(f"research cycle already exists for object_id={snapshot.object_id}: {snapshot.cycle_id}")
    cycle_root.mkdir(parents=True, exist_ok=False)
    normalized_snapshot_path = cycle_root / "snapshot.normalized.json"
    _write_json_file(normalized_snapshot_path, snapshot.to_payload())

    existing_object_before_cycle = _object_exists(thesis_root, snapshot.object_id)
    summary: dict[str, Any] = {
        "status": "failed",
        "cycle_id": snapshot.cycle_id,
        "cycle_date": snapshot.cycle_date,
        "object_id": snapshot.object_id,
        "subject": snapshot.subject,
        "scope": snapshot.scope,
        "strategy_profile": snapshot.strategy_profile,
        "asset_bucket": snapshot.asset_bucket,
        "compiler_backend": compiler_backend,
        "snapshot_path": str(normalized_snapshot_path),
        "source_snapshot_path": str(snapshot_path.resolve()),
        "workbench_root": str(resolved_workbench_root),
        "thesis_root": str(thesis_root),
        "cycle_root": str(cycle_root),
        "created_new_object": False,
        "existing_object_before_cycle": existing_object_before_cycle,
        "lane_results": {},
        "api_reminder": None,
        "generated_at_utc": _utc_now(),
    }
    cycle_summary_path = cycle_root / "cycle_summary.json"

    try:
        source_env = dict(os.environ if base_env is None else base_env)
        child_env, env_meta = resolve_openclaw_research_operator_env(source_env)
        child_env = _build_pythonpath_env(child_env)
        summary["live_env_mode"] = env_meta["live_env_mode"]
        summary["openclaw_mapping_used_by_lane"] = env_meta["openclaw_mapping_used_by_lane"]
        symbol_catalog = load_symbol_catalog(base_env=source_env)
        market_symbols = resolve_snapshot_market_symbols(snapshot=snapshot, symbol_catalog=symbol_catalog)
        ohlcv_context = load_ohlcv_context_from_ref(snapshot.ohlcv_context_ref)
        if ohlcv_context is None:
            ohlcv_context = build_ohlcv_context(
                market_symbols=market_symbols,
                scope=snapshot.scope,
            )
        history_coverage = snapshot.history_coverage or ohlcv_context.get("history_coverage", {})
        ohlcv_context_json_path = cycle_root / "ohlcv_context.json"
        ohlcv_context_md_path = cycle_root / "ohlcv_context.md"
        write_ohlcv_context_bundle(
            context=ohlcv_context,
            json_path=ohlcv_context_json_path,
            markdown_path=ohlcv_context_md_path,
        )
        summary["market_symbols"] = market_symbols
        summary["history_coverage"] = history_coverage
        summary["ohlcv_context_json_path"] = str(ohlcv_context_json_path.resolve())
        summary["ohlcv_context_md_path"] = str(ohlcv_context_md_path.resolve())
        summary["ohlcv_context_ref"] = str(ohlcv_context_json_path.resolve())

        lane_results: dict[str, Any] = {}
        active_provision_summary: dict[str, Any] | None = None

        def provision_lane_inputs() -> dict[str, Any]:
            nonlocal active_provision_summary
            active_provision_summary = provision_openclaw_research_inputs(
                external_root=external_root,
                trust_root_dir=trust_root_dir,
                expires_after_hours=expires_after_hours,
                base_env=source_env,
            )
            child_env[TRUST_ROOT_DIR_ENV] = str(active_provision_summary["trust_root_dir"])
            if "provisioning_summary_path" not in summary:
                summary["provisioning_summary_path"] = str(active_provision_summary["summary_path"])
                summary["permit_path"] = str(active_provision_summary["permit_path"])
                summary["trust_root_dir"] = str(active_provision_summary["trust_root_dir"])
                summary["external_root"] = str(active_provision_summary["external_root"])
            return active_provision_summary

        market_needed = not existing_object_before_cycle
        if market_needed:
            market_permit = provision_lane_inputs()
            market_result = _run_market_observer_lane(
                snapshot=snapshot,
                compiler_backend=compiler_backend,
                permit_path=Path(str(market_permit["permit_path"])),
                thesis_root=thesis_root,
                cycle_root=cycle_root,
                env=child_env,
            )
            market_result["permit_summary_path"] = str(market_permit["summary_path"])
            market_result["permit_path"] = str(market_permit["permit_path"])
            market_result["permit_id"] = market_permit.get("permit_id")
            lane_results["market_observer"] = market_result
            summary["lane_results"] = lane_results
            _require_lane_success("market_observer", market_result)
            summary["created_new_object"] = True
        else:
            lane_results["market_observer"] = {
                "status": "skipped",
                "reason": "existing_object_detected",
                "request_path": None,
                "response_path": None,
                "stdout_path": None,
                "stderr_path": None,
            }
            summary["lane_results"] = lane_results

        thesis_profile = ensure_thesis_profile(
            thesis_root=thesis_root,
            snapshot=snapshot,
            market_symbols=market_symbols,
            history_coverage=history_coverage,
            ohlcv_context_ref=str(ohlcv_context_json_path.resolve()),
        )
        summary["thesis_profile_path"] = str((thesis_root / "thesis_profile.json").resolve())
        summary["thesis_profile"] = thesis_profile

        evidence_text = _build_evidence_text(snapshot, ohlcv_context)
        synthesis_text = _build_synthesis_text(snapshot, ohlcv_context)
        for lane_spec, text_value in (
            (EVIDENCE_AGENT_LANE, evidence_text),
            (RISK_SIGNAL_AGENT_LANE, snapshot.risk),
            (RESEARCH_SYNTHESIZER_LANE, synthesis_text),
            (RESEARCH_LEAD_LANE, snapshot.next_step),
        ):
            lane_permit = provision_lane_inputs()
            lane_result = _run_continue_existing_lane(
                lane_spec=lane_spec,
                snapshot=snapshot,
                text_value=text_value,
                compiler_backend=compiler_backend,
                permit_path=Path(str(lane_permit["permit_path"])),
                thesis_root=thesis_root,
                cycle_root=cycle_root,
                env=child_env,
            )
            lane_result["permit_summary_path"] = str(lane_permit["summary_path"])
            lane_result["permit_path"] = str(lane_permit["permit_path"])
            lane_result["permit_id"] = lane_permit.get("permit_id")
            lane_results[lane_spec.agent_id] = lane_result
            summary["lane_results"] = lane_results
            _require_lane_success(lane_spec.agent_id, lane_result)

        pain_log_path = thesis_root / "pain_log.csv"
        pain_log_row = append_pain_log(
            pain_log_path=pain_log_path,
            snapshot=snapshot,
            history_coverage=history_coverage,
            ohlcv_context=ohlcv_context,
        )
        api_summary = evaluate_api_gap_summary(workbench_root=resolved_workbench_root)
        write_api_gap_summaries(workbench_root=resolved_workbench_root, summary=api_summary)
        pool_summary = evaluate_research_pool_summary(workbench_root=resolved_workbench_root)
        write_research_pool_summaries(workbench_root=resolved_workbench_root, summary=pool_summary)

        summary["pain_log_path"] = str(pain_log_path)
        summary["pain_log_recorded"] = pain_log_row is not None
        summary["pain_log_entry"] = pain_log_row
        summary["api_gap_summary_json_path"] = str((resolved_workbench_root / "api_gap_summary.json").resolve())
        summary["api_gap_summary_md_path"] = str((resolved_workbench_root / "api_gap_summary.md").resolve())
        summary["research_pool_summary_json_path"] = str(
            (resolved_workbench_root / "research_pool_summary.json").resolve()
        )
        summary["research_pool_summary_md_path"] = str(
            (resolved_workbench_root / "research_pool_summary.md").resolve()
        )
        summary["api_reminder"] = api_summary["recommendation"]
        summary["status"] = "success"
        _write_json_file(cycle_summary_path, summary)
        summary["cycle_summary_path"] = str(cycle_summary_path)
        return summary
    except Exception as exc:
        summary["error"] = str(exc)
        _write_json_file(cycle_summary_path, summary)
        summary["cycle_summary_path"] = str(cycle_summary_path)
        return summary


def append_pain_log(
    *,
    pain_log_path: Path,
    snapshot: ResearchCycleSnapshot,
    history_coverage: dict[str, Any],
    ohlcv_context: dict[str, Any],
) -> dict[str, str] | None:
    effective_pain_log = _resolve_effective_pain_log(
        snapshot=snapshot,
        history_coverage=history_coverage,
        ohlcv_context=ohlcv_context,
    )
    if effective_pain_log is None:
        return None
    pain_log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "object_id": snapshot.object_id,
        "subject": snapshot.subject,
        "cycle_date": snapshot.cycle_date,
        "cycle_id": snapshot.cycle_id,
        "strategy_profile": snapshot.strategy_profile,
        "asset_bucket": snapshot.asset_bucket,
        "gap_category": effective_pain_log.gap_category,
        "blocking": "true" if effective_pain_log.blocking else "false",
        "missing_question": effective_pain_log.missing_question,
        "notes": effective_pain_log.notes,
        "candidate_api_type": API_LABELS.get(effective_pain_log.gap_category, ""),
    }
    write_header = not pain_log_path.exists()
    with pain_log_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIN_LOG_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return row


def evaluate_api_gap_summary(*, workbench_root: Path) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    thesis_profiles = load_thesis_profiles(workbench_root=workbench_root)
    ohlcv_gap_active = (
        not thesis_profiles
        or any(str(profile.get("history_coverage_status", "missing")).strip() != "full" for profile in thesis_profiles)
    )
    if workbench_root.exists():
        for pain_log_path in sorted(workbench_root.glob("*/pain_log.csv")):
            with pain_log_path.open("r", encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))

    categories: dict[str, dict[str, Any]] = {}
    for category in KNOWN_GAP_CATEGORIES:
        category_rows = [row for row in rows if str(row.get("gap_category", "")).strip() == category]
        thesis_ids = {row["object_id"] for row in category_rows if row.get("object_id")}
        blocking_rows = [row for row in category_rows if _coerce_bool(row.get("blocking"))]
        blocking_objects = {row["object_id"] for row in blocking_rows if row.get("object_id")}
        current_gap_remaining = True
        if category == "ohlcv_history":
            current_gap_remaining = ohlcv_gap_active
        categories[category] = {
            "gap_category": category,
            "cycle_count": len(category_rows),
            "thesis_count": len(thesis_ids),
            "blocking_count": len(blocking_rows),
            "blocking_object_count": len(blocking_objects),
            "candidate_api_type": API_LABELS.get(category),
            "cycle_count_by_strategy_profile": _count_rows_by_key(category_rows, "strategy_profile"),
            "cycle_count_by_asset_bucket": _count_rows_by_key(category_rows, "asset_bucket"),
            "blocking_count_by_strategy_profile": _count_rows_by_key(blocking_rows, "strategy_profile"),
            "blocking_count_by_asset_bucket": _count_rows_by_key(blocking_rows, "asset_bucket"),
            "current_gap_remaining": current_gap_remaining,
            "threshold_reached": (
                current_gap_remaining
                and (len(thesis_ids) >= 3 or len(category_rows) >= 5 or len(blocking_objects) >= 2)
            ),
        }

    eligible_categories = [
        category_summary
        for category_summary in categories.values()
        if category_summary["threshold_reached"] and category_summary["candidate_api_type"]
    ]
    eligible_categories.sort(
        key=lambda item: (
            int(item["cycle_count"]),
            int(item["blocking_count"]),
            int(item["thesis_count"]),
            str(item["gap_category"]),
        ),
        reverse=True,
    )
    if eligible_categories:
        chosen = eligible_categories[0]
        recommendation: dict[str, Any] = {
            "reminder_triggered": True,
            "recommended_gap_category": chosen["gap_category"],
            "recommended_api_label": chosen["candidate_api_type"],
            "cycle_count": chosen["cycle_count"],
            "thesis_count": chosen["thesis_count"],
            "blocking_count": chosen["blocking_count"],
            "blocking_object_count": chosen["blocking_object_count"],
            "reason": "gap threshold reached; add only one external API class next",
        }
    else:
        recommendation = {
            "reminder_triggered": False,
            "recommended_gap_category": None,
            "recommended_api_label": None,
            "reason": "no single API gap category has crossed the pilot threshold",
        }

    return {
        "generated_at_utc": _utc_now(),
        "workbench_root": str(workbench_root.resolve()),
        "total_pain_log_rows": len(rows),
        "categories": categories,
        "recommendation": recommendation,
    }


def write_api_gap_summaries(*, workbench_root: Path, summary: dict[str, Any]) -> None:
    json_path = workbench_root / "api_gap_summary.json"
    md_path = workbench_root / "api_gap_summary.md"
    _write_json_file(json_path, summary)
    lines = [
        "# API Gap Summary",
        "",
        f"- Generated at: `{summary['generated_at_utc']}`",
        f"- Total pain-log rows: `{summary['total_pain_log_rows']}`",
        "",
        "## Recommendation",
        "",
    ]
    recommendation = summary["recommendation"]
    if recommendation["reminder_triggered"]:
        lines.extend(
            [
                f"- Recommended next API: `{recommendation['recommended_api_label']}`",
                f"- Gap category: `{recommendation['recommended_gap_category']}`",
                f"- Frequency: `{recommendation['cycle_count']}` cycles across `{recommendation['thesis_count']}` theses",
                f"- Blocking count: `{recommendation['blocking_count']}` rows across `{recommendation['blocking_object_count']}` theses",
            ]
        )
    else:
        lines.append("- No external API class should be added yet.")
    lines.extend(["", "## Category Counts", ""])
    for category in KNOWN_GAP_CATEGORIES:
        category_summary = summary["categories"][category]
        lines.append(
            "- `{gap_category}`: cycles=`{cycle_count}`, theses=`{thesis_count}`, blocking_rows=`{blocking_count}`, "
            "blocking_theses=`{blocking_object_count}`, current_gap_remaining=`{current_gap_remaining}`, "
            "threshold_reached=`{threshold_reached}`".format(**category_summary)
        )
        lines.append(
            "  strategy_profile_counts="
            + ", ".join(
                f"{profile}:{category_summary['cycle_count_by_strategy_profile'][profile]}"
                for profile in STRATEGY_PROFILES
            )
        )
        lines.append(
            "  asset_bucket_counts="
            + ", ".join(
                f"{bucket}:{category_summary['cycle_count_by_asset_bucket'][bucket]}"
                for bucket in ASSET_BUCKETS
            )
        )
    _write_text_file(md_path, "\n".join(lines) + "\n")


def evaluate_research_pool_summary(*, workbench_root: Path) -> dict[str, Any]:
    thesis_profiles = load_thesis_profiles(workbench_root=workbench_root)
    strategy_distribution = {profile: 0 for profile in STRATEGY_PROFILES}
    asset_bucket_distribution = {bucket: 0 for bucket in ASSET_BUCKETS}
    thesis_ids_by_strategy = {profile: [] for profile in STRATEGY_PROFILES}
    thesis_ids_by_bucket = {bucket: [] for bucket in ASSET_BUCKETS}
    ohlcv_coverage_by_strategy_profile = {profile: {"full": 0, "partial": 0, "missing": 0} for profile in STRATEGY_PROFILES}
    ohlcv_coverage_by_asset_bucket = {bucket: {"full": 0, "partial": 0, "missing": 0} for bucket in ASSET_BUCKETS}
    ohlcv_ready_thesis_count = 0
    for thesis in thesis_profiles:
        strategy_distribution[thesis["strategy_profile"]] += 1
        asset_bucket_distribution[thesis["asset_bucket"]] += 1
        thesis_ids_by_strategy[thesis["strategy_profile"]].append(thesis["object_id"])
        thesis_ids_by_bucket[thesis["asset_bucket"]].append(thesis["object_id"])
        coverage_status = str(thesis.get("history_coverage_status", "missing")).strip()
        if coverage_status not in {"full", "partial", "missing"}:
            coverage_status = "missing"
        ohlcv_coverage_by_strategy_profile[thesis["strategy_profile"]][coverage_status] += 1
        ohlcv_coverage_by_asset_bucket[thesis["asset_bucket"]][coverage_status] += 1
        if thesis.get("ohlcv_ready"):
            ohlcv_ready_thesis_count += 1

    rows: list[dict[str, str]] = []
    if workbench_root.exists():
        for pain_log_path in sorted(workbench_root.glob("*/pain_log.csv")):
            with pain_log_path.open("r", encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))

    pain_gap_counts_by_strategy_profile = {
        category: {profile: 0 for profile in STRATEGY_PROFILES}
        for category in KNOWN_GAP_CATEGORIES
    }
    pain_gap_counts_by_asset_bucket = {
        category: {bucket: 0 for bucket in ASSET_BUCKETS}
        for category in KNOWN_GAP_CATEGORIES
    }
    for row in rows:
        category = str(row.get("gap_category", "")).strip()
        strategy_profile = str(row.get("strategy_profile", "")).strip()
        asset_bucket = str(row.get("asset_bucket", "")).strip()
        if category in pain_gap_counts_by_strategy_profile and strategy_profile in STRATEGY_PROFILES:
            pain_gap_counts_by_strategy_profile[category][strategy_profile] += 1
        if category in pain_gap_counts_by_asset_bucket and asset_bucket in ASSET_BUCKETS:
            pain_gap_counts_by_asset_bucket[category][asset_bucket] += 1

    return {
        "generated_at_utc": _utc_now(),
        "workbench_root": str(workbench_root.resolve()),
        "thesis_count": len(thesis_profiles),
        "thesis_profiles": thesis_profiles,
        "strategy_profile_distribution": strategy_distribution,
        "asset_bucket_distribution": asset_bucket_distribution,
        "thesis_ids_by_strategy_profile": thesis_ids_by_strategy,
        "thesis_ids_by_asset_bucket": thesis_ids_by_bucket,
        "missing_asset_bucket_coverage": [bucket for bucket in ASSET_BUCKETS if asset_bucket_distribution[bucket] == 0],
        "missing_strategy_profile_coverage": [
            profile for profile in STRATEGY_PROFILES if strategy_distribution[profile] == 0
        ],
        "ohlcv_ready_thesis_count": ohlcv_ready_thesis_count,
        "ohlcv_coverage_by_strategy_profile": ohlcv_coverage_by_strategy_profile,
        "ohlcv_coverage_by_asset_bucket": ohlcv_coverage_by_asset_bucket,
        "pain_gap_counts_by_strategy_profile": pain_gap_counts_by_strategy_profile,
        "pain_gap_counts_by_asset_bucket": pain_gap_counts_by_asset_bucket,
    }


def write_research_pool_summaries(*, workbench_root: Path, summary: dict[str, Any]) -> None:
    json_path = workbench_root / "research_pool_summary.json"
    md_path = workbench_root / "research_pool_summary.md"
    _write_json_file(json_path, summary)
    lines = [
        "# Research Pool Summary",
        "",
        f"- Generated at: `{summary['generated_at_utc']}`",
        f"- Thesis count: `{summary['thesis_count']}`",
        "",
        "## Strategy Profile Distribution",
        "",
    ]
    for profile in STRATEGY_PROFILES:
        lines.append(f"- `{profile}`: `{summary['strategy_profile_distribution'][profile]}`")
    lines.extend(["", "## Asset Bucket Distribution", ""])
    for bucket in ASSET_BUCKETS:
        lines.append(f"- `{bucket}`: `{summary['asset_bucket_distribution'][bucket]}`")
    lines.extend(
        [
            "",
            "## Missing Coverage",
            "",
            f"- Missing asset buckets: `{', '.join(summary['missing_asset_bucket_coverage']) or 'none'}`",
            f"- Missing strategy profiles: `{', '.join(summary['missing_strategy_profile_coverage']) or 'none'}`",
            f"- OHLCV-ready theses: `{summary['ohlcv_ready_thesis_count']}`",
            "",
            "## OHLCV Coverage",
            "",
        ]
    )
    for profile in STRATEGY_PROFILES:
        coverage = summary["ohlcv_coverage_by_strategy_profile"][profile]
        lines.append(
            f"- `{profile}` ohlcv: full={coverage['full']}, partial={coverage['partial']}, missing={coverage['missing']}"
        )
    for bucket in ASSET_BUCKETS:
        coverage = summary["ohlcv_coverage_by_asset_bucket"][bucket]
        lines.append(
            f"- `{bucket}` ohlcv: full={coverage['full']}, partial={coverage['partial']}, missing={coverage['missing']}"
        )
    lines.extend(
        [
            "",
            "## Pain-Log Gap Counts",
            "",
        ]
    )
    for category in KNOWN_GAP_CATEGORIES:
        strategy_counts = ", ".join(
            f"{profile}={summary['pain_gap_counts_by_strategy_profile'][category][profile]}"
            for profile in STRATEGY_PROFILES
        )
        bucket_counts = ", ".join(
            f"{bucket}={summary['pain_gap_counts_by_asset_bucket'][category][bucket]}"
            for bucket in ASSET_BUCKETS
        )
        lines.append(f"- `{category}` strategy: {strategy_counts}")
        lines.append(f"- `{category}` bucket: {bucket_counts}")
    _write_text_file(md_path, "\n".join(lines) + "\n")
def ensure_thesis_profile(
    *,
    thesis_root: Path,
    snapshot: ResearchCycleSnapshot,
    market_symbols: dict[str, Any],
    history_coverage: dict[str, Any],
    ohlcv_context_ref: str | None,
) -> dict[str, Any]:
    thesis_root.mkdir(parents=True, exist_ok=True)
    profile_path = thesis_root / "thesis_profile.json"
    created_at_utc = _utc_now()
    if _path_exists(profile_path):
        existing_profile = _read_json_file(profile_path)
        _validate_stable_thesis_metadata(existing_profile=existing_profile, snapshot=snapshot)
        created_at_utc = str(existing_profile.get("created_at_utc") or created_at_utc)
    profile = {
        "object_id": snapshot.object_id,
        "subject": snapshot.subject,
        "scope": snapshot.scope,
        "strategy_profile": snapshot.strategy_profile,
        "asset_bucket": snapshot.asset_bucket,
        "market_symbols": market_symbols,
        "history_coverage_status": history_coverage.get("status", "missing"),
        "history_coverage": history_coverage,
        "ohlcv_ready": history_coverage.get("status") == "full",
        "ohlcv_context_ref": ohlcv_context_ref,
        "created_at_utc": created_at_utc,
        "updated_at_utc": _utc_now(),
    }
    _write_json_file(profile_path, profile)
    return profile


def load_thesis_profiles(*, workbench_root: Path) -> list[dict[str, Any]]:
    if not workbench_root.exists():
        return []
    profiles: list[dict[str, Any]] = []
    for candidate in sorted(workbench_root.iterdir()):
        if not candidate.is_dir() or candidate.name.startswith("_"):
            continue
        profile_path = candidate / "thesis_profile.json"
        if not _path_exists(profile_path):
            continue
        payload = _read_json_file(profile_path)
        strategy_profile = str(payload.get("strategy_profile", "")).strip()
        asset_bucket = str(payload.get("asset_bucket", "")).strip()
        if strategy_profile not in STRATEGY_PROFILES or asset_bucket not in ASSET_BUCKETS:
            continue
        profiles.append(payload)
    return profiles


def _run_market_observer_lane(
    *,
    snapshot: ResearchCycleSnapshot,
    compiler_backend: str,
    permit_path: Path,
    thesis_root: Path,
    cycle_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    request = OpenClawMarketObserverRequest(
        contract_version=OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
        subject=snapshot.subject,
        scope=snapshot.scope,
        object_id=snapshot.object_id,
        observation_text=snapshot.observation,
        execution_permit_path=str(permit_path),
        input_id=f"{snapshot.cycle_id}:market_observer",
        artifacts_root=str(thesis_root),
        compiler_backend=compiler_backend,
    )
    return _run_lane_cli(
        lane_id="market_observer",
        module_name="enhengclaw.integrations.openclaw.market_observer",
        request_payload=request.to_payload(),
        cycle_root=cycle_root,
        env=env,
    )


def _run_continue_existing_lane(
    *,
    lane_spec,
    snapshot: ResearchCycleSnapshot,
    text_value: str,
    compiler_backend: str,
    permit_path: Path,
    thesis_root: Path,
    cycle_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    request = OpenClawContinueExistingRequest(
        contract_version=lane_spec.contract_version,
        subject=snapshot.subject,
        scope=snapshot.scope,
        object_id=snapshot.object_id,
        text_value=text_value,
        execution_permit_path=str(permit_path),
        input_id=f"{snapshot.cycle_id}:{lane_spec.agent_id}",
        artifacts_root=str(thesis_root),
        compiler_backend=compiler_backend,
    )
    return _run_lane_cli(
        lane_id=lane_spec.agent_id,
        module_name=lane_spec.entrypoint_module,
        request_payload=request.to_payload(text_field_name=lane_spec.text_field_name),
        cycle_root=cycle_root,
        env=env,
    )


def _run_lane_cli(
    *,
    lane_id: str,
    module_name: str,
    request_payload: dict[str, Any],
    cycle_root: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    request_path = cycle_root / f"{lane_id}.request.json"
    response_path = cycle_root / f"{lane_id}.response.json"
    stdout_path = cycle_root / f"{lane_id}.stdout.log"
    stderr_path = cycle_root / f"{lane_id}.stderr.log"
    _write_json_file(request_path, request_payload)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            module_name,
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    _write_text_file(stdout_path, completed.stdout or "", errors="replace")
    _write_text_file(stderr_path, completed.stderr or "", errors="replace")
    response_payload = _read_json_file(response_path) if _path_exists(response_path) else None
    return {
        "status": None if response_payload is None else response_payload.get("status"),
        "exit_code": completed.returncode,
        "request_path": str(request_path),
        "response_path": str(response_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "response": response_payload,
    }


def _require_lane_success(lane_id: str, lane_result: dict[str, Any]) -> None:
    if int(lane_result["exit_code"]) != 0:
        raise RuntimeError(f"{lane_id} adapter exited with code {lane_result['exit_code']}")
    response = lane_result.get("response")
    if not isinstance(response, dict):
        raise RuntimeError(f"{lane_id} adapter did not produce a JSON response")
    if response.get("status") != "success":
        blocked_reason = response.get("blocked_reason") or response.get("quarantine_reason") or response.get("error")
        raise RuntimeError(f"{lane_id} did not finalize successfully: {blocked_reason}")


def resolve_snapshot_market_symbols(
    *,
    snapshot: ResearchCycleSnapshot,
    symbol_catalog: dict[str, Any],
) -> dict[str, Any]:
    explicit_symbols = snapshot.market_symbols or {}
    return resolve_market_symbols(
        subject=snapshot.subject,
        scope=snapshot.scope,
        symbol_catalog=symbol_catalog,
        spot_symbol=_optional_string(explicit_symbols.get("spot_symbol")),
        usdm_symbol=_optional_string(explicit_symbols.get("usdm_symbol")),
    )


def _build_evidence_text(snapshot: ResearchCycleSnapshot, ohlcv_context: dict[str, Any]) -> str:
    return (
        f"{snapshot.evidence}\n\n"
        "Historical OHLCV context:\n"
        f"{build_ohlcv_context_text(ohlcv_context)}"
    )


def _build_synthesis_text(snapshot: ResearchCycleSnapshot, ohlcv_context: dict[str, Any]) -> str:
    return (
        f"Scheduled cycle {snapshot.cycle_id} observation: {snapshot.observation}\n"
        f"Supporting evidence: {snapshot.evidence}\n"
        f"Current risk or invalidation: {snapshot.risk}\n"
        "Historical OHLCV context:\n"
        f"{build_ohlcv_context_text(ohlcv_context)}"
    )


def _resolve_effective_pain_log(
    *,
    snapshot: ResearchCycleSnapshot,
    history_coverage: dict[str, Any],
    ohlcv_context: dict[str, Any],
) -> ResearchCyclePainLog | None:
    snapshot_pain_log = snapshot.pain_log
    coverage_status = str(history_coverage.get("status", "missing")).strip() or "missing"
    breakout_ready = bool(history_coverage.get("breakout_comparison_ready"))

    if snapshot_pain_log is not None and snapshot_pain_log.gap_category != "ohlcv_history":
        return snapshot_pain_log

    if coverage_status == "full" and breakout_ready:
        return None

    if snapshot_pain_log is not None:
        return snapshot_pain_log

    if coverage_status != "full":
        return ResearchCyclePainLog(
            gap_category="ohlcv_history",
            blocking=False,
            missing_question="Default OHLCV coverage thresholds are not yet satisfied for this thesis.",
            notes=(
                "Local Binance OHLCV history coverage is "
                f"{coverage_status}; sync the historical store before relying on prior-breakout comparisons."
            ),
        )

    market_symbols = ohlcv_context.get("market_symbols", {})
    available_markets = ", ".join(
        market_type
        for market_type, symbol in (
            ("spot", market_symbols.get("spot_symbol")),
            ("usdm_perp", market_symbols.get("usdm_symbol")),
        )
        if symbol
    ) or "none"
    return ResearchCyclePainLog(
        gap_category="ohlcv_history",
        blocking=False,
        missing_question="I still cannot compare the current structure cleanly to the last three multi-week breakouts.",
        notes=(
            "OHLCV bars are present but the 1d breakout comparison is still unavailable for "
            f"markets={available_markets}."
        ),
    )


def _object_exists(thesis_root: Path, object_id: str) -> bool:
    return governed_runtime_session_path(artifacts_root=thesis_root, object_id=object_id).exists()


def _build_pythonpath_env(base_env: dict[str, str]) -> dict[str, str]:
    env = dict(base_env)
    pythonpath_parts = [str(ROOT), str(SRC)]
    existing = str(env.get("PYTHONPATH", "")).strip()
    if existing:
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    return env


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    _write_text_file(path, json.dumps(payload, indent=2, sort_keys=True))


def _read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(_read_text_file(path, encoding="utf-8-sig"))


def _path_exists(path: Path) -> bool:
    return os.path.exists(_runtime_io_path(path))


def _read_text_file(path: Path, *, encoding: str = "utf-8") -> str:
    with open(_runtime_io_path(path), "r", encoding=encoding) as handle:
        return handle.read()


def _write_text_file(path: Path, content: str, *, encoding: str = "utf-8", errors: str | None = None) -> None:
    os.makedirs(_runtime_io_path(path.parent), exist_ok=True)
    with open(_runtime_io_path(path), "w", encoding=encoding, errors=errors) as handle:
        handle.write(content)


def _runtime_io_path(path: Path) -> str:
    normalized = os.path.abspath(os.path.normpath(str(path.expanduser())))
    if os.name != "nt":
        return normalized
    if normalized.startswith("\\\\?\\"):
        return normalized
    if normalized.startswith("\\\\"):
        return "\\\\?\\UNC\\" + normalized[2:]
    return "\\\\?\\" + normalized


def _require_non_empty_string(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _require_enum_string(value: Any, field_name: str, allowed_values: tuple[str, ...]) -> str:
    text = _require_non_empty_string(value, field_name)
    if text not in allowed_values:
        raise ValueError(f"{field_name} must be one of: {', '.join(allowed_values)}")
    return text


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n", ""}:
        return False
    raise ValueError(f"unable to interpret boolean value: {value!r}")


def _coerce_optional_dict(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object when present")
    return dict(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _count_rows_by_key(rows: list[dict[str, str]], field_name: str) -> dict[str, int]:
    if field_name == "strategy_profile":
        allowed = STRATEGY_PROFILES
    elif field_name == "asset_bucket":
        allowed = ASSET_BUCKETS
    else:
        raise ValueError(f"unsupported grouped count field: {field_name}")
    counts = {value: 0 for value in allowed}
    for row in rows:
        value = str(row.get(field_name, "")).strip()
        if value in counts:
            counts[value] += 1
    return counts


def _validate_stable_thesis_metadata(*, existing_profile: dict[str, Any], snapshot: ResearchCycleSnapshot) -> None:
    mismatches: list[str] = []
    for field_name, expected_value in (
        ("object_id", snapshot.object_id),
        ("subject", snapshot.subject),
        ("scope", snapshot.scope),
        ("strategy_profile", snapshot.strategy_profile),
        ("asset_bucket", snapshot.asset_bucket),
    ):
        actual_value = str(existing_profile.get(field_name, "")).strip()
        if actual_value and actual_value != expected_value:
            mismatches.append(f"{field_name}={actual_value!r} != {expected_value!r}")
    if mismatches:
        raise ValueError(
            "thesis_profile.json metadata mismatch; open a new object_id instead of reclassifying in place: "
            + ", ".join(mismatches)
        )


if __name__ == "__main__":
    raise SystemExit(main())
