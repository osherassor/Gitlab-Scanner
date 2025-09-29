#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from typing import Set, Dict, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests
from urllib.parse import urlparse


def setup_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1200,900")
    opts.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def extract_users_ui(driver: webdriver.Chrome) -> Dict[str, str]:
    users: Dict[str, str] = {}
    # Prefer elements with explicit data attributes
    for css in [
        'a[data-username]',
        '[data-test-selector="user_link"]',
        '[data-user-username]',
    ]:
        for el in driver.find_elements(By.CSS_SELECTOR, css):
            uname = (el.get_attribute("data-username") or el.get_attribute("data-user-username") or "").strip()
            if not uname:
                continue
            dname = (el.text or "").strip()
            if not dname or dname.startswith("@") or dname == uname:
                # Try to find display name within the same row/card
                try:
                    row = el.find_element(By.XPATH, './ancestor::tr[1]')
                except Exception:
                    row = None
                candidates = []
                if row is not None:
                    candidates = row.find_elements(By.CSS_SELECTOR, 'a, span, strong, div')
                for c in candidates:
                    t = (c.text or "").strip()
                    if t and not t.startswith("@") and t.lower() not in {uname.lower(), "public"} and len(t) > 1:
                        dname = t
                        break
            if uname and uname not in users:
                users[uname] = dname

    # Fallback: profile hrefs
    for el in driver.find_elements(By.CSS_SELECTOR, 'a[href^="/"]'):  # relative links
        href = (el.get_attribute("href") or "").strip()
        # href is absolute after get_attribute; extract last part
        if not href:
            continue
        # GitLab profiles are usually at /<username>
        parts = href.rstrip('/').split('/')
        if len(parts) >= 4:  # https://host/<username>
            cand = parts[3]
            if cand and all(ch.isalnum() or ch in '._-' for ch in cand):
                # skip well-known non-user paths
                if cand.lower() not in {"groups", "users", "projects", "explore", "help", "admin", "profile", "dashboard", "oauth", "signin", "signout", "-"}:
                    if cand not in users:
                        dname = (el.text or "").strip()
                        if dname.startswith("@") or dname.lower() == cand.lower():
                            dname = ""
                        users[cand] = dname

    return users


def paginate(driver: webdriver.Chrome) -> bool:
    # Try common next selectors
    selectors = [
        'a[rel="next"]',
        'a.page-link[rel="next"]',
        'a[aria-label="Next"]',
        'ul.pagination li.page-item a[rel="next"]',
    ]
    for css in selectors:
        els = driver.find_elements(By.CSS_SELECTOR, css)
        if els:
            try:
                els[0].click()
                time.sleep(0.6)
                return True
            except Exception:
                continue
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe users from GitLab members page via Selenium")
    ap.add_argument("url", help="Full URL to project/group members page, e.g. https://host/ns/project/-/project_members")
    ap.add_argument("--headful", action="store_true", help="Show browser window (default: headless)")
    ap.add_argument("--verify-ssl", action="store_true", help="Verify TLS certificates (default: off)")
    args = ap.parse_args()

    driver = setup_driver(headless=not args.headful)
    try:
        print(f"Navigating to: {args.url}")
        driver.get(args.url)
        time.sleep(1.2)
        users: Dict[str, str] = {}
        pages = 0
        while True:
            pages += 1
            users.update(extract_users_ui(driver))
            if pages >= 50:
                break
            if not paginate(driver):
                break
        print(f"Collected users: {len(users)}")
        # show sample
        sample = list(sorted(users.items()))[:25]
        print("sample:", ", ".join([f"{u} ({n})" if n else u for u,n in sample]))

        # Query API for each username (best-effort)
        parsed = urlparse(args.url)
        api_base = f"{parsed.scheme}://{parsed.netloc}/api/v4"
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        verify = bool(args.verify_ssl)
        found = 0
        details: list[Tuple[str, str, int]] = []
        for u in sorted(users.keys()):
            try:
                r = sess.get(f"{api_base}/users", params={"username": u}, timeout=15, verify=verify)
                if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                    details.append((u, r.json()[0].get("name") or users.get(u, ""), r.json()[0].get("id")))
                    found += 1
                    continue
                # fallback search
                r2 = sess.get(f"{api_base}/users", params={"search": u}, timeout=15, verify=verify)
                if r2.status_code == 200 and isinstance(r2.json(), list) and r2.json():
                    details.append((u, r2.json()[0].get("name") or users.get(u, ""), r2.json()[0].get("id")))
                    found += 1
            except Exception:
                continue
        print(f"API matches: {found}/{len(users)}")
        for u,name,uid in details[:25]:
            print(f" - {u} (id={uid}, name={name})")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())


