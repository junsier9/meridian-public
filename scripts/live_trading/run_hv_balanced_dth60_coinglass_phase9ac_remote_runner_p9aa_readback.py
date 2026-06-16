from __future__ import annotations

import argparse
import json
import posixpath
import shlex
import subprocess
import sys
from dataclasses import dataclass
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9AB_CONTRACT,
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_REPO,
    P9AC_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback.v1"
APPROVE_P9AC_DECISION = "approve_p9ac_execute_remote_runner_no_order_p9aa_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ac_remote_runner_p9aa_readback"
PHASE9AB_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ab_remote_p9aa_owner_gate"
DEFAULT_REMOTE_LIVE_ENV = "/root/meridian_alpha_live_runner/bin/with-live-env"
DEFAULT_REMOTE_PROOF_PARENT = "/root/meridian_alpha_live_runner/proof_artifacts/p9ac"
REMOTE_SYNC_FILES = (
    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py",
    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate.py",
    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9y_owner_review_after_p9x.py",
    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate.py",
    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor.py",
    "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py",
)


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResult]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9AC on the remote runner: fresh read-only account proof, "
            "narrow proof/harness sync, remote no-order P9AA three-cycle readback, "
            "and local retained summary. Candidate execution and production timer "
            "service mutation remain forbidden."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9ab-summary", default="")
    parser.add_argument("--phase9z-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-proof-parent", default=DEFAULT_REMOTE_PROOF_PARENT)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--shadow-cycles", type=int, default=3)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AC_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:execute_p9ac_remote_runner_p9aa")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_command_runner(args: Sequence[str]) -> CommandResult:
    proc = subprocess.run(list(args), text=True, capture_output=True)
    return CommandResult(args=list(args), returncode=int(proc.returncode), stdout=proc.stdout, stderr=proc.stderr)


def ssh_args(host: str, timeout: int, command: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={int(timeout)}",
        host,
        f"bash -lc {shlex.quote(command)}",
    ]


def scp_args(host: str, timeout: int, source: str | Path, dest: str) -> list[str]:
    return [
        "scp",
        "-q",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={int(timeout)}",
        str(source),
        f"{host}:{dest}",
    ]


def scp_from_args(host: str, timeout: int, source: str, dest: str | Path) -> list[str]:
    return [
        "scp",
        "-q",
        "-r",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={int(timeout)}",
        f"{host}:{source}",
        str(dest),
    ]


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AC_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ac_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_remote_runner_no_order_p9aa_readback_only",
        "decision_effect": "execute_p9ac_remote_runner_no_order_p9aa_readback" if approved else "none",
        "p9ac_remote_runner_readback_approved": approved,
        "remote_sync_approved": approved,
        "remote_execution_approved": approved,
        "fresh_remote_account_read_proof_required": True,
        "generated_no_order_config_required": True,
        "consecutive_cycles_required": 3,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def p9ab_ready(summary: dict[str, Any]) -> bool:
    owner = dict(summary.get("owner_decision") or {})
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == P9AB_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ab_remote_p9aa_owner_gate_ready") is True
        and summary.get("eligible_for_p9ac_remote_runner_no_order_p9aa") is True
        and summary.get("allowed_next_gate") == P9AC_GATE
        and summary.get("future_p9ac_remote_sync_authorized") is True
        and summary.get("future_p9ac_remote_execution_authorized") is True
        and summary.get("future_p9ac_fresh_remote_account_read_proof_required") is True
        and summary.get("future_p9ac_consecutive_cycles_required") == 3
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and owner.get("decision") == "approve_p9ab_remote_runner_no_order_p9aa_owner_gate_only"
        and all(
            gates.get(key) is True
            for key in (
                "p9aa_blocked_fail_closed_due_local_account_read",
                "future_fresh_remote_account_read_proof_required",
                "future_p9ac_must_keep_executor_baseline_only",
                "future_p9ac_must_keep_candidate_shadow_only",
                "future_p9ac_must_keep_orders_and_fills_zero",
                "future_p9ac_must_not_load_production_timer_service",
            )
        )
    )


def preflight_ready(summary: dict[str, Any]) -> bool:
    side_effects = dict(summary.get("side_effects") or {})
    return (
        summary.get("status") == "passed_read_only_account_probe"
        and not summary.get("blockers")
        and summary.get("account_readable") is True
        and summary.get("can_trade") is True
        and summary.get("position_mode") == "one_way"
        and int(summary.get("open_order_count") or 0) == 0
        and int(summary.get("open_position_count") or 0) == 0
        and side_effects.get("orders_submitted") == 0
        and side_effects.get("orders_canceled") == 0
        and side_effects.get("only_http_get_endpoints") is True
    )


