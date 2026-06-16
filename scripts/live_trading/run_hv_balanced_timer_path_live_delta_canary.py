from __future__ import annotations

import argparse
import hashlib
import json
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
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = "hv_balanced_timer_path_live_delta_canary.v1"
REMOTE_CONTRACT_VERSION = "hv_balanced_timer_path_live_delta_canary.remote.v1"
APPROVE_DECISION = "approve_timer_path_single_cycle_live_delta_canary_only_no_continuous_automation"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/timer_path_live_delta_canary"
DEFAULT_REMOTE_PROOF_PARENT = "/root/meridian_alpha_live_runner/proof_artifacts/timer_path_live_delta_canary"


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResult]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one small timer-path live_delta canary through the remote supervisor/core/delta path. "
            "It uses an isolated state database and does not enable systemd timers or continuous automation."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--remote-proof-parent", default=DEFAULT_REMOTE_PROOF_PARENT)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", choices=("BUY", "SELL"), default="BUY")
    parser.add_argument("--quantity", type=float, default=0.001)
    parser.add_argument("--max-notional-usdt", type=float, default=150.0)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:timer_path_live_delta_canary_single_cycle_no_continuous_automation",
    )
    parser.add_argument(
        "--readback-summary",
        default="",
        help="Classify an existing remote_summary.json without SSH or another live order.",
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


def file_sha256(path: str | Path) -> str:
    target = Path(path)
    if not target.exists() or not target.is_file():
        return ""
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_DECISION
    return {
        "contract_version": "hv_balanced_timer_path_live_delta_canary.owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "execute_timer_path_single_cycle_live_delta_canary_only_no_continuous_automation",
        "approved": approved,
        "scope": "one remote supervisor invocation, one core loop cycle, at most one live_delta market order",
        "continuous_automation_authorized": False,
        "systemd_timer_enable_authorized": False,
        "production_timer_service_change_authorized": False,
        "production_state_mutation_authorized": False,
        "remote_live_order_submission_authorized": approved,
    }


def remote_timer_path_live_delta_canary_command(
    *,
    remote_repo: str,
    remote_config: str,
    remote_live_env: str,
    remote_python: str,
    remote_root: str,
    expected_egress_ip: str,
    symbol: str,
    side: str,
    quantity: float,
    max_notional_usdt: float,
) -> str:
    cfg = {
        "contract_version": REMOTE_CONTRACT_VERSION,
        "remote_repo": remote_repo,
        "remote_config": remote_config,
        "remote_root": remote_root,
        "expected_egress_ip": expected_egress_ip,
        "symbol": str(symbol).upper(),
        "side": str(side).upper(),
        "quantity": float(quantity),
        "max_notional_usdt": float(max_notional_usdt),
    }
    cfg_json = json.dumps(cfg, sort_keys=True)
    return (
        f"""set -euo pipefail
cd {shlex.quote(remote_repo)}
mkdir -p {shlex.quote(remote_root)}
{shlex.quote(remote_live_env)} /usr/bin/env PYTHONNOUSERSITE=1 {shlex.quote(remote_python)} - <<'PY'
"""
        + r"""import argparse
import copy
import csv
import getpass
import hashlib
import json
import math
import os
import pathlib
import socket
import subprocess
import sys
import traceback
import urllib.request
from datetime import UTC, datetime

import pandas as pd

"""
        + "CFG = json.loads(" + repr(cfg_json) + ")\n"
        + r"""
REPO = pathlib.Path(CFG["remote_repo"]).resolve()
SRC = REPO / "src"
for item in (REPO, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from enhengclaw.live_trading.binance_usdm_client import BINANCE_USDM_MAINNET_BASE_URL, BinanceUsdmClient
from enhengclaw.live_trading.config import load_live_trading_config
from enhengclaw.live_trading.live_position_monitor import run_live_position_monitor
from enhengclaw.live_trading.live_risk_controls import evaluate_margin_cushion_gate
from enhengclaw.live_trading.mainnet_core_loop_runner import run_mainnet_core_loop
from enhengclaw.live_trading.mainnet_delta_execution_runner import run_mainnet_delta_execution
from enhengclaw.live_trading.mainnet_live_supervisor import run_mainnet_live_supervisor
from enhengclaw.live_trading.market_data import parse_symbol_exchange_filters
from enhengclaw.live_trading.state_store import LiveTradingStateStore
from enhengclaw.quant_research.contracts import write_json


def iso_now():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha(path):
    p = pathlib.Path(path)
    if not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def f(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def b(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            return response.read().decode("utf-8", errors="replace").strip(), ""
    except Exception as exc:
        return "", f"{type(exc).__name__}:{exc}"


def deep_copy_jsonish(value):
    return json.loads(json.dumps(value))


def load_and_write_canary_config(root):
    base = load_live_trading_config(CFG["remote_config"])
    payload = deep_copy_jsonish(base.payload)
    payload.setdefault("binance", {})
    payload["binance"]["venue"] = "usdm_futures"
    payload["binance"]["position_mode"] = "one_way"
    payload["binance"]["margin_type"] = "cross"
    payload["binance"]["max_leverage"] = 2
    payload["binance"]["auto_prepare_planned_symbol_settings"] = True
    payload.setdefault("risk", {})
    payload["risk"]["trading_enabled"] = False
    payload["risk"]["require_manual_live_confirm"] = True
    payload["risk"]["max_heartbeat_age_seconds"] = 300
    payload.setdefault("core_loop", {})
    payload["core_loop"].update({
        "target_engine": "single_phase",
        "max_cycles_per_invocation": 1,
        "interval_seconds": 0,
        "live_delta_enabled": True,
        "allow_multiphase_live_delta": False,
        "submit_orders": True,
        "auto_confirm_delta_after_preflight": True,
        "allowed_execution_stages": "entry_second",
        "max_live_delta_order_count_per_cycle": 1,
        "live_delta_order_cap_policy": {"mode": "legacy_fixed", "hard_max_order_count": 1},
        "min_seconds_between_live_delta_executions": 0,
        "fast_follow_entry_second_enabled": False,
        "capital_topup_after_static_noop": False,
        "kill_switch_source": "sqlite_operator_state",
    })
    payload.setdefault("mainnet_live_supervisor", {})
    payload["mainnet_live_supervisor"].update({
        "mode": "sqlite_armed_single_cycle_live_delta_canary_timer_path",
        "target_engine": "single_phase",
        "max_cycles_per_invocation": 1,
        "interval_seconds": 0,
        "allow_live_delta_when_armed": True,
        "allow_multiphase_live_delta": False,
        "capital_topup_enabled": False,
        "recover_stale_heartbeats": False,
        "disarm_on_blocker": True,
        "fast_follow_entry_second_enabled": False,
        "fast_follow_entry_second_delay_seconds": 0,
        "fast_follow_max_chain_invocations": 0,
        "fast_follow_policy": {"mode": "disabled", "max_chain_invocations_hard_cap": 0},
    })
    payload.setdefault("mainnet_health_monitor", {})
    payload["mainnet_health_monitor"]["require_systemd_timer_active"] = False
    payload["mainnet_health_monitor"]["auto_rearm_live_delta"] = False
    payload.setdefault("state", {})
    payload["state"]["sqlite_path"] = str(root / "state" / "timer_path_live_delta_canary.sqlite3")
    payload["state"]["artifact_root"] = str(root / "runs")
    config_path = root / "canary_config.json"
    write_json(config_path, payload)
    return base, payload, config_path


def credentials(payload):
    binance = dict(payload.get("binance") or {})
    key_env = str(binance.get("api_key_env") or "ENHENGCLAW_BINANCE_USDM_API_KEY")
    secret_env = str(binance.get("api_secret_env") or "ENHENGCLAW_BINANCE_USDM_API_SECRET")
    blockers = []
    key = os.environ.get(key_env, "").strip()
    secret = os.environ.get(secret_env, "").strip()
    if not key:
        blockers.append(f"missing_api_key_env:{key_env}")
    if not secret:
        blockers.append(f"missing_api_secret_env:{secret_env}")
    return {
        "api_key_env": key_env,
        "api_secret_env": secret_env,
        "api_key": key,
        "api_secret": secret,
        "recv_window_ms": int(binance.get("recv_window_ms") or 5000),
        "timeout_seconds": float(binance.get("timeout_seconds") or 10.0),
        "blockers": blockers,
    }


def client_from_payload(payload):
    c = credentials(payload)
    if c["blockers"]:
        return None, c
    return BinanceUsdmClient(
        base_url=BINANCE_USDM_MAINNET_BASE_URL,
        api_key=c["api_key"],
        api_secret=c["api_secret"],
        recv_window_ms=c["recv_window_ms"],
        timeout_seconds=c["timeout_seconds"],
    ), c


def read_all_position_risk(client):
    payload = client.position_information_v2().payload
    return [dict(item) for item in list(payload or []) if isinstance(item, dict)]


def position_amount(row):
    return f(row.get("positionAmt"))


def current_position_rows(position_risk, symbol):
    rows = []
    seen = set()
    for item in position_risk:
        sym = str(item.get("symbol") or "").upper()
        if not sym:
            continue
        amount = position_amount(item)
        if abs(amount) <= 1e-12 and sym != symbol:
            continue
        seen.add(sym)
        rows.append({
            "symbol": sym,
            "positionAmt": amount,
            "positionSide": str(item.get("positionSide") or "BOTH"),
            "entryPrice": f(item.get("entryPrice")),
            "markPrice": f(item.get("markPrice")),
            "notional": f(item.get("notional")),
            "marginType": str(item.get("marginType") or ""),
            "leverage": str(item.get("leverage") or ""),
            "isolated": str(item.get("isolated") or ""),
        })
    if symbol not in seen:
        rows.append({
            "symbol": symbol,
            "positionAmt": 0.0,
            "positionSide": "BOTH",
            "entryPrice": 0.0,
            "markPrice": 0.0,
            "notional": 0.0,
            "marginType": "",
            "leverage": "",
            "isolated": "",
        })
    return sorted(rows, key=lambda row: str(row["symbol"]))


def build_position_reference(root, run_id, payload):
    client, cred = client_from_payload(payload)
    blockers = list(cred["blockers"])
    if blockers or client is None:
        return {"status": "blocked", "blockers": blockers}
    position_risk = read_all_position_risk(client)
    rows = current_position_rows(position_risk, CFG["symbol"])
    reference_root = root / "position_reference" / f"{run_id}-genesis-snapshot"
    reference_root.mkdir(parents=True, exist_ok=True)
    ref_rows = [
        {
            "symbol": row["symbol"],
            "expected_position_amt": row["positionAmt"],
            "positionAmt": row["positionAmt"],
            "positionSide": row["positionSide"],
            "entryPrice": row["entryPrice"],
            "isolated": row["isolated"],
        }
        for row in rows
    ]
    fieldnames = ["symbol", "expected_position_amt", "positionAmt", "positionSide", "entryPrice", "isolated"]
    write_csv(reference_root / "reference_positions.csv", ref_rows, fieldnames)
    summary = {
        "contract_version": "hv_balanced_timer_path_live_delta_canary.position_reference.v1",
        "run_id": run_id,
        "status": "mainnet_position_genesis_snapshot",
        "read_only": True,
        "proof_artifacts_only": True,
        "generated_at_utc": iso_now(),
        "expected_position_count": len(ref_rows),
        "expected_symbols": [str(row["symbol"]) for row in ref_rows],
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
            "reference_positions": str(reference_root / "reference_positions.csv"),
        },
    }
    write_json(reference_root / "run_summary.json", summary)
    write_json(reference_root / "genesis_snapshot.json", {**summary, "positions": ref_rows})
    return {"status": "ready", "blockers": [], "reference_root": str(reference_root), "summary": summary}


def canary_plan_runner_factory(root, payload):
    plan_calls = []

    def canary_plan_runner(args, *, env=None):
        started = datetime.now(UTC)
        run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "-timer-path-live-delta-canary-plan"
        plan_root = root / "canary_plan" / run_id
        plan_root.mkdir(parents=True, exist_ok=True)
        blockers = []
        client, cred = client_from_payload(payload)
        blockers.extend(cred["blockers"])
        side = CFG["side"]
        symbol = CFG["symbol"]
        quantity = float(CFG["quantity"])
        mark_price = 0.0
        current_amt = 0.0
        position_risk = []
        account = {}
        symbol_filter = None
        if client is not None and not blockers:
            account = dict(client.account_information_v3().payload)
            position_risk = read_all_position_risk(client)
            exchange_info = dict(client.exchange_info().payload)
            filters = parse_symbol_exchange_filters(exchange_info)
            symbol_filter = filters.get(symbol)
            risk_by_symbol = {str(row.get("symbol") or "").upper(): dict(row) for row in position_risk}
            symbol_risk = dict(risk_by_symbol.get(symbol) or {})
            current_amt = f(symbol_risk.get("positionAmt"))
            mark_payload = dict(client.premium_index(symbol=symbol).payload)
            mark_price = f(mark_payload.get("markPrice"), f(symbol_risk.get("markPrice")))
            if symbol_filter is None:
                blockers.append(f"exchange_filter_missing:{symbol}")
            elif not symbol_filter.tradable_usdm_perp:
                blockers.append(f"symbol_not_tradable_usdm_perp:{symbol}")
            elif quantity + 1e-12 < float(symbol_filter.min_qty):
                blockers.append(f"quantity_below_min_qty:{quantity}<{float(symbol_filter.min_qty)}")
            if symbol_filter is not None and float(symbol_filter.step_size) > 0.0:
                steps = quantity / float(symbol_filter.step_size)
                if abs(steps - round(steps)) > 1e-8:
                    blockers.append(f"quantity_not_step_aligned:{quantity}:{float(symbol_filter.step_size)}")
            if mark_price <= 0.0:
                blockers.append(f"mark_price_unreadable:{symbol}")
            notional = abs(quantity * mark_price)
            if symbol_filter is not None and float(symbol_filter.min_notional) > 0.0 and notional + 1e-9 < float(symbol_filter.min_notional):
                blockers.append(f"notional_below_min_notional:{notional}<{float(symbol_filter.min_notional)}")
            if notional > float(CFG["max_notional_usdt"]) + 1e-9:
                blockers.append(f"notional_above_canary_cap:{notional}>{float(CFG['max_notional_usdt'])}")
        else:
            notional = 0.0
        delta = quantity if side == "BUY" else -quantity
        target_amt = current_amt + delta
        planned_margin = 0.0 if False else (abs(quantity * mark_price) / 2.0 if mark_price > 0.0 else 0.0)
        margin_gate = evaluate_margin_cushion_gate(
            {
                "available_balance_usdt": f(account.get("availableBalance")),
                "total_wallet_balance_usdt": f(account.get("totalWalletBalance")),
            },
            config=payload,
            planned_additional_initial_margin_usdt=planned_margin,
            require_configured=True,
        )
        blockers.extend(str(item) for item in list(margin_gate.get("blockers") or []))
        source_client_id = "timer-canary-src-" + hashlib.sha256(f"{run_id}:{symbol}".encode()).hexdigest()[:8]
        current_rows = current_position_rows(position_risk, symbol)
        targets = {str(row["symbol"]): f(row["positionAmt"]) for row in current_rows}
        targets[symbol] = target_amt
        target_rows = [
            {
                "symbol": sym,
                "usdm_symbol": sym,
                "target_position_amt": amount,
                "current_position_amt": next((f(row["positionAmt"]) for row in current_rows if str(row["symbol"]) == sym), 0.0),
            }
            for sym, amount in sorted(targets.items())
            if abs(float(amount)) > 1e-12 or sym == symbol
        ]
        execution_rows = [{
            "intent_id": "timer_path_live_delta_canary_001",
            "portfolio_id": "timer_path_live_delta_canary",
            "symbol": symbol,
            "side": side,
            "position_side": "BOTH",
            "order_type": "MARKET",
            "quantity": quantity,
            "reduce_only": False,
            "target_position_amt": target_amt,
            "current_position_amt": current_amt,
            "delta_position_amt": delta,
            "max_slippage_bps": 20.0,
            "client_order_id": source_client_id,
            "execution_phase": "entry_second",
            "delta_classification": "timer_path_live_delta_canary",
            "final_target_position_amt": target_amt,
            "second_phase_required": False,
        }]
        sizing_rows = [{
            "symbol": symbol,
            "client_order_id": source_client_id,
            "quantity": quantity,
            "order_delta_position_amt": delta,
            "rounded_notional_usdt": abs(quantity * mark_price),
            "mark_price": mark_price,
            "reduce_only": False,
            "no_order_required": False,
            "execution_phase": "entry_second",
            "blockers": ";".join(sorted(set(blockers))),
        }]
        status = "mainnet_current_position_rebalance_plan_ready" if not blockers else "blocked"
        summary = {
            "contract_version": "hv_balanced_timer_path_live_delta_canary.source_plan.v1",
            "run_id": run_id,
            "status": status,
            "blockers": sorted(set(blockers)),
            "artifact_root": str(plan_root),
            "current_position_aware": True,
            "plan_only": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "recurring_mainnet_enabled": False,
            "mainnet_order_submission_authorized": False,
            "active_execution_phase": "entry_second",
            "planned_delta_order_count": 1,
            "target_position_count": len([row for row in target_rows if abs(float(row["target_position_amt"])) > 1e-12]),
            "current_position_count": len([row for row in current_rows if abs(float(row["positionAmt"])) > 1e-12]),
            "phase_counts": {"entry_second": 1},
            "deferred_phase_counts": {},
            "canary_symbol": symbol,
            "canary_side": side,
            "canary_quantity": quantity,
            "canary_notional_usdt": abs(quantity * mark_price),
        }
        write_json(plan_root / "run_summary.json", summary)
        write_json(plan_root / "runtime_gate_context.json", {
            "current_position_aware": True,
            "mainnet_order_submission_authorized": False,
            "timer_path_live_delta_canary": True,
        })
        write_json(plan_root / "execution_plan.json", {
            "plan_id": run_id,
            "portfolio_id": "timer_path_live_delta_canary",
            "mode": "plan_only",
            "status": "ok" if not blockers else "blocked",
            "blockers": sorted(set(blockers)),
            "active_execution_phase": "entry_second",
            "phase_counts": {"entry_second": 1},
            "deferred_phase_counts": {},
        })
        write_json(plan_root / "risk_gate.json", {
            "risk_gate_id": run_id + ":risk",
            "portfolio_id": "timer_path_live_delta_canary",
            "mode": "plan_only",
            "passed": not blockers,
            "decision": "allow_plan" if not blockers else "block_plan",
            "blockers": sorted(set(blockers)),
        })
        write_json(plan_root / "target_portfolio.json", {
            "portfolio_id": "timer_path_live_delta_canary",
            "positions": target_rows,
            "source": "timer_path_live_delta_canary",
        })
        write_json(plan_root / "margin_cushion_gate.json", margin_gate)
        write_json(plan_root / "market_data_audit.json", {
            "source": "timer_path_live_delta_canary_fresh_symbol_mark",
            "row_count": 1,
            "closed_daily_rows": 1,
            "closed_four_hour_rows": 1,
            "funding_history_error_symbols": [],
            "symbol": symbol,
            "mark_price": mark_price,
            "generated_at_utc": iso_now(),
        })
        write_json(plan_root / "decision_snapshot.json", {
            "status": "ok" if not blockers else "blocked",
            "rebalance_slot": True,
            "source": "timer_path_live_delta_canary",
            "blockers": sorted(set(blockers)),
        })
        pd.DataFrame(execution_rows).to_csv(plan_root / "execution_plan.csv", index=False)
        pd.DataFrame(sizing_rows).to_csv(plan_root / "order_sizing_report.csv", index=False)
        pd.DataFrame(current_rows).to_csv(plan_root / "current_positions.csv", index=False)
        pd.DataFrame(target_rows).to_csv(plan_root / "target_positions.csv", index=False)
        plan_calls.append(summary)
        return summary, 0 if not blockers else 2

    canary_plan_runner.plan_calls = plan_calls
    return canary_plan_runner


def guarded_command_runner(commands):
    return 2, "", "fast_follow_or_external_command_blocked_by_timer_path_live_delta_canary"


def main_remote():
    started = iso_now()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-timer-path-live-delta-canary"
    root = pathlib.Path(CFG["remote_root"]).resolve() / run_id
    root.mkdir(parents=True, exist_ok=True)
    ip, ip_error = public_ip()
    identity = {
        "contract_version": "hv_balanced_timer_path_live_delta_canary.remote_identity.v1",
        "whoami": getpass.getuser(),
        "hostname": socket.gethostname(),
        "repo_path": str(REPO),
        "remote_config": CFG["remote_config"],
        "remote_config_sha256": sha(CFG["remote_config"]),
        "egress_ip": ip,
        "egress_ip_error": ip_error,
        "expected_egress_ip": CFG["expected_egress_ip"],
        "mainnet_live_supervisor_sha256": sha(REPO / "src/enhengclaw/live_trading/mainnet_live_supervisor.py"),
        "mainnet_core_loop_sha256": sha(REPO / "src/enhengclaw/live_trading/mainnet_core_loop_runner.py"),
        "mainnet_delta_execution_sha256": sha(REPO / "src/enhengclaw/live_trading/mainnet_delta_execution_runner.py"),
    }
    blockers = []
    if ip and CFG["expected_egress_ip"] and ip != CFG["expected_egress_ip"]:
        blockers.append(f"remote_egress_ip_mismatch:{ip}!={CFG['expected_egress_ip']}")
    base = None
    payload = {}
    config_path = root / "canary_config.json"
    supervisor_summary = {}
    supervisor_exit = 2
    reference = {}
    operator_arm = {}
    operator_disarm = {}
    final_operator_state = {}
    plan_calls = []
    exception = ""
    try:
        base, payload, config_path = load_and_write_canary_config(root)
        reference = build_position_reference(root, run_id, payload)
        blockers.extend(str(item) for item in list(reference.get("blockers") or []))
        store = LiveTradingStateStore(config_path.parent / "state" / "timer_path_live_delta_canary.sqlite3")
        store.initialize()
        initial_state = store.read_operator_state()
        if bool(initial_state.get("paused")):
            blockers.append("isolated_operator_state_kill_switch_paused")
        if not blockers:
            operator_arm = store.record_operator_action(
                run_id=run_id,
                action_type="arm-live-delta",
                reason="single-cycle timer-path live_delta canary only",
                created_at_utc=iso_now(),
            )
            plan_runner = canary_plan_runner_factory(root, payload)

            def canary_core_loop_runner(core_args, *, env=None, now_fn=None):
                return run_mainnet_core_loop(
                    core_args,
                    env=env or os.environ,
                    monitor_runner=run_live_position_monitor,
                    plan_runner=plan_runner,
                    delta_runner=run_mainnet_delta_execution,
                    now_fn=now_fn,
                    sleep_fn=lambda _seconds: None,
                )

            sup_args = argparse.Namespace(
                config=str(config_path),
                as_of="now",
                fixture_panel="",
                symbols=CFG["symbol"],
                public_market_data=False,
                reference_run=str(reference.get("reference_root") or ""),
                target_engine="single_phase",
                cycles=1,
                interval_seconds=0.0,
                position_tolerance=1e-9,
                fast_follow_entry_second=False,
                fast_follow_chain_depth=0,
            )
            supervisor_summary, supervisor_exit = run_mainnet_live_supervisor(
                sup_args,
                env=os.environ,
                core_loop_runner=canary_core_loop_runner,
                sleep_fn=lambda _seconds: None,
                command_runner=guarded_command_runner,
            )
            plan_calls = list(getattr(plan_runner, "plan_calls", []))
    except Exception as exc:
        exception = traceback.format_exc()
        blockers.append(f"remote_timer_path_live_delta_canary_exception:{type(exc).__name__}:{exc}")
    finally:
        try:
            store = LiveTradingStateStore(config_path.parent / "state" / "timer_path_live_delta_canary.sqlite3")
            store.initialize()
            if bool(store.read_operator_state().get("live_delta_armed")):
                operator_disarm = store.record_operator_action(
                    run_id=run_id,
                    action_type="disarm-live-delta",
                    reason="single-cycle timer-path live_delta canary completed; no continuous automation",
                    created_at_utc=iso_now(),
                )
            final_operator_state = store.read_operator_state()
        except Exception as exc:
            blockers.append(f"isolated_operator_disarm_readback_failed:{type(exc).__name__}:{exc}")
    if supervisor_exit != 0:
        blockers.append(f"supervisor_exit_nonzero:{supervisor_exit}")
    blockers.extend(str(item) for item in list(supervisor_summary.get("blockers") or []))
    orders = int(supervisor_summary.get("orders_submitted") or 0)
    fills = int(supervisor_summary.get("fill_count") or 0)
    if orders != 1:
        blockers.append(f"timer_path_canary_expected_one_order:{orders}")
    if fills != 1:
        blockers.append(f"timer_path_canary_expected_one_fill:{fills}")
    if bool(final_operator_state.get("live_delta_armed")):
        blockers.append("isolated_operator_live_delta_still_armed_after_canary")
    fast_follow_schedule = dict(supervisor_summary.get("fast_follow_entry_second_schedule") or {})
    fast_follow_status = str(fast_follow_schedule.get("status") or "not_requested")
    fast_follow_reason = str(fast_follow_schedule.get("reason") or "")
    if not (
        fast_follow_status in {"", "not_requested", "disabled"}
        or (fast_follow_status == "skipped" and fast_follow_reason == "fast_follow_entry_second_disabled")
    ):
        blockers.append(f"fast_follow_schedule_unexpected:{fast_follow_schedule.get('status')}")
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": CFG["contract_version"],
        "run_id": run_id,
        "status": status,
        "blockers": sorted(set(blockers)),
        "started_at_utc": started,
        "finished_at_utc": iso_now(),
        "remote_root": str(root),
        "remote_runner_identity_readback": identity,
        "generated_config": str(config_path),
        "generated_config_sha256": sha(config_path),
        "base_config": CFG["remote_config"],
        "base_config_sha256": sha(CFG["remote_config"]),
        "position_reference": reference,
        "operator_arm_action": operator_arm,
        "operator_disarm_action": operator_disarm,
        "final_operator_state": final_operator_state,
        "supervisor_summary": supervisor_summary,
        "supervisor_exit_code": int(supervisor_exit),
        "plan_calls": plan_calls,
        "timer_path_invoked": bool(supervisor_summary),
        "supervisor_invoked": bool(supervisor_summary),
        "core_loop_invoked": bool(list(supervisor_summary.get("cycles") or [])),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "production_config_modified": False,
        "production_state_mutated": False,
        "continuous_automation_enabled": False,
        "configured_cycle_count": int(supervisor_summary.get("configured_cycle_count") or 0),
        "completed_cycle_count": int(supervisor_summary.get("completed_cycle_count") or 0),
        "orders_submitted": orders,
        "fill_count": fills,
        "canary_symbol": CFG["symbol"],
        "canary_side": CFG["side"],
        "canary_quantity": float(CFG["quantity"]),
        "max_notional_usdt": float(CFG["max_notional_usdt"]),
        "exception_traceback": exception,
    }
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if status == "ready" else 2


raise SystemExit(main_remote())
PY
"""
    )


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if not stripped:
        return {}
    try:
        return dict(json.loads(stripped))
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        return dict(json.loads(stripped[start : end + 1]))
    except json.JSONDecodeError:
        return {}


def acceptable_remote_blockers(remote_summary: dict[str, Any]) -> list[str]:
    blockers = [str(item) for item in list(remote_summary.get("blockers") or [])]
    fast_follow_schedule = dict(
        dict(remote_summary.get("supervisor_summary") or {}).get("fast_follow_entry_second_schedule") or {}
    )
    fast_follow_disabled_skip = (
        str(fast_follow_schedule.get("status") or "") == "skipped"
        and str(fast_follow_schedule.get("reason") or "") == "fast_follow_entry_second_disabled"
    )
    if fast_follow_disabled_skip:
        blockers = [item for item in blockers if item != "fast_follow_schedule_unexpected:skipped"]
    return sorted(set(blockers))


def remote_summary_ready(remote_summary: dict[str, Any]) -> bool:
    return (
        str(remote_summary.get("status") or "") in {"ready", "blocked"}
        and not acceptable_remote_blockers(remote_summary)
        and int(remote_summary.get("orders_submitted") or 0) == 1
        and int(remote_summary.get("fill_count") or 0) == 1
        and remote_summary.get("timer_path_invoked") is True
        and remote_summary.get("supervisor_invoked") is True
        and remote_summary.get("systemd_timer_service_invoked") is False
        and remote_summary.get("continuous_automation_enabled") is False
        and bool(dict(remote_summary.get("final_operator_state") or {}).get("live_delta_armed")) is False
    )


def run_canary(args: argparse.Namespace, *, command_runner: CommandRunner = local_command_runner) -> tuple[dict[str, Any], int]:
    generated_at = utc_now()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)

    owner = owner_decision_record(args, generated_at)
    write_json(root / "owner_decision.json", owner)
    blockers: list[str] = []
    if not owner["approved"]:
        blockers.append("owner_decision_not_approved_for_timer_path_live_delta_canary")
    if float(args.quantity) <= 0.0:
        blockers.append("canary_quantity_must_be_positive")
    if float(args.max_notional_usdt) <= 0.0:
        blockers.append("canary_max_notional_must_be_positive")
    if str(args.remote_host) != DEFAULT_REMOTE_HOST:
        blockers.append(f"remote_host_not_expected_runner:{args.remote_host}")
    if str(args.remote_repo) != DEFAULT_REMOTE_REPO:
        blockers.append(f"remote_repo_not_expected_runner:{args.remote_repo}")

    command = ""
    command_result: CommandResult | None = None
    remote_summary: dict[str, Any] = {}
    remote_root = f"{str(args.remote_proof_parent).rstrip('/')}/{run_id}"
    readback_summary_raw = str(getattr(args, "readback_summary", "") or "").strip()
    readback_summary_path = resolve_path(readback_summary_raw) if readback_summary_raw else Path("")
    if readback_summary_raw:
        if not readback_summary_path.exists():
            blockers.append(f"readback_summary_missing:{readback_summary_path}")
        else:
            remote_summary = dict(json.loads(readback_summary_path.read_text(encoding="utf-8")))
            write_json(root / "remote_summary.json", remote_summary)
            write_json(
                root / "remote_command_result.json",
                {
                    "readback_only": True,
                    "readback_summary": str(readback_summary_path),
                    "returncode": None,
                    "stdout_tail": "",
                    "stderr_tail": "",
                },
            )
            remote_root = str(remote_summary.get("remote_root") or remote_root)
            if not remote_summary_ready(remote_summary):
                blockers.append("remote_timer_path_canary_summary_not_ready")
                blockers.extend(acceptable_remote_blockers(remote_summary))
    elif not blockers:
        command = remote_timer_path_live_delta_canary_command(
            remote_repo=str(args.remote_repo),
            remote_config=str(args.remote_config),
            remote_live_env=str(args.remote_live_env),
            remote_python=str(args.remote_python),
            remote_root=remote_root,
            expected_egress_ip=str(args.expected_egress_ip),
            symbol=str(args.symbol),
            side=str(args.side),
            quantity=float(args.quantity),
            max_notional_usdt=float(args.max_notional_usdt),
        )
        write_json(
            root / "remote_command_manifest.json",
            {
                "remote_host": str(args.remote_host),
                "remote_repo": str(args.remote_repo),
                "remote_config": str(args.remote_config),
                "remote_live_env": str(args.remote_live_env),
                "remote_python": str(args.remote_python),
                "remote_root": remote_root,
                "symbol": str(args.symbol).upper(),
                "side": str(args.side).upper(),
                "quantity": float(args.quantity),
                "max_notional_usdt": float(args.max_notional_usdt),
            },
        )
        command_result = command_runner(ssh_args(str(args.remote_host), int(args.ssh_connect_timeout), command))
        write_json(
            root / "remote_command_result.json",
            {
                "args": command_result.args,
                "returncode": command_result.returncode,
                "stdout_tail": command_result.stdout[-12000:],
                "stderr_tail": command_result.stderr[-12000:],
            },
        )
        remote_summary = extract_json_object(command_result.stdout)
        write_json(root / "remote_summary.json", remote_summary)
        if command_result.returncode != 0 and not remote_summary_ready(remote_summary):
            blockers.append(f"remote_timer_path_canary_command_failed:{command_result.returncode}")
        if not remote_summary:
            blockers.append("remote_timer_path_canary_summary_missing")
        elif not remote_summary_ready(remote_summary):
            blockers.append("remote_timer_path_canary_summary_not_ready")
            blockers.extend(acceptable_remote_blockers(remote_summary))

    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "status": status,
        "timer_path_live_delta_canary_ready": status == "ready",
        "blockers": sorted(set(blockers)),
        "started_at_utc": iso_z(generated_at),
        "finished_at_utc": iso_z(utc_now()),
        "artifact_root": str(root),
        "project_profile": str(args.project_profile),
        "owner_decision": owner,
        "remote_root": remote_root,
        "remote_summary": remote_summary,
        "readback_only": bool(readback_summary_path),
        "readback_summary": str(readback_summary_path) if readback_summary_path else "",
        "orders_submitted": int(remote_summary.get("orders_submitted") or 0),
        "fill_count": int(remote_summary.get("fill_count") or 0),
        "timer_path_invoked": bool(remote_summary.get("timer_path_invoked")),
        "supervisor_invoked": bool(remote_summary.get("supervisor_invoked")),
        "core_loop_invoked": bool(remote_summary.get("core_loop_invoked")),
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "production_config_modified": False,
        "production_state_mutated": False,
        "continuous_automation_enabled": False,
        "operator_live_delta_armed_after_canary": bool(
            dict(remote_summary.get("final_operator_state") or {}).get("live_delta_armed")
        ),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision": str(root / "owner_decision.json"),
            "remote_command_result": str(root / "remote_command_result.json"),
            "remote_summary": str(root / "remote_summary.json"),
        },
    }
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    _, exit_code = run_canary(parse_args(argv))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
