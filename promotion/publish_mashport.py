#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = Path(os.getenv("PROMOTION_QUEUE_PATH", str(ROOT / "frontend/data/promotion/editorial_queue.json")))
HISTORY_PATH = Path(os.getenv("PROMOTION_HISTORY_PATH", str(ROOT / "frontend/data/promotion/editorial_history.json")))
TARGET_ID = "mashport"
LOGIN_URL = "https://www.mashport.ru/auth"
ADD_URL = "https://www.mashport.ru/annonce/add_update"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pick_entry() -> dict[str, Any]:
    queue = load_json(QUEUE_PATH, {"entries": []})
    for entry in queue.get("entries", []):
        if entry.get("target_id") == TARGET_ID and entry.get("status") in {"ready_for_publish", "ready_for_review"}:
            return entry
    raise RuntimeError(f"No ready MashPort promotion entry found in {QUEUE_PATH}")


def first_visible(page: Page, selectors: list[str]):
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
    return None


def fill_first(page: Page, selectors: list[str], value: str) -> bool:
    if not value:
        return False
    item = first_visible(page, selectors)
    if item is None:
        return False
    try:
        item.fill(value)
        return True
    except Exception:
        return False


def detect_captcha(page: Page) -> bool:
    selectors = [
        'iframe[src*="captcha" i]',
        '.g-recaptcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
        'img[src*="captcha" i]',
    ]
    if any(page.locator(selector).count() for selector in selectors):
        return True
    body = (page.locator("body").inner_text() or "").lower()
    return "captcha" in body or "капча" in body or "я не робот" in body


def page_summary(page: Page) -> dict[str, Any]:
    headings: list[str] = []
    for selector in ("h1", "h2", "h3", ".error", ".alert", ".message", ".notice"):
        loc = page.locator(selector)
        for i in range(min(loc.count(), 15)):
            try:
                text = (loc.nth(i).inner_text() or "").strip()
                if text:
                    headings.append(text[:300])
            except Exception:
                pass
    return {"url": page.url, "title": page.title(), "headings": headings[:25]}


def form_inventory(page: Page) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fields = page.locator("input, textarea, select, [contenteditable='true']")
    for i in range(min(fields.count(), 100)):
        field = fields.nth(i)
        try:
            rows.append(
                {
                    "tag": field.evaluate("(el) => el.tagName.toLowerCase()"),
                    "type": field.get_attribute("type") or "",
                    "name": field.get_attribute("name") or "",
                    "id": field.get_attribute("id") or "",
                    "placeholder": field.get_attribute("placeholder") or "",
                    "required": field.get_attribute("required") is not None,
                }
            )
        except Exception:
            continue
    return rows


def login(page: Page, login_value: str, password: str) -> None:
    page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)

    body = (page.locator("body").inner_text() or "").lower()
    if "необходимо войти" not in body and "личный кабинет" not in body:
        return

    login_input = first_visible(
        page,
        [
            'input[name="login"]',
            'input[name*="login" i]',
            'input[name*="user" i]',
            'input[name*="email" i]',
            'input[type="email"]',
            'input[type="text"]',
        ],
    )
    password_input = first_visible(
        page,
        [
            'input[name="password"]',
            'input[name*="pass" i]',
            'input[type="password"]',
        ],
    )
    if login_input is None or password_input is None:
        print("MASHPORT_PAGE_SUMMARY=" + json.dumps(page_summary(page), ensure_ascii=False))
        print("MASHPORT_FORM_INVENTORY=" + json.dumps(form_inventory(page), ensure_ascii=False))
        raise RuntimeError("MashPort login fields were not found")

    login_input.fill(login_value)
    password_input.fill(password)

    submit = page.get_by_role("button", name=re.compile(r"войти|вход|авториз", re.I))
    if not submit.count():
        submit = page.locator('button[type="submit"], input[type="submit"]')
    if not submit.count():
        raise RuntimeError("MashPort login submit control was not found")

    submit.first.click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(1000)

    page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)
    body = (page.locator("body").inner_text() or "").lower()
    if "необходимо войти в личный кабинет" in body:
        raise RuntimeError("MashPort login was not accepted")


def fill_body(page: Page, value: str) -> bool:
    selectors = [
        'textarea[name*="text" i]',
        'textarea[name*="content" i]',
        'textarea[name*="body" i]',
        'textarea[name*="description" i]',
        'textarea',
    ]
    candidates = []
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            try:
                if item.is_visible():
                    candidates.append(item)
            except Exception:
                pass
    if candidates:
        best = max(candidates, key=lambda x: (x.bounding_box() or {}).get("height", 0))
        try:
            best.fill(value)
            return True
        except Exception:
            pass

    for frame in page.frames:
        try:
            editor = frame.locator('[contenteditable="true"], body[contenteditable="true"]')
            if editor.count():
                editor.first.fill(value)
                return True
        except Exception:
            pass

    editor = page.locator('[contenteditable="true"]')
    if editor.count():
        try:
            editor.first.fill(value)
            return True
        except Exception:
            pass
    return False


