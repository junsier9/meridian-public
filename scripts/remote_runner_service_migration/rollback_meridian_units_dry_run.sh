#!/usr/bin/env bash
set -u

EXECUTE=0
CONFIRM=""
LEGACY_BACKUP_DIR=""
REQUIRED_CONFIRMATION="ROLLBACK_MERIDIAN_REMOTE_RUNNER_SERVICE_NAMES"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --confirm)
      CONFIRM="${2:?missing value for --confirm}"
      shift 2
      ;;
    --legacy-unit-backup-dir)
      LEGACY_BACKUP_DIR="${2:?missing value for --legacy-unit-backup-dir}"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: bash rollback_meridian_units_dry_run.sh [--execute --confirm ROLLBACK_MERIDIAN_REMOTE_RUNNER_SERVICE_NAMES] [--legacy-unit-backup-dir DIR]

Default mode is dry-run. Execute mode stops/disables Meridian timers, optionally
restores legacy unit files from a backup directory, reloads systemd, and starts
the legacy health and supervisor timers.
USAGE
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

MERIDIAN_TIMERS=(
  "meridian-alpha-mainnet-supervisor-live.timer"
  "meridian-alpha-mainnet-health-monitor.timer"
)

LEGACY_TIMERS=(
  "enhengclaw-mainnet-health-monitor.timer"
  "enhengclaw-mainnet-supervisor-live.timer"
)

LEGACY_UNITS=(
  "enhengclaw-mainnet-supervisor-live.service"
  "enhengclaw-mainnet-supervisor-live.timer"
  "enhengclaw-mainnet-health-monitor.service"
  "enhengclaw-mainnet-health-monitor.timer"
)

run() {
  printf '+ %s\n' "$*"
  if [ "$EXECUTE" -eq 1 ]; then
    "$@"
  fi
}

if [ "$EXECUTE" -eq 1 ] && [ "$CONFIRM" != "$REQUIRED_CONFIRMATION" ]; then
  echo "refusing execute mode without --confirm $REQUIRED_CONFIRMATION" >&2
  exit 2
fi

if [ "$EXECUTE" -eq 0 ]; then
  echo "DRY_RUN only. Add --execute --confirm $REQUIRED_CONFIRMATION during an approved rollback window."
fi

echo "Capture current state before rollback:"
run systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*' --no-pager
for unit in "${MERIDIAN_TIMERS[@]}" "${LEGACY_TIMERS[@]}"; do
  run systemctl status "$unit" --no-pager
done

echo "Stop and disable Meridian timers:"
for unit in "${MERIDIAN_TIMERS[@]}"; do
  run systemctl stop "$unit"
  run systemctl disable "$unit"
done

if [ -n "$LEGACY_BACKUP_DIR" ]; then
  echo "Restore legacy unit files from backup dir: $LEGACY_BACKUP_DIR"
  for unit in "${LEGACY_UNITS[@]}"; do
    src="$LEGACY_BACKUP_DIR/$unit"
    dst="/etc/systemd/system/$unit"
    if [ -f "$src" ]; then
      run install -m 0644 "$src" "$dst"
    else
      echo "WARN backup unit missing: $src"
    fi
  done
else
  echo "WARN no --legacy-unit-backup-dir supplied; legacy unit files will not be restored"
fi

run systemctl daemon-reload

echo "Enable and start legacy timers:"
for unit in "${LEGACY_TIMERS[@]}"; do
  run systemctl enable "$unit"
  run systemctl start "$unit"
done

echo "Rollback verification commands:"
run systemctl list-timers --all 'enhengclaw-mainnet*' 'meridian-alpha-mainnet*' --no-pager
for unit in "${MERIDIAN_TIMERS[@]}" "${LEGACY_TIMERS[@]}"; do
  run systemctl show "$unit" --no-pager -p Id -p LoadState -p ActiveState -p SubState -p UnitFileState -p Result
done

echo "Rollback script completed in dry-run=$((1 - EXECUTE)) mode."

