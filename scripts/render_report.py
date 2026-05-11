#!/usr/bin/env python3
"""Render the daily Teams production monitor HTML report.

Produces a 4-sheet 8.5"x11" paged document using the CandyCo Design System
(vendored at assets/design-system/):

  Sheet 1 — Org-wide briefing summary (cover, hero, stats, plant cards,
            cross-plant floor notes + watchlist)
  Sheet 2 — Lindon 1 (Caramel) self-contained brief
  Sheet 3 — Lindon 2 (Eco Moulding) self-contained brief
  Sheet 4 — Lindon 3 (Chocolate) self-contained brief

Each plant sheet is designed to print on its own so a plant leader can tear
off their page and walk the floor with it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path

REPO = "d-scott-code/teams-production-monitor"
ISSUE_URL = f"https://github.com/{REPO}/issues/{{n}}"
DS = "../assets/design-system"

PLANTS = [
    {"id": "L1", "name": "Lindon 1 — Caramel",      "accent": "#FFCA3A"},
    {"id": "L2", "name": "Lindon 2 — Eco Moulding", "accent": "#23CE6B"},
    {"id": "L3", "name": "Lindon 3 — Chocolate",    "accent": "#1982C4"},
]
TOTAL_SHEETS = 1 + len(PLANTS)

PRIORITY_CAP = {"P1": "error", "P2": "warning", "P3": "neutral"}
PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2, None: 3}

CATEGORY_ICON = {
    "Machine":   "cog",
    "Quality":   "shield-check",
    "Safety":    "triangle-alert",
    "Materials": "package",
    "Staffing":  "users",
    "Other":     "info",
}

ACCENT_RE = re.compile(r"\*([^*]+)\*")

PAGE_LOCAL_CSS = """
/* ---------- Sheet 1 — plant cards (audience grid) ---------- */
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
.plant-card .row {
  display: flex; justify-content: space-between;
  padding: 2pt 0; font-size: 8.5pt;
}
.plant-card .row .v {
  font-weight: 700; font-variant-numeric: tabular-nums; color: var(--fg-1);
}

/* ---------- Per-plant sheet — cover band ---------- */
.plant-sheet-head {
  margin: -0.5in -0.5in 14pt -0.5in;
  padding: 0.5in 0.5in 14pt 0.5in;
  border-bottom: 1px solid var(--border-default);
  position: relative;
}
.plant-sheet-head::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 8pt;
  background: var(--plant-accent, var(--primary));
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
  color-adjust: exact;
}
.plant-sheet-head .head-row {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16pt; margin-top: 14pt;
}
.plant-sheet-head .plant-name {
  font-family: var(--font-display);
  font-size: 22pt;
  line-height: 1.05;
  letter-spacing: -0.01em;
  margin: 0;
  color: var(--fg-1);
}
.plant-sheet-head .plant-id {
  font-size: 8pt; color: var(--fg-3);
  letter-spacing: 0.08em;
  margin: 4pt 0 0 0;
}
.plant-sheet-head .meta {
  text-align: right;
  font-size: 8.5pt; color: var(--fg-2);
  line-height: 1.4;
}
.plant-sheet-head .meta img {
  height: 22px; width: auto; display: block; margin-left: auto;
  margin-bottom: 4pt;
}

/* ---------- Plant narrative ---------- */
.plant-narrative {
  font-family: var(--font-serif);
  font-size: 11pt;
  line-height: 1.5;
  color: var(--fg-1);
  margin: 0 0 12pt 0;
  text-wrap: pretty;
}

