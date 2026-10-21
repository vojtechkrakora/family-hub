"""Save private Google iCal addresses locally without printing them."""

import getpass
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

if not sys.stdin.isatty():
    raise SystemExit("Run this setup in an interactive terminal.")
folder = Path(__file__).resolve().parents[1] / ".local"
if not (folder / "bakalari.json").is_file():
    raise SystemExit("Configure the protected Homeboard login with setup_bakalari.py first.")
path = folder / "calendar.json"
if path.exists():
    raise SystemExit(
        "Calendar configuration already exists; edit it locally instead of overwriting."
    )
feeds = []
for index in range(5):
    name = input("Calendar label (blank to finish): ").strip()
    if not name:
        break
    url = getpass.getpass("Secret address in iCal format (hidden): ").strip()
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme == "https"
            and parts.hostname in {"calendar.google.com", "www.google.com"}
            and parts.port in {None, 443}
            and not parts.username
            and not parts.password
            and not parts.query
            and not parts.fragment
            and parts.path.startswith("/calendar/ical/")
            and parts.path.endswith("/basic.ics")
        )
    except ValueError:
        valid = False
    if not valid or len(name) > 60:
        raise SystemExit("Invalid Google iCal address or label. No file written.")
    feeds.append({"name": name, "url": url})
if not feeds:
    raise SystemExit("No calendars entered; no file written.")
with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
    json.dump({"calendars": feeds}, output)
print("Saved local calendar configuration. Run scripts/start_homeboard.py to enable it.")
