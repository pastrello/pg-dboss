# DBOSS — unified telemetry architecture

## Runtime rule: exactly one scheduled PostgreSQL collector

The PG Intelligence 0.1.8 scheduler is the **only** continuous SQL polling
engine. DBOSS uses `pgintel.agent.run_forever` with an optional per-cycle host
observer callback. It does not run `dbos.collect_postgres` in the daemon.
The callback runs even when the PGIntel source collection fails; callback errors
are isolated and do not stop PostgreSQL monitoring.

```text
                        dboss run -c pgintel.ini
                                  |
                       PGIntel scheduler (one)
                           /              \
                     PostgreSQL        Host observer
                     FAST/SLOW/SIZE    every 300s
                           |               |
                 Telemetry repository   0600 local JSON
                      (existing)       bounded retention
```

- `dboss collect`: one explicit PGIntel cycle and one host report; the
  configured PGIntel telemetry repository receives its normal writes.
- `dboss run`: uses the **same** scheduler as `pgintel run`, not a second
  scheduler. Do not simultaneously run both services for one instance.
- `dboss host/postgres/probe/inspect/analyze`: DBOS PG18 ad-hoc diagnostic
  and offline comparison remain available; not scheduled in parallel.
- `dboss monitor` and `pgintel`: compatibility adapters for existing
  administrative workflows. The legacy service is not modified.
- `dboss-agent` Rust: **research-only executable**. It is not installed
  by the unified daemon; no second host poller is enabled.

## Data contracts and limitations

Host reports have `dboss_version`, `captured_at`, `instance`,
`postgres_cycle` (allow-listed aggregate metrics only), and `host`
(DBOS Linux/ZFS collector schema). The history is file-based, not yet a
database time-series. Default host interval is 300s; default retention
is 288 files (about 24 hours when uninterrupted).

ARC is host-wide, while PGIntel workload statistics belong to the configured
source database. Timestamp correlation is observational, not attribution of
ARC hits to a database or table. Do not treat PostgreSQL shared-buffer reads
as physical disk reads.

PG18-only ad-hoc `dbos` diagnostics remain distinct from PG13–18 legacy
PGIntel capability-based telemetry. Converting the legacy PGIntel repository
to an entirely new schema is explicitly **out of scope**.

## Safety and next research steps

No direct PostgreSQL data-file reads, no automatic pg_prewarm, DDL, DCL,
repository migration or changes to Linux, kernel, ZFS or PostgreSQL GUCs.
The original `pgintel` service continues to work, but **never enable a new
DBOSS observer daemon for the same instance simultaneously**.

Next: measure overhead across 24h, join host and SQL snapshots by verified
host/database identity, build read-only Smart Cache Advisor, then benchmark
Rust host collection and determine whether a replacement is worth it.
