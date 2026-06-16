# Tardis Remote Research Platform Plan

`Status: implemented through Phase 6; M3.1 v0 report-only failed research-watch gate`
`Date: 2026-06-15`
`Scope: Tardis.dev historical research store plus Meridian alpha-research compute`
`Live impact: none`

## Decision

Move retained Tardis raw-history research from the failed workstation-attached
E-drive pattern to a two-server remote research platform:

- `meridian-compute-01`: OVH RISE-XL compute node for repo checkout, Python
  environment, hot staging, feature builders, report cards, and h10d
  report-only diagnostics.
- `meridian-store-01`: OVH storage node for raw Tardis vendor partitions,
  derived immutable panels, sync manifests, checksums, and backups.

This platform is for research data and report-only alpha validation. It does
not modify live runners, h10d active manifests, scheduler manifests, or any
live-order control plane.

## 2026-06-15 Execution Result

The remote research platform path completed through the M3.1 full backfill,
feature build, context report, and frozen report-only ablation, but the v0
overlay failed the research-watch gate.

Backfill and panel:

- raw backfill run id: `20260615T035231Z_tardis_backfill_20230401_20260613`;
- raw summary: `/tank/meridian/report_archive/factor_reports/20260615T035231Z_tardis_backfill_20230401_20260613/backfill_controller_summary.json`;
- backfill range: `2023-04-01` through `2026-06-13`;
- monthly shards: `39/39` succeeded;
- raw daily partitions: `1170`, failed partitions `0`, missing partitions `0`;
- feature run label: `2026-06-15-full-backfill-20230401-20260613`;
- final storage panel: `/tank/meridian/options_surface_feature_panels/2026-06-15-full-backfill-20230401-20260613/tardis_deribit_options_surface_features.csv`;
- final panel rows: `2340` (`1170` days x BTC/ETH).

Context report and ablation:

- context report: `/data/meridian/artifacts/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_context_report_card.json`;
- ablation summary: `/data/meridian/artifacts/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_ablation/summary.json`;
- storage copy of ablation summary: `/tank/meridian/report_archive/factor_reports/2026-06-15-full-backfill-20230401-20260613/compute_outputs/m3_1_options_surface_overlay_ablation/summary.json`.

Registered verdict:

```text
M3.1 overlay v0 report-only failed research-watch gate
```

`overlay_context_research_allowed=true` in the context report allowed only the
frozen report-only ablation. It is not overlay availability. The ablation sets
`research_watch_state_allowed=false` with blockers:

- `full_oos_cumulative_return_worse_than_baseline`;
- `full_oos_h10d_equivalent_sharpe_worse_than_baseline`;
- `exclude_first_30_context_dates_cumulative_return_worse_than_baseline`;
- `exclude_first_30_context_dates_h10d_sharpe_worse_than_baseline`.

No active h10d registry, active manifest, v1 admission policy, live runner,
timer, or scheduler mutation was authorized by this result.

## Current Observed Hardware

Observed from the operator installation screenshots on 2026-06-15:

| Host | Role | Public IP | OS | System disk state | Data disk state |
| --- | --- | --- | --- | --- | --- |
| `meridian-compute-01` | compute / hot stage | `198.51.100.30` | Ubuntu 24.04 LTS | `2 x 1.92 TB NVMe`, Linux software RAID1, `/` on `/dev/md3`, about `1.7T` usable | no separate data pool |
| `meridian-store-01` | raw archive / cold store | `198.51.100.31` | Ubuntu 24.04 LTS | `2 x 480 GB SSD`, Linux software RAID1, `/` on `/dev/md3`, about `437G` usable | `8 x 14 TB SAS` exposed as empty raw disks, about `12.7 TiB` each |

The second NIC on both servers is expected to remain down until OVH vRack and
host-side private addresses are configured.

## Source Contracts

The plan is anchored to the following current contracts:

- Tardis downloadable CSV datasets are daily gzip CSV files split by exchange,
  data type, and symbol.
- Tardis `options_chain` uses symbol `OPTIONS` and one daily file containing
  all options instruments for the exchange.
- OVH vRack is the intended private network between the compute and storage
  nodes once both servers are attached and configured.
- Meridian M3.1 options work remains report-only until the preregistered
  report card and ablation evidence pass.

References:

