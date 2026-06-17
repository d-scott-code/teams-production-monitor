#!/usr/bin/env python3
"""Render the daily FSQA briefing HTML report.

Window-only design (mirrors the production briefing) but lensed for the
FSQA Manager: holds, food safety, quality, sanitation, allergen, plus a
short list of process-level "consider..." opportunities.

Single sheet (or two if content overflows). Uses the same CandyCo Design
System tokens as the production briefing so both reports feel like one
publication.
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

PLANTS = ["L1", "L2", "L3"]

# Canonical plant names per CandyCo design system (L2 "Eco" is retired).
PLANT_LABEL = {
    "L1": "L1 Caramel",
    "L2": "L2 Moulding",
    "L3": "L3 Chocolate",
}

SEVERITY_CAP = {"high": "error", "medium": "warning", "low": "neutral"}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2, None: 3}

# Section ID → (display title, lucide icon name, short description for empty state)
SECTIONS = [
    ("holds",       "Active holds",        "package",        "No holds today. Saleable product flowing clean."),
    ("food_safety", "Food safety",         "shield-alert",   "No food-safety events flagged."),
    ("quality",     "Quality flags",       "shield-check",   "No quality flags today."),
    ("sanitation",  "Sanitation",          "spray-can",      "No sanitation gaps flagged."),
    ("allergen",    "Allergen",            "triangle-alert", "No allergen events."),
]

ACCENT_RE = re.compile(r"\*([^*]+)\*")


PAGE_LOCAL_CSS = """
/* All cards are neutral — meaning lives in the data, not the chrome.
   No top/left accent stripes per the CandyCo design system. */

/* ---------- FSQA cover band (logo lockup at 42px) ---------- */
.fsqa-head {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16pt;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 10pt; margin-bottom: 12pt;
}
.fsqa-head h1 {
  font-family: var(--font-display);
  font-size: 22pt;
  line-height: 1.05;
  letter-spacing: -0.01em;
  margin: 0;
  color: var(--fg-1);
}
.fsqa-head .sub {
  font-size: 8pt; color: var(--fg-3);
  letter-spacing: 0.08em;
  margin: 4pt 0 0 0;
  text-transform: uppercase;
}
.fsqa-head .meta {
  text-align: right;
  font-size: 8.5pt; color: var(--fg-2);
  line-height: 1.4;
}
.fsqa-head .meta img {
  height: 42px; width: auto; display: block;
  margin: -2px 0 4pt auto;
}

/* ---------- Summary block ---------- */
.fsqa-summary {
  font-family: var(--font-serif);
  font-size: 11pt;
  line-height: 1.5;
  color: var(--fg-1);
  margin: 0 0 14pt 0;
  text-wrap: pretty;
}

/* ---------- Stats strip ---------- */
.fsqa-stats {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8pt;
  margin: 0 0 14pt 0;
}
.fsqa-stats .stat {
  background: var(--bg-1);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 8pt 10pt;
  text-align: left;
}
.fsqa-stats .stat .eyebrow {
  font-size: 7pt; color: var(--fg-3);
  letter-spacing: 0.08em; text-transform: uppercase;
}
.fsqa-stats .stat .num {
  font-family: var(--font-display);
  font-size: 18pt; line-height: 1;
  color: var(--fg-1);
  font-variant-numeric: tabular-nums;
  margin-top: 2pt;
}

/* ---------- Section blocks ---------- */
.fsqa-section {
  margin: 16pt 0 12pt 0;
  page-break-inside: avoid;
}
.fsqa-section .sec-head {
  display: flex; align-items: center; gap: 6pt;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 4pt; margin-bottom: 6pt;
}
.fsqa-section .sec-head h3 {
  font-size: 10.5pt; font-weight: 700;
  margin: 0; color: var(--fg-1);
}
.fsqa-section .sec-head .sec-icon {
  width: 14px; height: 14px; color: var(--fg-2);
}
.fsqa-section .sec-head .sec-count {
  margin-left: auto;
  font-size: 8pt; color: var(--fg-3);
  font-variant-numeric: tabular-nums;
}

