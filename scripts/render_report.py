#!/usr/bin/env python3
"""Render the daily Teams production monitor HTML report.

Window-only design: every section reflects what happened in the last 24h.
There is no "still open across days" tracking and no cumulative state.

Produces a 4-sheet 8.5"x11" paged document using the CandyCo Design System
(vendored at assets/design-system/):

  Sheet 1 — Org-wide briefing summary (cover, hero, stats, plant cards,
            cross-plant floor notes)
  Sheet 2 — Lindon 1 (Caramel)
  Sheet 3 — Lindon 2 (Moulding)
  Sheet 4 — Lindon 3 (Chocolate)

Each plant sheet has two sections: "Resolved" (raised and cleared in the
window) and "Needs attention" (raised in the window, not yet cleared).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")

DS = "../assets/design-system"

# Plant naming follows CandyCo design system: L2 is "Moulding" — "Eco" is
# retired (see README in the candyco-design-system plugin). Per design rules,
# we identify plants through text (the card title), never via colored chrome.
PLANTS = [
    {"id": "L1", "name": "Lindon 1 — Caramel"},
    {"id": "L2", "name": "Lindon 2 — Moulding"},
    {"id": "L3", "name": "Lindon 3 — Chocolate"},
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
/* All cards are neutral — meaning lives in the data, not the chrome.
   No top/left accent stripes per the CandyCo design system. */

/* ---------- Sheet 1 — plant cards ---------- */
.plant-card {
  background: var(--bg-1);
  border: 1px solid var(--border-subtle);
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
.plant-card .scale { font-size: 7.5pt; color: var(--fg-3); letter-spacing: 0.08em; }
.plant-card .row {
  display: flex; justify-content: space-between;
  padding: 2pt 0; font-size: 8.5pt;
}
.plant-card .row .v {
  font-weight: 700; font-variant-numeric: tabular-nums; color: var(--fg-1);
}

/* ---------- Per-plant sheet — cover band (logo lockup at 42pt) ---------- */
.plant-sheet-head {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16pt;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 10pt; margin-bottom: 12pt;
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
  text-transform: uppercase;
}
.plant-sheet-head .meta {
  text-align: right;
  font-size: 8.5pt; color: var(--fg-2);
  line-height: 1.4;
}
.plant-sheet-head .meta img {
  /* Logo PNGs carry a 4% transparent margin so artwork renders at 38px when
     the box is 42px — matches the design system's cover-head lockup. */
  height: 42px; width: auto; display: block; margin-left: auto;
  margin: -2px 0 4pt auto;
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

/* ---------- Entry table (used for both resolved and needs_attention) ---------- */
.entry-table {
  margin-top: 4pt;
}
.entry-table thead th {
  font-size: 7.5pt;
  vertical-align: bottom;
  padding: 5pt 6pt;
}
.entry-table tbody td {
  vertical-align: top;
  padding: 5pt 6pt;
  font-size: 8.5pt;
}
.entry-table .pri-col { width: 22pt; text-align: center; }
.entry-table .pri-num {
  font-weight: 800; color: var(--fg-1); font-variant-numeric: tabular-nums;
}
.entry-table .issue-cell .title-line {
  display: block; font-weight: 600; color: var(--fg-1);
}
.entry-table .issue-cell .summary {
  display: block;
  font-size: 8pt; color: var(--fg-2);
  line-height: 1.35; margin-top: 2pt;
  text-wrap: pretty;
}
.entry-table .issue-cell .resolution,
.entry-table .issue-cell .status {
  display: block;
  font-family: var(--font-serif); font-style: italic;
  font-size: 8pt; color: var(--fg-2);
  margin-top: 3pt;
  text-wrap: pretty;
}
/* No emoji — section heading "Resolved" and the italic resolution text
   carry the meaning. */
.entry-table .cat-cell { white-space: nowrap; }
.entry-table .cat-cell .cat-icon {
  display: inline-block; width: 12px; height: 12px;
  vertical-align: -2px; margin-right: 4pt;
  color: var(--fg-2);
}
.entry-table .raised-cell {
  white-space: nowrap; color: var(--fg-2); font-size: 8pt;
}
.entry-table .raised-cell .author { color: var(--fg-1); font-weight: 600; }
.entry-table .pri-cell { text-align: center; }

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


def fmt_date(date: str) -> str:
    return dt.datetime.strptime(date, "%Y-%m-%d").strftime("%B %-d, %Y")


def _to_mt(iso: str) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(MT)


def fmt_window(window: dict) -> str:
    start = window.get("start_mt") or window.get("start_utc")
    end = window.get("end_mt") or window.get("end_utc")
    if not start or not end:
        return ""
    s = _to_mt(start)
    e = _to_mt(end)
    if not s or not e:
        return ""
    return f'{s.strftime("%b %-d %H:%M MT")} → {e.strftime("%b %-d %H:%M MT")}'


def render_accents(text: str) -> str:
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
    fr = item.get("first_raised") or {}
    author = fr.get("author")
    time_utc = fr.get("time_utc")
    if author and time_utc:
        t = _to_mt(time_utc)
        if t:
            return (
                f'<span class="author">{esc(author)}</span><br>'
                f'<span>{t.strftime("%H:%M MT")}</span>'
            )
        return f'<span class="author">{esc(author)}</span>'
    return '<span>—</span>'


def category_glyph(category: str | None) -> str:
    if not category:
        return ""
    icon = CATEGORY_ICON.get(category)
    if not icon:
        return ""
    return f'<i class="cat-icon" data-lucide="{icon}"></i>'


def _sort_priority(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda i: (PRIORITY_RANK.get(i.get("priority"), 3),
                       i.get("first_raised", {}).get("time_utc", "")),
    )


# ---------------------------------------------------------------------
# Sheet 1: headline, stats, plant cards
# ---------------------------------------------------------------------

def headline(ledger: dict) -> tuple[str, str]:
    h = ledger.get("headline") or {}
    if h.get("eyebrow") and h.get("text"):
        return (h["eyebrow"], render_accents(h["text"]))
    needs = ledger.get("needs_attention", [])
    resolved = ledger.get("resolved", [])
    if not needs and not resolved:
        return ("Quiet 24 hours", "No production issues raised in the last 24 hours.")
    return ("Today", (
        f'<strong>{len(resolved)}</strong> resolved · '
        f'<strong>{len(needs)}</strong> still needing attention across L1/L2/L3.'
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
    resolved = sum(1 for i in ledger.get("resolved", []) if i.get("plant") == p)
    needs = [i for i in ledger.get("needs_attention", []) if i.get("plant") == p]
    p1_needs = sum(1 for i in needs if i.get("priority") == "P1")
    return (
        f'<div class="plant-card">'
        f'  <div class="head"><div class="title">{esc(plant["name"])}</div>'
        f'    <div class="scale">{p}</div></div>'
        f'  <div class="row"><span>Resolved</span><span class="v">{resolved}</span></div>'
        f'  <div class="row"><span>Needs attention</span><span class="v">{len(needs)}</span></div>'
        f'  <div class="row"><span>P1 open</span><span class="v">{p1_needs}</span></div>'
        f'</div>'
    )


def floor_notes_block(ledger: dict, plant_id: str | None = None) -> str:
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


# ---------------------------------------------------------------------
# Per-plant sheet
# ---------------------------------------------------------------------

def entry_row(idx: int, item: dict, trailing_html: str) -> str:
    """Render one row of the entry table. `trailing_html` is the
    italicized resolution or status line under the summary."""
    priority = item.get("priority")
    priority_cell = (
        cap(priority, PRIORITY_CAP[priority])
        if priority in PRIORITY_CAP else '<span class="cap neutral">—</span>'
    )
    category = item.get("category")
    cat_cell = (
        f'{category_glyph(category)}{esc(category)}'
        if category else '<span style="color: var(--fg-3);">—</span>'
    )
    summary = item.get("summary")
    summary_html = (
        f'<span class="summary">{esc(summary)}</span>' if summary else ""
    )
    return (
        f'<tr>'
        f'<td class="pri-col pri-num">{idx}</td>'
        f'<td class="issue-cell">'
        f'<span class="title-line">{esc(item.get("title", ""))}</span>'
        f'{summary_html}'
        f'{trailing_html}'
        f'</td>'
        f'<td class="cat-cell">{cat_cell}</td>'
        f'<td class="pri-cell">{priority_cell}</td>'
        f'<td class="raised-cell">{fmt_first_raised(item)}</td>'
        f'</tr>'
    )


def entry_table(items: list[dict], kind: str) -> str:
    """kind is 'resolved' or 'needs_attention' — picks the trailing field."""
    if not items:
        empty = "Nothing to flag." if kind == "needs_attention" else "Nothing resolved in this window."
        return f'<p class="empty-state">{empty}</p>'

    ordered = _sort_priority(items)
    rows: list[str] = []
    for n_idx, it in enumerate(ordered, 1):
        if kind == "resolved":
            text = it.get("resolution") or ""
            trailing = f'<span class="resolution">{esc(text)}</span>' if text else ""
        else:
            text = it.get("status") or ""
            trailing = f'<span class="status">{esc(text)}</span>' if text else ""
        rows.append(entry_row(n_idx, it, trailing))

    return f"""
