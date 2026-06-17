#!/usr/bin/env python3
"""Daily Teams Production Monitor — pure-Python orchestrator.

Window-only design: each report is a function of the last 24 hours of Teams
messages and nothing else. We do not carry open issues forward across days,
and we do not mutate GitHub Issues. Reports are the artifact; reading them
in sequence shows trends.

The same Teams data is run through two independent Claude calls to produce
two briefings for different audiences:

  - production briefing → reports/<date>.html for plant leadership
  - FSQA briefing       → reports/fsqa-<date>.html for the FSQA Manager

Required env vars:
  GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_USER_UPN
  ANTHROPIC_API_KEY
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-4-5-20250929"

PLANTS = ["L1", "L2", "L3"]
CATEGORIES = ["Machine", "Quality", "Safety", "Materials", "Staffing", "Other"]
PRIORITIES = ["P1", "P2", "P3"]
SEVERITIES = ["high", "medium", "low"]

# ---------------------------------------------------------------------
# Production briefing — system prompt + tool schema
# ---------------------------------------------------------------------

PRODUCTION_SYSTEM_PROMPT = """You are the daily production-briefing engine for CandyCo.

CandyCo runs three plants in Lindon, Utah: L1 (Caramel), L2 (Eco Moulding), L3 (Chocolate). Each plant has Microsoft Teams chats whose topic contains "L1", "L2", or "L3". A daily job collects the last 24h of messages from those chats and you turn them into the day's briefing.

The briefing is a fresh-slate, window-only view. You only look at the messages in this window. There is no list of issues from yesterday, no carry-over, no trend tracking. If a problem from earlier in the week is still live, the floor will mention it again in this window and you'll pick it up. If they don't mention it, it's not in today's report — and that's fine.

## What you produce

For each plant, classify every distinct production problem mentioned in the window as either:

- **resolved** — raised AND cleared inside this 24h window. The chat shows both the problem and the fix.
- **needs_attention** — raised inside this 24h window, NOT cleared by the end of the window. The chat shows the problem with no clear resolution.

You also write a headline, a 1-2 sentence summary per plant, and optionally floor notes.

## Reasoning approach

You have extended thinking enabled. Use it. Before writing the plan, work through the messages systematically: for each plant, scan every message, group related threads, identify problems and their resolutions (or lack thereof). Only commit to the plan once you've classified every signal you noticed.

## Classification rules

**Mark as resolved when:** the same problem thread contains a clear resolution signal — "fixed", "running", "back online", "back up", "resolved", "cleared", "good now", "working properly".

**Leave in needs_attention when:** the thread is in progress, partial ("running for now"), or stops mid-fix. When in doubt, leave it in needs_attention. The floor would rather see it flagged and decide it's fine than miss something live.

**Don't speculate.** If a problem is mentioned once and never revisited, classify based on what the message itself says. If it says "we fixed it" → resolved. If it just describes a problem without a follow-up → needs_attention.

**One thread = one entry.** A single problem discussed across multiple messages is one entry, not many. The `first_raised` field captures the first message; the resolution or status captures the last meaningful update.

## Title quality bar

Short, concrete, scannable on a phone. "L2 hopper #3 jamming on 0.5in crumb" not "hopper problem". Leave the plant out of the title — it's carried by the field.

## Priority rubric (P1 / P2 / P3)

Set `priority` on every entry. This reflects how the problem felt at the moment it was raised, not how it ended up.

- **P1** — Line down, safety incident or near-miss, customer-impacting quality miss, or anything that needed an answer inside the current shift. If the floor was bleeding throughput or someone could have been hurt, it's P1.
- **P2** — Elevated. Recurring or escalating, partial workaround, FSQA flag without an immediate hold, or something that would eat capacity if it wasn't fixed quickly.
- **P3** — Routine or informational. Maintenance notes, "FYI" mentions, minor quality variances, non-blocking questions, supplier scheduling.

When unsure between P1 and P2, prefer P2. When unsure between P2 and P3, prefer P3. Save P1 for the genuinely urgent.

