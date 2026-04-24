# Teams Production Monitor

Daily automated reports of Microsoft Teams activity for CandyCo's three Lindon plants (L1 Caramel, L2 Eco Moulding, L3 Chocolate).

**Live site:** https://d-scott-code.github.io/teams-production-monitor/

Every morning at 08:00 America/Denver, a scheduled Claude Code task runs the
`/teams-production-monitor` slash command and commits the resulting HTML to
[`reports/`](reports/). GitHub Pages serves the archive so any browser can
read it — no login required.

## Layout

- `index.html` — homepage with the latest report and full archive
- `reports/<YYYY-MM-DD>.html` — one file per day
- `reports/manifest.json` — list of report dates (rebuilt by the script below)
- `scripts/update_manifest.py` — rebuilds the manifest from files on disk
- `.claude/schedule-prompt.md` — the exact prompt the scheduled run follows

## One-time setup

### 1. Enable GitHub Pages

1. https://github.com/d-scott-code/teams-production-monitor/settings/pages
2. **Source:** "Deploy from a branch"
3. **Branch:** `main` / `/ (root)`
4. Save. First build finishes in ~1 minute.

### 2. Create the scheduled task (Claude Code on the web)

1. Go to https://claude.ai/code and open this repo.
2. Open the scheduler and add a new schedule:
   - **Repo:** `d-scott-code/teams-production-monitor`
   - **Branch:** `main`
   - **Cron:** `0 8 * * *`
   - **Timezone:** `America/Denver`
   - **Prompt:** paste the contents of [`.claude/schedule-prompt.md`](.claude/schedule-prompt.md),
     or simply say: *"Follow the routine in `.claude/schedule-prompt.md`."*
3. Enable notifications so you get the link in your inbox at 8am.

That's it — runs in the cloud, laptop can stay off.

## Reading the reports

- **Latest:** https://d-scott-code.github.io/teams-production-monitor/ auto-links to today.
- **Specific day:** `https://d-scott-code.github.io/teams-production-monitor/reports/YYYY-MM-DD.html`
- **Archive:** the homepage lists every past report, newest first.
