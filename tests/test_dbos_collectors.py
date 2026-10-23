import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dbos.collectors import collect_host, parse_arcstats, parse_meminfo, require_postgresql_18, INFO_SQL
from dbos.cli import main


class CollectorTests(unittest.TestCase):
    def test_pg18_major_version_gate(self):
        for ver in (180000, 180001, 180006, 189999):
            require_postgresql_18(ver)
        for ver in (160015, 170006, 190000):
            with self.assertRaises(RuntimeError):
                require_postgresql_18(ver)

    def test_pg18_io_config_reporting(self):
        self.assertIn("current_setting('io_method')", INFO_SQL)
        self.assertIn("current_setting('io_max_concurrency')", INFO_SQL)

    def test_parse_arcstats(self):
        raw = "13 1 0x01 50 300 1234\nname                            type data\nsize                            4 8388608\nhits 4 17\nmisses 4 3\n"
        stats = parse_arcstats(raw)
        self.assertEqual(stats["size"], 8388608)
        self.assertEqual(stats["hits"], 17)

    def test_meminfo_units(self):
        self.assertEqual(parse_meminfo("MemTotal: 1024 kB\nSwapTotal: 0 kB\n")["MemTotal"], 1048576)

    def test_host_without_zfs(self):
        with tempfile.TemporaryDirectory() as temp:
            memory = Path(temp) / "meminfo"
            memory.write_text("MemTotal: 1024 kB\nMemAvailable: 500 kB\n")
            with patch("dbos.collectors.command_lines", return_value=(None, "command_not_found")):
                data = collect_host(arc_path=Path(temp) / "absent", mem_path=memory)
        self.assertTrue(data["read_only"])
        self.assertEqual(data["zfs_arc_status"], "unavailable")
        self.assertEqual(data["memory_bytes"]["MemTotal"], 1048576)

    def test_cli_host(self):
        with patch("dbos.cli.collect_host", return_value={"read_only": True}):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "host.json"
                self.assertEqual(main(["host", "--output", str(path)]), 0)
                doc = json.loads(path.read_text())
                self.assertTrue(doc["host"]["read_only"])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                # Reports may contain operational details: refuse overwrite.
                self.assertEqual(main(["host", "--output", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
