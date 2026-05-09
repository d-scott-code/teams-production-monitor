# CandyCo Design System

> **Industrial confectionary, dressed sharp.**
> A design system for CandyCo — a full-scale confectionary manufacturing partner that private-labels for America's biggest retailers (Costco, Sam's Club, Trader Joe's, Kroger, Walmart, Albertsons).

This is a **B2B operations brand**, not a consumer candy brand. CandyCo's customers are merchandising teams, supply-chain planners, and retail buyers — people who care about throughput, lead times, and capacity utilization. The design language reflects that: a near-black "Shadow Grey" primary anchors the system, four bright "candy accent" colors (emerald, steel-blue, golden-yellow, racing-red) supply the personality, and the typographic hierarchy is engineered for dashboards and spec sheets, not storefronts.

---

## Sources Used

- **`uploads/design-tokens.css`** — provided color, type, spacing, and radius tokens. This is the canonical foundation; everything in `colors_and_type.css` is derived from it.
- **Brand description (provided in chat):** "CandyCo. Full scale confectionary manufacturing partner to the largest Retail Stores in America. We private label products for Costco, Sam's Club, Trader Joes, Kroger, Walmart, Albertsons."
- _No codebase, Figma, or product screenshots were provided._ The UI kit is a faithful interpretation of the supplied tokens applied to the company's stated business — a B2B manufacturing partner site. Marked clearly so future iteration can replace assumptions with actuals.

---

## Index

```
README.md                  ← you are here
SKILL.md                   ← agent skill manifest (Claude Code compatible)
colors_and_type.css        ← canonical tokens + semantic CSS variables
assets/                    ← logos, marks, illustrations, imagery
preview/                   ← cards rendered in the Design System tab
report-template/           ← default 8.5×11 paged layout for HTML reports
ui_kits/
  marketing-site/          ← B2B marketing site recreation (homepage + capabilities)
fonts/                     ← (Google-Fonts hosted; no local TTFs)
```

---

## CONTENT FUNDAMENTALS

**Voice — confident, plainspoken, slightly industrial.** CandyCo is the partner behind the brands you already buy. Copy should sound like an experienced ops lead, not a candy mascot.

**Casing.** Sentence case for headings and buttons. Title Case is reserved for proper nouns (product lines, retailer names) and for legal/spec callouts. ALL-CAPS is used **only** for eyebrows and tag-style labels — small, tracked-out (`letter-spacing: 0.14em`).

**Person.** "We" for CandyCo, "you" for the customer (the retail buyer / merchandiser). Never "I". Never "the user".

**Tone examples**
- ✅ "Twelve plants. One partner. Every aisle." _(headline — confident, structural)_
- ✅ "Lead times locked. Capacity allocated for Q3." _(dashboard copy — declarative)_
- ✅ "Tell us your forecast — we'll spec the line." _(CTA — collaborative, not pleading)_
- ❌ "Sweeten your shelves with our magical confections!" _(too consumer, too cute)_
- ❌ "🍬 Yummy candy for everyone! 🍭" _(emoji, exclamation, vibes only)_

**Numbers.** Always concrete. "12 plants," "1.4B units/yr," "98.7% on-time." Never "lots of" or "many." Use thin space or comma separators consistently. Percentages get the `%` symbol attached (no space).

**Emoji.** Not used. CandyCo speaks to procurement teams; emoji read as unserious. Status communicated through semantic color and named tokens (success/warning/error) and short text labels ("On track," "At capacity").

**Punctuation.** Em-dashes for emphasis are welcome. Oxford comma always. No exclamation points outside of error states or genuine celebration (a successful audit, a contract win).

**Vibe.** Imagine a 1960s candy-line spec sheet redrawn for 2026 — precise, grounded, with just enough sweetness in the accent palette to remind you what business we're in.

---

## VISUAL FOUNDATIONS

**Color philosophy.** The system runs on a 10-step **Shadow Grey** scale (`#F2F2F4` → `#1A1C27`) for everything structural — text, surfaces, borders, dividers, primary buttons. Accent color is rationed: a single accent per screen, used to draw the eye to the one thing that matters (the active capacity bar, the urgent alert, the primary CTA). The "Four Candies" — emerald, steel-blue, golden-yellow, racing-red — also serve as the **utilization scale** (ramping → growing → approaching → full), which is the system's signature data-viz move.

