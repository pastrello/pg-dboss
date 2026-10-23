# DBOSS Architecture (2026-10-23)

1. Legacy PG Intelligence: source DB read-only, FAST 60s, SLOW 900s, SIZE
   3600s, persisted history in separate PostgreSQL repository. Existing
   config /etc/pgintel/pgintel.ini, service pgintel.service unchanged.
2. DBOS: read-only Linux /proc and OpenZFS ARC/dataset capture; PostgreSQL
   18 stats capture and offline deltas for relations, indexes and I/O.
3. DBOSS CLI: dispatcher only. Does NOT couple PGIntel database repository
   writes into DBOS probes; that requires a reviewed schema/interface.
4. Rust research agent: independent static-ish Linux host metrics executable;
   NOT a replacement for PGIntel's repository/SQL analysis.
5. Future Smart Cache advisor: read-only recommendations; never auto-prewarm
   and no automatic SQL DDL, index removal, ZFS or kernel tuning.
6. Shared observability interface (planned): host identity, PostgreSQL
   cluster ID, database oid, sample timestamps, reset epochs, relation ID,
   namespace and exact data provenance. Do not attribute host-wide ARC to
   one database unless correlation is proven.

Research priorities: compression LZ4/Zstd at appropriate layers, ARC and
PostgreSQL buffer interaction, pg_stat_io, io_uring, filesystem observability,
and reproducible comparisons against vanilla Rocky Linux.
