#!/usr/bin/env python3
"""Daily Teams Production Monitor — pure-Python orchestrator.

Replaces the previous claude-code-action agent flow. Runs the existing
fetch / render / manifest scripts and makes ONE direct call to the
Anthropic API for the issue-reconciliation step.

Required env vars:
  GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_USER_UPN
  ANTHROPIC_API_KEY
  GITHUB_TOKEN  (auto-provided by GitHub Actions; needs repo write + issues)
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
import requests

REPO = "d-scott-code/teams-production-monitor"
GH_API = "https://api.github.com"
PLANT_LABELS = ["plant:L1", "plant:L2", "plant:L3"]
ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """You are the daily production-briefing engine for CandyCo.

CandyCo runs three plants in Lindon, Utah: L1 (Caramel), L2 (Eco Moulding), L3 (Chocolate). Each plant has Microsoft Teams chats whose topic contains "L1", "L2", or "L3". A daily job collects the last 24h of messages from those chats and tracks production issues as GitHub Issues labeled plant:L1, plant:L2, or plant:L3.

Your job has two halves:
  1. **Reconcile** — decide which issues to create, comment on, or close based on today's messages and the current open-issues snapshot.
  2. **Narrate** — pick the day's headline and write a 1–2 sentence summary per plant that the daily report will display verbatim.

Return both via the submit_plan tool.

## Reasoning approach

You have extended thinking enabled. Use it. Before writing the plan, work through the messages systematically: for each plant, scan every message, group related threads, identify problems and resolutions, and match against the open-issue snapshot. Only commit to the plan once you've reconciled every signal you noticed.

## Reconciliation rules

**Create a new issue when** the messages raise a problem that isn't already tracked. Good signals: explicit problem statements, blocker questions, safety/quality flags, machine-down reports.

