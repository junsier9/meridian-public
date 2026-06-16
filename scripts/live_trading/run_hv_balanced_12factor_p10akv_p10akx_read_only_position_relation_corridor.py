from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10aks_p10aku_revised_nonflat_terms_corridor import (  # noqa: E402
    P10AKU_CONTRACT,
    P10AKV_GATE,
    classify_position_relation,
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
    latest_match,
    local_command_runner,
    ssh_args,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10akv_p10akx_read_only_position_relation_corridor.v1"
P10AKV_CONTRACT = "hv_balanced_12factor_p10akv_read_only_fresh_position_relation_proof.v1"
P10AKW_CONTRACT = "hv_balanced_12factor_p10akw_review_fresh_position_relation_proof.v1"
P10AKX_CONTRACT = "hv_balanced_12factor_p10akx_define_post_relation_proof_scope.v1"
REMOTE_PROOF_CONTRACT = "hv_balanced_12factor_p10akv_remote_read_only_position_relation_proof.v1"

DEFAULT_P10AKU_PARENT = "artifacts/live_trading/proof_artifacts/p10aks_p10aku_revised_nonflat_canary_terms_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10akv_p10akx_read_only_position_relation_corridor"

P10AKW_GATE = "P10AKW_review_p10akv_fresh_position_relation_proof_only_if_separately_requested"
P10AKX_GATE = "P10AKX_define_post_position_relation_proof_scope_only_if_separately_requested"
P10AKY_RESOLUTION_GATE = "P10AKY_define_candidate_position_relation_resolution_scope_only_if_separately_requested"
P10AKY_READINESS_GATE = "P10AKY_prepare_nonflat_canary_readiness_package_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10AKV-P10AKX. P10AKV performs one fresh read-only remote "
            "position-relation proof against revised P10AKT terms. P10AKW "
            "reviews it. P10AKX only defines the next scope. No order/cancel, "
            "timer, supervisor, remote sync, or live mutation is allowed."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10aku-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10aku",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p10aku_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10AKU_PARENT, "*/p10aku_review/summary.json")


def source_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def p10aku_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10AKU_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10aku_review_revised_nonflat_terms_ready") is True
        and summary.get("terms_sufficient_for_future_read_only_position_relation_proof") is True
        and summary.get("allowed_next_gate") == P10AKV_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("remote_execution_performed") is False
        and int(summary.get("orders_submitted") or 0) == 0
    )


def terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("contract_version") == "hv_balanced_12factor_p10akt_revised_nonflat_canary_terms.v1"
        and terms.get("status") == "ready"
        and terms.get("pre_submit_position_relation_required") is True
        and terms.get("fresh_read_only_position_relation_proof_required_before_future_execution_gate") is True
        and terms.get("does_not_authorize_execution") is True
        and terms.get("market_orders_allowed") is False
        and terms.get("continuous_automation") is False
        and "opposite_direction_reduce_existing_long" in list(terms.get("blocked_position_relations") or [])
    )


