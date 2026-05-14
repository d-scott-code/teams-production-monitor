// Cloudflare Worker — "Mark resolved" button endpoint for the daily production
// briefing. The report (rendered by scripts/render_report.py) embeds a signed
// URL on each open priority. A plant leader taps the button, lands on a
// confirmation page, taps "Confirm close", and the worker closes the GitHub
// issue with a comment.
//
// Routes:
//   GET  /close?i=<num>&e=<expiry-epoch>&t=<hmac>   →  confirmation page
//   POST /close?i=<num>&e=<expiry-epoch>&t=<hmac>   →  closes the issue, returns "done"
//
// Security:
//   - The HMAC binds (issue_number, expiry) to a shared secret known to the
//     worker and the renderer. Anyone with the URL can close that issue, but
//     they can't forge URLs for other issues without the secret.
//   - The expiry caps replay risk to a 7-day window. Tampering with `i` or `e`
//     invalidates the signature.
//   - GET is read-only (renders the confirmation page) so crawlers, browser
//     link-preview, or accidental prefetch can't close issues.
//
// Required Worker secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN   fine-grained PAT, scope: Issues read+write on the repo
//   HMAC_SECRET    random string, must match $CLOSE_BUTTON_HMAC_SECRET in CI
//
// Optional Worker vars (set in wrangler.toml [vars]):
//   GITHUB_REPO    defaults to "d-scott-code/teams-production-monitor"

const DEFAULT_REPO = "d-scott-code/teams-production-monitor";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/close") {
      return html(404, page("Not found", "<p>Unknown route.</p>"));
    }

    const issue = parseInt(url.searchParams.get("i") || "", 10);
    const expiry = parseInt(url.searchParams.get("e") || "", 10);
    const token = url.searchParams.get("t") || "";

    if (!issue || !expiry || !token) {
      return html(400, page("Bad request", "<p>Missing or invalid parameters.</p>"));
    }
    if (Math.floor(Date.now() / 1000) > expiry) {
      return html(410, page(
        "Link expired",
        "<p>This close link has expired (links are valid for 7 days from the report date). " +
        "Open today's report and try again.</p>"
      ));
    }
    if (!(await verifyHmac(env.HMAC_SECRET, `${issue}.${expiry}`, token))) {
      return html(403, page("Invalid signature", "<p>This link is not valid.</p>"));
    }

    const repo = env.GITHUB_REPO || DEFAULT_REPO;

    if (request.method === "GET") {
      const meta = await fetchIssue(env.GITHUB_TOKEN, repo, issue);
      if (!meta.ok) {
        return html(meta.status, page("Issue not found", `<p>${escapeHtml(meta.error)}</p>`));
      }
      if (meta.issue.state === "closed") {
        return html(200, page(
          `#${issue} is already closed`,
          `<p class="title">${escapeHtml(meta.issue.title)}</p>` +
          `<p class="note">No action needed — this issue was closed previously.</p>` +
          `<p><a href="https://github.com/${repo}/issues/${issue}">View on GitHub</a></p>`
        ));
      }
      return html(200, confirmPage(issue, meta.issue.title, url.search));
    }

    if (request.method === "POST") {
      const result = await closeIssue(env.GITHUB_TOKEN, repo, issue);
      if (!result.ok) {
        return html(result.status, page("Could not close issue", `<p>${escapeHtml(result.error)}</p>`));
      }
      return html(200, page(
        `Closed #${issue}`,
        `<p class="title">${escapeHtml(result.title)}</p>` +
        `<p class="note">Resolved via report button. The team will see the update in tomorrow's briefing.</p>` +
        `<p><a href="https://github.com/${repo}/issues/${issue}">View on GitHub</a></p>`
      ));
    }

    return html(405, page("Method not allowed", "<p>Use GET or POST.</p>"));
  },
};

// ---------- HMAC ----------

