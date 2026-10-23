"""Pure, offline, read-only analysis of DBOS snapshots.

Never makes decisions to tune kernel, ZFS or PostgreSQL. Data is advisory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_REPORT_BYTES = 64 * 1024 * 1024


def read_snapshot(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("snapshot larger than 64 MiB")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("captured_at"), str):
        raise ValueError("invalid DBOS snapshot")
    if not isinstance(data.get("host", data.get("postgres")), dict):
        raise ValueError("snapshot contains neither host nor postgres data")
    return data


def as_pg(doc: dict[str, Any]) -> dict[str, Any] | None:
    value = doc.get("postgres")
    return value if isinstance(value, dict) else None


def as_host(doc: dict[str, Any]) -> dict[str, Any] | None:
    value = doc.get("host")
    return value if isinstance(value, dict) else None


def captured_time(doc: dict[str, Any]) -> datetime:
    moment = datetime.fromisoformat(doc["captured_at"].replace("Z", "+00:00"))
    if moment.utcoffset() is None:
        raise ValueError("snapshot timestamp must include a timezone")
    return moment


def inspect_snapshots(host_doc: dict[str, Any], pg_doc: dict[str, Any]) -> dict[str, Any]:
    """Provide non-destructive assessment, including older captured samples."""
    host = as_host(host_doc)
    pg = as_pg(pg_doc)
    if host is None or pg is None:
        raise ValueError("expected host and postgres snapshots")
    memory = host.get("memory_bytes", {})
    arc = host.get("zfs_arc", {})
    server = pg.get("server", {})
    mem_total = memory.get("MemTotal", 0)
    mem_avail = memory.get("MemAvailable", 0)
    arc_size = arc.get("size", 0)
    compressed_size = arc.get("compressed_size", 0)
    uncompressed_size = arc.get("uncompressed_size", 0)
    major = str(server.get("server_version", "unknown")).split(".")[0]
    notices = ["ARC counters are host-wide, not PostgreSQL-specific.",
               "A single cumulative snapshot cannot identify currently hot tables or indexes."]
    if major != "18":
        notices.append(f"PostgreSQL {major} detected; DBOS target is PostgreSQL 18.x. Only offline legacy inspection is allowed.")
    span = abs((captured_time(pg_doc) - captured_time(host_doc)).total_seconds())
    if span > 120:
        notices.append(f"Host and PostgreSQL samples are {round(span / 60, 1)} minutes apart; they do not describe one synchronized instant.")
    if mem_total and mem_avail / mem_total < 0.10:
        notices.append("MemAvailable below 10% of RAM in this sample; observe pressure over time before making cache reservations.")
    if not any(int(r.get("seq_scan", 0)) or int(r.get("idx_scan", 0)) for r in pg.get("top_tables", [])):
        notices.append("Returned top tables have no recorded scans; hotness ranking is currently unsupported.")
    return {
        "read_only": True,
        "source": {"host_captured_at": host_doc["captured_at"], "postgres_captured_at": pg_doc["captured_at"]},
        "postgres_version": server.get("server_version"),
        "postgres_database": server.get("database"),
        "kernel": host.get("kernel"),
        "memory": {"total_bytes": mem_total, "available_bytes": mem_avail,
                   "available_fraction": round(mem_avail / mem_total, 5) if mem_total else None},
        "arc": {"size_bytes": arc_size,
                "fraction_of_ram": round(arc_size / mem_total, 5) if mem_total else None,
                "cumulative_hit_ratio": arc.get("cumulative_hit_ratio"),
                "compressed_data_ratio": round(uncompressed_size / compressed_size, 3) if compressed_size else None},
        "datasets": host.get("zfs_datasets", []),
        "notices": notices,
        "actions_taken": [],
    }


TABLE_METRICS = ("seq_scan", "idx_scan", "seq_tup_read", "idx_tup_fetch",
                 "heap_blks_read", "heap_blks_hit", "idx_blks_read", "idx_blks_hit")
INDEX_METRICS = ("idx_scan", "idx_tup_read", "idx_tup_fetch", "idx_blks_read", "idx_blks_hit")


def entity_deltas(before: list[dict[str, Any]], after: list[dict[str, Any]],
                  ident: str, labels: tuple[str, ...], metrics: tuple[str, ...],
                  elapsed: float) -> tuple[list[dict[str, Any]], int]:
    old = {r[ident]: r for r in before}
    items: list[dict[str, Any]] = []
    skipped = 0
    for new in after:
        previous = old.get(new[ident])
        if previous is None or any(previous.get(k) != new.get(k) for k in labels):
            skipped += 1
            continue
        delta = {k: int(new.get(k) or 0) - int(previous.get(k) or 0) for k in metrics}
        if any(v < 0 for v in delta.values()):
            skipped += 1  # Individual counters may have reset; never use negative deltas.
            continue
        hits = delta.get("heap_blks_hit", 0) + delta.get("idx_blks_hit", 0)
        reads = delta.get("heap_blks_read", 0) + delta.get("idx_blks_read", 0)
        items.append({**{k: new[k] for k in (ident,) + labels}, "deltas": delta,
                      "activity_scans_per_second": round((delta.get("seq_scan", 0) + delta.get("idx_scan", 0)) / elapsed, 3),
                      "postgres_buffer_hit_ratio": round(hits / (hits + reads), 5) if hits + reads else None})
    items.sort(key=lambda d: (d["deltas"].get("heap_blks_read", 0) + d["deltas"].get("idx_blks_read", 0),
                              d["deltas"].get("seq_scan", 0) + d["deltas"].get("idx_scan", 0)), reverse=True)
    return items, skipped


def analyze_snapshots(before: dict[str, Any], after: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    """Compare two measurements. PG18 is required for valid baseline conclusions."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    elapsed = (captured_time(after) - captured_time(before)).total_seconds()
    if elapsed <= 0:
        raise ValueError("after snapshot must be later than before snapshot")
    out: dict[str, Any] = {"read_only": True, "interval_seconds": round(elapsed, 3),
                           "before": before["captured_at"], "after": after["captured_at"],
                           "warnings": [], "actions_taken": []}
    oldpg, newpg = as_pg(before), as_pg(after)
    if oldpg is not None and newpg is not None:
        old_server, new_server = oldpg.get("server", {}), newpg.get("server", {})
        if not (str(old_server.get("server_version", "")).split(".")[0] == "18"
                and str(new_server.get("server_version", "")).split(".")[0] == "18"):
            raise ValueError("PG18 required for DBOS interval analysis; PG14 report is historical inspection only")
        for key in ("database", "server_data_directory"):
            if not old_server.get(key) or old_server[key] != new_server.get(key):
                raise ValueError(f"PostgreSQL comparison invalid: {key} changed or is missing")
        # Since PostgreSQL 15, pg_stat_database.stats_reset may legitimately
        # be SQL NULL (serialized as JSON null) until an explicit reset.
        # Absent metadata is different from a recorded SQL NULL.
        if "database_stats_reset" not in old_server or "database_stats_reset" not in new_server:
            raise ValueError("PostgreSQL comparison invalid: database_stats_reset field missing")
        old_reset = old_server["database_stats_reset"]
        new_reset = new_server["database_stats_reset"]
        if old_reset != new_reset:
            raise ValueError("PostgreSQL comparison invalid: database_stats_reset changed")
        if old_reset is None:
            # With no reset epoch available, continuity across a restart is
            # unprovable: counters could have disappeared after a crash.
            old_started, new_started = old_server.get("started_at"), new_server.get("started_at")
            if not old_started or not new_started or old_started != new_started:
                raise ValueError(
                    "PostgreSQL comparison invalid: started_at changed or missing while database_stats_reset is NULL"
                )
            out["warnings"].append(
                "database_stats_reset is NULL in both samples (valid in PG18); "
                "continuity is inferred from unchanged start time and nondecreasing counters."
            )
        elif not old_reset:
            # A blank string is not a meaningful timestamp.
            raise ValueError("PostgreSQL comparison invalid: database_stats_reset empty")
        if old_server.get("started_at") != new_server.get("started_at"):
            out["warnings"].append("PostgreSQL restarted; stats_reset unchanged, but assess continuity before applying conclusions.")
        out["postgres"] = {"database": new_server["database"], "version": new_server["server_version"]}
        for field, identity, names, metrics, key in (
            ("relation_counters", "relid", ("schemaname", "relname"), TABLE_METRICS, "relations"),
            ("index_counters", "indexrelid", ("schemaname", "relname", "indexrelname"), INDEX_METRICS, "indexes"),
        ):
            if field not in oldpg or field not in newpg:
                out["warnings"].append(f"{field} unavailable: upgrade both collectors to DBOS 0.2.0")
                continue
            if oldpg.get(field + "_complete") is not True or newpg.get(field + "_complete") is not True:
                out["warnings"].append(f"{field} truncated: rankings are not database-wide")
            ranked, skipped = entity_deltas(oldpg[field], newpg[field], identity, names, metrics, elapsed)
            out["postgres"][key] = {"compared": len(ranked), "skipped_new_or_reset": skipped,
                                      "top_by_buffer_misses": ranked[:limit]}
        # pg_stat_io is cluster-wide. Match each source row and its reset epoch;
        # never attribute these figures to individual tables or to this DB.
        if "pg_stat_io" in oldpg and "pg_stat_io" in newpg:
            old_io = {(r.get("backend_type"), r.get("object"), r.get("context")): r
                      for r in oldpg["pg_stat_io"]}
            io_changes = []
            for r in newpg["pg_stat_io"]:
                ident = (r.get("backend_type"), r.get("object"), r.get("context"))
                previous = old_io.get(ident)
                if previous is None or previous.get("stats_reset") != r.get("stats_reset"):
                    continue
                d = {k: int(r.get(k, 0)) - int(previous.get(k, 0))
                     for k in ("reads", "writes", "hits", "evictions", "fsyncs")}
                if any(v < 0 for v in d.values()):
                    continue
                if any(d.values()):
                    io_changes.append({"backend_type": ident[0], "object": ident[1],
                                       "context": ident[2], "deltas": d})
            out["postgres"]["cluster_io_deltas"] = io_changes
            out["warnings"].append("pg_stat_io covers the PostgreSQL cluster, not just the selected database")
        a, b = oldpg.get("database_io"), newpg.get("database_io")
        if a and b:
            delta = {k: int(b[k]) - int(a[k]) for k in ("blks_read", "blks_hit", "xact_commit", "xact_rollback")}
            if all(v >= 0 for v in delta.values()):
                out["postgres"]["database_io_deltas"] = delta
            else:
                out["warnings"].append("Database-wide counters decreased; skipped their delta")
        out["warnings"].append("PostgreSQL blks_read is a shared-buffer miss, not proof of a physical disk read.")
    elif oldpg is not None or newpg is not None:
        out["warnings"].append("PostgreSQL appears in only one snapshot, so no SQL activity delta was calculated")
    oldh, newh = as_host(before), as_host(after)
    if oldh is not None and newh is not None:
        a, b = oldh.get("zfs_arc", {}), newh.get("zfs_arc", {})
        hits = int(b.get("hits", 0)) - int(a.get("hits", 0))
        misses = int(b.get("misses", 0)) - int(a.get("misses", 0))
        out["arc"] = {"size_bytes_after": b.get("size"), "interval_hits": hits if hits >= 0 else None,
                      "interval_misses": misses if misses >= 0 else None,
                      "interval_hit_ratio": round(hits / (hits + misses), 5) if hits >= 0 and misses >= 0 and hits + misses > 0 else None}
        if hits < 0 or misses < 0:
            out["warnings"].append("ARC counters reset or samples from different hosts; hit ratio omitted")
        out["warnings"].append("Host identity not verified by snapshots; ARC statistics cover all ZFS workloads")
    out["warnings"].append("Observational report only: no prewarm, pool settings, kernel tuning or SQL writes performed")
    return out
