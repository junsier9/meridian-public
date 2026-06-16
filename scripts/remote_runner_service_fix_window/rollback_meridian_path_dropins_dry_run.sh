#!/usr/bin/env bash
set -u

EXECUTE=0
CONFIRM=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --confirm)
      CONFIRM=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: bash rollback_meridian_path_dropins_dry_run.sh [--execute --confirm]

Dry-run rollback helper for the Meridian path/config-resolution fix window.
Execute mode is refused unless --confirm is present and
ROLLBACK_MERIDIAN_PATH_FIX_WINDOW=confirm-remove-dropins is set.
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
  "/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.service.d/10-meridian-path.conf"
  "/etc/systemd/system/meridian-alpha-mainnet-health-monitor.service.d/10-meridian-path.conf"
)

echo "Meridian path/config-resolution drop-in rollback plan"
for path in "${DROPINS[@]}"; do
  echo "remove-if-present: $path"
done
echo "then run: systemctl daemon-reload"
echo "then run: systemctl reset-failed meridian-alpha-mainnet-supervisor-live.service meridian-alpha-mainnet-health-monitor.service"
echo "then verify timers remain disabled/inactive and open orders remain zero"

if [ "$EXECUTE" -ne 1 ]; then
  echo "dry run only; no state changed"
  exit 0
fi

if [ "$CONFIRM" -ne 1 ] || [ "${ROLLBACK_MERIDIAN_PATH_FIX_WINDOW:-}" != "confirm-remove-dropins" ]; then
  echo "refusing execute mode without --confirm and ROLLBACK_MERIDIAN_PATH_FIX_WINDOW=confirm-remove-dropins" >&2
  exit 2
fi

for path in "${DROPINS[@]}"; do
  if [ -f "$path" ]; then
    rm -f -- "$path"
  fi
done
systemctl daemon-reload
systemctl reset-failed meridian-alpha-mainnet-supervisor-live.service meridian-alpha-mainnet-health-monitor.service || true
echo "rollback drop-in removal completed"
