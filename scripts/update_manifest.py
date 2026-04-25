#!/usr/bin/env python3
"""Rebuild reports/manifest.json from the HTML files in reports/.

Run from the repo root after a new report has been written:

    python3 scripts/update_manifest.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MANIFEST = REPORTS_DIR / "manifest.json"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main() -> None:
    dates = sorted(
        p.stem for p in REPORTS_DIR.glob("*.html") if DATE_RE.match(p.stem)
    )
    MANIFEST.write_text(json.dumps({"reports": dates}, indent=2) + "\n")
    print(f"manifest: {len(dates)} reports")


if __name__ == "__main__":
    main()
