#!/usr/bin/env bash
# Deploy the frontier + governance-gates + stage_4 governance stack to the remote host
# via tar-over-ssh (direct local->host; NO third-party hosting). D-1 Option B (repo is the
# governance authority) + D-2 (rsync-equivalent; rsync is unavailable on the Windows box).
#
# SAFETY: default is DRY-RUN (lists what would transfer, makes NO changes). Set EXECUTE=1 to
# apply. This script NEVER arms live_delta, submits orders, or enables timers. It DOES protect
# the owner-approved live scorer state: strategy.frontier.enabled must remain true and
# universe_policy.live_selection_mode must remain pit_rolling with an admitted candidate pool.
# trading_enabled stays false; timers stay disabled. It preserves the host runtime state
# (artifacts/live_trading, incl. the live SQLite) by excluding it from the transfer.
set -uo pipefail

HOST="${HOST:-root@203.0.113.10}"
REMOTE_REPO="${REMOTE_REPO:-/root/meridian_alpha_live_runner/repo}"
VENV_PY="${VENV_PY:-/root/meridian_alpha_live_runner/venv/bin/python}"
SSH_BIN="${SSH_BIN:-ssh}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new"
EXECUTE="${EXECUTE:-0}"   # 0 = dry-run (default), 1 = apply
LOCAL_PY="${LOCAL_PY:-}"

cd "$(git rev-parse --show-toplevel)"
COMMIT="$(git rev-parse HEAD)"

if [[ -z "$LOCAL_PY" ]]; then
  if command -v python >/dev/null 2>&1; then
    LOCAL_PY="python"
  elif command -v python3 >/dev/null 2>&1; then
    LOCAL_PY="python3"
  elif command -v py >/dev/null 2>&1; then
    LOCAL_PY="py -3"
  else
    echo "ERROR: no local Python found for live-config validation (tried python, python3, py -3)" >&2
    exit 1
  fi
fi
LOCAL_PY_CMD=($LOCAL_PY)

# Tracked code/config/contracts/docs + untracked governance evidence (D-1 provenance).
# EXCLUDES host runtime state + local-only dirs.
PATHS=(src scripts config docs/live_trading artifacts/governance)
TAR_EXCLUDES=(
  --exclude='.git' --exclude='.venv' --exclude='venv' --exclude='__pycache__'
  --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.mypy_cache'
  --exclude='.claude' --exclude='.env' --exclude='artifacts/live_trading'
)

# The host LOADS config/live_trading/<name>; the ported source lives under the migration
# staging dir. Map it explicitly after extract (the overlay alone would not place it).
SRC_REMOTE_RUNNER="scripts/remote_runner_service_migration/config/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml"
DST_REMOTE_RUNNER="config/live_trading/hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_meridian_remote_runner.yaml"
LIVE_CONFIG_VALIDATOR="scripts/deploy/validate_owner_approved_live_config.py"

echo "== Deploy plan =="
echo "host=$HOST  repo=$REMOTE_REPO  commit=$COMMIT  EXECUTE=$EXECUTE  ssh=$SSH_BIN"
echo "paths: ${PATHS[*]}"
echo "excludes: artifacts/live_trading (host SQLite/state preserved), .git/.venv/.env/__pycache__/.claude"
echo "== Validate owner-approved live config state locally =="
"${LOCAL_PY_CMD[@]}" "$LIVE_CONFIG_VALIDATOR" --config "$SRC_REMOTE_RUNNER" || exit 1

if [[ "$EXECUTE" != "1" ]]; then
  echo "== DRY-RUN (no changes). Per-path file counts that WOULD transfer: =="
  for p in "${PATHS[@]}"; do
    [[ -e "$p" ]] || { echo "  $p: (absent locally)"; continue; }
    cnt=$(tar "${TAR_EXCLUDES[@]}" -cf - "$p" 2>/dev/null | tar -tf - 2>/dev/null | wc -l)
    echo "  $p: files=$cnt"
  done
  echo "== DRY-RUN: would then validate + map  $SRC_REMOTE_RUNNER  ->  $DST_REMOTE_RUNNER  on host =="
  echo "== DRY-RUN: would write DEPLOYED_COMMIT=$COMMIT, run read-only active-frontier smoke, leave timers disabled. =="
  echo "== DRY-RUN done. Re-run with EXECUTE=1 to apply (backs up host first). =="
  exit 0
fi

