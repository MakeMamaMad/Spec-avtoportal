from __future__ import annotations
from typing import List, Dict, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from datetime import datetime, timedelta
import re

TRACK_PARAMS_PREFIXES = (
    "utm_", "ga_", "gclid", "yclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src"
)
DEFAULT_PORTS = {"http": "80", "https": "443"}

def _canonical_url(raw: str) -> str:
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        scheme = (parts.scheme or "https").lower()
        netloc = (parts.netloc or "").lower()
        if ":" in netloc:
            host, port = netloc.split(":", 1)
            if port == DEFAULT_PORTS.get(scheme):
                netloc = host
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=False):
            lk = k.lower()
            if lk.startswith(TRACK_PARAMS_PREFIXES) or lk in TRACK_PARAMS_PREFIXES:
                continue
            q.append((k, v))
        q.sort(key=lambda kv: kv[0])
        query = urlencode(q, doseq=True)

        path = parts.path or ""
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        canon = urlunsplit((scheme, netloc, path, query, ""))
        if canon.startswith("http://www."):
            canon = "http://" + canon[11:]
        elif canon.startswith("https://www."):
            canon = "https://" + canon[12:]
        return canon
    except Exception:
        return raw.strip()

def _host(url: str) -> str:
    try:
        return (urlsplit(url).netloc or "").lower().lstrip("www.")
    except Exception:
        return ""

def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

_TITLE_STOPWORDS = {
    "и", "в", "во", "на", "по", "для", "с", "со", "о", "об", "от", "до",
    "the", "a", "an", "of", "for", "to", "in", "on", "with", "and",
}


def _title_tokens(title: str) -> set[str]:
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9-]+", (title or "").lower())
    return {
        word for word in words
        if len(word) >= 3 and word not in _TITLE_STOPWORDS
    }


def _same_event_title(left: str, right: str) -> bool:
    """Conservative cross-source event match for near-identical headlines."""
    a = _title_tokens(left)
    b = _title_tokens(right)
    if len(a) < 5 or len(b) < 5:
        return False
    overlap = len(a & b) / max(1, len(a | b))
    containment = len(a & b) / max(1, min(len(a), len(b)))
    return overlap >= 0.72 or containment >= 0.86


def dedupe(items: List[Dict]) -> List[Dict]:
    """
    1) Remove exact duplicates by canonical source URL.
    2) Remove same-domain duplicate headlines within a 72-hour bucket.
    3) Collapse highly similar headlines from different sources when they describe
       the same event within 72 hours.

    The first item is retained so upstream source priority/order remains stable.
    """
    out: List[Dict] = []
    seen_urls: set[str] = set()
    seen_title_host_time: set[Tuple[str, str, int]] = set()
    recent_titles: list[tuple[str, str, datetime | None]] = []

    for it in items:
        if not it:
            continue

        raw_url = it.get("canonical_url") or it.get("url") or it.get("link") or ""
        url = _canonical_url(raw_url)
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)

        title_norm = (it.get("title") or "").strip().lower()
        host = _host(url or raw_url)
        dt = _parse_dt(it.get("published_at") or "") or _parse_dt(it.get("updated_at") or "")
        bucket = int((dt or datetime.min).timestamp() // (72 * 3600))
        k = (title_norm, host, bucket)

        if title_norm and host:
            if k in seen_title_host_time:
                continue
            seen_title_host_time.add(k)

        duplicate_event = False
        if title_norm:
            for previous_title, previous_host, previous_dt in recent_titles:
                if host and previous_host and host == previous_host:
                    continue
                if dt is not None and previous_dt is not None:
                    try:
                        if abs(dt - previous_dt) > timedelta(hours=72):
                            continue
                    except TypeError:
                        pass
                if _same_event_title(title_norm, previous_title):
                    duplicate_event = True
                    break
        if duplicate_event:
            continue

        recent_titles.append((title_norm, host, dt))
        if len(recent_titles) > 250:
            recent_titles = recent_titles[-250:]

        out.append(it)

    return out