## Category rubric

Set `category` on every entry — exactly one of:

- **Machine** — Equipment problems. "hopper jam," "conveyor stopped," "enrober down," "moulder skipping," "cooling tunnel temp out."
- **Quality** — Spec misses, FSQA flags, scrap spikes, holds. "out of spec," "weight check failing," "FSQA hold on lot," "color off."
- **Safety** — Near-miss, injury, lockout/tagout, PPE flag, ergonomics. "operator slipped," "guard removed," "lock-out issue."
- **Materials** — Inbound supply, off-spec ingredients, packaging shortages, vendor problems. "out of corrugate," "supplier shipped wrong SKU," "ingredient short."
- **Staffing** — Headcount, callouts, OT, training. "two callouts on B-shift," "no certified operator," "OT over plan."
- **Other** — Genuine catch-all. Use sparingly.

## Per-entry fields

Every entry (resolved or needs_attention) requires:

- `plant` — "L1", "L2", or "L3"
- `title` — short headline, no plant prefix
- `summary` — one sentence describing what someone needs to know to act. Not a restatement of the title; the read under the headline.
- `priority`, `category` — per rubrics above
- `first_raised` — `{ "author": "<display name>", "time_utc": "<ISO 8601 from sent_utc>" }`. Author is the `from` field on the source message; time_utc is the `sent_utc` of the first message that surfaced the problem.

`resolved` entries also require:
- `resolution` — one sentence in plain English of what cleared it, including the quoted resolution language if available. Example: `Cleared at 09:31 — "running again" (Mike R)`.

`needs_attention` entries also require:
- `status` — one sentence on the last known state from the messages. Example: `Maintenance on-site since 08:20, waiting on belt as of 13:11.`

## Headline

The daily report has a single hero callout. Pick what *one thing* belongs there based on today's window.

`headline.eyebrow` — short 2-3 word label:
  - "Line down" — there was/is an active P1 machine outage
  - "Safety flag" — there's a safety item
  - "Net closure" — meaningful resolutions vs. unresolved
  - "New volume" — a notable burst of new issues
  - "Quiet 24 hours" — nothing notable happened
  - Or invent your own.

`headline.text` is one sentence that reads cleanly on a phone. Lead with the gap. Include the one concrete number that matters most. The renderer wraps any token surrounded by *asterisks* in an accent color, so write `*3 hours down*` to emphasize "3 hours down." Use this sparingly — one accent per headline.

Good: "L2 enrober was down *3 hours* on a belt failure — cleared by 11:30."
Bad: "Several issues today across the plants, some resolved, some not."

## Per-plant summaries

`per_plant_summary.L1`, `.L2`, `.L3` — 1 or 2 sentences each describing what *actually happened* at that plant in the window. The renderer prints these verbatim above each plant's lists.

If a plant had no activity, write: "No activity in the last 24 hours." — short and honest.

Good: "L1 ran caramel cluster all shift with no breaks. Hopper #3 needed a quick clear at 14:20 but came back inside ten minutes."
Bad: "L1 had a busy day with lots going on across multiple lines."

## Floor notes (optional)

`notes` is an array of non-issue color from the floor that's worth reading but doesn't warrant being its own entry: vendor visits, capacity moves, schedule changes, supplier news. Each entry: `{ "plant": "L1|L2|L3", "text": "one sentence" }`. Default to an empty array if nothing fits.

## Voice rules (CandyCo design system)

These apply to `headline.text`, `per_plant_summary.*`, all summaries, resolutions, and statuses.

- Sentence case. Title case only for proper nouns (line names, vendor names).
- Concrete numbers. Never "lots of" or "several" — always the count. Times in 24-hour HH:MM, durations as "3 hours" or "20 minutes."
- "We" for CandyCo, "you" for the reader. Never "I." Never "the user."
- No emoji.
- No exclamation points.
- Lead with the gap. State the problem and the number before the explanation.

## Time zone — critical

CandyCo's plants are in Lindon, Utah (America/Denver). Every Teams message carries two timestamps:

