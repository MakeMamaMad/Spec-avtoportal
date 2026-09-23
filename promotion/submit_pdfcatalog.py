#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Locator, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "frontend/data/site_promo_queue.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"
TARGET_ID = "pdfcatalog"
TARGET_URL = "https://pdfcatalog.ru/index/addsite"
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
    raise RuntimeError("No ready PDFcatalog site-promotion entry")


def detect_captcha(page: Page) -> bool:
    selectors = [
        'iframe[src*="captcha" i]',
        'img[src*="captcha" i]',
        '.g-recaptcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
        'input[name*="captcha" i]',
        'input[name*="code" i][type="text"]',
    ]
    if any(page.locator(s).count() for s in selectors):
        return True
    body = (page.locator("body").inner_text() or "").lower()
    return any(token in body for token in ("captcha", "капча", "я не робот", "код с картинки"))


def safe_inventory(page: Page) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    controls = page.locator("form input, form textarea, form select, input, textarea, select")
    for i in range(min(controls.count(), 100)):
        el = controls.nth(i)
        try:
            rows.append({
                "tag": el.evaluate("(e) => e.tagName.toLowerCase()"),
                "type": el.get_attribute("type") or "",
                "name": el.get_attribute("name") or "",
                "id": el.get_attribute("id") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "visible": el.is_visible(),
            })
        except Exception:
            pass
    return rows


def visible(locator: Locator) -> list[Locator]:
    items: list[Locator] = []
    for i in range(locator.count()):
        el = locator.nth(i)
        try:
            if el.is_visible():
                items.append(el)
        except Exception:
            pass
    return items


def fill_first(page: Page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        loc = page.locator(selector)
        for el in visible(loc):
            try:
                el.fill(value)
                return True
            except Exception:
                continue
    return False


def select_category(page: Page) -> bool:
    wanted = [
        "Новости - Электронные СМИ",
        "Авто Мото - Разное",
        "Промышленность",
        "Новости - СМИ",
    ]
    for sel in visible(page.locator("select")):
        try:
            opts = sel.locator("option")
            labels = [
                ((opts.nth(i).inner_text() or "").strip(), opts.nth(i).get_attribute("value") or "")
                for i in range(opts.count())
            ]
            for desired in wanted:
                for label, value in labels:
                    if desired.lower() in label.lower() and value:
                        sel.select_option(value=value)
                        print(f"CATEGORY={label}")
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


def main() -> int:
    email = os.getenv("PROMOTION_CONTACT_EMAIL", "").strip()
    if not email:
        print("SKIP: PROMOTION_CONTACT_EMAIL is not configured.")
        return 0

    entry = choose_entry()
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    if any(
        row.get("target_id") == TARGET_ID
        and row.get("status") in {"submitted", "published", "accepted", "under_moderation"}
        for row in history.get("entries", [])
    ):
        print("SKIP: PDFcatalog was already submitted.")
        return 0

    title = str(entry.get("title") or "СпецАвтоПортал")
    site_url = str(entry.get("site_url") or SITE_URL)
    description = str(entry.get("full_description") or entry.get("short_description") or "")
    keywords = ", ".join(entry.get("keywords") or [])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        try:
            health_check(context)
            page = context.new_page()
            resp = page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            if not resp or not resp.ok:
                raise RuntimeError(f"PDFcatalog add-site page returned HTTP {resp.status if resp else 'no response'}")

            if detect_captcha(page):
                print("NEEDS_MANUAL: PDFcatalog CAPTCHA/manual code detected before filling")
                return 0

            # PDFcatalog's current add-site form has no category selector.
            # Moderators assign/adjust the category during review.
            if select_category(page):
                print("CATEGORY_SELECTED")
            else:
                print("CATEGORY_SELECTOR_ABSENT: continuing with moderator categorization")

            # Prefer semantic field names/types; fall back to visible control order.
            url_ok = fill_first(page, [
                'input[type="url"]',
                'input[name*="url" i]',
                'input[name*="site" i]',
                'input[name*="link" i]',
            ], site_url)

            title_ok = fill_first(page, [
                'input[name*="title" i]',
                'input[name*="name" i]',
            ], title)

            email_ok = fill_first(page, [
                'input[type="email"]',
                'input[name*="mail" i]',
                'input[name*="email" i]',
            ], email)

            textareas = visible(page.locator("textarea"))
            if textareas:
                textareas[0].fill(description)
                description_ok = True
            else:
                description_ok = fill_first(page, [
                    'input[name*="descr" i]',
                    'input[name*="text" i]',
                ], description)

            keywords_ok = fill_first(page, [
                'input[name*="keyword" i]',
                'input[name*="key" i]',
                'input[name*="tag" i]',
            ], keywords)

            # Positional fallback for old-style forms.
            text_inputs = [
                el for el in visible(page.locator('input[type="text"], input:not([type])'))
                if "captcha" not in (el.get_attribute("name") or "").lower()
                and "code" not in (el.get_attribute("name") or "").lower()
            ]
            if not url_ok and text_inputs:
                text_inputs[0].fill(site_url)
                url_ok = True
            if not title_ok and len(text_inputs) > 1:
                text_inputs[1].fill(title)
                title_ok = True
            if not email_ok:
                candidates = [el for el in text_inputs if "mail" in ((el.get_attribute("name") or "") + (el.get_attribute("id") or "")).lower()]
                if candidates:
                    candidates[0].fill(email)
                    email_ok = True
            if not keywords_ok and len(text_inputs) >= 4:
                text_inputs[-1].fill(keywords)
                keywords_ok = True

            if not all((url_ok, title_ok, email_ok, description_ok, keywords_ok)):
                print("FORM_INVENTORY=" + json.dumps(safe_inventory(page), ensure_ascii=False))
                raise RuntimeError(
                    f"PDFcatalog fields incomplete url={url_ok} title={title_ok} email={email_ok} "
                    f"description={description_ok} keywords={keywords_ok}"
                )

            if detect_captcha(page):
                print("NEEDS_MANUAL: PDFcatalog CAPTCHA/manual code detected after filling")
                return 0

            submit = page.locator("#submit_r")
            if not submit.count() or not submit.first.is_visible():
                candidates = page.locator('input[type="submit"], button[type="submit"]')
                visible_submit = None
                for i in range(candidates.count()):
                    candidate = candidates.nth(i)
                    try:
                        if candidate.is_visible():
                            visible_submit = candidate
                            break
                    except Exception:
                        pass
                if visible_submit is None:
                    print("FORM_INVENTORY=" + json.dumps(safe_inventory(page), ensure_ascii=False))
                    raise RuntimeError("PDFcatalog visible submit control was not found")
                submit = visible_submit
            else:
                submit = submit.first

            submit.click()
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            body = (page.locator("body").inner_text() or "").lower()

            if any(x in body for x in ("ошибка", "заполните", "неверно")) and "/addsite" in page.url:
                raise RuntimeError("PDFcatalog returned a validation error after submit")

            status = "submitted"
            if any(x in body for x in ("модерац", "провер", "рассмотр")):
                status = "under_moderation"

            record = {
                "target_id": TARGET_ID,
                "target_name": "PDFcatalog",
                "site_url": site_url,
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
