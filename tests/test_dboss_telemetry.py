"""Regression tests for a single SQL collector + private Linux/ZFS snapshots."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from dboss.cli import main
from dboss.telemetry import HostObserver, private_dir


class HostHistoryTests(unittest.TestCase):
    def test_private_snapshot_and_bounded_retention(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "history"
            observer = HostObserver("lab", path, interval=300, keep=2)
            with patch("dboss.telemetry.collect_host", return_value={"zfs_arc": {"size": 512}}):
                first = observer.capture({"server_major": 18, "unknown": "secret"})
                second = observer.capture()
                third = observer.capture()
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())
            self.assertTrue(third.exists())
            self.assertEqual(len(list(path.glob("dboss-host-*.json"))), 2)
            self.assertEqual(os.stat(third).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o700)
            payload = json.loads(third.read_text())
            self.assertEqual(payload["host"]["zfs_arc"]["size"], 512)
            self.assertNotIn("secret", third.read_text())
            self.assertTrue(payload["read_only_source"])

    def test_interval(self):
        with tempfile.TemporaryDirectory() as td:
            clock = [100.0]
            observer = HostObserver("lab", Path(td)/"history",
                                    interval=300, clock=lambda: clock[0])
            with patch("dboss.telemetry.collect_host", return_value={"memory_bytes": {}}) as host:
                observer({"server_major": 18})
                clock[0] = 200.0
                observer({"server_major": 18})
                clock[0] = 400.0
                observer({"server_major": 18})
            self.assertEqual(host.call_count, 2)

    def test_reject_insecure_directory(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "unsafe"
            path.mkdir(mode=0o777)
            path.chmod(0o755)
            with self.assertRaises(ValueError):
                private_dir(path)
            link = Path(td) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                private_dir(link)

    def test_collect_uses_one_pgintel_sql_cycle(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = SimpleNamespace(instance_name="lab")
            with patch("dboss.telemetry.load_config", return_value=cfg), \
                 patch("dboss.telemetry.collect_once", return_value={"server_major": 18}) as sql, \
                 patch("dboss.telemetry.collect_host", return_value={"zfs_arc": {}}) as host:
                with redirect_stdout(io.StringIO()) as out:
                    rc = main(["collect", "-c", "lab.ini", "--host-dir", str(Path(td)/"history")])
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(out.getvalue())["status"], "ok")
                sql.assert_called_once_with(cfg, collect_slow=False, collect_sizes=False)
                host.assert_called_once()

    def test_run_uses_existing_pgintel_scheduler(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = SimpleNamespace(instance_name="lab")
            with patch("dboss.telemetry.load_config", return_value=cfg), \
                 patch("dboss.telemetry.run_forever", return_value=None) as run:
                rc = main(["run", "--host-dir", str(Path(td)/"history")])
            self.assertEqual(rc, 0)
            run.assert_called_once()
            self.assertIsInstance(run.call_args.kwargs["on_cycle"], HostObserver)


if __name__ == "__main__":
    unittest.main()
