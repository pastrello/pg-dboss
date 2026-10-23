"""DBOS probe CLI. All commands are observation-only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .collectors import collect_host, collect_postgres, utc_now
from .analytics import analyze_snapshots, inspect_snapshots, read_snapshot


def json_fallback(o: Any) -> str:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DBOS v0.2 read-only kernel/PostgreSQL/ZFS observability")
    parser.add_argument("--version", action="version", version=f"dbos {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("host", "postgres", "probe"):
        p = sub.add_parser(name, help={"host": "Linux / OpenZFS metrics", "postgres": "PostgreSQL relation stats", "probe": "both collectors"}[name])
        p.add_argument("--output", help="write report to this path (local JSON); never include credentials")
        if name != "host":
            p.add_argument("--limit", type=int, default=20, help="maximum table/index rows (1..100)")
        if name != "host":
            p.add_argument("--max-relations", type=int, default=10000,
                           help="max counters kept per class (1..50000; no relation sizes)")
    inspect = sub.add_parser("inspect", help="offline single-sample diagnostics (also accepts legacy PG reports)")
    inspect.add_argument("--host", required=True, help="existing host JSON")
    inspect.add_argument("--postgres", required=True, help="existing PostgreSQL JSON")
    inspect.add_argument("--output", help="write results privately; never overwrite")
    analyze = sub.add_parser("analyze", help="compare two PG18 snapshots without modifying the host")
    analyze.add_argument("--before", required=True, help="earlier DBOS JSON snapshot")
    analyze.add_argument("--after", required=True, help="later DBOS JSON snapshot")
    analyze.add_argument("--limit", type=int, default=20, help="maximum output rows (1..100)")
    analyze.add_argument("--output", help="write results privately; never overwrite")
    args = parser.parse_args(argv)
    if hasattr(args, "limit") and not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    if hasattr(args, "max_relations") and not 1 <= args.max_relations <= 50000:
        parser.error("--max-relations must be between 1 and 50000")
    report: dict[str, Any] = {"dbos_version": __version__, "captured_at": utc_now(), "mode": args.command, "read_only": True}
    try:
        if args.command == "inspect":
            report["inspection"] = inspect_snapshots(read_snapshot(args.host), read_snapshot(args.postgres))
        elif args.command == "analyze":
            report["analysis"] = analyze_snapshots(read_snapshot(args.before), read_snapshot(args.after), args.limit)
        else:
            if args.command in ("host", "probe"):
                report["host"] = collect_host()
            if args.command in ("postgres", "probe"):
                report["postgres"] = collect_postgres(args.limit, args.max_relations)
    except Exception as ex:
        # Avoid echoing libpq connection strings and secrets from exception details.
        if isinstance(ex, (ValueError, RuntimeError, FileNotFoundError)) and args.command in ("inspect", "analyze"):
            # Offline parser messages have no connection strings or credentials.
            print(f"dbos: {type(ex).__name__}: {ex}", file=sys.stderr)
        else:
            print(f"dbos: collection failed ({type(ex).__name__}). Check DBOS inputs, PostgreSQL connection and permissions.", file=sys.stderr)
        return 1
    payload = json.dumps(report, default=json_fallback, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        dest = Path(args.output)
        # Default to private reports; refuse to overwrite an existing report.
        import os
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(dest, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
        except OSError as ex:
            print(f"dbos: unable to create new report ({type(ex).__name__}); file must not exist", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
