"""Interactively create local secrets without printing or passing them in arguments."""

import getpass
import json
import os
import sys
from pathlib import Path

if not sys.stdin.isatty():
    raise SystemExit("Run this setup in an interactive terminal.")

root = Path(__file__).resolve().parents[1]
folder = root / ".local"
folder.mkdir(mode=0o700, exist_ok=True)
path = folder / "bakalari.json"
if path.exists():
    raise SystemExit("Configuration already exists; edit it locally instead of overwriting it.")
username = getpass.getpass("Bakalari username (hidden): ")
password = getpass.getpass("Bakalari password (hidden): ")
dashboard_password = getpass.getpass("New Homeboard password (at least 12 characters): ")
confirmation = getpass.getpass("Repeat Homeboard password: ")
if (
    not username
    or not password
    or len(dashboard_password) < 12
    or dashboard_password != confirmation
):
    raise SystemExit("Invalid or mismatched credentials. No file written.")
with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
    json.dump(
        {
            "base_url": "https://zsplana.bakalari.cz",
            "username": username,
            "password": password,
            "dashboard_password": dashboard_password,
        },
        output,
    )
print("Saved local configuration. Enable SCHOOL_SOURCE=bakalari and restart Homeboard.")
print("Dashboard login: homeboard, with your new Homeboard password.")
