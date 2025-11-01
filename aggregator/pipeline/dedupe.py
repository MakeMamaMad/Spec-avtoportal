from __future__ import annotations
from typing import List, Dict, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from datetime import datetime, timedelta

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

def dedupe(items: List[Dict]) -> List[Dict]:
    """
    1) Удаляем полные дубли по каноническому URL.
    2) Удаляем «почти дубли»: одинаковый title на том же домене в пределах 72 часов.
    Порядок сохраняем (первый встреченный — главный).
    """
    out: List[Dict] = []
    seen_urls: set[str] = set()
    seen_title_host_time: set[Tuple[str, str, int]] = set()  # (title_norm, host, timebucket)

    for it in items:
        if not it:
            continue

        url = _canonical_url(it.get("url") or "")
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)

        title_norm = (it.get("title") or "").strip().lower()
        host = _host(url or (it.get("url") or ""))
        dt = _parse_dt(it.get("published_at") or "") or _parse_dt(it.get("updated_at") or "")
        # округляем до 72-часовых бакетов (3 суток)
        bucket = int((dt or datetime.min).timestamp() // (72 * 3600))
        k = (title_norm, host, bucket)

        if title_norm and host:
            if k in seen_title_host_time:
                # почти дубль
                continue
            seen_title_host_time.add(k)

        out.append(it)

    return out
