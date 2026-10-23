"""Synthetic offline advisor tests. Never connect to a database."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from dboss.advisor import advise, main, read_interval


def interval(start, end, read=8419, hit=10095):
    return {
        "read_only": True, "actions_taken": [], "interval_seconds": 3600,
        "before": start, "after": end,
        "postgres": {"database": "erp", "version": "18.6",
                     "relations": {"top_by_buffer_misses": [{
                         "relid": 12, "schemaname": "public", "relname": "pendfin",
                         "deltas": {"idx_scan": 2, "seq_scan": 0, "heap_blks_read": 3000,
                                    "heap_blks_hit": 4000, "idx_blks_read": 10,
                                    "idx_blks_hit": 100},
                     }]},
                     "indexes": {"top_by_buffer_misses": [{
                         "indexrelid": 123, "schemaname": "public", "relname": "recnfe",
                         "indexrelname": "rcnf_idx",
                         "deltas": {"idx_scan": 200, "idx_blks_read": read,
                                    "idx_blks_hit": hit},
                     }]}}
    }


class AdvisorTests(unittest.TestCase):
    def test_classification_is_not_an_action(self):
        x = interval("2026-10-23T10:00:00+00:00", "2026-10-23T11:00:00+00:00")
        report = advise([x])
        self.assertTrue(report["read_only"])
        self.assertEqual(report["actions_taken"], [])
        self.assertEqual(report["confidence"], "exploratory")
        self.assertFalse(report["source_identity_verified"])
        idx = next(c for c in report["candidates"] if c["kind"] == "index")
        self.assertEqual(idx["classification"], "investigate")
        self.assertEqual(idx["missed_blocks"], 8419)
        self.assertEqual(idx["postgres_buffer_hit_ratio"], 0.54526)

    def test_reject_multiple_without_identity_assertion(self):
        a = interval("2026-10-23T10:00:00+00:00", "2026-10-23T11:00:00+00:00")
        b = interval("2026-10-23T12:00:00+00:00", "2026-10-23T13:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "assume-same-source"):
            advise([a,b])
        report = advise([a,b], assume_same_source=True)
        idx = next(c for c in report["candidates"] if c["kind"] == "index")
        self.assertEqual(idx["observed_intervals"], 2)
        self.assertEqual(idx["missed_blocks"], 16838)

    def test_overlap_rejected(self):
        a = interval("2026-10-23T10:00:00+00:00", "2026-10-23T11:00:00+00:00")
        b = interval("2026-10-23T10:30:00+00:00", "2026-10-23T11:30:00+00:00")
        with self.assertRaisesRegex(ValueError, "overlapping"):
            advise([a,b], assume_same_source=True)

    def test_no_scan_index_not_automatically_unused(self):
        a = interval("2026-10-23T10:00:00+00:00", "2026-10-23T11:00:00+00:00")
        a["postgres"]["indexes"]["top_by_buffer_misses"][0]["deltas"]["idx_scan"] = 0
        idx = next(c for c in advise([a])["candidates"] if c["kind"] == "index")
        self.assertEqual(idx["classification"], "non_scan_activity")

    def test_invalid_actions_rejected(self):
        a = interval("2026-10-23T10:00:00+00:00", "2026-10-23T11:00:00+00:00")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"interval.json"
            path.write_text(json.dumps({
                "mode": "analyze", "analysis": {**a, "actions_taken": ["prewarm"]}
            }))
            with self.assertRaises(ValueError):
                read_interval(path)

    def test_cli_reads_only_existing_interval_json(self):
        a = interval("2026-10-23T10:00:00+00:00", "2026-10-23T11:00:00+00:00")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/"interval.json"
            path.write_text(json.dumps({"mode":"analyze", "analysis": a}))
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--interval", str(path)]), 0)
            self.assertEqual(json.loads(output.getvalue())["intervals_analyzed"], 1)


if __name__ == "__main__":
    unittest.main()
