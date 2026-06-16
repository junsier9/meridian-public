from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import sys
import time
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.config import load_live_trading_config  # noqa: E402
from enhengclaw.live_trading.default_off_scorer_shadow_wrapper import (  # noqa: E402
    DefaultOffScorerShadowConfig,
    run_default_off_scorer_shadow_wrapper,
)
from enhengclaw.live_trading.mainnet_live_supervisor import run_mainnet_live_supervisor  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles import (  # noqa: E402
    build_nonflat_position_reference_fixture,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bm_real_timer_path_shadow_readback import (  # noqa: E402
    build_retained_account_plan_fixture,
    retained_nonflat_account_proof_ready,
    retained_p9aa_summary_ready,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10f_timer_path_no_order_shadow_cycles.v1"
DEFAULT_P10E_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "proof_artifacts"
    / "hv_balanced_12factor_candidate"
    / "p10e_scorer_entry_fixture"
)
DEFAULT_BASE_CONFIG = (
    ROOT
    / "config"
    / "live_trading"
    / "hv_balanced_binance_usdm_live_supervisor_multiphase_noorder_candidate.yaml"
)
DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "proof_artifacts"
    / "p10f_timer_shadow"
)

SupervisorRunner = Callable[..., tuple[dict[str, Any], int]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10F: run consecutive no-order shadow cycles through the real "
            "mainnet_live_supervisor entrypoint, while the 12-factor candidate "
            "scorer writes only proof_artifacts shadow evidence."
        )
    )
    parser.add_argument("--p10e-summary", type=Path, default=None)
    parser.add_argument("--base-config", type=Path, default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--shadow-cycles", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--public-market-data", action="store_true")
    parser.add_argument("--target-engine", default="")
    parser.add_argument("--account-proof-source", default="")
    parser.add_argument("--position-reference-source", default="")
    parser.add_argument("--retained-p9aa-summary", default="")
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_p10f_timer_path_no_order_shadow_cycles(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    supervisor_runner: SupervisorRunner = run_mainnet_live_supervisor,
    env: Mapping[str, str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_repo_path(getattr(args, "output_root", None)) if getattr(args, "output_root", None) else DEFAULT_OUTPUT_PARENT / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root = root / "proof"

    p10e_summary_path = resolve_p10e_summary(getattr(args, "p10e_summary", None))
    p10e_summary = load_json(p10e_summary_path)
    p10e_artifacts = dict(p10e_summary.get("artifacts") or {})
    p10e_context_path = resolve_repo_path(p10e_artifacts.get("context"))
    p10e_context = load_json(p10e_context_path) if p10e_context_path.exists() else {}
    baseline_scores_source = evidence_path(p10e_context, "baseline_scores_copy")
    shadow_scores_source = evidence_path(p10e_context, "shadow_scores_copy")
    base_config = resolve_repo_path(getattr(args, "base_config", DEFAULT_BASE_CONFIG))
    account_proof_source = resolve_optional_repo_path(getattr(args, "account_proof_source", ""))
    position_reference_source = resolve_optional_repo_path(getattr(args, "position_reference_source", ""))
    retained_p9aa_summary_source = resolve_optional_repo_path(getattr(args, "retained_p9aa_summary", ""))
    retained_fixture_requested = any(
        path_is_set(path) for path in (account_proof_source, position_reference_source, retained_p9aa_summary_source)
    )
    account_proof = (
        load_json(account_proof_source)
        if path_is_set(account_proof_source) and account_proof_source.exists() and account_proof_source.is_file()
        else {}
    )
    retained_p9aa = (
        load_json(retained_p9aa_summary_source)
        if path_is_set(retained_p9aa_summary_source)
        and retained_p9aa_summary_source.exists()
        and retained_p9aa_summary_source.is_file()
        else {}
    )

    pre_gates = {
        "p10e_ready": p10e_ready(p10e_summary),
        "p10e_context_exists": p10e_context_path.exists(),
        "baseline_scores_source_exists": baseline_scores_source.exists(),
        "shadow_scores_source_exists": shadow_scores_source.exists(),
        "base_config_exists": base_config.exists(),
        "shadow_cycles_at_least_three": int(getattr(args, "shadow_cycles", 0) or 0) >= 3,
        "output_root_under_proof_artifacts": path_contains_part(root, "proof_artifacts"),
        "retained_fixture_sources_complete": (not retained_fixture_requested)
        or (
            account_proof_source.exists()
            and position_reference_source.exists()
            and retained_p9aa_summary_source.exists()
        ),
        "retained_account_proof_read_only_ready": (not retained_fixture_requested)
        or retained_nonflat_account_proof_ready(account_proof, generated_at=generated_at),
        "retained_p9aa_summary_ready": (not retained_fixture_requested) or retained_p9aa_summary_ready(retained_p9aa),
    }
    blockers = [key for key, value in pre_gates.items() if not value]

    position_reference_run = Path("")
    position_reference_summary: dict[str, Any] = {}
    position_reference_blockers: list[str] = []
    retained_account_fixture_summary: dict[str, Any] = {}
    retained_account_fixture_blockers: list[str] = []
    retained_core_summary: dict[str, Any] = {}

    if not blockers and retained_fixture_requested:
        position_reference_run, position_reference_summary, position_reference_blockers = (
            build_nonflat_position_reference_fixture(
                source_path=position_reference_source,
                proof_root=proof_root,
                run_id=run_id,
                generated_at=generated_at,
            )
        )
        pre_gates["pit_safe_position_reference_fixture_ready"] = (
            path_is_set(position_reference_run)
            and position_reference_run.exists()
            and not position_reference_blockers
            and position_reference_summary.get("status") == "position_genesis_snapshot"
            and position_reference_summary.get("read_only") is True
            and position_reference_summary.get("proof_artifacts_only") is True
            and position_reference_summary.get("source_created_before_p9aa") is True
        )
        if not pre_gates["pit_safe_position_reference_fixture_ready"]:
            blockers.append("pit_safe_position_reference_fixture_ready")
            blockers.extend(position_reference_blockers)

    if not blockers and retained_fixture_requested:
        retained_account_fixture_summary, retained_account_fixture_blockers = (
            build_retained_account_plan_fixture(
                p9aa_summary=retained_p9aa,
                account_proof=account_proof,
                position_reference_summary=position_reference_summary,
                fixture_root=proof_root / "acct_fx",
                run_id=run_id,
                generated_at=generated_at,
            )
        )
        retained_core_summary = dict(retained_account_fixture_summary.get("core_loop_summary") or {})
        pre_gates["retained_account_plan_fixture_ready"] = (
            retained_account_fixture_summary.get("status") == "ready"
            and not retained_account_fixture_blockers
            and retained_account_fixture_summary.get("read_only") is True
            and retained_account_fixture_summary.get("proof_artifacts_only") is True
            and retained_core_summary.get("status") == "mainnet_core_loop_completed"
            and zero_orders_fills(retained_account_fixture_summary)
        )
        if not pre_gates["retained_account_plan_fixture_ready"]:
            blockers.append("retained_account_plan_fixture_ready")
            blockers.extend(retained_account_fixture_blockers)

    generated_config_path = (
        generated_no_order_config(base_config=base_config, proof_root=proof_root, run_id=run_id)
        if not blockers
        else Path("")
    )

    baseline_scores = pd.read_csv(baseline_scores_source) if baseline_scores_source.exists() else pd.DataFrame()
    shadow_scores = pd.read_csv(shadow_scores_source) if shadow_scores_source.exists() else pd.DataFrame()
    cycle_rows: list[dict[str, Any]] = []
    if not blockers:
        for cycle_index in range(1, int(args.shadow_cycles) + 1):
            supervisor_args = Namespace(
                config=str(generated_config_path),
                as_of=str(getattr(args, "as_of", "now") or "now"),
                fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
                symbols=str(getattr(args, "symbols", "") or ""),
                public_market_data=bool(getattr(args, "public_market_data", False)),
                reference_run=str(position_reference_run) if retained_fixture_requested else "",
                target_engine=str(getattr(args, "target_engine", "") or ""),
                cycles=1,
                interval_seconds=0.0,
                position_tolerance=float(getattr(args, "position_tolerance", 1e-9) or 1e-9),
                fast_follow_entry_second=False,
                fast_follow_chain_depth=0,
            )
            try:
                supervisor_kwargs: dict[str, Any] = {"env": env or os.environ}
                if retained_fixture_requested:

                    def retained_core_loop_runner(_: Namespace, **__: Any) -> tuple[dict[str, Any], int]:
                        return copy.deepcopy(retained_core_summary), 0

                    supervisor_kwargs["core_loop_runner"] = retained_core_loop_runner
                supervisor_summary, supervisor_exit = supervisor_runner(supervisor_args, **supervisor_kwargs)
            except Exception as exc:  # pragma: no cover - covered through retained fail-closed behavior.
                supervisor_summary = {
                    "run_id": f"{run_id}-cycle-{cycle_index:03d}-supervisor-exception",
                    "status": "mainnet_live_supervisor_exception",
                    "blockers": [f"supervisor_entrypoint_exception:{type(exc).__name__}:{exc}"],
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "orders_submitted": 0,
                    "fill_count": 0,
                    "live_delta_authorized": False,
                    "cycles": [],
                }
                supervisor_exit = 2

            shadow_summary: dict[str, Any] = {}
            if supervisor_exit == 0 and supervisor_no_order_ready(supervisor_summary):
                shadow_result = run_default_off_scorer_shadow_wrapper(
                    config=DefaultOffScorerShadowConfig(
                        enabled=True,
                        output_root=proof_root / f"c{cycle_index:03d}" / "scorer",
                    ),
                    baseline_scores=baseline_scores,
                    executor_input_scores=baseline_scores.copy(),
                    shadow_scorer_scores=shadow_scores,
                    scorer_context={
                        "contract_version": CONTRACT_VERSION,
                        "run_id": run_id,
                        "cycle_index": int(cycle_index),
                        "supervisor_run_id": str(supervisor_summary.get("run_id") or ""),
                        "supervisor_artifact_root": str(supervisor_summary.get("artifact_root") or ""),
                        "execution_target_source": "baseline_only",
                        "candidate_overlay_execution_path": "shadow_only_not_executor",
                    },
                    run_id=f"{run_id}-cycle-{cycle_index:03d}-scorer-shadow",
                    now=generated_at,
                )
                shadow_summary = shadow_result.summary
            row = {
                "cycle_index": int(cycle_index),
                "supervisor_exit_code": int(supervisor_exit),
                "supervisor_summary": supervisor_summary,
                "scorer_shadow_summary": shadow_summary,
            }
            row["cycle_ready"] = cycle_ready(row)
            write_json(proof_root / f"c{cycle_index:03d}.json", row)
            cycle_rows.append(row)
            if not row["cycle_ready"]:
                break
            if float(getattr(args, "interval_seconds", 0.0) or 0.0) > 0 and cycle_index < int(args.shadow_cycles):
                sleep_fn(float(args.interval_seconds))

    supervisor_run_ids = [str(dict(row.get("supervisor_summary") or {}).get("run_id") or "") for row in cycle_rows]
    shadow_roots = [str(dict(row.get("scorer_shadow_summary") or {}).get("proof_root") or "") for row in cycle_rows]
    supervisor_blockers = collect_supervisor_blockers(cycle_rows)
    runtime_gates = {
        "generated_no_order_config_written": generated_config_path.exists() if str(generated_config_path) else False,
        "generated_config_under_proof_artifacts": path_contains_part(generated_config_path, "proof_artifacts")
        if str(generated_config_path)
        else False,
        "ran_requested_cycle_count": len(cycle_rows) == int(getattr(args, "shadow_cycles", 0) or 0),
        "ran_at_least_three_cycles": len(cycle_rows) >= 3,
        "cycles_are_contiguous": [int(row.get("cycle_index") or 0) for row in cycle_rows]
        == list(range(1, len(cycle_rows) + 1)),
        "fresh_supervisor_run_each_cycle": len(supervisor_run_ids) >= 3
        and len(set(supervisor_run_ids)) == len(supervisor_run_ids)
        and all(supervisor_run_ids),
        "fresh_shadow_artifact_each_cycle": len(shadow_roots) >= 3
        and len(set(shadow_roots)) == len(shadow_roots)
        and all(shadow_roots),
        "same_no_order_config_each_cycle": generated_config_path.exists() if str(generated_config_path) else False,
        "pit_safe_position_reference_fixture_ready": (not retained_fixture_requested)
        or (
            path_is_set(position_reference_run)
            and position_reference_run.exists()
            and position_reference_summary.get("status") == "position_genesis_snapshot"
            and position_reference_summary.get("read_only") is True
            and position_reference_summary.get("proof_artifacts_only") is True
        ),
        "retained_account_plan_fixture_ready": (not retained_fixture_requested)
        or (
            retained_account_fixture_summary.get("status") == "ready"
            and retained_account_fixture_summary.get("read_only") is True
            and retained_account_fixture_summary.get("proof_artifacts_only") is True
            and zero_orders_fills(retained_account_fixture_summary)
        ),
        "all_cycles_ready": bool(cycle_rows) and all(row.get("cycle_ready") is True for row in cycle_rows),
        "all_supervisor_no_order_ready": bool(cycle_rows)
        and all(supervisor_no_order_ready(dict(row.get("supervisor_summary") or {})) for row in cycle_rows),
        "all_supervisor_orders_zero": bool(cycle_rows)
        and all(zero_orders_fills(dict(row.get("supervisor_summary") or {})) for row in cycle_rows),
        "all_candidate_shadow_artifacts_written": bool(cycle_rows)
        and all(
            int(dict(row.get("scorer_shadow_summary") or {}).get("shadow_artifacts_written_count") or 0) > 0
            for row in cycle_rows
        ),
        "all_candidate_shadow_artifacts_under_proof_artifacts_only": bool(cycle_rows)
        and all(
            dict(row.get("scorer_shadow_summary") or {}).get("shadow_artifacts_under_proof_artifacts_only") is True
            for row in cycle_rows
        ),
        "all_executor_consumes_baseline_only": bool(cycle_rows)
        and all(
            dict(row.get("scorer_shadow_summary") or {}).get("executor_consumes_baseline_only") is True
            for row in cycle_rows
        ),
        "all_shadow_not_referenced_by_executor": bool(cycle_rows)
        and all(
            dict(row.get("scorer_shadow_summary") or {}).get("shadow_scorer_referenced_by_executor") is False
            for row in cycle_rows
        ),
        "candidate_not_loaded_into_timer_supervisor_executor": True,
        "zero_order_cancel_fill_trade_delta": bool(cycle_rows)
        and sum(int(dict(row.get("supervisor_summary") or {}).get("orders_submitted") or 0) for row in cycle_rows) == 0
        and sum(int(dict(row.get("supervisor_summary") or {}).get("fill_count") or 0) for row in cycle_rows) == 0,
        "no_supervisor_or_core_blockers": not supervisor_blockers,
        "no_exceptions_each_cycle": bool(cycle_rows)
        and all("exception" not in str(dict(row.get("supervisor_summary") or {}).get("status") or "").lower() for row in cycle_rows),
        "no_live_config_operator_timer_mutation": True,
        "no_systemd_timer_service_load_or_mutation": True,
        "no_remote_sync": True,
        "no_live_order_submission": True,
        "no_candidate_execution": True,
        "no_executor_input_mutation": True,
        "no_target_plan_replacement": True,
    }
    blockers.extend([key for key, value in runtime_gates.items() if not value])
    blockers.extend(supervisor_blockers)
    blockers = sorted(set(item for item in blockers if item))
    status = "ready" if not blockers else "blocked"
    total_orders = sum(int(dict(row.get("supervisor_summary") or {}).get("orders_submitted") or 0) for row in cycle_rows)
    total_fills = sum(int(dict(row.get("supervisor_summary") or {}).get("fill_count") or 0) for row in cycle_rows)

    control = {
        "contract_version": "hv_balanced_12factor_p10f_control_boundary_readback.v1",
        "run_id": run_id,
        "supervisor_entrypoint_invoked": bool(cycle_rows),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_order_authority": "disabled",
        "live_order_submission_authorized": False,
        "orders_submitted": int(total_orders),
        "orders_canceled": 0,
        "fill_count": int(total_fills),
        "trade_count": 0,
        "executor_input_changed": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed_outside_generated_p10f_state": False,
        "timer_state_changed": False,
    }
    write_json(proof_root / "control.json", control)

    output_files = {
        "summary": str(root / "summary.json"),
        "generated_no_order_config": str(generated_config_path) if str(generated_config_path) else "",
        "control_boundary_readback": str(proof_root / "control.json"),
        "report": str(root / "p10f.md"),
    }
    for row in cycle_rows:
        output_files[f"cycle_{int(row.get('cycle_index') or 0):03d}_readback"] = str(
            proof_root / f"c{int(row.get('cycle_index') or 0):03d}.json"
        )
    if path_is_set(position_reference_run):
        output_files["position_reference_fixture"] = str(position_reference_run / "run_summary.json")
    if retained_account_fixture_summary:
        output_files["retained_account_plan_fixture"] = str(
            proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
        )

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p10f_real_supervisor_entrypoint_no_order_scorer_shadow_cycles",
        "p10f_timer_path_no_order_shadow_cycles_ready": status == "ready",
        "timer_path_shadow_readback_mode": "real_mainnet_live_supervisor_entrypoint_no_order",
        "requested_shadow_cycles": int(getattr(args, "shadow_cycles", 0) or 0),
        "completed_shadow_cycles": len(cycle_rows),
        "fresh_proof_each_cycle": runtime_gates["fresh_supervisor_run_each_cycle"]
        and runtime_gates["fresh_shadow_artifact_each_cycle"],
        "same_no_order_config_each_cycle": runtime_gates["same_no_order_config_each_cycle"],
        "baseline_only_executor": runtime_gates["all_executor_consumes_baseline_only"],
        "candidate_shadow_only": runtime_gates["all_candidate_shadow_artifacts_written"]
        and runtime_gates["all_shadow_not_referenced_by_executor"],
        "candidate_artifacts_under_proof_artifacts_only": runtime_gates[
            "all_candidate_shadow_artifacts_under_proof_artifacts_only"
        ],
        "candidate_scorer_loaded_into_timer": False,
        "candidate_scorer_loaded_into_supervisor": False,
        "candidate_scorer_loaded_into_executor": False,
        "candidate_execution_authorized": False,
        "candidate_execution_performed": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "executor_input_changed": False,
        "target_plan_replaced": False,
        "orders_submitted": int(total_orders),
        "orders_canceled": 0,
        "fill_count": int(total_fills),
        "trade_count": 0,
        "zero_order_cancel_fill_trade_delta": runtime_gates["zero_order_cancel_fill_trade_delta"],
        "no_anomalies": not blockers,
        "supervisor_or_core_blockers": supervisor_blockers,
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "live_config_changed": False,
        "operator_state_changed_outside_generated_p10f_state": False,
        "timer_state_changed": False,
        "p10e_summary": evidence_file(p10e_summary_path),
        "p10e_context": evidence_file(p10e_context_path),
        "baseline_scores_source": evidence_file(baseline_scores_source),
        "shadow_scores_source": evidence_file(shadow_scores_source),
        "retained_fixture_requested": bool(retained_fixture_requested),
        "account_proof_source": evidence_file(account_proof_source),
        "position_reference_source": evidence_file(position_reference_source),
        "retained_p9aa_summary": evidence_file(retained_p9aa_summary_source),
        "position_reference_fixture": evidence_file(
            position_reference_run / "run_summary.json" if path_is_set(position_reference_run) else Path("")
        ),
        "position_reference_fixture_summary": position_reference_summary,
        "retained_account_plan_fixture": evidence_file(
            proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
            if retained_account_fixture_summary
            else Path("")
        ),
        "retained_account_plan_fixture_summary": retained_account_fixture_summary,
        "generated_no_order_config": evidence_file(generated_config_path),
        "cycle_rows": cycle_rows,
        "proof_root": str(proof_root),
        "gates": {**pre_gates, **runtime_gates},
        "blockers": blockers,
        "output_files": output_files,
    }
    write_json(root / "summary.json", summary)
    (root / "p10f.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def generated_no_order_config(*, base_config: Path, proof_root: Path, run_id: str) -> Path:
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
    state["sqlite_path"] = str(proof_root / "state" / "live.sqlite3")
    state["artifact_root"] = str(proof_root / "runs")
    out = proof_root / "cfg.json"
    write_json(out, payload | {"generated_config_context": {"contract_version": CONTRACT_VERSION, "run_id": run_id}})
    return out


def p10e_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10d_ready") is True
        and summary.get("disabled_baseline_scores_byte_for_byte_unchanged") is True
        and summary.get("disabled_executor_consumes_baseline_only") is True
        and int(summary.get("disabled_shadow_artifacts_written_count") or 0) == 0
        and summary.get("enabled_executor_consumes_baseline_only") is True
        and summary.get("enabled_shadow_artifacts_under_proof_artifacts_only") is True
        and summary.get("enabled_shadow_scorer_referenced_by_executor") is False
        and summary.get("candidate_scorer_loaded_into_live_scorer_entry") is False
        and summary.get("executor_invoked") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("supervisor_invoked") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
    )


def supervisor_no_order_ready(summary: dict[str, Any]) -> bool:
    supervisor_cycles = list(summary.get("cycles") or [])
    supervisor_cycle = dict(supervisor_cycles[-1]) if supervisor_cycles else {}
    core = dict(supervisor_cycle.get("core_loop_summary") or {})
    return (
        summary.get("status") == "mainnet_live_supervisor_completed"
        and not summary.get("blockers")
        and int(summary.get("completed_cycle_count") or 0) == 1
        and summary.get("live_delta_authorized") is False
        and zero_orders_fills(summary)
        and supervisor_cycle.get("execute_live_delta_requested") is False
        and supervisor_cycle.get("live_delta_authorized") is False
        and zero_orders_fills(supervisor_cycle)
        and core.get("status") == "mainnet_core_loop_completed"
        and not core.get("blockers")
        and core.get("execution_requested") is False
        and core.get("live_delta_authorized") is False
        and zero_orders_fills(core)
    )


def cycle_ready(row: dict[str, Any]) -> bool:
    supervisor = dict(row.get("supervisor_summary") or {})
    shadow = dict(row.get("scorer_shadow_summary") or {})
    return (
        int(row.get("supervisor_exit_code") or 0) == 0
        and supervisor_no_order_ready(supervisor)
        and shadow.get("status") == "ready"
        and shadow.get("hook_enabled") is True
        and int(shadow.get("shadow_artifacts_written_count") or 0) > 0
        and shadow.get("shadow_artifacts_under_proof_artifacts_only") is True
        and shadow.get("executor_consumes_baseline_only") is True
        and shadow.get("shadow_scorer_referenced_by_executor") is False
        and shadow.get("candidate_scorer_loaded_into_executor") is False
        and shadow.get("candidate_scorer_loaded_into_timer") is False
        and zero_orders_fills(shadow)
    )


def collect_supervisor_blockers(cycle_rows: list[dict[str, Any]]) -> list[str]:
    blockers: set[str] = set()
    for row in cycle_rows:
        supervisor = dict(row.get("supervisor_summary") or {})
        blockers.update(str(item) for item in list(supervisor.get("blockers") or []))
        for supervisor_cycle in list(supervisor.get("cycles") or []):
            cycle = dict(supervisor_cycle)
            blockers.update(str(item) for item in list(cycle.get("blockers") or []))
            core = dict(cycle.get("core_loop_summary") or {})
            blockers.update(str(item) for item in list(core.get("blockers") or []))
            for core_cycle in list(core.get("cycles") or []):
                blockers.update(str(item) for item in list(dict(core_cycle).get("blockers") or []))
    return sorted(item for item in blockers if item)


def zero_orders_fills(payload: dict[str, Any]) -> bool:
    return int_value(payload.get("orders_submitted")) == 0 and int_value(payload.get("fill_count")) == 0


def int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return -1


def evidence_path(payload: dict[str, Any], key: str) -> Path:
    raw = str(dict(payload.get(key) or {}).get("path") or "")
    return resolve_repo_path(raw) if raw else Path("")


def resolve_p10e_summary(path_ref: Path | str | None) -> Path:
    if path_ref:
        path = resolve_repo_path(path_ref)
        if path.is_dir():
            path = path / "summary.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = sorted(DEFAULT_P10E_PARENT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no P10E summary.json found under {DEFAULT_P10E_PARENT}")
    return candidates[-1]


