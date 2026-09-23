#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from publish_mexzona import login

ROOT = Path(__file__).resolve().parents[1]
DONE_PATH = ROOT / "promotion/first_launch_done.json"
LIST_URL = "https://mexzona.ru/admin/articles"


def load_done() -> dict:
    return json.loads(DONE_PATH.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def main() -> int:
    email = os.getenv("MEXZONA_LOGIN", "").strip()
    password = os.getenv("MEXZONA_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("MEXZONA_LOGIN/MEXZONA_PASSWORD GitHub Secrets are missing")

    done = load_done()
    title = str(done.get("title") or "").strip()
    if not title:
        raise RuntimeError("No recorded first-publication title")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        try:
            login(page, email, password)
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)

            target = normalize(title)
            rows = page.locator("tr")
            for i in range(rows.count()):
                row = rows.nth(i)
                text = normalize(row.inner_text() or "")
                if target in text or normalize(title[:60]) in text:
                    href = ""
                    links = row.locator("a")
                    for j in range(links.count()):
                        raw = links.nth(j).get_attribute("href") or ""
                        if raw:
                            href = urljoin("https://mexzona.ru", raw)
                            break
                    result = {
                        "verified": True,
                        "title": title,
                        "status_text": (row.inner_text() or "").strip()[:800],
                        "admin_url": href or page.url,
                    }
                    print("VERIFIED=" + json.dumps(result, ensure_ascii=False))
                    return 0

            # Some admin layouts use cards/list items instead of rows.
            links = page.locator("a")
            for i in range(links.count()):
                link = links.nth(i)
                text = normalize(link.inner_text() or "")
                if target in text or normalize(title[:60]) in text:
                    href = urljoin("https://mexzona.ru", link.get_attribute("href") or "")
                    result = {
                        "verified": True,
                        "title": title,
                        "status_text": (link.inner_text() or "").strip()[:800],
                        "admin_url": href or page.url,
                    }
                    print("VERIFIED=" + json.dumps(result, ensure_ascii=False))
                    return 0

            print("VERIFIED=" + json.dumps({
                "verified": False,
                "title": title,
                "page_url": page.url,
                "page_title": page.title(),
            }, ensure_ascii=False))
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
