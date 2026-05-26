#!/usr/bin/env python3
"""Download JEFIT workout CSV using Playwright.

Reads JEFIT_EMAIL and JEFIT_PASSWORD from environment variables.
Saves the CSV to data/workouts.csv relative to the repo root.
"""

import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

EMAIL    = os.environ.get("JEFIT_EMAIL", "")
PASSWORD = os.environ.get("JEFIT_PASSWORD", "")
OUT      = Path(__file__).parent.parent / "data" / "workouts.csv"

if not EMAIL or not PASSWORD:
    sys.exit("Error: set JEFIT_EMAIL and JEFIT_PASSWORD environment variables")


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = ctx.new_page()

        # ── 1. Log in ──────────────────────────────────────────────────────
        page.goto("https://www.jefit.com/login", wait_until="networkidle")
        page.screenshot(path=str(OUT.parent / "debug_login.png"))

        # Dismiss cookie banner if present
        try:
            page.click('button:has-text("Accept")', timeout=3000)
        except PWTimeout:
            pass

        # Wait for any visible email/text input
        try:
            page.wait_for_selector(
                'input[type="email"], input[type="text"], input[name="email"], input[name="username"]',
                timeout=15000, state="visible"
            )
        except PWTimeout:
            page.screenshot(path=str(OUT.parent / "debug_no_form.png"))
            print("Could not find login form — screenshot saved", file=sys.stderr)
            browser.close()
            sys.exit(1)

        page.screenshot(path=str(OUT.parent / "debug_form_visible.png"))

        # Fill whichever input is present
        email_input = page.locator('input[type="email"], input[name="email"]').first
        text_input  = page.locator('input[type="text"], input[name="username"]').first
        if email_input.count():
            email_input.fill(EMAIL)
        else:
            text_input.fill(EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.click('button[type="submit"]')

        try:
            page.wait_for_url(lambda url: "login" not in url.lower(), timeout=20000)
        except PWTimeout:
            page.screenshot(path=str(OUT.parent / "debug_after_submit.png"))
            print("Login failed — double-check JEFIT_EMAIL and JEFIT_PASSWORD", file=sys.stderr)
            browser.close()
            sys.exit(1)

        print(f"Logged in, current URL: {page.url}")

        # ── 2. Download CSV ─────────────────────────────────────────────────
        with page.expect_download(timeout=30000) as dl_info:
            page.goto("https://www.jefit.com/my-jefit/settings/exportData.php")

        dl = dl_info.value
        dl.save_as(OUT)
        print(f"Saved: {OUT}")

        browser.close()


if __name__ == "__main__":
    main()
