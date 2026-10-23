"""Ensure optional host observer cannot terminate the legacy PGIntel scheduler."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pgintel.agent import run_forever


class CollectorHookTests(unittest.TestCase):
    def test_hook_runs_once_even_on_pg_source_error(self):
        cfg = SimpleNamespace(instance_name="lab", interval_seconds=60,
                              slow_interval_seconds=900, size_interval_seconds=3600,
                              max_source_cycle_seconds=20.0, query_text_mode="none")
        calls = []
        with patch("pgintel.agent.collect_once", side_effect=RuntimeError("unavailable")), \
             patch("pgintel.agent.time.sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_forever(cfg, on_cycle=calls.append)
        self.assertEqual(calls, [None])

    def test_legacy_call_remains_valid(self):
        cfg = SimpleNamespace(instance_name="lab", interval_seconds=60,
                              slow_interval_seconds=900, size_interval_seconds=3600,
                              max_source_cycle_seconds=20.0, query_text_mode="none")
        with patch("pgintel.agent.collect_once", return_value={
                 "server_major": 18, "database_rows": 1, "table_rows_stored": 0,
                 "table_rows": 0, "index_rows_stored": 0, "index_rows": 0,
                 "query_rows_stored": 0, "query_rows_seen": 0, "events_created": 0,
                 "events_suppressed": 0, "source_duration_ms": 1.0,
                 "cycle_duration_ms": 2.0, "budget_exceeded": False}), \
             patch("pgintel.agent.time.sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_forever(cfg)


if __name__ == "__main__":
    unittest.main()
