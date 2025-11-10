# aggregator/main.py
from __future__ import annotations
import json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests, feedparser, yaml  # pip install requests feedparser pyyaml

BLOCKED_DOMAINS = {"tass.ru", "www.tass.ru"}

# ... там где у вас формируется result / all_items
result = [it for it in result if it.get("domain") not in BLOCKED_DOMAINS]
VER = "safe-collector v2.1"

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "frontend" / "data"
NEWS_JSON = DATA_DIR / "news.json"
META_JSON = DATA_DIR / "news_meta.json"
CFG_PATH = ROOT / "aggregator" / "sources.yml"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": UA, "Accept": "*/*"})

def log(k: str, msg: str) -> None:
    print(f"[{k}] {msg}")

def load_cfg() -> Dict[str, Any]:
    with CFG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def fetch_rss(url: str):
    try:
        r = HTTP.get(url, timeout=(10, 20))
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        log("ERR", f"fetch {url}: {e.__class__.__name__}: {e}")
        return None

def to_iso(dt_struct) -> Optional[str]:
    if not dt_struct:
        return None
    try:
        ts = time.mktime(dt_struct)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return None

def first_image(entry) -> Optional[str]:
    media = entry.get("media_content")
    if isinstance(media, list) and media:
        url = media[0].get("url")
        if url: return url
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and str(link.get("type","")).startswith(("image/","img/")):
            if link.get("href"): return link["href"]
    thumbs = entry.get("media_thumbnail")
    if isinstance(thumbs, list) and thumbs:
        url = thumbs[0].get("url")
        if url: return url
    if entry.get("image") and isinstance(entry["image"], dict):
        if entry["image"].get("href"): return entry["image"]["href"]
    return None

def normalize(entry, src_name: str) -> Dict[str, Any]:
    title = (entry.get("title") or "").strip() or "(без заголовка)"
    link = entry.get("link") or ""
    summary = (entry.get("summary") or "").strip()
    contents = entry.get("content") or []
    if not summary and isinstance(contents, list) and contents:
        summary = (contents[0].get("value") or "").strip()
    published = to_iso(entry.get("published_parsed")) or to_iso(entry.get("updated_parsed"))
    img = first_image(entry)
    domain = ""
    try:
        from urllib.parse import urlparse
        domain = urlparse(link).netloc
    except Exception:
        pass
    return {
        "source": src_name,
        "title": title,
        "link": link,
        "summary": summary,
        "image": img,
        "published_at": published,
        "domain": domain,
    }

def collect(sources_cfg: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for src in sources_cfg or []:
        name = src.get("name") or "source"
        url = src.get("url") or src.get("link") or ""
        if not url:
            log("ERR", f"{name}: empty url")
            continue
        fp = fetch_rss(url)
        entries = []
        if fp and getattr(fp, "entries", None):
            entries = list(fp.entries)  # гарантированно список
        else:
            log("ERR", f"{name}: entries empty")
        got = 0
        for e in entries:
            try:
                items.append(normalize(e, name))
                got += 1
            except Exception as ex:
                log("ERR", f"{name}: normalize error: {ex}")
        log("OK", f"{name}: +{got}")
    return items

def read_existing() -> List[Dict[str, Any]]:
    try:
        if NEWS_JSON.exists():
            return json.loads(NEWS_JSON.read_text("utf-8"))
    except Exception:
        pass
    return []

def dedup_by_link(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        key = it.get("link") or it.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def sort_by_date(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(it):
        val = it.get("published_at")
        try:
            return datetime.fromisoformat(val.replace("Z","+00:00")) if val else datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    return sorted(items, key=key, reverse=True)

def save(items: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_JSON.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
    META_JSON.write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "count": len(items)}, ensure_ascii=False, indent=2),
        "utf-8",
    )

def stats(items: List[Dict[str, Any]]) -> None:
    from collections import Counter
    c = Counter(it.get("domain") for it in items if it.get("domain"))
    if not c:
        log("STATS", "total: 0")
        return
    top_domain, top_count = c.most_common(1)[0]
    log("STATS", f"total: {len(items)} | top domains: {top_domain}:{top_count}")

def main() -> None:
    print("[BOOT] starting aggregator")
    print(f"[BOOT] version: {VER}")
    print(f"[BOOT] python: {sys.version.split()[0]}")
    print(f"[BOOT] cwd  = {ROOT}")
    cfg = load_cfg()
    sources = cfg.get("sources") or []
    print(f"[RUN] sources: {len(sources)}")
    fresh = collect(sources)
    log("INFO", f"fresh after aggregate: {len(fresh)}")
    existing = read_existing()
    log("INFO", f"existing in file: {len(existing)}")
    merged = dedup_by_link(fresh + existing)
    merged = sort_by_date(merged)
    if len(merged) > 5000:
        merged = merged[:5000]
    log("INFO", f"merged total (<= 5000): {len(merged)}")
    stats(merged)
    save(merged)
    log("DONE", f"saved {len(merged)} items -> {NEWS_JSON}")
    log("DONE", f"meta  -> {META_JSON}")
    print("[BOOT] done")

if __name__ == "__main__":
    main()

# >>> strip TASS
try:
    result = [it for it in result if (it or {}).get('domain') not in BLOCKED_DOMAINS]
except Exception:
    pass
