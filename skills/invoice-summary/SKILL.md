---
name: invoice-summary
description: Draft a client's monthly work summary from the time log, per the client's own billing settings
argument-hint: "<client> [month]; default = the previous month"
---

Monthly work summary for one client, to send with the invoice.

Arguments: $ARGUMENTS

- **Client**: required, a top-level directory of the projects root (`acme`). If missing, ask.
- **Month**: optional, any form (`10`, `October`, `2026-10`); default the previous month.

Rules:
- The client's settings are `clients/<client>.md` in the log directory: `language`, `format`, `rate`, `notes`. Missing file: stop and ask the user to create it; never guess the settings.
- The draft follows `format` exactly. Hours go into it only when `format` says so. Without hours, nothing that lets the rate be derived goes in either: no per-area shares, no day counts, no "N h" in task text.
- The amount is the user's number: compute it only when the settings give a `rate` and `format` bills by hours (with python), otherwise leave `___`.
- Write in the client's `language`, translating task notes that are in another language.
- Nothing is written to disk, nothing is committed: the draft lives in chat only.

## Steps

1. Read the settings and the month's rows:

```bash
cd "${TIMELOG_DATA:-${TIMELOG_ROOT:-$HOME/projects}/timelog-data}" && cat "clients/<client>.md" .confirmed && awk -F, -v c="<client>" -v m="<YYYY-MM>" '($2 == c || index($2, c "/") == 1) && substr($1, 1, 7) == m' timelog.csv
```

2. If `.confirmed` is before the month's last day, say which days are not logged yet and ask whether to go on.
3. Group the rows into 3–6 areas of work by what the client got (a feature, a fix, a campaign), not by repo; calls and planning are one area. Sum hours per area with python, not in your head.
4. Show the user, outside the draft: a table of areas with hours, and the total hours. This is for setting the price.
5. Then the draft in one fenced block, ready to paste: month as the heading, one line per area, the total. Paragraphs are not hard-wrapped.
