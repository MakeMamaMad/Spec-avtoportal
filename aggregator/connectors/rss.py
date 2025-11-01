import feedparser
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from datetime import datetime, timezone
from typing import Any, Tuple, List, Dict
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

TRACK_PARAMS_PREFIXES = (
    "utm_", "ga_", "gclid", "yclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src"
)
DEFAULT_PORTS = {"http": "80", "https": "443"}

def _source_to_tuple(source: Any) -> Tuple[str, str]:
    """Принимаем либо dict {'name','url'}, либо строку URL. Возвращаем (name, url)."""
    if isinstance(source, dict):
        return str(source.get("name") or "RSS").strip(), str(source.get("url") or "").strip()
    return "RSS", str(source or "").strip()

def _canonical_url(raw: str) -> str:
    """
    Приводим ссылку к стабильной форме:
    - схему/хост к нижнему регистру
    - выкидываем трекинг-параметры (utm_*, gclid, yclid, fbclid, ref, ...)
    - сортируем query, убираем пустые
    - убираем дефолтные порты (:80, :443)
    - убираем конечный '/'
    """
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        scheme = (parts.scheme or "https").lower()
        netloc = (parts.netloc or "").lower()

        # убрать default ports
        if ":" in netloc:
            host, port = netloc.split(":", 1)
            if port == DEFAULT_PORTS.get(scheme):
                netloc = host

        # чистка query
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=False):
            lk = k.lower()
            # вырезаем трекинг
            if lk.startswith(TRACK_PARAMS_PREFIXES) or lk in TRACK_PARAMS_PREFIXES:
                continue
            q.append((k, v))
        q.sort(key=lambda kv: kv[0])
        query = urlencode(q, doseq=True)

        # path без завершающего '/'
        path = parts.path or ""
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        canon = urlunsplit((scheme, netloc, path, query, ""))

        # унификация www → без www (чтобы http://www.site и https://site не плодили дубли)
        if canon.startswith("http://www."):
            canon = "http://" + canon[11:]
        elif canon.startswith("https://www."):
            canon = "https://" + canon[12:]

        return canon
    except Exception:
        return raw.strip()

def _entry_date(e) -> str:
    try:
        if getattr(e, "published_parsed", None):
            return datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        if getattr(e, "updated_parsed", None):
            return datetime(*e.updated_parsed[:6], tzinfo=timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()

def _clean_text(html_str: str) -> str:
    if not html_str:
        return ""
    return BeautifulSoup(html_str, "html.parser").get_text(" ", strip=True)

def _to_paragraphs(html_str: str) -> str:
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")
    ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    if ps:
        return "".join(f"<p>{p}</p>" for p in ps if p)
    text = soup.get_text("\n", strip=True)
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in parts)

def fetch_rss(source: Any) -> List[Dict]:
    """
    Сохраняем старое имя/контракт. Принимаем dict {'name','url'} ИЛИ строку URL.
    Возвращаем список новостей (list[dict]).
    """
    name, url = _source_to_tuple(source)
    if not url:
        print(f"[WARN] RSS skip {name}: empty url")
        return []

    print(f"[INFO] RSS load: {name} ({url})")
    feed = feedparser.parse(url)
    entries = getattr(feed, "entries", [])
    if not isinstance(entries, list):
        print(f"[WARN] RSS entries is not list for {url}")
        return []

    items: List[Dict] = []
    for e in entries:
        try:
            raw_link = (e.get("link") or e.get("id") or "").strip()
            title = (e.get("title") or "").strip()
            if not raw_link or not title:
                continue

            link = _canonical_url(raw_link)

            raw_html = (
                e.get("content")[0].value if e.get("content") else
                e.get("summary") or
                e.get("description") or
                ""
            )
            summary = _clean_text(raw_html)
            if len(summary) > 600:
                summary = summary[:600].rstrip() + "…"

            # media:* миниатюра (если есть)
            image = None
            mthumb = e.get("media_thumbnail")
            if isinstance(mthumb, list) and mthumb:
                image = mthumb[0].get("url")
            if not image:
                mcont = e.get("media_content")
                if isinstance(mcont, list) and mcont:
                    image = mcont[0].get("url")

            item = {
                "id": slugify(link)[:32],  # id по каноническому URL
                "title": title,
                "url": link,
                "summary": summary,
                "published_at": _entry_date(e),
                "source": {"name": name, "url": url},
            }
            if image:
                item["image"] = image

            content_html = _to_paragraphs(raw_html)
            if content_html:
                item["content_html"] = content_html

            items.append(item)

        except Exception as ex:
            print(f"[ERROR] RSS entry fail in {url}: {ex}")

    print(f"[INFO] RSS parsed: {len(items)} items from {name}")
    return items
