from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .search import SearchHit, SearchOptions, default_roots, parse_window, search


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openclaw-session-grep",
        description="Search local OpenClaw session transcript files.",
    )
    parser.add_argument("query", nargs="?", help="Keyword or regex to search for.")
    parser.add_argument("-p", "--path", action="append", type=Path, help="File or directory to search. Repeatable.")
    parser.add_argument("--agent", help="Filter by agent id.")
    parser.add_argument("--channel", help="Filter by channel.")
    parser.add_argument("--last", help="Only include records after a relative window, e.g. 7d, 24h, 30m.")
    parser.add_argument("--since", help="Only include records at or after this ISO timestamp.")
    parser.add_argument("--until", help="Only include records at or before this ISO timestamp.")
    parser.add_argument("--model", help="Filter by model.")
    parser.add_argument("--tool", help="Filter by exact tool name.")
    parser.add_argument("--session", help="Filter by session key or label.")
    parser.add_argument(
        "--type",
        choices=("assistant", "user", "tool", "system"),
        dest="message_type",
        help="Filter to assistant, user, tool, or system messages.",
    )
    parser.add_argument("--tool-only", action="store_true", help="Only include records with a tool name.")
    parser.add_argument("--regex", action="store_true", help="Treat query as a regular expression.")
    parser.add_argument("--case-sensitive", action="store_true", help="Make matching case-sensitive.")
    parser.add_argument("-C", "--context", type=int, default=0, help="Show N transcript records before and after each hit.")
    parser.add_argument("--usage", action="store_true", help="Include usage/cost fields when present.")
    parser.add_argument("--json", action="store_true", help="Emit JSON array output.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown output.")
    parser.add_argument("--count-only", action="store_true", help="Only print the number of hits.")
    parser.add_argument("--summary", action="store_true", help="Group hit counts by session.")
    parser.add_argument("--open", action="store_true", dest="show_source", help="Print source file path and line reference.")
    parser.add_argument("--limit", type=int, help="Stop after N hits.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.query and not any([args.tool, args.session, args.agent, args.channel, args.model, args.message_type, args.tool_only]):
        parser.error("query or at least one structured filter is required")

    now = datetime.now(timezone.utc)
    try:
        since = parse_window(args.since, now) if args.since else None
        if args.last:
            since = parse_window(args.last, now)
        until = parse_window(args.until, now) if args.until else None
    except ValueError as exc:
        parser.error(str(exc))

    roots = tuple(args.path) if args.path else default_roots()
    options = SearchOptions(
        query=args.query,
        roots=roots,
        agent=args.agent,
        channel=args.channel,
        since=since,
        until=until,
        model=args.model,
        tool=args.tool,
        session=args.session,
        message_type=args.message_type,
        regex=args.regex,
        case_sensitive=args.case_sensitive,
        context=max(args.context, 0),
        tool_only=args.tool_only,
        include_usage=args.usage,
        limit=args.limit,
    )

    try:
        hits = search(options)
    except Exception as exc:
        print(f"openclaw-session-grep: {exc}", file=sys.stderr)
        return 2

    if args.count_only:
        print(len(hits))
    elif args.summary:
        print_summary(hits)
    elif args.json:
        print(json.dumps([hit_to_dict(hit, args.usage, args.show_source) for hit in hits], indent=2, sort_keys=True))
    elif args.markdown:
        print_markdown(hits, args.usage, args.show_source)
    else:
        print_terminal(hits, args.usage, args.show_source)
    return 0


def hit_to_dict(hit: SearchHit, include_usage: bool, include_source: bool) -> dict[str, Any]:
    record = hit.record
    item: dict[str, Any] = {
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "session": record.session,
        "agent": record.agent or None,
        "channel": record.channel or None,
        "type": record.message_type or None,
        "model": record.model or None,
        "tool": record.tool_name or None,
        "excerpt": hit.excerpt,
    }
    if include_source:
        item["source"] = {"path": str(record.path), "line": record.line_number}
    if include_usage and record.usage:
        item["usage"] = record.usage
    if hit.before or hit.after:
        item["context"] = {
            "before": [context_record_to_dict(record) for record in hit.before],
            "after": [context_record_to_dict(record) for record in hit.after],
        }
    return item


def context_record_to_dict(record) -> dict[str, Any]:
    return {
        "line": record.line_number,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "type": record.message_type or None,
        "text": record.text,
        "tool": record.tool_name or None,
    }


def print_terminal(hits: list[SearchHit], include_usage: bool, include_source: bool) -> None:
    for hit in hits:
        record = hit.record
        timestamp = record.timestamp.isoformat() if record.timestamp else "unknown-time"
        fields = [
            timestamp,
            f"session={record.session}",
            f"agent={record.agent or '-'}",
            f"channel={record.channel or '-'}",
        ]
        if record.tool_name:
            fields.append(f"tool={record.tool_name}")
        if include_source:
            fields.append(f"{record.path}:{record.line_number}")
        print(" | ".join(fields))
        if include_usage and record.usage:
            print(f"  usage: {json.dumps(record.usage, sort_keys=True)}")
        for context in hit.before:
            print(f"  -{context.line_number}: {context.text}")
        print(f"  {hit.excerpt}")
        for context in hit.after:
            print(f"  +{context.line_number}: {context.text}")


def print_markdown(hits: list[SearchHit], include_usage: bool, include_source: bool) -> None:
    print("| Timestamp | Session | Agent | Channel | Tool | Excerpt |")
    print("| --- | --- | --- | --- | --- | --- |")
    for hit in hits:
        record = hit.record
        timestamp = record.timestamp.isoformat() if record.timestamp else ""
        tool = record.tool_name
        excerpt = hit.excerpt.replace("|", "\\|")
        if include_source:
            excerpt = f"{excerpt}<br>`{record.path}:{record.line_number}`"
        if include_usage and record.usage:
            excerpt = f"{excerpt}<br>`usage={json.dumps(record.usage, sort_keys=True)}`"
        print(f"| {timestamp} | {record.session} | {record.agent} | {record.channel} | {tool} | {excerpt} |")


def print_summary(hits: list[SearchHit]) -> None:
    counts = Counter(hit.record.session for hit in hits)
    tools: dict[str, Counter[str]] = defaultdict(Counter)
    for hit in hits:
        if hit.record.tool_name:
            tools[hit.record.session][hit.record.tool_name] += 1
    for session, count in counts.most_common():
        suffix = ""
        if tools[session]:
            top_tools = ", ".join(f"{tool}={n}" for tool, n in tools[session].most_common(3))
            suffix = f" tools: {top_tools}"
        print(f"{session}\t{count}{suffix}")


if __name__ == "__main__":
    raise SystemExit(main())

