"""Unified, opt-in command dispatcher; preserve both historical CLIs."""
from __future__ import annotations
import sys
from . import __version__

DBOS_COMMANDS = {"host", "postgres", "probe", "inspect", "analyze"}
USAGE = """DBOSS {version}: Linux/OpenZFS/PostgreSQL observability (read-only by default)
Usage:
  dboss --version
  dboss host|postgres|probe|inspect|analyze [options]  # DBOS 0.2.1
  dboss monitor -c /etc/pgintel/pgintel.ini <command> [options] # PG Intelligence
Compatibility: dbos and pgintel entrypoints are retained.
The monitor command retains PG Intelligence's original explicit repository operations.
"""

def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("--help", "-h", "help"):
        print(USAGE.format(version=__version__))
        return 0
    if args[0] in ("--version", "-V"):
        print(f"dboss {__version__} (DBOS 0.2.1 + PG Intelligence 0.1.8)")
        return 0
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
