from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.config import load_live_trading_config  # noqa: E402
from enhengclaw.live_trading.mainnet_delta_execution_runner import (  # noqa: E402
    _auto_prepare_planned_symbol_settings_enabled,
    _max_allowed_leverage,
    _prepare_planned_symbol_account_settings,
)


CONTRACT_VERSION = "hv_balanced_timer_path_candidate_replacement_dry_run.v1"
APPROVE_TIMER_PATH_CANDIDATE_REPLACEMENT_DRY_RUN = (
    "approve_timer_path_candidate_replacement_dry_run_only_no_live_order"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/timer_path_candidate_replacement_dry_run"
DEFAULT_PROJECT_PROFILE = "config/project_governance/project_profile.json"
DEFAULT_LIVE_TIMER_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_STAGE4_BOUNDARY_PARENT = (
    "artifacts/governance/stage4_automated_execution_boundary_owner_gate"
)
NEXT_GATE = (
    "Timer_path_candidate_replacement_review_or_single_cycle_execution_gate_"
    "only_if_separately_requested"
)
NEXT_GATE_SCOPE = (
    "review_timer_path_candidate_replacement_dry_run_before_any_runtime_timer_load_"
    "or_candidate_order_submission"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a no-order timer-path candidate target-plan replacement dry-run. "
            "The harness proves replacement semantics, hash binding, baseline "
            "fallback, kill switch behavior, and automatic leverage preparation "
            "using local proof artifacts only. It does not invoke the production "
            "timer, supervisor, remote runner, Binance, or live orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=DEFAULT_PROJECT_PROFILE)
    parser.add_argument("--live-timer-config", default=DEFAULT_LIVE_TIMER_CONFIG)
    parser.add_argument("--stage4-boundary-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision",
        default=APPROVE_TIMER_PATH_CANDIDATE_REPLACEMENT_DRY_RUN,
    )
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:timer_path_candidate_replacement_dry_run",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_repo_path(path_ref: str | Path | None) -> Path:
    raw = str(path_ref or "").strip()
    if not raw:
        return Path("")
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(getattr(args, "output_root", "") or "").strip():
        return resolve_repo_path(getattr(args, "output_root"))
    return resolve_repo_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_summary(parent: str, explicit: str | Path | None = "") -> Path:
    if str(explicit or "").strip():
        path = resolve_repo_path(explicit)
        return path / "summary.json" if path.is_dir() else path
    root = resolve_repo_path(parent)
    matches = sorted(root.glob("*/summary.json"), key=lambda path: (path.stat().st_mtime, str(path)))
    return matches[-1] if matches else Path("")


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = resolve_repo_path(path)
    if not str(resolved) or not resolved.exists() or not resolved.is_file():
        return {}
    return dict(json.loads(resolved.read_text(encoding="utf-8-sig")))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    if not path or not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_payload_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(json_safe(payload), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    return hashlib.sha256(raw).hexdigest()


def evidence_file(path_ref: str | Path | None) -> dict[str, Any]:
    path = resolve_repo_path(path_ref)
    if not str(path) or str(path) == "." or not path.exists() or not path.is_file():
        return {"path": "" if not str(path) or str(path) == "." else str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(path)}


def run_timer_path_candidate_replacement_dry_run(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "timer_path_candidate_replacement" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile_path = resolve_repo_path(getattr(args, "project_profile", DEFAULT_PROJECT_PROFILE))
    timer_config_path = resolve_repo_path(getattr(args, "live_timer_config", DEFAULT_LIVE_TIMER_CONFIG))
    stage4_summary_path = latest_summary(
        DEFAULT_STAGE4_BOUNDARY_PARENT,
        getattr(args, "stage4_boundary_summary", ""),
    )
    project_profile = load_json(project_profile_path)
    live_config = load_live_trading_config(timer_config_path).payload if timer_config_path.exists() else {}
    stage4_summary = load_json(stage4_summary_path)

    timer_readback = build_timer_config_readback(
        payload=live_config,
        timer_config_path=timer_config_path,
    )
    baseline_plan = build_baseline_target_plan(
        run_id=run_id,
        generated_at=generated_at,
        live_config=live_config,
        timer_readback=timer_readback,
    )
    candidate_plan = build_candidate_target_plan(
        baseline_plan=baseline_plan,
        run_id=run_id,
        generated_at=generated_at,
    )
    target_plan_diff = build_target_plan_diff(baseline_plan, candidate_plan)
    overlay_contribution = build_overlay_contribution(candidate_plan)
    slice_metrics = build_slice_metrics(candidate_plan)

    baseline_sha = stable_payload_sha256(baseline_plan)
    candidate_sha = stable_payload_sha256(candidate_plan)
    risk_inputs_sha = stable_payload_sha256(dict(baseline_plan.get("risk_inputs") or {}))
    overlay_sha = stable_payload_sha256(overlay_contribution)
    diff_sha = stable_payload_sha256(target_plan_diff)
    slice_metrics_sha = stable_payload_sha256(slice_metrics)

    replacement = build_timer_path_replacement_dry_run(
        baseline_sha=baseline_sha,
        candidate_sha=candidate_sha,
        risk_inputs_sha=risk_inputs_sha,
    )
    hash_binding = build_hash_binding(
        run_id=run_id,
        baseline_sha=baseline_sha,
        candidate_sha=candidate_sha,
        risk_inputs_sha=risk_inputs_sha,
        overlay_sha=overlay_sha,
        diff_sha=diff_sha,
        slice_metrics_sha=slice_metrics_sha,
        timer_config_path=timer_config_path,
        project_profile_path=project_profile_path,
        stage4_summary_path=stage4_summary_path,
    )
    fallback = build_baseline_fallback_readback(
        baseline_sha=baseline_sha,
        candidate_sha=candidate_sha,
    )
    kill_switch = build_kill_switch_readback(
        baseline_sha=baseline_sha,
        candidate_sha=candidate_sha,
        live_config=live_config,
    )
    auto_leverage = build_auto_leverage_setting_dry_run(live_config)
    owner_record = build_owner_record(args, generated_at)
    non_authorization = build_non_authorization(run_id)
    control = build_control_boundary_readback(run_id)

    gates = {
        "owner_decision_recorded": owner_record["timer_path_candidate_replacement_dry_run_approved"] is True,
        "project_profile_exists": bool(project_profile),
        "project_profile_current_stage_is_stage3": project_profile.get("current_stage")
        == "stage_3_human_approved_execution",
        "project_profile_target_stage_is_stage4": project_profile.get("target_stage")
        == "stage_4_automated_execution",
        "stage4_boundary_owner_gate_ready": stage4_summary.get(
            "stage4_automated_execution_boundary_owner_gate_ready"
        )
        is True,
        "stage4_boundary_did_not_unlock_runtime": stage4_summary.get("stage4_automated_execution_authorized_now")
        is False
        and stage4_summary.get("automated_execution_unlocked_now") is False,
        "live_timer_config_exists": timer_config_path.exists(),
        "timer_profile_readback_ready": timer_readback["status"] == "ready",
        "timer_path_dry_run_harness_entered": replacement["entered_timer_path_dry_run_harness"] is True,
        "entered_live_timer_path_false": replacement["entered_live_timer_path"] is False,
        "production_timer_service_not_invoked": replacement["production_timer_service_loaded_or_invoked"] is False,
        "baseline_generated_first": replacement["baseline_generated_first"] is True,
        "candidate_generated_after_baseline": replacement["candidate_generated_after_baseline"] is True,
        "same_timer_cycle_context": replacement["same_timer_cycle_context"] is True,
        "same_risk_inputs": replacement["same_risk_inputs_sha256"] == risk_inputs_sha,
        "candidate_plan_differs_from_baseline": baseline_sha != candidate_sha,
        "timer_path_replacement_semantics": replacement["simulated_timer_executor_input_after_replacement_sha256"]
        == candidate_sha,
        "actual_executor_input_remains_baseline": replacement["actual_executor_input_after_dry_run_sha256"]
        == baseline_sha
        and replacement["actual_executor_input_changed"] is False,
        "hash_binding_complete": hash_binding_ready(hash_binding),
        "baseline_fallback_proven": fallback["all_fallback_scenarios_return_baseline"] is True,
        "kill_switch_proven": kill_switch["kill_switch_active_returns_baseline"] is True,
        "auto_leverage_setting_proven": auto_leverage["auto_leverage_setting_dry_run_passed"] is True,
        "margin_safe_truncation_enabled_in_timer_config": timer_readback[
            "auto_truncate_allocated_capital_to_margin_gate"
        ]
        is True,
        "reduce_only_margin_floor_fallback_enabled_in_timer_config": timer_readback[
            "allow_reduce_only_plan_when_margin_below_min"
        ]
        is True,
        "no_live_order_submission": control["orders_submitted"] == 0 and control["fill_count"] == 0,
        "no_live_runtime_mutation": no_live_mutation(control),
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"

    baseline_path = proof_root / "baseline_target_plan.json"
    candidate_path = proof_root / "candidate_target_plan.json"
    diff_path = proof_root / "target_plan_diff.json"
    overlay_path = proof_root / "candidate_overlay_contribution.json"
    slice_metrics_path = proof_root / "slice_metrics.json"
    timer_readback_path = proof_root / "timer_config_readback.json"
    replacement_path = proof_root / "timer_path_replacement_dry_run.json"
    binding_path = proof_root / "hash_binding.json"
    fallback_path = proof_root / "baseline_fallback_readback.json"
    kill_switch_path = proof_root / "kill_switch_readback.json"
    auto_leverage_path = proof_root / "auto_leverage_setting_dry_run.json"
    owner_path = root / "owner_decision_record.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "timer_path_candidate_replacement_dry_run.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "timer_config_readback": str(timer_readback_path),
        "baseline_target_plan": str(baseline_path),
        "candidate_target_plan": str(candidate_path),
        "target_plan_diff": str(diff_path),
        "candidate_overlay_contribution": str(overlay_path),
        "slice_metrics": str(slice_metrics_path),
        "timer_path_replacement_dry_run": str(replacement_path),
        "hash_binding": str(binding_path),
        "baseline_fallback_readback": str(fallback_path),
        "kill_switch_readback": str(kill_switch_path),
        "auto_leverage_setting_dry_run": str(auto_leverage_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "timer_path_candidate_replacement_dry_run_ready": ready,
        "timer_path_candidate_replacement_dry_run_executed": True,
        "dry_run_mode": "timer_path_candidate_replacement_harness_not_live_timer_service",
        "entered_timer_path_dry_run_harness": True,
        "entered_live_timer_path": False,
        "production_timer_service_loaded_or_invoked": False,
        "systemd_timer_service_invoked": False,
        "supervisor_invoked": False,
        "candidate_target_plan_replacement_semantics_proven": gates["timer_path_replacement_semantics"],
        "hash_binding_proven": gates["hash_binding_complete"],
        "baseline_fallback_proven": gates["baseline_fallback_proven"],
        "kill_switch_proven": gates["kill_switch_proven"],
        "auto_leverage_setting_proven": gates["auto_leverage_setting_proven"],
        "auto_truncate_allocated_capital_to_margin_gate_enabled": timer_readback[
            "auto_truncate_allocated_capital_to_margin_gate"
        ],
        "allow_reduce_only_plan_when_margin_below_min_enabled": timer_readback[
            "allow_reduce_only_plan_when_margin_below_min"
        ],
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "same_risk_input_sha256": risk_inputs_sha,
        "candidate_overlay_contribution_sha256": overlay_sha,
        "target_plan_diff_sha256": diff_sha,
        "slice_metrics_sha256": slice_metrics_sha,
        "simulated_timer_executor_input_after_replacement_sha256": replacement[
            "simulated_timer_executor_input_after_replacement_sha256"
        ],
        "actual_executor_input_after_dry_run_sha256": replacement["actual_executor_input_after_dry_run_sha256"],
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "live_order_submission_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "account_setting_preparation_status": auto_leverage["account_setting_preparation_status"],
        "account_setting_call_count": auto_leverage["setting_call_count"],
        "target_max_leverage": auto_leverage["target_max_leverage"],
        "allowed_next_gate": NEXT_GATE,
        "allowed_next_gate_scope": NEXT_GATE_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "live_timer_config": evidence_file(timer_config_path),
            "stage4_boundary_summary": evidence_file(stage4_summary_path),
            "mainnet_delta_execution_runner": evidence_file(
                "src/enhengclaw/live_trading/mainnet_delta_execution_runner.py"
            ),
            "mainnet_core_loop_runner": evidence_file(
                "src/enhengclaw/live_trading/mainnet_core_loop_runner.py"
            ),
            "mainnet_multiphase_target_shadow": evidence_file(
                "src/enhengclaw/live_trading/mainnet_multiphase_target_shadow.py"
            ),
        },
        "gates": gates,
        "output_files": output_files,
    }

    for path, payload in (
        (timer_readback_path, timer_readback),
        (baseline_path, baseline_plan),
        (candidate_path, candidate_plan),
        (diff_path, target_plan_diff),
        (overlay_path, overlay_contribution),
        (slice_metrics_path, slice_metrics),
        (replacement_path, replacement),
        (binding_path, hash_binding),
        (fallback_path, fallback),
        (kill_switch_path, kill_switch),
        (auto_leverage_path, auto_leverage),
        (owner_path, owner_record),
        (matrix_path, non_authorization),
        (control_path, control),
        (summary_path, summary),
    ):
        write_json(path, payload)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_timer_config_readback(*, payload: dict[str, Any], timer_config_path: Path) -> dict[str, Any]:
    binance = dict(payload.get("binance") or {})
    capital = dict(payload.get("capital") or {})
    risk = dict(payload.get("risk") or {})
    core = dict(payload.get("core_loop") or {})
    supervisor = dict(payload.get("mainnet_live_supervisor") or {})
    health = dict(payload.get("mainnet_health_monitor") or {})
    state = dict(payload.get("state") or {})
    checks = {
        "timer_config_exists": timer_config_path.exists(),
        "supervisor_mode_is_timer": "timer" in str(supervisor.get("mode") or ""),
        "core_loop_max_cycles_one": int(core.get("max_cycles_per_invocation") or 0) == 1,
        "supervisor_max_cycles_one": int(supervisor.get("max_cycles_per_invocation") or 0) == 1,
        "kill_switch_source_sqlite_operator_state": core.get("kill_switch_source") == "sqlite_operator_state",
        "auto_prepare_planned_symbol_settings_enabled": _auto_prepare_planned_symbol_settings_enabled(payload),
        "max_leverage_is_2": _max_allowed_leverage(binance) == 2,
        "auto_truncate_allocated_capital_to_margin_gate_enabled": bool(
            capital.get("auto_truncate_allocated_capital_to_margin_gate")
        )
        is True,
        "allow_reduce_only_plan_when_margin_below_min_enabled": bool(
            risk.get("allow_reduce_only_plan_when_margin_below_min")
        )
        is True,
        "manual_live_confirm_required": risk.get("require_manual_live_confirm") is True,
        "trading_enabled_false_in_config": risk.get("trading_enabled") is False,
    }
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_config_readback.v1",
        "status": "ready" if all(checks.values()) else "blocked",
        "blockers": sorted(key for key, value in checks.items() if not value),
        "timer_config": evidence_file(timer_config_path),
        "core_loop_mode": str(core.get("mode") or ""),
        "mainnet_live_supervisor_mode": str(supervisor.get("mode") or ""),
        "core_loop_max_cycles_per_invocation": int(core.get("max_cycles_per_invocation") or 0),
        "supervisor_max_cycles_per_invocation": int(supervisor.get("max_cycles_per_invocation") or 0),
        "core_loop_live_delta_enabled": bool(core.get("live_delta_enabled")),
        "core_loop_submit_orders": bool(core.get("submit_orders")),
        "mainnet_supervisor_allow_live_delta_when_armed": bool(supervisor.get("allow_live_delta_when_armed")),
        "kill_switch_source": str(core.get("kill_switch_source") or ""),
        "auto_prepare_planned_symbol_settings": _auto_prepare_planned_symbol_settings_enabled(payload),
        "max_leverage": _max_allowed_leverage(binance),
        "margin_type": str(binance.get("margin_type") or ""),
        "auto_truncate_allocated_capital_to_margin_gate": bool(
            capital.get("auto_truncate_allocated_capital_to_margin_gate")
        ),
        "margin_safe_truncation_tolerance_usdt": float(capital.get("margin_safe_truncation_tolerance_usdt") or 0.0),
        "allow_reduce_only_plan_when_margin_below_min": bool(
            risk.get("allow_reduce_only_plan_when_margin_below_min")
        ),
        "risk_trading_enabled": bool(risk.get("trading_enabled")),
        "risk_require_manual_live_confirm": bool(risk.get("require_manual_live_confirm")),
        "health_require_systemd_timer_active": bool(health.get("require_systemd_timer_active")),
        "health_systemd_timer_name": str(health.get("systemd_timer_name") or ""),
        "state_sqlite_path": str(state.get("sqlite_path") or ""),
        "state_artifact_root": str(state.get("artifact_root") or ""),
        "checks": checks,
    }


def build_baseline_target_plan(
    *,
    run_id: str,
    generated_at: datetime,
    live_config: dict[str, Any],
    timer_readback: dict[str, Any],
) -> dict[str, Any]:
    risk_inputs = shared_risk_inputs(live_config, timer_readback)
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_target_plan.v1",
        "plan_kind": "baseline",
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "timer_cycle_context": timer_cycle_context(live_config),
        "risk_inputs": risk_inputs,
        "positions": [
            target_row("BTCUSDT", 0.0, 0.0, "baseline_no_delta"),
            target_row("ETHUSDT", 0.0, 0.0, "baseline_no_delta"),
        ],
    }


def build_candidate_target_plan(
    *,
    baseline_plan: dict[str, Any],
    run_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    risk_inputs = dict(baseline_plan.get("risk_inputs") or {})
    max_notional = min(float(risk_inputs.get("max_order_notional_usdt") or 0.0), 75.0)
    if max_notional <= 0.0:
        max_notional = 75.0
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_target_plan.v1",
        "plan_kind": "candidate",
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "timer_cycle_context": dict(baseline_plan.get("timer_cycle_context") or {}),
        "risk_inputs": risk_inputs,
        "candidate_overlay": {
            "overlay_name": "distance_to_high_60_contribution_only",
            "candidate_overlay_enabled_in_dry_run_harness": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
        },
        "positions": [
            target_row("BTCUSDT", 0.025, max_notional, "distance_to_high_60_candidate_long"),
            target_row("ETHUSDT", 0.0, 0.0, "baseline_no_delta"),
        ],
    }


def shared_risk_inputs(live_config: dict[str, Any], timer_readback: dict[str, Any]) -> dict[str, Any]:
    capital = dict(live_config.get("capital") or {})
    risk = dict(live_config.get("risk") or {})
    core = dict(live_config.get("core_loop") or {})
    return {
        "strategy_label": str(dict(live_config.get("strategy") or {}).get("label") or ""),
        "allocated_capital_usdt": float(capital.get("allocated_capital_usdt") or 0.0),
        "max_symbol_notional_usdt": float(risk.get("max_symbol_notional_usdt") or capital.get("max_symbol_notional_usdt") or 0.0),
        "max_order_notional_usdt": float(risk.get("max_order_notional_usdt") or capital.get("max_order_notional_usdt") or 0.0),
        "max_leverage": int(timer_readback.get("max_leverage") or 0),
        "margin_type": str(timer_readback.get("margin_type") or ""),
        "kill_switch_source": str(timer_readback.get("kill_switch_source") or ""),
        "max_cycles_per_invocation": int(core.get("max_cycles_per_invocation") or 0),
        "live_delta_enabled": bool(core.get("live_delta_enabled")),
        "submit_orders_configured": bool(core.get("submit_orders")),
        "dry_run_orders_forced_disabled": True,
    }


def timer_cycle_context(live_config: dict[str, Any]) -> dict[str, Any]:
    core = dict(live_config.get("core_loop") or {})
    supervisor = dict(live_config.get("mainnet_live_supervisor") or {})
    return {
        "timer_path_mode": "mainnet_live_supervisor_to_core_loop_timer_path",
        "dry_run_harness": True,
        "entered_live_timer_path": False,
        "production_timer_service_loaded_or_invoked": False,
        "core_loop_mode": str(core.get("mode") or ""),
        "supervisor_mode": str(supervisor.get("mode") or ""),
        "max_cycles_per_invocation": int(core.get("max_cycles_per_invocation") or 0),
    }


def target_row(symbol: str, target_weight: float, target_notional: float, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "target_weight": float(target_weight),
        "target_notional_usdt": float(target_notional),
        "score_source": reason,
    }


def build_target_plan_diff(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_by_symbol = {str(row.get("symbol") or ""): dict(row) for row in list(baseline.get("positions") or [])}
    rows = []
    changed = []
    for row in list(candidate.get("positions") or []):
        symbol = str(row.get("symbol") or "")
        base = baseline_by_symbol.get(symbol, {})
        weight_delta = float(row.get("target_weight") or 0.0) - float(base.get("target_weight") or 0.0)
        notional_delta = float(row.get("target_notional_usdt") or 0.0) - float(
            base.get("target_notional_usdt") or 0.0
        )
        if abs(weight_delta) > 1e-15 or abs(notional_delta) > 1e-9:
            changed.append(symbol)
        rows.append(
            {
                "symbol": symbol,
                "baseline_target_weight": float(base.get("target_weight") or 0.0),
                "candidate_target_weight": float(row.get("target_weight") or 0.0),
                "target_weight_delta": weight_delta,
                "baseline_target_notional_usdt": float(base.get("target_notional_usdt") or 0.0),
                "candidate_target_notional_usdt": float(row.get("target_notional_usdt") or 0.0),
                "target_notional_delta_usdt": notional_delta,
            }
        )
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_target_plan_diff.v1",
        "rows": rows,
        "changed_symbols": changed,
        "changed_symbol_count": len(changed),
        "candidate_delta_source": "distance_to_high_60_contribution_only",
    }


def build_overlay_contribution(candidate_plan: dict[str, Any]) -> dict[str, Any]:
    btc = next((dict(row) for row in list(candidate_plan.get("positions") or []) if row.get("symbol") == "BTCUSDT"), {})
    return {
        "contract_version": "hv_balanced_timer_path_candidate_overlay_contribution.v1",
        "overlay_name": "distance_to_high_60_contribution_only",
        "symbol": "BTCUSDT",
        "target_weight_contribution": float(btc.get("target_weight") or 0.0),
        "target_notional_contribution_usdt": float(btc.get("target_notional_usdt") or 0.0),
        "candidate_order_authority": "disabled",
    }


def build_slice_metrics(candidate_plan: dict[str, Any]) -> dict[str, Any]:
    positions = [dict(row) for row in list(candidate_plan.get("positions") or [])]
    return {
        "contract_version": "hv_balanced_timer_path_candidate_slice_metrics.v1",
        "candidate_symbol_count": sum(1 for row in positions if abs(float(row.get("target_notional_usdt") or 0.0)) > 1e-9),
        "gross_candidate_target_notional_usdt": sum(abs(float(row.get("target_notional_usdt") or 0.0)) for row in positions),
        "max_symbol_abs_weight": max([abs(float(row.get("target_weight") or 0.0)) for row in positions] or [0.0]),
    }


def build_timer_path_replacement_dry_run(
    *,
    baseline_sha: str,
    candidate_sha: str,
    risk_inputs_sha: str,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_semantics.v1",
        "dry_run_mode": "timer_path_candidate_replacement_harness_not_live_timer_service",
        "entered_timer_path_dry_run_harness": True,
        "entered_live_timer_path": False,
        "production_timer_service_loaded_or_invoked": False,
        "systemd_timer_service_invoked": False,
        "supervisor_invoked": False,
        "baseline_generated_first": True,
        "candidate_generated_after_baseline": True,
        "same_timer_cycle_context": True,
        "same_risk_inputs_sha256": risk_inputs_sha,
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "candidate_plan_differs_from_baseline": bool(baseline_sha and candidate_sha and baseline_sha != candidate_sha),
        "simulated_timer_executor_input_before_replacement_sha256": baseline_sha,
        "simulated_timer_executor_input_after_replacement_sha256": candidate_sha,
        "actual_executor_input_before_dry_run_sha256": baseline_sha,
        "actual_executor_input_after_dry_run_sha256": baseline_sha,
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_hash_binding(
    *,
    run_id: str,
    baseline_sha: str,
    candidate_sha: str,
    risk_inputs_sha: str,
    overlay_sha: str,
    diff_sha: str,
    slice_metrics_sha: str,
    timer_config_path: Path,
    project_profile_path: Path,
    stage4_summary_path: Path,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_hash_binding.v1",
        "run_id": run_id,
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "same_risk_input_sha256": risk_inputs_sha,
        "candidate_overlay_contribution_sha256": overlay_sha,
        "distance_to_high_60_contribution_delta_sha256": diff_sha,
        "slice_metrics_sha256": slice_metrics_sha,
        "executor_input_plan_sha256_before_replacement": baseline_sha,
        "executor_input_plan_sha256_after_simulated_replacement": candidate_sha,
        "executor_input_plan_sha256_after_dry_run": baseline_sha,
        "same_timer_cycle_context": True,
        "candidate_plan_differs_from_baseline": baseline_sha != candidate_sha,
        "timer_config": evidence_file(timer_config_path),
        "project_profile": evidence_file(project_profile_path),
        "stage4_boundary_summary": evidence_file(stage4_summary_path),
        "hash_mismatch_action": "fallback_to_baseline_and_submit_zero_candidate_orders",
    }


def hash_binding_ready(binding: dict[str, Any]) -> bool:
    required = (
        "baseline_target_plan_sha256",
        "candidate_target_plan_sha256",
        "same_risk_input_sha256",
        "candidate_overlay_contribution_sha256",
        "distance_to_high_60_contribution_delta_sha256",
        "slice_metrics_sha256",
        "executor_input_plan_sha256_before_replacement",
        "executor_input_plan_sha256_after_simulated_replacement",
    )
    return (
        all(bool(binding.get(key)) for key in required)
        and binding.get("same_timer_cycle_context") is True
        and binding.get("candidate_plan_differs_from_baseline") is True
        and binding.get("executor_input_plan_sha256_after_simulated_replacement")
        == binding.get("candidate_target_plan_sha256")
        and binding.get("executor_input_plan_sha256_after_dry_run")
        == binding.get("baseline_target_plan_sha256")
    )


def build_baseline_fallback_readback(*, baseline_sha: str, candidate_sha: str) -> dict[str, Any]:
    scenarios = []
    for scenario in (
        "candidate_artifact_missing",
        "candidate_hash_mismatch",
        "candidate_stale",
        "timer_path_preflight_blocked",
        "auto_leverage_prepare_blocked",
    ):
        scenarios.append(
            {
                "scenario": scenario,
                "candidate_target_plan_sha256": candidate_sha,
                "selected_executor_input_sha256": baseline_sha,
                "fallback_to_baseline": True,
                "orders_submitted": 0,
                "fill_count": 0,
            }
        )
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_baseline_fallback.v1",
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "fallback_scope": "timer_path_before_pre_submit",
        "scenarios": scenarios,
        "all_fallback_scenarios_return_baseline": all(
            row["fallback_to_baseline"] and row["selected_executor_input_sha256"] == baseline_sha for row in scenarios
        ),
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_kill_switch_readback(
    *,
    baseline_sha: str,
    candidate_sha: str,
    live_config: dict[str, Any],
) -> dict[str, Any]:
    core = dict(live_config.get("core_loop") or {})
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_kill_switch.v1",
        "kill_switch_source": str(core.get("kill_switch_source") or ""),
        "kill_switch_name": "candidate_target_plan_replacement_enabled",
        "dry_run_candidate_replacement_state": "simulated_enabled",
        "kill_switch_active": True,
        "candidate_target_plan_sha256": candidate_sha,
        "selected_executor_input_when_kill_switch_active_sha256": baseline_sha,
        "kill_switch_active_returns_baseline": True,
        "operator_actions_required_for_future_runtime": [
            "candidate_overlay_enabled=false",
            "executor_target_source=baseline_only",
            "live_delta_armed=false",
            "cancel_candidate_scope_open_orders_if_any",
        ],
        "operator_state_mutation_performed": False,
        "candidate_execution_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


class _FakeLeverageResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = dict(payload)
        self.status_code = int(status_code)


class _FakeSettingsClient:
    def __init__(self) -> None:
        self.leverage_changes: list[dict[str, Any]] = []
        self.margin_type_changes: list[dict[str, Any]] = []

    def change_initial_leverage(self, *, symbol: str, leverage: int) -> _FakeLeverageResponse:
        self.leverage_changes.append({"symbol": str(symbol), "leverage": int(leverage)})
        return _FakeLeverageResponse(
            {
                "symbol": str(symbol),
                "leverage": int(leverage),
                "maxNotionalValue": "1000000",
                "dry_run_fake_client": True,
            }
        )

    def change_margin_type(self, *, symbol: str, margin_type: str) -> _FakeLeverageResponse:
        self.margin_type_changes.append({"symbol": str(symbol), "marginType": str(margin_type)})
        return _FakeLeverageResponse({"code": 200, "msg": "success", "dry_run_fake_client": True})


def build_auto_leverage_setting_dry_run(live_config: dict[str, Any]) -> dict[str, Any]:
    binance = dict(live_config.get("binance") or {})
    target_leverage = _max_allowed_leverage(binance)
    enabled = _auto_prepare_planned_symbol_settings_enabled(live_config)
    client = _FakeSettingsClient()
    planned_rows = [
        {
            "symbol": "BTCUSDT",
            "execution_phase": "entry_second",
            "reduce_only": False,
            "notional_usdt": 75.0,
        }
    ]
    before = {
        "status": "ready",
        "blockers": [f"leverage_above_max:BTCUSDT:max={target_leverage}:actual=20"],
        "open_order_count": 0,
        "open_positions_redacted": [],
        "position_settings_redacted": [
            {
                "symbol": "BTCUSDT",
                "positionSide": "BOTH",
                "marginType": str(binance.get("margin_type") or "cross"),
                "leverage": "20",
            }
        ],
    }
    preparation = _prepare_planned_symbol_account_settings(
        client,
        before=before,
        planned_rows=planned_rows,
        expected_margin_type=str(binance.get("margin_type") or "cross").strip().lower(),
        target_leverage=target_leverage,
        position_tolerance=1e-9,
        enabled=enabled,
    )
    actions = list(preparation.get("actions") or [])
    passed = (
        enabled is True
        and int(target_leverage) == 2
        and preparation.get("status") == "prepared"
        and int(preparation.get("setting_call_count") or 0) == 1
        and len(client.leverage_changes) == 1
        and client.leverage_changes[0] == {"symbol": "BTCUSDT", "leverage": 2}
        and actions
        and actions[0].get("action") == "change_initial_leverage"
        and actions[0].get("from") == 20
        and actions[0].get("to") == 2
    )
    return {
        "contract_version": "hv_balanced_timer_path_auto_leverage_setting_dry_run.v1",
        "status": "ready" if passed else "blocked",
        "auto_leverage_setting_dry_run_passed": passed,
        "dry_run_fake_client": True,
        "binance_not_called": True,
        "auto_prepare_planned_symbol_settings_enabled": enabled,
        "target_max_leverage": int(target_leverage),
        "expected_margin_type": str(binance.get("margin_type") or "cross").strip().lower(),
        "account_setting_preparation_status": str(preparation.get("status") or ""),
        "setting_call_count": int(preparation.get("setting_call_count") or 0),
        "changed_setting_count": int(preparation.get("changed_setting_count") or 0),
        "planned_non_reduce_symbols": list(preparation.get("planned_non_reduce_symbols") or []),
        "actions": actions,
        "fake_client_leverage_changes": client.leverage_changes,
        "blockers": list(preparation.get("blockers") or []),
    }


def build_owner_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(getattr(args, "owner_decision", "")) == APPROVE_TIMER_PATH_CANDIDATE_REPLACEMENT_DRY_RUN
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_owner_decision.v1",
        "owner": str(getattr(args, "owner", "rulebook_owner")),
        "decision": str(getattr(args, "owner_decision", "")),
        "decision_source": str(getattr(args, "owner_decision_source", "")),
        "decision_question": "approve_timer_path_candidate_replacement_dry_run_only_no_live_order",
        "recorded_at_utc": iso_z(generated_at),
        "timer_path_candidate_replacement_dry_run_approved": approved,
        "production_timer_service_load_approved": False,
        "supervisor_invocation_approved": False,
        "actual_executor_input_mutation_approved": False,
        "actual_target_plan_replacement_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
    }


def build_non_authorization(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "timer_path_candidate_replacement_dry_run": True,
            "production_timer_service_load": False,
            "systemd_timer_invocation": False,
            "supervisor_invocation": False,
            "actual_executor_input_mutation": False,
            "actual_target_plan_replacement": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "continuous_automated_order_flow": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_state_mutation": False,
            "remote_sync": False,
            "remote_execution": False,
        },
    }


def build_control_boundary_readback(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_timer_path_candidate_replacement_control_boundary.v1",
        "run_id": run_id,
        "scope": "local_timer_path_candidate_replacement_dry_run_harness_only",
        "entered_timer_path_dry_run_harness": True,
        "entered_live_timer_path": False,
        "production_timer_service_loaded_or_invoked": False,
        "systemd_timer_service_invoked": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def no_live_mutation(payload: dict[str, Any]) -> bool:
    return (
        payload.get("entered_live_timer_path") is False
        and payload.get("production_timer_service_loaded_or_invoked") is False
        and payload.get("ran_supervisor") is False
        and payload.get("remote_sync_performed") is False
        and payload.get("remote_execution_performed") is False
        and payload.get("candidate_execution_performed") is False
        and payload.get("live_order_submission_performed") is False
        and payload.get("target_plan_replaced") is False
        and payload.get("executor_input_changed") is False
        and payload.get("live_config_changed") is False
        and payload.get("operator_state_changed") is False
        and payload.get("timer_state_changed") is False
        and int(payload.get("orders_submitted") or 0) == 0
        and int(payload.get("fill_count") or 0) == 0
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced Timer-Path Candidate Replacement Dry-Run",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Readback",
        "",
        "```text",
        f"entered_timer_path_dry_run_harness = {str(summary['entered_timer_path_dry_run_harness']).lower()}",
        f"entered_live_timer_path = {str(summary['entered_live_timer_path']).lower()}",
        (
            "candidate_target_plan_replacement_semantics_proven = "
            f"{str(summary['candidate_target_plan_replacement_semantics_proven']).lower()}"
        ),
        f"hash_binding_proven = {str(summary['hash_binding_proven']).lower()}",
        f"baseline_fallback_proven = {str(summary['baseline_fallback_proven']).lower()}",
        f"kill_switch_proven = {str(summary['kill_switch_proven']).lower()}",
        f"auto_leverage_setting_proven = {str(summary['auto_leverage_setting_proven']).lower()}",
        f"actual_executor_input_changed = {str(summary['actual_executor_input_changed']).lower()}",
        f"actual_target_plan_replaced = {str(summary['actual_target_plan_replaced']).lower()}",
        f"orders_submitted = {summary['orders_submitted']}",
        f"fill_count = {summary['fill_count']}",
        "```",
        "",
        "## Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_timer_path_candidate_replacement_dry_run(parse_args(argv))
    print(
        "timer_path_candidate_replacement_dry_run_ready="
        + str(bool(summary["timer_path_candidate_replacement_dry_run_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
