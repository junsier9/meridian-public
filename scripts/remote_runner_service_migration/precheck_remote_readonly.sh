#!/usr/bin/env bash
set -u

LEGACY_SUPERVISOR_TIMER="enhengclaw-mainnet-supervisor-live.timer"
LEGACY_SUPERVISOR_SERVICE="enhengclaw-mainnet-supervisor-live.service"
LEGACY_HEALTH_TIMER="enhengclaw-mainnet-health-monitor.timer"
LEGACY_HEALTH_SERVICE="enhengclaw-mainnet-health-monitor.service"
LEGACY_NOORDER_TIMER="enhengclaw-mainnet-supervisor-noorder.timer"

MERIDIAN_UNITS=(
  "meridian-alpha-mainnet-supervisor-live.service"
  "meridian-alpha-mainnet-supervisor-live.timer"
  "meridian-alpha-mainnet-health-monitor.service"
  "meridian-alpha-mainnet-health-monitor.timer"
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

is_active() {
  [ "$(unit_field "$1" ActiveState)" = "active" ]
}

is_loaded() {
  [ "$(unit_field "$1" LoadState)" = "loaded" ]
}

section "host"
printf 'hostname='; hostname
printf 'user='; id -un
printf 'utc='; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'kernel='; uname -a

section "legacy timers"
for unit in "$LEGACY_SUPERVISOR_TIMER" "$LEGACY_HEALTH_TIMER" "$LEGACY_NOORDER_TIMER"; do
  printf '\n-- %s --\n' "$unit"
  systemctl show "$unit" --no-pager \
    -p Id -p LoadState -p ActiveState -p SubState -p UnitFileState \
    -p FragmentPath -p LastTriggerUSec -p Result 2>&1 || true
done

if is_active "$LEGACY_SUPERVISOR_TIMER"; then
  pass "$LEGACY_SUPERVISOR_TIMER is active"
else
  fail "$LEGACY_SUPERVISOR_TIMER is not active"
fi

if is_active "$LEGACY_HEALTH_TIMER"; then
  pass "$LEGACY_HEALTH_TIMER is active"
else
  fail "$LEGACY_HEALTH_TIMER is not active"
fi

if is_active "$LEGACY_NOORDER_TIMER"; then
  fail "$LEGACY_NOORDER_TIMER is active; live/no-order timer selection is ambiguous"
else
  pass "$LEGACY_NOORDER_TIMER is not active"
fi

section "legacy oneshot service quiet gate"
for unit in "$LEGACY_SUPERVISOR_SERVICE" "$LEGACY_HEALTH_SERVICE"; do
  state="$(unit_field "$unit" ActiveState)"
  substate="$(unit_field "$unit" SubState)"
  printf '%s ActiveState=%s SubState=%s\n' "$unit" "$state" "$substate"
  if [ "$state" = "active" ]; then
    fail "$unit is currently active; abort before any apply window"
  else
    pass "$unit is not active"
  fi
done

section "Meridian absent gate"
for unit in "${MERIDIAN_UNITS[@]}"; do
  printf '\n-- %s --\n' "$unit"
  systemctl show "$unit" --no-pager \
    -p Id -p LoadState -p ActiveState -p SubState -p UnitFileState \
    -p FragmentPath -p LastTriggerUSec -p Result 2>&1 || true
  if is_loaded "$unit"; then
    fail "$unit already exists before install; abort and inspect drift"
  else
    pass "$unit is absent"
  fi
done

section "runner roots"
for path in \
  /root/enhengclaw_live_runner \
  /root/enhengclaw_live_runner/repo \
  /root/enhengclaw_live_runner/bin/with-live-env \
  /root/enhengclaw_live_runner/venv/bin/python; do
  if [ -e "$path" ]; then
    stat -c 'PASS %F %a %U:%G %y %n' "$path"
  else
    fail "missing required legacy path $path"
  fi
done

if [ -e /root/meridian_alpha_live_runner ]; then
  fail "/root/meridian_alpha_live_runner already exists before apply"
else
  pass "/root/meridian_alpha_live_runner is absent"
fi

section "unit consumers"
systemctl cat "$LEGACY_SUPERVISOR_SERVICE" "$LEGACY_HEALTH_SERVICE" "$LEGACY_NOORDER_TIMER" --no-pager 2>&1 || true

section "latest legacy artifact directories"
artifact_base=/root/enhengclaw_live_runner/repo/artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate
if [ -d "$artifact_base" ]; then
  find "$artifact_base" -type d \
    \( -path '*mainnet_live_supervisor*' -o -path '*mainnet_health_monitor*' -o -path '*mainnet_delta_execution*' -o -path '*mainnet_core_loop*' \) \
    -printf '%T@ %TY-%Tm-%TdT%TH:%TM:%TS %p\n' 2>/dev/null | sort -nr | head -30
else
  warn "artifact base missing: $artifact_base"
fi

section "summary"
if [ "$failures" -eq 0 ]; then
  pass "remote precheck passed; no state was changed"
  exit 0
fi

fail "remote precheck failed with $failures blocker(s); no state was changed"
exit 1

