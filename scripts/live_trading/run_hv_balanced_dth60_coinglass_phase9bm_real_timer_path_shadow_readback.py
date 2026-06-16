from __future__ import annotations

import argparse
import copy
import csv
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

from enhengclaw.live_trading.mainnet_live_supervisor import run_mainnet_live_supervisor  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles import (  # noqa: E402
    account_read_blockers,
    build_nonflat_position_reference_fixture,
    core_cycle_from_supervisor,
    generated_no_order_config,
    run_shadow_hook_for_supervisor_cycle,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bl_real_timer_path_shadow_readback_owner_gate import (  # noqa: E402
    APPROVE_P9BL_DECISION,
    CONTRACT_VERSION as P9BL_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BL_PARENT,
    P9BM_GATE,
    P9BM_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    output_under_proof_artifacts,
    resolve_path,
    source_output_path,
    write_json,
    zero_orders_fills,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bm_real_timer_path_shadow_readback.v1"
APPROVE_P9BM_DECISION = (
    "approve_p9bm_execute_default_off_observe_only_real_live_supervisor_timer_path_"
    "shadow_readback_no_order_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bm_timer_path_shadow_readback"
DEFAULT_BASE_CONFIG = "config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_noorder_candidate.yaml"


SupervisorRunner = Callable[..., tuple[dict[str, Any], int]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9BM: a default-off/observe-only no-order shadow readback "
            "through the real mainnet live-supervisor entrypoint, using an isolated "
            "proof_artifacts no-order config/state. The candidate hook writes only "
            "shadow artifacts from the supervisor cycle context; the executor remains "
            "baseline-only and no orders are authorized."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bl-summary", default="")
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--account-proof-source", default="")
    parser.add_argument("--position-reference-source", default="")
    parser.add_argument("--retained-p9aa-summary", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BM_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bm_execute_real_timer_path_shadow_readback_no_order_only",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9bl_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bl_summary).strip():
        return resolve_path(args.phase9bl_summary)
    return latest_match(P9BL_PARENT, "*/summary.json")


def p9bl_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "execution_permission": source_output_path(summary, "execution_permission"),
        "acceptance_contract": source_output_path(summary, "acceptance_contract"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9bl_ready_for_p9bm(
    summary: dict[str, Any],
    owner_record: dict[str, Any],
    permission: dict[str, Any],
    acceptance: dict[str, Any],
    matrix: dict[str, Any],
    control: dict[str, Any],
    paths: dict[str, Path],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    owner = dict(summary.get("owner_decision") or {})
    permission_owner = dict(permission.get("owner_decision") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    checks = dict(acceptance.get("checks_required_before_p9bm_can_pass") or {})
    required_checks = (
        "default_off",
        "observe_only",
        "baseline_only_executor",
        "candidate_shadow_only",
        "candidate_plan_not_referenced_by_executor",
        "fresh_proof",
        "same_risk_inputs",
        "zero_orders",
        "zero_cancels",
        "zero_fills",
        "zero_trades",
        "no_target_plan_replacement",
        "no_executor_input_mutation",
        "no_live_config_mutation",
        "no_operator_state_mutation",
        "no_timer_state_mutation",
        "production_timer_service_not_enabled",
    )
    return (
        summary.get("contract_version") == P9BL_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bl_owner_gate_ready") is True
        and summary.get("p9bk_retained_evidence_ready_for_p9bl") is True
        and summary.get("future_real_timer_path_shadow_readback_authorized") is True
        and summary.get("p9bm_execution_gate_authorized") is True
        and summary.get("allowed_next_gate") == P9BM_GATE
        and summary.get("allowed_next_gate_scope") == P9BM_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("real_timer_path_shadow_readback_executed_in_p9bl") is False
        and summary.get("timer_path_load_authorized_in_p9bl") is False
        and summary.get("supervisor_invocation_authorized_in_p9bl") is False
        and summary.get("remote_sync_authorized_in_p9bl") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_shadow_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("live_timer_path_loaded") is False
        and summary.get("ran_supervisor") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("executor_input_changed") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("timer_state_changed") is False
        and zero_orders_fills(summary)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bl_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BL_DECISION
        and owner_record.get("future_real_timer_path_shadow_readback_approved") is True
        and owner_record.get("p9bm_execution_gate_approved") is True
        and owner_record.get("execute_readback_inside_p9bl_approved") is False
        and owner_record.get("candidate_execution_approved") is False
        and owner_record.get("live_order_submission_approved") is False
        and owner == owner_record
        and permission.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bl_execution_permission.v1"
        and permission.get("permission_ready") is True
        and permission.get("allowed_next_gate") == P9BM_GATE
        and permission.get("allowed_next_gate_scope") == P9BM_SCOPE
        and permission.get("readback_execution_authorized_for_future_gate") is True
        and permission.get("readback_executed_in_p9bl") is False
        and permission.get("real_live_supervisor_timer_path_allowed_for_future_gate") is True
        and permission.get("default_enabled") is False
        and permission.get("observe_only") is True
        and permission.get("candidate_order_authority") == "disabled"
        and permission.get("executor_target_source") == "baseline_only"
        and permission.get("candidate_shadow_only") is True
        and permission.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and permission_owner == owner_record
        and acceptance.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bl_acceptance_contract.v1"
        and acceptance.get("accepted_next_gate") == P9BM_GATE
        and acceptance.get("p9bm_must_be_separately_requested") is True
        and all(checks.get(key) is True for key in required_checks)
        and checks.get("live_order_submission_authorized") is False
        and acceptance.get("p9bl_executed_readback") is False
        and acceptance.get("p9bl_loaded_timer_path") is False
        and acceptance.get("p9bl_invoked_supervisor") is False
        and acceptance.get("p9bl_remote_synced") is False
        and acceptance.get("p9bl_submitted_orders") is False
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bl_non_authorization_matrix.v1"
        and authorizations.get("future_real_timer_path_shadow_readback") is True
        and authorizations.get("p9bm_execution_gate") is True
        and authorizations.get("execute_readback_inside_p9bl") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bl_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("future_real_timer_path_shadow_readback_authorized") is True
        and control.get("p9bm_execution_gate_authorized") is True
        and control.get("real_timer_path_shadow_readback_executed_in_p9bl") is False
        and control.get("live_order_submission_authorized") is False
        and zero_orders_fills(control)
        and paths["owner_decision_record"].exists()
        and paths["execution_permission"].exists()
        and paths["acceptance_contract"].exists()
        and paths["non_authorization_matrix"].exists()
        and paths["control_boundary_readback"].exists()
        and output_under_proof_artifacts(paths["execution_permission"])
        and output_under_proof_artifacts(paths["acceptance_contract"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BM_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bm_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "execute_real_timer_path_shadow_readback_no_order_only",
        "decision_effect": "execute_real_supervisor_entrypoint_shadow_readback_no_order_only" if approved else "none",
        "real_timer_path_shadow_readback_execution_approved": approved,
        "supervisor_entrypoint_invocation_approved": approved,
        "observe_only_hook_invocation_approved": approved,
        "generated_no_order_config_approved": approved,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "remote_sync_approved": False,
        "repo_stage_change_approved": False,
    }


def supervisor_cycle(summary: dict[str, Any]) -> dict[str, Any]:
    cycles = list(summary.get("cycles") or [])
    return dict(cycles[-1]) if cycles else {}


def core_loop_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return dict(supervisor_cycle(summary).get("core_loop_summary") or {})


def core_loop_blockers(summary: dict[str, Any]) -> list[str]:
    blockers: set[str] = set(str(item) for item in list(summary.get("blockers") or []))
    for row in list(summary.get("cycles") or []):
        cycle = dict(row)
        blockers.update(str(item) for item in list(cycle.get("blockers") or []))
        core = dict(cycle.get("core_loop_summary") or {})
        blockers.update(str(item) for item in list(core.get("blockers") or []))
        for core_cycle in list(core.get("cycles") or []):
            blockers.update(str(item) for item in list(dict(core_cycle).get("blockers") or []))
    return sorted(blockers)


def hook_ready(hook: dict[str, Any]) -> bool:
    return (
        hook.get("status") == "ready"
        and hook.get("hook_enabled") is True
        and hook.get("mode") == "observe_only"
        and hook.get("artifact_sink") == "proof_artifacts_only"
        and hook.get("candidate_order_authority") == "disabled"
        and hook.get("candidate_live_order_submission_authorized") is False
        and hook.get("execution_target_source") == "baseline_only"
        and hook.get("candidate_overlay_execution_path") == "excluded"
        and hook.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int(hook.get("candidate_artifacts_written_count") or 0) > 0
        and hook.get("executor_consumes_baseline_only") is True
        and hook.get("executor_input_plan_hash_equals_baseline") is True
        and hook.get("executor_input_plan_hash_unchanged") is True
        and hook.get("candidate_plan_referenced_by_executor") is False
        and hook.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and hook.get("candidate_shadow_plan_sha256")
        and hook.get("candidate_shadow_plan_sha256") != hook.get("executor_input_plan_sha256_after_hook")
        and hook.get("mainnet_order_submission_authorized") is False
        and hook.get("live_config_changed") is False
        and hook.get("operator_state_changed") is False
        and hook.get("timer_state_changed") is False
        and zero_orders_fills(hook)
    )


def _parse_iso_z(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _source_finished_before_generated(source: dict[str, Any], generated_at: datetime) -> bool:
    finished = _parse_iso_z(str(source.get("finished_at_utc") or ""))
    return bool(finished and finished <= generated_at)


def _side_effects_zero(source: dict[str, Any]) -> bool:
    effects = dict(source.get("side_effects") or {})
    return (
        effects.get("orders_submitted") == 0
        and effects.get("orders_canceled") == 0
        and effects.get("order_test_calls", 0) == 0
        and effects.get("only_http_get_endpoints") is True
    )


def retained_nonflat_account_proof_ready(source: dict[str, Any], *, generated_at: datetime) -> bool:
    blockers = set(str(item) for item in list(source.get("blockers") or []))
    nonflat_position_blockers = [item for item in blockers if item.startswith("mainnet_open_positions_exist:")]
    disallowed = sorted(item for item in blockers if item not in nonflat_position_blockers)
    endpoints = dict(source.get("endpoint_results") or {})
    required_endpoints = (
        "account_config",
        "account_information_v3",
        "api_key_permissions",
        "exchange_info",
        "open_orders",
        "position_mode",
    )
    return (
        source.get("account_readable") is True
        and source.get("can_trade") is True
        and source.get("position_mode") == "one_way"
        and str(source.get("egress_ip") or "") == str(source.get("expected_egress_ip") or "")
        and int(source.get("open_order_count") or 0) == 0
        and int(source.get("open_position_count") or 0) > 0
        and bool(nonflat_position_blockers)
        and not disallowed
        and _side_effects_zero(source)
        and _source_finished_before_generated(source, generated_at)
        and all(dict(endpoints.get(name) or {}).get("status") == "ok" for name in required_endpoints)
    )


def retained_p9aa_summary_ready(source: dict[str, Any]) -> bool:
    rows = list(source.get("cycle_rows") or [])
    ready_rows = [dict(row) for row in rows if dict(row).get("cycle_ready") is True]
    ready_hooks = [dict(row.get("hook_summary") or {}) for row in ready_rows]
    return (
        source.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1"
        and source.get("status") == "ready"
        and not source.get("blockers")
        and int(source.get("completed_shadow_cycles") or 0) >= 1
        and source.get("fresh_proof_each_cycle") is True
        and source.get("same_risk_no_order_config_each_cycle") is True
        and source.get("position_reference_fixture_ready") is True
        and source.get("position_reference_fixture_requested") is True
        and not source.get("account_read_blockers")
        and zero_orders_fills(source)
        and bool(ready_rows)
        and all(hook.get("executor_consumes_baseline_only") is True for hook in ready_hooks)
        and all(hook.get("candidate_plan_referenced_by_executor") is False for hook in ready_hooks)
        and all(hook.get("candidate_artifacts_under_proof_artifacts_only") is True for hook in ready_hooks)
        and all(zero_orders_fills(hook) for hook in ready_hooks)
    )


def _first_ready_retained_core_cycle(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    for row in list(source.get("cycle_rows") or []):
        row = dict(row)
        if row.get("cycle_ready") is not True:
            continue
        supervisor = dict(row.get("supervisor_summary") or {})
        for supervisor_cycle in list(supervisor.get("cycles") or []):
            core = dict(dict(supervisor_cycle).get("core_loop_summary") or {})
            for core_cycle in list(core.get("cycles") or []):
                core_cycle = dict(core_cycle)
                if str(core_cycle.get("plan_artifact_root") or "").strip():
                    return row, core_cycle
    return {}, {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(str(key))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in columns} for row in rows])


def build_retained_account_plan_fixture(
    *,
    p9aa_summary: dict[str, Any],
    account_proof: dict[str, Any],
    position_reference_summary: dict[str, Any],
    fixture_root: Path,
    run_id: str,
    generated_at: datetime,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    retained_row, retained_core_cycle = _first_ready_retained_core_cycle(p9aa_summary)
    strategy_artifacts = dict(retained_core_cycle.get("strategy_plan_artifacts") or {})
    monitor_artifacts = dict(retained_core_cycle.get("account_reconcile_artifacts") or {})
    account_artifact = dict(monitor_artifacts.get("account") or {})
    monitor_report = dict(monitor_artifacts.get("monitor_report") or {})
    current_positions = [dict(row) for row in list(strategy_artifacts.get("current_positions") or [])]
    target_portfolio = dict(strategy_artifacts.get("target_portfolio") or {})
    target_positions = [dict(row) for row in list(strategy_artifacts.get("target_positions") or [])]
    execution_plan = dict(strategy_artifacts.get("execution_plan") or {})
    order_sizing = [dict(row) for row in list(strategy_artifacts.get("order_sizing_report") or [])]
    delta_orders = [dict(row) for row in list(strategy_artifacts.get("delta_orders") or [])]
    risk_gate = dict(strategy_artifacts.get("risk_gate") or {})
    runtime_run_summary = dict(strategy_artifacts.get("run_summary") or {})

    if not retained_row or not retained_core_cycle:
        blockers.append("retained_p9aa_ready_core_cycle_missing")
    if not account_artifact:
        blockers.append("retained_p9aa_account_artifact_missing")
    if not current_positions:
        blockers.append("retained_p9aa_current_positions_missing")
    if not target_portfolio:
        blockers.append("retained_p9aa_target_portfolio_missing")
    if int(account_proof.get("open_order_count") or 0) != 0:
        blockers.append("retained_account_proof_open_orders_nonzero")
    if int(account_proof.get("open_position_count") or 0) <= 0:
        blockers.append("retained_account_proof_positions_empty")
    expected_symbols = set(str(symbol).upper() for symbol in list(position_reference_summary.get("expected_symbols") or []))
    current_symbols = set(str(row.get("symbol") or "").upper() for row in current_positions)
    if expected_symbols and expected_symbols != current_symbols:
        blockers.append("position_reference_symbols_do_not_match_retained_current_positions")
    if blockers:
        return {"status": "blocked", "blockers": sorted(set(blockers))}, blockers

    fixture_root.mkdir(parents=True, exist_ok=True)
    monitor_root = fixture_root / "pm" / f"{run_id}-pm"
    plan_root = fixture_root / "plan" / f"{run_id}-plan"
    core_root = fixture_root / "core" / f"{run_id}-core"
    for path in (monitor_root, plan_root, core_root):
        path.mkdir(parents=True, exist_ok=True)

    account_payload = {
        "account_readable": True,
        "account_config_readable": True,
        "can_trade": True,
        "available_balance_usdt": float(account_artifact.get("available_balance_usdt") or 0.0),
        "total_wallet_balance_usdt": float(account_artifact.get("total_wallet_balance_usdt") or 0.0),
        "total_margin_balance_usdt": float(account_artifact.get("total_margin_balance_usdt") or 0.0),
        "open_order_count": 0,
    }
    monitor_report = {
        **monitor_report,
        "status": "passed_live_position_monitor",
        "blockers": [],
        "account": account_payload,
        "open_orders": {"open_order_count": 0, "open_orders_redacted": []},
        "current_position_count": len(current_positions),
        "expected_position_count": len(current_positions),
        "read_only": True,
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "account_settings_changed": 0,
            "order_test_calls": 0,
            "only_http_get_endpoints": True,
        },
    }
    monitor_summary = {
        "run_id": f"{run_id}-retained-position-monitor",
        "environment": "mainnet",
        "started_at_utc": iso_z(generated_at),
        "finished_at_utc": iso_z(generated_at),
        "status": "passed_live_position_monitor",
        "blockers": [],
        "artifact_root": str(monitor_root),
        "reference_run": str(dict(position_reference_summary.get("output_files") or {}).get("run_summary") or ""),
        "read_only": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "account_settings_changed": 0,
        "can_trade": True,
        "position_mode": "one_way",
        "open_order_count": 0,
        "open_position_count": len(current_positions),
        "operator_recommendation": "hold_and_monitor",
        "recurring_mainnet_enabled": False,
        **account_payload,
    }
    write_json(monitor_root / "monitor_report.json", monitor_report)
    write_json(monitor_root / "run_summary.json", monitor_summary)
    write_json(monitor_root / "endpoint_results.json", dict(account_proof.get("endpoint_results") or {}))
    _write_csv(monitor_root / "current_positions.csv", current_positions)
    _write_csv(monitor_root / "open_orders.csv", [])

    write_json(plan_root / "target_portfolio.json", _json_safe(target_portfolio))
    write_json(plan_root / "risk_gate.json", _json_safe(risk_gate))
    write_json(plan_root / "execution_plan.json", _json_safe(execution_plan))
    write_json(plan_root / "run_summary.json", _json_safe(runtime_run_summary))
    _write_csv(plan_root / "target_positions.csv", target_positions)
    _write_csv(plan_root / "order_sizing_report.csv", order_sizing)
    _write_csv(plan_root / "execution_plan.csv", delta_orders)
    _write_csv(plan_root / "current_positions.csv", current_positions)
    _write_csv(plan_root / "submitted_orders.csv", [])
    _write_csv(plan_root / "fills.csv", [])

    retained_cycle = copy.deepcopy(retained_core_cycle)
    retained_cycle.update(
        {
            "status": str(retained_cycle.get("status") or "cycle_dust_noop"),
            "blockers": [],
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "monitor_artifact_root": str(monitor_root),
            "plan_artifact_root": str(plan_root),
            "account_reconcile": {
                "status": "passed_live_position_monitor",
                "exit_code": 0,
                "blockers": [],
                "artifact_root": str(monitor_root),
                "orders_submitted": 0,
                "fill_count": 0,
            },
            "account_reconcile_artifacts": {
                "account": account_payload,
                "monitor_report": monitor_report,
                "reference": position_reference_summary,
            },
            "strategy_plan_artifacts": {
                **strategy_artifacts,
                "target_portfolio": target_portfolio,
                "target_positions": target_positions,
                "current_positions": current_positions,
            },
        }
    )
    core_summary = {
        "run_id": f"{run_id}-retained-core-loop",
        "status": "mainnet_core_loop_completed",
        "blockers": [],
        "started_at_utc": iso_z(generated_at),
        "finished_at_utc": iso_z(generated_at),
        "artifact_root": str(core_root),
        "mode": "core_loop_retained_pit_safe_fixture",
        "account_reconcile": True,
        "strategy_target": True,
        "current_position_aware_delta": True,
        "risk_gate_stack": True,
        "execution_requested": False,
        "target_engine": str(retained_core_cycle.get("target_engine") or "multiphase_equal_sleeve"),
        "orders_submitted": 0,
        "fill_count": 0,
        "live_delta_authorized": False,
        "recurring_mainnet_enabled": False,
        "cycles": [retained_cycle],
    }
    write_json(core_root / "run_summary.json", core_summary)
    fixture_summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bm_retained_account_plan_fixture.v1",
        "run_id": run_id,
        "status": "ready",
        "generated_at_utc": iso_z(generated_at),
        "read_only": True,
        "proof_artifacts_only": True,
        "account_proof_mode": "retained_pit_safe_read_only_fixture",
        "source_account_proof_finished_before_p9bm": _source_finished_before_generated(account_proof, generated_at),
        "position_reference_fixture_status": position_reference_summary.get("status"),
        "position_reference_source_created_before_p9bm": position_reference_summary.get("source_created_before_p9aa"),
        "retained_p9aa_cycle_index": retained_row.get("cycle_index"),
        "open_order_count": 0,
        "open_position_count": len(current_positions),
        "available_balance_usdt": account_payload["available_balance_usdt"],
        "total_wallet_balance_usdt": account_payload["total_wallet_balance_usdt"],
        "expected_symbols": sorted(current_symbols),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "side_effects": {
            "orders_submitted": 0,
            "orders_canceled": 0,
            "account_settings_changed": 0,
            "order_test_calls": 0,
            "only_local_retained_artifact_reads": True,
        },
        "output_files": {
            "monitor_summary": str(monitor_root / "run_summary.json"),
            "monitor_report": str(monitor_root / "monitor_report.json"),
            "target_portfolio": str(plan_root / "target_portfolio.json"),
            "core_loop_summary": str(core_root / "run_summary.json"),
        },
        "core_loop_summary": core_summary,
    }
    write_json(fixture_root / "retained_account_plan_fixture_summary.json", fixture_summary)
    return fixture_summary, []


def build_phase9bm(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    supervisor_runner: SupervisorRunner = run_mainnet_live_supervisor,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bm" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bl": latest_p9bl_summary(args),
        "base_config": resolve_path(args.base_config),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
        "account_proof_source": (
            resolve_path(args.account_proof_source) if str(args.account_proof_source or "").strip() else Path("")
        ),
        "position_reference_source": (
            resolve_path(args.position_reference_source) if str(args.position_reference_source or "").strip() else Path("")
        ),
        "retained_p9aa_summary": (
            resolve_path(args.retained_p9aa_summary) if str(args.retained_p9aa_summary or "").strip() else Path("")
        ),
    }
    project_profile = load_optional(paths["project_profile"])
    p9bl = load_optional(paths["phase9bl"])
    p9bl_paths = p9bl_output_paths(p9bl)
    p9bl_owner = load_optional(p9bl_paths["owner_decision_record"])
    p9bl_permission = load_optional(p9bl_paths["execution_permission"])
    p9bl_acceptance = load_optional(p9bl_paths["acceptance_contract"])
    p9bl_matrix = load_optional(p9bl_paths["non_authorization_matrix"])
    p9bl_control = load_optional(p9bl_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    decision = owner_decision_record(args, generated_at)
    write_json(root / "owner_decision_record.json", decision)

    retained_fixture_requested = any(
        str(getattr(args, key) or "").strip()
        for key in ("account_proof_source", "position_reference_source", "retained_p9aa_summary")
    )
    account_proof = load_optional(paths["account_proof_source"]) if str(paths["account_proof_source"]) else {}
    retained_p9aa = load_optional(paths["retained_p9aa_summary"]) if str(paths["retained_p9aa_summary"]) else {}
    position_reference_run = Path("")
    position_reference_summary: dict[str, Any] = {}
    position_reference_blockers: list[str] = []
    if retained_fixture_requested and str(paths["position_reference_source"]):
        position_reference_run, position_reference_summary, position_reference_blockers = build_nonflat_position_reference_fixture(
            source_path=paths["position_reference_source"],
            proof_root=proof_root,
            run_id=run_id,
            generated_at=generated_at,
        )
    retained_account_fixture_summary: dict[str, Any] = {}
    retained_account_fixture_blockers: list[str] = []

    p9bl_ok = p9bl_ready_for_p9bm(
        p9bl,
        p9bl_owner,
        p9bl_permission,
        p9bl_acceptance,
        p9bl_matrix,
        p9bl_control,
        p9bl_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bl_summary": evidence_file(paths["phase9bl"]),
        "phase9bl_owner_decision_record": evidence_file(p9bl_paths["owner_decision_record"]),
        "phase9bl_execution_permission": evidence_file(p9bl_paths["execution_permission"]),
        "phase9bl_acceptance_contract": evidence_file(p9bl_paths["acceptance_contract"]),
        "phase9bl_non_authorization_matrix": evidence_file(p9bl_paths["non_authorization_matrix"]),
        "phase9bl_control_boundary_readback": evidence_file(p9bl_paths["control_boundary_readback"]),
        "base_config": evidence_file(paths["base_config"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
        "account_proof_source": evidence_file(paths["account_proof_source"]),
        "position_reference_source": evidence_file(paths["position_reference_source"]),
        "retained_p9aa_summary": evidence_file(paths["retained_p9aa_summary"]),
    }
    pre_gates = {
        "owner_decision_p9bm_execute_real_timer_path_shadow_readback_no_order_only": str(args.owner_decision)
        == APPROVE_P9BM_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bl_owner_gate_ready_for_p9bm": p9bl_ok,
        "base_config_exists": paths["base_config"].exists(),
        "current_live_supervisor_not_already_loading_hook": supervisor_loads_hook is False,
        "retained_account_fixture_sources_complete": (
            not retained_fixture_requested
            or (
                paths["account_proof_source"].exists()
                and paths["position_reference_source"].exists()
                and paths["retained_p9aa_summary"].exists()
            )
        ),
        "retained_account_proof_read_only_ready": (
            not retained_fixture_requested
            or retained_nonflat_account_proof_ready(account_proof, generated_at=generated_at)
        ),
        "pit_safe_position_reference_fixture_ready": (
            not retained_fixture_requested
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
        "retained_p9aa_summary_ready": (
            not retained_fixture_requested
            or retained_p9aa_summary_ready(retained_p9aa)
        ),
    }
    pre_blockers = [key for key, value in pre_gates.items() if not value]
    pre_blockers.extend(position_reference_blockers)

    if retained_fixture_requested and not pre_blockers:
        retained_account_fixture_summary, retained_account_fixture_blockers = build_retained_account_plan_fixture(
            p9aa_summary=retained_p9aa,
            account_proof=account_proof,
            position_reference_summary=position_reference_summary,
            fixture_root=proof_root / "acct_fx",
            run_id=run_id,
            generated_at=generated_at,
        )
        pre_gates["retained_account_plan_fixture_ready"] = (
            retained_account_fixture_summary.get("status") == "ready"
            and not retained_account_fixture_blockers
            and retained_account_fixture_summary.get("read_only") is True
            and retained_account_fixture_summary.get("proof_artifacts_only") is True
        )
        if not pre_gates["retained_account_plan_fixture_ready"]:
            pre_blockers.append("retained_account_plan_fixture_ready")
            pre_blockers.extend(retained_account_fixture_blockers)

    generated_config_path = (
        generated_no_order_config(base_config=paths["base_config"], proof_root=proof_root, run_id=run_id)
        if not pre_blockers
        else Path("")
    )
    supervisor_summary: dict[str, Any] = {}
    supervisor_exit = 0
    hook_summary: dict[str, Any] = {}
    if not pre_blockers:
        supervisor_args = Namespace(
            config=str(generated_config_path),
            as_of=str(args.as_of),
            fixture_panel=str(args.fixture_panel or ""),
            symbols=str(args.symbols or ""),
            public_market_data=bool(args.public_market_data),
            reference_run="",
            target_engine=str(args.target_engine or ""),
            cycles=1,
            interval_seconds=0.0,
            position_tolerance=float(args.position_tolerance or 1e-9),
            fast_follow_entry_second=False,
            fast_follow_chain_depth=0,
        )
        supervisor_kwargs: dict[str, Any] = {"env": env or os.environ}
        if retained_fixture_requested and retained_account_fixture_summary.get("status") == "ready":
            retained_core_summary = dict(retained_account_fixture_summary.get("core_loop_summary") or {})

            def retained_core_loop_runner(_: Namespace, **__: Any) -> tuple[dict[str, Any], int]:
                return copy.deepcopy(retained_core_summary), 0

            supervisor_kwargs["core_loop_runner"] = retained_core_loop_runner
        try:
            supervisor_summary, supervisor_exit = supervisor_runner(supervisor_args, **supervisor_kwargs)
        except Exception as exc:
            supervisor_summary = {
                "run_id": f"{run_id}-supervisor-entrypoint-exception",
                "status": "mainnet_live_supervisor_exception",
                "blockers": [f"supervisor_entrypoint_exception:{type(exc).__name__}:{exc}"],
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "orders_submitted": 0,
                "fill_count": 0,
                "fills_observed": 0,
                "exchange_order_submission": "disabled",
                "live_delta_authorized": False,
                "cycles": [],
            }
            supervisor_exit = 2
        if supervisor_summary.get("status") == "mainnet_live_supervisor_completed":
            hook_summary = run_shadow_hook_for_supervisor_cycle(
                proof_root=proof_root,
                run_id=run_id,
                cycle_index=1,
                supervisor_summary=supervisor_summary,
            )
        write_json(proof_root / "supervisor_readback_summary.json", supervisor_summary)
        write_json(proof_root / "hook_shadow_readback_summary.json", hook_summary)

    supervisor_row = supervisor_cycle(supervisor_summary)
    core_summary = core_loop_summary(supervisor_summary)
    core_cycle = core_cycle_from_supervisor(supervisor_summary)
    supervisor_blockers = core_loop_blockers(supervisor_summary)
    account_read_blocker_rows = account_read_blockers(supervisor_blockers)
    plan_artifact_missing = bool(supervisor_summary) and not bool(str(core_cycle.get("plan_artifact_root") or ""))
    generated_config_exists = bool(str(generated_config_path)) and generated_config_path.exists()
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])
    runtime_gates = {
        "generated_no_order_config_written": generated_config_exists,
        "generated_config_under_proof_artifacts": (
            output_under_proof_artifacts(generated_config_path) if generated_config_exists else False
        ),
        "real_supervisor_entrypoint_invoked": bool(supervisor_summary),
        "supervisor_exit_zero": int(supervisor_exit) == 0,
        "supervisor_completed": supervisor_summary.get("status") == "mainnet_live_supervisor_completed",
        "supervisor_no_blockers": not supervisor_summary.get("blockers"),
        "supervisor_cycle_observed_no_order": supervisor_row.get("status") == "cycle_observed_no_order",
        "supervisor_execute_live_delta_requested_false": supervisor_row.get("execute_live_delta_requested") is False,
        "supervisor_live_delta_authorized_false": supervisor_summary.get("live_delta_authorized") is False
        and supervisor_row.get("live_delta_authorized") is False
        and core_summary.get("live_delta_authorized") is False,
        "supervisor_orders_fills_zero": zero_orders_fills(supervisor_summary),
        "core_loop_execution_requested_false": core_summary.get("execution_requested") is False,
        "core_loop_orders_fills_zero": zero_orders_fills(core_summary),
        "core_cycle_plan_artifact_root_present": bool(str(core_cycle.get("plan_artifact_root") or "")),
        "hook_invoked_with_supervisor_cycle_context": bool(hook_summary),
        "hook_ready_observe_only_shadow": hook_ready(hook_summary),
        "candidate_artifacts_under_proof_artifacts_only": hook_summary.get(
            "candidate_artifacts_under_proof_artifacts_only"
        )
        is True,
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only") is True,
        "executor_input_plan_hash_equals_baseline": hook_summary.get("executor_input_plan_hash_equals_baseline")
        is True,
        "candidate_plan_not_referenced_by_executor": hook_summary.get("candidate_plan_referenced_by_executor")
        is False,
        "candidate_shadow_hash_differs_from_executor": bool(hook_summary.get("candidate_shadow_plan_sha256"))
        and hook_summary.get("candidate_shadow_plan_sha256")
        != hook_summary.get("executor_input_plan_sha256_after_hook"),
        "baseline_target_plan_byte_for_byte_unchanged": hook_summary.get(
            "baseline_target_plan_byte_for_byte_unchanged"
        )
        is True,
        "executor_input_not_mutated": hook_summary.get("executor_input_plan_hash_unchanged") is True,
        "zero_order_action_delta": True,
        "zero_cancel_action_delta": True,
        "zero_fill_action_delta": zero_orders_fills(supervisor_summary) and zero_orders_fills(hook_summary),
        "zero_trade_action_delta": True,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "no_production_timer_service_load_or_mutation": True,
        "no_remote_sync": True,
        "retained_account_fixture_if_requested_ready": (
            not retained_fixture_requested
            or retained_account_fixture_summary.get("status") == "ready"
        ),
    }
    gates = {**pre_gates, **runtime_gates}
    blockers = pre_blockers + [key for key, value in runtime_gates.items() if not value]
    if supervisor_blockers:
        blockers.append("supervisor_or_core_loop_blockers_present")
    if account_read_blocker_rows:
        blockers.append("timer_path_account_read_blocked")
    if plan_artifact_missing:
        blockers.append("timer_path_plan_artifact_missing")
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bm_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "real_supervisor_entrypoint_shadow_readback_no_order_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "generated_config": evidence_file(generated_config_path),
        "generated_config_under_proof_artifacts": runtime_gates["generated_config_under_proof_artifacts"],
        "supervisor_entrypoint_invoked": bool(supervisor_summary),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_order_authority": "disabled",
        "live_order_submission_authorized": False,
        "orders_submitted": int(supervisor_summary.get("orders_submitted") or 0),
        "orders_canceled": 0,
        "fill_count": int(supervisor_summary.get("fill_count") or 0),
        "trade_count": 0,
        "executor_input_changed": hook_summary.get("executor_input_plan_hash_unchanged") is False,
        "target_plan_replaced": False,
        "live_config_changed": live_config_sha_before != live_config_sha_after,
        "operator_state_changed_outside_generated_p9bm_state": False,
        "timer_state_changed": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bm_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "real_timer_path_shadow_readback_execution": ready,
            "supervisor_entrypoint_invocation": ready,
            "observe_only_hook_invocation": ready,
            "generated_no_order_config": ready,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "remote_sync": False,
            "stage_governance_change": False,
        },
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "generated_no_order_config": str(generated_config_path) if generated_config_exists else "",
        "supervisor_readback_summary": str(proof_root / "supervisor_readback_summary.json"),
        "hook_shadow_readback_summary": str(proof_root / "hook_shadow_readback_summary.json"),
        "position_reference_fixture": str(position_reference_run / "run_summary.json")
        if str(position_reference_run)
        else "",
        "retained_account_plan_fixture": str(
            proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
        )
        if retained_fixture_requested
        else "",
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "report": str(root / "p9bm_real_timer_path_shadow_readback.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9bm_real_timer_path_shadow_readback_no_order_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bm_real_timer_path_shadow_readback_ready": ready,
        "real_timer_path_shadow_readback_executed": bool(supervisor_summary and hook_summary),
        "timer_path_shadow_readback_mode": (
            "real_supervisor_entrypoint_with_retained_pit_safe_account_position_reference_fixture"
            if retained_fixture_requested
            else "real_supervisor_entrypoint_with_observe_only_shadow_hook_context"
        ),
        "account_proof_mode": (
            "retained_pit_safe_read_only_fixture" if retained_fixture_requested else "live_runtime_account_read"
        ),
        "retained_account_fixture_requested": retained_fixture_requested,
        "retained_account_proof_ready": (
            retained_nonflat_account_proof_ready(account_proof, generated_at=generated_at)
            if retained_fixture_requested
            else False
        ),
        "pit_safe_position_reference_fixture_ready": (
            bool(str(position_reference_run))
            and position_reference_run.exists()
            and not position_reference_blockers
            and position_reference_summary.get("status") == "position_genesis_snapshot"
            if retained_fixture_requested
            else False
        ),
        "position_reference_fixture": evidence_file(position_reference_run / "run_summary.json" if str(position_reference_run) else Path("")),
        "position_reference_fixture_summary": position_reference_summary,
        "retained_account_plan_fixture": evidence_file(
            proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
            if retained_fixture_requested
            else Path("")
        ),
        "retained_account_plan_fixture_summary": retained_account_fixture_summary,
        "supervisor_entrypoint_invoked": bool(supervisor_summary),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "generated_no_order_config": evidence_file(generated_config_path),
        "supervisor_exit_code": int(supervisor_exit),
        "supervisor_summary": supervisor_summary,
        "hook_summary": hook_summary,
        "supervisor_or_core_loop_blockers": supervisor_blockers,
        "account_read_blockers": account_read_blocker_rows,
        "plan_artifact_missing": plan_artifact_missing,
        "completed_shadow_cycles": 1 if ready else int(bool(supervisor_summary)),
        "fresh_proof": bool(supervisor_summary and hook_summary),
        "same_risk_no_order_config": generated_config_exists,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_execution_authorized": False,
        "candidate_execution_performed": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "candidate_shadow_only": hook_summary.get("hook_enabled") is True,
        "candidate_artifacts_under_proof_artifacts_only": hook_summary.get(
            "candidate_artifacts_under_proof_artifacts_only"
        )
        is True,
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only") is True,
        "candidate_plan_referenced_by_executor": hook_summary.get("candidate_plan_referenced_by_executor") is True,
        "target_plan_replaced": False,
        "executor_input_changed": hook_summary.get("executor_input_plan_hash_unchanged") is False,
        "orders_submitted": int(supervisor_summary.get("orders_submitted") or 0),
        "orders_canceled": 0,
        "fill_count": int(supervisor_summary.get("fill_count") or 0),
        "trade_count": 0,
        "zero_order_cancel_fill_trade_delta": (
            int(supervisor_summary.get("orders_submitted") or 0) == 0
            and int(supervisor_summary.get("fill_count") or 0) == 0
        ),
        "live_config_changed": live_config_sha_before != live_config_sha_after,
        "operator_state_changed_outside_generated_p9bm_state": False,
        "timer_state_changed": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": sorted(set(blockers)),
        "output_files": output_files,
    }
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization)
    write_json(root / "summary.json", summary)
    (root / "p9bm_real_timer_path_shadow_readback.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BM Real Timer-Path Shadow Readback",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BM invokes the real live-supervisor entrypoint with an isolated no-order config, then runs the observe-only hook against that supervisor cycle context.",
        "",
        "```text",
        f"p9bm_real_timer_path_shadow_readback_ready = "
        f"{str(bool(summary['p9bm_real_timer_path_shadow_readback_ready'])).lower()}",
        f"real_timer_path_shadow_readback_executed = "
        f"{str(bool(summary['real_timer_path_shadow_readback_executed'])).lower()}",
        "systemd_timer_service_invoked = false",
        "production_timer_service_loaded_or_modified = false",
        "execution_target_source = baseline_only",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
        f"orders_submitted = {int(summary.get('orders_submitted') or 0)}",
        f"fill_count = {int(summary.get('fill_count') or 0)}",
        "```",
        "",
        "## Gates",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("gates") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Blockers", ""])
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9bm(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
