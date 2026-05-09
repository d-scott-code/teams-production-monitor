#!/usr/bin/env python3
"""Render the daily Teams production monitor HTML report.

Produces a 2-sheet 8.5"x11" paged document using the CandyCo Design System
(vendored at assets/design-system/). Sheet 1 is the cover + executive
summary; sheet 2 is per-plant detail.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path

REPO = "d-scott-code/teams-production-monitor"
ISSUE_URL = f"https://github.com/{REPO}/issues/{{n}}"
DS = "../assets/design-system"

PLANTS = [
    {"id": "L1", "name": "Lindon 1 — Caramel",      "accent": "#FFCA3A"},
    {"id": "L2", "name": "Lindon 2 — Eco Moulding", "accent": "#23CE6B"},
    {"id": "L3", "name": "Lindon 3 — Chocolate",    "accent": "#1982C4"},
]

PAGE_LOCAL_CSS = """
.plant-block {
  margin: 10pt 0 14pt 0;
  padding: 10pt 12pt 12pt 14pt;
  background: var(--bg-1);
  border: 1px solid var(--border-subtle);
  border-left: 4pt solid var(--plant-accent, var(--primary));
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  page-break-inside: avoid;
}
.plant-block .plant-head {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 12pt; margin-bottom: 6pt;
}
.plant-block .plant-head h3 {
  margin: 0; font-size: 12pt; color: var(--fg-1);
}
.plant-block .plant-head .stat-line {
  font-size: 8.5pt; color: var(--fg-2); font-variant-numeric: tabular-nums;
}
.plant-block .plant-head .stat-line strong { color: var(--fg-1); }
.plant-block .lists {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12pt;
}
.plant-block .lists .col .eyebrow { margin-bottom: 4pt; }
.plant-block .lists .col ul {
  list-style: none; margin: 0; padding: 0;
  font-size: 8.5pt; line-height: 1.45;
}
.plant-block .lists .col li {
  padding: 3pt 0; border-bottom: 1px dashed var(--border-subtle);
  display: flex; gap: 6pt; align-items: baseline;
}
.plant-block .lists .col li:last-child { border-bottom: none; }
.plant-block .lists .col .num {
  color: var(--fg-3); font-variant-numeric: tabular-nums;
  min-width: 26pt; font-size: 8pt;
}
.plant-block .lists .col .age {
  margin-left: auto; color: var(--fg-3); font-size: 7.5pt; white-space: nowrap;
}
.plant-block .lists .col .empty {
  color: var(--fg-3); font-style: italic; font-size: 8.5pt;
}
.plant-card {
  background: var(--bg-1);
  border: 1px solid var(--border-subtle);
  border-top: 4pt solid var(--plant-accent, var(--primary));
  border-radius: var(--radius);
  padding: 10pt 12pt;
  box-shadow: var(--shadow-sm);
  page-break-inside: avoid;
}
.plant-card .head {
  display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 5pt; margin-bottom: 6pt;
}
.plant-card .title { font-weight: 700; font-size: 10pt; color: var(--fg-1); }
.plant-card .scale { font-size: 7.5pt; color: var(--fg-3); }
.plant-card .row { display: flex; justify-content: space-between; padding: 2pt 0; font-size: 8.5pt; }
.plant-card .row .v { font-weight: 700; font-variant-numeric: tabular-nums; color: var(--fg-1); }
.archive-link { color: var(--steel-blue); }
"""


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def issue_link(num: int, title: str) -> str:
    return f'<a href="{ISSUE_URL.format(n=num)}">{esc(title)}</a>'


def fmt_date(date: str) -> str:
    return dt.datetime.strptime(date, "%Y-%m-%d").strftime("%B %-d, %Y")


def fmt_window(window: dict) -> str:
    if not window.get("start_utc") or not window.get("end_utc"):
        return ""
    s = dt.datetime.fromisoformat(window["start_utc"]).strftime("%b %-d %H:%M UTC")
    e = dt.datetime.fromisoformat(window["end_utc"]).strftime("%b %-d %H:%M UTC")
    return f"{s} → {e}"


def headline(ledger: dict) -> tuple[str, str]:
    """Return (eyebrow, headline_html) for the hero callout."""
    open_issues = ledger.get("still_open", [])
    closed = ledger.get("closed_today", [])
    opened = ledger.get("opened_today", [])

    if open_issues:
        oldest = max(open_issues, key=lambda i: i.get("age_days", 0))
        if oldest.get("age_days", 0) >= 7:
            return ("Long-running issue", (
                f'<span class="accent">{oldest["age_days"]} days open</span> · '
                f'<strong>{esc(oldest["plant"])}</strong> #{oldest["number"]} '
                f'— {esc(oldest["title"])}.'
            ))
    if not opened and not closed and not open_issues:
        return ("Quiet 24 hours", "No new issues raised. Nothing escalated. Nothing carrying over.")
    if len(closed) >= len(opened) and len(closed) > 0:
        net = len(closed) - len(opened)
        if net > 0:
            return ("Net closure", (
                f'<strong>{len(closed)}</strong> resolved against '
                f'<strong>{len(opened)}</strong> newly raised — '
                f'<span class="accent">net &minus;{net}</span>.'
            ))
        return ("Held the line", (
            f'<strong>{len(closed)}</strong> resolved, '
            f'<strong>{len(opened)}</strong> newly raised. Wash.'
        ))
    if opened and not closed:
        return ("New volume", (
            f'<strong>{len(opened)}</strong> newly raised, '
            f'<span class="accent">none closed</span>. Watch tomorrow.'
        ))
    if open_issues and not opened and not closed:
        return ("Holding pattern", (
            f'<strong>{len(open_issues)}</strong> still open, no movement today.'
        ))
    return ("Today", (
        f'<strong>{len(closed)}</strong> resolved · '
        f'<strong>{len(opened)}</strong> newly raised · '
        f'<strong>{len(open_issues)}</strong> still open across L1/L2/L3.'
    ))


def stat_card(eyebrow: str, value: str, sub: str) -> str:
    return (
        f'<div class="stat">'
        f'<div class="eyebrow">{esc(eyebrow)}</div>'
        f'<div class="num">{esc(value)}</div>'
        f'<div class="sub">{esc(sub)}</div>'
        f'</div>'
    )


def plant_card(plant: dict, ledger: dict) -> str:
    p = plant["id"]
    closed = sum(1 for i in ledger.get("closed_today", []) if i.get("plant") == p)
    opened = sum(1 for i in ledger.get("opened_today", []) if i.get("plant") == p)
    open_now = [i for i in ledger.get("still_open", []) if i.get("plant") == p]
    oldest = max((i.get("age_days", 0) for i in open_now), default=0)
    return (
        f'<div class="plant-card" style="--plant-accent: {plant["accent"]};">'
        f'  <div class="head"><div class="title">{esc(plant["name"])}</div>'
        f'    <div class="scale">{p}</div></div>'
        f'  <div class="row"><span>Resolved</span><span class="v">{closed}</span></div>'
        f'  <div class="row"><span>Newly raised</span><span class="v">{opened}</span></div>'
        f'  <div class="row"><span>Still open</span><span class="v">{len(open_now)}</span></div>'
        f'  <div class="row"><span>Oldest open</span><span class="v">{oldest}d</span></div>'
        f'</div>'
    )


def plant_block(plant: dict, ledger: dict) -> str:
    p = plant["id"]
    closed = [i for i in ledger.get("closed_today", []) if i.get("plant") == p]
    opened = [i for i in ledger.get("opened_today", []) if i.get("plant") == p]
    open_now = [i for i in ledger.get("still_open", []) if i.get("plant") == p]

    def li(i: dict, show_age: bool = False) -> str:
        age = ""
        if show_age and (d := i.get("age_days")) is not None:
            age = f'<span class="age">{d}d open</span>'
        return (
            f'<li><span class="num">#{i["number"]}</span>'
            f'<span>{issue_link(i["number"], i["title"])}</span>{age}</li>'
        )

    def col(label: str, items: list, *, show_age: bool, empty_text: str) -> str:
        if not items:
            body = f'<p class="empty">{esc(empty_text)}</p>'
        else:
            body = "<ul>" + "".join(li(i, show_age=show_age) for i in items) + "</ul>"
        return (
            f'<div class="col">'
            f'<div class="eyebrow">{esc(label)}</div>{body}'
            f'</div>'
        )

    stat = (
        f'<strong>{len(closed)}</strong> resolved · '
        f'<strong>{len(opened)}</strong> newly raised · '
        f'<strong>{len(open_now)}</strong> still open'
    )

    return f"""