/* ---------- Entry rows ---------- */
.fsqa-entry {
  display: grid;
  grid-template-columns: 26pt 1fr auto;
  gap: 8pt;
  align-items: start;
  padding: 6pt 0;
  border-bottom: 1px solid var(--border-subtle);
}
.fsqa-entry:last-child { border-bottom: 0; }
.fsqa-entry .sev-col { text-align: center; padding-top: 1pt; }
.fsqa-entry .body { min-width: 0; }
.fsqa-entry .title-line {
  font-weight: 600; color: var(--fg-1);
  font-size: 9.5pt; line-height: 1.3;
}
.fsqa-entry .plant-tag {
  display: inline-block;
  font-size: 7pt; font-weight: 700;
  color: var(--fg-2);
  background: var(--shadow-grey-50);
  border-radius: var(--radius-sm);
  padding: 1pt 6pt;
  margin-right: 6pt;
  vertical-align: 1pt;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.fsqa-entry .summary {
  display: block; font-size: 8.5pt; color: var(--fg-2);
  margin-top: 2pt; line-height: 1.35;
  text-wrap: pretty;
}
.fsqa-entry .status {
  display: block;
  font-family: var(--font-serif); font-style: italic;
  font-size: 8pt; color: var(--fg-2);
  margin-top: 3pt; line-height: 1.4;
  text-wrap: pretty;
}
.fsqa-entry .status::before {
  content: "→ "; font-style: normal; color: var(--fg-3);
}
.fsqa-entry .raised {
  font-size: 7.5pt; color: var(--fg-3);
  text-align: right; white-space: nowrap;
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
}
.fsqa-entry .raised .author { color: var(--fg-2); font-weight: 600; display: block; }

/* ---------- Empty state ---------- */
.fsqa-section .empty {
  padding: 6pt 0 4pt 0;
  font-style: italic; font-size: 9pt;
  color: var(--fg-3);
}

/* ---------- Opportunities (per-plant boxes — neutral cards) ---------- */
.opportunities-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10pt;
  margin: 18pt 0 12pt 0;
  page-break-inside: avoid;
}
.opp-box {
  background: var(--bg-1);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  padding: 9pt 11pt 10pt 11pt;
}
.opp-box .eyebrow {
  font-size: 7pt; color: var(--fg-3);
  letter-spacing: 0.08em; text-transform: uppercase;
  margin-bottom: 4pt;
}
.opp-box h4 {
  font-size: 9.5pt; font-weight: 700;
  margin: 0 0 5pt 0; color: var(--fg-1);
}
.opp-box ul { margin: 0; padding-left: 12pt; }
.opp-box li {
  font-size: 8.5pt; line-height: 1.4;
  color: var(--fg-1);
  padding: 2pt 0;
  text-wrap: pretty;
}
.opp-box .empty {
  font-style: italic; font-size: 8.5pt;
  color: var(--fg-3); margin: 0;
}
.opportunities-eyebrow {
  font-size: 8pt; color: var(--fg-3);
  letter-spacing: 0.08em; text-transform: uppercase;
  margin: 18pt 0 2pt 0;
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


def fmt_raised(item: dict) -> str:
    fr = item.get("first_raised") or {}
    author = fr.get("author")
    time_utc = fr.get("time_utc")
    t = _to_mt(time_utc) if time_utc else None
    if author and t:
        return (
            f'<span class="author">{esc(author)}</span>'
            f'<span>{t.strftime("%H:%M MT")}</span>'
        )
    if author:
        return f'<span class="author">{esc(author)}</span>'
    if t:
        return f'<span>{t.strftime("%H:%M MT")}</span>'
    return '<span>—</span>'


def plant_tag(plant: str) -> str:
    return f'<span class="plant-tag">{esc(plant)}</span>'


def severity_cell(severity: str | None) -> str:
    if severity in SEVERITY_CAP:
        label = {"high": "HIGH", "medium": "MED", "low": "LOW"}[severity]
        return cap(label, SEVERITY_CAP[severity])
    return cap("—", "neutral")


# ---------------------------------------------------------------------
# Section rendering
# ---------------------------------------------------------------------

def section_block(section_id: str, title: str, icon: str, empty_msg: str,
                  items: list[dict]) -> str:
    if not items:
        body = f'<p class="empty">{esc(empty_msg)}</p>'
    else:
        rows: list[str] = []
        for it in items:
            summary = it.get("summary")
            summary_html = (
                f'<span class="summary">{esc(summary)}</span>' if summary else ""
            )
            status = it.get("status")
            status_html = (
                f'<span class="status">{esc(status)}</span>' if status else ""
            )
            rows.append(
                f'<div class="fsqa-entry">'
                f'<div class="sev-col">{severity_cell(it.get("severity"))}</div>'
                f'<div class="body">'
                f'<div class="title-line">{plant_tag(it.get("plant", "—"))}'
                f'{esc(it.get("title", ""))}</div>'
                f'{summary_html}{status_html}'
                f'</div>'
                f'<div class="raised">{fmt_raised(it)}</div>'
                f'</div>'
            )
        body = "".join(rows)

    return (
        '<section class="fsqa-section">'
        '<div class="sec-head">'
        f'<i class="sec-icon" data-lucide="{esc(icon)}"></i>'
        f'<h3>{esc(title)}</h3>'
        f'<span class="sec-count">{len(items)}</span>'
        '</div>'
        f'{body}'
        '</section>'
    )


def opportunities_row(items: list[dict]) -> str:
    """Render three per-plant opportunity boxes (one per plant). Each
    plant has its own Quality Manager, so opportunities are scoped to
    the plant where the originating event occurred. Empty boxes show a
    short "Nothing flagged" note rather than collapsing — the layout
    stays consistent so the Quality Manager always sees their box."""
    by_plant: dict[str, list[dict]] = {p: [] for p in PLANTS}
    for it in items:
        p = it.get("plant")
        if p in by_plant and it.get("text"):
            by_plant[p].append(it)

    if not any(by_plant.values()):
        return ""

    def box(plant: str) -> str:
        opps = by_plant[plant]
        if opps:
            lis = "".join(f'<li>{esc(o.get("text", ""))}</li>' for o in opps)
            body = f'<ul>{lis}</ul>'
        else:
            body = '<p class="empty">No opportunities flagged today.</p>'
        return (
            f'<div class="opp-box">'
            f'<div class="eyebrow">{esc(plant)}</div>'
            f'<h4>{esc(PLANT_LABEL[plant])}</h4>'
            f'{body}'
            f'</div>'
        )

    return (
        '<div class="opportunities-eyebrow">Opportunities — by plant</div>'
        '<div class="opportunities-row">'
        + "".join(box(p) for p in PLANTS) +
        '</div>'
    )


# ---------------------------------------------------------------------
# Headline
# ---------------------------------------------------------------------

def headline(ledger: dict) -> tuple[str, str]:
    h = ledger.get("headline") or {}
    if h.get("eyebrow") and h.get("text"):
        return (h["eyebrow"], render_accents(h["text"]))
    total = sum(
        len(ledger.get(s, []))
        for s in ["holds", "food_safety", "quality", "sanitation", "allergen"]
    )
    if total == 0:
        return ("Quiet 24 hours", "No FSQA events flagged across L1, L2, or L3.")
    return ("Today", f'<strong>{total}</strong> FSQA items across L1, L2, L3.')


# ---------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------

def render(ledger: dict, messages: dict, date: str) -> str:
    eyebrow_text, headline_html = headline(ledger)
    summary_text = ledger.get("summary") or ""
    long_date = fmt_date(date)
    window = fmt_window(messages.get("window", {}))

    high_count = 0
    for s in ["holds", "food_safety", "quality", "sanitation", "allergen"]:
        high_count += sum(1 for i in ledger.get(s, []) if i.get("severity") == "high")

    stats_html = "".join(
        f'<div class="stat"><div class="eyebrow">{label}</div>'
        f'<div class="num">{len(ledger.get(key, []))}</div></div>'
        for key, label in [
            ("holds", "Holds"),
            ("food_safety", "Food safety"),
            ("quality", "Quality"),
            ("sanitation", "Sanitation"),
            ("allergen", "Allergen"),
        ]
    ) + (
        f'<div class="stat"><div class="eyebrow">High severity</div>'
        f'<div class="num">{high_count}</div></div>'
    )

    sections_html = "".join(
        section_block(sid, title, icon, empty, ledger.get(sid, []))
        for sid, title, icon, empty in SECTIONS
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FSQA briefing — {esc(date)} · CandyCo</title>
<link rel="stylesheet" href="{DS}/colors_and_type.css">
<link rel="stylesheet" href="{DS}/report-template/report.css">
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<style>{PAGE_LOCAL_CSS}</style>
</head>
<body>
<div class="doc-frame">

<section class="sheet">
  <div class="fsqa-head">
    <div>
      <h1>FSQA briefing</h1>
      <div class="sub">Food safety · Quality · Sanitation · Allergen</div>
    </div>
    <div class="meta">
      <img src="{DS}/assets/logo/candyco-logo-black.png" alt="CandyCo">
      <div>{esc(long_date)}</div>
      <div>08:00 America/Denver</div>
    </div>
  </div>

  <div class="meta-strip">
    <div class="item"><div class="eyebrow">Window</div><div class="v">{esc(window) or "—"}</div></div>
    <div class="item"><div class="eyebrow">Plants in scope</div><div class="v">L1 · L2 · L3</div></div>
    <div class="item"><div class="eyebrow">Audience</div><div class="v">FSQA Manager</div></div>
  </div>

  <div class="hero">
    <div class="eyebrow">{esc(eyebrow_text)}</div>
    <p class="headline">{headline_html}</p>
  </div>

  {f'<p class="fsqa-summary">{esc(summary_text)}</p>' if summary_text else ''}

  <div class="fsqa-stats">{stats_html}</div>

  {sections_html}

  {opportunities_row(ledger.get("opportunities") or [])}

  <p style="font-size: 7.5pt; color: var(--fg-3); margin-top: 18pt;">
    Production briefing for the same day:
    <a class="archive-link" href="{esc(date)}.html">reports/{esc(date)}.html</a> ·
    <a class="archive-link" href="../index.html">Archive of past briefings</a>
  </p>

  <div class="sheet-footer">
    <span class="doc">FSQA briefing · {esc(date)}</span>
    <span class="page-no">Page 1 of 1</span>
  </div>
</section>

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
