---
name: timelog
description: Confirm Claude-measured hours into the time log, or add one manual row
argument-hint: "[date] <task> <hours> [client or client/repo]; empty = confirm unconfirmed days"
---

Time log. Spec: `${CLAUDE_PLUGIN_ROOT}/docs/design.md`.

Arguments: $ARGUMENTS

Rules for both modes:
- Hours are the user's number: you propose; nothing is written to `timelog.csv` without an explicit "ok". A correction means: apply it, show the rows again, wait for "ok". The one exception is changing rows by their `#` ("ok, skip 3", "ok, 3 to general"): that already is the "ok", so write at once without showing the table again.
- Never copy hours anywhere else: no other repo, PR, artifact or client message.
- A row is `YYYY-MM-DD,project,hours,task`: hours in 0.25 steps with two decimals (`0.50`), the task last (commas need no quoting).
- Rows reach the file only through the quoted heredoc below, verbatim, never inside shell quotes: task text may contain `'` or `$(`.
- The projects root is `$TIMELOG_ROOT` (default `~/projects`); the log lives in `$TIMELOG_DATA` (default `<projects root>/timelog-data`), a git repo holding `timelog.csv` and `.confirmed`.

## With arguments: one manual row

The row is time without Claude. Parse the arguments in any order and form:
- **Date**: optional, default today; any form (`06.10`, `yesterday`).
- **Project**: default is the current session's client, the first directory of `cwd` under the projects root (`acme/web` → `acme`); if `cwd` is not inside a client directory, ask. `acme/<repo>` only when the repo is named explicitly, never guessed.
- **Hours**: required. If missing, ask; never fill them in.
- **Task**: the remaining words.

Show the row. On "ok":

```bash
cd "${TIMELOG_DATA:-${TIMELOG_ROOT:-$HOME/projects}/timelog-data}" && cat >> timelog.csv <<'ROWS' && git commit -q -m 'log: manual <YYYY-MM-DD>' -- timelog.csv
<row>
ROWS
```

No draft, no marker change, even for a day already confirmed.

## Without arguments: confirm the unconfirmed days

1. Run `/usr/bin/python3 -I "${CLAUDE_PLUGIN_ROOT}/timelog.py" draft`. Its first line is `range: after <marker> through <last day>`; keep both dates. No day lines: say there is nothing to confirm and stop. An error: show it and stop.
2. Each session line gives its share, its project, its `cwd`, title and first prompt. Take the project as given, except one that is just the client of a directory of repos (a session at its root, or in a directory git does not know, such as a deleted worktree): attribute it to one of that client's repos when its `cwd`, title or prompt clearly names one, otherwise keep the client alone. Group by project.
3. Per day and client: quarters = round(client total × 4); give each project floor(its share × 4) quarters, then hand the remaining quarters one at a time to the projects with the largest remainders; hours = quarters / 4. A project with 0 gets no row. Compute this with python, not in your head.
4. Write a short task description per row, from the session titles.
5. Lines marked `csv:` are rows already in the file: time without Claude that the user wrote. Keep them; never net them against the draft.
6. Show one table with a first column `#`, numbering the rows 1, 2, 3… continuously across days: every day and every client of the draft with its rows, the user's own tooling repos included: the log tracks all the user's time. "ok" confirms the whole draft; "ok, skip 3, 5" confirms it without those rows (their hours are dropped, not redistributed), and the day still counts as confirmed; "ok, 3 to general" keeps the row with its hours but changes its project to `general` (a project with no client; rows moved there on the same day merge into one row, hours added, tasks joined with `; `). End the message with these three options as one line under the table, so the user sees them every time. Then re-read `.confirmed`: if it is no longer `<marker>`, stop and ask the user to run `/timelog` again. Otherwise, in one command, append the rows (leave out `cat` and its heredoc when there are none), write `<last day>` to `.confirmed` and commit:

```bash
cd "${TIMELOG_DATA:-${TIMELOG_ROOT:-$HOME/projects}/timelog-data}" && cat >> timelog.csv <<'ROWS' && echo '<last day>' > .confirmed && git commit -q -m 'log: <marker + 1 day>..<last day>' -- timelog.csv .confirmed
<row>
<row>
ROWS
```

`ROWS` closes the heredoc only at the start of its own line, with no indentation.
