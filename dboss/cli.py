"""DBOSS public CLI: one operational entry point; legacy CLIs remain thin adapters."""
from __future__ import annotations
import sys
from . import __version__

DBOS_COMMANDS = {"host", "postgres", "probe", "inspect", "analyze"}
USAGE = """DBOSS {version} — PostgreSQL + Linux/OpenZFS observability
Usage:
  dboss --version
  dboss collect -c /etc/pgintel/pgintel.ini [--full] [--host-dir DIR]
  dboss run -c /etc/pgintel/pgintel.ini [--host-dir DIR] [--host-interval 300]
  dboss host|postgres|probe|inspect|analyze [options]  # on-demand DBOS PG18 analysis
  dboss monitor -c /etc/pgintel/pgintel.ini <command> [options]  # legacy operations

Continuous mode: PG Intelligence performs ALL periodic SQL collection; DBOSS
adds local Linux/ZFS host snapshots. There is no second PostgreSQL poller.
dboss collect/run write only to the configured telemetry repository and local
private host history; the monitored application database is read-only.
Compatibility: dbos and pgintel entrypoints are retained during migration.
"""

def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("--help", "-h", "help"):
        print(USAGE.format(version=__version__))
        return 0
    if args[0] in ("--version", "-V"):
        print(f"dboss {__version__} (DBOS 0.2.1 + PG Intelligence 0.1.8)")
        return 0
    if args[0] in ("collect", "run"):
        from .telemetry import main as telemetry_main
        return telemetry_main(args)
    if args[0] in DBOS_COMMANDS:
        from dbos.cli import main as dbos_main
        return dbos_main(args)
    if args[0] in ("monitor", "pgintel"):
        from pgintel.cli import main as pgintel_main
        return pgintel_main(args[1:])
    print(f"dboss: unknown command {args[0]!r}; see dboss --help", file=sys.stderr)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
