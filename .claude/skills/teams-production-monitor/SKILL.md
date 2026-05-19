---
name: teams-production-monitor
description: Generate the daily CandyCo production briefing from Microsoft Teams chat activity in the L1/L2/L3 plant chats over the last 24 hours. Each briefing is window-only — no carry-over across days. Use when the user asks for today's production briefing, runs /teams-production-monitor, or when the 8am schedule fires.
---

# Teams Production Monitor

Produces the daily production briefing for CandyCo's three Lindon plants
(L1 Caramel, L2 Eco Moulding, L3 Chocolate) by scanning the last 24 hours
of Microsoft Teams chats whose topic contains `L1`, `L2`, or `L3`.

Each briefing is window-only: it covers what happened in the last 24 hours
and nothing else. There is no cumulative tracking, no carry-over, no aging
issue queue. If a problem from earlier is still live, the floor will mention
it again today and it'll show up. If they don't, it won't.

Per plant, the briefing shows:

- **Needs attention** — problems raised in the window that didn't clear
- **Resolved in the last 24 hours** — problems raised AND cleared in the window

## Prerequisites

Set as environment variables (populated from GitHub Secrets when running on
the schedule):

- `GRAPH_TENANT_ID` — Azure AD tenant GUID
- `GRAPH_CLIENT_ID` — App registration (client) ID
- `GRAPH_CLIENT_SECRET` — App registration client secret
- `GRAPH_USER_UPN` — UPN (email) of the account whose chats we scan
- `ANTHROPIC_API_KEY` — for the classification call

Setup steps are in [`README.md`](../../../README.md#one-time-setup).

## Running it

The orchestrator handles fetch, classify, render, manifest, commit, and push
in one call. There's nothing manual to do here unless something breaks.

```bash
python3 scripts/run_daily.py
```

Outputs:

- `data/messages-<date>.json` — raw Teams dump
- `data/ledger-<date>.json` — classified resolved + needs_attention for the day
- `reports/<date>.html` — published HTML briefing
- `reports/manifest.json` — refreshed archive index

If the orchestrator exits non-zero, stop and surface the error to the user.
Do not patch around it — a silent-wrong briefing is worse than a loud-broken
one.

## When something breaks

Common failure modes:

- **Graph 401/403** — the client secret expired or admin consent was
  revoked. Check Entra → App registrations → "Teams Production Monitor".
- **Anthropic 429** — rate limit; the schedule's backup slot will retry
  20 minutes later, or rerun `workflow_dispatch` by hand.
- **GitHub push rejected** — the daily commit raced with another push.
  Pull and re-run.

## Data retention

- `reports/*.html` — permanent, the archive is the product
- `data/messages-*.json` — permanent, source of truth if you want to build
  weekly/monthly roll-ups with a separate tool
- `data/ledger-*.json` — permanent, classified daily snapshot

Nothing under `data/` or `reports/` should ever be deleted by this skill.