- Tardis downloadable CSV overview: <https://docs.tardis.dev/downloadable-csv-files/overview>
- Tardis downloadable CSV API: <https://docs.tardis.dev/downloadable-csv-files/api>
- Tardis data types, including `options_chain`: <https://docs.tardis.dev/downloadable-csv-files/data-types>
- OVH vRack dedicated-server guide: <https://docs.ovhcloud.com/en/guides/bare-metal-cloud/dedicated-servers/vrack-configuring-on-dedicated-server>

## Architecture

```text
Tardis.dev datasets API
        |
        | HTTPS, resumable daily partitions
        v
meridian-store-01
  /tank/tardis/raw/...                 raw vendor history
  /tank/tardis/manifests/...           checksums and sync reports
  /tank/meridian/backups/...           repo configs and retained reports
        |
        | rsync over vRack private IP, monthly/quarterly staging windows
        v
meridian-compute-01
  /data/meridian/repo                  Meridian checkout
  /data/meridian/venv                  Python environment
  /data/meridian/hot_stage             staged raw partitions for builders
  /data/meridian/artifacts             report cards and derived panels
        |
        v
M3.1 probe -> options_surface_features -> report card -> frozen-rule ablation
```

Key design rule: builders should not stream large research windows directly
from the storage server's HDD pool. Stage bounded monthly or quarterly raw
partitions to compute NVMe, run the builder locally, then sync sanitized
artifacts and manifests back to storage.

## Disk Layout

Storage server target:

```text
/tank
  tardis/
    raw/
      deribit/options_chain/YYYY/MM/DD/OPTIONS.csv.gz
      <future_exchange>/<future_data_type>/...
    manifests/
    derived/
  meridian/
    backups/
    report_archive/
    repo_snapshots/
```

Compute server target:

```text
/data/meridian
  repo/
  venv/
  hot_stage/
    tardis_deribit_options_chain/
  artifacts/
  logs/
  tmp/
```

The storage node should use ZFS on the `8 x 14 TB SAS` data disks. Default
target:

```text
pool: tank
layout: raidz2
mountpoint: /tank
compression: zstd
atime: off
recordsize: 1M for raw gzip datasets
```

RAIDZ2 gives capacity for the first multi-exchange intraday research stage
while preserving two-disk fault tolerance. The OS SSD RAID1 array must stay
separate from the `/tank` pool.

## Security And Secrets

Rules:

- Keep the Tardis API key out of git, logs, shell history, reports, and store
  manifests.
- Store the key only as a host environment secret or systemd credential on the
  node that runs downloader jobs.
- Use a non-root `meridian` user for research operations.
- Keep public SSH open only as needed; use vRack private IPs for compute-store
  rsync once private networking is configured.
- Do not expose `/tank` via public NFS or unauthenticated services.

Initial host convention:

```bash
sudo adduser meridian
sudo usermod -aG sudo meridian
sudo install -d -o meridian -g meridian /data/meridian
sudo install -d -o meridian -g meridian /tank/tardis /tank/meridian
```

Tardis key convention:

```bash
# set outside repo, for interactive sessions only
export TARDIS_API_KEY='<redacted>'
export Tardis_api_key="$TARDIS_API_KEY"
```

For scheduled jobs, prefer an environment file owned by root and readable only
by root:

```text
/etc/meridian/tardis.env
```

with permissions:

```bash
sudo chown root:root /etc/meridian/tardis.env
sudo chmod 600 /etc/meridian/tardis.env
```

## Implementation Phases

### Phase 0 - Host Audit

Goal: prove both servers are clean and correctly installed before any raw
vendor retention.

Run on both hosts:

```bash
hostnamectl
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL,SERIAL
df -hT
cat /proc/mdstat
ip -br addr
```

Run on `meridian-store-01` before pool creation:

```bash
sudo apt update
sudo apt install -y zfsutils-linux smartmontools nvme-cli
for d in /dev/sdb /dev/sdc /dev/sdd /dev/sde /dev/sdf /dev/sdh /dev/sdi /dev/sdj; do
  echo "===== $d ====="
  sudo smartctl -H -i "$d"
done
ls -l /dev/disk/by-id/ | grep -E 'WUH721414|Micron|ata-|scsi-'
```

Acceptance:

