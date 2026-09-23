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
QUEUE_PATH = ROOT / "frontend/data/promotion_queue.json"
HISTORY_PATH = ROOT / "frontend/data/promotion_history.json"
DONE_PATH = ROOT / "promotion/first_launch_done.json"
TARGET_ID = "truckmix-publishing"
LOGIN_URL = "https://truckmix.ru/login"
ADD_URL = "https://truckmix.ru/news/add?utm_content=main&utm_medium=news&utm_source=help"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pick_entry() -> dict[str, Any]:
    queue = load_json(QUEUE_PATH, {"entries": []})
    for entry in queue.get("entries", []):
        if entry.get("target_id") == TARGET_ID and entry.get("status") == "ready_for_review":
            return entry
    raise RuntimeError("No ready TruckMix promotion entry found in promotion_queue.json")


def find_first(page: Page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count():
            return locator.first
    return None


def fill_locator(locator, value: str) -> bool:
    if locator is None or not value:
        return False
    try:
        locator.scroll_into_view_if_needed()
        locator.fill(value)
        return True
    except Exception:
        return False


def fill_by_label(page: Page, pattern: str, value: str) -> bool:
    rx = re.compile(pattern, re.I)
    labels = page.locator("label")
    for i in range(labels.count()):
        label = labels.nth(i)
        text = (label.inner_text() or "").strip()
        if not rx.search(text):
            continue
        target_id = label.get_attribute("for")
        if target_id:
            target = page.locator(f"#{target_id}")
            if target.count() and fill_locator(target.first, value):
                return True
        nested = label.locator("input, textarea")
        if nested.count() and fill_locator(nested.first, value):
            return True
        parent = label.locator("xpath=..").locator("input, textarea")
        if parent.count() and fill_locator(parent.first, value):
            return True
    return False


def detect_captcha(page: Page) -> bool:
    selectors = [
        'iframe[src*="captcha" i]',
        '.g-recaptcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
    ]
    if any(page.locator(s).count() for s in selectors):
        return True
    body = (page.locator("body").inner_text() or "").lower()
    return "captcha" in body or "капча" in body or "я не робот" in body


def safe_page_summary(page: Page) -> dict[str, Any]:
    headings = []
    for selector in ("h1", "h2", "h3", ".alert", ".error", ".message"):
        loc = page.locator(selector)
        for i in range(min(loc.count(), 12)):
            try:
                text = (loc.nth(i).inner_text() or "").strip()
                if text:
                    headings.append(text[:240])
            except Exception:
                pass
    return {
        "url": page.url,
        "title": page.title(),
        "headings": headings[:20],
    }


def safe_form_inventory(page: Page) -> list[dict[str, str]]:
    """Return only structural form metadata. Never include field values."""
    result: list[dict[str, str]] = []
    fields = page.locator("input, textarea, select, [contenteditable='true']")
    for i in range(min(fields.count(), 80)):
        loc = fields.nth(i)
        try:
            result.append(
                {
                    "tag": loc.evaluate("(el) => el.tagName.toLowerCase()"),
                    "type": loc.get_attribute("type") or "",
                    "name": loc.get_attribute("name") or "",
                    "id": loc.get_attribute("id") or "",
                    "placeholder": loc.get_attribute("placeholder") or "",
                    "required": loc.get_attribute("required") is not None,
                }
            )
        except Exception:
            continue
    return result


def login(page: Page, email: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

    # TruckMix exposes two login forms. Use the main #login-form explicitly,
    # otherwise a generic email selector can hit the newsletter field.
    email_input = page.locator("#LoginForm_username")
    password_input = page.locator("#LoginForm_password")
    submit_button = page.locator("#login-form input[type='submit'], #login-form button[type='submit']")

    if not email_input.count() or not password_input.count() or not submit_button.count():
        raise RuntimeError("TruckMix main login form was not found")

    email_input.fill(email)
    password_input.fill(password)
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            submit_button.first.click()
    except Exception:
        # Some deployments complete auth through client-side navigation.
        # Give the browser a moment to settle before checking errors / protected access.
        page.wait_for_timeout(1500)

    error_text = " ".join(
        page.locator("#login-form .errorMessage, #login-form .error").all_inner_texts()
    ).strip()
    if error_text:
        raise RuntimeError("TruckMix login rejected credentials or validation")

    # Do not infer login failure merely because the login form remains in the DOM.
    # The definitive authentication check happens when we open the protected add-news page.


def fill_editor(page: Page, content: str) -> bool:
    if fill_by_label(page, r"текст|содержание|описание|материал|новост", content):
        return True

    selectors = [
        'textarea[name*="text" i]',
        'textarea[name*="content" i]',
        'textarea[name*="body" i]',
        'textarea[name*="description" i]',
    ]
    loc = find_first(page, selectors)
    if loc and fill_locator(loc, content):
        return True

    textareas = page.locator("textarea")
    visible = []
    for i in range(textareas.count()):
        t = textareas.nth(i)
        try:
            if t.is_visible():
                visible.append(t)
        except Exception:
            pass
    if visible:
        best = max(visible, key=lambda t: (t.bounding_box() or {}).get("height", 0))
        if fill_locator(best, content):
            return True

    for frame in page.frames:
        try:
            editors = frame.locator('[contenteditable="true"]')
            if editors.count():
                editors.first.fill(content)
                return True
        except Exception:
            pass

    editor = page.locator('[contenteditable="true"]')
    if editor.count():
        editor.first.fill(content)
        return True

    return False


def fill_required_selects(page: Page) -> None:
    selects = page.locator("select")
    for i in range(selects.count()):
        sel = selects.nth(i)
        try:
            if not sel.is_visible():
                continue
            current = sel.input_value()
            if current:
                continue
            options = sel.locator("option")
            for j in range(options.count()):
                opt = options.nth(j)
                value = opt.get_attribute("value") or ""
                if value and not opt.is_disabled():
                    sel.select_option(value=value)
                    break
        except Exception:
            continue


def submit(page: Page) -> None:
    if detect_captcha(page):
        raise RuntimeError("CAPTCHA/manual anti-bot check detected; publication was not submitted")

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
        name=re.compile(r"опубликовать|добавить|разместить|отправить|сохранить", re.I),
    )
    if not button.count():
        button = page.locator('button[type="submit"], input[type="submit"]')
    if not button.count():
        raise RuntimeError("TruckMix publication submit button was not found")

    button.first.click()
    page.wait_for_load_state("domcontentloaded", timeout=60000)


def main() -> int:
    if DONE_PATH.exists():
        print("First external promotion has already completed; skipping.")
        return 0

    if os.getenv("PROMOTION_LIVE") != "1":
        raise RuntimeError("PROMOTION_LIVE=1 is required for live third-party publication")

    email = os.getenv("TRUCKMIX_LOGIN", "").strip()
    password = os.getenv("TRUCKMIX_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("TRUCKMIX_LOGIN/TRUCKMIX_PASSWORD GitHub Secrets are missing")

    entry = pick_entry()
    title = str(entry.get("title") or "Новости рынка спецтехники").strip()[:180]
    site_url = str(entry.get("site_url") or "https://spec-avtoportal.ru/").strip()
    post_text = str(entry.get("post_text") or "").strip()
    if site_url not in post_text:
        post_text = (post_text + "\n\nИсточник: " + site_url).strip()

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        try:
            login(page, email, password)
            page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)

            if "/login" in page.url.lower():
                raise RuntimeError("TruckMix redirected back to login before publication")
            if detect_captcha(page):
                raise RuntimeError("CAPTCHA/manual anti-bot check detected on add-news page")

            title_ok = (
                fill_by_label(page, r"заголов|назван", title)
                or fill_locator(
                    find_first(
                        page,
                        [
                            'input[name*="title" i]',
                            'input[name*="name" i]',
                            'input[placeholder*="заголов" i]',
                        ],
                    ),
                    title,
                )
            )
            if not title_ok:
                print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
                print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
                raise RuntimeError("TruckMix title field was not found")

            if not fill_editor(page, post_text):
                print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
                print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
                raise RuntimeError("TruckMix article/news body field was not found")

            source = find_first(
                page,
                [
                    'input[name*="source" i]',
                    'input[name*="url" i]',
                    'input[placeholder*="ссыл" i]',
                    'input[placeholder*="источник" i]',
                ],
            )
            if source:
                fill_locator(source, site_url)

            fill_required_selects(page)
            submit(page)

            body = (page.locator("body").inner_text() or "").lower()
            if "/news/add" in page.url.lower() and any(
                marker in body for marker in ("ошиб", "обязатель", "заполните")
            ):
                print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
                raise RuntimeError("TruckMix returned validation errors after submit")

            published_url = page.url
            record = {
                "target_id": TARGET_ID,
                "target_name": "TRUCKmix.ru",
                "item_key": entry.get("item_key"),
                "title": title,
                "source_url": site_url,
                "published_url": published_url,
                "published_at": utc_now(),
                "status": "published",
            }
            history.setdefault("entries", []).append(record)
            save_json(HISTORY_PATH, history)
            save_json(DONE_PATH, record)
            print(f"PUBLISHED: {published_url}")
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
