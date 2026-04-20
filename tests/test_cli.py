from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from openclaw_session_grep.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


class CliTests(unittest.TestCase):
    def test_cli_json_output(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(["timeout", "--path", str(FIXTURES), "--json", "--tool-only"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["tool"], "shell")

    def test_cli_count_only(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(["briefing", "--path", str(FIXTURES), "--channel", "telegram", "--count-only"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "3")


if __name__ == "__main__":
    unittest.main()

