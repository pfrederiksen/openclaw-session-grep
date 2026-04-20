from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


TEXT_FIELDS = ("text", "content", "message", "output", "input", "error", "name")
SESSION_EXTENSIONS = {".jsonl", ".json", ".log", ".ndjson"}


@dataclass(frozen=True)
class SearchOptions:
    query: str | None = None
    roots: tuple[Path, ...] = ()
    agent: str | None = None
    channel: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    model: str | None = None
    tool: str | None = None
    session: str | None = None
    message_type: str | None = None
    regex: bool = False
    case_sensitive: bool = False
    context: int = 0
    tool_only: bool = False
    include_usage: bool = False
    limit: int | None = None


@dataclass(frozen=True)
class TranscriptRecord:
    path: Path
    line_number: int
    raw: dict[str, Any]
    timestamp: datetime | None
    session: str
    agent: str
    channel: str
    message_type: str
    text: str
    model: str
    tool_name: str
    usage: dict[str, Any] | None


@dataclass(frozen=True)
class SearchHit:
    record: TranscriptRecord
    excerpt: str
    before: tuple[TranscriptRecord, ...] = ()
    after: tuple[TranscriptRecord, ...] = ()


def default_roots() -> tuple[Path, ...]:
    values: list[Path] = []
    for env_name in ("OPENCLAW_SESSION_DIR", "OPENCLAW_TRANSCRIPT_DIR"):
        value = os.environ.get(env_name)
        if value:
            values.extend(Path(part).expanduser() for part in value.split(os.pathsep) if part)

    home = Path.home()
    values.extend(
        [
            home / ".openclaw" / "sessions",
            home / ".openclaw" / "transcripts",
            home / ".openclaw",
        ]
    )
    return tuple(dict.fromkeys(values))