**Typography.** Four families, three roles:
- **Yeseva One** (display) — high-contrast didone-flavored serif. Reserved for marketing display headlines, hero numbers, and section openers. The brand's most recognizable typographic move.
- **Frank Ruhl Libre** (editorial serif) — pull quotes, testimonials, long-form storytelling. Provides warmth and editorial weight where Yeseva would be too loud.
- **Assistant** (sans, 6 weights) — 90% of all UI text: body, navigation, forms, dashboards, tabular data. Activated with `font-variant-numeric: tabular-nums` for column alignment.
- **Minion Pro** (legacy serif) — held in reserve for legal, archival, and long-form documents only. Not used in product UI.

Hierarchy is established with **weight and size**, not color. Body copy is `--fg-1` (near-black); secondary text is `--fg-2`; never use accent colors as text color outside of inline status pills.

**Spacing.** Strict 4px base unit. Component-internal padding lives in the `xs/sm/md/lg` range; section-level rhythm uses `xl/2xl/3xl/4xl`. Avoid arbitrary pixel values.

**Backgrounds.** Mostly white (`--bg-1`) and pale grey (`--bg-2`). Hero sections occasionally invert to **`--primary` Shadow Grey** with white text for emphasis — this inversion is the brand's most recognizable layout move. **No gradients. No textures. No background imagery behind text.** When imagery is used (factory floors, candy production lines, finished retail-shelf shots), it is **full-bleed and uncropped**, sitting in its own band of the page rather than layered behind copy.

**Imagery direction.** Cool-leaning, daylight-color photography. Slight desaturation. Real factory floors and real production lines — never staged, never AI-rendered. Product shots are top-down on a neutral grey or deep Shadow Grey background to match the primary token. **No grain filters, no duotones, no hand-drawn illustration.**

**Animation.** Restrained. Default easing is `cubic-bezier(0.2, 0, 0, 1)` (standard) at `200ms`. Hover and press transitions only — no decorative motion, no scroll-tied parallax. The one allowed flourish is a **utilization bar fill** that animates from 0 to its target value on first paint, easing-out over 600ms.

**Hover states.** Buttons darken by one step (e.g. `--primary` → `--primary-dark`). Cards rise by one shadow level (`--shadow-sm` → `--shadow`). Links shift from `--steel-blue` to `--primary`. No scale transforms on hover.

**Press states.** Buttons shift to `--primary-dark` and shrink imperceptibly (`scale(0.98)`). Cards drop their elevation entirely (`--shadow-xs`).

**Borders.** 1px hairlines in `--border-subtle` for divisions inside cards, `--border-default` for card edges, `--border-strong` only when a control needs explicit definition (form inputs at rest). No 2px borders. No colored borders except for active/focus states.

**Shadows.** Six-step elevation system, all derived from a tinted Shadow Grey at low alpha — never pure black. Cards use `--shadow-sm` at rest; menus and dropdowns use `--shadow-lg`; modals use `--shadow-xl`. Inset shadows (`--shadow-inset`) only inside form inputs.

**Focus.** Universal `--shadow-focus` ring — `0 0 0 3px rgba(25, 130, 196, 0.25)` — the steel-blue accent at 25% alpha. Visible on every interactive element, no exceptions.

**Capsules vs. protection gradients.** Status and category labels are **capsules** (pill-shaped, `--radius-pill`) with a tinted background (`--success-bg`, `--warning-bg`, etc.) and the matching strong color as text. Protection gradients (dark→transparent overlays on imagery) are not part of this system — text always lives outside imagery, never on top of it.

**Layout rules.** 12-column grid at `1280px` content width. Header is fixed (sticky) at the top, 64px tall. No sidebars on marketing pages; sidebars appear in the (forthcoming) operator dashboard product. Footer is full-width on `--primary`.

**Transparency & blur.** Used in exactly one place: the sticky header has a `rgba(255,255,255,0.85)` background with `backdrop-filter: blur(12px)` once the user scrolls past 8px. Otherwise opacity is binary — fully visible or hidden.

