"""Independent, read-only metrics collectors.

This is NOT a PostgreSQL cache controller or kernel integration module.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARC_PATH = Path("/proc/spl/kstat/zfs/arcstats")
MEMINFO_PATH = Path("/proc/meminfo")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_arcstats(raw: str) -> dict[str, int]:
    """Parse Linux OpenZFS kstats. Unknown counters are retained."""
    result: dict[str, int] = {}
    for line in raw.splitlines():
        cols = line.split()
        if len(cols) == 3 and cols[1].isdigit():
            try:
                result[cols[0]] = int(cols[2])
            except ValueError:
                pass
    return result


def parse_meminfo(raw: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parts = value.split()
        if not parts or not parts[0].isdigit():
            continue
        amount = int(parts[0])
        # Linux /proc/meminfo reports kB (KiB) for these counters.
        if len(parts) > 1 and parts[1] == "kB":
            amount *= 1024
        result[key] = amount
    return result


def command_lines(argv: list[str]) -> tuple[list[str] | None, str | None]:
    if not shutil.which(argv[0]):
        return None, "command_not_found"
    try:
        result = subprocess.run(argv, text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, type(ex).__name__
    if result.returncode:
        return None, f"exit_{result.returncode}: {result.stderr.strip()[:300]}"
    return result.stdout.splitlines(), None


def collect_host(arc_path: Path = ARC_PATH, mem_path: Path = MEMINFO_PATH) -> dict[str, Any]:
    output: dict[str, Any] = {
        "captured_at": utc_now(),
        "kernel": platform.release(),
        "os": platform.platform(),
        "read_only": True,
    }
    try:
        raw = mem_path.read_text(encoding="utf-8")
        mem = parse_meminfo(raw)
        output["memory_bytes"] = {k: mem[k] for k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree") if k in mem}
    except OSError as ex:
        output["memory_error"] = type(ex).__name__

    try:
        raw = arc_path.read_text(encoding="utf-8")
        arc = parse_arcstats(raw)
        wanted = ("size", "c", "c_max", "hits", "misses", "demand_data_hits", "demand_data_misses", "compressed_size", "uncompressed_size")
        output["zfs_arc"] = {k: arc[k] for k in wanted if k in arc}
        hits, misses = arc.get("hits", 0), arc.get("misses", 0)
        if hits + misses:
            output["zfs_arc"]["cumulative_hit_ratio"] = round(hits / (hits + misses), 5)
        output["zfs_arc_status"] = "available"
    except OSError:
        output["zfs_arc_status"] = "unavailable"
        output["zfs_arc"] = {}

    lines, err = command_lines(["zfs", "list", "-H", "-t", "filesystem", "-o", "name,mountpoint,compression,recordsize,primarycache,compressratio"])
    if err:
        output["zfs_datasets_error"] = err
        output["zfs_datasets"] = []
    else:
        output["zfs_datasets"] = [dict(zip(("name", "mountpoint", "compression", "recordsize", "primarycache", "compressratio"), ln.split("\t"))) for ln in lines if len(ln.split("\t")) == 6]
    output["note"] = "ARC statistics are host-wide and cannot be attributed to PostgreSQL without additional correlation."
    return output


TABLE_SQL = """
WITH ranked AS MATERIALIZED (
    SELECT s.relid, s.schemaname, s.relname,
           COALESCE(s.seq_scan, 0) AS seq_scan,
           COALESCE(s.idx_scan, 0) AS idx_scan,
           COALESCE(s.seq_tup_read, 0) AS seq_tup_read,
           COALESCE(s.idx_tup_fetch, 0) AS idx_tup_fetch,
           COALESCE(s.n_live_tup, 0) AS n_live_tup,
           COALESCE(s.n_dead_tup, 0) AS n_dead_tup
    FROM pg_catalog.pg_stat_user_tables AS s
    JOIN pg_catalog.pg_class AS c ON c.oid = s.relid
    WHERE c.relpersistence = 'p' AND c.relkind IN ('r', 'm')
    ORDER BY COALESCE(s.seq_tup_read, 0) + COALESCE(s.idx_tup_fetch, 0) DESC
    LIMIT %s
)
SELECT r.schemaname, r.relname, r.relid,
       r.seq_scan, r.idx_scan, r.seq_tup_read, r.idx_tup_fetch,
       r.n_live_tup, r.n_dead_tup,
       pg_catalog.pg_relation_filepath(r.relid) AS relative_path,
       pg_catalog.pg_relation_size(r.relid) AS main_bytes,
       pg_catalog.pg_total_relation_size(r.relid) AS total_bytes
