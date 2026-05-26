#!/usr/bin/env python3
"""Parse data/workouts.csv and regenerate index.html from template.html."""

import csv
import io
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATA     = ROOT / "data" / "workouts.csv"
TEMPLATE = ROOT / "template.html"
OUT      = ROOT / "index.html"


def infer_type(name: str) -> str | None:
    n = name.lower()
    if any(k in n for k in ("strength", "lift", "weight")):
        return "strength"
    if any(k in n for k in ("run", "cardio", "jog", "walk", "bike", "cycle")):
        return "running"
    if any(k in n for k in ("core", "abs", "plank")):
        return "core"
    if any(k in n for k in ("mobil", "stretch", "yoga", "flexib")):
        return "mobility"
    return None


def csv_row(header: str, line: str) -> dict[str, str]:
    cols = [c.strip() for c in header.split(",")]
    vals = next(csv.reader(io.StringIO(line)), [])
    return {
        cols[i]: vals[i].strip().strip('"') if i < len(vals) else ""
        for i in range(len(cols))
    }


def parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^###\s+(.+?)\s+#+", line)
        if m:
            cur = m.group(1).strip()
            continue
        if cur is not None:
            sections.setdefault(cur, []).append(line)
    return sections


def parse_workouts(csv_text: str) -> dict[str, list[str]]:
    sections = parse_sections(csv_text)
    result: dict[str, set[str]] = {}

    def add(date: str, wtype: str) -> None:
        if date:
            result.setdefault(date, set()).add(wtype)

    # Read user timezone offset from SETTING section (zonedifference column)
    zone_hours = 0
    setting_lines = sections.get("SETTING", [])
    if len(setting_lines) >= 2:
        hdr_line = next((l for l in setting_lines if l.startswith("row_id,")), None)
        dat_lines = [l for l in setting_lines if l[0].isdigit()]
        if hdr_line and dat_lines:
            row = csv_row(hdr_line, dat_lines[0])
            try:
                zone_hours = int(row.get("zonedifference", "0"))
            except ValueError:
                pass
    user_tz = timezone(timedelta(hours=zone_hours))

    # Build dayId → workout type from ROUTINES section
    day_type: dict[str, str] = {}
    last_hdr: str | None = None
    for line in sections.get("ROUTINES", []):
        if line.startswith("row_id,"):
            last_hdr = line
            continue
        if not last_hdr:
            continue
        if "package" in last_hdr and "dayIndex" in last_hdr:
            row = csv_row(last_hdr, line)
            day_id = row.get("_id", "")
            name   = row.get("name", "")
            if day_id and name:
                t = infer_type(name)
                if t:
                    day_type[day_id] = t

    # WORKOUT SESSIONS → typed workout dates
    sess_hdr: str | None = None
    for line in sections.get("WORKOUT SESSIONS", []):
        if line.startswith(("rowid,", "row_id,")):
            sess_hdr = line
            continue
        if not sess_hdr or not line[0].isdigit():
            continue
        row = csv_row(sess_hdr, line)
        starttime = row.get("starttime", "0")
        if not starttime.lstrip("-").isdigit() or int(starttime) <= 0:
            continue
        t = day_type.get(row.get("day_id", ""))
        if not t:
            continue
        ds = datetime.fromtimestamp(int(starttime), tz=user_tz).strftime("%Y-%m-%d")
        add(ds, t)

    # EXERCISE LOGS → running (ename contains "run")
    ex_hdr: str | None = None
    for line in sections.get("EXERCISE LOGS", []):
        if line.startswith("USERID,"):
            ex_hdr = line
            continue
        if not ex_hdr or not line[0].isdigit():
            continue
        row = csv_row(ex_hdr, line)
        if "run" in row.get("ename", "").lower() and row.get("mydate"):
            add(row["mydate"], "running")

    # CARDIO LOGS → running (eid = 317)
    cardio_hdr: str | None = None
    for line in sections.get("CARDIO LOGS", []):
        if line.startswith("row_id,"):
            cardio_hdr = line
            continue
        if not cardio_hdr or not line[0].isdigit():
            continue
        row = csv_row(cardio_hdr, line)
        try:
            eid = int(row.get("eid", "0"))
        except ValueError:
            continue
        if eid == 317 and row.get("mydate"):
            add(row["mydate"], "running")

    return {date: sorted(types) for date, types in sorted(result.items())}


def main() -> None:
    csv_text = DATA.read_text(encoding="utf-8")
    workouts = parse_workouts(csv_text)
    template = TEMPLATE.read_text(encoding="utf-8")

    today     = datetime.now().strftime("%Y-%m-%d")
    json_str  = json.dumps(workouts)

    out = re.sub(
        r"const SEEDED_DATA = \{[^}]*\};",
        f"const SEEDED_DATA = {json_str};",
        template,
        count=1,
    )
    out = re.sub(r"__DATE__", today, out)

    OUT.write_text(out, encoding="utf-8")
    print(f"Generated {OUT} ({len(workouts)} workout days)")


if __name__ == "__main__":
    main()
