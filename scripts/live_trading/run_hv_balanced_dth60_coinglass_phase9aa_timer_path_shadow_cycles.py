from __future__ import annotations

import argparse
import csv
import copy
import json
import os
import sys
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.config import load_live_trading_config  # noqa: E402
from enhengclaw.live_trading.dth60_observe_only_shadow_hook import (  # noqa: E402
    ObserveOnlyShadowHookConfig,
    run_observe_only_shadow_hook,
)
from enhengclaw.live_trading.mainnet_live_supervisor import run_mainnet_live_supervisor  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate import (  # noqa: E402
    P9AA_GATE,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1"
APPROVE_P9AA_DECISION = "approve_p9aa_run_consecutive_timer_path_observe_only_shadow_cycles_no_order"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9aa_timer_shadow"
PHASE9Z_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9z_timer_path_readback_owner_gate"
DEFAULT_BASE_CONFIG = "config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_noorder_candidate.yaml"
P9Z_CONTRACT = "hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate.v1"


SupervisorRunner = Callable[..., tuple[dict[str, Any], int]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run consecutive no-order timer-path shadow cycles through the real "
            "mainnet_live_supervisor entrypoint, then write observe-only candidate "
            "shadow artifacts under proof_artifacts. Candidate execution and live "
            "order submission remain disabled."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9z-summary", default="")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--shadow-cycles", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--position-reference-source", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AA_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:request_p9y_p9z_p9aa")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def zero_orders_fills(payload: dict[str, Any]) -> bool:
    return int_zero(payload, "orders_submitted") and int_zero(payload, "fill_count")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AA_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aa_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "run_consecutive_timer_path_observe_only_shadow_cycles_no_order",
        "decision_effect": "run_local_no_order_timer_path_shadow_cycles" if approved else "none",
        "p9aa_timer_path_shadow_cycles_approved": approved,
        "supervisor_entrypoint_invocation_approved": approved,
        "observe_only_hook_enablement_approved": approved,
        "generated_no_order_config_approved": approved,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "remote_sync_approved": False,
        "repo_stage_change_approved": False,
    }