**Comment on an existing issue when** a thread discusses an already-open issue (add today's context, e.g. attempted fixes, partial progress, escalations).

**Close an existing issue when** someone says it's fixed, back online, cleared, resolved, etc. Capture the resolution language verbatim in the closing comment.

**Same-window resolution** — if a problem is *both* raised and resolved within today's messages (a chat reports a line down at 14:00, then says "line is running" at 14:20), include `resolved_in_window` on the create item with the resolution comment quoted verbatim. The orchestrator will create the issue and immediately close it so the lifecycle is captured for the archive.

Resolution signals: "fixed", "running", "back online", "back up", "resolved", "cleared", "good now", "working properly". Be conservative: "running for now" or "running again" without a root-cause fix is partial — leave it open. When in doubt, leave it open.

## Title quality bar

Short, concrete, scannable on a phone. "L2 hopper #3 jamming on 0.5in crumb" not "hopper problem". Leave the plant out of the title — it's carried by the label.

## Body template for new issues

```
**Plant:** L{1,2,3}
**Priority:** P{1,2,3}
**Category:** <one of: Machine, Quality, Safety, Materials, Staffing, Other>
**First raised:** <timestamp> by <author>
**Source chat:** <topic>

<1-2 sentence summary of the problem>

---
Source messages:
> <quoted message>
— <author>, <time>
```

## Priority rubric (P1 / P2 / P3)

Set `priority` on every create item.

- **P1** — Line down, safety incident or near-miss, customer-impacting quality miss, or anything that needs an answer *inside the current shift*. If the floor is bleeding throughput or someone could get hurt, it's P1.
- **P2** — Elevated. Recurring or escalating issue, partial workaround in place, FSQA flag without an immediate hold, or a problem that will eat capacity if it isn't fixed in the next day or two.
- **P3** — Routine or informational. Maintenance notes, "FYI" mentions, minor quality variances, non-blocking questions, supplier scheduling.

When unsure between P1 and P2, prefer P2. When unsure between P2 and P3, prefer P3. Save P1 for the genuinely urgent.

## Category rubric

Set `category` on every create item — exactly one of:

- **Machine** — Equipment problems. Examples: "hopper jam," "conveyor stopped," "enrober down," "moulder skipping," "cooling tunnel temp out."
- **Quality** — Spec misses, FSQA flags, scrap spikes, holds. Examples: "out of spec," "weight check failing," "FSQA hold on lot," "color off."
- **Safety** — Near-miss, injury, lockout/tagout, PPE flag, ergonomics. Examples: "operator slipped," "guard removed," "lock-out issue."
- **Materials** — Inbound supply, off-spec ingredients, packaging shortages, vendor problems. Examples: "out of corrugate," "supplier shipped wrong SKU," "ingredient short."
- **Staffing** — Headcount, callouts, OT, training. Examples: "two callouts on B-shift," "no certified operator," "OT over plan."
- **Other** — Genuine catch-all. Use sparingly; if you reach for Other twice, reconsider whether one of the above fits.

## Headline

The daily report has a single hero callout. Pick what *one thing* belongs there based on today's activity.

`headline.eyebrow` is a short 2-3 word label categorizing what kind of day it was:
  - "Line down" — there's an active P1 machine outage
  - "Safety flag" — there's an active safety item
  - "Long-running issue" — something has been open for many days and matters most today
  - "Net closure" — meaningful resolutions, net favorable vs. opens
  - "New volume" — a notable burst of new issues
  - "Quiet 24 hours" — nothing notable happened
  - Or invent your own when none of those fit.

`headline.text` is one sentence that reads cleanly on a phone. Lead with the gap. Include the one concrete number that matters most. The renderer will wrap any token surrounded by *asterisks* in an accent color, so write `*3 days open*` to emphasize "3 days open." Use this sparingly — one accent per headline.

Good: "L2 enrober has been down *3 hours* — Maintenance is on-site, no ETA yet."
Bad: "Several issues today across the plants, some resolved, some not." (vague, no number, no accent)

## Per-plant summaries

`per_plant_summary.L1`, `.L2`, `.L3` — 1 or 2 sentences each describing what *actually happened* at that plant in the window. The renderer prints these verbatim as the intro to each plant's section.

If a plant had no activity, write something like "No activity in the last 24 hours." — short and honest. Don't invent narrative.

Good: "L1 ran caramel cluster all shift with no breaks. Hopper #3 needed a quick clear at 14:20 but came back inside ten minutes."
Bad: "L1 had a busy day with lots going on across multiple lines." (vague, no facts)

## Voice rules (CandyCo design system)

These apply to `headline.text`, `per_plant_summary.*`, all issue bodies, and resolution comments.

- Sentence case. Title case only for proper nouns (line names, vendor names).
- Concrete numbers. Never "lots of" or "several" — always the count. Times in 24-hour HH:MM, durations as "3 hours" or "20 minutes," ages as "3 days open."
- "We" for CandyCo, "you" for the reader. Never "I." Never "the user."
- No emoji. Status is conveyed via priority and category.
- No exclamation points.
- Lead with the gap. State the problem and the number before the explanation.

## Time zone — critical

CandyCo's plants are in Lindon, Utah (America/Denver). Every Teams message in the input carries two timestamps:

- `sent_utc` — UTC, machine-readable
- `sent_mt` — the same moment in Mountain Time, what the floor crew actually saw on their phones

**All human-facing times in your output must be Mountain Time** — the headline, per-plant summaries, summaries, resolution comments, and any time mentioned in the issue body. Read `sent_mt` to determine when something happened. Do not try to convert `sent_utc` yourself; DST math is error-prone and `sent_mt` is pre-computed for you.

Format as 24-hour `HH:MM` in narrative text. The renderer adds the "MT" label where the surrounding context doesn't already imply Mountain Time, so do not append "MT" yourself in narrative prose.

For `first_raised.time_utc` on create items: copy the source message's `sent_utc` verbatim (this field is machine-readable; the renderer converts to Mountain Time for display).

## Per-issue summary and attribution

On every `create` item, set:

- `summary` — one sentence in plain English describing the problem (not the title). This is what someone needs to know to act, not just a label. Goes under the title in the printed priorities table; the issue title is the headline, the summary is the read. Examples:
  - Good: "Drive belt slipping under load — tensioning didn't hold, maintenance is on-site and waiting on the replacement belt."
  - Bad: "Belt failure on the enrober." (just restates the title)
- `first_raised.author` — the Teams display name of the person who first mentioned the problem in the window. Use the `from` field on the source message exactly as it appears.
- `first_raised.time_utc` — the `sent_utc` timestamp of that same first message, copied verbatim (ISO-8601 with `Z` or `+00:00` — whichever Teams returned).

Pick the *first* message that surfaces the problem, not the most recent. If the same person mentioned it twice, use the earlier one. Both fields are required on every create item.

## Watchlist (optional)

`watchlist` is an array of existing open issues that didn't have any messages today but you want to keep on the reader's radar — typically because they've been open a while or are blocking something. Each entry: `{ "issue_number": N, "reason": "one sentence why this matters" }`. Use sparingly; if you list more than 3, you're diluting.

## Floor notes (optional)

`notes` is an array of non-issue color from the floor that's worth reading but doesn't warrant a GitHub issue: vendor visits, capacity moves, schedule changes, supplier news. Each entry: `{ "plant": "L1|L2|L3", "text": "one sentence" }`. Optional; default to empty if nothing fits.

## Worked example 1 — modest day at L2

Messages (excerpt, times shown are Mountain Time — `sent_mt`):
```
[L2 Floor] 09:14 MT Mike R: line 2 down — hopper #3 jammed on a crumb cluster
[L2 Floor] 09:31 MT Mike R: cleared, running again
[L2 Floor] 11:02 MT Sarah K: anyone seen the second pallet of foil wrap? supposed to be here yesterday
[L2 Floor] 13:45 MT Mike R: foil arrived, back on schedule
[L2 Floor] 15:10 MT Sarah K: FSQA flagged 4 pouches for weight on the 14:00 check, isolated and reworked
```

Plan fragment:
```json
{
  "headline": {
    "eyebrow": "Same-day recovery",
    "text": "L2 cleared a hopper jam in *17 minutes* and rebalanced after a late foil delivery — no carry-over."
  },
  "per_plant_summary": {
    "L2": "L2 had a 17-minute hopper jam at 09:14 that cleared cleanly. Foil supply ran late but arrived at 13:45 and the line stayed on schedule. FSQA caught 4 underweight pouches at the 14:00 check; isolated and reworked."
  },
  "create": [
    {
      "plant": "L2", "title": "L2 hopper #3 jam on crumb cluster",
      "priority": "P3", "category": "Machine",
      "summary": "Crumb cluster jammed hopper #3; cleared by hand in 17 minutes with no rework needed.",
      "first_raised": {"author": "Mike R", "time_utc": "2026-05-11T15:14:00Z"},
      "body": "...",
      "resolved_in_window": {"resolution_comment": "Cleared at 09:31 — \"cleared, running again\""}
    },
    {
      "plant": "L2", "title": "L2 foil wrap pallet arrived a day late",
      "priority": "P3", "category": "Materials",
      "summary": "Second pallet of foil wrap was a day late from the supplier; line stayed on schedule once it landed at 13:45.",
      "first_raised": {"author": "Sarah K", "time_utc": "2026-05-11T17:02:00Z"},
      "body": "...",
      "resolved_in_window": {"resolution_comment": "Foil arrived at 13:45 — \"back on schedule\""}
    },
    {
      "plant": "L2", "title": "L2 underweight pouches caught at 14:00 weight check (4 ct)",
      "priority": "P2", "category": "Quality",
      "summary": "Four pouches flagged underweight at the 14:00 FSQA check, isolated and reworked; need to review checkweigher calibration on the next shift.",
      "first_raised": {"author": "Sarah K", "time_utc": "2026-05-11T21:10:00Z"},
      "body": "..."
    }
  ]
}
```

## Worked example 2 — active P1 at L3

Messages (excerpt, times are Mountain Time):
```
[L3 Floor] 06:42 MT Tom W: enrober down, drive belt slipping
[L3 Floor] 07:05 MT Tom W: tried tensioning, no luck, calling maintenance
[L3 Floor] 08:20 MT Tom W: maintenance on-site, ordering belt
[L3 Floor] 13:11 MT Tom W: still waiting on belt, line idle 6+ hours now
```

Plan fragment:
```json
{
  "headline": {
    "eyebrow": "Line down",
    "text": "L3 enrober has been down *over 6 hours* on a belt failure — maintenance on-site, waiting on parts."
  },
  "per_plant_summary": {
    "L3": "L3 enrober drive belt failed at 06:42. Tensioning didn't hold. Maintenance is on-site since 08:20 and waiting on the replacement belt; line idle for the rest of the window."
  },
  "create": [
    {
      "plant": "L3", "title": "L3 enrober drive belt failure — line down",
      "priority": "P1", "category": "Machine",
      "summary": "Drive belt slipping under load — tensioning didn't hold, maintenance is on-site since 08:20 and waiting on the replacement belt.",
      "first_raised": {"author": "Tom W", "time_utc": "2026-05-11T12:42:00Z"},
      "body": "..."
    }
  ]
}
```

## Output

Call submit_plan with every required field populated. Use empty arrays for optional fields (`watchlist`, `notes`) when nothing applies. Be conservative: when in doubt about whether a chat references an existing issue, comment rather than create. Don't invent activity that isn't in the messages — short summaries are fine if the day was quiet."""

CATEGORIES = ["Machine", "Quality", "Safety", "Materials", "Staffing", "Other"]
PRIORITIES = ["P1", "P2", "P3"]

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the daily briefing plan: reconciliation actions + narrative for the report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "object",
                "description": "The single most important thing about today, rendered in the report's hero callout.",
                "properties": {
                    "eyebrow": {
                        "type": "string",
                        "description": "Short 2-3 word label, e.g. 'Line down', 'Quiet 24 hours', 'Long-running issue'.",
                    },
                    "text": {
                        "type": "string",
                        "description": "One sentence. Lead with the gap, include the one number that matters. Wrap a single accent token in *asterisks*.",
                    },
                },
                "required": ["eyebrow", "text"],
            },
            "per_plant_summary": {
                "type": "object",
                "description": "1-2 sentences per plant of what actually happened. Printed verbatim above each plant's issue lists.",
                "properties": {
                    "L1": {"type": "string"},
                    "L2": {"type": "string"},
                    "L3": {"type": "string"},
                },
                "required": ["L1", "L2", "L3"],
            },
            "watchlist": {
                "type": "array",
                "description": "Existing open issues with no activity today that still deserve attention. Use sparingly (<= 3).",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue_number": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["issue_number", "reason"],
                },
            },
            "notes": {
                "type": "array",
                "description": "Non-issue floor color (vendor visits, capacity moves, schedule changes). Optional.",
                "items": {
                    "type": "object",
                    "properties": {
                        "plant": {"type": "string", "enum": ["L1", "L2", "L3"]},
                        "text": {"type": "string"},
                    },
                    "required": ["plant", "text"],
                },
            },
            "create": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "plant": {"type": "string", "enum": ["L1", "L2", "L3"]},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "priority": {
                            "type": "string",
                            "enum": PRIORITIES,
                            "description": "P1 = urgent (line down, safety, customer-impacting); P2 = elevated; P3 = routine.",
                        },
                        "category": {
                            "type": "string",
                            "enum": CATEGORIES,
                            "description": "Exactly one of Machine, Quality, Safety, Materials, Staffing, Other.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "One sentence in plain English. What someone needs to know to act, not a restatement of the title. Printed under the title in the priorities table.",
                        },
                        "first_raised": {
                            "type": "object",
                            "description": "Author + timestamp of the Teams message that first surfaced the problem in today's window. Used for printed attribution.",
                            "properties": {
                                "author": {
                                    "type": "string",
                                    "description": "Display name from the source message's `from` field.",
                                },
                                "time_utc": {
                                    "type": "string",
                                    "description": "ISO-8601 timestamp from the source message's `sent_utc` field, verbatim.",
                                },
                            },
                            "required": ["author", "time_utc"],
                        },
                        "resolved_in_window": {
                            "type": "object",
                            "description": "Set ONLY when the issue was both raised AND resolved within today's messages. The orchestrator will create the issue and immediately close it.",
                            "properties": {
                                "resolution_comment": {"type": "string"},
                            },
                            "required": ["resolution_comment"],
                        },
                    },
                    "required": ["plant", "title", "body", "priority", "category", "summary", "first_raised"],
                },
            },
            "comment": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue_number": {"type": "integer"},
                        "body": {"type": "string"},
                    },
                    "required": ["issue_number", "body"],
                },
            },
            "close": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "issue_number": {"type": "integer"},
                        "resolution_comment": {"type": "string"},
                    },
                    "required": ["issue_number", "resolution_comment"],
                },
            },
        },
        "required": ["headline", "per_plant_summary", "create", "comment", "close"],
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


def gh(method: str, path: str, **kwargs) -> dict | list:
    token = env("GITHUB_TOKEN")
    r = requests.request(
        method,
        f"{GH_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
        **kwargs,
    )
    if not r.ok:
        sys.exit(f"ERROR: GitHub {method} {path} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.text else {}


def list_open_issues() -> list[dict]:
    """Fetch every open issue with any plant:L* label. Returns the trimmed
    snapshot we send to the LLM (number, title, body, plant, created_at)."""
    out: list[dict] = []
    seen: set[int] = set()
    for label in PLANT_LABELS:
        page = 1
        while True:
            items = gh(
                "GET",
                f"/repos/{REPO}/issues",
                params={
                    "state": "open",
                    "labels": label,
                    "per_page": 100,
                    "page": page,
                },
            )
            assert isinstance(items, list)
            if not items:
                break
            for it in items:
                if "pull_request" in it or it["number"] in seen:
                    continue
                seen.add(it["number"])
                plant = next(
                    (l["name"].split(":")[1] for l in it.get("labels", [])
                     if l["name"].startswith("plant:")),
                    None,
                )
                out.append({
                    "number": it["number"],
                    "title": it["title"],
                    "body": (it.get("body") or "")[:2000],
                    "plant": plant,
                    "created_at": it["created_at"],
                })
            if len(items) < 100:
                break
            page += 1
    return out


def call_claude_for_plan(messages: dict, open_issues: list[dict]) -> dict:
    """One-shot Anthropic call. Returns {create, comment, close}."""
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    user_payload = (
        f"TODAY: {messages['window'].get('end_utc', '')}\n\n"
        f"OPEN ISSUES (snapshot):\n```json\n{json.dumps(open_issues, indent=2)}\n```\n\n"
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


def apply_plan(plan: dict, open_issues: list[dict]) -> tuple[list, list, list]:
    open_by_num = {i["number"]: i for i in open_issues}
    closed: list[dict] = []
    for c in plan.get("close", []):
        n = c["issue_number"]
        if n not in open_by_num:
            print(f"  skip close #{n} (not in open snapshot)")
            continue
        gh("POST", f"/repos/{REPO}/issues/{n}/comments",
           json={"body": c["resolution_comment"]})
        gh("PATCH", f"/repos/{REPO}/issues/{n}", json={"state": "closed"})
        closed.append({"number": n, "title": open_by_num[n]["title"],
                       "plant": open_by_num[n]["plant"],
                       "priority": None, "category": None,
                       "summary": None, "first_raised": None,
                       "resolution_comment": c["resolution_comment"]})
        print(f"  closed #{n}")

    for c in plan.get("comment", []):
        n = c["issue_number"]
        if n not in open_by_num:
            print(f"  skip comment #{n} (not in open snapshot)")
            continue
        gh("POST", f"/repos/{REPO}/issues/{n}/comments", json={"body": c["body"]})
        print(f"  commented #{n}")

    created: list[dict] = []
    for c in plan.get("create", []):
        plant = c["plant"]
        if plant not in {"L1", "L2", "L3"}:
            print(f"  skip create (bad plant: {plant})")
            continue
        priority = c.get("priority") if c.get("priority") in PRIORITIES else None
        category = c.get("category") if c.get("category") in CATEGORIES else None
        summary = c.get("summary") or None
        first_raised = c.get("first_raised") if isinstance(c.get("first_raised"), dict) else None
        new = gh("POST", f"/repos/{REPO}/issues", json={
            "title": c["title"],
            "body": c["body"],
            "labels": [f"plant:{plant}"],
        })
        assert isinstance(new, dict)
        n = new["number"]
        created.append({
            "number": n, "title": c["title"], "plant": plant,
            "priority": priority, "category": category,
            "summary": summary, "first_raised": first_raised,
        })
        print(f"  created #{n} [{priority or '–'}/{category or '–'}]: {c['title']}")

        resolved = c.get("resolved_in_window")
        if resolved and resolved.get("resolution_comment"):
            gh("POST", f"/repos/{REPO}/issues/{n}/comments",
               json={"body": resolved["resolution_comment"]})
            gh("PATCH", f"/repos/{REPO}/issues/{n}", json={"state": "closed"})
            closed.append({
                "number": n, "title": c["title"], "plant": plant,
                "priority": priority, "category": category,
                "summary": summary, "first_raised": first_raised,
                "resolution_comment": resolved["resolution_comment"],
            })
            print(f"  closed #{n} (resolved in same window)")
    return closed, [], created


def build_ledger(today: str, plan: dict, closed: list, created: list,
                 open_issues: list[dict], created_nums: set[int],
                 closed_nums: set[int]) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    still_open: list[dict] = []
    for i in open_issues:
        if i["number"] in closed_nums:
            continue
        age = (now - dt.datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))).days
        still_open.append({
            "number": i["number"], "title": i["title"],
            "plant": i["plant"], "age_days": age,
            "priority": None, "category": None,
        })
    for c in created:
        if c["number"] in closed_nums:
            continue
        still_open.append({
            "number": c["number"], "title": c["title"],
            "plant": c["plant"], "age_days": 0,
            "priority": c.get("priority"), "category": c.get("category"),
            "summary": c.get("summary"), "first_raised": c.get("first_raised"),
        })
    plant_order = {"L1": 0, "L2": 1, "L3": 2}
    priority_rank = {"P1": 0, "P2": 1, "P3": 2, None: 3}
    still_open.sort(key=lambda x: (
        plant_order.get(x["plant"], 9),
        priority_rank.get(x.get("priority"), 3),
        -x["age_days"],
    ))
    return {
        "date": today,
        "headline": plan.get("headline") or {},
        "per_plant_summary": plan.get("per_plant_summary") or {},
        "watchlist": plan.get("watchlist") or [],
        "notes": plan.get("notes") or [],
        "closed_today": closed,
        "opened_today": created,
        "still_open": still_open,
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

    # Idempotency guard for the backup cron slot. The workflow runs twice
    # in a row (primary + backup ~20 minutes later) so a slipped primary
    # gets a second chance; on days where the primary lands, the backup
    # is a no-op. Manual `workflow_dispatch` runs always proceed —
    # rerunning by hand should always produce a fresh report.
    if (
        os.environ.get("GITHUB_EVENT_NAME") == "schedule"
        and report_path.exists()
    ):
        print(f"already published {report_path.name} — backup slot skipping")
        return

    for k in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET",
              "GRAPH_USER_UPN", "ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
        env(k)

    messages_path = ROOT / "data" / f"messages-{today}.json"
    ledger_path = ROOT / "data" / f"ledger-{today}.json"
    messages_path.parent.mkdir(parents=True, exist_ok=True)

    print("\n--- 1. Fetch Teams messages ---")
    run("python3", str(ROOT / "scripts" / "fetch_teams_messages.py"),
        "--out", str(messages_path))
    messages = json.loads(messages_path.read_text())

    print("\n--- 2. Load open plant:L* issues ---")
    open_issues = list_open_issues()
    print(f"open issues: {len(open_issues)}")

    print("\n--- 3. Reconcile messages → plan (Claude) ---")
    plan = call_claude_for_plan(messages, open_issues)
    print(f"plan: create={len(plan.get('create', []))} "
          f"comment={len(plan.get('comment', []))} "
          f"close={len(plan.get('close', []))}")

    print("\n--- 4. Apply plan to GitHub ---")
    closed, _, created = apply_plan(plan, open_issues)
    closed_nums = {c["number"] for c in closed}
    created_nums = {c["number"] for c in created}

    print("\n--- 5. Build & write ledger ---")
    ledger = build_ledger(today, plan, closed, created, open_issues, created_nums, closed_nums)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    print(f"wrote {ledger_path}")

    print("\n--- 6. Render HTML report ---")
    run("python3", str(ROOT / "scripts" / "render_report.py"),
        "--messages", str(messages_path),
        "--ledger", str(ledger_path),
        "--out", str(report_path))

    print("\n--- 7. Refresh manifest ---")
    run("python3", str(ROOT / "scripts" / "update_manifest.py"))

    print("\n--- 8. Commit and push ---")
    configure_git()
    pushed = commit_and_push(today)

    print("\n=== Summary ===")
    counts_per_plant = {}
    for p in ("L1", "L2", "L3"):
        c = sum(1 for x in closed if x["plant"] == p)
        n = sum(1 for x in created if x["plant"] == p)
        o = sum(1 for x in ledger["still_open"] if x["plant"] == p)
        counts_per_plant[p] = (c, n, o)
    line = ". ".join(
        f"{p}: {c} closed, {n} new, {o} open"
        for p, (c, n, o) in counts_per_plant.items()
    )
    print(line + ".")
    if ledger["still_open"]:
        oldest = ledger["still_open"][0]
        print(f"Oldest open: #{oldest['number']} ({oldest['plant']}) "
              f"{oldest['title']} — {oldest['age_days']}d")
    if pushed:
        print(f"Report: https://d-scott-code.github.io/teams-production-monitor/"
              f"reports/{today}.html")


if __name__ == "__main__":
    main()
