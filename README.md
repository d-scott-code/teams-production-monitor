# Teams Production Monitor

Daily automated reports of Microsoft Teams activity for CandyCo's three Lindon plants (L1 Caramel, L2 Eco Moulding, L3 Chocolate).

**Live site:** https://d-scott-code.github.io/teams-production-monitor/

Every morning at 08:00 America/Denver, a scheduled Claude Code task runs the
`teams-production-monitor` skill: it pulls the last 24 hours of messages
from every Teams chat whose topic contains `L1`, `L2`, or `L3`, reconciles
them against the open issue ledger (GitHub Issues in this repo), and commits
an HTML briefing to [`reports/`](reports/). GitHub Pages serves the archive
so any browser can read it — no login required.

## What each report covers

Per plant (L1, L2, L3):

- **What went well** — issues resolved in the last 24 hours
- **What didn't** — new issues raised in the last 24 hours
- **Today's priorities** — every still-open issue, oldest first

The issue ledger lives as GitHub Issues in this repo, labeled `plant:L1`,
`plant:L2`, or `plant:L3`. Raw message dumps land in [`data/`](data/) — the
source of truth for weekly/monthly/quarterly roll-ups.

## Repo layout

- `index.html` — homepage (archive + latest)
- `reports/<YYYY-MM-DD>.html` — one briefing per day
- `reports/manifest.json` — list of dates, rebuilt by `scripts/update_manifest.py`
- `data/messages-<YYYY-MM-DD>.json` — raw Teams dump for the day
- `data/ledger-<YYYY-MM-DD>.json` — closed/opened/still-open snapshot
- `.claude/skills/teams-production-monitor/SKILL.md` — the skill itself
- `.claude/schedule-prompt.md` — the prompt the 8am scheduled task follows
- `.claude/hooks/session-start.sh` — installs `requests` for the skill

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

### 4. Add secrets to the Claude Code scheduled task

When you create the schedule in Claude Code on the web (step 5), attach
these as repo-level secrets so the cloud container can read them:

| Secret | Value |
|---|---|
| `GRAPH_TENANT_ID` | Directory (tenant) ID from step 1.6 |
| `GRAPH_CLIENT_ID` | Application (client) ID from step 1.6 |
| `GRAPH_CLIENT_SECRET` | Client secret value from step 1.5 |
| `GRAPH_USER_UPN` | Your email (the account that's in every L1/L2/L3 chat) |
| `GITHUB_TOKEN` | A PAT with `repo` scope (only needed if Claude Code's built-in token can't write issues) |

### 5. Create the scheduled task (Claude Code on the web)

1. https://claude.ai/code → open this repo.
2. Scheduler → New schedule:
   - Repo: `d-scott-code/teams-production-monitor`, branch `main`
   - Cron: `0 8 * * *`, timezone `America/Denver`
   - Prompt: *"Follow the routine in `.claude/schedule-prompt.md`."*
   - Env: attach the secrets from step 4.
3. Turn on notifications so you get the link in your inbox each morning.

That's it — runs in the cloud, laptop can stay off.

## Reading the reports

- **Latest:** https://d-scott-code.github.io/teams-production-monitor/ auto-links to today.
- **Specific day:** `https://d-scott-code.github.io/teams-production-monitor/reports/YYYY-MM-DD.html`
- **Archive:** the homepage lists every past report, newest first.
- **Open issues:** https://github.com/d-scott-code/teams-production-monitor/issues?q=is%3Aopen+label%3Aplant%3AL1%2Cplant%3AL2%2Cplant%3AL3

## Running it manually

In a Claude Code session with the secrets in your environment:

```
/teams-production-monitor
```

Or from a shell, just the fetch half (writes a JSON dump, doesn't touch issues):

```bash
export GRAPH_TENANT_ID=...
export GRAPH_CLIENT_ID=...
export GRAPH_CLIENT_SECRET=...
export GRAPH_USER_UPN=you@candyco.example
python3 scripts/fetch_teams_messages.py --out data/messages-$(TZ=America/Denver date +%F).json
```
