#!/bin/bash
set -euo pipefail

# Install Python deps the teams-production-monitor skill needs.
# Only `requests` is required; Python stdlib covers the rest.
python3 -m pip install --quiet --disable-pip-version-check requests