/* ---------- Priorities table (extends .actions from the design system) ---------- */
.priorities-table {
  margin-top: 4pt;
}
.priorities-table thead th {
  font-size: 7.5pt;
  vertical-align: bottom;
  padding: 5pt 6pt;
}
.priorities-table tbody td {
  vertical-align: top;
  padding: 5pt 6pt;
  font-size: 8.5pt;
}
.priorities-table .pri-col { width: 22pt; text-align: center; }
.priorities-table .pri-num {
  font-weight: 800; color: var(--fg-1); font-variant-numeric: tabular-nums;
}
.priorities-table .issue-cell .title-line {
  display: block; font-weight: 600; color: var(--fg-1);
}
.priorities-table .issue-cell .num {
  color: var(--fg-3); font-variant-numeric: tabular-nums; margin-right: 4pt;
}
.priorities-table .issue-cell .summary {
  display: block;
  font-size: 8pt; color: var(--fg-2);
  line-height: 1.35; margin-top: 2pt;
  text-wrap: pretty;
}
.priorities-table .cat-cell { white-space: nowrap; }
.priorities-table .cat-cell .cat-icon {
  display: inline-block; width: 12px; height: 12px;
  vertical-align: -2px; margin-right: 4pt;
  color: var(--fg-2);
}
.priorities-table .age-col, .priorities-table .age-cell {
  text-align: right; font-variant-numeric: tabular-nums;
  white-space: nowrap; color: var(--fg-2);
}
.priorities-table .raised-cell {
  white-space: nowrap; color: var(--fg-2); font-size: 8pt;
}
.priorities-table .raised-cell .author { color: var(--fg-1); font-weight: 600; }
.priorities-table .pri-cell { text-align: center; }

/* ---------- Resolved list ---------- */
.resolved-list {
  margin: 8pt 0 12pt 0;
  padding-left: 14pt;
  font-size: 8.5pt; line-height: 1.55;
  list-style: none;
}
.resolved-list li {
  position: relative;
  padding: 2pt 0 2pt 12pt;
  color: var(--fg-1);
}
.resolved-list li::before {
  content: "✓";
  position: absolute; left: -2pt; top: 2pt;
  color: #15803d; font-weight: 700;
}
.resolved-list .num {
  color: var(--fg-3); font-variant-numeric: tabular-nums; margin-right: 4pt;
}
.resolved-list .title { font-weight: 600; color: var(--fg-1); }
.resolved-list .resolution {
  display: block;
  font-family: var(--font-serif); font-style: italic;
  color: var(--fg-2); font-size: 8pt; margin-top: 1pt;
}

/* ---------- Floor notes (sheet 1 + plant sheets) ---------- */
.floor-notes {
  margin: 10pt 0 14pt 0;
  padding: 8pt 12pt;
  background: #FAF9F4;
  border-left: 3pt solid var(--primary);
  border-radius: var(--radius-sm);
  font-size: 8.5pt;
  page-break-inside: avoid;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
  color-adjust: exact;
}
.floor-notes .eyebrow { margin-bottom: 4pt; }
.floor-notes ul { margin: 0; padding-left: 14pt; }
.floor-notes li { padding: 1pt 0; color: var(--fg-1); }
.floor-notes li .plant-tag {
  font-weight: 700; color: var(--fg-2); margin-right: 4pt;
}

/* ---------- Watchlist ---------- */
.watchlist-strip {
  margin: 8pt 0 12pt 0;
  padding: 8pt 12pt;
  background: var(--shadow-grey-50);
  border-radius: var(--radius-sm);
  font-size: 8.5pt; color: var(--fg-1);
  page-break-inside: avoid;
}
.watchlist-strip .eyebrow { margin-bottom: 4pt; }
.watchlist-strip ul { margin: 0; padding-left: 14pt; }
.watchlist-strip li { padding: 1pt 0; color: var(--fg-1); }
.watchlist-strip li .num {
  color: var(--fg-3); font-variant-numeric: tabular-nums;
  font-weight: 600; margin-right: 4pt;
}

/* ---------- Empty state for sections with no content ---------- */
.empty-state {
  padding: 8pt 0;
  color: var(--fg-3); font-style: italic; font-size: 9pt;
}

