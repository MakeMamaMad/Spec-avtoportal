#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
PUBLIC_URL = "https://123ru.net/kazan/"


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


def norm(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip().lower()


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href = ""
        self.depth = 0
        self.buf: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a" and self.depth == 0:
            self.href = dict(attrs).get("href") or ""
            self.buf = []
            self.depth = 1
        elif self.depth:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        self.depth -= 1
        if self.depth == 0:
            self.links.append((self.href, norm(" ".join(self.buf))))
            self.href = ""
            self.buf = []

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.buf.append(data)


def fetch() -> str:
    req = urllib.request.Request(
        PUBLIC_URL,
        headers={
            "User-Agent": "SpecAvtoPortal-123ru-Verifier/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read(2_500_000).decode(
            response.headers.get_content_charset() or "utf-8",
            errors="replace",
        )


def absolute(href: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return "https://123ru.net" + href
    return "https://123ru.net/kazan/" + href.lstrip("/")


def find_title(page_html: str, title: str) -> str | None:
    wanted = norm(title)
    parser = LinkCollector()
    parser.feed(page_html)
    for href, text in parser.links:
        if wanted and (wanted == text or wanted in text):
            return absolute(href)
    return None


def main() -> int:
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    pending = [
        row
        for row in history.get("entries", [])
        if isinstance(row, dict)
        and row.get("target_id") == "123ru"
        and str(row.get("status") or "") == "submitted"
    ]
    if not pending:
        print("RU123_VERIFY_SKIP no_pending")
        return 0

    try:
        page_html = fetch()
    except Exception as exc:
        print(f"RU123_VERIFY_TEMP_ERROR {type(exc).__name__}")
        return 0

    published = 0
    for row in pending:
        row["last_public_check_at"] = utc_now()
        url = find_title(page_html, str(row.get("title") or ""))
        if not url:
            row["public_status"] = "pending_moderation"
            continue
        row["status"] = "published"
        row["public_status"] = "published"
        row["public_url"] = url
        row["published_at"] = utc_now()
        published += 1
        print(
            "RU123_PUBLISHED "
            + json.dumps(
                {"title": row.get("title"), "public_url": url},
                ensure_ascii=False,
            )
        )

    save_json(HISTORY_PATH, history)
    print(f"RU123_VERIFY_OK checked={len(pending)} published={published}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