- compute OS RAID1 healthy;
- store OS RAID1 healthy;
- exactly eight unused HDD data disks visible on storage;
- SMART health passes for all eight HDDs;
- no Tardis downloads have run.

### Phase 1 - Storage Pool

Goal: create `/tank` once, using stable disk IDs.

Commands must use `/dev/disk/by-id/...` paths, not volatile `/dev/sdX` names.
Representative shape:

```bash
sudo zpool create \
  -o ashift=12 \
  -O compression=zstd \
  -O atime=off \
  -O xattr=sa \
  -O acltype=posixacl \
  -O mountpoint=/tank \
  tank raidz2 \
  /dev/disk/by-id/<disk-1> \
  /dev/disk/by-id/<disk-2> \
  /dev/disk/by-id/<disk-3> \
  /dev/disk/by-id/<disk-4> \
  /dev/disk/by-id/<disk-5> \
  /dev/disk/by-id/<disk-6> \
  /dev/disk/by-id/<disk-7> \
  /dev/disk/by-id/<disk-8>
sudo zfs create -o recordsize=1M tank/tardis
sudo zfs create -o recordsize=1M tank/tardis/raw
sudo zfs create tank/tardis/manifests
sudo zfs create tank/tardis/derived
sudo zfs create tank/meridian
sudo zfs create tank/meridian/backups
sudo zpool status tank
```

Acceptance:

- `zpool status tank` is `ONLINE`;
- `/tank/tardis/raw` is mounted;
- `zfs get compression,recordsize,atime tank/tardis/raw` matches the target;
- no raw Tardis partitions are present yet.

### Phase 2 - vRack Private Path

Goal: keep compute-store transfers off the public Internet.

Target private addressing:

```text
meridian-compute-01 vRack IP: 198.51.100.10/24
meridian-store-01   vRack IP: 198.51.100.20/24
```

Acceptance:

- both servers are attached to the same OVH vRack;
- private NIC is up on both hosts;
- `ping 198.51.100.20` from compute works;
- `ping 198.51.100.10` from storage works;
- rsync over private IP works with SSH key auth;
- public-IP rsync is not used for normal research data movement.

### Phase 3 - Repo And Python Environment

Goal: make compute the only node that runs Meridian feature builders and
report-only alpha diagnostics.

On compute:

```bash
sudo apt install -y git python3.12-venv python3-pip build-essential rsync jq
sudo -iu meridian
mkdir -p /data/meridian/{repo,venv,hot_stage,artifacts,logs,tmp}
```

Repo deployment should use the same branch/commit intended for the current
research run. Environment variables should point outside the checkout:

```bash
export MERIDIAN_TARDIS_RAW_STORE=/data/meridian/hot_stage/tardis_deribit_options_chain
export MERIDIAN_ARTIFACT_ROOT=/data/meridian/artifacts
```

Acceptance:

- `pytest tests/test_quant_tardis_deribit_options_probe.py tests/test_quant_options_surface.py` passes on compute;
- the Tardis API key is visible to probe jobs without printing the key;
- repo-local `artifacts/` is not used as the long-term raw store.

### Phase 4 - Tardis Smoke Download

Goal: prove access, schema, file layout, and store write permissions with a
small sample before backfill.

Use the existing read-only probe first. Then run the raw store helper for one
or two dates with explicit raw-retention confirmation, writing to storage:

```bash
python scripts/quant_research/provider_leaf_sync_helpers/sync_tardis_deribit_options_chain_history.py \
  --as-of 2026-06-15 \
  --from-date 2026-06-10 \
  --to-date 2026-06-11 \
  --external-root /tank/tardis/raw_stores/tardis_deribit_options_chain \
  --execute \
  --confirm-retain-raw-vendor-data I_UNDERSTAND_RAW_TARDIS_OPTIONS_CHAIN_WILL_BE_RETAINED \
  --summary-only
```

Acceptance:

- store summary success is true;
- daily partitions exist under the expected layout;
- manifest is written;
- no key material is present in summary or manifest;
- a one-day builder run can consume the staged data and produce F56-F60 fields.

### Phase 5 - Backfill

Goal: cover the M3.1 research interval without destabilizing the hosts.

Backfill priority:

1. `2023-04-01` through `2026-06-13`.
2. If capacity and runtime are healthy, extend backward to Tardis subscription
   start `2022-06-11`.
