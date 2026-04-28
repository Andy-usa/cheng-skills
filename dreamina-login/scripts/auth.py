#!/usr/bin/env python3
"""Dreamina / 即梦 auth helper: login / logout / status / refresh / cookies.

Captures the user's browser session via Playwright and persists it as a
storage_state JSON file at ~/.dreamina/auth.json. Other skills (e.g. the
`dreamina` CLI used by english-picture-to-video) can load this file to
re-use the authenticated session.

Detection strategy (most reliable first):
  1. Presence of a session cookie (e.g. `sessionid`, `sid_tt`) for the site domain.
  2. DOM signal: avatar/userInfo element present AND login button absent.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

AUTH_DIR = Path(os.path.expanduser("~/.dreamina"))
AUTH_FILE = AUTH_DIR / "auth.json"

SITES = {
    "jimeng": {
        "login_url": "https://jimeng.jianying.com/",
        "home_url": "https://jimeng.jianying.com/",
        # Bytedance/jianying session cookies. `sessionid` is the canonical signal.
        "session_cookies": ["sessionid", "sid_tt", "sid_guard"],
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
        "session_cookies": ["sessionid", "sid_tt", "passport_auth_status"],
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


def _has_session_cookie(cookies: list, site: dict) -> bool:
    names = {c.get("name") for c in cookies}
    return any(n in names for n in site["session_cookies"])


async def _detect_logged_in(page, context, site: dict) -> bool:
    cookies = await context.cookies()
    if _has_session_cookie(cookies, site):
        return True
    try:
        avatar = await page.query_selector(site["logged_in_selector"])
        if avatar is None:
            return False
        login_button = await page.query_selector(site["login_button_selector"])
        return login_button is None
    except Exception:
        return False


async def cmd_login(site_key: str, timeout_seconds: int) -> int:
    from playwright.async_api import async_playwright

    site = SITES[site_key]
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale=site["locale"])
        page = await context.new_page()
        await page.goto(site["login_url"], wait_until="domcontentloaded")

        print(f"[dreamina-login] 浏览器已打开 {site['login_url']}", file=sys.stderr)
        print(
            f"[dreamina-login] 请在浏览器里完成登录（扫码/短信/第三方），"
            f"最多等待 {timeout_seconds}s ...",
            file=sys.stderr,
        )

        deadline = time.monotonic() + timeout_seconds
        logged_in = False
        while time.monotonic() < deadline:
            if await _detect_logged_in(page, context, site):
                logged_in = True
                break
            await asyncio.sleep(2)

        if not logged_in:
            emit({"ok": False, "error": "login_timeout", "site": site_key})
            await browser.close()
            return 2

        # Beat for any post-login redirects to finish setting cookies.
        await page.wait_for_timeout(1500)
        state = await context.storage_state()
        AUTH_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
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
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    site = SITES[site_key]
    if not AUTH_FILE.exists():
        emit({"logged_in": False, "reason": "no_auth_file", "site": site_key})
        return 1

    # Quick offline pre-check: if no session cookie in the file, fail fast
    # without launching a browser.
    try:
        state = json.loads(AUTH_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        emit({"logged_in": False, "reason": f"auth_file_unreadable:{e}", "site": site_key})
        return 1

    if not _has_session_cookie(state.get("cookies", []), site):
        emit({"logged_in": False, "reason": "no_session_cookie", "site": site_key})
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

        await page.wait_for_timeout(2500)
        logged_in = await _detect_logged_in(page, context, site)

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


def cmd_cookies(fmt: str) -> int:
    """Emit cookies from the saved auth file in the requested format."""
    if not AUTH_FILE.exists():
        emit({"ok": False, "error": "no_auth_file"})
        return 1
    try:
        state = json.loads(AUTH_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        emit({"ok": False, "error": f"auth_file_unreadable:{e}"})
        return 1

    cookies = state.get("cookies", [])

    if fmt == "json":
        print(json.dumps(cookies, ensure_ascii=False, indent=2))
    elif fmt == "header":
        # Cookie header value: name=value; name2=value2
        print("; ".join(f"{c['name']}={c['value']}" for c in cookies))
    elif fmt == "netscape":
        # Netscape cookies.txt format (curl/wget compatible)
        print("# Netscape HTTP Cookie File")
        for c in cookies:
            domain = c.get("domain", "")
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure") else "FALSE"
            expires = int(c.get("expires", 0)) if c.get("expires", -1) > 0 else 0
            name = c.get("name", "")
            value = c.get("value", "")
            print(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    else:
        emit({"ok": False, "error": f"unknown_format:{fmt}"})
        return 1
    return 0


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

    p_cookies = sub.add_parser("cookies", help="export cookies from saved auth")
    p_cookies.add_argument(
        "--format", choices=["json", "header", "netscape"], default="json"
    )

    args = parser.parse_args()

    if args.cmd == "login":
        sys.exit(asyncio.run(cmd_login(args.site, args.timeout)))
    elif args.cmd == "status":
        sys.exit(asyncio.run(cmd_status(args.site, args.verbose)))
    elif args.cmd == "logout":
        sys.exit(cmd_logout())
    elif args.cmd == "refresh":
        sys.exit(asyncio.run(cmd_refresh(args.site, args.timeout)))
    elif args.cmd == "cookies":
        sys.exit(cmd_cookies(args.format))


if __name__ == "__main__":
    main()