/* ---------- Misc ---------- */
.archive-link { color: var(--steel-blue); }
.section-label { margin-top: 14pt; }
"""


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------

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


def render_accents(text: str) -> str:
    """Wrap *asterisk-tokens* in an accent span."""
    parts: list[str] = []
    last = 0
    for m in ACCENT_RE.finditer(text):
        parts.append(esc(text[last:m.start()]))
        parts.append(f'<span class="accent">{esc(m.group(1))}</span>')
        last = m.end()
    parts.append(esc(text[last:]))
    return "".join(parts)


def cap(text: str, kind: str = "neutral") -> str:
    return f'<span class="cap {kind}">{esc(text)}</span>'


def fmt_first_raised(item: dict) -> str:
    """Render the 'First raised' cell. Prefers Claude's `first_raised` (author +
    time_utc from the source Teams message) over GitHub's `created_at`. Falls
    back gracefully for carry-over items that have neither."""
    fr = item.get("first_raised") or {}
    author = fr.get("author")
    time_utc = fr.get("time_utc")
    if author and time_utc:
        try:
            t = dt.datetime.fromisoformat(time_utc.replace("Z", "+00:00"))
            return (
                f'<span class="author">{esc(author)}</span><br>'
                f'<span>{t.strftime("%H:%M UTC")}</span>'
            )
        except ValueError:
            return f'<span class="author">{esc(author)}</span>'
    created = item.get("created_at")
    if created:
        try:
            t = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
            return f'<span>{t.strftime("%b %-d")}</span>'
        except ValueError:
            pass
    age = item.get("age_days")
    if age is not None:
        return f'<span>{age}d ago</span>'
    return '<span>—</span>'


def category_glyph(category: str | None) -> str:
    """Inline Lucide icon for the category. Renders as <i data-lucide=…>;
    the design system's lucide.createIcons() swaps it to an SVG on load."""
    if not category:
        return ""
    icon = CATEGORY_ICON.get(category)
    if not icon:
        return ""
    return f'<i class="cat-icon" data-lucide="{icon}"></i>'


# ---------------------------------------------------------------------
# Sheet 1: headline, stats, plant cards
# ---------------------------------------------------------------------

def headline(ledger: dict) -> tuple[str, str]:
    """Return (eyebrow, headline_html) for the hero callout.

    Prefer ledger["headline"] (Claude-written) when present. Fall back to a
    deterministic 6-mode picker for pre-change ledgers and crash safety."""
    h = ledger.get("headline") or {}
    if h.get("eyebrow") and h.get("text"):
        return (h["eyebrow"], render_accents(h["text"]))

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


def floor_notes_block(ledger: dict, plant_id: str | None = None) -> str:
    """Render the floor-notes block. When plant_id is None, include all notes
    with a plant tag. When plant_id is set, filter to just that plant and
    drop the tag (the surrounding sheet already labels the plant)."""
    notes = ledger.get("notes") or []
    if plant_id is not None:
        notes = [n for n in notes if n.get("plant") == plant_id]
    if not notes:
        return ""
    def item(n: dict) -> str:
        text = esc(n.get("text", ""))
        if plant_id is None:
            return f'<li><span class="plant-tag">{esc(n.get("plant", "—"))}</span>{text}</li>'
        return f'<li>{text}</li>'
    return (
        '<div class="floor-notes">'
        '<div class="eyebrow">Floor notes</div>'
        f'<ul>{"".join(item(n) for n in notes)}</ul>'
        '</div>'
    )


def watchlist_block(ledger: dict, plant_id: str | None,
                    open_by_num: dict[int, dict]) -> str:
    """Render the watchlist. When plant_id is set, include only items whose
    issue belongs to that plant (matched via the open-issues snapshot)."""
    wl = ledger.get("watchlist") or []
    if plant_id is not None:
        wl = [w for w in wl
              if open_by_num.get(w.get("issue_number", 0), {}).get("plant") == plant_id]
    if not wl:
        return ""
    items = []
    for w in wl:
        n = w.get("issue_number")
        reason = esc(w.get("reason", ""))
        if not n:
            continue
        items.append(
            f'<li><a class="archive-link num" href="{ISSUE_URL.format(n=n)}">#{n}</a>'
            f'<span>{reason}</span></li>'
        )
    if not items:
        return ""
    return (
        '<div class="watchlist-strip">'
        '<div class="eyebrow">Watchlist</div>'
        f'<ul>{"".join(items)}</ul>'
        '</div>'
    )


