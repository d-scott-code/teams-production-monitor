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

SYSTEM_PROMPT = """You are the issue reconciliation engine for CandyCo's daily production monitor.

CandyCo runs three plants in Lindon, Utah: L1 (Caramel), L2 (Eco Moulding), L3 (Chocolate). Each plant has Microsoft Teams chats whose topic contains "L1", "L2", or "L3". A daily job collects the last 24h of messages from those chats and tracks production issues as GitHub Issues labeled plant:L1, plant:L2, or plant:L3.

Your job: given today's messages and the currently-open issues, decide which issues to create, comment on, or close. Return a strict JSON plan via the submit_plan tool.

## Rules

**Create a new issue when** the messages raise a problem that isn't already tracked. Good signals: explicit problem statements, blocker questions, safety/quality flags, machine-down reports.

**Comment on an existing issue when** a thread discusses an already-open issue (add today's context, e.g. attempted fixes, partial progress, escalations).

**Close an existing issue when** someone says it's fixed, back online, cleared, resolved, etc. Capture the resolution language verbatim in the closing comment.

## Title quality bar

Short, concrete, scannable on a phone. "L2 hopper #3 jamming on 0.5in crumb" not "hopper problem". Leave the plant out of the title — it's carried by the label.

## Body template for new issues

```
**Plant:** L{1,2,3}
**First raised:** <timestamp> by <author>
**Source chat:** <topic>

<1-2 sentence summary of the problem>

---
Source messages:
> <quoted message>
— <author>, <time>
```

## Output

Call submit_plan with three lists. Use empty lists when nothing applies. Be conservative: when in doubt about whether a chat references an existing issue, comment rather than create. Don't invent activity that isn't in the messages."""

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the issue reconciliation plan for today's messages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "create": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "plant": {"type": "string", "enum": ["L1", "L2", "L3"]},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["plant", "title", "body"],
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
        "required": ["create", "comment", "close"],
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
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[PLAN_TOOL],
        tool_choice={"type": "tool", "name": "submit_plan"},
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
                       "plant": open_by_num[n]["plant"]})
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
        new = gh("POST", f"/repos/{REPO}/issues", json={
            "title": c["title"],
            "body": c["body"],
            "labels": [f"plant:{plant}"],
        })
        assert isinstance(new, dict)
        created.append({"number": new["number"], "title": c["title"], "plant": plant})
        print(f"  created #{new['number']}: {c['title']}")
    return closed, [], created


def build_ledger(today: str, closed: list, created: list,
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
        })
    for c in created:
        still_open.append({
            "number": c["number"], "title": c["title"],
            "plant": c["plant"], "age_days": 0,
        })
    plant_order = {"L1": 0, "L2": 1, "L3": 2}
    still_open.sort(key=lambda x: (plant_order.get(x["plant"], 9), -x["age_days"]))
    return {
        "date": today,
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

    for k in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET",
              "GRAPH_USER_UPN", "ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
        env(k)

    messages_path = ROOT / "data" / f"messages-{today}.json"
    ledger_path = ROOT / "data" / f"ledger-{today}.json"
    report_path = ROOT / "reports" / f"{today}.html"
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
    ledger = build_ledger(today, closed, created, open_issues, created_nums, closed_nums)
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