def p9aa_ready(summary: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("timer_path_shadow_cycles_ready") is True
        and int(summary.get("completed_shadow_cycles") or 0) >= 3
        and summary.get("fresh_proof_each_cycle") is True
        and summary.get("same_risk_no_order_config_each_cycle") is True
        and summary.get("timer_path_supervisor_entrypoint_invoked") is True
        and summary.get("systemd_timer_service_invoked") is False
        and summary.get("production_timer_service_loaded_or_modified") is False
        and summary.get("candidate_execution_enabled") is False
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_mutated") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed_outside_generated_p9aa_state") is False
        and summary.get("timer_state_changed") is False
        and all(
            gates.get(key) is True
            for key in (
                "all_cycles_ready",
                "all_executor_baseline_only",
                "all_candidate_artifacts_shadow_only",
                "all_candidate_plan_not_referenced_by_executor",
                "no_candidate_execution",
                "no_live_order_submission",
                "no_target_plan_replacement",
                "no_executor_input_mutation",
                "no_production_timer_service_mutation",
            )
        )
    )


def snapshot_boundary_ok(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    return (
        pre.get("remote_live_config_sha256") == post.get("remote_live_config_sha256")
        and pre.get("live_supervisor_sha256") == post.get("live_supervisor_sha256")
        and pre.get("operator_state") == post.get("operator_state")
        and timer_state_digest(pre) == timer_state_digest(post)
    )


def timer_state_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    units = dict(snapshot.get("systemd_units") or {})
    digest: dict[str, Any] = {}
    for unit, data in units.items():
        item = dict(data or {})
        digest[unit] = {
            key: item.get(key)
            for key in (
                "LoadState",
                "UnitFileState",
                "ActiveState",
                "SubState",
                "FragmentPath",
            )
        }
    return digest


def json_from_command(result: CommandResult) -> dict[str, Any]:
    try:
        return dict(json.loads(result.stdout))
    except Exception:
        return {
            "status": "parse_failed",
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }


def remote_snapshot_script(remote_repo: str, remote_config: str) -> str:
    return f"""
cd {shlex.quote(remote_repo)}
python3 - <<'PY'
import hashlib, json, pathlib, sqlite3, subprocess
repo = pathlib.Path({remote_repo!r})
config = pathlib.Path({remote_config!r})
sqlite_path = repo / 'artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/state/live_trading.sqlite3'
units = [
  'meridian-alpha-mainnet-supervisor-live.timer',
  'meridian-alpha-mainnet-supervisor-live.service',
  'meridian-alpha-mainnet-health-monitor.timer',
  'meridian-alpha-mainnet-health-monitor.service',
]
def sha(path):
    p = pathlib.Path(path)
    if not p.exists() or not p.is_file():
        return ''
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()
def systemd(unit):
    keys = ['LoadState','UnitFileState','ActiveState','SubState','FragmentPath']
    out = {{}}
    try:
        proc = subprocess.run(['systemctl','show',unit,'--no-pager'] + [f'-p{{key}}' for key in keys], text=True, capture_output=True, timeout=15)
        out['returncode'] = proc.returncode
        for line in proc.stdout.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                out[k] = v
        if proc.stderr.strip():
            out['stderr'] = proc.stderr.strip()[-500:]
    except Exception as exc:
        out = {{'error_type': type(exc).__name__, 'error': str(exc)}}
    return out
operator_state = {{}}
if sqlite_path.exists():
    try:
        with sqlite3.connect(str(sqlite_path)) as conn:
            rows = conn.execute('SELECT key, value, updated_at_utc FROM operator_state ORDER BY key').fetchall()
        operator_state = {{str(k): {{'value': str(v), 'updated_at_utc': str(t)}} for k, v, t in rows}}
    except Exception as exc:
        operator_state = {{'_error_type': type(exc).__name__, '_error': str(exc)}}
print(json.dumps({{
  'remote_repo': str(repo),
  'remote_config': str(config),
  'remote_live_config_sha256': sha(config),
  'live_supervisor_sha256': sha(repo / 'src/enhengclaw/live_trading/mainnet_live_supervisor.py'),
  'hook_sha256': sha(repo / 'src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py'),
  'sqlite_path': str(sqlite_path),
  'operator_state': operator_state,
  'systemd_units': {{unit: systemd(unit) for unit in units}},
}}, indent=2, sort_keys=True))
PY
"""


def remote_preflight_command(remote_repo: str, remote_live_env: str, expected_egress_ip: str, output_path: str) -> str:
    return f"""
cd {shlex.quote(remote_repo)}
mkdir -p {shlex.quote(posixpath.dirname(output_path))}
set +e
{shlex.quote(remote_live_env)} python3 scripts/live_trading/run_binance_usdm_remote_readonly_preflight_standalone.py --expected-egress-ip {shlex.quote(expected_egress_ip)} > {shlex.quote(output_path)}
rc=$?
cat {shlex.quote(output_path)}
exit $rc
"""


def remote_p9aa_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_p9z_summary: str,
    remote_config: str,
    remote_p9aa_output: str,
    shadow_cycles: int,
) -> str:
    stdout_log = f"{remote_p9aa_output.rstrip('/')}/p9aa_cli_stdout.log"
    stderr_log = f"{remote_p9aa_output.rstrip('/')}/p9aa_cli_stderr.log"
    return f"""
cd {shlex.quote(remote_repo)}
mkdir -p {shlex.quote(remote_p9aa_output)}
set +e
{shlex.quote(remote_live_env)} python3 scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py \\
  --phase9z-summary {shlex.quote(remote_p9z_summary)} \\
  --base-config {shlex.quote(remote_config)} \\
  --output-root {shlex.quote(remote_p9aa_output)} \\
  --shadow-cycles {int(shadow_cycles)} > {shlex.quote(stdout_log)} 2> {shlex.quote(stderr_log)}
rc=$?
cat {shlex.quote(remote_p9aa_output)}/summary.json 2>/dev/null || true
exit $rc
"""


