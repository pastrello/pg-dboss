# DBOSS — Project State
Updated: 2026-10-23

## Repository
pastrello/pg-dboss: renamed PG Intelligence repository, Git history retained.
Target branch for integration: feature/dboss-consolidation. No automatic main
merge; PR must pass CI and review before adoption.

## Baseline
- PG Intelligence existing 0.1.8 sources in pgintel/, install-rocky.sh,
  pgintel.service, sql/ and tests/ preserved.
- DBOS 0.2.1 Python snapshot/analysis component integrated in dbos/.
- DBOSS wrapper: dboss/ with host/postgres/probe/inspect/analyze/monitor.
- install.sh: one entry point, default safe self-test, explicit isolated
  venv install, explicit opt-in to old guided bootstrap.
- Experimental Rust host-only collector at crates/dboss-agent.
- PostgreSQL 18 for new features; legacy PG13–17 telemetry preserved.
- No changes to monitored PGDATA, indexes, GUCs, pools, systemd units.

## Still pending
- CI and real PG18/ZFS integration test on Rocky Linux.
- Common PGIntel / DBOS timeseries schema and scheduler; existing PGIntel
  repository remains authoritative for historical samples.
- Host identity / ARC PG-specific attribution and intelligent cache advisor.
- Rust parity benchmarks and proper packaging of Rust binary as an optional
  component. Do not replace PGIntel agent yet.
- Rollback test and signed release packaging.

## Install & safety
Run ./install.sh (tests); ./install.sh --doctor (inspect); 
sudo ./install.sh --install (isolated CLI only).
Existing pgintel service is unchanged; avoid double collectors in production.