set -e
TS="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_REMOTE_RUNNER="${DST_REMOTE_RUNNER}.tmp_${TS}"
echo "== [1/5] Backup the host dirs we overwrite (compressed, excludes artifacts) =="
"$SSH_BIN" $SSH_OPTS "$HOST" "cd '$REMOTE_REPO' && tar czf '../repo_backup_${TS}.tgz' src scripts config docs 2>/dev/null; ls -lh '../repo_backup_${TS}.tgz'"

echo "== [2/5] Transfer stack via tar-over-ssh =="
tar "${TAR_EXCLUDES[@]}" -cf - "${PATHS[@]}" | "$SSH_BIN" $SSH_OPTS "$HOST" "tar -xf - -C '$REMOTE_REPO'"

echo "== [3/5] Validate on-host source + map live-loaded config + write DEPLOYED_COMMIT =="
"$SSH_BIN" $SSH_OPTS "$HOST" "cd '$REMOTE_REPO' && \
  '$VENV_PY' '$LIVE_CONFIG_VALIDATOR' --config '$SRC_REMOTE_RUNNER' >/dev/null && \
  cp -f '$REMOTE_REPO/$SRC_REMOTE_RUNNER' '$REMOTE_REPO/$TMP_REMOTE_RUNNER' && \
  '$VENV_PY' '$LIVE_CONFIG_VALIDATOR' --config '$TMP_REMOTE_RUNNER' >/dev/null && \
  mv -f '$REMOTE_REPO/$TMP_REMOTE_RUNNER' '$REMOTE_REPO/$DST_REMOTE_RUNNER' && \
  '$VENV_PY' '$LIVE_CONFIG_VALIDATOR' --config '$DST_REMOTE_RUNNER' >/dev/null && \
  { echo '$COMMIT'; date -u; } > '$REMOTE_REPO/DEPLOYED_COMMIT'"

echo "== [4/5] On-host read-only smoke (no arm, no orders) =="
"$SSH_BIN" $SSH_OPTS "$HOST" "cd '$REMOTE_REPO' && \
  '$VENV_PY' -m compileall -q src/enhengclaw/live_trading/frozen_frontier_live.py src/enhengclaw/live_trading/mainnet_rebalance_plan_runner.py scripts/governance/run_frontier_contract_governance_gate.py '$LIVE_CONFIG_VALIDATOR' && \
  '$VENV_PY' '$LIVE_CONFIG_VALIDATOR' --config '$DST_REMOTE_RUNNER' && \
  '$VENV_PY' -c \"import sys,yaml;sys.path.insert(0,'src');from enhengclaw.live_trading.frozen_frontier_live import resolve_frontier_live_plan;p=yaml.safe_load(open('$DST_REMOTE_RUNNER'));r=resolve_frontier_live_plan(p, operator_state={'paused': False});print('resolve live ->', r.status, 'enabled=', r.enabled, 'overlay=', r.overlay_enabled, 'blockers=', r.blockers)\" && \
  '$VENV_PY' scripts/governance/run_frontier_contract_governance_gate.py --host-config '$DST_REMOTE_RUNNER' --output-root artifacts/_deploy_smoke >/dev/null && \
  '$VENV_PY' -c \"import json;s=json.load(open('artifacts/_deploy_smoke/summary.json'));print('frontier_gov_gate:', s['status'], 'carry_forward_absent=', s['carry_forward_absent'], 'blockers=', s['blockers'])\"; \
  rm -rf artifacts/_deploy_smoke"

echo "== [5/5] Verify governance stage + safety posture (read-only) =="
"$SSH_BIN" $SSH_OPTS "$HOST" "cd '$REMOTE_REPO' && \
  python3 -c \"import json;print('host current_stage =', json.load(open('config/project_governance/project_profile.json'))['current_stage'])\" && \
  '$VENV_PY' -c \"import yaml;c=yaml.safe_load(open('$DST_REMOTE_RUNNER'));print('remote_runner frontier.enabled =', c['strategy']['frontier']['enabled']);print('remote_runner live_selection_mode =', c['universe_policy']['live_selection_mode']);print('remote_runner candidate_symbols =', len(c['universe_policy']['candidate_symbols']))\" && \
  echo \"timer_enabled = \$(systemctl is-enabled meridian-alpha-mainnet-supervisor-live.timer 2>/dev/null) (should be disabled)\""

echo "== DONE. Stack deployed; owner-approved 12-factor frontier state preserved; timers disabled; nothing armed. =="
echo "== Next (owner): fresh gates/plan-only before any separate arm or timer action. =="