async function verifyHmac(secret, message, hexToken) {
  const expected = await hmacHex(secret, message);
  if (expected.length !== hexToken.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ hexToken.charCodeAt(i);
  }
  return diff === 0;
}

async function hmacHex(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  const bytes = new Uint8Array(sig);
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return hex.slice(0, 32);
}

// ---------- GitHub API ----------

async function fetchIssue(token, repo, n) {
  const r = await fetch(`https://api.github.com/repos/${repo}/issues/${n}`, {
    headers: ghHeaders(token),
  });
  if (r.status === 404) return { ok: false, status: 404, error: `Issue #${n} not found.` };
  if (!r.ok) return { ok: false, status: 502, error: `GitHub returned ${r.status}.` };
  const issue = await r.json();
  if (issue.pull_request) {
    return { ok: false, status: 400, error: "That number is a pull request, not an issue." };
  }
  return { ok: true, issue };
}

async function closeIssue(token, repo, n) {
  const meta = await fetchIssue(token, repo, n);
  if (!meta.ok) return { ok: false, status: meta.status, error: meta.error };
  if (meta.issue.state === "closed") {
    return { ok: true, title: meta.issue.title };
  }

  const commentBody = "Resolved on the floor — closed via report button.";
  const c = await fetch(`https://api.github.com/repos/${repo}/issues/${n}/comments`, {
    method: "POST",
    headers: { ...ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ body: commentBody }),
  });
  if (!c.ok) return { ok: false, status: 502, error: `Could not add comment (${c.status}).` };

  const p = await fetch(`https://api.github.com/repos/${repo}/issues/${n}`, {
    method: "PATCH",
    headers: { ...ghHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ state: "closed" }),
  });
  if (!p.ok) return { ok: false, status: 502, error: `Could not close (${p.status}).` };

  return { ok: true, title: meta.issue.title };
}

function ghHeaders(token) {
  return {
    "Authorization": `Bearer ${token}`,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "teams-production-monitor-close-worker",
  };
}

// ---------- HTML ----------

function html(status, body) {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Robots-Tag": "noindex, nofollow",
    },
  });
}

function page(heading, bodyHtml) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>${escapeHtml(heading)} — CandyCo production briefing</title>
  <style>${BASE_CSS}</style>
</head>
<body>
  <main>
    <h1>${escapeHtml(heading)}</h1>
    ${bodyHtml}
  </main>
</body>
</html>`;
}

function confirmPage(issue, title, qs) {
  return page(
    `Close issue #${issue}?`,
    `<p class="title">${escapeHtml(title)}</p>
     <form method="POST" action="/close${qs}">
       <button type="submit" class="primary">Mark #${issue} resolved</button>
     </form>
     <p class="note">This will close the GitHub issue and post a "resolved on the floor" comment. If you tapped this by mistake, close the tab.</p>`
  );
}

const BASE_CSS = `
  :root {
    --fg: #272838;
    --fg-2: #525463;
    --fg-3: #7a7c8a;
    --bg: #fbf9f4;
    --card: #fff;
    --border: #e6e3da;
    --green: #15803d;
    --green-dark: #0f5f2d;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
  }
  main {
    max-width: 480px;
    margin: 0 auto;
    padding: 40px 24px;
  }
  h1 {
    font-size: 22px;
    font-weight: 700;
    margin: 0 0 16px 0;
    letter-spacing: -0.01em;
  }
  p { margin: 0 0 16px 0; }
  p.title {
    font-size: 17px;
    color: var(--fg);
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
  }
  p.note { color: var(--fg-2); font-size: 14px; }
  a { color: var(--fg); text-decoration: underline; }
  form { margin: 24px 0; }
  button.primary {
    width: 100%;
    min-height: 56px;
    font-size: 17px;
    font-weight: 600;
    color: #fff;
    background: var(--green);
    border: 0;
    border-radius: 10px;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  button.primary:active { background: var(--green-dark); }
`;

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