def no_order_matrix(*, remote_api_called: bool = False) -> dict[str, Any]:
    return {
        "remote_api_called": remote_api_called,
        "remote_execution_performed": remote_api_called,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "timer_path_load_authorized": False,
        "timer_path_load_performed": False,
        "supervisor_invocation_authorized": False,
        "supervisor_invocation_performed": False,
        "live_config_mutation_performed": False,
        "operator_state_mutation_performed": False,
        "executor_input_mutation_performed": False,
        "target_plan_replacement_performed": False,
        "live_order_submission_authorized": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


def remote_position_relation_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_python: str,
    remote_config: str,
    expected_egress_ip: str,
    symbol: str,
    candidate_side: str,
    allowed_relations: Sequence[str],
    blocked_relations: Sequence[str],
) -> str:
    payload = {
        "symbol": symbol,
        "candidate_side": candidate_side,
        "remote_config": remote_config,
        "expected_egress_ip": expected_egress_ip,
        "allowed_relations": list(allowed_relations),
        "blocked_relations": list(blocked_relations),
    }
    return f"""
cd {shlex.quote(remote_repo)}
{shlex.quote(remote_live_env)} /usr/bin/env PYTHONNOUSERSITE=1 {shlex.quote(remote_python)} - <<'PY'
import hashlib, hmac, json, os, pathlib, sqlite3, subprocess, time, urllib.error, urllib.parse, urllib.request
from decimal import Decimal

CONFIG = {json.dumps(payload, sort_keys=True)!r}
CFG = json.loads(CONFIG)
FAPI = "https://fapi.binance.com"
REPO = pathlib.Path({remote_repo!r})
REMOTE_CONFIG = pathlib.Path(CFG["remote_config"])
SYMBOL = CFG["symbol"]
SIDE = CFG["candidate_side"]
started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sha(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()

def sha_file(path):
    p = pathlib.Path(path)
    if not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def dec(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")

def public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            return response.read().decode().strip()
    except Exception as exc:
        return "unavailable:" + type(exc).__name__

def sign(params, secret):
    params = dict(params)
    params.setdefault("recvWindow", "30000")
    params.setdefault("timestamp", str(int(time.time() * 1000)))
    query = urllib.parse.urlencode(params)
    params["signature"] = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return params

def request(path, params, signed, api_key, api_secret):
    params = {{k: str(v) for k, v in dict(params or {{}}).items() if v is not None}}
    if signed:
        params = sign(params, api_secret)
    query = urllib.parse.urlencode(params)
    url = FAPI + path + (("?" + query) if query else "")
    req = urllib.request.Request(url, headers={{"X-MBX-APIKEY": api_key, "User-Agent": "Meridian/P10AKV-read-only"}}, method="GET")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode()
            return {{"status": "ok", "status_code": int(response.status), "path": path, "method": "GET", "latency_ms": int((time.time()-t0)*1000), "payload": json.loads(raw) if raw else {{}}}}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        return {{"status": "failed", "status_code": int(exc.code), "path": path, "method": "GET", "latency_ms": int((time.time()-t0)*1000), "error": body}}
    except Exception as exc:
        return {{"status": "failed", "status_code": None, "path": path, "method": "GET", "latency_ms": int((time.time()-t0)*1000), "error_type": type(exc).__name__, "error": str(exc)[:1000]}}

def compact_order(row):
    return {{k: row.get(k) for k in ["symbol","orderId","clientOrderId","status","side","positionSide","type","origQty","executedQty","updateTime","time"] if k in row}}

def compact_trade(row):
    return {{k: row.get(k) for k in ["symbol","id","orderId","side","qty","quoteQty","commission","commissionAsset","time","maker"] if k in row}}

def position_rows(payload):
    rows = payload if isinstance(payload, list) else []
    out = []
    for row in rows:
        if isinstance(row, dict) and row.get("symbol") == SYMBOL:
            out.append({{k: row.get(k) for k in ["symbol","positionSide","positionAmt","entryPrice","breakEvenPrice","updateTime"] if k in row}})
    return out

def position_amt(rows):
    total = Decimal("0")
    for row in rows:
        if isinstance(row, dict) and row.get("symbol") == SYMBOL:
            total += dec(row.get("positionAmt"))
    return total

def relation(amt):
    if abs(amt) <= Decimal("0.000000000001"):
        rel = "flat_position_canary"
        executable = True
    elif amt > 0 and SIDE == "BUY":
        rel = "same_direction_long_add"
        executable = True
    elif amt < 0 and SIDE == "SELL":
        rel = "same_direction_short_add"
        executable = True
    elif amt > 0 and SIDE == "SELL":
        rel = "opposite_direction_reduce_existing_long"
        executable = False
    elif amt < 0 and SIDE == "BUY":
        rel = "opposite_direction_reduce_existing_short"
        executable = False
    else:
        rel = "unknown_or_unsupported_position_relation"
        executable = False
    return {{
        "relation": rel,
        "candidate_side": SIDE,
        "pre_position_amt": str(amt.normalize()),
        "executable_under_revised_terms": executable and rel in CFG["allowed_relations"],
        "relation_allowed_by_terms": rel in CFG["allowed_relations"],
        "relation_blocked_by_terms": rel in CFG["blocked_relations"],
        "non_reduce_only_restoration_required": rel in {{"opposite_direction_reduce_existing_long", "opposite_direction_reduce_existing_short"}},
        "non_reduce_only_restoration_authorized": False,
    }}

def systemd(unit):
    keys = ["LoadState","UnitFileState","ActiveState","SubState","FragmentPath"]
    out = {{}}
    try:
        proc = subprocess.run(["systemctl","show",unit,"--no-pager"] + [f"-p{{key}}" for key in keys], text=True, capture_output=True, timeout=10)
        out["returncode"] = proc.returncode
        for line in proc.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
        if proc.stderr.strip():
            out["stderr_tail"] = proc.stderr.strip()[-300:]
    except Exception as exc:
        out = {{"error_type": type(exc).__name__, "error": str(exc)[:300]}}
    return out

def operator_state():
    sqlite_path = REPO / "artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/state/live_trading.sqlite3"
    if not sqlite_path.exists():
        return {{"sqlite_path": str(sqlite_path), "rows": []}}
    try:
        with sqlite3.connect(str(sqlite_path)) as conn:
            rows = conn.execute("SELECT key, value, updated_at_utc FROM operator_state ORDER BY key").fetchall()
        return {{"sqlite_path": str(sqlite_path), "rows": [{{"key": str(k), "value": str(v), "updated_at_utc": str(t)}} for k, v, t in rows]}}
    except Exception as exc:
        return {{"sqlite_path": str(sqlite_path), "error_type": type(exc).__name__, "error": str(exc)[:300]}}

def control_snapshot():
    units = [
        "meridian-alpha-mainnet-supervisor-live.timer",
        "meridian-alpha-mainnet-supervisor-live.service",
        "meridian-alpha-mainnet-health-monitor.timer",
        "meridian-alpha-mainnet-health-monitor.service",
    ]
    return {{
        "remote_repo": str(REPO),
        "remote_config": str(REMOTE_CONFIG),
        "remote_live_config_sha256": sha_file(REMOTE_CONFIG),
        "live_supervisor_sha256": sha_file(REPO / "src/enhengclaw/live_trading/mainnet_live_supervisor.py"),
        "hook_sha256": sha_file(REPO / "src/enhengclaw/live_trading/default_off_scorer_shadow_wrapper.py"),
        "operator_state": operator_state(),
        "systemd_units": {{unit: systemd(unit) for unit in units}},
    }}

def read_state(label, api_key, api_secret):
    account_v2 = request("/fapi/v2/account", {{}}, True, api_key, api_secret)
    account_v3 = request("/fapi/v3/account", {{}}, True, api_key, api_secret)
    position_mode = request("/fapi/v1/positionSide/dual", {{}}, True, api_key, api_secret)
    position_risk = request("/fapi/v2/positionRisk", {{"symbol": SYMBOL}}, True, api_key, api_secret)
    open_orders = request("/fapi/v1/openOrders", {{"symbol": SYMBOL}}, True, api_key, api_secret)
    all_orders = request("/fapi/v1/allOrders", {{"symbol": SYMBOL, "limit": "20"}}, True, api_key, api_secret)
    user_trades = request("/fapi/v1/userTrades", {{"symbol": SYMBOL, "limit": "20"}}, True, api_key, api_secret)
    positions = position_rows(position_risk.get("payload"))
    open_rows = [compact_order(row) for row in list(open_orders.get("payload") or []) if isinstance(row, dict)]
    order_rows = [compact_order(row) for row in list(all_orders.get("payload") or []) if isinstance(row, dict)]
    trade_rows = [compact_trade(row) for row in list(user_trades.get("payload") or []) if isinstance(row, dict)]
    amt = position_amt(positions)
    endpoints = {{
        "account_v2": {{k: account_v2.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
        "account_v3": {{k: account_v3.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
        "position_mode": {{k: position_mode.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
        "position_risk": {{k: position_risk.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
        "open_orders": {{k: open_orders.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
        "all_orders": {{k: all_orders.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
        "user_trades": {{k: user_trades.get(k) for k in ["status","status_code","method","path","latency_ms","error","error_type"]}},
    }}
    return {{
        "label": label,
        "generated_at_utc": iso_now(),
        "endpoints": endpoints,
        "can_trade_v2": (account_v2.get("payload") or {{}}).get("canTrade") if isinstance(account_v2.get("payload"), dict) else None,
        "position_mode_one_way": (position_mode.get("payload") or {{}}).get("dualSidePosition") is False if isinstance(position_mode.get("payload"), dict) else False,
        "position_rows": positions,
        "position_amt": str(amt.normalize()),
        "open_order_count": len(open_rows),
        "open_order_rows": open_rows,
        "open_order_hash": sha(open_rows),
        "order_history_hash": sha(order_rows),
        "trade_history_hash": sha(trade_rows),
        "last_order_rows": order_rows[-3:],
        "last_trade_rows": trade_rows[-3:],
    }}

api_key = os.environ.get("Trade", "").strip()
api_secret = os.environ.get("Secret_Key", "").strip()
blockers = []
egress_ip = public_ip()
if not api_key:
    blockers.append("missing_api_key_env:Trade")
if not api_secret:
    blockers.append("missing_api_secret_env:Secret_Key")
if egress_ip != CFG["expected_egress_ip"]:
    blockers.append("egress_ip_mismatch")

control_pre = control_snapshot()
pre = post = {{}}
rel = {{"relation": "not_computed", "executable_under_revised_terms": False}}
if not blockers:
    pre = read_state("pre", api_key, api_secret)
    time.sleep(0.25)
    post = read_state("post", api_key, api_secret)
    amt = dec(pre.get("position_amt"))
    rel = relation(amt)
    for state_name, state in (("pre", pre), ("post", post)):
        for endpoint_name, endpoint in dict(state.get("endpoints") or {{}}).items():
            if endpoint.get("status") != "ok":
                blockers.append(f"{{state_name}}_{{endpoint_name}}_read_failed")
    if pre.get("position_amt") != post.get("position_amt"):
        blockers.append("position_amt_changed_during_read_only_probe")
    if pre.get("open_order_hash") != post.get("open_order_hash"):
        blockers.append("open_order_hash_changed_during_read_only_probe")
    if pre.get("order_history_hash") != post.get("order_history_hash"):
        blockers.append("order_history_hash_changed_during_read_only_probe")
    if pre.get("trade_history_hash") != post.get("trade_history_hash"):
        blockers.append("trade_history_hash_changed_during_read_only_probe")
control_post = control_snapshot()
control_stable = {{
    "remote_live_config_sha256_stable": control_pre.get("remote_live_config_sha256") == control_post.get("remote_live_config_sha256"),
    "live_supervisor_sha256_stable": control_pre.get("live_supervisor_sha256") == control_post.get("live_supervisor_sha256"),
    "hook_sha256_stable": control_pre.get("hook_sha256") == control_post.get("hook_sha256"),
    "operator_state_stable": control_pre.get("operator_state") == control_post.get("operator_state"),
    "systemd_units_stable": control_pre.get("systemd_units") == control_post.get("systemd_units"),
}}
if not all(control_stable.values()):
    blockers.append("remote_control_boundary_changed_during_read_only_probe")

status = "ready" if not blockers else "blocked"
summary = {{
    "contract_version": "{REMOTE_PROOF_CONTRACT}",
    "status": status,
    "blockers": sorted(set(blockers)),
    "started_at_utc": started_at,
    "finished_at_utc": iso_now(),
    "remote_runner_identity_readback": {{
        "repo_path": str(REPO),
        "config_path": str(REMOTE_CONFIG),
        "egress_ip": egress_ip,
        "expected_egress_ip": CFG["expected_egress_ip"],
    }},
    "candidate_side": SIDE,
    "symbol": SYMBOL,
    "fresh_position_relation": rel,
    "fresh_relation_executable_under_revised_terms": bool(rel.get("executable_under_revised_terms")),
    "fresh_open_order_count": int(pre.get("open_order_count") or 0),
    "fresh_open_order_count_zero": int(pre.get("open_order_count") or 0) == 0,
    "pre_readback": pre,
    "post_readback": post,
    "control_pre": control_pre,
    "control_post": control_post,
    "control_stability": control_stable,
    "side_effects": {{
        "http_methods_used": ["GET"],
        "only_http_get_endpoints": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "timer_path_invoked": False,
        "supervisor_invoked": False,
        "candidate_executed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_mutated": False,
        "operator_state_mutated": False,
    }},
}}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
"""