FROM ranked AS r
ORDER BY r.seq_tup_read + r.idx_tup_fetch DESC
"""

INDEX_SQL = """
SELECT s.schemaname, s.relname, s.indexrelname, s.indexrelid,
       COALESCE(s.idx_scan, 0) AS idx_scan,
       COALESCE(s.idx_tup_read, 0) AS idx_tup_read,
       COALESCE(s.idx_tup_fetch, 0) AS idx_tup_fetch,
       pg_catalog.pg_relation_filepath(s.indexrelid) AS relative_path,
       pg_catalog.pg_relation_size(s.indexrelid) AS bytes
FROM pg_catalog.pg_stat_user_indexes AS s
JOIN pg_catalog.pg_class AS c ON c.oid = s.indexrelid
WHERE c.relpersistence = 'p'
ORDER BY COALESCE(s.idx_scan, 0) DESC
LIMIT %s
"""

INFO_SQL = """
SELECT current_database() AS database,
       current_setting('server_version') AS server_version,
       current_setting('server_version_num')::integer AS server_version_num,
       current_setting('io_method') AS io_method,
       current_setting('io_max_concurrency')::integer AS io_max_concurrency,
       current_setting('data_directory') AS server_data_directory,
       current_setting('block_size')::integer AS block_size,
       pg_catalog.pg_postmaster_start_time() AS started_at,
       d.stats_reset AS database_stats_reset
FROM pg_catalog.pg_stat_database AS d
WHERE d.datname = current_database()
"""



# Broad, inexpensive catalog snapshots. Unlike top-N, these retain counters
# for every user relation up to a fixed safety bound, enabling correct deltas.
# Sizes and physical paths are deliberately excluded from these broad queries.
RELATION_COUNTERS_SQL = """
SELECT s.relid, s.schemaname, s.relname,
       COALESCE(s.seq_scan, 0) AS seq_scan,
       COALESCE(s.idx_scan, 0) AS idx_scan,
       COALESCE(s.seq_tup_read, 0) AS seq_tup_read,
       COALESCE(s.idx_tup_fetch, 0) AS idx_tup_fetch,
       COALESCE(io.heap_blks_read, 0) AS heap_blks_read,
       COALESCE(io.heap_blks_hit, 0) AS heap_blks_hit,
       COALESCE(io.idx_blks_read, 0) AS idx_blks_read,
       COALESCE(io.idx_blks_hit, 0) AS idx_blks_hit
FROM pg_catalog.pg_stat_user_tables AS s
JOIN pg_catalog.pg_class AS c ON c.oid = s.relid
LEFT JOIN pg_catalog.pg_statio_user_tables AS io ON io.relid = s.relid
WHERE c.relpersistence = 'p' AND c.relkind IN ('r', 'm')
ORDER BY s.relid
LIMIT %s
"""

INDEX_COUNTERS_SQL = """
SELECT s.indexrelid, s.schemaname, s.relname, s.indexrelname,
       COALESCE(s.idx_scan, 0) AS idx_scan,
       COALESCE(s.idx_tup_read, 0) AS idx_tup_read,
       COALESCE(s.idx_tup_fetch, 0) AS idx_tup_fetch,
       COALESCE(io.idx_blks_read, 0) AS idx_blks_read,
       COALESCE(io.idx_blks_hit, 0) AS idx_blks_hit
