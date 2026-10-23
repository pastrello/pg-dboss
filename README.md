# DBOSS — Database Optimized Operating System

One observability tool for PostgreSQL, Linux and OpenZFS, consolidating
DBOS Intelligence 0.2.1 and PG Intelligence 0.1.8.

**One scheduled SQL collector, no duplicate PostgreSQL polling.**
The production-tested PGIntel scheduler remains the authoritative telemetry
engine. DBOSS adds Linux/ZFS snapshots on the same schedule via a hook.

## Install and offline tests

```bash
git clone https://github.com/pastrello/pg-dboss.git
cd pg-dboss
./install.sh
.venv/bin/dboss --help
```

`./install.sh` creates the local virtualenv and runs offline tests.
Use `./install.sh --doctor` and `./install.sh --self-test` for diagnostics.
The explicit `sudo ./install.sh --install` installs the isolated DBOSS CLI
under `/opt/dboss` without changing the old PGIntel service.
`sudo ./install.sh --legacy-configure` invokes the historical PGIntel
bootstrap **only when intentionally requested**.

## Unified commands

```bash
# Config uses the existing /etc/pgintel/pgintel.ini format.
# The application DB is observed read-only; PGIntel repository gets writes.
dboss collect -c /etc/pgintel/pgintel.ini --host-dir ~/.local/state/dboss/host

# A single continuous process; PGIntel runs SQL, DBOSS adds host/ZFS
# every 300 seconds (and keeps up to 288 private JSON files).
dboss run -c /etc/pgintel/pgintel.ini --host-interval 300

# Ad-hoc DBOS PG18-only diagnostics (never scheduled by dboss run):
dboss host --output host.json
dboss probe --output sample.json
dboss analyze --before sample-a.json --after sample-b.json

# Existing PGIntel maintenance commands remain reachable:
dboss monitor -c /etc/pgintel/pgintel.ini report --hours 24
pgintel -c /etc/pgintel/pgintel.ini health --hours 24
```

**Never run the old `pgintel` daemon and `dboss run` together** against
the same configured instance: that would cause redundant SQL sampling.
No systemd service is enabled or replaced automatically.

The host-history directory must be owned by the executing user and be
private (mode 0700). Each JSON report is created mode 0600. It may expose
internal mounts and should not be committed or uploaded unredacted.

## Architecture / support

- PGIntel FAST/SLOW/SIZE, repository SQL/schema, `pgintel` CLI, and legacy
  installation stay operational on PostgreSQL 13–18.
- DBOS PG18 collectors remain for explicit diagnosis and offline deltas,
  not for a competing second SQL monitoring daemon.
- Rust host agent in `crates/dboss-agent` stays a research experiment,
  not an active second collector. Replace Python only after measured parity.
- No automatic `pg_prewarm`, cache policy, index changes or ZFS tuning.

See `docs/ARCHITECTURE.md`, `docs/PROJECT-STATE.md`,
`docs/RUST-STRATEGY.md`, `AGENTS.md` and
`docs/PG-INTELLIGENCE-ORIGINAL.md` (original README archived).

## Smart Cache Advisor (experimental, offline only)

```bash
dboss advise --interval interval.json --output advice.json
# For two non-overlapping intervals FROM THE SAME INSTANCE ONLY:
dboss advise --interval day1.json --interval day2.json \
  --assume-same-source --output advice-two-days.json
```

Advisor reads existing `dboss analyze` interval JSON; it does **not**
query PostgreSQL or perform any prewarm, index removal or cache changes.
Review flags are rule-based (>=1000 missed shared-buffer blocks plus hit
ratio below 90%) and preliminary, not proof of physical disk I/O or bad
PostgreSQL configuration. It has **no object-size or block-residency data**.
Do not blindly implement its suggestions. The `--assume-same-source` flag
requires operator verification of instance continuity across intervals.