def remote_proof_ready(proof: dict[str, Any]) -> bool:
    side_effects = dict(proof.get("side_effects") or {})
    stability = dict(proof.get("control_stability") or {})
    return (
        proof.get("contract_version") == REMOTE_PROOF_CONTRACT
        and proof.get("status") == "ready"
        and not proof.get("blockers")
        and side_effects.get("only_http_get_endpoints") is True
        and int(side_effects.get("orders_submitted") or 0) == 0
        and int(side_effects.get("orders_canceled") or 0) == 0
        and int(side_effects.get("fill_count") or 0) == 0
        and int(side_effects.get("trade_count") or 0) == 0
        and all(stability.values())
    )


def build_p10akv(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10aku_path: Path,
    p10aku: dict[str, Any],
    terms_path: Path,
    terms: dict[str, Any],
    command_runner: CommandRunner,
) -> tuple[dict[str, Any], Path]:
    phase_dir = root / "p10akv_read_only_proof"
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10akv_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10akv_read_only_fresh_position_relation_proof_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "read_only_remote_account_position_proof_approved": True,
        "live_order_approved": False,
        "timer_or_supervisor_approved": False,
    }
    write_json(proof_dir / "owner_decision.json", owner_decision)
    pre_checks = {
        "p10aku_ready_for_p10akv": p10aku_ready(p10aku),
        "terms_ready": terms_ready(terms),
        "owner_decision_p10akv_recorded": True,
        "remote_host_matches_expected_runner": str(args.remote_host) == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo) == DEFAULT_REMOTE_REPO,
    }
    blockers = [key for key, ready in pre_checks.items() if not ready]
    remote_proof: dict[str, Any] = {}
    command_record: dict[str, Any] = {}
    if not blockers:
        cmd = ssh_args(
            args.remote_host,
            args.ssh_connect_timeout,
            remote_position_relation_command(
                remote_repo=args.remote_repo,
                remote_live_env=args.remote_live_env,
                remote_python=args.remote_python,
                remote_config=args.remote_config,
                expected_egress_ip=args.expected_egress_ip,
                symbol=str(terms.get("symbol") or "BTCUSDT"),
                candidate_side=str(dict(terms.get("current_retained_position_relation") or {}).get("candidate_side") or "SELL"),
                allowed_relations=list(terms.get("allowed_position_relations") or []),
                blocked_relations=list(terms.get("blocked_position_relations") or []),
            ),
        )
        result = command_runner(cmd)
        command_record = {
            "label": "remote_read_only_fresh_position_relation_proof",
            "args": list(cmd),
            "returncode": int(result.returncode),
            "stdout_bytes": len(result.stdout.encode("utf-8")),
            "stderr_tail": result.stderr[-4000:],
        }
        remote_proof = json_from_command(result)
        write_json(proof_dir / "remote_position_relation_proof.json", remote_proof)
        write_json(proof_dir / "command_record.json", command_record)
        if result.returncode != 0:
            blockers.append("remote_read_only_position_relation_command_failed")
        if not remote_proof_ready(remote_proof):
            blockers.append("remote_read_only_position_relation_proof_not_ready")
    else:
        write_json(proof_dir / "remote_position_relation_proof.json", remote_proof)
        write_json(proof_dir / "command_record.json", command_record)

    relation = dict(remote_proof.get("fresh_position_relation") or {})
    status = "ready" if not blockers else "blocked"
    fresh_relation_executable = bool(remote_proof.get("fresh_relation_executable_under_revised_terms"))
    future_execution_precheck_ready = (
        status == "ready"
        and fresh_relation_executable
        and remote_proof.get("fresh_open_order_count_zero") is True
    )
    summary = {
        "contract_version": P10AKV_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10akv_read_only_fresh_position_relation_proof_ready": status == "ready",
        "fresh_relation_executable_under_revised_terms": fresh_relation_executable,
        "future_execution_precheck_ready_under_revised_terms": future_execution_precheck_ready,
        "fresh_position_relation": relation,
        "fresh_open_order_count_zero": remote_proof.get("fresh_open_order_count_zero"),
        **no_order_matrix(remote_api_called=bool(remote_proof)),
        "pre_checks": pre_checks,
        "blockers": sorted(set(blockers)),
        "source_evidence": {
            "p10aku_summary": evidence_file(p10aku_path),
            "execution_terms": evidence_file(terms_path),
        },
        "allowed_next_gate": P10AKW_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_read_only_position_relation_proof_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(proof_dir / "owner_decision.json"),
            "remote_position_relation_proof": str(proof_dir / "remote_position_relation_proof.json"),
            "command_record": str(proof_dir / "command_record.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10akw(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10akv_path: Path,
    p10akv: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    proof_path = Path(str(dict(p10akv.get("output_files") or {}).get("remote_position_relation_proof") or ""))
    proof = load_optional(proof_path)
    relation = dict(p10akv.get("fresh_position_relation") or {})
    checks = {
        "owner_decision_p10akw_recorded": True,
        "p10akv_ready": p10akv.get("status") == "ready" and p10akv.get("allowed_next_gate") == P10AKW_GATE,
        "remote_proof_ready": remote_proof_ready(proof),
        "relation_classified": bool(relation.get("relation")),
        "no_orders_or_fills": int(p10akv.get("orders_submitted") or 0) == 0
        and int(p10akv.get("orders_canceled") or 0) == 0
        and int(p10akv.get("fill_count") or 0) == 0
        and int(p10akv.get("trade_count") or 0) == 0,
        "no_live_mutation": p10akv.get("live_config_mutation_performed") is False
        and p10akv.get("operator_state_mutation_performed") is False
        and p10akv.get("timer_path_load_performed") is False,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    relation_executable = bool(p10akv.get("fresh_relation_executable_under_revised_terms"))
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10akw_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10akw_review_p10akv_position_relation_proof_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only": True,
        "authorizes_next_scope_gate": status == "ready",
        "authorizes_live_order": False,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10akw_review.v1",
        "status": status,
        "blockers": blockers,
        "fresh_relation_executable_under_revised_terms": relation_executable,
        "conclusion": (
            "fresh_relation_proof_ready_but_current_relation_not_executable"
            if status == "ready" and not relation_executable
            else "fresh_relation_proof_ready_for_future_readiness_package"
            if status == "ready"
            else "fresh_relation_proof_not_sufficient"
        ),
        "does_not_authorize": [
            "additional live order",
            "candidate executor path execution",
            "timer/supervisor path load",
            "live config/operator/executor mutation",
            "continuous automated order flow",
        ],
    }
    phase_dir = write_phase(root, "p10akw_review", {"owner_decision": owner_decision, "review": review})
    summary = {
        "contract_version": P10AKW_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10akw_review_fresh_position_relation_proof_ready": status == "ready",
        "fresh_relation_executable_under_revised_terms": relation_executable,
        "p10akv_sufficient_for_additional_live_order_without_new_gate": False,
        "eligible_for_position_relation_resolution_scope": status == "ready" and not relation_executable,
        "eligible_for_execution_readiness_package_scope": status == "ready" and relation_executable,
        **no_order_matrix(remote_api_called=False),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {
            "p10akv_summary": evidence_file(p10akv_path),
            "remote_position_relation_proof": evidence_file(proof_path),
        },
        "allowed_next_gate": P10AKX_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "define_post_relation_proof_scope_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "review": str(phase_dir / "proof" / "review.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10akx(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10akw_path: Path,
    p10akw: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    relation_executable = bool(p10akw.get("fresh_relation_executable_under_revised_terms"))
    next_gate = P10AKY_READINESS_GATE if relation_executable else P10AKY_RESOLUTION_GATE
    next_scope = (
        "prepare_nonflat_canary_readiness_package_no_order_no_timer_no_supervisor"
        if relation_executable
        else "define_candidate_side_vs_existing_position_resolution_scope_no_order_no_remote_no_timer"
    )
    checks = {
        "owner_decision_p10akx_recorded": True,
        "p10akw_ready": p10akw.get("status") == "ready" and p10akw.get("allowed_next_gate") == P10AKX_GATE,
        "scope_only": True,
        "does_not_authorize_execution": True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10akx_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10akx_define_post_position_relation_proof_scope_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "scope_only": True,
        "authorizes_live_order": False,
    }
    scope = {
        "contract_version": "hv_balanced_12factor_p10akx_scope.v1",
        "status": status,
        "blockers": blockers,
        "fresh_relation_executable_under_revised_terms": relation_executable,
        "next_gate": next_gate,
        "next_gate_scope": next_scope,
        "why": (
            "fresh relation is executable under revised terms; next step may prepare readiness evidence only"
            if relation_executable
            else "fresh relation is still opposite-direction against existing position; next step must resolve candidate-side/account-position alignment"
        ),
        "does_not_authorize": [
            "live order",
            "remote read inside P10AKX",
            "timer/supervisor path load",
            "candidate executor path execution",
            "live config/operator/executor mutation",
        ],
    }
    phase_dir = write_phase(root, "p10akx_scope", {"owner_decision": owner_decision, "scope": scope})
    summary = {
        "contract_version": P10AKX_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10akx_post_relation_proof_scope_ready": status == "ready",
        "fresh_relation_executable_under_revised_terms": relation_executable,
        "next_scope_requires_position_relation_resolution": not relation_executable,
        "next_scope_allows_readiness_package_only": relation_executable,
        **no_order_matrix(remote_api_called=False),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {"p10akw_summary": evidence_file(p10akw_path)},
        "allowed_next_gate": next_gate if status == "ready" else "",
        "allowed_next_gate_scope": next_scope if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "scope": str(phase_dir / "proof" / "scope.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def run_corridor(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started = now_fn()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)
    p10aku_path = latest_p10aku_summary(args.p10aku_summary)
    p10aku = load_optional(p10aku_path)
    terms_path = source_path(p10aku, "execution_terms")
    terms = load_optional(terms_path)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10akv, p10akv_path = build_p10akv(
        root=root,
        run_id=run_id,
        now=started,
        args=args,
        p10aku_path=p10aku_path,
        p10aku=p10aku,
        terms_path=terms_path,
        terms=terms,
        command_runner=command_runner,
    )
    steps.append({"gate": "P10AKV", "status": p10akv.get("status"), "summary": evidence_file(p10akv_path)})
    if p10akv.get("status") != "ready":
        blockers.append("p10akv_blocked")
        status = "blocked"

    p10akw: dict[str, Any] = {}
    p10akw_path = root / "p10akw_review" / "summary.json"
    if status == "ready":
        p10akw, p10akw_path = build_p10akw(
            root=root,
            run_id=run_id,
            now=started,
            args=args,
            p10akv_path=p10akv_path,
            p10akv=p10akv,
        )
        steps.append({"gate": "P10AKW", "status": p10akw.get("status"), "summary": evidence_file(p10akw_path)})
        if p10akw.get("status") != "ready":
            blockers.append("p10akw_blocked")
            status = "blocked"

    p10akx: dict[str, Any] = {}
    p10akx_path = root / "p10akx_scope" / "summary.json"
    if status == "ready":
        p10akx, p10akx_path = build_p10akx(
            root=root,
            run_id=run_id,
            now=started,
            args=args,
            p10akw_path=p10akw_path,
            p10akw=p10akw,
        )
        steps.append({"gate": "P10AKX", "status": p10akx.get("status"), "summary": evidence_file(p10akx_path)})
        if p10akx.get("status") != "ready":
            blockers.append("p10akx_blocked")
            status = "blocked"

    relation_executable = bool(p10akv.get("fresh_relation_executable_under_revised_terms"))
    next_gate = str(p10akx.get("allowed_next_gate") or "") if p10akx else ""
    next_scope = str(p10akx.get("allowed_next_gate_scope") or "") if p10akx else ""
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10akv_p10akx_read_only_position_relation_corridor_ready": status == "ready",
        "corridor_scope": "P10AKV read-only fresh proof + P10AKW review + P10AKX next scope",
        "steps": steps,
        "fresh_relation_executable_under_revised_terms": relation_executable,
        "future_execution_precheck_ready_under_revised_terms": bool(
            p10akv.get("future_execution_precheck_ready_under_revised_terms")
        ),
        "next_scope_requires_position_relation_resolution": bool(
            p10akx.get("next_scope_requires_position_relation_resolution")
        )
        if p10akx
        else False,
        "blockers": blockers,
        **no_order_matrix(remote_api_called=bool(p10akv.get("remote_api_called"))),
        "source_evidence": {"p10aku_summary": evidence_file(p10aku_path), "execution_terms": evidence_file(terms_path)},
        "allowed_next_gate": next_gate if status == "ready" else "",
        "allowed_next_gate_scope": next_scope if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {"summary": str(root / "summary.json")},
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_corridor(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(
        "fresh_relation_executable_under_revised_terms="
        + str(summary["fresh_relation_executable_under_revised_terms"]).lower()
    )
    print("summary=" + summary["output_files"]["summary"])
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
