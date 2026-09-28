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
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
LOGIN_URL = "https://sdelanounas.ru/blogs/add/"
ADD_URL = "https://sdelanounas.ru/blogs/add/"
TARGET_ID = "sdelanounas"


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


def login(page: Page, username: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    body = (page.locator("body").inner_text() or "").lower()
    if "войти на сайт" not in body:
        return

    user = page.locator("#fx-login")
    pwd = page.locator("#fx-password")
    if not user.count() or not pwd.count():
        raise RuntimeError("SdelanoU nas login form was not found")

    user.fill(username)
    pwd.fill(password)

    submit = page.get_by_role("button", name=re.compile(r"войти", re.I))
    if not submit.count():
        submit = page.locator('button[type="submit"], input[type="submit"]')
    if not submit.count():
        raise RuntimeError("SdelanoU nas login submit button was not found")

    submit.first.click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(1000)

    page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)
    body = (page.locator("body").inner_text() or "").lower()
    if "войти на сайт" in body:
        raise RuntimeError("SdelanoU nas login was rejected")


def select_category(page: Page) -> str:
    select = page.locator("#fx-blog-select")
    if not select.count():
        raise RuntimeError("SdelanoU nas category select was not found")

    options = select.locator("option")
    preferred = None
    fallback = None
    for i in range(options.count()):
        opt = options.nth(i)
        value = opt.get_attribute("value") or ""
        text = (opt.inner_text() or "").strip()
        if not value:
            continue
        fallback = fallback or value
        lowered = text.lower()
        if "транспорт" in lowered and ("спецтех" in lowered or "логист" in lowered):
            preferred = value
            break
    value = preferred or fallback
    if not value:
        raise RuntimeError("SdelanoU nas has no selectable category")
    select.select_option(value=value)
    return value


def fill_message(page: Page, body: str) -> None:
    textarea = page.locator("#htmlarea_mce")
    if textarea.count():
        ok = page.evaluate(
            """(value) => {
                const ta = document.querySelector('#htmlarea_mce');
                if (!ta) return false;
                ta.value = value;
                ta.dispatchEvent(new Event('input', {bubbles:true}));
                ta.dispatchEvent(new Event('change', {bubbles:true}));
                if (window.tinymce) {
                    const ed = window.tinymce.get('htmlarea_mce') || window.tinymce.activeEditor;
                    if (ed) {
                        const escaped = value
                            .replace(/&/g, '&amp;')
                            .replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;')
                            .replaceAll(String.fromCharCode(10), '<br>');
                        ed.setContent(escaped);
                        ed.save();
                    }
                }
                return true;
            }""",
            body,
        )
        if ok:
            return

    editor = page.locator('[contenteditable="true"]')
    if editor.count():
        editor.first.fill(body)
        return

    raise RuntimeError("SdelanoU nas article editor was not found")


def validation_messages(page: Page) -> list[str]:
    messages: list[str] = []
    selectors = (
        ".error", ".errors", ".alert", ".alert-danger", ".invalid-feedback",
        ".help-block", "[role='alert']", ".fx-error", ".form-error",
    )
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(min(loc.count(), 40)):
            try:
                text = (loc.nth(i).inner_text() or "").strip()
                if text and text not in messages:
                    messages.append(text[:500])
            except Exception:
                pass
    return messages[:50]


def structural_inventory(page: Page) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fields = page.locator("input, textarea, select, [contenteditable='true']")
    for i in range(min(fields.count(), 120)):
        field = fields.nth(i)
        try:
            rows.append(
                {
                    "tag": field.evaluate("(el)=>el.tagName.toLowerCase()"),
                    "type": field.get_attribute("type") or "",
                    "name": field.get_attribute("name") or "",
                    "id": field.get_attribute("id") or "",
                    "required": field.get_attribute("required") is not None,
                    "visible": field.is_visible(),
                }
            )
        except Exception:
            continue
    return rows


def submit(page: Page) -> None:
    title = page.locator("#fx-title")
    form = title.locator("xpath=ancestor::form[1]") if title.count() else page.locator("form").first
    buttons = form.locator('button[type="submit"], input[type="submit"]')
    if not buttons.count():
        buttons = form.get_by_role(
            "button",
            name=re.compile(r"опубликовать|добавить|сохранить|разместить|отправить", re.I),
        )
    if not buttons.count():
        raise RuntimeError("SdelanoU nas submit button was not found")

    buttons.last.click()
    page.wait_for_timeout(700)

    body = (page.locator("body").inner_text() or "")
    if "Я подтверждаю, что в заголовке НЕТ будущего времени" in body:
        yes = page.get_by_text("Да", exact=True)
        clicked = False
        for i in range(yes.count()):
            try:
                if yes.nth(i).is_visible():
                    yes.nth(i).click()
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            raise RuntimeError("SdelanoU nas future-tense confirmation could not be accepted")
        page.wait_for_timeout(300)

        form = page.locator("#fx-title").locator("xpath=ancestor::form[1]")
        submit_again = form.locator('button[type="submit"], input[type="submit"]')
        if submit_again.count():
            submit_again.last.click()

    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(1800)


