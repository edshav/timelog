# timelog

A Claude Code plugin that turns your session transcripts into a time log. Each new session
reminds you of past days with unconfirmed activity; `/timelog` drafts those days per project,
you correct and confirm, and the rows land in a CSV you keep in your own git repo.

- **Client** = a top-level directory of your projects root; **project** = the repo inside it
  (worktrees count as their main repo), or the client itself when it is a single repo.
- Hours are measured from transcript timestamps: a pause up to 20 minutes is work, a longer
  one a break. Parallel sessions of one client count once.
- Nothing is written without your explicit "ok".

The full design is in [`docs/design.md`](docs/design.md).

## Install

```
/plugin install timelog --marketplace edshav/skills
```

Create the log repo once (it stays local; the plugin never publishes it):

```sh
mkdir -p ~/projects/timelog-data && cd ~/projects/timelog-data && git init -q
echo 'date,project,hours,task' > timelog.csv
date -v-1d +%F > .confirmed   # Linux: date -d yesterday +%F
git add . && git commit -qm 'log: start'
```

`.confirmed` is the last day already logged; the next draft starts the day after.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `TIMELOG_ROOT` | `~/projects` | Sessions under this directory are counted. |
| `TIMELOG_DATA` | `$TIMELOG_ROOT/timelog-data` | Git repo holding `timelog.csv`, `.confirmed` and `clients/*.md`. |

Set them in the `env` block of `~/.claude/settings.json` so both the hook and `/timelog` see
them, as absolute paths: nothing expands `~` there.

## Use

- `/timelog`: draft every unconfirmed day, then "ok", "ok, skip 3" or "ok, 3 to general".
- `/timelog yesterday call 0.5 acme`: one manual row for time without Claude.
- `/timelog:invoice-summary acme`: last month's work summary for the invoice, per
  `$TIMELOG_DATA/clients/acme.md` (`language`, `format`, `rate`, `notes`).

macOS and Linux only. Requires `/usr/bin/python3` (3.9+) and `git`. Self-check:
`/usr/bin/python3 -I timelog.py test`.