# ---------------------------------------------------------------------
# Per-plant sheet
# ---------------------------------------------------------------------

def _sort_priority(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda i: (PRIORITY_RANK.get(i.get("priority"), 3), -i.get("age_days", 0)),
    )


def priorities_table(plant_id: str, ledger: dict) -> str:
    open_now = _sort_priority([i for i in ledger.get("still_open", [])
                               if i.get("plant") == plant_id])
    if not open_now:
        return (
            '<p class="empty-state">No open issues. Clean slate.</p>'
        )

    rows: list[str] = []
    for n_idx, it in enumerate(open_now, 1):
        priority = it.get("priority")
        priority_cell = (
            cap(priority, PRIORITY_CAP[priority])
            if priority in PRIORITY_CAP else '<span class="cap neutral">—</span>'
        )
        category = it.get("category")
        cat_cell = (
            f'{category_glyph(category)}{esc(category)}'
            if category else '<span style="color: var(--fg-3);">—</span>'
        )
        summary = it.get("summary")
        summary_html = (
            f'<span class="summary">{esc(summary)}</span>' if summary else ""
        )
        age = it.get("age_days")
        age_cell = f'{age}d' if age is not None else '—'
        rows.append(
            f'<tr>'
            f'<td class="pri-col pri-num">{n_idx}</td>'
            f'<td class="issue-cell">'
            f'<span class="title-line"><span class="num">#{it["number"]}</span>'
            f'{issue_link(it["number"], it["title"])}</span>'
            f'{summary_html}'
            f'</td>'
            f'<td class="cat-cell">{cat_cell}</td>'
            f'<td class="pri-cell">{priority_cell}</td>'
            f'<td class="age-cell">{age_cell}</td>'
            f'<td class="raised-cell">{fmt_first_raised(it)}</td>'
            f'</tr>'
        )

    return f"""
<table class="actions priorities-table">
  <thead>
    <tr>
      <th class="pri-col">#</th>
      <th>Issue</th>
      <th>Category</th>
      <th class="pri-cell">Priority</th>
      <th class="age-col">Age</th>
      <th>First raised</th>
    </tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def resolved_list(plant_id: str, ledger: dict) -> str:
    closed = [i for i in ledger.get("closed_today", []) if i.get("plant") == plant_id]
    if not closed:
        return ""

    def truncate(s: str, n: int = 120) -> str:
        s = (s or "").strip()
        if len(s) <= n:
            return s
        return s[: n - 1].rstrip() + "…"

    items: list[str] = []
    for it in closed:
        resolution = truncate(it.get("resolution_comment") or "")
        resolution_html = (
            f'<span class="resolution">"{esc(resolution)}"</span>'
            if resolution else ""
        )
        items.append(
            f'<li><span class="num">#{it["number"]}</span>'
            f'<span class="title">{esc(it["title"])}</span>'
            f'{resolution_html}</li>'
        )
    return (
        '<h3 class="section-label">Resolved in the last 24 hours</h3>'
        f'<ul class="resolved-list">{"".join(items)}</ul>'
    )


def plant_sheet(plant: dict, ledger: dict, page_num: int, total: int,
                long_date: str, open_by_num: dict[int, dict]) -> str:
    p = plant["id"]
    closed_n = sum(1 for i in ledger.get("closed_today", []) if i.get("plant") == p)
    opened_n = sum(1 for i in ledger.get("opened_today", []) if i.get("plant") == p)
    open_items = [i for i in ledger.get("still_open", []) if i.get("plant") == p]
    oldest = max((i.get("age_days", 0) for i in open_items), default=0)
    narrative = (ledger.get("per_plant_summary") or {}).get(p, "")
    narrative_html = (
        f'<p class="plant-narrative">{esc(narrative)}</p>'
        if narrative else
        '<p class="plant-narrative" style="color: var(--fg-3); font-style: italic;">'
        'No activity in the last 24 hours.</p>'
    )

    priorities = priorities_table(p, ledger)
    resolved = resolved_list(p, ledger)
    plant_watch = watchlist_block(ledger, p, open_by_num)
    plant_notes_html = floor_notes_block(ledger, p)

    return f"""
