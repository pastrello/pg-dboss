import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dbos.analytics import analyze_snapshots, inspect_snapshots, read_snapshot
from dbos.cli import main


class AnalysisTests(unittest.TestCase):
    def sample(self, time, scans, misses, resets="2026-10-23T00:00:00+00:00"):
        relation = {"relid": 12, "schemaname": "erp", "relname": "pendfin", "seq_scan": scans,
                    "idx_scan": 4, "seq_tup_read": scans * 100, "idx_tup_fetch": 10,
                    "heap_blks_read": misses, "heap_blks_hit": scans * 10,
                    "idx_blks_read": 3, "idx_blks_hit": 20}
        return {"captured_at": time, "mode": "probe", "read_only": True,
                "postgres": {"server": {"server_version": "18.1", "database": "erp",
                                        "server_data_directory": "/db/18", "database_stats_reset": resets,
                                        "started_at": "2026-10-22T00:00:00+00:00"},
                             "relation_counters": [relation], "index_counters": [],
                             "relation_counters_complete": True, "index_counters_complete": True,
                             "pg_stat_io": [{"backend_type": "client backend", "object": "relation",
                                             "context": "normal", "reads": scans, "writes": 0,
                                             "hits": scans * 10, "evictions": 0, "fsyncs": 0,
                                             "stats_reset": resets}],
                             "database_io": {"blks_read": misses, "blks_hit": scans * 10,
                                             "xact_commit": scans, "xact_rollback": 0}},
                "host": {"zfs_arc": {"hits": scans * 100, "misses": misses, "size": 1024}}}

    def test_valid_delta_and_pg_cache_ratio(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7)
        result = analyze_snapshots(a, b)
        top = result["postgres"]["relations"]["top_by_buffer_misses"][0]
        self.assertEqual(top["deltas"]["heap_blks_read"], 4)
        self.assertEqual(top["deltas"]["seq_scan"], 20)
        self.assertEqual(result["arc"]["interval_hits"], 2000)
        self.assertEqual(result["postgres"]["database_io_deltas"]["xact_commit"], 20)
        self.assertEqual(result["postgres"]["cluster_io_deltas"][0]["deltas"]["reads"], 20)

    def test_stats_reset_refuses_comparison(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7, "2026-10-23T01:00:30+00:00")
        with self.assertRaisesRegex(ValueError, "database_stats_reset"):
            analyze_snapshots(a, b)

    def test_both_null_stats_reset_are_accepted_if_start_time_is_same(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3, None)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7, None)
        report = analyze_snapshots(a, b)
        self.assertEqual(report["postgres"]["relations"]["top_by_buffer_misses"][0]["deltas"]["heap_blks_read"], 4)
        self.assertTrue(any("database_stats_reset is NULL" in w for w in report["warnings"]))

    def test_missing_stats_reset_key_is_rejected(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3, None)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7, None)
        del a["postgres"]["server"]["database_stats_reset"]
        with self.assertRaisesRegex(ValueError, "database_stats_reset field missing"):
            analyze_snapshots(a, b)
        a["postgres"]["server"]["database_stats_reset"] = None
        del b["postgres"]["server"]["database_stats_reset"]
        with self.assertRaisesRegex(ValueError, "database_stats_reset field missing"):
            analyze_snapshots(a, b)

    def test_null_and_non_null_reset_are_rejected(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3, None)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7)
        with self.assertRaisesRegex(ValueError, "database_stats_reset changed"):
            analyze_snapshots(a, b)

    def test_null_reset_on_postgres_restart_is_rejected(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3, None)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7, None)
        b["postgres"]["server"]["started_at"] = "2026-10-23T01:00:15+00:00"
        with self.assertRaisesRegex(ValueError, "started_at changed"):
            analyze_snapshots(a, b)

    def test_null_reset_without_start_time_is_rejected(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3, None)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7, None)
        del b["postgres"]["server"]["started_at"]
        with self.assertRaisesRegex(ValueError, "started_at changed or missing"):
            analyze_snapshots(a, b)

    def test_null_reset_negative_counter_still_excluded(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 50, 10, None)
        b = self.sample("2026-10-23T01:01:00+00:00", 2, 3, None)
        report = analyze_snapshots(a, b)
        self.assertEqual(report["postgres"]["relations"]["compared"], 0)
        self.assertEqual(report["postgres"]["relations"]["skipped_new_or_reset"], 1)

    def test_legacy_pg_rejected_for_deltas(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7)
        b["postgres"]["server"]["server_version"] = "14.24"
        with self.assertRaisesRegex(ValueError, "PG18"):
            analyze_snapshots(a, b)

    def test_oid_reuse_excluded(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7)
        b["postgres"]["relation_counters"][0]["relname"] = "another"
        self.assertEqual(analyze_snapshots(a, b)["postgres"]["relations"]["compared"], 0)

    def test_negative_counters_not_used(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 50, 10)
        b = self.sample("2026-10-23T01:01:00+00:00", 2, 3)
        report = analyze_snapshots(a, b)
        self.assertEqual(report["postgres"]["relations"]["skipped_new_or_reset"], 1)
        self.assertIsNone(report["arc"]["interval_hits"])

    def test_inspect_legacy_and_warning(self):
        host = {"captured_at": "2026-10-23T01:00:00+00:00", "host": {
            "kernel": "5.14", "memory_bytes": {"MemTotal": 100, "MemAvailable": 5},
            "zfs_arc": {"size": 90, "compressed_size": 20, "uncompressed_size": 60}}}
        pg = {"captured_at": "2026-10-23T01:00:00+00:00", "postgres": {
            "server": {"server_version": "14.24", "database": "erp"}, "top_tables": []}}
        result = inspect_snapshots(host, pg)
        self.assertIn("14", " ".join(result["notices"]))
        self.assertEqual(result["arc"]["compressed_data_ratio"], 3)
        self.assertEqual(result["actions_taken"], [])

    def test_offline_cli_and_private_output(self):
        a = self.sample("2026-10-23T01:00:00+00:00", 10, 3)
        b = self.sample("2026-10-23T01:01:00+00:00", 30, 7)
        with tempfile.TemporaryDirectory() as root:
            old, new, out = (Path(root) / n for n in ("a.json", "b.json", "result.json"))
            old.write_text(json.dumps(a))
            new.write_text(json.dumps(b))
            self.assertEqual(main(["analyze", "--before", str(old), "--after", str(new), "--output", str(out)]), 0)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(out.read_text())["analysis"]["interval_seconds"], 60)
            self.assertEqual(main(["analyze", "--before", str(old), "--after", str(new), "--output", str(out)]), 1)

    def test_bad_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "bad.json"
            p.write_text('{"captured_at":"2026-10-23T01:00:00Z"}')
            with self.assertRaises(ValueError):
                read_snapshot(p)


if __name__ == "__main__":
    unittest.main()
