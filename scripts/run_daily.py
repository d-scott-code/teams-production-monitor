#!/usr/bin/env python3
"""Daily Teams Production Monitor — pure-Python orchestrator.

Window-only design: each report is a function of the last 24 hours of Teams
messages and nothing else. We do not carry open issues forward across days,
and we do not mutate GitHub Issues. Reports are the artifact; reading them
in sequence shows trends.

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

SYSTEM_PROMPT = """You are the daily production-briefing engine for CandyCo.

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

## Worked example — modest day at L2

Messages (excerpt, times shown are Mountain Time):
```
[L2 Floor] 09:14 MT Mike R: line 2 down — hopper #3 jammed on a crumb cluster
[L2 Floor] 09:31 MT Mike R: cleared, running again
[L2 Floor] 11:02 MT Sarah K: anyone seen the second pallet of foil wrap? supposed to be here yesterday
[L2 Floor] 13:45 MT Mike R: foil arrived, back on schedule
[L2 Floor] 15:10 MT Sarah K: FSQA flagged 4 pouches for weight on the 14:00 check, isolated and reworked
[L2 Floor] 16:42 MT Mike R: ML2 PTL pump just seized again, maintenance pulling it now
```

Plan fragment:
```json
{
  "headline": {
    "eyebrow": "PTL pump down",
    "text": "L2 ML2 PTL pump *seized at 16:42* — maintenance pulling, no ETA yet."
  },
  "per_plant_summary": {
    "L2": "L2 cleared a hopper jam in 17 minutes at 09:14 and rebalanced after a late foil delivery at 13:45. FSQA caught 4 underweight pouches at 14:00, isolated and reworked. ML2 PTL pump seized at 16:42 and is still down at window close."
  },
  "resolved": [
    {
      "plant": "L2", "title": "Hopper #3 jam on crumb cluster",
      "priority": "P3", "category": "Machine",
      "summary": "Crumb cluster jammed hopper #3; cleared by hand.",
      "first_raised": {"author": "Mike R", "time_utc": "2026-05-11T15:14:00Z"},
      "resolution": "Cleared at 09:31 — \\"cleared, running again\\" (Mike R)."
    },
    {
      "plant": "L2", "title": "Foil wrap pallet arrived a day late",
      "priority": "P3", "category": "Materials",
      "summary": "Second pallet of foil wrap was a day late; line stayed on schedule once it landed.",
      "first_raised": {"author": "Sarah K", "time_utc": "2026-05-11T17:02:00Z"},
      "resolution": "Foil arrived at 13:45 — \\"back on schedule\\" (Mike R)."
    },
    {
      "plant": "L2", "title": "4 underweight pouches at 14:00 weight check",
      "priority": "P2", "category": "Quality",
      "summary": "Four pouches flagged underweight at the 14:00 FSQA check, isolated and reworked.",
      "first_raised": {"author": "Sarah K", "time_utc": "2026-05-11T21:10:00Z"},
      "resolution": "Isolated and reworked on-shift by 15:10 — \\"isolated and reworked\\" (Sarah K)."
    }
  ],
  "needs_attention": [
    {
      "plant": "L2", "title": "ML2 PTL pump seized",
      "priority": "P1", "category": "Machine",
      "summary": "PTL pump seized at 16:42, maintenance pulling it now.",
      "first_raised": {"author": "Mike R", "time_utc": "2026-05-11T22:42:00Z"},
      "status": "Maintenance pulling pump as of 16:42, no ETA."
    }
  ]
}
```

## Output

