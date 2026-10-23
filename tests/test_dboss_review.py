"""Offline review CLI: synthetic fixtures, no PostgreSQL dependency."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from dboss.cli import main as dboss_main
from dboss.review import read_advice, render_advice


def example():
    return {
        "mode": "smart-cache-advisor", "read_only": True,
        "actions_taken": [], "database": "erp", "intervals_analyzed": 1,
        "source_identity_verified": False, "confidence": "exploratory",
        "candidates": [{
            "kind": "index", "schemaname": "public", "relname": "recnfe",
            "indexrelname": "rcnf_idnfe_tipodcto_idx", "classification": "investigate",
            "missed_blocks": 8419, "postgres_buffer_hit_ratio": 0.54526,
        }],
    }


class ReviewTests(unittest.TestCase):
    def test_read_and_review_without_extra_sql(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "advice.json"
            path.write_text(json.dumps(example()), encoding="utf-8")
            result = read_advice(path)
            self.assertEqual(result["database"], "erp")
            with redirect_stdout(io.StringIO()) as buf:
                self.assertEqual(dboss_main(["review", "--advice", str(path)]), 0)
            output = buf.getvalue()
            self.assertIn("rcnf_idnfe_tipodcto_idx", output)
            self.assertIn("54.5%", output)
            self.assertIn("identidade", output.lower())
            self.assertIn("Nenhuma acao", output)

    def test_reject_non_readonly_or_malformed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "advice.json"
            bad = example()
            bad["actions_taken"] = ["pg_prewarm"]
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_advice(path)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(dboss_main(["review", "--advice", str(path)]), 1)

    def test_no_control_character_in_terminal(self):
        doc = example()
        doc["candidates"][0]["relname"] = "recnfe\x1b[31m"
        self.assertNotIn("\x1b", render_advice(doc))
        self.assertIn("investigacao=1", render_advice(doc))

    def test_limit(self):
        with self.assertRaises(ValueError):
            render_advice(example(), limit=0)


if __name__ == "__main__":
    unittest.main()
