#!/usr/bin/env python3
"""Fetch the last 24h of Microsoft Teams messages from L1/L2/L3 plant chats.

Reads credentials from env vars (GRAPH_TENANT_ID, GRAPH_CLIENT_ID,
GRAPH_CLIENT_SECRET, GRAPH_USER_UPN) and writes a normalized JSON dump to the
path given by --out. Exits non-zero on any auth or fetch failure so the
daily routine can abort cleanly instead of publishing a silent-wrong report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from typing import Any, Iterable
from urllib.parse import quote

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
PLANT_RE = re.compile(r"\bL([123])\b", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
DENVER = dt.timezone(dt.timedelta(hours=-6))  # MDT; close enough for the window label


def env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        sys.exit(f"ERROR: environment variable {key} is not set")
    return val


def get_token() -> str:
    tenant = env("GRAPH_TENANT_ID")
    r = requests.post(
        TOKEN_URL_TMPL.format(tenant=tenant),
        data={
            "client_id": env("GRAPH_CLIENT_ID"),
            "client_secret": env("GRAPH_CLIENT_SECRET"),
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    if not r.ok:
        sys.exit(f"ERROR: token request failed ({r.status_code}): {r.text}")
    return r.json()["access_token"]


def graph_get(url: str, token: str, params: dict | None = None) -> dict:
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=60,
    )
    if r.status_code == 429:
        # Honor Retry-After and bail — scheduled runs can try again in an hour
        sys.exit(
            f"ERROR: Graph throttled (429). Retry-After={r.headers.get('Retry-After')}"
        )
    if not r.ok:
        sys.exit(f"ERROR: GET {url} -> {r.status_code}: {r.text[:400]}")
    return r.json()


def paged(url: str, token: str, params: dict | None = None) -> Iterable[dict]:
    next_url: str | None = url
    next_params = params
    while next_url:
        page = graph_get(next_url, token, next_params)
        for item in page.get("value", []):
            yield item
        next_url = page.get("@odata.nextLink")
        next_params = None  # nextLink already encodes params


def plant_of(topic: str | None) -> str | None:
    if not topic:
        return None
    m = PLANT_RE.search(topic)
    return f"L{m.group(1)}" if m else None


def strip_html(body: dict | None) -> str:
    if not body:
        return ""
    content = body.get("content", "") or ""
    if body.get("contentType") == "text":
        return content.strip()
    # Minimal HTML strip — Graph returns <p>, <br>, <div>, <at> mentions
    text = TAG_RE.sub("", content)
    return html.unescape(text).strip()


def list_user_chats(token: str, upn: str) -> list[dict]:
    user_id = quote(upn, safe="")
    url = f"{GRAPH}/users/{user_id}/chats"
    # $expand=lastMessagePreview is cheap and lets us skip dead chats
    return list(paged(url, token, params={"$expand": "lastMessagePreview"}))


def fetch_messages(
    token: str, upn: str, chat_id: str, since_utc: dt.datetime
) -> list[dict]:
    """Fetch messages for a chat, newest-first, stopping when older than since_utc."""
    user_id = quote(upn, safe="")
    cid = quote(chat_id, safe="")
    url = f"{GRAPH}/users/{user_id}/chats/{cid}/messages"
    collected: list[dict] = []
    for msg in paged(url, token, params={"$top": "50"}):
        sent = msg.get("createdDateTime")
        if not sent:
            continue
        sent_dt = dt.datetime.fromisoformat(sent.replace("Z", "+00:00"))
        if sent_dt < since_utc:
            # Graph returns messages newest-first; once we cross the boundary we're done
            break
        if msg.get("messageType") != "message":
            continue  # skip systemEventMessage, etc.
        sender = (msg.get("from") or {}).get("user") or {}
        collected.append(
            {
                "id": msg.get("id"),
                "from": sender.get("displayName") or "(system)",
                "from_upn": sender.get("userPrincipalName"),
                "sent_utc": sent,
                "text": strip_html(msg.get("body")),
                "importance": msg.get("importance"),
                "web_url": msg.get("webUrl"),
            }
        )
    # Return chronological order so Claude reads them top-down
    collected.reverse()
    return collected


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--hours", type=int, default=24, help="Window size (default 24)"
    )
    args = ap.parse_args()

    token = get_token()
    upn = env("GRAPH_USER_UPN")

    now_utc = dt.datetime.now(dt.timezone.utc)
    since_utc = now_utc - dt.timedelta(hours=args.hours)

    chats = list_user_chats(token, upn)
    matching = [
        c for c in chats if plant_of(c.get("topic")) is not None
    ]

    out_chats = []
    for c in matching:
        plant = plant_of(c.get("topic"))
        messages = fetch_messages(token, upn, c["id"], since_utc)
        if not messages:
            continue  # skip quiet chats from the window
        out_chats.append(
            {
                "id": c["id"],
                "topic": c.get("topic"),
                "plant": plant,
                "web_url": c.get("webUrl"),
                "messages": messages,
            }
        )

    payload = {
        "window": {
            "start_utc": since_utc.isoformat(),
            "end_utc": now_utc.isoformat(),
            "tz": "America/Denver",
            "hours": args.hours,
        },
        "chat_count": len(out_chats),
        "message_count": sum(len(c["messages"]) for c in out_chats),
        "chats": out_chats,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(
        f"wrote {args.out}: {payload['chat_count']} chats, "
        f"{payload['message_count']} messages"
    )


if __name__ == "__main__":
    main()
