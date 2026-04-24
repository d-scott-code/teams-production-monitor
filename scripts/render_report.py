#!/usr/bin/env python3
"""Render the daily Teams production monitor HTML report.

Reads a messages dump (from fetch_teams_messages.py) and a ledger JSON
describing today's issue outcomes, and writes a single self-contained HTML
file suitable for serving via GitHub Pages.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path

REPO = "d-scott-code/teams-production-monitor"
ISSUE_URL = f"https://github.com/{REPO}/issues/{{n}}"
PLANT_NAME = {
    "L1": "L1 — Caramel",
    "L2": "L2 — Eco Moulding",
    "L3": "L3 — Chocolate",
}

CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 900px; margin: 2rem auto; padding: 0 1.25rem; line-height: 1.55; }
h1 { margin-bottom: 0.1rem; }
.date { color: #666; margin-top: 0; }
.summary { background: #f5f7fa; border: 1px solid #dde3ea; border-radius: 10px;
           padding: 1rem 1.25rem; margin: 1.5rem 0; }
.summary b { font-variant-numeric: tabular-nums; }
.plant { border-top: 1px solid #dde3ea; padding-top: 1.25rem; margin-top: 2rem; }
.plant h2 { margin-bottom: 0.25rem; }
.plant .stat { color: #666; font-size: 0.95rem; margin-top: 0; }
.section { margin: 1rem 0 1.25rem; }
.section h3 { font-size: 1rem; text-transform: uppercase; letter-spacing: 0.05em;
              color: #555; margin-bottom: 0.35rem; }
ul.issues { list-style: none; padding: 0; margin: 0; }
ul.issues li { padding: 0.35rem 0; display: flex; gap: 0.75rem;
               align-items: baseline; border-bottom: 1px dashed #e5e5e5; }
ul.issues li:last-child { border-bottom: 0; }
ul.issues .num { color: #888; font-variant-numeric: tabular-nums; min-width: 3.2rem; }
ul.issues .age { color: #999; font-size: 0.85rem; margin-left: auto; white-space: nowrap; }
.empty { color: #888; font-style: italic; }
.went-well h3 { color: #1b8f4a; }
.didnt h3 { color: #a83232; }
.footer { margin-top: 3rem; font-size: 0.85rem; color: #888; }
a { color: #0a66c2; text-decoration: none; }
a:hover { text-decoration: underline; }
@media (prefers-color-scheme: dark) {
  body { background: #1a1a1a; color: #e6e6e6; }
  .date, .section h3, .plant .stat, ul.issues .num, ul.issues .age, .footer { color: #aaa; }
  .summary { background: #242424; border-color: #333; }
  .plant { border-top-color: #333; }
  ul.issues li { border-bottom-color: #2a2a2a; }
  a { color: #5aa7ff; }
  .went-well h3 { color: #5bcf84; }
  .didnt h3 { color: #e06b6b; }
}
"""


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def link(num: int, title: str) -> str:
    return f'<a href="{ISSUE_URL.format(n=num)}">#{num}</a> {esc(title)}'


def issue_list(
    issues: list[dict], *, show_age: bool = False, empty: str = "Nothing here."
) -> str:
    if not issues:
        return f'<p class="empty">{esc(empty)}</p>'
    rows = []
    for i in issues:
        age = ""
        if show_age and (d := i.get("age_days")) is not None:
            age = f'<span class="age">{d}d open</span>'
        rows.append(
            f'<li><span class="num">#{i["number"]}</span>'
            f'<span><a href="{ISSUE_URL.format(n=i["number"])}">{esc(i["title"])}</a></span>'
            f"{age}</li>"
        )
    return f'<ul class="issues">{"".join(rows)}</ul>'


def plant_section(plant: str, ledger: dict) -> str:
    closed = [i for i in ledger.get("closed_today", []) if i.get("plant") == plant]
    opened = [i for i in ledger.get("opened_today", []) if i.get("plant") == plant]
    open_now = [i for i in ledger.get("still_open", []) if i.get("plant") == plant]
    stat = (
        f"<b>{len(closed)}</b> closed · "
        f"<b>{len(opened)}</b> new · "
        f"<b>{len(open_now)}</b> still open"
    )
    return f"""
<section class="plant">
  <h2>{esc(PLANT_NAME.get(plant, plant))}</h2>
  <p class="stat">{stat}</p>
  <div class="section went-well">
    <h3>What went well</h3>
    {issue_list(closed, empty="No resolutions in the last 24 hours.")}
  </div>
  <div class="section didnt">
    <h3>What didn't</h3>
    {issue_list(opened, empty="No new issues opened in the last 24 hours.")}
  </div>
  <div class="section">
    <h3>Today's priorities</h3>
    {issue_list(open_now, show_age=True, empty="No open issues. Clean slate.")}
  </div>
</section>
"""


def render(ledger: dict, messages: dict, date: str) -> str:
    totals = {
        "closed": len(ledger.get("closed_today", [])),
        "opened": len(ledger.get("opened_today", [])),
        "open": len(ledger.get("still_open", [])),
    }
    window = messages.get("window", {})
    window_line = ""
    if window.get("start_utc") and window.get("end_utc"):
        start = dt.datetime.fromisoformat(window["start_utc"]).strftime("%b %d %H:%M UTC")
        end = dt.datetime.fromisoformat(window["end_utc"]).strftime("%b %d %H:%M UTC")
        window_line = f"Window: {start} → {end} · {messages.get('message_count', 0)} messages across {messages.get('chat_count', 0)} chats."
    body = "".join(plant_section(p, ledger) for p in ("L1", "L2", "L3"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Production Briefing — {esc(date)}</title>
<style>{CSS}</style>
</head>
<body>
<h1>Production Briefing</h1>
<p class="date">{esc(date)} · compiled 08:00 America/Denver</p>

<div class="summary">
  <b>{totals['closed']}</b> resolved ·
  <b>{totals['opened']}</b> newly raised ·
  <b>{totals['open']}</b> still open across L1/L2/L3.
  {f"<br><small>{esc(window_line)}</small>" if window_line else ""}
</div>

{body}

<p class="footer">
  Archive: <a href="../index.html">all reports</a> ·
  Issue ledger: <a href="https://github.com/{REPO}/issues?q=is%3Aissue+label%3Aplant%3AL1%2Cplant%3AL2%2Cplant%3AL3">open issues</a>
</p>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--messages", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    messages = json.loads(Path(args.messages).read_text())
    ledger = json.loads(Path(args.ledger).read_text())
    date = ledger.get("date") or dt.date.today().isoformat()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(ledger, messages, date))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
