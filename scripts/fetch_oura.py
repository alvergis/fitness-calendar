#!/usr/bin/env python3
"""Pull recent daily steps from Oura (OAuth2) and merge them into steps.json (history is kept).

Oura refresh tokens are single-use: every refresh returns a new one that must be saved, or the
next run cannot authenticate. The new token is written back to the OURA_REFRESH_TOKEN repo secret
using the token in GH_SECRETS_PAT (the built-in GITHUB_TOKEN cannot edit secrets).

Do not run this locally with the production refresh token — it would invalidate the copy in GitHub.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

STEPS = Path(__file__).parent.parent / "steps.json"
WINDOW_DAYS = 45
TOKEN_URL = "https://api.ouraring.com/oauth/token"
API_URL = "https://api.ouraring.com/v2/usercollection/daily_activity"


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def save_refresh_token(token: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    pat = os.environ.get("GH_SECRETS_PAT")
    if not repo or not pat:
        fail("New Oura refresh token received but GITHUB_REPOSITORY / GH_SECRETS_PAT is missing — "
             "cannot save it. Re-run scripts/oura_auth.py to re-authorize.")
    proc = subprocess.run(
        ["gh", "secret", "set", "OURA_REFRESH_TOKEN", "--repo", repo],
        input=token, text=True, capture_output=True, env={**os.environ, "GH_TOKEN": pat},
    )
    if proc.returncode != 0:
        fail(f"Could not save the new Oura refresh token ({proc.stderr.strip()}). "
             "The old token is now invalid — re-run scripts/oura_auth.py to re-authorize.")


def main() -> None:
    client_id = os.environ.get("OURA_CLIENT_ID")
    client_secret = os.environ.get("OURA_CLIENT_SECRET")
    refresh = os.environ.get("OURA_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh):
        print("Oura credentials not set — skipping steps sync")
        return
    if not (os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GH_SECRETS_PAT")):
        # Refreshing consumes the single-use token, so never do it if we cannot save the new one.
        print("GH_SECRETS_PAT not set — skipping steps sync (refreshing would lose the token)")
        return

    tok = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token", "refresh_token": refresh,
        "client_id": client_id, "client_secret": client_secret,
    }, timeout=30)
    if tok.status_code != 200:
        fail(f"Oura token refresh failed: {tok.status_code} {tok.text[:200]}")
    body = tok.json()
    save_refresh_token(body["refresh_token"])   # save before anything else can fail

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=WINDOW_DAYS)
    resp = requests.get(
        API_URL,
        headers={"Authorization": f"Bearer {body['access_token']}"},
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        timeout=30,
    )
    if resp.status_code != 200:
        fail(f"Oura request failed: {resp.status_code} {resp.text[:200]}")

    history = json.loads(STEPS.read_text()) if STEPS.exists() else {}
    for item in resp.json().get("data", []):
        if item.get("day") and item.get("steps") is not None:
            history[item["day"]] = item["steps"]

    STEPS.write_text(json.dumps(history, indent=0, sort_keys=True) + "\n")
    print(f"Saved {len(history)} days of steps to {STEPS}")


if __name__ == "__main__":
    main()
