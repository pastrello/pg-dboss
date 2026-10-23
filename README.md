# DBOSS — Database Optimized Operating System

Research-stage PostgreSQL 18 observability and Linux/OpenZFS intelligence, with
the proven PG Intelligence 0.1.8 monitoring agent preserved.

**Safety:** DBOSS monitoring is read-only on the monitored database.
Legacy PG Intelligence's explicit bootstrap/migrate operations still change
only its own telemetry/monitoring infrastructure. DBOSS does not automatically
tune PostgreSQL, ZFS or the kernel.

## Architecture

- `dbos/`: DBOS 0.2.1 host/ZFS/PostgreSQL 18 snapshot and interval analyzer.
- `pgintel/`: unmodified PG Intelligence 0.1.8 continuous data collection,
  PostgreSQL repository and original compatibility with PostgreSQL 13–18.
- `dboss/`: unified command routing (no new daemon or telemetry schema yet).
- `crates/dboss-agent/`: experimental read-only Rust Linux host metrics probe.

## Quickstart (safe tests)

```bash
git clone https://github.com/pastrello/pg-dboss.git
cd pg-dboss
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
./install.sh
dboss --help
dboss probe --output sample.json
dboss monitor -c /etc/pgintel/pgintel.ini check
```

`./install.sh` runs unit tests only, does not require root, and does not touch
any DB/ZFS configuration. To install an isolated CLI in /opt/dboss:
`sudo ./install.sh --install`. This **does not enable systemd** or change
legacy PG Intelligence. The old `install-rocky.sh` remains available; its
setup/bootstrap path requires `sudo ./install.sh --legacy-configure`.

## CLI

```bash
dboss host --output host.json
dboss postgres --output postgres.json
dboss probe --output sample.json
dboss analyze --before a.json --after b.json --output interval.json
dboss monitor -c /etc/pgintel/pgintel.ini health --hours 24
# Preserved:
pgintel -c /etc/pgintel/pgintel.ini check
dbos --help
```

See [architecture](docs/ARCHITECTURE.md),
[project state](docs/PROJECT-STATE.md), and
[Rust design](docs/RUST-STRATEGY.md).

## Compatibility and release gates

PG18 is the target for new features. Legacy PG Intelligence capabilities in
PG13–17 remain supported, but no new DBOSS automatic tuning is planned there.
No cluster migrations, PostgreSQL configuration rewrites, systemd swaps or
repository schema migrations occur as part of this code integration.

This repository retains the original PG Intelligence Git history and
`pgintel` source paths. The prior DBOS code is imported from its tested 0.2.1
prototype rather than rewritten.

The original PG Intelligence repository did not declare an explicit license in
its inspected source tree. Do not assume all components are Apache-2.0; review
license provenance before distributing composite packages.