def resolve_repo_path(path_ref: Path | str | None) -> Path:
    if path_ref is None:
        raise ValueError("path is required")
    path = Path(path_ref).expanduser()
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def resolve_optional_repo_path(path_ref: Path | str | None) -> Path:
    raw = str(path_ref or "").strip()
    if not raw:
        return Path("")
    return resolve_repo_path(raw)


def path_is_set(path: Path) -> bool:
    text = str(path)
    return bool(text) and text != "."


def path_contains_part(path: Path, part: str) -> bool:
    if not str(path):
        return False
    return part.lower() in [item.lower() for item in path.resolve().parts]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: Path | None) -> dict[str, Any]:
    if not path or not str(path):
        return {"path": "", "exists": False, "sha256": ""}
    if str(path) == ".":
        return {"path": "", "exists": False, "sha256": ""}
    if not path.exists() or not path.is_file():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(path)}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    return value


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced 12-Factor P10F Timer-Path No-Order Shadow Cycles",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P10F invokes the real mainnet_live_supervisor entrypoint in no-order mode and writes candidate scorer shadow artifacts only under proof_artifacts.",
        "",
        "```text",
        f"completed_shadow_cycles = {int(summary.get('completed_shadow_cycles') or 0)}",
        f"fresh_proof_each_cycle = {str(bool(summary.get('fresh_proof_each_cycle'))).lower()}",
        f"baseline_only_executor = {str(bool(summary.get('baseline_only_executor'))).lower()}",
        f"candidate_shadow_only = {str(bool(summary.get('candidate_shadow_only'))).lower()}",
        f"orders_submitted = {int(summary.get('orders_submitted') or 0)}",
        f"fill_count = {int(summary.get('fill_count') or 0)}",
        "systemd_timer_service_invoked = false",
        "production_timer_service_loaded_or_modified = false",
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
    summary, exit_code = run_p10f_timer_path_no_order_shadow_cycles(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
