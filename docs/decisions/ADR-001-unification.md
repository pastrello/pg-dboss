# ADR-001 — Consolidate DBOS and PG Intelligence as DBOSS
Date: 2026-10-23 — Accepted for experimental development

Use the Git history of renamed pastrello/pg-dboss, add DBOS 0.2.1,
retain original PGIntel API/code/service and independent telemetry DB.
Unified CLI routes commands without invasive refactors. New capability
baseline PG18; pre-existing PG13–17 monitoring remains.

Rationale: low-risk versioned consolidation, no downtime, retains data,
avoids duplicate engines and allows research on kernel/ZFS independently.
Reject blind Python-to-Rust rewrite; add an experimental read-only Rust
host probe, measure first, then selectively port if benefits are proven.

Security: no automatic SQL DDL, source DB writes, ZFS tuning, kernel
changes, service enablement or repository migration in this PR.