def iter_candidate_files(roots: Sequence[Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        paths: Iterable[Path]
        if root.is_file():
            paths = (root,)
        else:
            paths = (path for path in root.rglob("*") if path.is_file())

        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            if path.suffix.lower() in SESSION_EXTENSIONS:
                yield path


def load_records(path: Path) -> list[TranscriptRecord]:
    records: list[TranscriptRecord] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    raw = {"type": "text", "text": line}
                if isinstance(raw, dict):
                    records.append(normalize_record(raw, path, line_number))
    except OSError:
        return []
    return records


def normalize_record(raw: dict[str, Any], path: Path, line_number: int) -> TranscriptRecord:
    timestamp = parse_datetime(first_value(raw, ("timestamp", "time", "created_at", "createdAt", "ts")))
    message = raw.get("message") if isinstance(raw.get("message"), dict) else {}
    session = str(
        first_value(
            raw,
            ("session_key", "sessionKey", "session", "label", "conversation_id", "conversationId"),
        )
        or first_value(message, ("session_key", "session", "label"))
        or path.stem
    )
    agent = str(first_value(raw, ("agent", "agent_id", "agentId", "role")) or first_value(message, ("agent", "role")) or "")
    channel = str(first_value(raw, ("channel", "source", "transport")) or first_value(message, ("channel",)) or "")
    message_type = str(first_value(raw, ("type", "kind", "role")) or first_value(message, ("type", "role")) or "")
    model = str(first_value(raw, ("model", "model_name", "modelName")) or first_value(message, ("model",)) or "")
    tool_name = extract_tool_name(raw)
    usage = extract_usage(raw)
    text = extract_text(raw)

    if not message_type and tool_name:
        message_type = "tool"

    return TranscriptRecord(
        path=path,
        line_number=line_number,
        raw=raw,
        timestamp=timestamp,
        session=session,
        agent=agent,
        channel=channel,
        message_type=message_type,
        text=text,
        model=model,
        tool_name=tool_name,
        usage=usage,
    )


def first_value(data: Any, keys: Sequence[str]) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def extract_tool_name(raw: dict[str, Any]) -> str:
    candidates = [
        first_value(raw, ("tool_name", "toolName")),
        first_value(raw.get("tool") if isinstance(raw.get("tool"), dict) else {}, ("name", "tool_name")),
        first_value(raw.get("function") if isinstance(raw.get("function"), dict) else {}, ("name",)),
    ]
    calls = raw.get("tool_calls") or raw.get("toolCalls")
    if isinstance(calls, list) and calls:
        first = calls[0]
        if isinstance(first, dict):
            candidates.extend(
                [
                    first_value(first, ("name", "tool_name", "toolName")),
                    first_value(first.get("function") if isinstance(first.get("function"), dict) else {}, ("name",)),
                ]
            )
    for value in candidates:
        if value:
            return str(value)
    return ""


def extract_usage(raw: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("usage", "cost", "token_usage", "tokenUsage"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return None


def extract_text(value: Any) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            parts.append(item)
            return
        if isinstance(item, (int, float, bool)):
            return
        if isinstance(item, list):
            for child in item:
                walk(child)
            return
        if isinstance(item, dict):
            for key in TEXT_FIELDS:
                if key in item:
                    walk(item[key])
            if not parts:
                for child in item.values():
                    if isinstance(child, (dict, list)):
                        walk(child)

    walk(value)
    return " ".join(part.strip() for part in parts if part.strip())


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_window(value: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    value = value.strip()
    match = re.fullmatch(r"(\d+)([smhdw])", value, flags=re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        deltas = {
            "s": timedelta(seconds=amount),
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
            "w": timedelta(weeks=amount),
        }
        return now - deltas[unit]
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValueError(f"invalid date/time window: {value}")
    return parsed


def search(options: SearchOptions) -> list[SearchHit]:
    matcher = build_matcher(options)
    hits: list[SearchHit] = []
    for path in iter_candidate_files(options.roots):
        records = load_records(path)
        for index, record in enumerate(records):
            if not passes_filters(record, options):
                continue
            if not matcher(record):
                continue
            start = max(0, index - options.context)
            end = min(len(records), index + options.context + 1)
            hit = SearchHit(
                record=record,
                excerpt=make_excerpt(record.text, options.query, options.regex, options.case_sensitive),
                before=tuple(records[start:index]),
                after=tuple(records[index + 1 : end]),
            )
            hits.append(hit)
            if options.limit is not None and len(hits) >= options.limit:
                return hits
    return hits


def build_matcher(options: SearchOptions):
    query = options.query
    if not query:
        return lambda record: True

    haystack_fields = lambda record: " ".join(
        part
        for part in (record.text, record.tool_name, record.session, record.agent, record.channel, record.model)
        if part
    )
    flags = 0 if options.case_sensitive else re.IGNORECASE
    if options.regex:
        pattern = re.compile(query, flags=flags)
        return lambda record: bool(pattern.search(haystack_fields(record)))

    needle = query if options.case_sensitive else query.lower()
    return lambda record: needle in (haystack_fields(record) if options.case_sensitive else haystack_fields(record).lower())


def passes_filters(record: TranscriptRecord, options: SearchOptions) -> bool:
    if options.agent and record.agent != options.agent:
        return False
    if options.channel and record.channel != options.channel:
        return False
    if options.model and record.model != options.model:
        return False
    if options.tool and record.tool_name != options.tool:
        return False
    if options.session and options.session not in {record.session, str(record.raw.get("label", ""))}:
        return False
    if options.message_type and record.message_type != options.message_type:
        return False
    if options.tool_only and not record.tool_name:
        return False
    if options.since and record.timestamp and record.timestamp < options.since:
        return False
    if options.until and record.timestamp and record.timestamp > options.until:
        return False
    return True


def make_excerpt(text: str, query: str | None, regex: bool, case_sensitive: bool, width: int = 160) -> str:
    clean = " ".join(text.split())
    if not clean:
        return ""
    start = 0
    end = min(len(clean), width)
    if query:
        flags = 0 if case_sensitive else re.IGNORECASE
        match = re.search(query if regex else re.escape(query), clean, flags=flags)
        if match:
            center = (match.start() + match.end()) // 2
            start = max(0, center - width // 2)
            end = min(len(clean), start + width)
            start = max(0, end - width)
    excerpt = clean[start:end]
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(clean):
        excerpt = excerpt + "..."
    return excerpt