- `sent_utc` — UTC, machine-readable
- `sent_mt` — same moment in Mountain Time, what the floor saw on their phones

**All human-facing times in your output must be Mountain Time** — the headline, per-plant summaries, summaries, resolutions, statuses. Read `sent_mt` to determine when something happened. Format as 24-hour `HH:MM` in narrative prose. The renderer adds the "MT" label where context doesn't already imply Mountain Time, so don't append "MT" yourself in narrative prose.

For `first_raised.time_utc`: copy the source message's `sent_utc` verbatim. This field is machine-readable; the renderer converts to Mountain Time for display.

## Output

Call submit_plan with every required field populated. Use empty arrays for `notes` when nothing applies. Be conservative: when in doubt about whether something resolved, leave it in needs_attention. Don't invent activity that isn't in the messages — short summaries are fine if the day was quiet."""

PRODUCTION_ENTRY_SHARED = {
    "plant": {"type": "string", "enum": PLANTS},
    "title": {"type": "string"},
    "summary": {
        "type": "string",
        "description": "One sentence — what someone needs to know to act, not a restatement of the title.",
    },
    "priority": {"type": "string", "enum": PRIORITIES},
    "category": {"type": "string", "enum": CATEGORIES},
    "first_raised": {
        "type": "object",
        "properties": {
            "author": {"type": "string"},
            "time_utc": {"type": "string"},
        },
        "required": ["author", "time_utc"],
    },
}

PRODUCTION_TOOL = {
    "name": "submit_plan",
    "description": "Submit the daily production briefing: a window-only view of the last 24h, classified as resolved or needs_attention.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "object",
                "properties": {
                    "eyebrow": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["eyebrow", "text"],
            },
            "per_plant_summary": {
                "type": "object",
                "properties": {p: {"type": "string"} for p in PLANTS},
                "required": PLANTS,
            },
            "notes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "plant": {"type": "string", "enum": PLANTS},
                        "text": {"type": "string"},
                    },
                    "required": ["plant", "text"],
                },
            },
            "resolved": {
                "type": "array",
                "description": "Problems raised AND cleared inside this 24h window.",
                "items": {
                    "type": "object",
                    "properties": {
                        **PRODUCTION_ENTRY_SHARED,
                        "resolution": {
                            "type": "string",
                            "description": "One sentence describing what cleared it, including quoted resolution language if available.",
                        },
                    },
                    "required": [*PRODUCTION_ENTRY_SHARED.keys(), "resolution"],
                },
            },
            "needs_attention": {
                "type": "array",
                "description": "Problems raised inside this 24h window that did NOT clear by window close.",
                "items": {
                    "type": "object",
                    "properties": {
                        **PRODUCTION_ENTRY_SHARED,
                        "status": {
                            "type": "string",
                            "description": "One sentence on the last known state from the messages.",
                        },
                    },
                    "required": [*PRODUCTION_ENTRY_SHARED.keys(), "status"],
                },
            },
        },
        "required": ["headline", "per_plant_summary", "notes", "resolved", "needs_attention"],
    },
}


# ---------------------------------------------------------------------
# FSQA briefing — system prompt + tool schema
# ---------------------------------------------------------------------

FSQA_SYSTEM_PROMPT = """You are the daily FSQA briefing engine for CandyCo.

CandyCo runs three plants in Lindon, Utah (L1 Caramel, L2 Eco Moulding, L3 Chocolate). A daily job collects the last 24h of Teams chat messages from those plants. Your job is to extract the FSQA-relevant signal for one reader: the FSQA Manager who owns food safety, quality, sanitation, allergen control, and audit readiness across all three plants.

The reader of the production briefing already sees line-down events, staffing, scheduling, supply. You DO NOT repeat that here unless it creates a food-safety or quality risk. You DO report anything that could harm a consumer, fail an audit, or surface a process weakness.

The briefing is a fresh-slate, window-only view. You only look at this 24h window. No carry-over, no trend tracking across days. If something is still live, the floor will mention it again tomorrow and you'll see it.

