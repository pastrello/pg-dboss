"""Read-only, offline DBOSS Smart Cache Advisor, using DBOS interval JSON only.

No PostgreSQL connection, no privileged operations, and no execution of advice.
The heuristics are exploratory. Hits/misses refer to PostgreSQL shared_buffers,
not physical disk reads, and never identify specific hot block ranges.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import __version__

MAX_FILE_BYTES = 64 * 1024 * 1024
MIN_BLOCK_MISSES_FOR_REVIEW = 1000
MAX_HIT_RATIO_FOR_REVIEW = 0.90


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("interval timestamps are required")
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.utcoffset() is None:
        raise ValueError("interval timestamps must include timezones")
    return ts


def read_interval(filename: str | Path) -> dict:
    source = Path(filename)
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("interval JSON exceeds the 64 MiB safety limit")
    with source.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or doc.get("mode") != "analyze":
        raise ValueError("expected a DBOS analyze JSON report")
    analysis = doc.get("analysis")
    if not isinstance(analysis, dict) or analysis.get("read_only") is not True:
        raise ValueError("interval is not verified as an observation-only report")
    if analysis.get("actions_taken") != []:
        raise ValueError("interval reports non-empty actions_taken")
    pg = analysis.get("postgres")
    if not isinstance(pg, dict) or str(pg.get("version", "")).split(".")[0] != "18":
        raise ValueError("advisor requires PostgreSQL 18 interval statistics")
    start, end = _timestamp(analysis.get("before")), _timestamp(analysis.get("after"))
    if end <= start or float(analysis.get("interval_seconds", 0)) <= 0:
        raise ValueError("invalid comparison interval")
    for group in ("relations", "indexes"):
        obj = pg.get(group)
        if not isinstance(obj, dict) or not isinstance(obj.get("top_by_buffer_misses"), list):
            raise ValueError(f"interval lacks {group} counters")
    return analysis


def _nonnegative(row: dict, key: str) -> int:
    value = row.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid nonnegative metric: {key}")
    return value


def _accumulate(aggregates: dict, rows: list, kind: str, elapsed: float) -> None:
    ident = "indexrelid" if kind == "index" else "relid"
    labels = ("schemaname", "relname", "indexrelname") if kind == "index" else ("schemaname", "relname")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("deltas"), dict):
            raise ValueError("invalid relation/index interval entry")
        obj_id = row.get(ident)
        if not isinstance(obj_id, int) or obj_id <= 0 or any(not isinstance(row.get(k), str) for k in labels):
            raise ValueError("invalid relation/index identity")
        delta = row["deltas"]
        if kind == "index":
            reads = _nonnegative(delta, "idx_blks_read")
            hits = _nonnegative(delta, "idx_blks_hit")
            scans = _nonnegative(delta, "idx_scan")
        else:
            reads = _nonnegative(delta, "heap_blks_read") + _nonnegative(delta, "idx_blks_read")
            hits = _nonnegative(delta, "heap_blks_hit") + _nonnegative(delta, "idx_blks_hit")
            scans = _nonnegative(delta, "seq_scan") + _nonnegative(delta, "idx_scan")
        k = (kind, obj_id)
        meta = {label: row[label] for label in labels}
        entry = aggregates.setdefault(k, {
            "kind": kind, "oid": obj_id, **meta, "missed_blocks": 0,
            "hit_blocks": 0, "scans": 0, "observed_intervals": 0,
            "observation_seconds": 0.0,
        })
        if any(entry[label] != row[label] for label in labels):
            raise ValueError("object identity changed between intervals")
        entry["missed_blocks"] += reads
        entry["hit_blocks"] += hits
        entry["scans"] += scans
        entry["observed_intervals"] += 1
        entry["observation_seconds"] += elapsed


def advise(intervals: list[dict], *, assume_same_source: bool = False, limit: int = 20) -> dict:
    if not intervals or not 1 <= limit <= 100:
        raise ValueError("supply intervals and use a result limit 1..100")
    if len(intervals) > 1 and not assume_same_source:
        raise ValueError("multiple intervals require explicit --assume-same-source")
    ordered = sorted(intervals, key=lambda x: _timestamp(x["before"]))
    databases = {x["postgres"]["database"] for x in ordered}
    if len(databases) != 1 or any(not isinstance(x, str) or not x for x in databases):
        raise ValueError("all intervals must describe the same named database")
    for prev, nxt in zip(ordered, ordered[1:]):
        if _timestamp(prev["after"]) > _timestamp(nxt["before"]):
            raise ValueError("overlapping intervals may double-count activity")
    agg: dict = {}
    for analysis in ordered:
        elapsed = float(analysis["interval_seconds"])
        pg = analysis["postgres"]
        _accumulate(agg, pg["relations"]["top_by_buffer_misses"], "relation", elapsed)
        _accumulate(agg, pg["indexes"]["top_by_buffer_misses"], "index", elapsed)

    results: list[dict] = []
    for item in agg.values():
        total = item["missed_blocks"] + item["hit_blocks"]
        ratio = item["hit_blocks"] / total if total else None
        if item["kind"] == "index" and item["scans"] == 0 and item["missed_blocks"]:
            category = "non_scan_activity"
        elif item["missed_blocks"] >= MIN_BLOCK_MISSES_FOR_REVIEW and ratio is not None and ratio < MAX_HIT_RATIO_FOR_REVIEW:
            category = "investigate"
        elif ratio is not None and ratio >= 0.95:
            category = "cache_effective_in_sample"
        else:
            category = "observe"
        results.append({
            **{k: v for k, v in item.items() if k != "observation_seconds"},
            "postgres_buffer_hit_ratio": round(ratio, 5) if ratio is not None else None,
            "misses_per_minute_observed": round(
                60 * item["missed_blocks"] / item["observation_seconds"], 3
            ) if item["observation_seconds"] else None,
            "classification": category,
            "suggested_next_step": (
                "Inspect maintenance/VACUUM and index definition; zero scans do not imply unused."
                if category == "non_scan_activity" else
                "Measure object size, block residency, and another representative interval."
                if category == "investigate" else
                "Observe; no prewarming justified from these snapshots."
            ),
        })
    priority = {"investigate": 0, "non_scan_activity": 1, "observe": 2,
                "cache_effective_in_sample": 3}
    results.sort(key=lambda r: (priority[r["classification"]], -r["missed_blocks"],
                                r["kind"], r["oid"]))
    return {
        "dboss_version": __version__,
        "mode": "smart-cache-advisor",
        "read_only": True,
        "actions_taken": [],
        "database": next(iter(databases)),
        "intervals_analyzed": len(ordered),
        "source_identity_verified": False,
        "confidence": "exploratory",
        "heuristic": {"minimum_missed_blocks_for_review": MIN_BLOCK_MISSES_FOR_REVIEW,
                      "max_hit_ratio_for_review": MAX_HIT_RATIO_FOR_REVIEW},
        "candidates": results[:limit],
        "notices": [
            "All inputs are DBOS interval deltas; no additional PostgreSQL SQL was executed.",
            "PostgreSQL buffer misses are not proof of disk I/O; ARC is host-wide.",
            "No object sizes or resident block maps were provided: no prewarm recommendation.",
            "The DBOS top-N input can omit objects outside the prior result limit.",
            "Source instance identity is not verified; multi-interval combination requires operator assertion.",
            "Recommendations are preliminary even for repeated intervals; no configuration change is performed.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dboss advise",
                                     description="Offline, read-only Smart Cache Advisor")
    parser.add_argument("--interval", action="append", required=True, help="DBOS analyze JSON; repeat for more intervals")
    parser.add_argument("--assume-same-source", action="store_true",
                        help="Explicitly assert the intervals refer to the same PostgreSQL instance")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", help="New private JSON file (never overwrite)")
    args = parser.parse_args(argv)
    try:
        report = advise([read_interval(f) for f in args.interval],
                        assume_same_source=args.assume_same_source, limit=args.limit)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(args.output, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
        else:
            sys.stdout.write(payload)
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"dboss advise: invalid input or output ({type(exc).__name__}).",
              file=sys.stderr)
        return 1
