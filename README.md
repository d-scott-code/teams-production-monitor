# Teams Production Monitor

Daily automated reports of Microsoft Teams activity for CandyCo's three Lindon plants (L1 Caramel, L2 Eco Moulding, L3 Chocolate).

**Live site:** https://d-scott-code.github.io/teams-production-monitor/

Every morning at 14:00 UTC (08:00 MDT / 07:00 MST), a GitHub Actions
workflow runs `scripts/run_daily.py`: it pulls the last 24 hours of
messages from every Teams chat whose topic contains `L1`, `L2`, or `L3`,
makes one Anthropic API call to classify the activity, renders an HTML
briefing, and commits everything to `main`. GitHub Pages serves the
archive so any browser can read it — no login required.

Each report is **window-only**: it reflects what happened in the last 24
hours and nothing else. There is no cumulative tracking, no carry-over,
no aging issue queue. If a problem from earlier in the week is still
live, the floor will mention it again today and it'll show up. If
they don't, it won't. Trends are something to extract from the report
archive, not bake into the report.

## What each report covers

Per plant (L1, L2, L3):

- **Needs attention** — problems raised in the last 24h that didn't clear
- **Resolved in the last 24 hours** — problems raised AND cleared in the window

Raw message dumps land in [`data/`](data/) — the source of truth if you
want to build weekly/monthly/quarterly roll-ups with a separate tool.

## Repo layout

- `index.html` — homepage (archive + latest)
- `reports/<YYYY-MM-DD>.html` — one briefing per day
- `reports/manifest.json` — list of dates, rebuilt by `scripts/update_manifest.py`
- `data/messages-<YYYY-MM-DD>.json` — raw Teams dump for the day
- `data/ledger-<YYYY-MM-DD>.json` — classified resolved + needs_attention for the day
- `scripts/fetch_teams_messages.py` — Graph API client (called by orchestrator)
- `scripts/run_daily.py` — the orchestrator the workflow invokes
- `scripts/render_report.py` — HTML report generator
- `scripts/update_manifest.py` — rebuilds `reports/manifest.json`
- `.claude/skills/teams-production-monitor/SKILL.md` — manual-run skill (Claude Code sessions only)
- `.claude/hooks/session-start.sh` — installs `requests` when the skill is used interactively
- `.github/workflows/daily.yml` — the GitHub Actions cron that runs it

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
