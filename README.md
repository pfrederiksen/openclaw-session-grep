# openclaw-session-grep

`openclaw-session-grep` is a small CLI for quickly searching local OpenClaw session and transcript files. It is meant for finding prior conversations, tool usage, errors, expensive model runs, channel-specific history, and session labels without manually opening JSONL files.

It stays deliberately narrow: fast transcript search with useful filters, not an analytics database.

## Install

```bash
pipx install openclaw-session-grep
```

For local development:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Where It Searches

By default, the CLI searches these locations if they exist:

- `$OPENCLAW_SESSION_DIR`
- `$OPENCLAW_TRANSCRIPT_DIR`
- `~/.openclaw/sessions`
- `~/.openclaw/transcripts`
- `~/.openclaw`

`OPENCLAW_SESSION_DIR` and `OPENCLAW_TRANSCRIPT_DIR` may contain multiple paths separated with your platform path separator. You can also pass `--path` one or more times to search specific files or directories.

Candidate files currently use these extensions: `.jsonl`, `.json`, `.log`, and `.ndjson`.

## Examples

```bash
openclaw-session-grep "morning briefing"
openclaw-session-grep "timeout" --channel telegram --last 7d
openclaw-session-grep "message tool" --agent main --json
openclaw-session-grep "network\\s+timeout" --regex --tool-only
openclaw-session-grep --tool shell --summary
openclaw-session-grep "briefing" --context 2 --open
```

## Filters

- `--agent main`
- `--channel telegram`
- `--last 7d`, `--last 24h`, `--since 2026-04-10T00:00:00Z`, `--until ...`
- `--model gpt-5.4`
- `--tool message`
- `--session alpha`
- `--type assistant|user|tool|system`
- `--tool-only`

Search is case-insensitive by default. Use `--case-sensitive` to change that, and `--regex` to treat the query as a Python regular expression.

## Output Modes

Default terminal output includes timestamp, session, agent, channel, optional tool name, and a short excerpt.

Other modes:

```bash
openclaw-session-grep "timeout" --json
openclaw-session-grep "timeout" --markdown
openclaw-session-grep "timeout" --count-only
openclaw-session-grep "timeout" --summary
```

Use `--usage` to include usage/cost fields when present in the transcript record. Use `--open` to include `path:line` references.

## Transcript Format

OpenClaw transcript schemas may vary, so the parser is intentionally tolerant. It reads newline-delimited JSON and extracts common fields such as:

- timestamp: `timestamp`, `time`, `created_at`, `createdAt`, `ts`
- session: `session_key`, `sessionKey`, `session`, `label`, `conversation_id`
- agent: `agent`, `agent_id`, `agentId`, `role`
- channel: `channel`, `source`, `transport`
- message type: `type`, `kind`, `role`
- model: `model`, `model_name`, `modelName`
- tool: `tool`, `tool_name`, `toolName`, `tool.name`, `function.name`, first `tool_calls[]`
- usage/cost: `usage`, `cost`, `token_usage`, `tokenUsage`

Malformed JSON lines are treated as plain text records so older logs can still be searched.

## Performance Notes

The utility streams candidate files by path, then loads one transcript file at a time to support context records around each hit. That keeps memory bounded by the largest single transcript file rather than the whole transcript directory.

For large stores, pass a narrower `--path`, combine structured filters, or use `--limit` when you only need the first few hits.

## Known Limitations

- There is no persistent index; every invocation scans files.
- Date filters skip records without timestamps instead of rejecting them.
- Tool and structured filters are exact matches.
- JSON object files that are not line-delimited are not recursively unpacked as full transcript arrays yet.

## Development

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests
```

Sample fixtures live in `tests/fixtures`.

## Releases

Tagged releases use GitHub Actions:

- `v*` tags build and publish distributions to PyPI using PyPI trusted publishing.
- The Homebrew workflow updates `pfrederiksen/homebrew-tap` with a formula that installs from the PyPI source distribution.

Do not commit PyPI tokens. Configure PyPI trusted publishing for this repository, or store credentials as GitHub Actions secrets if you choose a different release strategy.
