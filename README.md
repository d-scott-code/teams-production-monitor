# Teams Production Monitor

Daily automated briefings on Microsoft Teams activity for CandyCo's three Lindon plants (L1 Caramel, L2 Moulding, L3 Chocolate). Two views of the same 24 hours, generated in one pass:

- **Production briefing** — for plant leadership. Ops focus: what was resolved, what needs attention, per plant.
- **FSQA briefing** — for the FSQA Manager. Food safety, quality, sanitation, allergen, plus 1-3 process-level opportunities surfaced by the day's events.

**Live site:** https://d-scott-code.github.io/teams-production-monitor/

Every morning at 13:15 UTC (7:15 AM MDT / 6:15 AM MST), a Cloudflare
Worker fires the GitHub Actions workflow via the `workflow_dispatch`
API. The workflow runs `scripts/run_daily.py`: it pulls the last 24
hours of messages from every Teams chat whose topic contains `L1`,
`L2`, or `L3`, makes one Anthropic API call to classify the activity,
renders an HTML briefing, and commits everything to `main`. GitHub
Pages serves the archive so any browser can read it — no login
required.

The Worker exists because GitHub Actions scheduled events are
best-effort and routinely run hours late under peak load.
`workflow_dispatch` isn't subject to the same queueing, so the Worker
gets the report on Pages by ~7:25 AM Mountain reliably. See
[`cloudflare/README.md`](cloudflare/README.md) for setup. The
GitHub-scheduled cron in `.github/workflows/daily.yml` stays in place
as a fallback.

Each report is **window-only**: it reflects what happened in the last 24
hours and nothing else. There is no cumulative tracking, no carry-over,
no aging issue queue. If a problem from earlier in the week is still
live, the floor will mention it again today and it'll show up. If
they don't, it won't. Trends are something to extract from the report
archive, not bake into the report.

## What each briefing covers

**Production briefing**, per plant (L1, L2, L3):

- **Needs attention** — problems raised in the last 24h that didn't clear
- **Resolved in the last 24 hours** — problems raised AND cleared in the window

**FSQA briefing**, single sheet across all plants:

- **Active holds** — product on hold or pending QA disposition
- **Food safety** — foreign material, contamination, food-safety equipment failures, damaged equipment in food-contact zones
- **Quality flags** — spec misses, weight/count failures, label errors
- **Sanitation** — ATP failures, cleaning gaps, hygiene issues
- **Allergen** — cross-contact, label errors, allergen verification
- **Opportunities** — 0-3 process-level "consider..." suggestions surfaced by today's events

Raw message dumps land in [`data/`](data/) — the source of truth if you
want to build weekly/monthly/quarterly roll-ups with a separate tool.

## Repo layout

- `index.html` — homepage (archive + latest)
- `reports/<YYYY-MM-DD>.html` — one briefing per day
- `reports/manifest.json` — list of dates, rebuilt by `scripts/update_manifest.py`
- `reports/fsqa-<YYYY-MM-DD>.html` — one FSQA briefing per day
- `data/messages-<YYYY-MM-DD>.json` — raw Teams dump for the day
- `data/ledger-<YYYY-MM-DD>.json` — production briefing ledger (resolved + needs_attention)
- `data/fsqa-<YYYY-MM-DD>.json` — FSQA briefing ledger (holds/food_safety/quality/sanitation/allergen/opportunities)
- `scripts/fetch_teams_messages.py` — Graph API client (called by orchestrator)
- `scripts/run_daily.py` — the orchestrator the workflow invokes
- `scripts/render_report.py` — production briefing HTML generator
- `scripts/render_fsqa_report.py` — FSQA briefing HTML generator
- `scripts/update_manifest.py` — rebuilds `reports/manifest.json`
- `.claude/skills/teams-production-monitor/SKILL.md` — manual-run skill (Claude Code sessions only)
- `.claude/hooks/session-start.sh` — installs `requests` when the skill is used interactively
- `.github/workflows/daily.yml` — the GitHub Actions workflow (triggered by the Worker, with a cron fallback)
- `cloudflare/` — Worker that triggers the daily workflow at 13:15 UTC (see its README for deploy steps)

## One-time setup

You only do this once. Order matters.

### 1. Register an Azure AD app (tenant admin)

1. https://entra.microsoft.com → **App registrations** → **New registration**
2. Name: `Teams Production Monitor`, single tenant, no redirect URI.
3. On the new app, go to **API permissions** → **Add a permission** →
   **Microsoft Graph** → **Application permissions**:
   - `Chat.Read.All`
   - `ChatMessage.Read.All`
   - `User.Read.All`
4. Click **Grant admin consent** (green check next to each permission).
5. **Certificates & secrets** → **New client secret** → 24-month expiry.
   Copy the **Value** now — you won't see it again.
6. Note the **Application (client) ID** and **Directory (tenant) ID** from the
   Overview tab.

### 2. Enable metered billing for protected Teams APIs

Reading Teams chat messages app-only is a "protected API" — Microsoft bills
per message read. At L1/L2/L3 chat volumes this is pennies per month, but
you have to link an Azure subscription first.

1. https://learn.microsoft.com/en-us/graph/teams-licenses — follow "Set up a
   billing model with your Azure subscription" for the app registered above.
2. Pick any Azure subscription you own; usage shows up as "Microsoft Graph"
   in cost reports.

### 3. Enable GitHub Pages

1. https://github.com/d-scott-code/teams-production-monitor/settings/pages
2. **Source:** *Deploy from a branch*
3. **Branch:** `main` / `/ (root)` → Save.
4. First build finishes in ~1 minute.

### 4. Add repo secrets

Go to https://github.com/d-scott-code/teams-production-monitor/settings/secrets/actions
and add:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | From https://console.anthropic.com/settings/keys |
| `GRAPH_TENANT_ID` | Directory (tenant) ID from step 1.6 |
| `GRAPH_CLIENT_ID` | Application (client) ID from step 1.6 |
| `GRAPH_CLIENT_SECRET` | Client secret value from step 1.5 |
| `GRAPH_USER_UPN` | Your email (the account that's in every L1/L2/L3 chat) |

`GITHUB_TOKEN` is auto-provided by Actions — no need to add. The workflow
declares `contents: write` so the orchestrator can commit reports.

### 5. Done

The workflow at `.github/workflows/daily.yml` runs daily at 14:00 UTC
(08:00 MDT / 07:00 MST). To run it manually, go to **Actions** → **Daily
Teams Production Monitor** → **Run workflow**.

## Reading the reports

- **Latest:** https://d-scott-code.github.io/teams-production-monitor/ auto-links to today.
- **Specific day:** `https://d-scott-code.github.io/teams-production-monitor/reports/YYYY-MM-DD.html`
- **Archive:** the homepage lists every past report, newest first.

## Running it manually

**From GitHub:** Actions tab → **Daily Teams Production Monitor** → **Run
workflow**. Same path the cron uses.

**From a shell** (full pipeline, with the five secrets exported):

```bash
pip install requests anthropic
export ANTHROPIC_API_KEY=...
export GRAPH_TENANT_ID=...
export GRAPH_CLIENT_ID=...
export GRAPH_CLIENT_SECRET=...
export GRAPH_USER_UPN=you@candyco.example
python3 scripts/run_daily.py
```

**From a shell, just the fetch half** (writes a JSON dump, doesn't touch
issues):

```bash
python3 scripts/fetch_teams_messages.py --out data/messages-$(TZ=America/Denver date +%F).json
```

**From a Claude Code session** (interactive, agent-driven — useful for
ad-hoc investigation, not the daily cron):

```
/teams-production-monitor
```
