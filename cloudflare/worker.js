// Cloudflare Worker — daily trigger for the Teams Production Monitor workflow.
//
// GitHub Actions scheduled events are best-effort and routinely run hours late
// during peak load (we've seen 3-4 hour delays). This Worker fires reliably at
// the scheduled time and calls the workflow_dispatch API. Manual dispatches are
// NOT subject to the same queueing as `schedule` events — they run within
// seconds.
//
// The GitHub Actions cron in daily.yml stays in place as a belt-and-suspenders
// fallback: if this Worker is misconfigured, its PAT expires, or Cloudflare has
// an outage, the GitHub-scheduled run still eventually fires (late). The
// orchestrator's idempotency guard prevents duplicate reports on days when both
// trigger paths succeed.
//
// Routes:
//   - cron       → calls workflow_dispatch
//   - GET /      → health check (returns "ok\n")
//
// Required secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN   fine-grained PAT, scope: Actions read+write on the repo
//
// Vars (set in wrangler.toml [vars], defaults shown):
//   GITHUB_REPO    "d-scott-code/teams-production-monitor"
//   WORKFLOW_FILE  "daily.yml"
//   WORKFLOW_REF   "main"

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, "cron"));
  },

  async fetch(request, env) {
    return new Response("teams-monitor-cron: ok\n", {
      status: 200,
      headers: { "Content-Type": "text/plain" },
    });
  },
};

async function dispatch(env, source) {
  const repo = env.GITHUB_REPO || "d-scott-code/teams-production-monitor";
  const workflow = env.WORKFLOW_FILE || "daily.yml";
  const ref = env.WORKFLOW_REF || "main";
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;

  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "teams-monitor-cron",
    },
    body: JSON.stringify({ ref }),
  });

  const ok = r.status === 204;  // GitHub returns 204 No Content on success
  if (!ok) {
    const body = await r.text();
    console.error(`dispatch failed (${source}): ${r.status} ${body.slice(0, 500)}`);
  } else {
    console.log(`dispatch ok (${source}): ${repo}/${workflow}@${ref}`);
  }
  return { ok, status: r.status };
}
