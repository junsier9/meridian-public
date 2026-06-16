#!/usr/bin/env bash
set -u

DROPIN_ROOT="systemd-dropins"
EXPECT_INSTALLED=0
failures=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dropin-root)
      DROPIN_ROOT="${2:?missing value for --dropin-root}"
      shift 2
      ;;
    --expect-installed)
      EXPECT_INSTALLED=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: bash verify_meridian_path_dropins.sh [--dropin-root DIR] [--expect-installed]

Read-only verifier for the Meridian service path/config-resolution drop-ins.
It checks the static drop-in content and, when --expect-installed is provided,
also inspects installed systemd service state without enabling or starting
anything.
USAGE
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

DROPINS=(
  "meridian-alpha-mainnet-supervisor-live.service.d/10-meridian-path.conf"
  "meridian-alpha-mainnet-health-monitor.service.d/10-meridian-path.conf"
)
SERVICES=(
  "meridian-alpha-mainnet-supervisor-live.service"
  "meridian-alpha-mainnet-health-monitor.service"
)

fail() {
  printf 'FAIL %s\n' "$1"
  failures=$((failures + 1))
}

pass() {
  printf 'PASS %s\n' "$1"
}

unit_field() {
  systemctl show "$1" --no-pager -p "$2" 2>/dev/null | sed "s/^$2=//"
}

printf 'VERIFY dropin_root=%s expect_installed=%s\n' "$DROPIN_ROOT" "$EXPECT_INSTALLED"

for rel in "${DROPINS[@]}"; do
  path="$DROPIN_ROOT/$rel"
  if [ -f "$path" ]; then
    pass "found drop-in $path"
  else
    fail "missing drop-in $path"
    continue
  fi

  if grep -InE '/root/enhengclaw_live_runner|enhengclaw-mainnet-' "$path" 2>/dev/null; then
    fail "$path contains legacy runner or unit names"
  else
    pass "$path avoids legacy runner and unit names"
  fi

  if grep -q '^ExecStart=$' "$path"; then
    pass "$path clears the base ExecStart"
  else
    fail "$path does not clear the base ExecStart"
  fi

  for token in \
    '/root/meridian_alpha_live_runner/bin/with-live-env' \
    '/usr/bin/env' \
    'PYTHONPATH=/root/meridian_alpha_live_runner/repo/src' \
    'VIRTUAL_ENV=/root/meridian_alpha_live_runner/venv' \
    '/root/meridian_alpha_live_runner/venv/bin/python' \
    '/root/meridian_alpha_live_runner/repo/config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_handoff_observation.yaml'; do
    if grep -q "$token" "$path"; then
      pass "$path contains $token"
    else
      fail "$path missing $token"
    fi
  done

  if grep -qE ' python scripts/|--config config/' "$path"; then
    fail "$path still contains relative script or config execution"
  else
    pass "$path uses explicit script/config paths"
  fi
done

if [ "$EXPECT_INSTALLED" -eq 1 ]; then
  for unit in "${SERVICES[@]}"; do
    load_state="$(unit_field "$unit" LoadState)"
    active_state="$(unit_field "$unit" ActiveState)"
    unit_file_state="$(unit_field "$unit" UnitFileState)"
    printf '%s LoadState=%s ActiveState=%s UnitFileState=%s\n' \
      "$unit" "$load_state" "$active_state" "$unit_file_state"
    if [ "$load_state" != "loaded" ]; then
      fail "$unit is not installed/loaded"
    fi
    if [ "$active_state" = "active" ]; then
      fail "$unit is active; fix-window verifier expects no running service"
    fi
    if [ "$unit_file_state" = "enabled" ]; then
      fail "$unit is enabled; fix-window verifier does not authorize timers/services"
    fi
    systemctl cat "$unit" --no-pager 2>&1 | sed -n '1,160p' || true
  done
fi

if [ "$failures" -eq 0 ]; then
  pass "Meridian path drop-in verification passed; no state was changed"
  exit 0
fi

fail "Meridian path drop-in verification failed with $failures blocker(s); no state was changed"
exit 1