def fill_selects(page: Page) -> None:
    selects = page.locator("select")
    for i in range(selects.count()):
        sel = selects.nth(i)
        try:
            if not sel.is_visible() or sel.input_value():
                continue
            options = sel.locator("option")
            preferred = ""
            fallback = ""
            for j in range(options.count()):
                opt = options.nth(j)
                value = opt.get_attribute("value") or ""
                text = (opt.inner_text() or "").strip().lower()
                if not value or opt.is_disabled():
                    continue
                fallback = fallback or value
                if any(key in text for key in ("транспорт", "логист", "машин", "спецтех", "подъем")):
                    preferred = value
                    break
            chosen = preferred or fallback
            if chosen:
                sel.select_option(value=chosen)
        except Exception:
            continue


def submit(page: Page) -> None:
    if detect_captcha(page):
        raise RuntimeError("CAPTCHA/manual anti-bot check detected on MashPort")

    checks = page.locator(
        'input[type="checkbox"][required], '
        'input[type="checkbox"][name*="agree" i], '
        'input[type="checkbox"][name*="accept" i]'
    )
    for i in range(checks.count()):
        try:
            if checks.nth(i).is_visible() and not checks.nth(i).is_checked():
                checks.nth(i).check()
        except Exception:
            pass

    button = page.get_by_role(
        "button",
        name=re.compile(r"добавить|опубликовать|разместить|отправить|сохранить", re.I),
    )
    if not button.count():
        button = page.locator('button[type="submit"], input[type="submit"]')
    if not button.count():
        raise RuntimeError("MashPort article submit control was not found")

    button.first.click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(1200)


def main() -> int:
    if os.getenv("PROMOTION_LIVE") != "1":
        raise RuntimeError("PROMOTION_LIVE=1 is required")

    login_value = os.getenv("MASHPORT_LOGIN", "").strip()
    password = os.getenv("MASHPORT_PASSWORD", "").strip()
    if not login_value or not password:
        raise RuntimeError("MASHPORT_LOGIN/MASHPORT_PASSWORD GitHub Secrets are missing")

    entry = pick_entry()
    title = str(entry.get("title") or "Материал СпецАвтоПортала").strip()[:200]
    site_url = str(entry.get("site_url") or "https://spec-avtoportal.ru/").strip()
    body_text = str(entry.get("post_text") or "").strip()
    if site_url not in body_text:
        body_text = (body_text + "\n\nИсточник: " + site_url).strip()

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        try:
            login(page, login_value, password)
            page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)

            if detect_captcha(page):
                raise RuntimeError("CAPTCHA/manual anti-bot check detected on MashPort add page")

            title_ok = fill_first(
                page,
                [
                    'input[name*="title" i]',
                    'input[name*="name" i]',
                    'input[placeholder*="заголов" i]',
                    'input[placeholder*="назван" i]',
                ],
                title,
            )
            if not title_ok:
                print("MASHPORT_PAGE_SUMMARY=" + json.dumps(page_summary(page), ensure_ascii=False))
                print("MASHPORT_FORM_INVENTORY=" + json.dumps(form_inventory(page), ensure_ascii=False))
                raise RuntimeError("MashPort title field was not found")

            if not fill_body(page, body_text):
                print("MASHPORT_PAGE_SUMMARY=" + json.dumps(page_summary(page), ensure_ascii=False))
                print("MASHPORT_FORM_INVENTORY=" + json.dumps(form_inventory(page), ensure_ascii=False))
                raise RuntimeError("MashPort article body field was not found")

            fill_first(
                page,
                [
                    'input[name*="source" i]',
                    'input[name*="url" i]',
                    'input[name*="link" i]',
                    'input[placeholder*="источник" i]',
                    'input[placeholder*="ссыл" i]',
                ],
                site_url,
            )
            fill_selects(page)
            submit(page)

            body = (page.locator("body").inner_text() or "").lower()
            if "необходимо войти в личный кабинет" in body:
                raise RuntimeError("MashPort session was lost before submit")
            if page.url.rstrip("/").endswith("/annonce/add_update") and any(
                marker in body for marker in ("ошиб", "обязатель", "заполните")
            ):
                print("MASHPORT_PAGE_SUMMARY=" + json.dumps(page_summary(page), ensure_ascii=False))
                print("MASHPORT_FORM_INVENTORY=" + json.dumps(form_inventory(page), ensure_ascii=False))
                raise RuntimeError("MashPort validation failed after submit")

            public = "/annonce/show/" in page.url
            record = {
                "target_id": TARGET_ID,
                "target_name": "МашПорт",
                "item_key": entry.get("item_key"),
                "title": title,
                "source_url": site_url,
                "result_url": page.url,
                "submitted_at": utc_now(),
                "status": "published" if public else "verified_in_author_cabinet",
            }
            if public:
                record["public_url"] = page.url
                record["published_at"] = record["submitted_at"]

            history.setdefault("entries", []).append(record)
            save_json(HISTORY_PATH, history)
            print("MASHPORT_SUBMITTED=" + json.dumps(record, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(f"MASHPORT_ERROR: {exc}", file=sys.stderr)
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
