"""New DBOSS dispatch tests; no running database is needed."""
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from dboss.cli import main

class TestDispatch(unittest.TestCase):
    def test_help(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--help"]), 0)
            self.assertIn("DBOSS", out.getvalue())

    def test_version(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--version"]), 0)
            self.assertIn("0.1.0", out.getvalue())

    def test_unknown(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["nonsense"]), 2)

    def test_host_dispatch(self):
        with patch("dbos.cli.main", return_value=42) as call:
            self.assertEqual(main(["host", "--output", "/dev/null"]), 42)
            call.assert_called_once_with(["host", "--output", "/dev/null"])

    def test_legacy_pgintel_dispatch(self):
        with patch("pgintel.cli.main", return_value=42) as call:
            self.assertEqual(main(["monitor", "-c", "legacy.ini", "check"]), 42)
            call.assert_called_once_with(["-c", "legacy.ini", "check"])

if __name__ == "__main__":
    unittest.main()
