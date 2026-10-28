# Time log automation — design

## Goal

The user's hours on every project under the projects root land in `timelog.csv` without
relying on memory, accurate enough to invoice from. Success: every working day with Claude
activity under the root reaches the CSV within a day, confirmed by the user.

## Decisions

- **Scope**: every session whose `cwd` is under the projects root (`$TIMELOG_ROOT`, default
  `~/projects`), at any depth.
- **Client = top-level directory** of the root. Hours measure the value delivered to each
  client, so parallel work across clients is not split: each client's day is the union of
  that client's own sessions, and client totals add up even when they ran at the same time.
  Within one client, parallel sessions are one hour on the clock and count once.
- **Project = directory, not judgement**: a client that is a git repo is its own project
  (`solo`); a client that is a directory of repos has one project per repo (`acme/web`), a
  worktree counting as its main repository. Anything else is the client alone (`acme`).
- **Gap threshold 20 minutes**: a pause up to 20 min between two records of a session is
  work; a longer one is a break.
- **Confirmation is daily**: a reminder in every new session while a past day is
  unconfirmed.
- **Hours are the user's number**: the system proposes, the user confirms; nothing is
  written to the CSV without an explicit "ok".
- **The log is never in the code repo**: it lives in its own git repo, `$TIMELOG_DATA`
  (default `<root>/timelog-data`), never published.

## Components

| File | Role |
|---|---|
| `$TIMELOG_DATA/timelog.csv` | `date,project,hours,task` with a header row; ISO dates; hours in 0.25 steps; free text last so commas need no quoting. |
| `$TIMELOG_DATA/.confirmed` | One line, `YYYY-MM-DD`: every day up to and including it is confirmed. |
| `timelog.py` | Reads transcripts. `hook` prints the one-line notice; `draft [SINCE]` prints the per-session draft for Claude; `test` runs the self-check. Never writes the CSV. |
| `hooks/hooks.json` | A `SessionStart` hook (no matcher, so every session source; timeout 60 s: a 30-day backlog takes about 12 s) running `/usr/bin/python3 -I timelog.py hook` (an absolute interpreter: pyenv's `python3` follows a repo's `.python-version`). |
| `skills/timelog/SKILL.md` | The `/timelog` procedure Claude follows: one manual row with arguments, confirming the unconfirmed days without. |

## Flow

1. A session starts.
2. The hook exits silently unless all hold: `CLAUDE_CODE_ENTRYPOINT` does not start with
   `sdk-` (automated reviews run as `sdk-py` / `sdk-cli`), `cwd` is under the root, and
   some day after the marker and before today has activity under the root.
3. Otherwise it prints `{"systemMessage": "⏱ unconfirmed: 07.10 ≈1.1 h, 08.10 ≈7.4 h — /timelog"}`
   (per day: the sum of client totals). The message is shown to the user.
4. The notice repeats in every new session until the days are confirmed.
5. On `/timelog` without arguments Claude runs `draft`, builds the rows, shows them, and on
   "ok" appends them, moves the marker to the draft's last day and commits.

## `timelog.py`

Constants: `ROOT` (`$TIMELOG_ROOT`), `DATA` (`$TIMELOG_DATA`), `GAP = 20 min`, transcripts
at `$CLAUDE_CONFIG_DIR/projects/*/*.jsonl` (default `~/.claude`; top-level threads only,
`subagents/` excluded).

**Collection.** Read only files whose mtime is after the start of the day following the
start day (`SINCE` or the marker). A session's directory is the `cwd` of its first record
that has one; a session outside `ROOT`, or at `ROOT` itself, is dropped. Only records with a `timestamp` count; timestamps
convert to local time. Records of subtype `away_summary` do not count: Claude Code writes
them about 3 minutes after a turn, while the user is idle, so they would bridge breaks. Records dated on or before the start day are dropped, so a session
resumed across the marker contributes only its new days. A line that fails to parse is
skipped. The session title is its last `aiTitle`; the first prompt is the first `user`
record with string content that does not start with `<`.

**Client.** The first path component of `cwd` under `ROOT`.

**Project.** The client alone when `cwd` is the client directory or the client is a git
repo. Otherwise `git rev-parse --git-common-dir` in `cwd` names the main repository (the
same for a worktree); a repository inside the client gives `client/<its first path
component under the client>`. A directory git does not know, or one that no longer exists,
is the client alone.

**Time.** Within a session, sorted by time, each pair of consecutive timestamps no more than
`GAP` apart is an active interval. An interval belongs to the local date it starts on; a day
has activity when it has at least one interval, and is complete `GAP` after midnight (an
interval from 23:50 may still close at 00:10), so "today" in `draft` and `hook` is the date
of now minus `GAP`. Per day and client:
the client total is the union of that client's intervals; each session's share is its own
union scaled by `client total / sum of the client's session unions`, so shares add up to the
client total. The day's wall-clock time (the union over all clients) is printed for
reference only.

**`draft [SINCE]`.** Days from `SINCE` (default: marker) exclusive to yesterday inclusive,
skipping days without activity. Per day: wall-clock time; then per client: its total, the
CSV rows already present for that date and client, and one line per session: share in
hours, project, `cwd` relative to `ROOT`, title, first 80 chars of the first prompt. Errors
raise normally.

**`hook`.** Reads the hook JSON from stdin (uses `cwd`), applies the filters in Flow §2,
prints the notice or nothing. Any exception, a missing marker included, prints
`{"systemMessage": "⏱ timelog: script error (<the exception>) — /timelog"}` and exits 0, so a session start
is never blocked and a broken reminder is never silent.

**`test`.** Assert-based self-check on synthetic timestamps: two overlapping sessions of
one client count once; two overlapping sessions of different clients count for each; gaps
just under and over `GAP`; an interval crossing midnight; the transcript shape `collect()`
reads; project names for a repo client, a directory of repos, a worktree and a directory
git does not know.

## `/timelog`

The procedure is [`skills/timelog/SKILL.md`](../skills/timelog/SKILL.md). Claude names
nothing the draft already names: it only attributes a client-alone session in a directory
of repos to one of the repos when the session clearly names it, splits each client's
rounded total among projects, and writes the task text.

## Known limits

- Transcripts are deleted after 30 days; a day left unconfirmed longer is lost. The daily
  notice makes this unlikely; no separate warning.
- Only time with Claude is measured. Calls, chat and reading outside sessions are added by
  the user.
- By design, a day's CSV total can exceed its wall-clock time when clients ran in parallel.
- Automated review sessions still count toward time (they run inside active periods and
  last minutes); only the notice skips them.
- Renaming or moving a directory changes the project name of later sessions; earlier rows
  keep the old one.
