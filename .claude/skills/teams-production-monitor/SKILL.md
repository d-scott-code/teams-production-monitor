---
name: teams-production-monitor
description: Generate the daily CandyCo production briefing from Microsoft Teams chat activity in the L1/L2/L3 plant chats over the last 24 hours. Tracks open vs. resolved issues as GitHub Issues and renders an HTML report published via GitHub Pages. Use when the user asks for today's production briefing, runs /teams-production-monitor, or when the 8am schedule fires.
---

# Teams Production Monitor

Produces the daily production briefing for CandyCo's three Lindon plants
(L1 Caramel, L2 Eco Moulding, L3 Chocolate) by scanning the last 24 hours of
Microsoft Teams chats whose topic contains `L1`, `L2`, or `L3`.

The briefing answers three questions for leadership:

1. **What went well** — issues resolved in the last 24h.
2. **What didn't** — issues opened or still open, by plant.
3. **Where to focus today** — prioritized list of still-open issues.

Raw message dumps and issue ledgers are preserved for later weekly/monthly/
quarterly roll-ups.

## Prerequisites

Set as environment variables (populated from GitHub Secrets when running on
the schedule):

- `GRAPH_TENANT_ID` — Azure AD tenant GUID
- `GRAPH_CLIENT_ID` — App registration (client) ID
- `GRAPH_CLIENT_SECRET` — App registration client secret
- `GRAPH_USER_UPN` — UPN (email) of the account whose chats we scan
- `GITHUB_TOKEN` — PAT or Actions token with `repo` scope on this repo

Setup steps are in [`README.md`](../../../README.md#one-time-setup).

## Workflow

Follow these steps in order. Do not skip any step.

### 1. Determine the window

The "last 24 hours" ends at the moment this run starts, in America/Denver.

```bash
TODAY="$(TZ=America/Denver date +%F)"
```

Store `$TODAY` — every file for this run uses it.

### 2. Fetch Teams messages

```bash
python3 scripts/fetch_teams_messages.py --out data/messages-$TODAY.json
```

This writes `data/messages-<date>.json` with the shape:

```json
{
  "window": {"start_utc": "...", "end_utc": "...", "tz": "America/Denver"},
  "chats": [
    {
      "id": "19:...@thread.v2",
      "topic": "L1 Caramel - Ops",
      "plant": "L1",
      "messages": [
        {"id": "...", "from": "Jane Doe", "sent_utc": "...", "text": "..."}
      ]
    }
  ]
}
```

If the script exits non-zero, stop and surface the error to the user. Do not
write a report, do not commit anything — a silent-wrong briefing is worse
than a loud-broken one.

### 3. Load the current open-issue ledger

Fetch every open issue in this repo labeled `plant:L1`, `plant:L2`, or
`plant:L3`. Use the GitHub MCP tools (`mcp__github__list_issues` with
`state: "open"` and each label).

For each open issue, read its title and body — those are the issues you
need to match incoming chat activity against.

### 4. Reason over messages and plan ledger changes

Read `data/messages-<date>.json`. For each plant chat's messages, decide:

- **New issue** — something the team is raising that isn't already tracked.
  Good signal: explicit problem statements, questions about blockers,
  safety/quality flags, machine-down reports.
- **Update to an existing issue** — a chat thread discussing an open issue
  (add a comment with today's context).
- **Resolution** — someone says it's fixed, back online, cleared, etc.
  (close the issue with a comment quoting the resolution message).

Produce a plan as a JSON blob in your scratch space — do not act yet:

```json
{
  "create": [
    {"plant": "L1", "title": "...", "body": "...", "source_msg_ids": ["..."]}
  ],
  "comment": [
    {"issue_number": 42, "body": "..."}
  ],
  "close": [
    {"issue_number": 37, "resolution_comment": "..."}
  ]
}
```

**Quality bar for issue titles:** short, concrete, scannable on a phone.
"L2 hopper #3 jamming on 0.5in crumb" not "hopper problem". Leave plant out
of the title (it's carried by the label).

**Body template for new issues:**

```
**Plant:** L{1,2,3}
**First raised:** <timestamp> by <author>
**Source chat:** <topic>

<1-2 sentence summary of the problem>

---
Source messages:
> <quoted message>
— <author>, <time>
```

### 5. Apply the plan

Using the GitHub MCP tools, in this order:

1. Close issues from `plan.close` (`mcp__github__issue_write` with
   `action: "update"`, `state: "closed"`, and add a closing comment).
2. Add comments from `plan.comment` (`mcp__github__add_issue_comment`).
3. Create issues from `plan.create` (`mcp__github__issue_write` with
   `action: "create"` and labels `plant:L{1,2,3}`).

Capture the issue numbers that were created/closed — the HTML render needs
them.

### 6. Render the HTML report

```bash
python3 scripts/render_report.py \
  --messages data/messages-$TODAY.json \
  --ledger data/ledger-$TODAY.json \
  --out reports/$TODAY.html
```

Before calling the renderer, write `data/ledger-<date>.json` capturing the
final state for the day:

```json
{
  "date": "2026-04-24",
  "closed_today": [{"number": 37, "title": "...", "plant": "L2"}],
  "opened_today": [{"number": 55, "title": "...", "plant": "L1"}],
  "still_open": [{"number": 42, "title": "...", "plant": "L3", "age_days": 3}]
}
```

`still_open` is the full list of open `plant:L*` issues after today's updates,
ordered by plant then by age descending (oldest first — those are your
priorities).

### 7. Refresh the manifest

```bash
python3 scripts/update_manifest.py
```

### 8. Hand back to the schedule routine

Return control to `.claude/schedule-prompt.md` step 4 (commit & push). Include
in your final user-facing message:

- Link to today's report
- One-line summary: `"L1: 2 closed, 1 new, 3 open. L2: 0 closed, 0 new, 1 open. L3: 1 closed, 0 new, 0 open."`
- The most urgent still-open issue across all plants (oldest), by title + link

## Data retention

- `reports/*.html` — permanent, the archive is the product
- `data/messages-*.json` — permanent, source of truth for weekly/monthly rollups
- `data/ledger-*.json` — permanent, day-over-day delta for KPI trending

Nothing under `data/` or `reports/` should ever be deleted by this skill.
