# aggregator/connectors/rss.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import feedparser  # type: ignore
import requests    # type: ignore
from bs4 import BeautifulSoup  # type: ignore
from slugify import slugify    # type: ignore

from aggregator.pipeline.fullgrab import grab  # <-- важно

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
DEFAULT_PORTS = {"http": "80", "https": "443"}
TRACK_PARAMS_PREFIXES = ("utm_", "ga_", "gclid", "yclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src")

def _normalize_url(raw: str) -> str:
    """Обрезаем трекинг, дефолтные порты, конечный слэш; задаём https по умолчанию."""
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = (parts.netloc or "").lower()

    # Убираем default ports
    if ":" in netloc:
        host, port = netloc.split(":", 1)
        if port == DEFAULT_PORTS.get(scheme):
            netloc = host

    # Чистим трекинг
    q = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if any(k.lower().startswith(pref) for pref in TRACK_PARAMS_PREFIXES):
            continue
        q.append((k, v))
    query = urlencode(q, doseq=True)

    path = parts.path or "/"
    if path.endswith("/") and path != "/":
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, query, ""))

def _rss_content_encoded(entry: Any) -> str | None:
    # feedparser может класть <content:encoded> по-разному
    if "content" in entry and isinstance(entry["content"], list) and entry["content"]:
        first = entry["content"][0]
        if isinstance(first, dict) and first.get("type", "").startswith("text"):
            return first.get("value")
    # иногда лежит как отдельное поле
    for key in ("content:encoded", "encoded", "summary_detail"):
        if key in entry:
            val = entry[key]
            if isinstance(val, dict):
                return val.get("value")
            if isinstance(val, str):
                return val
    return None

def _summary_text(entry: Any) -> str:
    s = entry.get("summary") or entry.get("description") or ""
    return s

def _first_image_from_html(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    # meta og/twitter
    for tag, attrs in [("meta", {"property": "og:image"}), ("meta", {"name": "twitter:image"}), ("link", {"rel": "image_src"})]:
        el = soup.find(tag, attrs=attrs)
        if el:
            src = el.get("content") or el.get("href")
            if src:
                return src
    # первый <img> с учётом srcset/data-src
    img = soup.find("img")
    if img:
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        if not src and img.get("srcset"):
            src = img.get("srcset").split(",")[0].split()[0]
        return src
    return None

def fetch_rss(name: str, url: str) -> List[Dict[str, Any]]:
    """
    Скачиваем RSS/Atom, нормализуем поля, вытаскиваем полноценный контент:
      - если в RSS есть content:encoded и он «длинный» — используем его
      - иначе идём на страницу статей (fullgrab.grab)
    """
    headers = {"User-Agent": USER_AGENT}
    d = feedparser.parse(requests.get(url, headers=headers, timeout=20).content)

    items: List[Dict[str, Any]] = []
    for raw in d.entries:
        try:
            link = _normalize_url(raw.get("link", ""))

            # Базовые поля
            title = (raw.get("title") or "").strip()
            published = raw.get("published_parsed") or raw.get("updated_parsed") or None
            dt = datetime(*published[:6], tzinfo=timezone.utc).isoformat() if published else None
            guid = raw.get("id") or raw.get("guid") or link or title
            slug = slugify(f"{name}-{guid}")[:80]

            # HTML из RSS: content:encoded > summary
            html_from_rss = _rss_content_encoded(raw) or _summary_text(raw)
            prefer_full = isinstance(html_from_rss, str) and len(html_from_rss) > 500 and "<p" in html_from_rss.lower()

            # Попытка получить сразу картинку из RSS-HTML (быстрее)
            img_from_rss = _first_image_from_html(html_from_rss or "", link)

            # Если нет «полного» контента — идём на страницу
            if not prefer_full:
                grabbed = grab(link)
                content_html = (grabbed.html if grabbed else None) or html_from_rss or ""
                image = (grabbed.lead_image if grabbed else None) or img_from_rss
            else:
                content_html = html_from_rss or ""
                image = img_from_rss
                # если картинка не нашлась — всё равно пробуем страницу (только за картинкой)
                if not image:
                    grabbed = grab(link)
                    image = grabbed.lead_image if grabbed else None

            item: Dict[str, Any] = {
                "source": name,
                "slug": slug,
                "title": title,
                "link": link,
                "published_at": dt,
                "content_html": content_html,
            }
            if image:
                item["image"] = image

            items.append(item)
        except Exception as ex:
            print(f"[ERROR] RSS entry fail in {url}: {ex}")

    print(f"[INFO] RSS parsed: {len(items)} items from {name}")
    return items
