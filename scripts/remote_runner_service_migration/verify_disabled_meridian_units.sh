#!/usr/bin/env bash
set -u

UNIT_DIR="systemd"
EXPECT_INSTALLED=0
failures=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --unit-dir)
      UNIT_DIR="${2:?missing value for --unit-dir}"
      shift 2
      ;;
    --expect-installed)
      EXPECT_INSTALLED=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: bash verify_disabled_meridian_units.sh [--unit-dir DIR] [--expect-installed]

Read-only verifier for the Meridian unit drafts or installed disabled units.
It runs systemd-analyze verify when available and fails if Meridian timers are
active/enabled or if the legacy supervisor service is currently active.
USAGE
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

MERIDIAN_UNITS=(
  "meridian-alpha-mainnet-supervisor-live.service"
  "meridian-alpha-mainnet-supervisor-live.timer"
  "meridian-alpha-mainnet-health-monitor.service"
  "meridian-alpha-mainnet-health-monitor.timer"
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

printf 'VERIFY unit_dir=%s expect_installed=%s\n' "$UNIT_DIR" "$EXPECT_INSTALLED"

for unit in "${MERIDIAN_UNITS[@]}"; do
  path="$UNIT_DIR/$unit"
  if [ -f "$path" ]; then
    pass "found unit draft $path"
  else
    fail "missing unit draft $path"
  fi
done

legacy_refs=0
for unit in "${MERIDIAN_UNITS[@]}"; do
  path="$UNIT_DIR/$unit"
  if [ -f "$path" ] && grep -InE '/root/enhengclaw_live_runner|enhengclaw-mainnet-' "$path" 2>/dev/null; then
    legacy_refs=1
  fi
done

if [ "$legacy_refs" -ne 0 ]; then
  fail "Meridian unit drafts contain legacy runner or unit names"
else
  pass "Meridian unit drafts avoid legacy runner and unit names"
fi

if command -v systemd-analyze >/dev/null 2>&1; then
  if systemd-analyze verify "${MERIDIAN_UNITS[@]/#/$UNIT_DIR/}"; then
    pass "systemd-analyze verify passed"
  else
    fail "systemd-analyze verify failed"
  fi
else
  fail "systemd-analyze is unavailable"
fi

if [ "$(unit_field enhengclaw-mainnet-supervisor-live.service ActiveState)" = "active" ]; then
  fail "legacy supervisor service is active; do not install/cut over now"
else
  pass "legacy supervisor service is not active"
fi

for unit in "${MERIDIAN_UNITS[@]}"; do
  load_state="$(unit_field "$unit" LoadState)"
  active_state="$(unit_field "$unit" ActiveState)"
  unit_file_state="$(unit_field "$unit" UnitFileState)"
  printf '%s LoadState=%s ActiveState=%s UnitFileState=%s\n' \
    "$unit" "$load_state" "$active_state" "$unit_file_state"
  if [ "$EXPECT_INSTALLED" -eq 1 ] && [ "$load_state" != "loaded" ]; then
    fail "$unit is not installed/loaded"
  fi
  if [ "$active_state" = "active" ]; then
    fail "$unit is active; disabled proof requires inactive units"
  fi
  if [ "$unit_file_state" = "enabled" ]; then
    fail "$unit is enabled; disabled proof requires disabled units"
  fi
done

if [ "$failures" -eq 0 ]; then
  pass "disabled Meridian unit verification passed; no state was changed"
  exit 0
fi

fail "disabled Meridian unit verification failed with $failures blocker(s); no state was changed"
exit 1