**Corner radii.** Default `--radius` (10px) for buttons and cards. Inputs use `--radius-sm` (6px). Modals and feature panels use `--radius-xl` (20px). Capsules use `--radius-pill`. **Never zero radius** except on data-table cells.

**Cards.** White background, `--border-subtle` 1px hairline, `--radius` corners, `--shadow-sm` at rest, `--shadow` on hover. Internal padding `--spacing-lg` (24px). No left-border accent stripes — a tropey pattern we explicitly avoid.

---

## ICONOGRAPHY

**System: Lucide Icons (CDN-linked).** No proprietary icon set was provided. We standardize on [Lucide](https://lucide.dev) — a 1.5px-stroke, rounded-corner, line-weight-consistent set that pairs cleanly with IBM Plex's geometric humanism. Loaded from CDN; see `assets/icons/README.md`.

**Stroke weight.** 1.5px default; 2px only for icons rendered ≤16px where 1.5 antialiases poorly.

**Icon size scale.** 16 / 20 / 24 / 32 / 48px. 20px is the default in-line size; 24px in primary navigation.

**Icon color.** Inherits from text color (`currentColor`). Never colored independently. Status icons (✓ success, ! warning) take their semantic color from the surrounding capsule, not from the icon itself.

**SVG vs. font.** SVG only. No icon fonts. Each icon is a single `<svg>` element inline.

**Emoji.** **Not used in product UI** — see Content Fundamentals. Permitted in internal Slack and external social copy, never in shipping interfaces.

**Unicode glyphs.** Permitted for typographic punctuation only (em-dash, en-dash, curly quotes, ×, →, ←, ↑, ↓). Not as decorative icons.

**Logo.** The CandyCo logo is a candy-wrapper mark above a custom wordmark. Three files live in `assets/logo/`:
- `candyco-logo-black.png` — primary, on light surfaces.
- `candyco-logo-white.png` — reverse, on `--primary` Shadow Grey.
- `candyco-mark.jpg` — the wordless wrapper mark for tight spaces and avatars.

**Substitution flag.** Lucide is a substitution. If CandyCo has a proprietary icon set, please share it and we'll swap.

---

## REPORTS & PAGED DOCUMENTS

**Every CandyCo HTML report defaults to the paged 8.5×11 layout in
`report-template/`.** Reports, briefings, analyses, recaps, dashboards
distributed as documents, and any long-form HTML belong in this format unless
the user explicitly asks for something else.

The format is non-negotiable on three points:

1. **Discrete sheets, not continuous flow.** Each section lives inside a
   `<section class="sheet">` that renders as an 8.5" × 11" white page on
   screen and prints as one page on Letter paper. The reader sees the page
   boundaries while drafting and gets a clean PDF on print.
2. **Logo lockup in every cover header.** The official `candyco-logo-black.png`
   sits at 38px height beside the document meta (eyebrow + date + scope).
   Never substitute with a text wordmark. Use the white logo on inverse
   Shadow Grey blocks.
3. **Page-numbered footers on every sheet.** `[Doc title] · Page N of M` in
   the bottom strip. Footer-derived page numbers are part of the trust signal —
   the reader knows the document is intentional, not a print accident.

To start a new report, copy `report-template/template.html` and follow the
instructions in `report-template/README.md`. The component library —
hero callout, stat strip, capsules, audience grid, action-assignment table,
chart card, footnote — is already wired up and uses only tokens from
`colors_and_type.css`.

**Skip the paged layout only when** the user says "raw," "single page,"
"one-pager," "no branding," "quick draft," "dashboard," "slide," or asks for
a non-paged format outright.

---

## CAVEATS & FONT SUBSTITUTIONS

- **Fonts:** Real brand fonts are loaded locally from `fonts/` — **Assistant** (sans), **Frank Ruhl Libre** (serif), **Yeseva One** (display), **Minion Pro** (legacy). The `--font-family` token in the original tokens file (system stack) has been superseded by `--font-sans` etc.
- **Imagery:** No photography assets were supplied. Marketing site uses CSS-only placeholder bands where photography would live in production.
- **Product surfaces:** Only a marketing-site UI kit is included. If CandyCo has an operator dashboard, retailer portal, or QC app, please share screenshots or codebase access.
