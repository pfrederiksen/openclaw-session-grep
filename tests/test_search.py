from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw_session_grep.search import SearchOptions, make_excerpt, parse_window, search


FIXTURES = Path(__file__).parent / "fixtures"


class SearchTests(unittest.TestCase):
    def test_plain_text_search_is_case_insensitive(self) -> None:
        hits = search(SearchOptions(query="MORNING BRIEFING", roots=(FIXTURES,)))

        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].record.session, "alpha")
        self.assertIn("morning briefing", hits[0].excerpt.lower())

    def test_filter_combination_channel_agent_and_tool(self) -> None:
        hits = search(
            SearchOptions(
                query="briefing",
                roots=(FIXTURES,),
                agent="main",
                channel="telegram",
                tool="message",
                tool_only=True,
            )
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].record.tool_name, "message")
        self.assertEqual(hits[0].record.message_type, "tool")

    def test_regex_mode(self) -> None:
        hits = search(SearchOptions(query=r"network\s+timeout", roots=(FIXTURES,), regex=True, tool_only=True))

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].record.session, "beta")
        self.assertEqual(hits[0].record.tool_name, "shell")

    def test_excerpt_generation_centers_match(self) -> None:
        text = "alpha " * 20 + "needle phrase " + "omega " * 20

        excerpt = make_excerpt(text, "needle phrase", regex=False, case_sensitive=False, width=60)

        self.assertIn("needle phrase", excerpt)
        self.assertTrue(excerpt.startswith("..."))
        self.assertTrue(excerpt.endswith("..."))

    def test_date_window_filter(self) -> None:
        since = parse_window("2026-04-11T00:00:00Z", now=datetime(2026, 4, 12, tzinfo=timezone.utc))

        hits = search(SearchOptions(query="timeout", roots=(FIXTURES,), since=since, channel="cli"))

        self.assertEqual(len(hits), 2)
        self.assertEqual({hit.record.session for hit in hits}, {"beta"})

    def test_context_records(self) -> None:
        hits = search(SearchOptions(query="gather headlines", roots=(FIXTURES,), context=1))

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].before[0].message_type, "user")
        self.assertEqual(hits[0].after[0].tool_name, "message")


if __name__ == "__main__":
    unittest.main()