## Reasoning approach

Extended thinking is enabled. Use it. Scan every message systematically. Sort each FSQA-relevant event into the right section. Then for opportunities, look across today's events for process-level patterns worth flagging.

## Sections

Sort every FSQA-relevant event into exactly ONE of these sections:

- **holds** — Any product, batch, lot, or pallet placed on hold or pending QA disposition today. Includes "isolated for rework," "pulled from line for review," "on hold pending FSQA," "X retained as sample for investigation." If product was held AND released within the window, still include it (mark status as resolved).
- **food_safety** — Direct hazards to the consumer or product integrity. Foreign material in product (metal, plastic, glass, wood, hair, fiber). Pest sightings. Contamination events (microbial, chemical). Damaged equipment in food-contact zones where pieces could enter product (broken blades, cracked guards, missing parts). Failures or anomalies of food-safety equipment itself (metal detector rejecting test cards, X-ray faults, checkweigher misbehavior).
- **quality** — Spec misses, weight/count failures, color/sensory deviations, scrap spikes, label errors, packaging quality. Things that didn't make it into food_safety but represent a quality concern.
- **sanitation** — ATP failures, missed or incomplete cleaning, sanitation tools used incorrectly (e.g., equipment sanitizer used on drains), allergen test failures during cleaning verification, hygiene flags.
- **allergen** — Cross-contact concerns, label/packaging allergen errors, allergen verification test results, allergen storage or handling issues. Note: allergen test failures during cleaning belong in sanitation; allergen on finished product belongs in food_safety.

**One event = one section.** If something could fit two, pick the one the FSQA Manager would most want to see it in (food_safety beats quality; sanitation beats allergen for cleaning context).

**Skip events that don't fit any section.** Line-down for mechanical reasons, staffing, supply, scheduling — these go in the production briefing, not this one. Don't pad sections.

## Per-entry fields

Every entry across all five sections requires:

- `plant` — "L1", "L2", or "L3"
- `title` — short headline, scannable on a phone, no plant prefix
- `summary` — one sentence: what the FSQA Manager needs to know to decide if action is needed
- `severity` — "high", "medium", or "low":
  - **high** — Direct food-safety risk, active formal hold on saleable product, audit-finding-class deviation, anything that could harm a consumer if missed
  - **medium** — Quality holds, FSQA flags without a formal hold, recurring failures suggesting systemic weakness, cleaning verification gaps
  - **low** — Informational, near-miss caught at QA, FYI for awareness
- `first_raised` — `{ "author": "<display name>", "time_utc": "<ISO 8601 from sent_utc verbatim>" }`
- `status` — one sentence on the CURRENT state at window close. Examples: "Open, awaiting maintenance investigation.", "On hold pending QA disposition.", "Resolved on shift — released back to line.", "Released after FM not found in second inspection."

## Headline

The briefing has a single hero callout. Pick the one thing the FSQA Manager needs to know first.

`headline.eyebrow` — short 2-3 word label like "Active hold," "FM event," "Allergen flag," "Sanitation gap," "Quiet 24 hours." Invent your own when none fit.

`headline.text` — one sentence, leads with the gap, includes the one number that matters. Wrap one accent token in *asterisks* — the renderer color-highlights it. One accent per headline, used sparingly.

Good: "L1 S2 jar held on *metal-in-product* — X-ray caught, metal detector did not. Investigation open."
Bad: "Several FSQA things happened today."

## Summary

`summary` — 1-2 sentences total. The FSQA Manager's executive read of the day. Printed below the headline.

Good: "Two active holds — metal-in-product on L1 S2 jar line, underweight pouches on L1 Twist Wrap. ML1 metal detector at L3 still rejecting all test cards after maintenance; root cause unknown."
Bad: "Various food-safety and quality issues occurred."

## Opportunities

`opportunities` — 0 to 3 process-level suggestions **per plant** surfaced by TODAY'S events. Each plant has its own Quality Manager, so opportunities are scoped to one plant. Attribute each opportunity to the plant where the originating event occurred.

