#!/usr/bin/env bash
set -u

MERIDIAN_ROOT="/root/meridian_alpha_live_runner"
MERIDIAN_REPO="$MERIDIAN_ROOT/repo"
MERIDIAN_VENV="$MERIDIAN_ROOT/venv"
MERIDIAN_PYTHON="$MERIDIAN_VENV/bin/python"
MERIDIAN_WRAPPER="$MERIDIAN_ROOT/bin/with-live-env"
MERIDIAN_CONFIG="$MERIDIAN_REPO/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml"

MERIDIAN_SERVICES=(
  "meridian-alpha-mainnet-supervisor-live.service"
  "meridian-alpha-mainnet-health-monitor.service"
)

failures=0

section() {
  printf '\n==== %s ====\n' "$1"
}

pass() {
  printf 'PASS %s\n' "$1"
}

warn() {
  printf 'WARN %s\n' "$1"
}

fail() {
  printf 'FAIL %s\n' "$1"
  failures=$((failures + 1))
}

unit_field() {
  systemctl show "$1" --no-pager -p "$2" 2>/dev/null | sed "s/^$2=//"
}

section "host"
printf 'hostname='; hostname
printf 'user='; id -un
printf 'utc='; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'kernel='; uname -a

section "Meridian runner paths"
for path in \
  "$MERIDIAN_ROOT" \
  "$MERIDIAN_REPO" \
  "$MERIDIAN_REPO/src/enhengclaw/live_trading/config.py" \
  "$MERIDIAN_REPO/scripts/live_trading/run_hv_balanced_mainnet_live_supervisor.py" \
  "$MERIDIAN_REPO/scripts/live_trading/run_hv_balanced_mainnet_health_monitor.py" \
  "$MERIDIAN_WRAPPER" \
  "$MERIDIAN_PYTHON" \
  "$MERIDIAN_CONFIG"; do
  if [ -e "$path" ]; then
    stat -c 'PASS %F %a %U:%G %y %n' "$path"
  else
    fail "missing Meridian path $path"
  fi
done

section "systemd service state"
for unit in "${MERIDIAN_SERVICES[@]}"; do
  printf '\n-- %s --\n' "$unit"
  systemctl show "$unit" --no-pager \
    -p Id -p LoadState -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p DropInPaths -p ExecStart 2>&1 || true
  if [ "$(unit_field "$unit" ActiveState)" = "active" ]; then
    fail "$unit is active; fix-window precheck expects disabled/quiet services"
  else
    pass "$unit is not active"
  fi
  systemctl cat "$unit" --no-pager 2>&1 | sed -n '1,140p' || true
done

section "explicit Python path probe"
if [ -x "$MERIDIAN_WRAPPER" ] && [ -x "$MERIDIAN_PYTHON" ] && [ -f "$MERIDIAN_CONFIG" ]; then
  "$MERIDIAN_WRAPPER" /usr/bin/env \
    PYTHONPATH="$MERIDIAN_REPO/src" \
    PYTHONNOUSERSITE=1 \
    VIRTUAL_ENV="$MERIDIAN_VENV" \
    PATH="$MERIDIAN_VENV/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    "$MERIDIAN_PYTHON" - "$MERIDIAN_CONFIG" "$MERIDIAN_REPO" <<'PY'
import json
import os
import sys
from pathlib import Path

config_path = Path(sys.argv[1]).resolve()
expected_repo = Path(sys.argv[2]).resolve()

import enhengclaw.live_trading.config as cfg
from enhengclaw.live_trading.config import load_live_trading_config

loaded = load_live_trading_config(config_path)
payload = {
    "sys_executable": sys.executable,
    "pythonpath": os.environ.get("PYTHONPATH", ""),
    "config_module_file": str(Path(cfg.__file__).resolve()),
    "config_root": str(Path(cfg.ROOT).resolve()),
    "loaded_config_path": str(loaded.path),
    "artifact_root": str(loaded.artifact_root),
    "sqlite_path": str(loaded.sqlite_path),
}
print(json.dumps(payload, indent=2, sort_keys=True))

module_ok = Path(cfg.__file__).resolve().is_relative_to(expected_repo / "src")
root_ok = Path(cfg.ROOT).resolve() == expected_repo
config_ok = loaded.path == config_path
artifact_ok = loaded.artifact_root.is_relative_to(expected_repo / "artifacts")
sqlite_ok = loaded.sqlite_path.is_relative_to(expected_repo / "artifacts")
if not (module_ok and root_ok and config_ok and artifact_ok and sqlite_ok):
    raise SystemExit(3)
PY
  rc=$?
  if [ "$rc" -eq 0 ]; then
    pass "explicit Meridian Python path probe passed"
  else
    fail "explicit Meridian Python path probe failed with rc=$rc"
  fi
else
  warn "skipping Python path probe because wrapper, Python, or config is missing"
fi

section "summary"
if [ "$failures" -eq 0 ]; then
  pass "Meridian path-resolution read-only precheck passed; no state was changed"
  exit 0
fi

fail "Meridian path-resolution read-only precheck failed with $failures blocker(s); no state was changed"
exit 1
