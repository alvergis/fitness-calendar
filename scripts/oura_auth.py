#!/usr/bin/env python3
"""One-time Oura OAuth2 authorization. Run locally:

    OURA_CLIENT_ID=... OURA_CLIENT_SECRET=... python3 scripts/oura_auth.py

Opens the Oura consent page, catches the redirect on localhost, exchanges the code for tokens, and
stores OURA_CLIENT_ID, OURA_CLIENT_SECRET and OURA_REFRESH_TOKEN as GitHub repo secrets via `gh`.
Nothing secret is printed.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

REPO = "alvergis/fitness-calendar"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPE = "daily"


def set_secret(name: str, value: str) -> None:
    subprocess.run(["gh", "secret", "set", name, "--repo", REPO], input=value, text=True, check=True)


def main() -> None:
    cid, csec = os.environ.get("OURA_CLIENT_ID"), os.environ.get("OURA_CLIENT_SECRET")
    if not (cid and csec):
        sys.exit("Set OURA_CLIENT_ID and OURA_CLIENT_SECRET first.")

    state = secrets.token_urlsafe(16)
    url = "https://cloud.ouraring.com/oauth/authorize?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
        "scope": SCOPE, "state": state,
    })
    got: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorized. You can close this tab and return to the terminal.")

        def log_message(self, *_):
            pass

    server = HTTPServer(("localhost", PORT), Handler)
    print("Opening Oura authorization page (if nothing opens, visit this URL):\n" + url)
    webbrowser.open(url)
    server.handle_request()

    if got.get("state") != state or "code" not in got:
        sys.exit(f"Authorization failed: {got.get('error', 'missing code or state mismatch')}")

    resp = requests.post("https://api.ouraring.com/oauth/token", data={
        "grant_type": "authorization_code", "code": got["code"], "redirect_uri": REDIRECT,
        "client_id": cid, "client_secret": csec,
    }, timeout=30)
    if resp.status_code != 200:
        sys.exit(f"Token exchange failed: {resp.status_code} {resp.text[:200]}")

    set_secret("OURA_CLIENT_ID", cid)
    set_secret("OURA_CLIENT_SECRET", csec)
    set_secret("OURA_REFRESH_TOKEN", resp.json()["refresh_token"])
    print("Done. Saved OURA_CLIENT_ID, OURA_CLIENT_SECRET and OURA_REFRESH_TOKEN to", REPO)


if __name__ == "__main__":
    main()