def p9z_ready(summary: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    owner = dict(summary.get("owner_decision") or {})
    required = (
        "owner_decision_p9z_gate_only",
        "project_stage_boundary_preserved",
        "p9y_owner_review_ready",
        "observe_only_shadow_readback_authorized",
        "default_off_implementation_required",
        "baseline_only_executor_input_required",
        "candidate_execution_forbidden",
        "live_order_submission_forbidden",
        "target_plan_replacement_forbidden",
        "executor_input_mutation_forbidden",
        "operator_state_mutation_forbidden",
        "production_timer_service_load_forbidden",
        "no_timer_path_execution_in_p9z",
        "no_supervisor_run_in_p9z",
        "no_remote_sync_in_p9z",
        "zero_orders_fills_in_p9z",
    )
    return (
        summary.get("contract_version") == P9Z_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9z_timer_path_readback_owner_gate_ready") is True
        and summary.get("eligible_for_p9aa_timer_path_shadow_cycles") is True
        and summary.get("allowed_next_gate") == P9AA_GATE
        and summary.get("observe_only_shadow_readback_authorized") is True
        and summary.get("future_p9aa_consecutive_cycles_required") == 3
        and summary.get("future_p9aa_supervisor_entrypoint_authorized") is True
        and summary.get("future_p9aa_observe_only_hook_enabled_authorized") is True
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("operator_state_mutation_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and owner.get("decision") == "approve_p9z_observe_only_default_off_timer_path_readback_gate_only"
        and owner.get("future_p9aa_timer_path_shadow_cycles_approved") is True
        and zero_orders_fills(summary)
        and all(gates.get(key) is True for key in required)
    )


def generated_no_order_config(
    *,
    base_config: Path,
    proof_root: Path,
    run_id: str,
) -> Path:
    payload = copy.deepcopy(load_live_trading_config(base_config).payload)
    payload.setdefault("risk", {})["trading_enabled"] = False
    core = payload.setdefault("core_loop", {})
    core["live_delta_enabled"] = False
    core["submit_orders"] = False
    core["auto_confirm_delta_after_preflight"] = False
    core["max_cycles_per_invocation"] = 1
    supervisor = payload.setdefault("mainnet_live_supervisor", {})
    supervisor["allow_live_delta_when_armed"] = False
    supervisor["allow_multiphase_live_delta"] = False
    supervisor["max_cycles_per_invocation"] = 1
    supervisor["interval_seconds"] = 0
    supervisor["disarm_on_blocker"] = False
    health = payload.setdefault("mainnet_health_monitor", {})
    health["no_order_expected"] = True
    health["require_systemd_timer_active"] = False
    state = payload.setdefault("state", {})
    state_root = proof_root / "state"
    state["sqlite_path"] = str(state_root / "live_trading.sqlite3")
    state["artifact_root"] = str(proof_root / "runs")
    out = proof_root / "generated_no_order_timer_path_config.json"
    write_json(out, payload | {"generated_config_context": {"contract_version": CONTRACT_VERSION, "run_id": run_id}})
    return out


def _parse_iso_z(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _source_side_effects_zero(summary: dict[str, Any]) -> bool:
    side_effects = dict(summary.get("side_effects") or {})
    return (
        side_effects.get("orders_submitted") == 0
        and side_effects.get("orders_canceled") == 0
        and side_effects.get("order_test_calls", 0) == 0
        and side_effects.get("only_http_get_endpoints") is True
    )


def build_nonflat_position_reference_fixture(
    *,
    source_path: Path,
    proof_root: Path,
    run_id: str,
    generated_at: datetime,
) -> tuple[Path, dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not source_path.exists():
        return Path(""), {}, [f"position_reference_source_missing:{source_path}"]
    source = load_optional(source_path)
    finished_at = _parse_iso_z(str(source.get("finished_at_utc") or ""))
    rows = list(dict(source.get("position_fingerprint") or {}).get("stable_rows") or [])
    expected_rows: list[dict[str, Any]] = []
    if source.get("contract_version") != "hv_balanced_dth60_coinglass_phase9ag_position_fingerprint.v1":
        blockers.append("position_reference_source_contract_mismatch")
    if source.get("status") != "ready" or source.get("blockers"):
        blockers.append("position_reference_source_not_ready")
    if int(source.get("open_order_count") or 0) != 0:
        blockers.append(f"position_reference_source_open_orders:{source.get('open_order_count')}")
    if int(source.get("open_position_count") or 0) <= 0:
        blockers.append("position_reference_source_requires_nonflat_positions")
    if not _source_side_effects_zero(source):
        blockers.append("position_reference_source_side_effects_not_zero")
    if finished_at is None:
        blockers.append("position_reference_source_finished_at_missing_or_invalid")
    elif finished_at > generated_at:
        blockers.append("position_reference_source_not_point_in_time_safe")
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        amount = float(row.get("positionAmt") or 0.0)
        if abs(amount) <= 1e-12:
            continue
        expected_rows.append(
            {
                "symbol": symbol,
                "expected_position_amt": amount,
                "positionAmt": str(row.get("positionAmt") or ""),
                "positionSide": str(row.get("positionSide") or "BOTH"),
                "entryPrice": str(row.get("entryPrice") or ""),
                "breakEvenPrice": str(row.get("breakEvenPrice") or ""),
                "isolated": str(row.get("isolated") or ""),
                "isolatedWallet": str(row.get("isolatedWallet") or ""),
                "source_position_fingerprint_hash": str(dict(source.get("position_fingerprint") or {}).get("stable_hash") or ""),
            }
        )
    if not expected_rows:
        blockers.append("position_reference_expected_rows_empty")
    reference_root = proof_root / "position_reference" / f"{run_id}-nonflat-genesis-snapshot"
    if blockers:
        return reference_root, {"status": "blocked", "blockers": sorted(set(blockers))}, blockers
    reference_root.mkdir(parents=True, exist_ok=True)
    csv_path = reference_root / "reference_positions.csv"
    fieldnames = [
        "symbol",
        "expected_position_amt",
        "positionAmt",
        "positionSide",
        "entryPrice",
        "breakEvenPrice",
        "isolated",
        "isolatedWallet",
        "source_position_fingerprint_hash",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(expected_rows, key=lambda item: str(item["symbol"])))
    fixture_summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aa_nonflat_position_reference_fixture.v1",
        "run_id": run_id,
        "status": "position_genesis_snapshot",
        "read_only": True,
        "proof_artifacts_only": True,
        "generated_at_utc": iso_z(generated_at),
        "source_position_fingerprint": evidence_file(source_path),
        "source_finished_at_utc": source.get("finished_at_utc"),
        "source_created_before_p9aa": bool(finished_at and finished_at <= generated_at),
        "source_open_order_count": int(source.get("open_order_count") or 0),
        "source_open_position_count": int(source.get("open_position_count") or 0),
        "source_position_fingerprint_hash": str(dict(source.get("position_fingerprint") or {}).get("stable_hash") or ""),
        "expected_position_count": len(expected_rows),
        "expected_symbols": [str(row["symbol"]) for row in sorted(expected_rows, key=lambda item: str(item["symbol"]))],
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "account_settings_changed": 0,
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
        "output_files": {
            "run_summary": str(reference_root / "run_summary.json"),
            "genesis_snapshot": str(reference_root / "genesis_snapshot.json"),
            "reference_positions": str(csv_path),
        },
    }
    write_json(reference_root / "genesis_snapshot.json", fixture_summary | {"positions": expected_rows})
    write_json(reference_root / "run_summary.json", fixture_summary)
    return reference_root, fixture_summary, []


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def core_cycle_from_supervisor(summary: dict[str, Any]) -> dict[str, Any]:
    cycles = list(summary.get("cycles") or [])
    if not cycles:
        return {}
    supervisor_cycle = dict(cycles[-1])
    core = dict(supervisor_cycle.get("core_loop_summary") or {})
    core_cycles = list(core.get("cycles") or [])
    return dict(core_cycles[-1]) if core_cycles else {}


def write_candidate_shadow_source(
    *,
    path: Path,
    run_id: str,
    cycle_index: int,
    target_portfolio_path: Path,
) -> None:
    target_payload = read_json(target_portfolio_path) if target_portfolio_path.exists() else {}
    write_json(
        path,
        {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aa_candidate_shadow_source.v1",
            "run_id": run_id,
            "cycle_index": int(cycle_index),
            "mode": "observe_only_shadow_readback",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "source_target_portfolio": evidence_file(target_portfolio_path),
            "source_target_portfolio_payload": target_payload,
            "shadow_annotation": "candidate_shadow_artifact_only_not_executor_input",
        },
    )


def run_shadow_hook_for_supervisor_cycle(
    *,
    proof_root: Path,
    run_id: str,
    cycle_index: int,
    supervisor_summary: dict[str, Any],
) -> dict[str, Any]:
    cycle_proof_root = proof_root / f"cycle_{cycle_index:03d}"
    core_cycle = core_cycle_from_supervisor(supervisor_summary)
    plan_root = repo_path(str(core_cycle.get("plan_artifact_root") or ""))
    target_portfolio = plan_root / "target_portfolio.json"
    candidate_source = cycle_proof_root / "candidate_shadow_source.json"
    if target_portfolio.exists():
        write_candidate_shadow_source(
            path=candidate_source,
            run_id=run_id,
            cycle_index=cycle_index,
            target_portfolio_path=target_portfolio,
        )
    else:
        write_json(
            candidate_source,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9aa_candidate_shadow_source.v1",
                "run_id": run_id,
                "cycle_index": int(cycle_index),
                "blocker": "target_portfolio_missing",
                "source_target_portfolio": evidence_file(target_portfolio),
            },
        )
    return run_observe_only_shadow_hook(
        config=ObserveOnlyShadowHookConfig(
            enabled=True,
            output_root=cycle_proof_root / "hook",
        ),
        baseline_target_plan_path=target_portfolio,
        executor_input_plan_path=target_portfolio,
        candidate_shadow_plan_path=candidate_source,
        supervisor_context={
            "contract_version": CONTRACT_VERSION,
            "run_id": run_id,
            "cycle_index": int(cycle_index),
            "supervisor_summary": {
                "run_id": supervisor_summary.get("run_id"),
                "status": supervisor_summary.get("status"),
                "artifact_root": supervisor_summary.get("artifact_root"),
                "orders_submitted": supervisor_summary.get("orders_submitted"),
                "fill_count": supervisor_summary.get("fill_count"),
                "live_delta_authorized": supervisor_summary.get("live_delta_authorized"),
            },
            "core_cycle": {
                "status": core_cycle.get("status"),
                "plan_artifact_root": core_cycle.get("plan_artifact_root"),
                "orders_submitted": core_cycle.get("orders_submitted"),
                "fill_count": core_cycle.get("fill_count"),
            },
        },
        run_id=f"{run_id}-cycle-{cycle_index:03d}-timer-path-shadow-hook",
    )


def cycle_ready(row: dict[str, Any]) -> bool:
    supervisor = dict(row.get("supervisor_summary") or {})
    hook = dict(row.get("hook_summary") or {})
    supervisor_cycles = list(supervisor.get("cycles") or [])
    supervisor_cycle = dict(supervisor_cycles[-1]) if supervisor_cycles else {}
    return (
        int(row.get("supervisor_exit_code") or 0) == 0
        and supervisor.get("status") == "mainnet_live_supervisor_completed"
        and not supervisor.get("blockers")
        and zero_orders_fills(supervisor)
        and supervisor.get("live_delta_authorized") is False
        and supervisor_cycle.get("execute_live_delta_requested") is False
        and hook.get("status") == "ready"
        and hook.get("hook_enabled") is True
        and int(hook.get("candidate_artifacts_written_count") or 0) > 0
        and hook.get("candidate_artifacts_under_proof_artifacts_only") is True
        and hook.get("executor_consumes_baseline_only") is True
        and hook.get("executor_input_plan_hash_equals_baseline") is True
        and hook.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(hook)
        and hook.get("live_config_changed") is False
        and hook.get("operator_state_changed") is False
        and hook.get("timer_state_changed") is False
    )


def supervisor_blockers(cycle_rows: list[dict[str, Any]]) -> list[str]:
    blockers: set[str] = set()
    for row in cycle_rows:
        summary = dict(row.get("supervisor_summary") or {})
        blockers.update(str(item) for item in summary.get("blockers") or [])
        for supervisor_cycle in list(summary.get("cycles") or []):
            core = dict(dict(supervisor_cycle).get("core_loop_summary") or {})
            blockers.update(str(item) for item in core.get("blockers") or [])
            for core_cycle in list(core.get("cycles") or []):
                blockers.update(str(item) for item in dict(core_cycle).get("blockers") or [])
    return sorted(blockers)


def account_read_blockers(blockers: list[str]) -> list[str]:
    needles = (
        "read_only_endpoint_failed",
        "api_key",
        "account_reconcile",
        "account_config",
        "account_information",
        "open_orders",
        "position_risk",
        "position_mode",
        "cantrade",
    )
    return [item for item in blockers if any(needle in item.lower() for needle in needles)]


def plan_artifact_missing_cycles(cycle_rows: list[dict[str, Any]]) -> list[int]:
    missing: list[int] = []
    for row in cycle_rows:
        core_cycle = core_cycle_from_supervisor(dict(row.get("supervisor_summary") or {}))
        plan_root = str(core_cycle.get("plan_artifact_root") or "").strip()
        target = repo_path(plan_root) / "target_portfolio.json" if plan_root else Path("")
        if not plan_root or not target.exists():
            missing.append(int(row.get("cycle_index") or 0))
    return missing


def build_phase9aa(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    supervisor_runner: SupervisorRunner = run_mainnet_live_supervisor,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9aa" / run_id
    p9z_path = resolve_path(args.phase9z_summary) if str(args.phase9z_summary).strip() else latest_match(PHASE9Z_PARENT, "*/summary.json")
    p9z = load_optional(p9z_path)
    base_config = resolve_path(args.base_config)
    decision = owner_decision_record(args, generated_at)
    write_json(root / "owner_decision_record.json", decision)

    pre_gates = {
        "owner_decision_p9aa_no_order_cycles": args.owner_decision == APPROVE_P9AA_DECISION,
        "p9z_owner_gate_ready": p9z_ready(p9z),
        "base_config_exists": base_config.exists(),
        "shadow_cycles_at_least_three": int(args.shadow_cycles or 0) >= 3,
    }
    pre_blockers = [key for key, value in pre_gates.items() if not value]
    generated_config_path = generated_no_order_config(base_config=base_config, proof_root=proof_root, run_id=run_id) if not pre_blockers else Path("")
    _position_reference_raw = str(args.position_reference_source or "").strip()
    has_position_reference_source = bool(_position_reference_raw)
    # NOTE: Path("") stringifies to "." (truthy), so "no source" must be detected from the RAW
    # arg, not str(position_reference_source); otherwise the flat (no-reference) path would wrongly
    # try to build a reference fixture from "." and fail closed (the D-3 nonflat-reference feature
    # regressed this).
    position_reference_source = resolve_path(_position_reference_raw) if has_position_reference_source else Path("")
    position_reference_run = Path("")
    position_reference_summary: dict[str, Any] = {}
    position_reference_blockers: list[str] = []
    if not pre_blockers and has_position_reference_source:
        position_reference_run, position_reference_summary, position_reference_blockers = build_nonflat_position_reference_fixture(
            source_path=position_reference_source,
            proof_root=proof_root,
            run_id=run_id,
            generated_at=generated_at,
        )
        pre_blockers.extend(position_reference_blockers)
    cycle_rows: list[dict[str, Any]] = []

    if not pre_blockers:
        for cycle_index in range(1, int(args.shadow_cycles) + 1):
            supervisor_args = Namespace(
                config=str(generated_config_path),
                as_of=str(args.as_of),
                fixture_panel=str(args.fixture_panel or ""),
                symbols=str(args.symbols or ""),
                public_market_data=bool(args.public_market_data),
                reference_run=str(position_reference_run) if str(position_reference_run) else "",
                target_engine=str(args.target_engine or ""),
                cycles=1,
                interval_seconds=0.0,
                position_tolerance=float(args.position_tolerance or 1e-9),
                fast_follow_entry_second=False,
                fast_follow_chain_depth=0,
            )
            supervisor_summary, supervisor_exit = supervisor_runner(supervisor_args, env=env or os.environ)
            hook_summary = run_shadow_hook_for_supervisor_cycle(
                proof_root=proof_root,
                run_id=run_id,
                cycle_index=cycle_index,
                supervisor_summary=supervisor_summary,
            )
            row = {
                "cycle_index": int(cycle_index),
                "supervisor_exit_code": int(supervisor_exit),
                "supervisor_summary": supervisor_summary,
                "hook_summary": hook_summary,
            }
            row["cycle_ready"] = cycle_ready(row)
            write_json(proof_root / f"cycle_{cycle_index:03d}_timer_path_shadow_readback.json", row)
            cycle_rows.append(row)
            if float(args.interval_seconds or 0.0) > 0 and cycle_index < int(args.shadow_cycles):
                import time

                time.sleep(float(args.interval_seconds))

    cycle_run_ids = [str(dict(row.get("supervisor_summary") or {}).get("run_id") or "") for row in cycle_rows]
    proof_roots = [str(dict(row.get("hook_summary") or {}).get("proof_root") or "") for row in cycle_rows]
    generated_config_exists = bool(str(generated_config_path)) and generated_config_path.exists()
    supervisor_blocker_rows = supervisor_blockers(cycle_rows)
    account_read_blocker_rows = account_read_blockers(supervisor_blocker_rows)
    missing_plan_cycles = plan_artifact_missing_cycles(cycle_rows)
    gates = {
        **pre_gates,
        "generated_no_order_config_written": generated_config_exists,
        "generated_config_under_proof_artifacts": (
            "proof_artifacts" in [part.lower() for part in generated_config_path.resolve().parts]
            if generated_config_exists
            else False
        ),
        "position_reference_fixture_ready": (
            not has_position_reference_source
            or (
                bool(str(position_reference_run))
                and position_reference_run.exists()
                and not position_reference_blockers
                and position_reference_summary.get("status") == "position_genesis_snapshot"
                and position_reference_summary.get("read_only") is True
                and position_reference_summary.get("proof_artifacts_only") is True
                and position_reference_summary.get("source_created_before_p9aa") is True
            )
        ),
        "ran_requested_cycle_count": len(cycle_rows) == int(args.shadow_cycles or 0),
        "ran_at_least_three_cycles": len(cycle_rows) >= 3,
        "fresh_supervisor_run_each_cycle": len(cycle_run_ids) >= 3 and len(set(cycle_run_ids)) == len(cycle_run_ids),
        "fresh_hook_proof_root_each_cycle": len(proof_roots) >= 3 and len(set(proof_roots)) == len(proof_roots),
        "all_cycles_ready": bool(cycle_rows) and all(bool(row.get("cycle_ready")) for row in cycle_rows),
        "all_supervisor_orders_zero": bool(cycle_rows) and all(zero_orders_fills(dict(row.get("supervisor_summary") or {})) for row in cycle_rows),
        "all_hook_orders_zero": bool(cycle_rows) and all(zero_orders_fills(dict(row.get("hook_summary") or {})) for row in cycle_rows),
        "all_executor_baseline_only": bool(cycle_rows)
        and all(dict(row.get("hook_summary") or {}).get("executor_consumes_baseline_only") is True for row in cycle_rows),
        "all_candidate_artifacts_shadow_only": bool(cycle_rows)
        and all(int(dict(row.get("hook_summary") or {}).get("candidate_artifacts_written_count") or 0) > 0 for row in cycle_rows),
        "all_candidate_plan_not_referenced_by_executor": bool(cycle_rows)
        and all(dict(row.get("hook_summary") or {}).get("candidate_plan_referenced_by_executor") is False for row in cycle_rows),
        "no_candidate_execution": True,
        "no_live_order_submission": True,
        "no_target_plan_replacement": True,
        "no_executor_input_mutation": bool(cycle_rows)
        and all(dict(row.get("hook_summary") or {}).get("executor_input_plan_hash_unchanged") is True for row in cycle_rows),
        "no_production_timer_service_mutation": True,
        "no_remote_sync": True,
    }
    blockers = pre_blockers + [key for key, value in gates.items() if not value and key not in pre_gates]
    if account_read_blocker_rows:
        blockers.append("timer_path_account_read_blocked")
    if missing_plan_cycles:
        blockers.append("timer_path_plan_artifact_missing")
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": sorted(set(blockers)),
        "owner_decision": decision,
        "timer_path_shadow_cycles_ready": status == "ready",
        "timer_path_supervisor_entrypoint_invoked": bool(cycle_rows),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "generated_no_order_config": evidence_file(generated_config_path),
        "base_config": evidence_file(base_config),
        "phase9z_summary": evidence_file(p9z_path),
        "position_reference_fixture_requested": has_position_reference_source,
        "position_reference_source": evidence_file(position_reference_source),
        "position_reference_fixture": evidence_file(position_reference_run / "run_summary.json" if str(position_reference_run) else Path("")),
        "position_reference_fixture_ready": gates["position_reference_fixture_ready"],
        "position_reference_fixture_summary": position_reference_summary,
        "requested_shadow_cycles": int(args.shadow_cycles or 0),
        "completed_shadow_cycles": len(cycle_rows),
        "fresh_proof_each_cycle": gates["fresh_supervisor_run_each_cycle"] and gates["fresh_hook_proof_root_each_cycle"],
        "same_risk_no_order_config_each_cycle": generated_config_exists,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_execution_enabled": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "orders_submitted": sum(int(dict(row.get("supervisor_summary") or {}).get("orders_submitted") or 0) for row in cycle_rows),
        "fill_count": sum(int(dict(row.get("supervisor_summary") or {}).get("fill_count") or 0) for row in cycle_rows),
        "supervisor_cycle_blockers": supervisor_blocker_rows,
        "account_read_blockers": account_read_blocker_rows,
        "plan_artifact_missing_cycles": missing_plan_cycles,
        "remote_execution_performed": False,
        "live_config_changed": False,
        "operator_state_changed_outside_generated_p9aa_state": False,
        "timer_state_changed": False,
        "cycle_rows": cycle_rows,
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "generated_no_order_config": str(generated_config_path) if generated_config_exists else "",
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9aa(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