<section class="plant-block" style="--plant-accent: {plant["accent"]};">
  <div class="plant-head">
    <h3>{esc(plant["name"])}</h3>
    <div class="stat-line">{stat}</div>
  </div>
  <div class="lists">
    {col("What went well", closed, show_age=False, empty_text="No resolutions in the last 24 hours.")}
    {col("What didn't", opened, show_age=False, empty_text="No new issues opened in the last 24 hours.")}
    {col("Today's priorities", open_now, show_age=True, empty_text="No open issues. Clean slate.")}
  </div>
</section>"""


def render(ledger: dict, messages: dict, date: str) -> str:
    eyebrow_text, headline_html = headline(ledger)
    closed_today = ledger.get("closed_today", [])
    opened_today = ledger.get("opened_today", [])
    still_open = ledger.get("still_open", [])
    oldest_age = max((i.get("age_days", 0) for i in still_open), default=0)
    window = fmt_window(messages.get("window", {}))
    msg_count = messages.get("message_count", 0)
    chat_count = messages.get("chat_count", 0)
    long_date = fmt_date(date)

    cards = "".join(plant_card(p, ledger) for p in PLANTS)
    blocks = "".join(plant_block(p, ledger) for p in PLANTS)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Production briefing — {esc(date)} · CandyCo</title>
<link rel="stylesheet" href="{DS}/colors_and_type.css">
<link rel="stylesheet" href="{DS}/report-template/report.css">
<style>{PAGE_LOCAL_CSS}</style>
</head>
<body>
<div class="doc-frame">

<!-- ========== SHEET 1 — COVER + EXECUTIVE SUMMARY ========== -->
<section class="sheet">
  <div class="cover-head">
    <div class="brand">
      <img src="{DS}/assets/logo/candyco-logo-black.png" alt="CandyCo">
    </div>
    <div class="doc-meta">
      <div class="eyebrow" style="font-size: 7pt;">Production briefing</div>
      <div>{esc(long_date)} &nbsp;·&nbsp; 08:00 America/Denver</div>
    </div>
  </div>

  <h1>Production briefing</h1>
  <p class="lead">Last 24 hours across {", ".join(p["name"] for p in PLANTS)}. Distribution: Operations, FSQA, plant leadership.</p>

  <div class="meta-strip">
    <div class="item"><div class="eyebrow">Window</div><div class="v">{esc(window) or "—"}</div></div>
    <div class="item"><div class="eyebrow">Messages</div><div class="v">{msg_count} across {chat_count} chats</div></div>
    <div class="item"><div class="eyebrow">Plants in scope</div><div class="v">L1 · L2 · L3</div></div>
    <div class="item"><div class="eyebrow">Issues touched</div><div class="v">{len(opened_today) + len(closed_today)} today</div></div>
  </div>

  <h2>Executive summary</h2>

  <div class="hero">
    <div class="eyebrow">{esc(eyebrow_text)}</div>
    <p class="headline">{headline_html}</p>
  </div>

  <div class="stats">
    {stat_card("Resolved", str(len(closed_today)), "Closed in the last 24 hours")}
    {stat_card("Newly raised", str(len(opened_today)), "New issues opened today")}
    {stat_card("Still open", str(len(still_open)), "Across L1, L2, L3")}
    {stat_card("Oldest open", f"{oldest_age}d", "Longest-running issue")}
  </div>

  <h3>By plant</h3>
  <div class="audience-grid" style="grid-template-columns: 1fr 1fr 1fr;">
    {cards}
  </div>

  <div class="sheet-footer">
    <span class="doc">Production briefing · {esc(date)}</span>
    <span class="page-no">Page 1 of 2</span>
  </div>
</section>

<!-- ========== SHEET 2 — BY-PLANT DETAIL ========== -->
<section class="sheet">
  <h2>Plant detail</h2>
  <p class="lead">What went well, what didn't, and where to focus today.</p>

  {blocks}

  <p style="font-size: 7.5pt; color: var(--fg-3); margin-top: 14pt;">
    Issue ledger:
    <a class="archive-link" href="https://github.com/{REPO}/issues?q=is%3Aopen+label%3Aplant%3AL1%2Cplant%3AL2%2Cplant%3AL3">open issues on GitHub</a> ·
    <a class="archive-link" href="../index.html">archive of past briefings</a>
  </p>

  <div class="sheet-footer">
    <span class="doc">Production briefing · {esc(date)}</span>
    <span class="page-no">Page 2 of 2</span>
  </div>
</section>

</div>
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
