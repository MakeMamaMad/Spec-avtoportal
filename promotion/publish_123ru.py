#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
TARGET_ID = "123ru"
ADD_URL = "https://123ru.net/kazan/addnews/"


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


def gmail_address() -> str:
    token_path = Path(os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json"))
    if not token_path.exists():
        raise RuntimeError("GMAIL_TOKEN_FILE is missing")

    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json() + "\n", encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Gmail OAuth credentials are not valid")

    headers = {"Authorization": f"Bearer {creds.token}", "Accept": "application/json"}

    try:
        req = urllib.request.Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        address = str(payload.get("emailAddress") or "").strip()
        if "@" in address:
            return address
    except Exception:
        pass

    # Some Gmail tokens can read mail but the profile endpoint is unavailable.
    # Resolve the account address from the From header of the latest sent message.
    list_req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=in%3Asent&maxResults=1",
        headers=headers,
    )
    with urllib.request.urlopen(list_req, timeout=30) as response:
        listing = json.loads(response.read().decode("utf-8"))
    messages = listing.get("messages") or []
    if not messages:
        raise RuntimeError("Could not resolve Gmail account email: no sent messages")

    message_id = str(messages[0].get("id") or "")
    msg_req = urllib.request.Request(
        (
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
            + message_id
            + "?format=metadata&metadataHeaders=From"
        ),
        headers=headers,
    )
    with urllib.request.urlopen(msg_req, timeout=30) as response:
        message = json.loads(response.read().decode("utf-8"))
    from_value = ""
    for header in ((message.get("payload") or {}).get("headers") or []):
        if str(header.get("name") or "").lower() == "from":
            from_value = str(header.get("value") or "")
            break
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", from_value, flags=re.I)
    if not match:
        raise RuntimeError("Could not resolve Gmail account email from Sent header")
    return match.group(0)


def main() -> int:
    if os.getenv("PROMOTION_LIVE") != "1":
        raise RuntimeError("PROMOTION_LIVE=1 is required")

    title = os.getenv(
        "RU123_TITLE",
        "На Comtrans в Казани показали новые коммунальные машины на шасси JAC",
    ).strip()
    source_url = os.getenv(
        "RU123_SOURCE_URL",
        (
            "https://spec-avtoportal.ru/news/"
            "dzhak-avtomobil-predstavil-na-comtrans-novye-musorovoz-i-samosval-na-sha-06501839/"
            "?utm_source=123ru&utm_medium=editorial&utm_campaign=industry_promotion"
            "&utm_content=jac-comtrans-kazan"
        ),
    ).strip()
    body = os.getenv(
        "RU123_BODY",
        (
            "На выставке Comtrans в Казани компания «Джак Автомобиль», "
            "эксклюзивный дистрибьютор JAC Motors в России, показала две новинки "
            "для коммунальной сферы. Среди них — мусоровоз Alfanord KGH на новом "
            "шасси JAC N200X с третьей подъёмно-поворотной осью и новый самосвал "
            "на шасси JAC. Техника ориентирована на коммунальные и городские работы.\n\n"
            "Подробности о представленных машинах опубликованы на СпецАвтоПортале."
        ),
    ).strip()
    item_key = os.getenv("RU123_ITEM_KEY", "news:065018397658").strip()

    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    if any(
        isinstance(row, dict)
        and row.get("target_id") == TARGET_ID
        and row.get("item_key") == item_key
        and str(row.get("status") or "") in {"submitted", "published", "verified"}
        for row in history.get("entries", [])
    ):
        print("RU123_SKIP duplicate")
        return 0

    email = gmail_address()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        try:
            page.goto(ADD_URL, wait_until="domcontentloaded", timeout=60000)

            if page.locator('iframe[src*="captcha" i], .g-recaptcha, [class*="captcha" i], [id*="captcha" i]').count():
                raise RuntimeError("123ru CAPTCHA detected")

            title_field = page.locator('textarea[name="title"]')
            body_field = page.locator('textarea[name="desc"]')
            link_field = page.locator('input[name="link"]')
            email_field = page.locator('input[name="userEmail"]')
            if not all(x.count() for x in (title_field, body_field, link_field, email_field)):
                raise RuntimeError("123ru required article fields were not found")

            title_field.fill(title)
            body_field.fill(body)
            link_field.fill(source_url)
            email_field.fill(email)

            subscribe = page.locator('input[name="subscribe"]')
            if subscribe.count() and subscribe.is_checked():
                subscribe.uncheck()
            telegram = page.locator('input[name="tgPublish"]')
            if telegram.count() and telegram.is_checked():
                telegram.uncheck()

            submit = page.get_by_role("button", name=re.compile(r"опубликовать", re.I))
            if not submit.count():
                submit = page.locator('input[type="submit"], button[type="submit"]')
            if not submit.count():
                raise RuntimeError("123ru publish button was not found")

            submit.last.click()
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            page.wait_for_timeout(1800)

            text = (page.locator("body").inner_text() or "").strip()
            lower = text.lower()
            if page.url.rstrip("/") == ADD_URL.rstrip("/") and any(
                marker in lower for marker in ("ошибка", "заполните", "неверно", "обязательно")
            ):
                print("RU123_RESPONSE_TEXT=" + json.dumps(text[:3500], ensure_ascii=False))
                raise RuntimeError("123ru rejected submission")

            record = {
                "target_id": TARGET_ID,
                "target_name": "123ru.net",
                "item_key": item_key,
                "title": title,
                "source_url": source_url,
                "result_url": page.url,
                "submitted_at": utc_now(),
                "status": "submitted",
                "location": "Казань",
            }

            # A direct public article URL is stronger confirmation than a generic success page.
            if page.url != ADD_URL and "/addnews" not in page.url:
                record["status"] = "published"
                record["public_url"] = page.url
                record["published_at"] = record["submitted_at"]

            history.setdefault("entries", []).append(record)
            save_json(HISTORY_PATH, history)
            print("RU123_RESULT=" + json.dumps(record, ensure_ascii=False))
            print("RU123_RESPONSE_TEXT=" + json.dumps(text[:1800], ensure_ascii=False))
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