FROM pg_catalog.pg_stat_user_indexes AS s
JOIN pg_catalog.pg_class AS c ON c.oid = s.indexrelid
LEFT JOIN pg_catalog.pg_statio_user_indexes AS io ON io.indexrelid = s.indexrelid
WHERE c.relpersistence = 'p'
ORDER BY s.indexrelid
LIMIT %s
"""

# pg_stat_io is cluster-wide, not attributable to a relation or database.
IO_SQL = """
SELECT backend_type, object, context,
       COALESCE(reads, 0) AS reads,
       COALESCE(writes, 0) AS writes,
       COALESCE(hits, 0) AS hits,
       COALESCE(evictions, 0) AS evictions,
       COALESCE(fsyncs, 0) AS fsyncs,
       stats_reset
FROM pg_catalog.pg_stat_io
ORDER BY backend_type, object, context
"""

# PostgreSQL's pg_stat_database counters apply to the current DB.
DATABASE_IO_SQL = """
SELECT blks_read, blks_hit, xact_commit, xact_rollback
FROM pg_catalog.pg_stat_database
WHERE datname = current_database()
"""

def require_postgresql_18(version_num: int) -> None:
    """DBOS currently supports only the PostgreSQL 18 major release."""
    if not 180000 <= version_num < 190000:
        raise RuntimeError("DBOS Intelligence 0.2.0 requires PostgreSQL 18.x")


def dictrows(cursor: Any) -> list[dict[str, Any]]:
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def collect_postgres(limit: int = 20, max_relations: int = 10000) -> dict[str, Any]:
    """Read-only, one database at a time, using local libpq connection defaults."""
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if not 1 <= max_relations <= 50000:
        raise ValueError("max_relations must be between 1 and 50000")
    try:
        import psycopg
    except ImportError as ex:
        raise RuntimeError('Missing driver. Install: python -m pip install ".[postgres]"') from ex

    # No DSN on the command line or in JSON output; libpq reads PG* environment
    # or ~/.pg_service.conf and ~/.pgpass. PostgreSQL enforces read-only transactions.
    with psycopg.connect("", connect_timeout=5, options="-c default_transaction_read_only=on -c statement_timeout=5000 -c stats_fetch_consistency=snapshot") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('server_version_num')::integer")
            server_version_num = cur.fetchone()[0]
            require_postgresql_18(server_version_num)
            cur.execute(INFO_SQL)
            info = dictrows(cur)
            cur.execute(TABLE_SQL, (limit,))
            tables = dictrows(cur)
            cur.execute(INDEX_SQL, (limit,))
            indexes = dictrows(cur)
            cur.execute(RELATION_COUNTERS_SQL, (max_relations + 1,))
            relation_raw = dictrows(cur)
            cur.execute(INDEX_COUNTERS_SQL, (max_relations + 1,))
            index_raw = dictrows(cur)
            cur.execute(IO_SQL)
            io_stats = dictrows(cur)
            cur.execute(DATABASE_IO_SQL)
            database_io = dictrows(cur)

    for row in io_stats:
        if row["stats_reset"] is not None:
            row["stats_reset"] = row["stats_reset"].isoformat()
    for row in info:
        for key in ("started_at", "database_stats_reset"):
            if row[key] is not None:
                row[key] = row[key].isoformat()
    return {
        "captured_at": utc_now(),
        "read_only": True,
        "server": info[0] if info else {},
        "top_tables": tables,
        "top_indexes": indexes,
        "relation_counters": relation_raw[:max_relations],
        "index_counters": index_raw[:max_relations],
        "relation_counters_complete": len(relation_raw) <= max_relations,
        "index_counters_complete": len(index_raw) <= max_relations,
        "pg_stat_io": io_stats,
        "database_io": database_io[0] if database_io else {},
        "note": (
            "Statistics are cumulative since their last reset, NOT instantaneous hotness. "
            "pg_stat_io is cluster-wide and may include other databases. "
            "Paths are relative to the database server's PGDATA, which may be on a different host. "
            "A main relation path does not enumerate segments, TOAST, or FSM/VM forks."
        ),
    }