<!-- ========== SHEET {page_num} — {esc(plant["name"])} ========== -->
<section class="sheet" style="--plant-accent: {plant["accent"]};">
  <div class="plant-sheet-head">
    <div class="head-row">
      <div>
        <h1 class="plant-name">{esc(plant["name"])}</h1>
        <div class="plant-id">{esc(p)} · Production briefing</div>
      </div>
      <div class="meta">
        <img src="{DS}/assets/logo/candyco-logo-black.png" alt="CandyCo">
        <div>{esc(long_date)}</div>
        <div>08:00 America/Denver</div>
      </div>
    </div>
  </div>

  {narrative_html}

  <div class="stats">
    {stat_card("Resolved", str(closed_n), "Closed in the last 24 hours")}
    {stat_card("Newly raised", str(opened_n), "New issues opened today")}
    {stat_card("Still open", str(len(open_items)), "Items on the floor")}
    {stat_card("Oldest open", f"{oldest}d", "Longest-running issue")}
  </div>

  <h3 class="section-label">Today's priorities</h3>
  {priorities}

  {resolved}
  {plant_watch}
  {plant_notes_html}

  <div class="sheet-footer">
    <span class="doc">{esc(plant["name"])} · Production briefing · {esc(ledger.get("date", ""))}</span>
    <span class="page-no">Page {page_num} of {total}</span>
  </div>
</section>"""


# ---------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------

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

    # Index open issues by number so the watchlist filter can match plant
    open_by_num = {i["number"]: i for i in still_open}

    cards = "".join(plant_card(p, ledger) for p in PLANTS)
    plant_sheets = "".join(
        plant_sheet(p, ledger, page_num=2 + idx, total=TOTAL_SHEETS,
                    long_date=long_date, open_by_num=open_by_num)
        for idx, p in enumerate(PLANTS)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Production briefing — {esc(date)} · CandyCo</title>
<link rel="stylesheet" href="{DS}/colors_and_type.css">
<link rel="stylesheet" href="{DS}/report-template/report.css">
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<style>{PAGE_LOCAL_CSS}</style>
</head>
<body>
<div class="doc-frame">

<!-- ========== SHEET 1 — ORG-WIDE BRIEFING SUMMARY ========== -->
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

  <h3 class="section-label">By plant</h3>
  <div class="audience-grid" style="grid-template-columns: 1fr 1fr 1fr;">
    {cards}
  </div>

  {floor_notes_block(ledger)}
  {watchlist_block(ledger, None, open_by_num)}

  <p style="font-size: 7.5pt; color: var(--fg-3); margin-top: 14pt;">
    Issue ledger:
    <a class="archive-link" href="https://github.com/{REPO}/issues?q=is%3Aopen+label%3Aplant%3AL1%2Cplant%3AL2%2Cplant%3AL3">open issues on GitHub</a> ·
    <a class="archive-link" href="../index.html">archive of past briefings</a>
  </p>

  <div class="sheet-footer">
    <span class="doc">Production briefing · {esc(date)}</span>
    <span class="page-no">Page 1 of {TOTAL_SHEETS}</span>
  </div>
</section>

{plant_sheets}

</div>
<script>if (window.lucide) window.lucide.createIcons();</script>
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
