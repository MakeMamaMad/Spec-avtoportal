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
QUEUE_PATH = ROOT / "frontend/data/site_promo_queue.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"
TARGET_ID = "popcat"
TARGET_URL = "https://www.popcat.ru/addsite"
SITE_URL = "https://spec-avtoportal.ru/"


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


def choose_entry() -> dict[str, Any]:
    queue = load_json(QUEUE_PATH, {"entries": []})
    for row in queue.get("entries", []):
        if row.get("target_id") == TARGET_ID and row.get("status") == "ready":
            return row
    raise RuntimeError("No ready PopCat site-promotion entry")


def detect_captcha(page: Page) -> bool:
    selectors = [
        'iframe[src*="captcha" i]',
        '.g-recaptcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
    ]
    if any(page.locator(s).count() for s in selectors):
        return True
    text = (page.locator("body").inner_text() or "").lower()
    return "captcha" in text or "капча" in text or "я не робот" in text


def fill_by_placeholder(page: Page, pattern: str, value: str) -> bool:
    fields = page.locator("input, textarea")
    rx = re.compile(pattern, re.I)
    for i in range(fields.count()):
        field = fields.nth(i)
        placeholder = field.get_attribute("placeholder") or ""
        if rx.search(placeholder):
            try:
                field.fill(value)
                return True
            except Exception:
                pass
    return False


def fill_textareas(page: Page, short_text: str, full_text: str) -> None:
    textareas = page.locator("textarea")
    visible = []
    for i in range(textareas.count()):
        ta = textareas.nth(i)
        try:
            if ta.is_visible():
                visible.append(ta)
        except Exception:
            pass
    if len(visible) < 2:
        raise RuntimeError("PopCat description fields were not found")
    visible[0].fill(short_text)
    visible[1].fill(full_text)


def choose_select_option(page: Page, wanted: list[str], *, prefer_free: bool = False) -> bool:
    selects = page.locator("select")
    for i in range(selects.count()):
        sel = selects.nth(i)
        try:
            if not sel.is_visible():
                continue
            opts = sel.locator("option")
            labels = []
            for j in range(opts.count()):
                opt = opts.nth(j)
                labels.append(((opt.inner_text() or "").strip(), opt.get_attribute("value") or ""))
            if prefer_free:
                for label, value in labels:
                    if "бесплат" in label.lower() and value:
                        sel.select_option(value=value)
                        return True
            else:
                for desired in wanted:
                    for label, value in labels:
                        if desired.lower() in label.lower() and value:
                            sel.select_option(value=value)
                            return True
        except Exception:
            continue
    return False


def health_check(context) -> None:
    page = context.new_page()
    try:
        resp = page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
        if not resp or not resp.ok:
            raise RuntimeError("SpecAvtoPortal homepage is not reachable")
        result = page.evaluate(
            """async () => {
                for (const u of ['/data/news.json', 'data/news.json']) {
                    try {
                        const r = await fetch(u, {cache: 'no-store'});
                        if (!r.ok) continue;
                        const d = await r.json();
                        const items = Array.isArray(d) ? d : (d.items || []);
                        if (items.length) return {ok:true, count:items.length, url:r.url};
                    } catch (_) {}
                }
                return {ok:false};
            }"""
        )
        if not result or not result.get("ok"):
            raise RuntimeError("SpecAvtoPortal news feed health-check failed")
        print(f"SITE_HEALTH_OK items={result.get('count')}")
    finally:
        page.close()


def safe_inventory(page: Page) -> list[dict[str, str]]:
    rows = []
    controls = page.locator("input, textarea, select")
    for i in range(min(controls.count(), 80)):
        el = controls.nth(i)
        try:
            rows.append({
                "tag": el.evaluate("(e) => e.tagName.toLowerCase()"),
                "type": el.get_attribute("type") or "",
                "name": el.get_attribute("name") or "",
                "id": el.get_attribute("id") or "",
                "placeholder": el.get_attribute("placeholder") or "",
            })
        except Exception:
            pass
    return rows


def main() -> int:
    email = os.getenv("PROMOTION_CONTACT_EMAIL", "").strip()
    if not email:
        print("SKIP: PROMOTION_CONTACT_EMAIL GitHub Secret is not configured.")
        return 0

    entry = choose_entry()
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    if any(
        row.get("target_id") == TARGET_ID
        and row.get("status") in {"submitted", "published", "accepted", "under_moderation"}
        for row in history.get("entries", [])
    ):
        print("SKIP: PopCat was already submitted.")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        try:
            health_check(context)
            page = context.new_page()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

            if detect_captcha(page):
                print("NEEDS_MANUAL: captcha detected before form submission")
                return 0

            choose_select_option(page, [], prefer_free=True)
            if not choose_select_option(page, entry.get("preferred_categories", [])):
                print("FORM_INVENTORY=" + json.dumps(safe_inventory(page), ensure_ascii=False))
                raise RuntimeError("PopCat category option was not found")

            if not fill_by_placeholder(page, r"PopCat|назван|сайт", str(entry.get("title") or "")):
                # First visible text input after selects is normally title.
                inputs = page.locator('input[type="text"]')
                if not inputs.count():
                    raise RuntimeError("PopCat title field was not found")
                inputs.first.fill(str(entry.get("title") or ""))

            if not fill_by_placeholder(page, r"https?://|адрес", str(entry.get("site_url") or SITE_URL)):
                url_input = page.locator('input[type="url"]')
                if url_input.count():
                    url_input.first.fill(str(entry.get("site_url") or SITE_URL))
                else:
                    raise RuntimeError("PopCat URL field was not found")

            if not fill_by_placeholder(page, r"@|mail|yandex", email):
                email_input = page.locator('input[type="email"]')
                if email_input.count():
                    email_input.first.fill(email)
                else:
                    raise RuntimeError("PopCat email field was not found")

            fill_textareas(
                page,
                str(entry.get("short_description") or ""),
                str(entry.get("full_description") or ""),
            )
            fill_by_placeholder(page, r"Россия|Москва|город", str(entry.get("region") or "Россия"))
            fill_by_placeholder(page, r"ключев", ", ".join(entry.get("keywords") or []))

            if detect_captcha(page):
                print("NEEDS_MANUAL: captcha detected after form completion")
                return 0

            submit = page.locator('input[type="submit"], button[type="submit"]')
            if not submit.count():
                button = page.get_by_role("button", name=re.compile(r"добавить сайт|отправить|добавить", re.I))
                submit = button
            if not submit.count():
                print("FORM_INVENTORY=" + json.dumps(safe_inventory(page), ensure_ascii=False))
                raise RuntimeError("PopCat submit control was not found")

            submit.first.click()
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            body = (page.locator("body").inner_text() or "").lower()

            status = "submitted"
            if "модерац" in body or "рассмотр" in body or "очеред" in body:
                status = "under_moderation"
            elif "добавлен" in body or "успеш" in body:
                status = "submitted"

            record = {
                "target_id": TARGET_ID,
                "target_name": "PopCat.ru",
                "site_url": entry.get("site_url"),
                "result_url": page.url,
                "submitted_at": utc_now(),
                "status": status,
            }
            history.setdefault("entries", []).append(record)
            save_json(HISTORY_PATH, history)
            print("SUBMITTED=" + json.dumps(record, ensure_ascii=False))
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