3. After M3.1 is green, expand to intraday multi-exchange datasets by research
   priority, not by downloading everything available.

Operational policy:

- download in monthly shards;
- keep per-shard summaries;
- allow resume by skipping existing partitions;
- hash files as they arrive;
- monitor `zpool status`, disk SMART, free space, and failed partition count;
- do not run full backfill and heavy builder jobs simultaneously.

Acceptance:

- monthly shard success is true;
- failed partitions are zero or explicitly re-run;
- manifest date coverage matches the target interval;
- free space remains above the operating floor selected by the owner;
- raw store remains outside the repo.

### Phase 6 - Feature Build And M3.1 Report-Only Validation

Goal: rebuild options-surface features from the remote raw store without
changing F56-F60 definitions or active h10d manifests.

Flow:

1. Stage one month or quarter from storage to compute:

```bash
rsync -a --info=progress2 \
  meridian@198.51.100.20:/tank/tardis/raw_stores/tardis_deribit_options_chain/ \
  /data/meridian/hot_stage/tardis_deribit_options_chain/
```

2. Run `build_tardis_deribit_options_surface_features.py` with the staged raw
   store and formal OHLCV realized-vol join.
3. Run `compute_options_surface_overlay_context_report.py`.
4. Run the preregistered frozen-rule ablation runner.
5. Sync reports and derived panels back to storage.

Acceptance:

- F57-F60 train/test ready coverage is sufficient in the report card;
- F56 remains diagnostic only for the v0 overlay;
- frozen-rule ablation report is green;
- active manifests are unchanged;
- all artifacts are tied to command, date range, repo commit, and raw-store
  manifest.

Actual 2026-06-15 outcome: the platform and full panel path completed, but the
frozen-rule v0 ablation was not green. Treat the result as `M3.1 overlay v0
report-only failed research-watch gate`.

## Research Admission Boundaries

Allowed on this platform:

- Tardis access probes;
- raw store backfills;
- feature-panel builds;
- report-card generation;
- report-only frozen-rule ablations;
- multi-exchange intraday exploratory coverage reports.

Forbidden without a later explicit owner gate:

- modifying `config/quant_research/active_h10d_registry.json`;
- modifying active h10d manifests;
- adding F56-F60 to score-layer admission allowlists;
- changing live, timer, remote-runner, or OpenClaw execution config;
- treating raw data coverage as alpha evidence by itself;
- using downloaded data without point-in-time coverage and schema reports.

## Capacity Policy

The `8 x 14 TB` storage node is sufficient for:

- Deribit options-chain raw history for M3.1;
- first-stage multi-exchange intraday research for selected venues and symbols;
- derived daily and intraday feature panels.

It is not a license to download every Tardis dataset indiscriminately. For
multi-exchange intraday expansion, each new dataset family needs a short
coverage and storage report before bulk retention. Default priority:

1. Deribit `options_chain` for M3.1 F56-F60.
2. Core derivatives venues for top symbols: trades, incremental L2, derivative
   ticker, liquidations.
3. Derived 1s/5s/1m book features from incremental L2, rather than retaining
   redundant full snapshot families everywhere.
4. Wider symbol coverage only after the first alpha report cards show value.

## Immediate Checklist

1. Finish storage-node SMART and by-id audit.
2. Create `/tank` ZFS RAIDZ2 using stable disk IDs.
3. Create `meridian` user and directory ownership on both hosts.
4. Attach both servers to OVH vRack and configure `198.51.100.10/24` and
   `198.51.100.20/24`.
5. Clone Meridian onto compute and install the Python environment.
6. Configure Tardis key on the storage/download host without printing it.
7. Run the Tardis Phase 0 probe.
8. Run a two-day raw-store smoke sync.
9. Stage smoke partitions to compute and run the builder.
10. Only after the smoke path is green, start monthly backfill.

## Completion Definition

This infrastructure plan is complete when:

- `/tank` is online and healthy;
- compute can rsync from storage over vRack;
- Tardis Phase 0 probe is green;
- a smoke raw-store sync writes the expected manifest;
- a smoke builder run produces F56-F60 with formal F57 RV/OHLCV join;
- the M3.1 report card and frozen ablation can be run from remote-store data;
- no active h10d or live manifest has changed.
