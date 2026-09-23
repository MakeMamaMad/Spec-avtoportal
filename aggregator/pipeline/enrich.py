from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})


def _clean(value: Any) -> str:
    if not value:
        return ""
    text = BeautifulSoup(str(value), "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _meta(soup: BeautifulSoup, attr: str, value: str) -> str:
    tag = soup.find("meta", attrs={attr: value})
    return _clean(tag.get("content")) if tag else ""


def extract_summary(html: str, title: str = "", limit: int = 650) -> str:
    soup = BeautifulSoup(html[:400_000], "lxml")
    candidates = [
        _meta(soup, "name", "description"),
        _meta(soup, "property", "og:description"),
        _meta(soup, "name", "twitter:description"),
    ]
    for value in candidates:
        if len(value) >= 50 and value.lower() != title.lower():
            return value[:limit].rstrip()

    for selector in ("article", ".news-detail", ".detail_text", ".detail-text", ".content", "main"):
        node = soup.select_one(selector)
        if not node:
            continue
        for junk in node.select("script,style,nav,footer,form,button,.breadcrumb,.breadcrumbs"):
            junk.decompose()
        text = _clean(node.get_text(" ", strip=True))
        if title and text.lower().startswith(title.lower()):
            text = text[len(title):].lstrip(" .:-")
        if len(text) >= 80:
            if len(text) > limit:
                cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-")
                text = (cut or text[:limit]).rstrip() + "…"
            return text
    return ""


def backfill_missing_summaries(items: list[dict[str, Any]], limit: int = 36) -> int:
    """Fill missing summaries for the newest items using their public article pages."""
    filled = 0
    checked = 0

    for item in items:
        if checked >= limit:
            break
        if _clean(item.get("summary")):
            continue

        url = str(
            item.get("canonical_url")
            or item.get("url")
            or item.get("link")
            or ""
        ).strip()
        if not url.startswith(("http://", "https://")):
            continue

        checked += 1
        try:
            response = HTTP.get(url, timeout=(5, 10), allow_redirects=True)
            response.raise_for_status()
            if "html" not in str(response.headers.get("Content-Type", "")).lower():
                continue
            summary = extract_summary(response.text, str(item.get("title") or ""))
        except Exception:
            continue

        if not summary:
            continue

        item["summary"] = summary
        filled += 1

        # If a translated item had no summary before, the new source-language
        # text must go through the normal translation pass on this ingest run.
        if item.get("translation_status") == "ru" and not re.search(r"[А-Яа-яЁё]", summary):
            item.setdefault("original_summary", summary)
            item.pop("translation_status", None)

    return filled
