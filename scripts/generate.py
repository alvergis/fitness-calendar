#!/usr/bin/env python3
"""Parse data/workouts.csv + steps.json and regenerate index.html from template.html."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

USER_TZ = ZoneInfo("America/Los_Angeles")

ROOT     = Path(__file__).parent.parent
DATA     = ROOT / "data" / "workouts.csv"
STEPS    = ROOT / "steps.json"
TEMPLATE = ROOT / "template.html"
OUT      = ROOT / "index.html"

STATIONARY_BIKE_EID = "318"


def routine_kind(name: str) -> str | None:
    n = name.lower()
    if any(k in n for k in ("strength", "lift", "weight")):
        return "strength"
    if any(k in n for k in ("core", "abs", "plank")):
        return "core"
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


def rows(lines: list[str], header_prefixes: tuple[str, ...]):
    """Yield dict rows from a section, using the most recent header line."""
    hdr = None
    for line in lines:
        if line.startswith(header_prefixes):
            hdr = line
            continue
        if hdr and line[0].isdigit():
            yield hdr, csv_row(hdr, line)


def parse_days(csv_text: str) -> dict[str, list[int]]:
    """Return {date: [strength 0/1, core 0/1, bike_minutes]}."""
    sections = parse_sections(csv_text)
    strength: set[str] = set()
    core: set[str] = set()
    bike_secs_sessions: dict[str, int] = {}
    bike_secs_cardio: dict[str, int] = {}

    # ROUTINES → day _id → kind
    day_kind: dict[str, str] = {}
    last_hdr = None
    for line in sections.get("ROUTINES", []):
        if line.startswith("row_id,"):
            last_hdr = line
            continue
        if last_hdr and "package" in last_hdr and "dayIndex" in last_hdr:
            row = csv_row(last_hdr, line)
            kind = routine_kind(row.get("name", ""))
            if row.get("_id") and kind:
                day_kind[row["_id"]] = kind

    # WORKOUT SESSIONS → strength / core dates
    for _, row in rows(sections.get("WORKOUT SESSIONS", []), ("rowid,", "row_id,")):
        starttime = row.get("starttime", "0")
        if not starttime.isdigit() or int(starttime) <= 0:
            continue
        kind = day_kind.get(row.get("day_id", ""))
        if not kind:
            continue
        date = datetime.fromtimestamp(int(starttime), tz=USER_TZ).strftime("%Y-%m-%d")
        (strength if kind == "strength" else core).add(date)

    # EXERCISE SET LOGS → duration (seconds) per exercise log id
    set_secs: dict[str, int] = {}
    for _, row in rows(sections.get("EXERCISE SET LOGS", []), ("_id,",)):
        dur = row.get("duration", "")
        if dur.isdigit():
            key = row.get("exercise_log_id", "")
            set_secs[key] = set_secs.get(key, 0) + int(dur)

    # EXERCISE LOGS → stationary bike (duration from set logs)
    for _, row in rows(sections.get("EXERCISE LOGS", []), ("USERID,",)):
        if row.get("eid") == STATIONARY_BIKE_EID and row.get("mydate"):
            d = row["mydate"]
            bike_secs_sessions[d] = bike_secs_sessions.get(d, 0) + set_secs.get(row.get("_id", ""), 0)

    # CARDIO LOGS (older format) → stationary bike
    for _, row in rows(sections.get("CARDIO LOGS", []), ("row_id,",)):
        if row.get("eid") == STATIONARY_BIKE_EID and row.get("mydate"):
            dur = row.get("duration", "")
            if dur.isdigit():
                d = row["mydate"]
                bike_secs_cardio[d] = bike_secs_cardio.get(d, 0) + int(dur)

    dates = set(strength) | set(core) | set(bike_secs_sessions) | set(bike_secs_cardio)
    result: dict[str, list[int]] = {}
    for d in sorted(dates):
        # The two bike sources can describe the same entry, so take the larger.
        bike = max(bike_secs_sessions.get(d, 0), bike_secs_cardio.get(d, 0)) // 60
        result[d] = [int(d in strength), int(d in core), bike]
    return result


def main() -> None:
    days  = parse_days(DATA.read_text(encoding="utf-8"))
    steps = json.loads(STEPS.read_text()) if STEPS.exists() else {}
    template = TEMPLATE.read_text(encoding="utf-8")

    today = datetime.now(USER_TZ).strftime("%Y-%m-%d")
    out = (
        template
        .replace("__DAYS__", json.dumps(days))
        .replace("__STEPS__", json.dumps(steps, sort_keys=True))
        .replace("__DATE__", today)
    )
    OUT.write_text(out, encoding="utf-8")
    print(f"Generated {OUT} ({len(days)} workout days, {len(steps)} step days)")


if __name__ == "__main__":
    main()