Each entry: `{ "plant": "L1|L2|L3", "text": "one sentence ending with — based on Y" }`. Cite the specific event(s) it's drawn from in the sentence. Frame as "Consider X..." — these are the Quality Manager's call, not a directive.

If a single insight genuinely applies cross-plant (e.g., a checklist gap that exists on all three lines), write one entry per affected plant — each one citing that plant's specific event. Don't merge cross-plant opportunities into a single entry; the Quality Manager reading just their plant should see what applies to them.

If a plant's events don't suggest a process improvement today, just don't include an entry for that plant. Don't pad. A plant with zero opportunities is a clean read.

Good: `{ "plant": "L3", "text": "Consider adding cleaning-roller blade inspection to ML4 startup checklist — today's damaged blade and possible metal shavings echo two similar incidents earlier this month." }`
Good: `{ "plant": "L1", "text": "Review labeling on sanitation tools — the sprayer used on drains nearly went back into equipment service." }`
Bad: A single opportunity with `plant: "L1"` whose text refers to events at L2 or L3. The plant attribution must match the events cited.

## Voice rules

- Sentence case. Title case only for proper nouns.
- Concrete numbers. Never "lots of" or "several."
- "We" for CandyCo, "you" for the reader. Never "I."
- No emoji.
- No exclamation points.
- Lead with the gap.

## Time zone

Plants are in Mountain Time (America/Denver). Use `sent_mt` for human-facing times in your prose, format as 24-hour HH:MM. Use `sent_utc` verbatim for the `first_raised.time_utc` machine-readable field. The renderer converts UTC→MT for display.

## Empty sections

If a section has no events, return an empty array. Don't invent content. A quiet FSQA day is a good FSQA day — say so honestly in the summary.

## Output

