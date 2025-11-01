import re
import html
import feedparser # pyright: ignore[reportMissingImports]
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def _iso8601(dt_struct) -> str:
    if not dt_struct:
        return ""
    try:
        dt = datetime(*dt_struct[:6], tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""

def _video_id_from_link(link: str) -> Optional[str]:
    if not link:
        return None
    m = re.search(r"[?&]v=([A-Za-z0-9_\-]{6,})", link)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([A-Za-z0-9_\-]{6,})", link)
    if m:
        return m.group(1)
    return None

def _thumb_from_entry(entry: Any, fallback_id: Optional[str]) -> Optional[str]:
    try:
        if getattr(entry, "media_thumbnail", None):
            th = entry.media_thumbnail[0]
            if "url" in th:
                return th["url"]
        if getattr(entry, "media_content", None):
            for c in entry.media_content:
                if c.get("medium") == "image" and c.get("url"):
                    return c["url"]
    except Exception:
        pass
    if fallback_id:
        return f"https://img.youtube.com/vi/{fallback_id}/hqdefault.jpg"
    return None

def fetch_youtube(source: Dict) -> List[Dict]:
    """
    Берём YouTube только через RSS/Atom, без API.
    source:
      - {"url": "..."}  ИЛИ
      - {"channel_id": "...", "name": "..."}
    Возвращаем столько элементов, сколько реально отдаёт лента (обычно 15).
    """
    url = (source or {}).get("url")
    name = (source or {}).get("name") or ""
    ch = (source or {}).get("channel_id")

    if not url and ch:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch}"

    if not url:
        print(f"[YT-RSS] skip: empty url/channel_id for {name or 'channel'}")
        return []

    feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
    items: List[Dict] = []

    for e in feed.entries:  # без потолков с нашей стороны
        title = _clean(getattr(e, "title", ""))
        link = getattr(e, "link", "") or ""
        summary = _clean(getattr(e, "summary", "") or getattr(e, "description", ""))
        vid = _video_id_from_link(link)

        published = ""
        if getattr(e, "published_parsed", None):
            published = _iso8601(e.published_parsed)
        elif getattr(e, "updated_parsed", None):
            published = _iso8601(e.updated_parsed)

        thumb = _thumb_from_entry(e, vid)

        items.append({
            "id": vid or link or title,
            "title": title,
            "url": link,
            "summary": summary,
            "published_at": published,
            "source": {
                "name": name or "YouTube",
                "url": url,
            },
            "platform": "YouTube",
            "thumbnail": thumb,
        })

    print(f"[YT-RSS] parsed: {len(items)} items from {name or url}")
    return items
