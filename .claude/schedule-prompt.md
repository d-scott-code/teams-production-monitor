# Daily Teams Production Monitor — scheduled run

You are running on a schedule (08:00 America/Denver). Produce today's
production briefing and publish it so the user can read it in the browser.

Do these steps in order. Do not skip any step.

## 1. Check out `main`

```bash
git checkout main
git pull --ff-only origin main
```

Work directly on `main`. GitHub Pages serves from `main`, so the report has to
land there to be visible.

## 2. Generate today's report

Invoke the user's slash command:

```
/teams-production-monitor
```

The command returns a complete HTML document (a full `<!doctype html>` page).
Save that HTML — exactly as produced, no edits — to:

```
reports/<YYYY-MM-DD>.html
```

where `<YYYY-MM-DD>` is today's date in America/Denver (e.g. `2026-04-23`).
Use the `date` command with that timezone to be sure:

```bash
TZ=America/Denver date +%F
```

If a file for today already exists, overwrite it (re-runs should be idempotent).

## 3. Refresh the manifest

```bash
python3 scripts/update_manifest.py
```

This rebuilds `reports/manifest.json` from whatever HTML files now live under
`reports/`. The homepage (`index.html`) reads that manifest to list reports
and link to the latest one.

## 4. Commit and push

```bash
git add reports/
git commit -m "report: <YYYY-MM-DD>"
git push origin main
```

If there is nothing to commit (e.g. `/teams-production-monitor` produced
identical output as an earlier run today), skip the commit — don't force an
empty one.

## 5. Report back to the user

In your final message, give the user:

- The public link to today's report:
  `https://d-scott-code.github.io/teams-production-monitor/reports/<YYYY-MM-DD>.html`
- The homepage link (archive of all past reports):
  `https://d-scott-code.github.io/teams-production-monitor/`
- A one-sentence summary of what's in today's briefing (plants with issues,
  anything urgent), so the email/notification preview is useful on its own.

## Notes

- Never delete older reports under `reports/`. The archive is the product.
- If `/teams-production-monitor` fails, commit nothing and surface the error in
  your final message so the user sees it at 8am instead of silent failure.
- GitHub Pages usually refreshes within a minute of the push. If the link 404s
  right after the push, that's the Pages build — it'll come up shortly.
