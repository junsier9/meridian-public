from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    CAN_TRADE_SOURCE,
    build_pit_safe_account_proof,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
    CommandResult,
    CommandRunner,
    json_from_command,
    local_command_runner,
    remote_snapshot_script,
    snapshot_boundary_ok,
    ssh_args,
    timer_state_digest,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    collector_ready as p9ce_collector_ready,
    fingerprint_delta_acceptance as p9ce_fingerprint_delta_acceptance,
    remote_identity_ready as p9ce_remote_identity_ready,
    remote_p9ce_collector_command,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    account_delta_acceptance,
    collector_contract_ready as p9ci_collector_ready,
    history_delta_acceptance,
    remote_identity_ready as p9ci_remote_identity_ready,
    remote_p9ci_collector_command,
    sanitized_collector as sanitize_p9ci_collector,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    file_sha256,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_timer_path_post_canary_health_position_readback.v1"
APPROVE_DECISION = (
    "approve_post_canary_read_only_health_position_readback_only_no_order_no_candidate_no_timer_no_supervisor"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/timer_path_post_canary_health_position_readback"
DEFAULT_CANARY_SYMBOL = "BTCUSDT"
DEFAULT_MAX_HISTORY_SYMBOLS = 20
NEXT_GATE = (
    "post_canary_health_position_readback_review_or_followup_gate_only_if_separately_requested"
)
NEXT_GATE_SCOPE = (
    "review_post_canary_health_position_readback_evidence_before_any_live_order_or_executor_path_change"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a stand-alone post-canary read-only health/position readback "
            "against the remote Meridian live runner. It reuses the P9CE and P9CI "
            "stdout-only collectors plus pre/post control-boundary snapshots and "
            "the PIT-safe v2/v3 account proof builder. It does not depend on the "
            "P9CN/P9CD ladder, does not call order-test endpoints, write remote "
            "files, remote sync, invoke supervisor/timer paths, execute the "
            "candidate, replace target plans, mutate executor input, cancel "
            "orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--canary-symbol", default=DEFAULT_CANARY_SYMBOL)
    parser.add_argument(
        "--max-history-symbols", type=int, default=DEFAULT_MAX_HISTORY_SYMBOLS
    )
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:post_canary_health_position_readback_only_no_order",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def ssh_stdin_run(host: str, timeout: int, script: str) -> CommandResult:
    """Run a bash script on the remote host by piping it through SSH stdin.

    Avoids the shell-quote escape pitfalls of passing the script via the
    ``bash -lc '<...>'`` command-line argument under Windows OpenSSH.
    """
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={int(timeout)}",
        host,
        "bash -l",
    ]
    proc = subprocess.run(
        args,
        input=script,
        text=True,
        capture_output=True,
    )
    return CommandResult(
        args=args,
        returncode=int(proc.returncode),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_DECISION
    return {
        "contract_version": "hv_balanced_timer_path_post_canary_health_position_readback_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_post_canary_read_only_health_position_readback_only_no_order",
        "decision_effect": (
            "execute_post_canary_read_only_collectors_and_snapshots" if approved else "none"
        ),
        "post_canary_read_only_readback_approved": approved,
        "remote_stdout_read_only_collection_approved": approved,
        "remote_sync_approved": False,
        "remote_files_written_approved": False,
        "supervisor_invocation_approved": False,
        "timer_path_load_approved": False,
        "production_timer_service_load_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "stage_governance_change_approved": False,
    }


def write_proof_manifest(
    proof_root: Path, proof_files: dict[str, Path]
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for key in sorted(proof_files):
        path = proof_files[key]
        if not path or not path.exists() or not path.is_file():
            rows.append({"name": key, "path": str(path), "exists": False, "sha256": ""})
            continue
        rows.append(
            {
                "name": key,
                "path": str(path.relative_to(ROOT)) if path.is_absolute() and ROOT in path.parents else str(path),
                "exists": True,
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "contract_version": "hv_balanced_timer_path_post_canary_health_position_readback_proof_artifact_manifest.v1",
        "files": rows,
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = {
        "path": str(manifest_path),
        "sha256": file_sha256(manifest_path),
    }
    return manifest


def build_post_canary_readback(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "post_canary" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)

    pre_checks = {
        "owner_decision_post_canary_readback_recorded": str(args.owner_decision)
        == APPROVE_DECISION,
        "remote_host_matches_expected_runner": str(args.remote_host)
        == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo)
        == DEFAULT_REMOTE_REPO,
        "canary_symbol_set": bool(str(args.canary_symbol).strip()),
    }
    blockers = [key for key, value in pre_checks.items() if not value]
    command_records: list[dict[str, Any]] = []
    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    account_collector: dict[str, Any] = {}
    market_collector: dict[str, Any] = {}
    account_sanitized: dict[str, Any] = {}
    account_proof: dict[str, Any] = {}

    def run_record(label: str, script: str) -> CommandResult:
        result = ssh_stdin_run(args.remote_host, args.ssh_connect_timeout, script)
        command_records.append(
            {
                "label": label,
                "args": list(result.args),
                "script_sha256": sha256_text(script),
                "script_bytes": len(script.encode("utf-8")),
                "returncode": result.returncode,
                "stdout_sha256": sha256_text(result.stdout),
                "stdout_bytes": len(result.stdout.encode("utf-8")),
                "stderr_tail": result.stderr[-4000:],
            }
        )
        return result

    if not blockers:
        pre_result = run_record(
            "pre_control_snapshot",
            remote_snapshot_script(args.remote_repo, args.remote_config),
        )
        pre_snapshot = json_from_command(pre_result)
        write_json(root / "pre_control_snapshot.json", pre_snapshot)
        if pre_result.returncode != 0:
            blockers.append("pre_control_snapshot_failed")

    if not blockers:
        account_result = run_record(
            "remote_stdout_pit_safe_v2v3_account_collector",
            remote_p9ci_collector_command(
                remote_repo=args.remote_repo,
                remote_live_env=args.remote_live_env,
                remote_python=args.remote_python,
                remote_config=args.remote_config,
                expected_egress_ip=args.expected_egress_ip,
                history_canary_symbol=args.canary_symbol,
                max_history_symbols=int(args.max_history_symbols or 0),
            ),
        )
        account_collector = json_from_command(account_result)
        account_sanitized = sanitize_p9ci_collector(account_collector)
        write_json(
            root / "remote_stdout_account_collector_sanitized.json", account_sanitized
        )
        if account_result.returncode != 0:
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_failed")
        if not p9ci_collector_ready(account_collector):
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_not_ready")
        fixture = {
            "expected_egress_ip": args.expected_egress_ip,
            "pre_egress_ip": account_collector.get("pre_egress_ip"),
            "post_egress_ip": account_collector.get("post_egress_ip"),
            "pre_endpoint_results": dict(account_collector.get("pre_endpoint_results") or {}),
            "post_endpoint_results": dict(account_collector.get("post_endpoint_results") or {}),
            "side_effects": dict(account_collector.get("side_effects") or {}),
        }
        account_proof = build_pit_safe_account_proof(fixture, generated_at=started_at)

    if not blockers:
        market_result = run_record(
            "remote_stdout_market_and_fingerprint_collector",
            remote_p9ce_collector_command(
                remote_repo=args.remote_repo,
                remote_live_env=args.remote_live_env,
                remote_python=args.remote_python,
                remote_config=args.remote_config,
                expected_egress_ip=args.expected_egress_ip,
                canary_symbol=args.canary_symbol,
                max_history_symbols=int(args.max_history_symbols or 0),
            ),
        )
        market_collector = json_from_command(market_result)
        write_json(root / "remote_stdout_market_collector.json", market_collector)
        if market_result.returncode != 0:
            blockers.append("remote_stdout_market_and_fingerprint_collector_failed")
        if not p9ce_collector_ready(market_collector):
            blockers.append("remote_stdout_market_and_fingerprint_collector_not_ready")

    if pre_snapshot:
        post_result = run_record(
            "post_control_snapshot",
            remote_snapshot_script(args.remote_repo, args.remote_config),
        )
        post_snapshot = json_from_command(post_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if post_result.returncode != 0:
            blockers.append("post_control_snapshot_failed")
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    account_delta = account_delta_acceptance(account_proof) if account_proof else {}
    history_delta = (
        history_delta_acceptance(account_collector) if account_collector else {}
    )
    market_delta = (
        p9ce_fingerprint_delta_acceptance(market_collector) if market_collector else {}
    )
    account_identity = dict(account_collector.get("remote_runner_identity_readback") or {})
    market_identity = dict(market_collector.get("remote_runner_identity_readback") or {})
    remote_control_unchanged = bool(pre_snapshot and post_snapshot) and snapshot_boundary_ok(
        pre_snapshot, post_snapshot
    )

    if account_collector and not p9ci_remote_identity_ready(
        account_identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("account_collector_remote_runner_identity_not_ready")
    if market_collector and not p9ce_remote_identity_ready(
        market_identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("market_collector_remote_runner_identity_not_ready")
    if account_proof and account_proof.get("pit_safe_read_only_account_proof_ready") is not True:
        blockers.append("pit_safe_v2v3_account_proof_not_ready")
    if account_proof and account_proof.get("can_trade_source") != CAN_TRADE_SOURCE:
        blockers.append("can_trade_source_not_fapi_v2_account")
    if account_proof and account_proof.get("account_v3_canTrade_ignored_for_permission_decision") is not True:
        blockers.append("account_v3_canTrade_not_ignored")
    if account_proof and (
        account_proof.get("can_trade_pre") is not True
        or account_proof.get("can_trade_post") is not True
    ):
        blockers.append("can_trade_v2_false_or_missing_after_canary")
    if account_delta and account_delta.get("open_order_count_zero_pre_post") is not True:
        blockers.append("open_order_count_not_zero_pre_post")
    if history_delta and history_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("account_history_order_cancel_fill_trade_delta_not_zero")
    if market_delta and market_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("market_order_cancel_fill_trade_delta_not_zero")
    if market_delta and market_delta.get("position_delta_zero_or_stable") is not True:
        blockers.append("market_position_delta_not_zero_or_unstable")
    if market_delta and market_delta.get("balance_delta_zero_or_stable") is not True:
        blockers.append("market_balance_delta_not_zero_or_unstable")

    fresh_book = dict(market_collector.get("fresh_order_book") or {})
    filters = dict(market_collector.get("exchange_filter_readback") or {})
    operator_control = dict(market_collector.get("operator_control_readback") or {})
    non_auth = {
        "contract_version": "hv_balanced_timer_path_post_canary_health_position_readback_non_authorization.v1",
        "authorizations": {
            "post_canary_read_only_health_position_readback": str(args.owner_decision)
            == APPROVE_DECISION,
            "remote_stdout_read_only_account_market_collection": str(args.owner_decision)
            == APPROVE_DECISION,
            "order_test_endpoint": False,
            "remote_files_written": False,
            "remote_sync": False,
            "supervisor_invocation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_timer_path_post_canary_health_position_readback_control_boundary.v1",
        "scope": "post_canary_read_only_health_position_readback_stdout_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(account_collector or market_collector),
        "remote_execution_scope": "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "order_test_endpoint_called": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("remote_live_config_sha256")
        != post_snapshot.get("remote_live_config_sha256"),
        "operator_state_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("operator_state") != post_snapshot.get("operator_state"),
        "timer_state_changed": bool(pre_snapshot and post_snapshot)
        and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    proof_files = {
        "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
        "remote_stdout_account_collector_sanitized": proof_root / "remote_stdout_account_collector_sanitized.json",
        "pit_safe_v2v3_account_proof": proof_root / "pit_safe_v2v3_account_proof.json",
        "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
        "account_history_delta_acceptance": proof_root / "account_history_delta_acceptance.json",
        "remote_stdout_market_collector": proof_root / "remote_stdout_market_collector.json",
        "market_proof_collection_delta_acceptance": proof_root / "market_proof_collection_delta_acceptance.json",
        "fresh_order_book": proof_root / "fresh_order_book.json",
        "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
        "operator_control_readback": proof_root / "operator_control_readback.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
    }
    combined_identity = {
        "contract_version": "hv_balanced_timer_path_post_canary_health_position_readback_remote_identity_readback.v1",
        "account_collector_identity": account_identity,
        "market_collector_identity": market_identity,
        "account_collector_identity_ready": bool(account_collector)
        and p9ci_remote_identity_ready(
            account_identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
        "market_collector_identity_ready": bool(market_collector)
        and p9ce_remote_identity_ready(
            market_identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
    }
    write_json(proof_files["remote_runner_identity_readback"], combined_identity)
    write_json(proof_files["remote_stdout_account_collector_sanitized"], account_sanitized)
    write_json(proof_files["pit_safe_v2v3_account_proof"], account_proof)
    write_json(proof_files["account_delta_acceptance"], account_delta)
    write_json(proof_files["account_history_delta_acceptance"], history_delta)
    write_json(proof_files["remote_stdout_market_collector"], market_collector)
    write_json(proof_files["market_proof_collection_delta_acceptance"], market_delta)
    write_json(proof_files["fresh_order_book"], fresh_book)
    write_json(proof_files["exchange_filter_readback"], filters)
    write_json(proof_files["operator_control_readback"], operator_control)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    manifest = write_proof_manifest(proof_root, proof_files)
    write_json(root / "command_records.json", {"commands": command_records})

    gates = {
        **pre_checks,
        "pre_control_snapshot_ready": bool(pre_snapshot)
        and pre_snapshot.get("status") != "parse_failed",
        "remote_stdout_pit_safe_v2v3_account_collector_ready": p9ci_collector_ready(
            account_collector
        ),
        "remote_stdout_market_and_fingerprint_collector_ready": p9ce_collector_ready(
            market_collector
        ),
        "account_collector_remote_identity_ready": combined_identity[
            "account_collector_identity_ready"
        ],
        "market_collector_remote_identity_ready": combined_identity[
            "market_collector_identity_ready"
        ],
        "pit_safe_v2v3_account_proof_ready": account_proof.get(
            "pit_safe_read_only_account_proof_ready"
        )
        is True,
        "can_trade_source_is_fapi_v2_account": account_proof.get("can_trade_source")
        == CAN_TRADE_SOURCE,
        "account_v3_canTrade_ignored": account_proof.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "can_trade_v2_true_pre_post": account_proof.get("can_trade_pre") is True
        and account_proof.get("can_trade_post") is True,
        "position_fingerprint_stable": account_delta.get("position_fingerprint_stable")
        is True
        and market_delta.get("position_delta_zero_or_stable") is True,
        "open_order_fingerprint_stable": account_delta.get(
            "open_order_fingerprint_stable"
        )
        is True
        and market_delta.get("open_order_fingerprint_stable") is True,
        "balance_fingerprint_stable": account_delta.get("balance_fingerprint_stable")
        is True
        and market_delta.get("balance_delta_zero_or_stable") is True,
        "open_order_count_zero_pre_post": account_delta.get(
            "open_order_count_zero_pre_post"
        )
        is True,
        "order_cancel_fill_trade_delta_zero": history_delta.get(
            "order_cancel_fill_trade_delta_zero"
        )
        is True
        and market_delta.get("order_cancel_fill_trade_delta_zero") is True,
        "fresh_order_book_ready": fresh_book.get("status") == "ready",
        "exchange_filter_readback_ready": filters.get("status") == "ready",
        "remote_control_boundary_unchanged": remote_control_unchanged,
        "proof_artifact_manifest_ready": bool(manifest.get("self", {}).get("sha256")),
        "remote_files_written_zero": control.get("remote_files_written") == 0,
        "remote_sync_not_performed": control.get("remote_sync_performed") is False,
        "order_test_endpoint_not_called": control.get("order_test_endpoint_called")
        is False,
        "supervisor_not_invoked": control.get("ran_supervisor") is False,
        "timer_path_not_loaded": control.get("entered_timer_path") is False,
        "candidate_not_executed": control.get("candidate_execution_performed") is False,
        "executor_input_not_mutated": control.get("executor_input_changed") is False,
        "target_plan_not_replaced": control.get("target_plan_replaced") is False,
        "zero_orders_fills_trades": control.get("orders_submitted") == 0
        and control.get("orders_canceled") == 0
        and control.get("fill_count") == 0
        and control.get("trade_count") == 0,
    }
    blockers.extend(key for key, value in gates.items() if not value and key not in blockers)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "post_canary_read_only_health_position_readback_ready": status == "ready",
        "ssh_invoked": control["ssh_invoked"],
        "remote_network_connection_performed": control["remote_network_connection_performed"],
        "remote_execution_scope": control["remote_execution_scope"],
        "remote_files_written": control["remote_files_written"],
        "remote_sync_performed": control["remote_sync_performed"],
        "fresh_remote_account_read_performed": control["fresh_remote_account_read_performed"],
        "fresh_order_book_read_performed": control["fresh_order_book_read_performed"],
        "exchange_filter_read_performed": control["exchange_filter_read_performed"],
        "order_test_endpoint_called": control["order_test_endpoint_called"],
        "entered_timer_path": control["entered_timer_path"],
        "ran_supervisor": control["ran_supervisor"],
        "candidate_execution_performed": control["candidate_execution_performed"],
        "live_order_submission_performed": control["live_order_submission_performed"],
        "target_plan_replaced": control["target_plan_replaced"],
        "executor_input_changed": control["executor_input_changed"],
        "live_config_changed": control["live_config_changed"],
        "operator_state_changed": control["operator_state_changed"],
        "timer_state_changed": control["timer_state_changed"],
        "remote_control_boundary_unchanged": remote_control_unchanged,
        "can_trade_decision_source": account_proof.get("can_trade_source") or CAN_TRADE_SOURCE,
        "can_trade_pre": account_proof.get("can_trade_pre"),
        "can_trade_post": account_proof.get("can_trade_post"),
        "account_v3_canTrade_ignored_for_permission_decision": account_proof.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        ),
        "open_position_count_pre": dict(
            dict(account_collector.get("pre_account_snapshot") or {}).get("v3_summary")
            or {}
        ).get("open_position_count"),
        "open_position_count_post": dict(
            dict(account_collector.get("post_account_snapshot") or {}).get("v3_summary")
            or {}
        ).get("open_position_count"),
        "open_order_count_pre": dict(
            dict(account_collector.get("pre_account_snapshot") or {}).get("v3_summary")
            or {}
        ).get("open_order_count"),
        "open_order_count_post": dict(
            dict(account_collector.get("post_account_snapshot") or {}).get("v3_summary")
            or {}
        ).get("open_order_count"),
        "position_fingerprint_stable": gates["position_fingerprint_stable"],
        "open_order_fingerprint_stable": gates["open_order_fingerprint_stable"],
        "balance_fingerprint_stable": gates["balance_fingerprint_stable"],
        "fill_trade_fingerprint_stable": history_delta.get(
            "fill_trade_fingerprint_stable"
        ),
        "order_cancel_fill_trade_delta_zero": gates["order_cancel_fill_trade_delta_zero"],
        "open_order_count_zero_pre_post": gates["open_order_count_zero_pre_post"],
        "fresh_order_book_status": fresh_book.get("status"),
        "exchange_filter_readback_status": filters.get("status"),
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "canary_symbol": args.canary_symbol,
        "allowed_next_gate": NEXT_GATE,
        "allowed_next_gate_scope": NEXT_GATE_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {},
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "pre_control_snapshot": str(root / "pre_control_snapshot.json"),
            "post_control_snapshot": str(root / "post_control_snapshot.json"),
            "remote_stdout_account_collector_sanitized": str(
                root / "remote_stdout_account_collector_sanitized.json"
            ),
            "remote_stdout_market_collector": str(
                root / "remote_stdout_market_collector.json"
            ),
            "proof_artifact_manifest": str(
                proof_root / "proof_artifact_manifest.json"
            ),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_post_canary_readback(parse_args(argv))
    print(
        "post_canary_read_only_health_position_readback_ready="
        + str(bool(summary["post_canary_read_only_health_position_readback_ready"])).lower()
    )
    print("status=" + str(summary["status"]))
    if summary.get("blockers"):
        for blocker in summary["blockers"]:
            print("blocker=" + blocker)
    print("summary=" + str(summary["output_files"]["summary"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
