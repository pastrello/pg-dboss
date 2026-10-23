# DBOSS — Project State
Updated: 2026-10-23

## Repository / branch
- Remote: pastrello/pg-dboss (renamed from pastrello/pg-intel).
- Original Git commits, service and PG Intelligence 0.1.8 source retained.
- Integration branch: feature/dboss-consolidation, PR #5 (draft).
- Keep main unchanged until code/CI and real laboratory acceptance.

## Working parts
- Root pgintel/ + install-rocky.sh + pgintel.service + sql/: legacy intact.
- dbos/: original DBOS 0.2.1 collectors, CLI and analyzer; 20 regression tests.
- dboss/: dispatch to dbos or pgintel CLI; no new scheduler.
- install.sh: default local venv bootstrap + tests; --self-test/--doctor;
  --install isolated CLI in /opt/dboss; legacy bootstrap explicit opt-in.
- Rust crates/dboss-agent: read-only kernel memory/ARC metrics prototype;
  no database access, no daemon or automatic changes.
- New DBOSS features target PG18. Legacy PG Intel PG13–18 support preserved.

## Safety and pending
- No changes to any DB schema/index/role, PGDATA, ZFS pool, Linux kernel,
  systemd service or existing telemetry repository in this PR.
- Still required: PG18/ARC end-to-end Rocky tests, burn-in, installer
  smoke test on Rocky 8/9/10, comparison against Python.
- No automatic Smart Cache Advisor/prewarm, no cache controller,
  no unified PGIntel/DBOS timeseries database yet.
- No Python removal before Rust parity, operator validation and rollback.
- Python distribution remains pg-intelligence 0.1.8 for historical
  installer/test compatibility; dboss product CLI version is 0.1.0.
