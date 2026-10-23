# DBOSS — development contract

- Source of truth: https://github.com/pastrello/pg-dboss
- Scope: DBOS Linux/ZFS observability + PG Intelligence continuous telemetry; exactly ONE scheduled SQL poller (PGIntel scheduler with optional DBOSS host callback).
- PostgreSQL 18 is the required baseline for **new** DBOS intelligence; PGIntel monitoring compatibility with PostgreSQL 13–18 is legacy and must not be broken.
- Preserve current 'pgintel' CLI, installer, service paths, configuration, telemetry schema, and migrated data until a separate verified migration has a rollback plan.
- Never modify a monitored database, index, role, GUC, data directory, or ZFS pool automatically. Existing historical PGIntel bootstrap/migrate functions require explicit user action.
- Do not read PostgreSQL relation files directly to infer table semantics; use official SQL/catalog/stats.
- No automatic prewarm, ARC tuning, kernel patch, or index removal.
- Use isolated branches/PRs; do not force-push main. Keep AGENTS.md and docs/PROJECT-STATE.md current.
- Prefer standard PGDG PostgreSQL packages. OpenZFS remains a separate Linux kernel module.
- New system agents may be Rust; keep existing Python operational until parity, tests and safe deployment/rollback.
- Do not commit DSNs with secrets, customer data, snapshots, SQL texts, credentials or production diagnostics.
- Never run pgintel.service and dboss run concurrently for the same instance; no automatic systemd migration.
- DBOSS collect/run write to the dedicated telemetry repository, while monitored application DB must remain read-only.
- Before release, run 'bash ./install.sh --self-test', CI, and explicit Linux/PG18/ZFS integration tests.

- `dboss advise` is offline and advisory-only; no cache changes, SQL, or prewarming. Never assume host identity from legacy interval files.