<table class="actions entry-table">
  <thead>
    <tr>
      <th class="pri-col">#</th>
      <th>Issue</th>
      <th>Category</th>
      <th class="pri-cell">Priority</th>
      <th>First raised</th>
    </tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def plant_sheet(plant: dict, ledger: dict, page_num: int, total: int,
                long_date: str) -> str:
    p = plant["id"]
    resolved = [i for i in ledger.get("resolved", []) if i.get("plant") == p]
    needs = [i for i in ledger.get("needs_attention", []) if i.get("plant") == p]
    p1_needs = sum(1 for i in needs if i.get("priority") == "P1")
    narrative = (ledger.get("per_plant_summary") or {}).get(p, "")
    narrative_html = (
        f'<p class="plant-narrative">{esc(narrative)}</p>'
        if narrative else
        '<p class="plant-narrative" style="color: var(--fg-3); font-style: italic;">'
        'No activity in the last 24 hours.</p>'
    )

    return f"""
<!-- ========== SHEET {page_num} — {esc(plant["name"])} ========== -->
<section class="sheet">
  <div class="plant-sheet-head">
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

  {narrative_html}

  <div class="stats">
    {stat_card("Resolved", str(len(resolved)), "Cleared in the last 24 hours")}
    {stat_card("Needs attention", str(len(needs)), "Raised, not yet cleared")}
    {stat_card("P1 open", str(p1_needs), "Urgent items still live")}
  </div>

  <h3 class="section-label">Needs attention</h3>
  {entry_table(needs, "needs_attention")}

  <h3 class="section-label">Resolved in the last 24 hours</h3>
  {entry_table(resolved, "resolved")}

  {floor_notes_block(ledger, p)}

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
    resolved = ledger.get("resolved", [])
    needs = ledger.get("needs_attention", [])
    p1_needs = sum(1 for i in needs if i.get("priority") == "P1")
    window = fmt_window(messages.get("window", {}))
    msg_count = messages.get("message_count", 0)
    chat_count = messages.get("chat_count", 0)
    long_date = fmt_date(date)

    cards = "".join(plant_card(p, ledger) for p in PLANTS)
    plant_sheets = "".join(
        plant_sheet(p, ledger, page_num=2 + idx, total=TOTAL_SHEETS,
                    long_date=long_date)
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
    <div class="item"><div class="eyebrow">Items today</div><div class="v">{len(resolved) + len(needs)}</div></div>
  </div>

  <h2>Executive summary</h2>

  <div class="hero">
    <div class="eyebrow">{esc(eyebrow_text)}</div>
    <p class="headline">{headline_html}</p>
  </div>

  <div class="stats">
    {stat_card("Resolved", str(len(resolved)), "Cleared in the last 24 hours")}
    {stat_card("Needs attention", str(len(needs)), "Raised, not yet cleared")}
    {stat_card("P1 open", str(p1_needs), "Urgent items still live")}
    {stat_card("Total raised", str(len(resolved) + len(needs)), "All items mentioned today")}
  </div>

  <h3 class="section-label">By plant</h3>
  <div class="audience-grid" style="grid-template-columns: 1fr 1fr 1fr;">
    {cards}
  </div>

  {floor_notes_block(ledger)}

  <p style="font-size: 7.5pt; color: var(--fg-3); margin-top: 14pt;">
    <a class="archive-link" href="../index.html">Archive of past briefings</a>
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
