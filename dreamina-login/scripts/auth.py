#!/usr/bin/env python3
"""Dreamina / 即梦 auth helper: login / logout / status / refresh.

Captures the user's browser session via Playwright and persists it as a
storage_state JSON file at ~/.dreamina/auth.json. Other skills (e.g. the
`dreamina` CLI used by english-picture-to-video) can load this file to
re-use the authenticated session.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

AUTH_DIR = Path(os.path.expanduser("~/.dreamina"))
AUTH_FILE = AUTH_DIR / "auth.json"

SITES = {
    "jimeng": {
        "login_url": "https://jimeng.jianying.com/",
        "home_url": "https://jimeng.jianying.com/",
        "logged_in_selector": (
            '[class*="avatar" i], [class*="Avatar" i], '
            '[data-testid*="user" i], [class*="userInfo" i]'
        ),
        "login_button_selector": (
            'button:has-text("登录"), a:has-text("登录"), text=立即登录'
        ),
        "locale": "zh-CN",
    },
    "dreamina": {
        "login_url": "https://dreamina.capcut.com/",
        "home_url": "https://dreamina.capcut.com/",
        "logged_in_selector": (
            '[class*="avatar" i], [class*="Avatar" i], '
            '[data-testid*="user" i], [class*="userInfo" i]'
        ),
        "login_button_selector": (
            'button:has-text("Sign in"), a:has-text("Sign in"), '
            'button:has-text("Log in")'
        ),
        "locale": "en-US",
    },
}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


async def _detect_logged_in(page, site: dict) -> bool:
    avatar = await page.query_selector(site["logged_in_selector"])
    if avatar is None:
        return False
    login_button = await page.query_selector(site["login_button_selector"])
    return login_button is None


async def cmd_login(site_key: str, timeout_seconds: int) -> int:
    site = SITES[site_key]
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale=site["locale"])
        page = await context.new_page()
        await page.goto(site["login_url"], wait_until="domcontentloaded")

        print(
            f"[dreamina-login] 浏览器已打开 {site['login_url']}",
            file=sys.stderr,
        )
        print(
            f"[dreamina-login] 请手动完成登录，最多等待 {timeout_seconds}s ...",
            file=sys.stderr,
        )

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        logged_in = False
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await _detect_logged_in(page, site):
                    logged_in = True
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        if not logged_in:
            emit({"ok": False, "error": "login_timeout", "site": site_key})
            await browser.close()
            return 2

        # Give the page a beat to set cookies after login redirects settle.
        await page.wait_for_timeout(1500)
        state = await context.storage_state()
        AUTH_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2)
        )
        os.chmod(AUTH_FILE, 0o600)
        emit({
            "ok": True,
            "auth_file": str(AUTH_FILE),
            "site": site_key,
            "cookie_count": len(state.get("cookies", [])),
        })
        await browser.close()
        return 0


async def cmd_status(site_key: str, verbose: bool = False) -> int:
    site = SITES[site_key]
    if not AUTH_FILE.exists():
        emit({"logged_in": False, "reason": "no_auth_file", "site": site_key})
        return 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(AUTH_FILE), locale=site["locale"]
        )
        page = await context.new_page()
        try:
            await page.goto(site["home_url"], wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            emit({"logged_in": False, "reason": "page_load_timeout", "site": site_key})
            await browser.close()
            return 1

        await page.wait_for_timeout(3000)
        logged_in = await _detect_logged_in(page, site)

        result = {"logged_in": logged_in, "site": site_key}
        if verbose:
            cookies = await context.cookies()
            result["cookie_count"] = len(cookies)
            result["auth_file"] = str(AUTH_FILE)
        emit(result)
        await browser.close()
        return 0 if logged_in else 1


def cmd_logout() -> int:
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
        emit({"ok": True, "removed": str(AUTH_FILE)})
    else:
        emit({"ok": True, "note": "auth file already absent"})
    return 0


async def cmd_refresh(site_key: str, timeout_seconds: int) -> int:
    status_code = await cmd_status(site_key)
    if status_code == 0:
        emit({"ok": True, "note": "still logged in", "site": site_key})
        return 0
    return await cmd_login(site_key, timeout_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dreamina/即梦 auth helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_site(p):
        p.add_argument("--site", choices=list(SITES.keys()), default="jimeng")

    p_login = sub.add_parser("login", help="open browser and capture session")
    add_site(p_login)
    p_login.add_argument("--timeout", type=int, default=300)

    p_status = sub.add_parser("status", help="check whether saved session is valid")
    add_site(p_status)
    p_status.add_argument("--verbose", action="store_true")

    sub.add_parser("logout", help="delete saved session")

    p_refresh = sub.add_parser("refresh", help="re-login only if expired")
    add_site(p_refresh)
    p_refresh.add_argument("--timeout", type=int, default=300)

    args = parser.parse_args()

    if args.cmd == "login":
        sys.exit(asyncio.run(cmd_login(args.site, args.timeout)))
    elif args.cmd == "status":
        sys.exit(asyncio.run(cmd_status(args.site, args.verbose)))
    elif args.cmd == "logout":
        sys.exit(cmd_logout())
    elif args.cmd == "refresh":
        sys.exit(asyncio.run(cmd_refresh(args.site, args.timeout)))


if __name__ == "__main__":
    main()
