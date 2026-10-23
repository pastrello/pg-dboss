# DBOSS — Database Optimized Operating System

Experimental unified project combining PostgreSQL 18 / Linux / OpenZFS
observability (DBOS 0.2.1) and continuous telemetry/historical analysis
(PG Intelligence 0.1.8).

**No monitored database or ZFS tuning is applied automatically.**

## Components
- `dbos/`: original DBOS 0.2.1 snapshots, PG18 stats and offline delta analysis.
- `pgintel/`: preserved PG Intelligence 0.1.8 source, SQL migrations,
  compatible monitor for PG13–18 and historical telemetry repository.
- `dboss/`: unified CLI dispatcher.
- `crates/dboss-agent/`: optional read-only Linux/ZFS prototype in Rust.

## Rocky Linux 8/9/10 — setup and tests (recommended)

```bash
git clone -b feature/dboss-consolidation https://github.com/pastrello/pg-dboss.git
cd pg-dboss
./install.sh
.venv/bin/dboss --version
.venv/bin/dboss host --output host.json
```

Running `./install.sh` creates a **local** Python virtual environment,
installs package dependencies and runs offline unit tests; it requires
internet package access on first use. No root, PostgreSQL object change or
service enablement is needed. Python >=3.9 is required.
`DBOSS_PYTHON=python3.12 ./install.sh` selects the interpreter.

Additional commands:

```bash
./install.sh --self-test
./install.sh --doctor
sudo ./install.sh --install
/opt/dboss/venv/bin/dboss --help
```

`--install` creates an **isolated DBOSS** environment under /opt/dboss
and **does not replace** the older /opt/pg-intelligence installation or
`pgintel.service`. The original PG Intelligence installer
`install-rocky.sh` is retained for compatibility; opt-in setup:
`sudo ./install.sh --legacy-configure`. It can create PG Intelligence's
monitoring/repository objects, so read its safety documentation first.

## Unified commands

```bash
.venv/bin/dboss host --output host.json
.venv/bin/dboss postgres --output postgres.json
.venv/bin/dboss probe --output sample.json
.venv/bin/dboss analyze --before a.json --after b.json --output interval.json
.venv/bin/dboss monitor -c /etc/pgintel/pgintel.ini check
.venv/bin/dboss monitor -c /etc/pgintel/pgintel.ini health --hours 24
```

The `dbos` and `pgintel` CLIs remain available.
DBOS PostgreSQL collection uses libpq's PGSERVICE/PGPASSFILE mechanisms
and requires PostgreSQL 18. PG Intelligence retains PG13–18 compatibility.

## Development, safety and licensing
- [Architecture](docs/ARCHITECTURE.md)
- [Project state](docs/PROJECT-STATE.md)
- [Rust evaluation](docs/RUST-STRATEGY.md)
- [Original PG Intelligence README](docs/PG-INTELLIGENCE-ORIGINAL.md)
- [ADR-001 unification](docs/decisions/ADR-001-unification.md)

Release gate: successful CI plus PG18/ZFS validation on Rocky; no automatic
kernel/ARC/prewarm/DDL changes.

For compatibility with the existing PG Intelligence installer/tests, the
Python distribution metadata remains `pg-intelligence==0.1.8` during
transition. Product CLI uses `dboss 0.1.0`.
The original PG Intelligence source has no explicit LICENSE in the inspected
repository: resolve legal provenance before wider redistribution.
