"""Start only Homeboard with protected local school/calendar configuration."""

import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
raw = (root / ".local" / "bakalari.json").read_text()
try:
    json.loads(raw)
except ValueError:
    raise SystemExit("Invalid local configuration") from None
if os.environ.get("HOMEBOARD_PORT") == "8000":
    raise SystemExit("Port 8000 belongs to YouDidWell; use 8091 or another unused port.")

environment = dict(os.environ, SCHOOL_SOURCE="bakalari", BAKALARI_CONFIG_JSON=raw)
calendar_path = root / ".local" / "calendar.json"
if calendar_path.exists():
    calendar_raw = calendar_path.read_text()
    try:
        json.loads(calendar_raw)
    except ValueError:
        raise SystemExit("Invalid local calendar configuration") from None
    environment.update(CALENDAR_SOURCE="google_ics", GOOGLE_CALENDAR_CONFIG_JSON=calendar_raw)
subprocess.run(
    ["docker", "compose", "up", "-d", "--build", "homeboard"], cwd=root, env=environment, check=True
)
