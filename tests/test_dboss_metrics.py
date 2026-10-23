"""Portability guards for the original DBOS 0.2.1 Python metrics."""
import unittest
from dbos.collectors import parse_arcstats, parse_meminfo, require_postgresql_18
from dbos.analytics import analyze_snapshots

class TestMetrics(unittest.TestCase):
    def test_arc(self):
        arc = parse_arcstats("13 1 0x01\nname type data\nhits 4 15\nmisses 4 5\n")
        self.assertEqual((arc["hits"], arc["misses"]), (15, 5))

    def test_meminfo(self):
        self.assertEqual(parse_meminfo("MemTotal: 1024 kB\n")["MemTotal"], 1048576)

    def test_pg18(self):
        require_postgresql_18(180006)
        with self.assertRaises(RuntimeError):
            require_postgresql_18(170019)

    def test_reject_bad_interval(self):
        first = {"captured_at": "2026-10-23T09:00:00+00:00"}
        last = {"captured_at": "2026-10-23T08:00:00+00:00"}
        with self.assertRaises(ValueError):
            analyze_snapshots(first, last)

if __name__ == "__main__":
    unittest.main()