def main() -> int:
    if os.getenv("PROMOTION_LIVE") != "1":
        raise RuntimeError("PROMOTION_LIVE=1 is required")

    username = os.getenv("SDELANOUNAS_LOGIN", "").strip()
    password = os.getenv("SDELANOUNAS_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("SDELANOUNAS_LOGIN/SDELANOUNAS_PASSWORD are missing")

    title = os.getenv("SDELANOUNAS_TITLE", "").strip()
    source_url = os.getenv("SDELANOUNAS_SOURCE_URL", "").strip()
    body = os.getenv("SDELANOUNAS_BODY", "").strip()
    tags = os.getenv("SDELANOUNAS_TAGS", "").strip()
    item_key = os.getenv("SDELANOUNAS_ITEM_KEY", "").strip()

    if not title or not source_url or not body or not tags or not item_key:
        raise RuntimeError(
            "SDELANOUNAS_TITLE/SOURCE_URL/BODY/TAGS/ITEM_KEY are required"
        )

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    if any(
        isinstance(row, dict)
        and row.get("target_id") == TARGET_ID
        and (
            row.get("item_key") == item_key
            or row.get("source_url") == source_url
        )
        and row.get("status") in {"submitted", "published", "verified_in_author_cabinet"}
        for row in history.get("entries", [])
    ):
        print("SDELANOUNAS_SKIP duplicate")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        try:
            login(page, username, password)
            page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)

            category = select_category(page)

            title_input = page.locator("#fx-title")
            title_editor = page.locator("#editableTitle")
            if not title_input.count() and not title_editor.count():
                raise RuntimeError("SdelanoU nas title field was not found")

            if title_editor.count():
                try:
                    title_editor.fill(title)
                except Exception:
                    title_editor.evaluate(
                        "(el, value) => { el.textContent = value; el.dispatchEvent(new Event('input', {bubbles:true})); }",
                        title,
                    )

            if title_input.count():
                title_input.evaluate(
                    "(el, value) => { el.value = value; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                    title,
                )

            fill_message(page, body)

            tags_input = page.locator("#fx-tags")
            if not tags_input.count():
                raise RuntimeError("SdelanoU nas tags field was not found")
            tags_input.fill(tags)

            source_input = page.locator("#fx-source")
            if source_input.count():
                source_input.fill(source_url)

            unique = page.locator("#fx-unique_content")
            if unique.count() and unique.is_checked():
                unique.uncheck()

            submit(page)

            page_text = (page.locator("body").inner_text() or "")
            current_title = ""
            if page.locator("#fx-title").count():
                try:
                    current_title = page.locator("#fx-title").input_value()
                except Exception:
                    current_title = ""
            if not current_title and page.locator("#editableTitle").count():
                try:
                    current_title = (page.locator("#editableTitle").inner_text() or "").strip()
                except Exception:
                    current_title = ""

            still_add = page.url.rstrip("/").endswith("/blogs/add")
            if still_add and current_title.strip() == title.strip():
                print("SDELANOUNAS_VALIDATION=" + json.dumps(validation_messages(page), ensure_ascii=False))
                print("SDELANOUNAS_FORM_AFTER_SUBMIT=" + json.dumps(structural_inventory(page), ensure_ascii=False))
                print("SDELANOUNAS_BODY_AFTER_SUBMIT=" + json.dumps(page_text[:2500], ensure_ascii=False))
                raise RuntimeError("SdelanoU nas submission did not leave the article form")

            status = "published" if "/blogs/" in page.url and not still_add else "submitted"
            record = {
                "target_id": TARGET_ID,
                "target_name": "Сделано у нас",
                "item_key": item_key,
                "title": title,
                "source_url": source_url,
                "result_url": page.url,
                "category_id": category,
                "submitted_at": utc_now(),
                "status": status,
            }
            if status == "published":
                record["public_url"] = page.url
                record["published_at"] = record["submitted_at"]

            history.setdefault("entries", []).append(record)
            save_json(HISTORY_PATH, history)
            print("SDELANOUNAS_RESULT=" + json.dumps(record, ensure_ascii=False))
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
