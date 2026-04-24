# Daily Teams Production Monitor — scheduled run

You are running on a schedule (08:00 America/Denver). Produce today's
production briefing and publish it so the user can read it in the browser.

Do these steps in order. Do not skip any step.

## 1. Check out `main`

```bash
git checkout main
git pull --ff-only origin main
TODAY="$(TZ=America/Denver date +%F)"
```

Work directly on `main`. GitHub Pages serves from `main`, so the report has to
land there to be visible.

## 2. Run the `teams-production-monitor` skill

Invoke the skill (it lives at `.claude/skills/teams-production-monitor/`):

```
/teams-production-monitor
```

The skill handles fetching Teams messages, reconciling open/closed GitHub
Issues, writing `data/messages-$TODAY.json` + `data/ledger-$TODAY.json`, and
rendering `reports/$TODAY.html`. Follow its SKILL.md end to end.

If the skill fails (usually Graph auth or GitHub rate limits), **commit
nothing** and surface the error in your final message — a silent-wrong
briefing is worse than a loud-broken one.

## 3. Refresh the manifest

```bash
python3 scripts/update_manifest.py
```

Rebuilds `reports/manifest.json` so the homepage archive picks up today.

## 4. Commit and push

```bash
git add reports/ data/
git commit -m "report: $TODAY"
git push origin main
```

If there is nothing new to commit (e.g. the skill was re-run and produced
identical output), skip the commit — don't force an empty one.

## 5. Report back to the user

In your final message, give the user:

- The public link to today's report:
  `https://d-scott-code.github.io/teams-production-monitor/reports/$TODAY.html`
- The homepage link (archive of all past reports):
  `https://d-scott-code.github.io/teams-production-monitor/`
- A one-line roll-up from the ledger, e.g.
  `"L1: 2 closed, 1 new, 3 open. L2: 0/0/1. L3: 1/0/0."`
- The single most urgent still-open issue (oldest, across any plant), by
  title + issue link.

## Notes

- Never delete older reports under `reports/` or dumps under `data/`. The
  archive is the product; the dumps fuel weekly/monthly/quarterly rollups.
- GitHub Pages usually refreshes within a minute of the push. If the link
  404s right after the push, that's the Pages build — it'll come up shortly.
