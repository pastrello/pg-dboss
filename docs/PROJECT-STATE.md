# DBOSS — Project State

Updated: 2026-10-23

## Source of truth

- Repository: https://github.com/pastrello/pg-dboss
- Main: PR #5 merged (DBOS 0.2.1 + PG Intelligence 0.1.8).
- This change: unified observer on `feature/dboss-unified-observer`.

## What works

- PGIntel scheduler retained: one SQL collection engine with FAST 60s,
  SLOW 15min and SIZE 60min collection classes (configurable).
- `dboss run` binds one host/ZFS observer to the existing PGIntel
  scheduler, default 300s. No extra recurring PostgreSQL queries.
- `dboss collect`: single PGIntel collection and one host snapshot.
- Host observations are 0600 JSON in a 0700 local directory, retained
  up to 288 files. Does not include raw queries or DSNs.
- `dboss host/postgres/probe/inspect/analyze` continue as explicit
  on-demand DBOS PG18 diagnostics; `dboss monitor` is compatibility only.
- Rust host agent is experimental/research-only, never auto-enabled.
- `install.sh` remains the single entry point for local install/test,
  doctor, isolated system installation; legacy installer stays opt-in.
- PGIntel 13–18 source support remains unchanged.

## Not implemented / known risks

- DBOSS local host JSON is not yet joined into PGIntel repository tables.
- No automatic cache tuning or Smart Cache Advisor execution.
- No auto systemd migration. Existing `pgintel.service` stays intact.
- Operators **must not** run `pgintel run` and `dboss run` at the same time
  for the same source/repository instance; both would collect SQL.
- Test on Rocky 8/9/10 and PG18+ZFS with repository configured before
  enabling a continuous service. Confirm user/permissions and measured
  observer overhead. Python-to-Rust transition requires feature parity,
  benchmarks and rollback; Rust does not yet replace PostgreSQL collector.

## Safety

Do not alter monitored application DB, roles, indexes, PGDATA, PostgreSQL
configuration, ZFS datasets, system kernel or live systemd services.
Historical telemetry repository writes still occur when `collect` or
`run` is invoked. User must explicitly choose these commands.
