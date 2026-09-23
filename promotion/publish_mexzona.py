#!/usr/bin/env python3
from __future__ import annotations

import html
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
TARGET_ID = "mexzona"
LOGIN_URL = "https://mexzona.ru/login"
HOME_URL = "https://mexzona.ru/"


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
    raise RuntimeError("No ready MEXZONA promotion entry found in promotion_queue.json")


def detect_captcha(page: Page) -> bool:
    selectors = [
        'iframe[src*="captcha" i]',
        '.g-recaptcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
        'img[src*="captcha" i]',
    ]
    if any(page.locator(s).count() for s in selectors):
        return True
    body = (page.locator("body").inner_text() or "").lower()
    return "captcha" in body or "капча" in body or "я не робот" in body


def safe_page_summary(page: Page) -> dict[str, Any]:
    headings: list[str] = []
    for selector in ("h1", "h2", "h3", ".alert", ".error", ".message", ".notice"):
        loc = page.locator(selector)
        for i in range(min(loc.count(), 15)):
            try:
                txt = (loc.nth(i).inner_text() or "").strip()
                if txt:
                    headings.append(txt[:260])
            except Exception:
                pass
    return {"url": page.url, "title": page.title(), "headings": headings[:25]}


def safe_form_inventory(page: Page) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    fields = page.locator("input, textarea, select, [contenteditable='true']")
    for i in range(min(fields.count(), 100)):
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


def first_visible(page: Page, selectors: list[str]):
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            try:
                if loc.nth(i).is_visible():
                    return loc.nth(i)
            except Exception:
                continue
    return None


def fill_first(page: Page, selectors: list[str], value: str) -> bool:
    loc = first_visible(page, selectors)
    if loc is None:
        return False
    try:
        loc.fill(value)
        return True
    except Exception:
        return False


