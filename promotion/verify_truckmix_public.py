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
PUBLIC_URL = "https://truckmix.ru/publication"


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
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip().lower()


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href = ""
        self.current_text: list[str] = []
        self.depth = 0
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a" and self.depth == 0:
            self.current_href = dict(attrs).get("href") or ""
            self.current_text = []
            self.depth = 1
        elif self.depth:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        self.depth -= 1
        if self.depth == 0:
            text = norm(" ".join(self.current_text))
            self.links.append((self.current_href, text))
            self.current_href = ""
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.current_text.append(data)


def fetch_public() -> str:
    req = urllib.request.Request(
        PUBLIC_URL,
        headers={
            "User-Agent": "SpecAvtoPortal-TruckMix-Verifier/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read(2_000_000).decode(
            response.headers.get_content_charset() or "utf-8",
            errors="replace",
        )


def absolute(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return "https://truckmix.ru" + href
    return "https://truckmix.ru/" + href.lstrip("/")


def find_public_url(page_html: str, title: str) -> str | None:
    wanted = norm(title)
    if not wanted:
        return None

    parser = LinkCollector()
    parser.feed(page_html)
    for href, text in parser.links:
        if wanted in text or text in wanted and len(text) >= 40:
            return absolute(href)

    # Some layouts keep the title outside the anchor. Only treat the page as
    # confirmed if the exact normalized title is visible.
    page_text = norm(re.sub(r"<[^>]+>", " ", page_html))
    if wanted in page_text:
        return PUBLIC_URL
    return None


def main() -> int:
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    rows = [
        row
        for row in history.get("entries", [])
        if isinstance(row, dict)
        and row.get("target_id") == "truckmix-publishing"
        and str(row.get("status") or "") in {"verified_in_author_cabinet", "submitted"}
    ]
    if not rows:
        print("TRUCKMIX_VERIFY_SKIP no_pending")
        return 0

    try:
        page_html = fetch_public()
    except Exception as exc:
        print(f"TRUCKMIX_VERIFY_TEMP_ERROR {type(exc).__name__}")
        return 0

    changed = 0
    for row in rows:
        public_url = find_public_url(page_html, str(row.get("title") or ""))
        row["last_public_check_at"] = utc_now()
        if not public_url:
            row["public_status"] = "pending"
            continue
        row["status"] = "published"
        row["public_status"] = "published"
        row["public_url"] = public_url
        row["published_at"] = utc_now()
        changed += 1

    save_json(HISTORY_PATH, history)
    print(f"TRUCKMIX_VERIFY_OK checked={len(rows)} published={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
