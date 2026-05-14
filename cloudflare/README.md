# "Mark resolved" button — Cloudflare Worker

Plant leaders read the daily report on their phone but don't have GitHub
accounts. This Cloudflare Worker is the small public endpoint each priority
row's **Mark resolved** button hits. It validates a signed URL (HMAC bound to
the issue number + expiry) and closes the issue via the GitHub API.

The renderer (`scripts/render_report.py`) emits the signed URLs. The worker
verifies them. No login from plant leaders; one tap to confirm; signed links
expire after 7 days.

## Architecture

```
┌──────────────┐   tap "Mark resolved"   ┌──────────────────────┐
│ Daily report │ ───────────────────────▶│ Cloudflare Worker    │
│ (GH Pages)   │   signed URL            │ GET → confirm page   │
└──────────────┘                         │ POST → closes issue  │
                                         └──────────┬───────────┘
                                                    │ GitHub API
                                                    ▼
                                          ┌──────────────────────┐
                                          │ teams-production-    │
                                          │ monitor issue closed │
                                          └──────────────────────┘
```

The shared HMAC secret (set as a GitHub repo secret AND a worker secret)
binds the two ends. The worker holds a fine-grained GitHub PAT scoped to
just "Issues: write" on this one repo.

## One-time setup

You'll do this once. Plan ~15 minutes the first time.

### 1. Cloudflare account (free)

- Sign up at https://dash.cloudflare.com/sign-up (no credit card needed; the
  free tier covers 100,000 requests/day — we'll use a handful).

### 2. Install wrangler

```bash
npm install -g wrangler
wrangler login    # opens a browser to authorize
```

### 3. Generate the shared HMAC secret

Pick something random and long. Save it — you'll set it in two places.

```bash
openssl rand -hex 32
# example output: 3f9a...b4 (don't use this one; generate your own)
```

### 4. Generate a GitHub fine-grained PAT

1. Go to https://github.com/settings/personal-access-tokens/new
2. **Resource owner:** your account (`d-scott-code`).
3. **Repository access:** "Only select repositories" → `teams-production-monitor`.
4. **Repository permissions:** find **Issues** → set to **Read and write**.
   (Leave everything else at "No access". Don't grant Contents, Actions, etc.)
5. **Expiration:** pick something you can renew (90 days is reasonable; the
   worker will start returning errors when it expires and you'll need to
   regenerate).
6. Copy the token (starts with `github_pat_...`). Save it — you'll set it as
   a worker secret in the next step.

### 5. Deploy the worker

From the repo root:

```bash
cd cloudflare
wrangler deploy
```

The first deploy will print a URL like
`https://teams-monitor-close.<your-subdomain>.workers.dev`. Save it — that's
the `CLOSE_BUTTON_WORKER_URL` you'll add to GitHub secrets.

### 6. Set worker secrets

```bash
wrangler secret put HMAC_SECRET
# paste the random hex string from step 3

wrangler secret put GITHUB_TOKEN
# paste the github_pat_... from step 4
```

### 7. Add the GitHub repo secrets

In https://github.com/d-scott-code/teams-production-monitor/settings/secrets/actions,
add **two** new secrets:

- **`CLOSE_BUTTON_WORKER_URL`** — the `*.workers.dev` URL from step 5
  (no trailing slash).
- **`CLOSE_BUTTON_HMAC_SECRET`** — the same hex string from step 3.

That's it. The next daily report (or a manual `workflow_dispatch` run of
"Daily Teams Production Monitor") will render with **Mark resolved** buttons.

## Verifying it works

After the first run, open today's report on your phone. Each open priority
should have a green **✓ Mark resolved** button on the right. Tap one →
confirm → the issue closes on GitHub with a "Resolved on the floor — closed
via report button." comment.

If the buttons don't appear, check:

- Both `CLOSE_BUTTON_WORKER_URL` and `CLOSE_BUTTON_HMAC_SECRET` are set as
  GitHub Actions secrets (the renderer omits the column if either is
  missing).
- The workflow has run since you added the secrets (re-run "Daily Teams
  Production Monitor" via the Actions tab if needed).

If a button errors:

- **"Link expired"** — the report is more than 7 days old. Open a newer one.
- **"Invalid signature"** — the `HMAC_SECRET` on the worker doesn't match
  the `CLOSE_BUTTON_HMAC_SECRET` in GitHub. Re-set both to the same value.
- **"Could not close issue"** — the worker's `GITHUB_TOKEN` PAT is missing,
  expired, or lacks `Issues: write` scope. Rotate it via step 4 and re-run
  `wrangler secret put GITHUB_TOKEN`.

## Iterating on the worker

```bash
cd cloudflare
wrangler dev           # local preview at http://localhost:8787
wrangler deploy        # ship
wrangler tail          # stream live logs (useful for debugging tap failures)
```

## Rotation

To rotate the HMAC secret: generate a new one, update **both** the worker
secret (`wrangler secret put HMAC_SECRET`) and the GitHub repo secret
(`CLOSE_BUTTON_HMAC_SECRET`), then re-run the daily workflow. Buttons on
reports rendered before the rotation will stop working — fine, since you're
rotating because something leaked.

To rotate the GitHub PAT: regenerate it, then `wrangler secret put
GITHUB_TOKEN`. No GitHub-side changes needed.

## Cost

Cloudflare Workers free tier: 100,000 requests/day. We expect roughly N
button taps per report × 3 plants × 1 report/day — well under 100/day even
counting curious clicks. Free.
