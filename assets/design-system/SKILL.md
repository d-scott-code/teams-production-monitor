---
name: candyco-design
description: CandyCo's design system — colors, typography, spacing, voice, components, and assets. This is the DEFAULT visual language for every artifact, widget, HTML page, slide deck, dashboard, document, mock, or any visual output created for Scott Maxfield (CandyCo CEO) unless the user explicitly says otherwise. Apply automatically whenever building any visual artifact, even if the user does not name the design system. Skip only when the user signals "raw," "no branding," "quick sketch," or similar.
user-invocable: true
---

# CandyCo Design System

**Persistent location:** `/Users/SM/Documents/CandyCo Design System/`

This skill is the always-on default for artifacts. When invoked (explicitly or by default), read `README.md` for content fundamentals and visual foundations, then use the tokens and assets below.

## Quick map

- `README.md` — content fundamentals (voice, tone, casing), visual foundations (color, type, spacing, motion, layout, iconography), caveats.
- `colors_and_type.css` — canonical CSS variables and `@font-face` declarations. Source of truth for tokens. Copy this file into artifacts or `@import` it directly when feasible.
- `fonts/` — Assistant (sans, UI), Frank Ruhl Libre (editorial serif), Yeseva One (display), Minion Pro (legacy).
- `assets/logo/` — `candyco-logo-black.png` (dark on light), `candyco-logo-white.png` (light on Shadow Grey), `candyco-mark.jpg` (wordless mark for tight spaces). **Place the logo in the cover header of every report — never substitute with a text wordmark.**
- `assets/icons/` — Lucide iconography reference. Lucide icons are CDN-linked, 1.5px stroke, `currentColor` only.
- `preview/` — specimen cards for every token group. Useful as cookbook examples.
- `report-template/` — **default layout for every HTML report.** Paged 8.5×11 sheets with logo header, page-numbered footers, ready-to-use components. Always start here for reports, briefings, analyses, and long-form documents.
- `ui_kits/marketing-site/` — JSX components and a working `index.html` showing the system in production layout.
- `board-deck/` — board deck reference materials and reusable deck-stage scaffolding.

## How to use this skill

1. If the user has asked for a visual artifact (HTML page, dashboard, slide, mock, doc), apply this design system by default.
2. Read `README.md` first for the content and visual rules.
3. **For HTML reports, briefings, or analyses, default to `report-template/`** — paged 8.5×11 sheets with the logo lockup, page-numbered footers, and the standard component library. Read `report-template/README.md` and copy `report-template/template.html` as the starting point. Skip only if the user signals "raw," "single page," "one-pager," "no branding," or asks for a non-paged format.
4. Pull tokens from `colors_and_type.css` rather than redefining colors, type, spacing, radii, or shadows ad hoc.
5. Use logos and fonts from this folder. **Place `candyco-logo-black.png` in the cover header of every report** (or `candyco-logo-white.png` on inverse Shadow Grey backgrounds). Copy the logo file into the artifact output folder so the relative path resolves when the file is shared or printed.
6. Apply the voice rules from `README.md` to all copy: sentence case, "we/you," concrete numbers, no emoji.
7. If the user invokes this skill without other guidance, ask what they want to build, ask the right clarifying questions, then deliver as either an HTML artifact or production code.

## When to skip

If the user says "raw output," "no styling," "quick sketch," "unbranded," or similar — skip the design system and produce something fast and unstyled.

## Report components — operations / finance pattern library

The `report-template/report.css` includes ready-to-use components for analytical / operational reports. Use them by class name; styles handle print color preservation automatically.

- **`.hero`** — light-cream callout for the executive headline. Print-safe (the legacy dark-bg version was getting stripped by browser print color economy and rendering white-on-white). Use `.hero.dark` only for digital-only artifacts.
- **`.sheet.landscape`** — wide-content sheet (14" wide on screen for comfortable browsing) that prints as Letter portrait with the content rotated 90° CCW so wide tables fit on portrait paper. **Required pattern**: wrap ALL inner content (h2, intro, meta-strip, table, goal-box, caption, footer) inside `<div class="print-rotated-region"><div class="print-rotated-inner">...</div></div>`. Set inline `style="--print-scale: 0.82;"` (or whatever scale fits) on the section to shrink all fonts/padding together based on row count. See `report-template/README.md` for the full pattern and the row-count → scale formula.
- **`.run-meta-strip`** — light-cream context band with metadata (e.g., produced units, revenue, period). Pairs above appendix tables.
- **`table.appendix-wide`** — dense numeric reporting table (15+ columns) matched to the cycle-count team's report format. Light-blue header band with grouped column heads. Use inside `.sheet.landscape`. Includes a `.totals` row class.
- **`.goal-box`** — bold-bordered KPI callout that frames a result against an operational target. Three cells: two context numbers + one headline % with color band. Color modifiers: `.goal-good` (green, beating target), `.goal-warn` (amber), `.goal-bad` (red).
- **Variance tinting** — apply `.pos` (green, favorable), `.neg` (amber, small unfavorable), or `.neg-strong` (red bold, large unfavorable) to `<td>` cells in comparison tables.

## Number formatting conventions for reports

Every operational/finance report should follow these conventions so the output reads consistently with what the cycle-count and finance teams produce:

- **Negative values** in parentheses: `(1,234)` not `-1,234`
- **Zero or no data** as em-dash: `—` (never `0`, `N/A`, or blank cells in numeric columns)
- **Currency** with $-prefix: positive `$1,234`, negative `$(1,234)`
- **Percentages** always signed on variance columns: `+0.1%`, `-12.4%`
- **Column alignment** uses tabular numerals: `font-variant-numeric: tabular-nums` (already on `.num`, `.stat .num`, `.goal-value`)
- **Lead with lbs (or units), follow with dollars** in operational reports — pounds is the operational metric; dollars is the financial expression of the same data

These conventions live in code (formatting helpers, not CSS), but are documented here and at the bottom of `report-template/report.css` so every future report uses the same helpers.

## How to extend

This is a living system. Edits live here:

- Tokens → `colors_and_type.css`
- Rules and voice → `README.md`
- Components → `ui_kits/`
- Specimens → `preview/`
- Report layout / paged-document defaults → `report-template/`
- Assets → `assets/`

Update directly. Changes apply to every future artifact automatically.