def login(page: Page, email: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

    email_input = first_visible(page, [
        'input[type="email"]',
        'input[name*="email" i]',
        'input[placeholder*="email" i]',
    ])
    password_input = first_visible(page, [
        'input[type="password"]',
        'input[name*="pass" i]',
    ])
    if email_input is None or password_input is None:
        print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
        print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
        raise RuntimeError("MEXZONA login fields were not found")

    email_input.fill(email)
    password_input.fill(password)

    button = page.get_by_role("button", name=re.compile(r"вход|войти|login", re.I))
    if not button.count():
        button = page.locator('button[type="submit"], input[type="submit"]')
    if not button.count():
        raise RuntimeError("MEXZONA login submit button was not found")

    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            button.first.click()
    except Exception:
        page.wait_for_timeout(1500)

    body = (page.locator("body").inner_text() or "").lower()
    if "неверн" in body and ("парол" in body or "email" in body):
        raise RuntimeError("MEXZONA rejected login/password")


def open_article_form(page: Page) -> None:
    entry_pages = [
        HOME_URL,
        "https://mexzona.ru/prodazha-zemlerojnyh-mashin",
    ]
    link = None

    # Prefer article over short news: it gives enough room for useful content + source.
    for entry_url in entry_pages:
        page.goto(entry_url, wait_until="domcontentloaded", timeout=60000)
        candidate = page.get_by_role("link", name=re.compile(r"добавить статью", re.I))
        if not candidate.count():
            candidate = page.locator('a:has-text("Добавить статью")')
        if not candidate.count():
            candidate = page.get_by_role("link", name=re.compile(r"добавить новость", re.I))
        if not candidate.count():
            candidate = page.locator('a:has-text("Добавить новость")')
        if candidate.count():
            link = candidate
            break

    if link is None or not link.count():
        print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
        raise RuntimeError("MEXZONA add-article/news link was not found")

    href = link.first.get_attribute("href")
    if href:
        if href.startswith("http"):
            target = href
        elif href.startswith("/"):
            target = "https://mexzona.ru" + href
        else:
            target = "https://mexzona.ru/" + href
        page.goto(target, wait_until="domcontentloaded", timeout=60000)
    else:
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                link.first.click()
        except Exception:
            link.first.click()
            page.wait_for_timeout(1500)

    # MEXZONA's public "Добавить статью" link can open the article list first.
    # From there, enter the actual create form.
    if "/admin/articles" in page.url and not page.locator(
        'input[name*="title" i], textarea[name*="text" i], textarea[name*="content" i]'
    ).count():
        create_link = page.get_by_role(
            "link",
            name=re.compile(r"добавить|создать|новая статья|новую статью", re.I),
        )
        if not create_link.count():
            create_link = page.locator(
                'a[href*="/admin/articles/create"], '
                'a[href*="/admin/articles/new"], '
                'a[href*="/admin/articles/add"]'
            )

        if create_link.count():
            href2 = create_link.first.get_attribute("href")
            if href2:
                if href2.startswith("http"):
                    target2 = href2
                elif href2.startswith("/"):
                    target2 = "https://mexzona.ru" + href2
                else:
                    target2 = "https://mexzona.ru/" + href2
                page.goto(target2, wait_until="domcontentloaded", timeout=60000)
            else:
                try:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                        create_link.first.click()
                except Exception:
                    create_link.first.click()
                    page.wait_for_timeout(1500)
        else:
            # Laravel-style resource routes commonly expose /create.
            for direct_url in (
                "https://mexzona.ru/admin/articles/create",
                "https://mexzona.ru/admin/articles/new",
                "https://mexzona.ru/admin/articles/add",
            ):
                page.goto(direct_url, wait_until="domcontentloaded", timeout=60000)
                fields = page.locator(
                    'input[name*="title" i], textarea, [contenteditable="true"]'
                )
                if fields.count():
                    break


def fill_body(page: Page, body_text: str) -> bool:
    # MEXZONA uses TinyMCE and hides textarea[name="content"].
    content = page.locator('textarea[name="content"]')
    if content.count():
        editor_id = content.first.get_attribute("id") or ""
        html_text = "<p>" + html.escape(body_text).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
        try:
            page.evaluate(
                """({editorId, plain, html}) => {
                    const el = document.querySelector('textarea[name="content"]');
                    if (!el) return false;
                    el.value = plain;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    if (window.tinymce) {
                        const editor = window.tinymce.get(editorId) || window.tinymce.activeEditor;
                        if (editor) {
                            editor.setContent(html);
                            editor.save();
                        }
                    }
                    return true;
                }""",
                {"editorId": editor_id, "plain": body_text, "html": html_text},
            )
            return True
        except Exception:
            pass

    selectors = [
        'textarea[name*="text" i]',
        'textarea[name*="content" i]',
        'textarea[name*="body" i]',
        'textarea[name*="description" i]',
        'textarea',
    ]
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            try:
                if not item.is_visible():
                    continue
                box = item.bounding_box() or {}
                if box.get("height", 0) < 80 and selector == "textarea":
                    continue
                item.fill(body_text)
                return True
            except Exception:
                continue

    for frame in page.frames:
        try:
            editors = frame.locator('[contenteditable="true"], body[contenteditable="true"]')
            if editors.count():
                editors.first.fill(body_text)
                return True
        except Exception:
            pass

    editors = page.locator('[contenteditable="true"]')
    if editors.count():
        try:
            editors.first.fill(body_text)
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
            opts = sel.locator("option")
            preferred = None
            fallback = None
            for j in range(opts.count()):
                opt = opts.nth(j)
                value = opt.get_attribute("value") or ""
                text = (opt.inner_text() or "").strip().lower()
                if not value or opt.is_disabled():
                    continue
                if fallback is None:
                    fallback = value
                if any(word in text for word in ("груз", "спец", "техник", "транспорт", "строит")):
                    preferred = value
                    break
            value = preferred or fallback
            if value:
                sel.select_option(value=value)
        except Exception:
            continue


def submit(page: Page) -> None:
    if detect_captcha(page):
        raise RuntimeError("CAPTCHA/manual anti-bot check detected; MEXZONA was not submitted")

    checks = page.locator('input[type="checkbox"][required], input[type="checkbox"][name*="agree" i]')
    for i in range(checks.count()):
        try:
            if checks.nth(i).is_visible() and not checks.nth(i).is_checked():
                checks.nth(i).check()
        except Exception:
            pass

    button = page.get_by_role(
        "button",
        name=re.compile(r"опубликовать|добавить|разместить|отправить|сохранить|создать", re.I),
    )
    if not button.count():
        button = page.locator('button[type="submit"], input[type="submit"]')
    if not button.count():
        raise RuntimeError("MEXZONA publish submit button was not found")

    before = page.url
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            button.first.click()
    except Exception:
        button.first.click()
        page.wait_for_timeout(2000)

    if page.url == before:
        page.wait_for_timeout(1000)


def main() -> int:
    if DONE_PATH.exists():
        print("First external promotion has already completed; skipping.")
        return 0

    if os.getenv("PROMOTION_LIVE") != "1":
        raise RuntimeError("PROMOTION_LIVE=1 is required")

    email = os.getenv("MEXZONA_LOGIN", "").strip()
    password = os.getenv("MEXZONA_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("MEXZONA_LOGIN/MEXZONA_PASSWORD GitHub Secrets are missing")

    entry = pick_entry()
    title = str(entry.get("title") or "Материал о рынке спецтехники").strip()[:180]
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
            login(page, email, password)
            open_article_form(page)

            if "/login" in page.url.lower():
                raise RuntimeError("MEXZONA redirected to login before publishing")
            if detect_captcha(page):
                raise RuntimeError("CAPTCHA/manual anti-bot check detected on MEXZONA form")

            title_ok = fill_first(page, [
                'input[name*="title" i]',
                'input[name*="name" i]',
                'input[placeholder*="заголов" i]',
                'input[placeholder*="назван" i]',
            ], title)
            if not title_ok:
                print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
                print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
                raise RuntimeError("MEXZONA title field was not found")

            preview_text = re.sub(r"\\s+", " ", body_text).strip()[:500]
            fill_first(page, ['textarea[name="preview"]'], preview_text)
            fill_first(
                page,
                ['input[name="keywords"]'],
                "спецтехника, грузовая техника, грузовики, прицепы, полуприцепы",
            )

            if not fill_body(page, body_text):
                print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
                print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
                raise RuntimeError("MEXZONA article body field was not found")

            source = first_visible(page, [
                'input[name*="source" i]',
                'input[name*="url" i]',
                'input[name*="link" i]',
                'input[placeholder*="ссыл" i]',
                'input[placeholder*="источник" i]',
            ])
            if source is not None:
                try:
                    source.fill(site_url)
                except Exception:
                    pass

            fill_selects(page)
            submit(page)

            body = (page.locator("body").inner_text() or "").lower()
            if any(x in body for x in ("ошибка", "заполните обязатель", "не удалось")):
                print("PAGE_SUMMARY=" + json.dumps(safe_page_summary(page), ensure_ascii=False))
                print("FORM_INVENTORY=" + json.dumps(safe_form_inventory(page), ensure_ascii=False))
                raise RuntimeError("MEXZONA returned a validation error after submit")

            status = "submitted"
            if page.url and "/login" not in page.url.lower():
                status = "published_or_submitted"

            record = {
                "target_id": TARGET_ID,
                "target_name": "MEXZONA.RU",
                "item_key": entry.get("item_key"),
                "title": title,
                "source_url": site_url,
                "result_url": page.url,
                "submitted_at": utc_now(),
                "status": status,
            }
            history.setdefault("entries", []).append(record)
            save_json(HISTORY_PATH, history)
            save_json(DONE_PATH, record)
            print("SUBMITTED=" + json.dumps(record, ensure_ascii=False))
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
