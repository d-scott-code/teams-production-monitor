# Daily trigger — Cloudflare Worker

GitHub Actions scheduled events run when the platform has capacity. During
peak load (mornings, US East Coast hours) they're commonly delayed by 1-4
hours. This Worker bypasses that queue by firing on Cloudflare's own cron
trigger and calling the GitHub `workflow_dispatch` API, which is not
subject to the same queueing as `schedule` events.

The GitHub Actions cron in `.github/workflows/daily.yml` stays in place as
a fallback. If this Worker is broken or Cloudflare has an outage, the
GitHub-scheduled run still eventually fires (late). On a normal day:

1. **13:15 UTC** — Worker fires → workflow runs in seconds → report
   commits by ~13:20 UTC → Pages publishes by ~13:23 UTC = **7:23 AM MDT**.
2. **13:20 UTC** — GitHub schedule tries to fire, gets queued.
3. **Hours later** — GitHub queued run finally starts, sees today's report
   exists, no-ops (idempotency guard in `run_daily.py`).

## One-time setup

Plan ~10 minutes the first time.

### 1. Cloudflare account (free)

Sign up at https://dash.cloudflare.com/sign-up. No credit card needed.

### 2. Install wrangler

```bash
npm install -g wrangler
wrangler login    # opens a browser to authorize
```

### 3. Generate a GitHub fine-grained PAT

1. Go to https://github.com/settings/personal-access-tokens/new
2. **Resource owner:** `d-scott-code`.
3. **Repository access:** "Only select repositories" → `teams-production-monitor`.
4. **Repository permissions:** find **Actions** → set to **Read and write**.
   (Leave everything else at "No access".)
5. **Expiration:** 90 days is reasonable. The Worker will start failing
   silently when it expires — set a calendar reminder to rotate, or pick
   a longer expiry.
6. Copy the token (starts with `github_pat_...`).

### 4. Deploy the Worker

From the repo root:

```bash
cd cloudflare
wrangler deploy
```

First deploy prints a URL like `https://teams-monitor-cron.<subdomain>.workers.dev`.
You don't need to save it — the Worker is invoked by the cron, not by HTTP.

### 5. Set the GITHUB_TOKEN secret

```bash
wrangler secret put GITHUB_TOKEN
# paste the github_pat_... from step 3
```

That's it. The Worker is live. The next 13:15 UTC fire (= 7:15 AM MDT
today) will trigger the daily workflow.

## Verifying it works

After deploy:

```bash
# Watch the next scheduled fire live (Ctrl+C to exit):
wrangler tail

# Or manually test the dispatch immediately:
wrangler dev          # spawns a local instance at http://localhost:8787
curl http://localhost:8787   # returns "teams-monitor-cron: ok"
# Then trigger the scheduled handler manually:
curl "http://localhost:8787/__scheduled?cron=15+13+%2A+%2A+%2A"
```

To verify GitHub received it:
- Open https://github.com/d-scott-code/teams-production-monitor/actions
- You should see a new "Daily Teams Production Monitor" run with the
  trigger `workflow_dispatch` — not `schedule`.

## Iterating on the Worker

```bash
cd cloudflare
wrangler dev          # local preview
wrangler deploy       # ship
wrangler tail         # stream live logs (includes any dispatch failures)
```

## Rotation

When the GitHub PAT expires:

```bash
# regenerate the PAT (step 3 above), then:
wrangler secret put GITHUB_TOKEN
```

No redeploy needed.

## Cost

Cloudflare Workers free tier: 100,000 requests/day + 100,000 cron
invocations/month. We use 1 cron/day. Free.

## Changing the schedule

Edit `wrangler.toml` → `[triggers] crons`. Cron expression is UTC; standard
Unix cron syntax (minute hour day month weekday). Then:

```bash
wrangler deploy
```