Call submit_plan with every required field populated. Use empty arrays for `notes` when nothing applies. Be conservative: when in doubt about whether something resolved, leave it in needs_attention. Don't invent activity that isn't in the messages — short summaries are fine if the day was quiet."""

CATEGORIES = ["Machine", "Quality", "Safety", "Materials", "Staffing", "Other"]
PRIORITIES = ["P1", "P2", "P3"]
PLANTS = ["L1", "L2", "L3"]

ENTRY_SHARED = {
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
            "time_utc": {
                "type": "string",
                "description": "ISO-8601 from the source message's sent_utc, verbatim.",
            },
        },
        "required": ["author", "time_utc"],
    },
}

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the daily briefing: a window-only view of the last 24h, classified as resolved or needs_attention.",
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
                        **ENTRY_SHARED,
                        "resolution": {
                            "type": "string",
                            "description": "One sentence describing what cleared it, including quoted resolution language if available.",
                        },
                    },
                    "required": [*ENTRY_SHARED.keys(), "resolution"],
                },
            },
            "needs_attention": {
                "type": "array",
                "description": "Problems raised inside this 24h window that did NOT clear by window close.",
                "items": {
                    "type": "object",
                    "properties": {
                        **ENTRY_SHARED,
                        "status": {
                            "type": "string",
                            "description": "One sentence on the last known state from the messages.",
                        },
                    },
                    "required": [*ENTRY_SHARED.keys(), "status"],
                },
            },
        },
        "required": ["headline", "per_plant_summary", "notes", "resolved", "needs_attention"],
    },
}


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


def call_claude_for_plan(messages: dict) -> dict:
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
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
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[PLAN_TOOL],
        messages=[{"role": "user", "content": user_payload}],
    )
    print(
        f"claude usage: input={resp.usage.input_tokens} "
        f"output={resp.usage.output_tokens} "
        f"cache_read={getattr(resp.usage, 'cache_read_input_tokens', 0)} "
        f"cache_create={getattr(resp.usage, 'cache_creation_input_tokens', 0)}"
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_plan":
            return block.input
    sys.exit(f"ERROR: Claude did not return a submit_plan tool call. Response: {resp.content}")


def build_ledger(today: str, plan: dict) -> dict:
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


def main() -> None:
    today = today_in_denver()
    print(f"=== Daily Teams Production Monitor — {today} ===")

    report_path = ROOT / "reports" / f"{today}.html"

    # Idempotency guard for the backup cron slot.
    if (
        os.environ.get("GITHUB_EVENT_NAME") == "schedule"
        and report_path.exists()
    ):
        print(f"already published {report_path.name} — backup slot skipping")
        return

    for k in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET",
              "GRAPH_USER_UPN", "ANTHROPIC_API_KEY"):
        env(k)

    messages_path = ROOT / "data" / f"messages-{today}.json"
    ledger_path = ROOT / "data" / f"ledger-{today}.json"
    messages_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n--- 1. Fetch Teams messages ---")
    run("python3", str(ROOT / "scripts" / "fetch_teams_messages.py"),
        "--out", str(messages_path))
    messages = json.loads(messages_path.read_text())

    print("\n--- 2. Classify messages → plan (Claude) ---")
    plan = call_claude_for_plan(messages)
    print(f"plan: resolved={len(plan.get('resolved', []))} "
          f"needs_attention={len(plan.get('needs_attention', []))} "
          f"notes={len(plan.get('notes', []))}")

    print("\n--- 3. Build & write ledger ---")
    ledger = build_ledger(today, plan)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    print(f"wrote {ledger_path}")

    print("\n--- 4. Render HTML report ---")
    run("python3", str(ROOT / "scripts" / "render_report.py"),
        "--messages", str(messages_path),
        "--ledger", str(ledger_path),
        "--out", str(report_path))

    print("\n--- 5. Refresh manifest ---")
    run("python3", str(ROOT / "scripts" / "update_manifest.py"))

    print("\n--- 6. Commit and push ---")
    configure_git()
    pushed = commit_and_push(today)

    print("\n=== Summary ===")
    for p in PLANTS:
        r = sum(1 for x in ledger["resolved"] if x.get("plant") == p)
        n = sum(1 for x in ledger["needs_attention"] if x.get("plant") == p)
        print(f"  {p}: {r} resolved, {n} needs attention")
    if pushed:
        print(f"Report: https://d-scott-code.github.io/teams-production-monitor/"
              f"reports/{today}.html")


if __name__ == "__main__":
    main()
