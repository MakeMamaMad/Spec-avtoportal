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
        try:
            textarea.fill(body)
            page.evaluate(
                """() => {
                    if (window.tinymce) {
                        const ed = window.tinymce.get('htmlarea_mce') || window.tinymce.activeEditor;
                        if (ed) {
                            ed.setContent(document.querySelector('#htmlarea_mce').value.replace(/\n/g, '<br>'));
                            ed.save();
                        }
                    }
                }"""
            )
            return
        except Exception:
            pass

    editor = page.locator('[contenteditable="true"]')
    if editor.count():
        editor.first.fill(body)
        return

    raise RuntimeError("SdelanoU nas article editor was not found")


def submit(page: Page) -> None:
    buttons = page.get_by_role(
        "button",
        name=re.compile(r"добавить|опубликовать|сохранить|разместить|отправить", re.I),
    )
    if not buttons.count():
        buttons = page.locator('button[type="submit"], input[type="submit"]')
    if not buttons.count():
        raise RuntimeError("SdelanoU nas submit button was not found")

    buttons.first.click()
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(1500)


def main() -> int:
    if os.getenv("PROMOTION_LIVE") != "1":
        raise RuntimeError("PROMOTION_LIVE=1 is required")

    username = os.getenv("SDELANOUNAS_LOGIN", "").strip()
    password = os.getenv("SDELANOUNAS_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("SDELANOUNAS_LOGIN/SDELANOUNAS_PASSWORD are missing")

    title = os.getenv(
        "SDELANOUNAS_TITLE",
        "UMG «СДМ» представит продукцию брянских предприятий на выставке «Иннопром. Беларусь»",
    ).strip()

    source_url = os.getenv(
        "SDELANOUNAS_SOURCE_URL",
        "https://spec-avtoportal.ru/news/umg-sdm-predstavit-produktsiyu-bryanskih-predpriyatiy-gruppy-na-vystavke-9cc7bd13/?utm_source=sdelanounas&utm_medium=editorial&utm_campaign=industry_promotion&utm_content=umg-sdm-innoprom-belarus",
    ).strip()

    body = os.getenv(
        "SDELANOUNAS_BODY",
        (
            "Группа компаний UMG «СДМ» представит продукцию брянских предприятий "
            "на международной промышленной выставке «Иннопром. Беларусь», которая пройдёт "
            "с 30 сентября по 2 октября в Минске.\n\n"
            "Техника будет представлена в составе коллективного стенда Брянской области. "
            "Центральное место в экспозиции займут решения предприятий «Брянский арсенал» "
            "и «Брянский тракторный завод». Посетителям покажут направления дорожно-строительной "
            "и сельскохозяйственной техники, а также производственные и инженерные компетенции предприятий.\n\n"
            "UMG объединяет российские машиностроительные предприятия и выпускает экскаваторы, "
            "автогрейдеры, погрузчики, коммунальные машины, автокраны и другую специальную технику.\n\n"
            f"Подробнее: {source_url}"
        ),
    ).strip()

    tags = os.getenv(
        "SDELANOUNAS_TAGS",
        "UMG, спецтехника, Брянск, машиностроение, производство, Иннопром, Беларусь",
    ).strip()

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    if any(
        isinstance(row, dict)
        and row.get("target_id") == TARGET_ID
        and row.get("source_url") == source_url
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
            if not title_input.count():
                raise RuntimeError("SdelanoU nas title field was not found")
            title_input.fill(title)

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
            lowered = page_text.lower()
            if "/blogs/add" in page.url and any(
                marker in lowered for marker in ("ошибка", "обязатель", "заполните", "необходимо")
            ):
                raise RuntimeError("SdelanoU nas validation failed after submit")

            status = "published" if "/blogs/" in page.url and not page.url.rstrip("/").endswith("/blogs/add") else "submitted"
            record = {
                "target_id": TARGET_ID,
                "target_name": "Сделано у нас",
                "item_key": "news:umg-sdm-innoprom-belarus",
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
