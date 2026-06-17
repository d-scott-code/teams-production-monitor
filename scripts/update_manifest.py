#!/usr/bin/env python3
"""Rebuild reports/manifest.json from the HTML files in reports/.

Run from the repo root after a new report has been written:

    python3 scripts/update_manifest.py

Manifest shape:

    {
      "production": ["YYYY-MM-DD", ...],   # newest last (sorted ASC; index.html reverses)
      "fsqa":       ["YYYY-MM-DD", ...]
    }
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MANIFEST = REPORTS_DIR / "manifest.json"

PRODUCTION_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})$")
FSQA_RE = re.compile(r"^fsqa-(\d{4}-\d{2}-\d{2})$")


def main() -> None:
    production: list[str] = []
    fsqa: list[str] = []
    for p in REPORTS_DIR.glob("*.html"):
        m = PRODUCTION_RE.match(p.stem)
        if m:
            production.append(m.group(1))
            continue
        m = FSQA_RE.match(p.stem)
        if m:
            fsqa.append(m.group(1))
    production.sort()
    fsqa.sort()
    MANIFEST.write_text(
        json.dumps({"production": production, "fsqa": fsqa}, indent=2) + "\n"
    )
    print(f"manifest: {len(production)} production, {len(fsqa)} fsqa")


if __name__ == "__main__":
    main()