Call submit_fsqa_briefing with every required field populated."""

FSQA_ENTRY_SHARED = {
    "plant": {"type": "string", "enum": PLANTS},
    "title": {"type": "string"},
    "summary": {
        "type": "string",
        "description": "One sentence — what the FSQA Manager needs to know to decide if action is needed.",
    },
    "severity": {
        "type": "string",
        "enum": SEVERITIES,
        "description": "high = direct food-safety risk or formal hold; medium = quality hold / recurring failure / audit-finding-class; low = informational / FYI.",
    },
    "first_raised": {
        "type": "object",
        "properties": {
            "author": {"type": "string"},
            "time_utc": {"type": "string"},
        },
        "required": ["author", "time_utc"],
    },
    "status": {
        "type": "string",
        "description": "One sentence on the current state at window close: open, on hold pending disposition, resolved, investigation ongoing, etc.",
    },
}

FSQA_SECTION_ITEM = {
    "type": "object",
    "properties": FSQA_ENTRY_SHARED,
    "required": list(FSQA_ENTRY_SHARED.keys()),
}

FSQA_TOOL = {
    "name": "submit_fsqa_briefing",
    "description": "Submit the daily FSQA briefing: a window-only view of the last 24h, sorted into food-safety / quality / sanitation / allergen / hold sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "object",
                "properties": {
                    "eyebrow": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["eyebrow", "text"],
            },
            "summary": {
                "type": "string",
                "description": "1-2 sentence FSQA Manager's read of the day. Printed below the headline.",
            },
            "holds": {"type": "array", "items": FSQA_SECTION_ITEM},
            "food_safety": {"type": "array", "items": FSQA_SECTION_ITEM},
            "quality": {"type": "array", "items": FSQA_SECTION_ITEM},
            "sanitation": {"type": "array", "items": FSQA_SECTION_ITEM},
            "allergen": {"type": "array", "items": FSQA_SECTION_ITEM},
            "opportunities": {
                "type": "array",
                "description": "0-3 process-level suggestions per plant surfaced by today's events. Each entry is attributed to ONE plant (the plant where the originating event occurred). Cross-plant insights should be written as one entry per affected plant.",
                "items": {
                    "type": "object",
                    "properties": {
                        "plant": {"type": "string", "enum": PLANTS},
                        "text": {
                            "type": "string",
                            "description": "One sentence ending with — based on Y, citing the specific event(s) at this plant that prompted the suggestion.",
                        },
                    },
                    "required": ["plant", "text"],
                },
            },
        },
        "required": [
            "headline", "summary",
            "holds", "food_safety", "quality", "sanitation", "allergen",
            "opportunities",
        ],
    },
}


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

def env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        sys.exit(f"ERROR: {key} is not set")
    return val


def today_in_denver() -> str:
    return dt.datetime.now(ZoneInfo("America/Denver")).strftime("%Y-%m-%d")


def run(*cmd: str) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def call_claude(client: anthropic.Anthropic, system_prompt: str, tool: dict,
                messages: dict, label: str) -> dict:
    """Generic single-turn Claude call with extended thinking + one tool.
    Returns the tool's input dict. Exits with a non-zero code if the model
    doesn't return the expected tool call."""
    user_payload = (
        f"TODAY: {messages['window'].get('end_utc', '')}\n\n"
        f"MESSAGES (last 24h):\n```json\n{json.dumps(messages, indent=2)}\n```"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        thinking={"type": "enabled", "budget_tokens": 5000},
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool],
        messages=[{"role": "user", "content": user_payload}],
    )
    print(
        f"  [{label}] claude usage: input={resp.usage.input_tokens} "
        f"output={resp.usage.output_tokens} "
        f"cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)} "
        f"cache_create={getattr(resp.usage, 'cache_creation_input_tokens', 0)}"
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input
    sys.exit(f"ERROR: Claude did not return a {tool['name']} tool call. Response: {resp.content}")


# ---------------------------------------------------------------------
# Ledger builders
# ---------------------------------------------------------------------

def build_production_ledger(today: str, plan: dict) -> dict:
    plant_order = {p: i for i, p in enumerate(PLANTS)}
    priority_rank = {"P1": 0, "P2": 1, "P3": 2}

    def sort_key(item: dict) -> tuple:
        return (
            plant_order.get(item.get("plant"), 9),
            priority_rank.get(item.get("priority"), 9),
            item.get("first_raised", {}).get("time_utc", ""),
        )

    return {
        "date": today,
        "headline": plan.get("headline") or {},
        "per_plant_summary": plan.get("per_plant_summary") or {},
        "notes": plan.get("notes") or [],
        "resolved": sorted(plan.get("resolved") or [], key=sort_key),
        "needs_attention": sorted(plan.get("needs_attention") or [], key=sort_key),
    }


def build_fsqa_ledger(today: str, plan: dict) -> dict:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    plant_order = {p: i for i, p in enumerate(PLANTS)}

    def sort_key(item: dict) -> tuple:
        return (
            severity_rank.get(item.get("severity"), 9),
            plant_order.get(item.get("plant"), 9),
            item.get("first_raised", {}).get("time_utc", ""),
        )

    sections = ["holds", "food_safety", "quality", "sanitation", "allergen"]
    opportunities = sorted(
        plan.get("opportunities") or [],
        key=lambda o: plant_order.get(o.get("plant"), 9),
    )
    return {
        "date": today,
        "headline": plan.get("headline") or {},
        "summary": plan.get("summary") or "",
        **{s: sorted(plan.get(s) or [], key=sort_key) for s in sections},
        "opportunities": opportunities,
    }


# ---------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------

def configure_git() -> None:
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com")


def commit_and_push(today: str) -> bool:
    run("git", "add", "reports", "data")
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode
    if diff == 0:
        print("nothing to commit")
        return False
    run("git", "commit", "-m", f"report: {today}")
    run("git", "push", "origin", "HEAD:main")
    return True


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    today = today_in_denver()
    print(f"=== Daily Teams Production Monitor — {today} ===")

    production_report = ROOT / "reports" / f"{today}.html"
    fsqa_report = ROOT / "reports" / f"fsqa-{today}.html"

    # Idempotency guard for the backup cron slot. Skip only when BOTH reports
    # already exist — if one is missing we want to retry to finish the job.
    if (
        os.environ.get("GITHUB_EVENT_NAME") == "schedule"
        and production_report.exists()
        and fsqa_report.exists()
    ):
        print(f"already published {production_report.name} and {fsqa_report.name} — backup slot skipping")
        return

    for k in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET",
              "GRAPH_USER_UPN", "ANTHROPIC_API_KEY"):
        env(k)

    messages_path = ROOT / "data" / f"messages-{today}.json"
    production_ledger_path = ROOT / "data" / f"ledger-{today}.json"
    fsqa_ledger_path = ROOT / "data" / f"fsqa-{today}.json"
    messages_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n--- 1. Fetch Teams messages ---")
    run("python3", str(ROOT / "scripts" / "fetch_teams_messages.py"),
        "--out", str(messages_path))
    messages = json.loads(messages_path.read_text())

    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))

    print("\n--- 2a. Classify messages → production briefing (Claude) ---")
    production_plan = call_claude(client, PRODUCTION_SYSTEM_PROMPT, PRODUCTION_TOOL,
                                  messages, label="production")
    print(f"  production: resolved={len(production_plan.get('resolved', []))} "
          f"needs_attention={len(production_plan.get('needs_attention', []))} "
          f"notes={len(production_plan.get('notes', []))}")

    print("\n--- 2b. Classify messages → FSQA briefing (Claude) ---")
    fsqa_plan = call_claude(client, FSQA_SYSTEM_PROMPT, FSQA_TOOL,
                            messages, label="fsqa")
    print(f"  fsqa: holds={len(fsqa_plan.get('holds', []))} "
          f"food_safety={len(fsqa_plan.get('food_safety', []))} "
          f"quality={len(fsqa_plan.get('quality', []))} "
          f"sanitation={len(fsqa_plan.get('sanitation', []))} "
          f"allergen={len(fsqa_plan.get('allergen', []))} "
          f"opportunities={len(fsqa_plan.get('opportunities', []))}")

    print("\n--- 3. Build & write ledgers ---")
    production_ledger = build_production_ledger(today, production_plan)
    production_ledger_path.write_text(json.dumps(production_ledger, indent=2) + "\n")
    print(f"wrote {production_ledger_path}")

    fsqa_ledger = build_fsqa_ledger(today, fsqa_plan)
    fsqa_ledger_path.write_text(json.dumps(fsqa_ledger, indent=2) + "\n")
    print(f"wrote {fsqa_ledger_path}")

    print("\n--- 4a. Render production briefing ---")
    run("python3", str(ROOT / "scripts" / "render_report.py"),
        "--messages", str(messages_path),
        "--ledger", str(production_ledger_path),
        "--out", str(production_report))

    print("\n--- 4b. Render FSQA briefing ---")
    run("python3", str(ROOT / "scripts" / "render_fsqa_report.py"),
        "--messages", str(messages_path),
        "--ledger", str(fsqa_ledger_path),
        "--out", str(fsqa_report))

    print("\n--- 5. Refresh manifest ---")
    run("python3", str(ROOT / "scripts" / "update_manifest.py"))

    print("\n--- 6. Commit and push ---")
    configure_git()
    pushed = commit_and_push(today)

    print("\n=== Summary ===")
    for p in PLANTS:
        r = sum(1 for x in production_ledger["resolved"] if x.get("plant") == p)
        n = sum(1 for x in production_ledger["needs_attention"] if x.get("plant") == p)
        print(f"  {p}: {r} resolved, {n} needs attention")
    fsqa_total = sum(len(fsqa_ledger[s]) for s in
                     ["holds", "food_safety", "quality", "sanitation", "allergen"])
    print(f"  FSQA: {fsqa_total} items, {len(fsqa_ledger['opportunities'])} opportunities")
    if pushed:
        base = "https://d-scott-code.github.io/teams-production-monitor/reports"
        print(f"Production:  {base}/{today}.html")
        print(f"FSQA:        {base}/fsqa-{today}.html")


if __name__ == "__main__":
    main()
