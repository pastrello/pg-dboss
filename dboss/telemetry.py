"""Unified DBOSS telemetry: PGIntel is the sole scheduled PostgreSQL collector.

Host/ZFS observations are independent, bounded and private. No PostgreSQL
index/schema/GUC/prewarm changes, and no ZFS or kernel adjustments.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from dbos.collectors import collect_host
from pgintel.agent import collect_once, run_forever
from pgintel.config import load_config
from . import __version__

_CYCLE_KEYS = ("collected_at", "server_major", "cycle_duration_ms",
               "source_duration_ms", "repository_duration_ms",
               "budget_exceeded", "events_created", "events_suppressed")
_FILE_PREFIX = "dboss-host-"


def default_host_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state).expanduser() if state else Path.home() / ".local" / "state"
    return base / "dboss" / "host"


def private_dir(directory: str | Path) -> Path:
    """Refuse symlinks, unowned directories and directories visible to others."""
    path = Path(directory).expanduser()
    if path.is_symlink():
        raise ValueError("host history directory must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("host history directory must be owned by the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("host history directory permissions must be 0700 or stricter")
    return path


class HostObserver:
    """An optional on-cycle hook; it never performs PostgreSQL queries."""

    def __init__(self, instance: str, directory: str | Path,
                 interval: int = 300, keep: int = 288, clock=None) -> None:
        if interval < 60:
            raise ValueError("host interval must be at least 60 seconds")
        if not 1 <= keep <= 10000:
            raise ValueError("host keep must be between 1 and 10000")
        self.instance = instance
        self.directory = private_dir(directory)
        self.interval = interval
        self.keep = keep
        self.clock = clock or time.monotonic
        self.last = None

    def capture(self, cycle: dict | None = None) -> Path:
        """Save a single private JSON report with no DSN, password or SQL text."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        filename = f"{_FILE_PREFIX}{stamp}-{uuid4().hex[:12]}.json"
        record = {
            "dboss_version": __version__,
            "mode": "unified-host-observation",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "read_only_source": True,
            "instance": self.instance,
            "postgres_cycle": ({k: cycle[k] for k in _CYCLE_KEYS if k in cycle}
                               if cycle is not None else None),
            "host": collect_host(),
            "note": "ARC is host-wide; no PostgreSQL database attribution is inferred.",
        }
        path = self.directory / filename
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(record, out, indent=2, ensure_ascii=False)
            out.write("\n")
        self._prune()
        return path

    def _prune(self) -> None:
        own_files = sorted(
            p for p in self.directory.glob(f"{_FILE_PREFIX}*.json")
            if p.is_file() and not p.is_symlink()
        )
        for old in own_files[:-self.keep]:
            old.unlink()

    def __call__(self, cycle: dict | None = None) -> None:
        now = self.clock()
        if self.last is not None and now - self.last < self.interval:
            return
        self.capture(cycle)
        self.last = now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dboss", description="Unified PostgreSQL/host telemetry")
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("collect", "run"):
        p = sub.add_parser(mode)
        p.add_argument("-c", "--config", default="/etc/pgintel/pgintel.ini")
        p.add_argument("--host-dir", default=None, help="Private JSON host-history folder (0700)")
        p.add_argument("--host-keep", type=int, default=288, help="Max host files to retain")
        if mode == "collect":
            p.add_argument("--full", action="store_true", help="Include PGIntel slow/size classes")
        else:
            p.add_argument("--host-interval", type=int, default=300,
                           help="Host sampling seconds; PGIntel keeps its own SQL cadence")
    opts = parser.parse_args(argv)
    try:
        cfg = load_config(opts.config)
        interval = opts.host_interval if opts.mode == "run" else 300
        observer = HostObserver(cfg.instance_name, opts.host_dir or default_host_dir(),
                                interval=interval, keep=opts.host_keep)
        if opts.mode == "run":
            run_forever(cfg, on_cycle=observer)
        else:
            cycle = collect_once(cfg, collect_slow=opts.full, collect_sizes=opts.full)
            saved = observer.capture(cycle)
            print(json.dumps({
                "status": "ok", "instance": cfg.instance_name,
                "host_report": str(saved), "pgintel_cycle": {
                    k: cycle[k] for k in _CYCLE_KEYS if k in cycle
                }, "read_only_source": True,
            }, default=str, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as ex:
        # Avoid echoing source DSN, pgpass, SQL texts or connection errors.
        print(f"dboss: unified observation failed ({type(ex).__name__}); "
              "verify config, repository permissions and private host directory.",
              file=sys.stderr)
        return 1