def remote_prepare_sync_command(remote_repo: str, remote_backup_dir: str, rel_path: str) -> str:
    target = f"{remote_repo.rstrip('/')}/{rel_path}"
    backup = f"{remote_backup_dir.rstrip('/')}/{rel_path}"
    return f"""
mkdir -p {shlex.quote(posixpath.dirname(target))}
mkdir -p {shlex.quote(posixpath.dirname(backup))}
if [ -f {shlex.quote(target)} ]; then cp -a {shlex.quote(target)} {shlex.quote(backup)}; fi
"""


def remote_sha_command(remote_repo: str, rel_path: str) -> str:
    target = f"{remote_repo.rstrip('/')}/{rel_path}"
    return f"if [ -f {shlex.quote(target)} ]; then sha256sum {shlex.quote(target)} | awk '{{print $1}}'; fi"


def build_phase9ac(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    root.mkdir(parents=True, exist_ok=True)
    readback_root = root / "remote_readback"
    readback_root.mkdir(parents=True, exist_ok=True)
    phase9ab_path = (
        resolve_path(args.phase9ab_summary)
        if str(args.phase9ab_summary).strip()
        else latest_match(PHASE9AB_PARENT, "*/summary.json")
    )
    p9ab = load_optional(phase9ab_path)
    phase9z_path = resolve_path(args.phase9z_summary) if str(args.phase9z_summary).strip() else latest_match(
        "artifacts/live_trading/hv_balanced_dth60_p9z_timer_path_readback_owner_gate",
        "*/summary.json",
    )
    decision = owner_decision_record(args, generated_at)
    write_json(root / "owner_decision_record.json", decision)

    pre_gates = {
        "owner_decision_p9ac_execute_only": args.owner_decision == APPROVE_P9AC_DECISION,
        "p9ab_owner_gate_ready": p9ab_ready(p9ab),
        "phase9z_summary_exists": phase9z_path.exists(),
        "requested_shadow_cycles_at_least_three": int(args.shadow_cycles or 0) >= 3,
    }
    blockers = [key for key, value in pre_gates.items() if not value]
    command_records: list[dict[str, Any]] = []
    remote_root = f"{str(args.remote_proof_parent).rstrip('/')}/{run_id}"
    remote_inputs = f"{remote_root}/inputs"
    remote_backup = f"{remote_root}/backups"
    remote_p9z = f"{remote_inputs}/phase9z_summary.json"
    remote_preflight_pre = f"{remote_root}/fresh_remote_account_read_pre.json"
    remote_preflight_post = f"{remote_root}/fresh_remote_account_read_post.json"
    remote_p9aa_output = f"{remote_root}/p9aa"

    def run_record(label: str, cmd: Sequence[str]) -> CommandResult:
        result = command_runner(cmd)
        command_records.append(
            {
                "label": label,
                "args": list(cmd),
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        )
        return result

    pre_snapshot: dict[str, Any] = {}
    preflight_pre: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    preflight_post: dict[str, Any] = {}
    p9aa_summary: dict[str, Any] = {}
    sync_records: list[dict[str, Any]] = []

    if not blockers:
        run_record(
            "remote_mkdir",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                f"mkdir -p {shlex.quote(remote_inputs)} {shlex.quote(remote_backup)} {shlex.quote(remote_p9aa_output)}",
            ),
        )
        pre_snapshot_result = run_record(
            "pre_control_snapshot",
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        pre_snapshot = json_from_command(pre_snapshot_result)
        write_json(root / "pre_control_snapshot.json", pre_snapshot)

    if not blockers:
        preflight_pre_result = run_record(
            "fresh_remote_account_read_pre",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_preflight_command(args.remote_repo, args.remote_live_env, args.expected_egress_ip, remote_preflight_pre),
            ),
        )
        preflight_pre = json_from_command(preflight_pre_result)
        write_json(root / "fresh_remote_account_read_pre.json", preflight_pre)
        if not preflight_ready(preflight_pre):
            blockers.append("fresh_remote_account_read_pre_failed")

    if not blockers:
        p9z_copy = run_record("copy_phase9z_summary", scp_args(args.remote_host, args.ssh_connect_timeout, phase9z_path, remote_p9z))
        if p9z_copy.returncode != 0:
            blockers.append("phase9z_remote_copy_failed")
        for rel in REMOTE_SYNC_FILES:
            local_path = resolve_path(rel)
            if not local_path.exists():
                sync_records.append({"path": rel, "status": "missing_local"})
                blockers.append(f"sync_file_missing_local:{rel}")
                continue
            prep = run_record(
                f"sync_prepare:{rel}",
                ssh_args(args.remote_host, args.ssh_connect_timeout, remote_prepare_sync_command(args.remote_repo, remote_backup, rel)),
            )
            if prep.returncode != 0:
                sync_records.append({"path": rel, "status": "prepare_failed", "returncode": prep.returncode})
                blockers.append(f"sync_prepare_failed:{rel}")
                continue
            dest = f"{str(args.remote_repo).rstrip('/')}/{rel}"
            copy = run_record(f"sync_copy:{rel}", scp_args(args.remote_host, args.ssh_connect_timeout, local_path, dest))
            remote_sha = run_record(
                f"sync_sha:{rel}",
                ssh_args(args.remote_host, args.ssh_connect_timeout, remote_sha_command(args.remote_repo, rel)),
            )
            local_sha = file_sha256(local_path)
            remote_sha_text = remote_sha.stdout.strip().splitlines()[-1] if remote_sha.stdout.strip() else ""
            record = {
                "path": rel,
                "status": "synced" if copy.returncode == 0 and remote_sha_text == local_sha else "blocked",
                "local_sha256": local_sha,
                "remote_sha256": remote_sha_text,
                "copy_returncode": copy.returncode,
            }
            sync_records.append(record)
            if record["status"] != "synced":
                blockers.append(f"sync_sha_mismatch_or_copy_failed:{rel}")
        write_json(root / "remote_sync_manifest.json", {"remote_root": remote_root, "files": sync_records})

    if not blockers:
        compile_result = run_record(
            "remote_py_compile_p9aa",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                (
                    f"cd {shlex.quote(args.remote_repo)} && "
                    "python3 -m py_compile "
                    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py "
                    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate.py "
                    "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
                ),
            ),
        )
        if compile_result.returncode != 0:
            blockers.append("remote_py_compile_failed")

    if not blockers:
        p9aa_result = run_record(
            "remote_p9aa_no_order_readback",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9aa_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_p9z_summary=remote_p9z,
                    remote_config=args.remote_config,
                    remote_p9aa_output=remote_p9aa_output,
                    shadow_cycles=int(args.shadow_cycles or 0),
                ),
            ),
        )
        p9aa_summary = json_from_command(p9aa_result)
        write_json(root / "remote_p9aa_summary_inline.json", p9aa_summary)
        if not p9aa_ready(p9aa_summary):
            blockers.append("remote_p9aa_no_order_readback_failed")

    if not blockers:
        preflight_post_result = run_record(
            "fresh_remote_account_read_post",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_preflight_command(args.remote_repo, args.remote_live_env, args.expected_egress_ip, remote_preflight_post),
            ),
        )
        preflight_post = json_from_command(preflight_post_result)
        write_json(root / "fresh_remote_account_read_post.json", preflight_post)
        if not preflight_ready(preflight_post):
            blockers.append("fresh_remote_account_read_post_failed")

    if not blockers:
        post_snapshot_result = run_record(
            "post_control_snapshot",
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        post_snapshot = json_from_command(post_snapshot_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    # Best-effort retained readback. Failure to copy does not override a ready remote proof,
    # but it is recorded as a retention blocker before ready status is granted.
    if not blockers:
        fetch_result = run_record(
            "fetch_remote_readback",
            scp_from_args(args.remote_host, args.ssh_connect_timeout, remote_root, readback_root),
        )
        if fetch_result.returncode != 0:
            blockers.append("remote_readback_fetch_failed")

    if pre_snapshot and not post_snapshot:
        post_snapshot_result = run_record(
            "post_control_snapshot_after_block",
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        post_snapshot = json_from_command(post_snapshot_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    write_json(root / "command_records.json", {"commands": command_records})
    status = "ready" if not blockers else "blocked"
    command_returncodes = {str(item.get("label")): int(item.get("returncode") or 0) for item in command_records}
    gates = {
        **pre_gates,
        "remote_sync_performed": bool(sync_records) and all(item.get("status") == "synced" for item in sync_records),
        "remote_py_compile_passed": command_returncodes.get("remote_py_compile_p9aa") == 0
        if "remote_py_compile_p9aa" in command_returncodes
        else False,
        "fresh_remote_account_read_pre_ready": preflight_ready(preflight_pre),
        "remote_p9aa_no_order_readback_ready": p9aa_ready(p9aa_summary),
        "fresh_remote_account_read_post_ready": preflight_ready(preflight_post),
        "remote_control_boundary_unchanged": bool(pre_snapshot and post_snapshot) and snapshot_boundary_ok(pre_snapshot, post_snapshot),
        "shadow_cycles_at_least_three": int(p9aa_summary.get("completed_shadow_cycles") or 0) >= 3,
        "baseline_only_executor_input": p9aa_ready(p9aa_summary),
        "candidate_shadow_only": p9aa_ready(p9aa_summary),
        "zero_orders_fills": int(p9aa_summary.get("orders_submitted") or 0) == 0 and int(p9aa_summary.get("fill_count") or 0) == 0,
        "production_timer_service_not_loaded_or_modified": (
            p9aa_summary.get("production_timer_service_loaded_or_modified") is False if p9aa_summary else True
        ),
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": sorted(set(blockers)),
        "owner_decision": decision,
        "p9ac_remote_runner_no_order_p9aa_ready": status == "ready",
        "remote_host": args.remote_host,
        "remote_repo": args.remote_repo,
        "remote_config": args.remote_config,
        "remote_proof_root": remote_root,
        "remote_sync_performed": bool(sync_records),
        "remote_execution_performed": bool(p9aa_summary),
        "fresh_remote_account_read_pre": evidence_file(root / "fresh_remote_account_read_pre.json"),
        "fresh_remote_account_read_post": evidence_file(root / "fresh_remote_account_read_post.json"),
        "remote_p9aa_summary": evidence_file(root / "remote_p9aa_summary_inline.json"),
        "pre_control_snapshot": evidence_file(root / "pre_control_snapshot.json"),
        "post_control_snapshot": evidence_file(root / "post_control_snapshot.json"),
        "remote_sync_manifest": evidence_file(root / "remote_sync_manifest.json"),
        "source_evidence": {
            "phase9ab_summary": evidence_file(phase9ab_path),
            "phase9z_summary": evidence_file(phase9z_path),
        },
        "remote_runner": {
            "expected_egress_ip": args.expected_egress_ip,
            "pre_egress_ip": preflight_pre.get("egress_ip"),
            "post_egress_ip": preflight_post.get("egress_ip"),
        },
        "completed_shadow_cycles": int(p9aa_summary.get("completed_shadow_cycles") or 0),
        "fresh_proof_each_cycle": p9aa_summary.get("fresh_proof_each_cycle") is True,
        "same_risk_no_order_config_each_cycle": p9aa_summary.get("same_risk_no_order_config_each_cycle") is True,
        "baseline_only_executor_input": gates["baseline_only_executor_input"],
        "candidate_shadow_only": gates["candidate_shadow_only"],
        "candidate_execution_authorized": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "orders_submitted": int(p9aa_summary.get("orders_submitted") or 0),
        "fill_count": int(p9aa_summary.get("fill_count") or 0),
        "production_timer_service_loaded_or_modified": p9aa_summary.get("production_timer_service_loaded_or_modified") if p9aa_summary else False,
        "live_config_changed": bool(pre_snapshot and post_snapshot) and pre_snapshot.get("remote_live_config_sha256") != post_snapshot.get("remote_live_config_sha256"),
        "operator_state_changed": bool(pre_snapshot and post_snapshot) and pre_snapshot.get("operator_state") != post_snapshot.get("operator_state"),
        "timer_state_changed": bool(pre_snapshot and post_snapshot) and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "remote_sync_manifest": str(root / "remote_sync_manifest.json"),
            "remote_readback": str(readback_root),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ac(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
