# aggregator/main.py
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse, urljoin

import feedparser  # type: ignore
import requests    # type: ignore
import yaml        # type: ignore
from bs4 import BeautifulSoup  # type: ignore

# --------- настройки ----------
DAYS_BACK = 120          # окно по времени для свежей выборки
PER_FEED_LIMIT = 300     # максимум элементов с одного источника
GLOBAL_LIMIT = 5000      # общий срез свежих после объединения
ARCHIVE_LIMIT = 5000     # сколько храним в news.json после слияния
TIMEOUT = 15

# базовые домены; субдомены разрешаем автоматически (news.drom.ru, m.tass.ru и т.п.)
ALLOWED_SCRAPE = {
    "tass.ru", "motor.ru", "drom.ru", "vedomosti.ru", "logirus.ru"
}

# --------- утилиты ввода/вывода ----------
def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_existing_news(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

# --------- сетевые утилиты ----------
def fetch_rss(url: str) -> feedparser.FeedParserDict:
    return feedparser.parse(url)

def fetch_page(url: str) -> str:
    r = requests.get(url, timeout=TIMEOUT, headers={
        "User-Agent": "Mozilla/5.0 (Aggregator; +https://example.local)"
    })
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def host_allowed(url_or_host: str) -> bool:
    """разрешить как точный домен, так и *.домен из ALLOWED_SCRAPE"""
    host = url_or_host
    if "://" in url_or_host:
        host = urlparse(url_or_host).netloc
    host = (host or "").lower()
    return any(host == d or host.endswith("." + d) for d in ALLOWED_SCRAPE)

# --------- парсинг HTML для картинки/контента ----------
def extract_content_from_html(html: str, page_url: str) -> Tuple[str | None, str | None]:
    """
    Возвращает (image_url, content_text), если удалось найти.
    Ищем og:image / twitter:image / link[rel=image_src] / первый <img> (в т.ч. data-src).
    Текст: meta description или первые 1–2 абзаца.
    """
    soup = BeautifulSoup(html, "lxml")

    def _abs(u: str | None) -> str | None:
        if not u:
            return None
        return urljoin(page_url, u.strip())

    # 1) meta-изображения
    image = None
    meta_candidates = [
        ("meta", {"property": "og:image"}),
        ("meta", {"property": "og:image:secure_url"}),
        ("meta", {"name": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"name": "twitter:image:src"}),
    ]
    for tag, attrs in meta_candidates:
        node = soup.find(tag, attrs=attrs)
        if node and node.get("content"):
            image = _abs(node.get("content"))
            if image:
                break

    # 2) <link rel="image_src">
    if not image:
        link_img = soup.find("link", rel=lambda v: v and "image_src" in v)
        if link_img and link_img.get("href"):
            image = _abs(link_img["href"])

    # 3) первый валидный <img> (учитываем ленивые атрибуты)
    if not image:
        for img in soup.find_all("img"):
            src = (img.get("src") or img.get("data-src") or
                   img.get("data-original") or img.get("data-lazy-src"))
            if not src:
                continue
            src = _abs(src)
            if src and not src.startswith("data:") and not src.endswith(".svg"):
                image = src
                break

    # Текст
    text = None
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        text = desc["content"].strip()
    if not text:
        ps = [p.get_text(" ", strip=True) for p in soup.select("p")]
        text = " ".join(ps[:2]).strip() if ps else None

    if text:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            text = None

    return image, text

# --------- нормализация и дедуп ----------
def _best_time(entry: dict) -> datetime:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(tz=timezone.utc)

def norm_entry(entry: dict, source_name: str) -> dict:
    link = (entry.get("link") or "").strip()
    title = (entry.get("title") or "").strip() or "(без заголовка)"
    summary = (entry.get("summary") or entry.get("description") or "").strip()
    dt = _best_time(entry)

    # изображения из RSS
    image = None
    media = entry.get("media_content") or entry.get("media_thumbnail") or []
    if media and isinstance(media, list) and media[0].get("url"):
        image = media[0]["url"]
    if not image:
        enclosures = entry.get("enclosures") or []
        if enclosures and isinstance(enclosures, list) and enclosures[0].get("href"):
            image = enclosures[0]["href"]

    # возможный HTML-контент из RSS
    content_html = None
    try:
        content_list = entry.get("content") or []
        if content_list and isinstance(content_list, list):
            val = content_list[0].get("value")
            if val and len(val) > 120:
                content_html = val.strip()
    except Exception:
        pass
    if not content_html:
        sd = entry.get("summary_detail") or {}
        if str(sd.get("type", "")).startswith("text/html") and sd.get("value"):
            v = sd["value"].strip()
            if len(v) > 120:
                content_html = v

    domain = urlparse(link).netloc or ""

    # Догрузка со страницы (с учётом субдоменов)
    if link and host_allowed(domain):
        try:
            html = fetch_page(link)
            img_from_page, content_from_page = extract_content_from_html(html, link)
            if (not content_html) and content_from_page and len(content_from_page) > 120:
                content_html = content_from_page
            if (not image) and img_from_page:
                image = img_from_page
        except Exception:
            pass

    return {
        "source": source_name,
        "title": title,
        "link": link,
        "summary": summary,
        "content_html": content_html,
        "image": image,
        "published_at": dt.isoformat(),
        "domain": domain,
    }

def dedupe(items: List[dict]) -> List[dict]:
    """Дедуп приоритетно по link, иначе по (title.lower(), domain)."""
    seen_link = set()
    seen_title = set()
    out: List[dict] = []
    for it in items:
        link = (it.get("link") or "").strip()
        key2 = ((it.get("title") or "").strip().lower(), it.get("domain") or "")
        if link and link in seen_link:
            continue
        if not link and key2 in seen_title:
            continue
        out.append(it)
        if link:
            seen_link.add(link)
        else:
            seen_title.add(key2)
    return out

def merge_and_trim(existing: list[dict], fresh: list[dict], limit: int) -> list[dict]:
    """Объединяем архив со свежим, дедупим и сортируем по дате."""
    all_items = fresh + existing
    all_items = dedupe(all_items)
    all_items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return all_items[:limit]

# --------- сборка из sources.yml ----------
def aggregate(sources_cfg: List[dict]) -> List[dict]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
    collected: List[dict] = []

    for s in sources_cfg:
        name = s.get("name") or s.get("title") or "Источник"
        url = s.get("url") or s.get("link")
        if not url:
            continue
        try:
            feed = fetch_rss(url)
            entries = feed.entries or []
            batch: List[dict] = []
            for e in entries[:PER_FEED_LIMIT]:
                it = norm_entry(e, name)
                try:
                    dt = datetime.fromisoformat(it["published_at"])
                except Exception:
                    dt = datetime.now(tz=timezone.utc)
                if dt < since:
                    continue
                batch.append(it)
            collected.extend(batch)
            print(f"[OK] {name}: +{len(batch)}")
        except Exception as ex:
            print(f"[ERR] {name}: {ex}")

    collected = dedupe(collected)
    collected.sort(key=lambda x: x.get("published_at", ""), reverse=True)

    if GLOBAL_LIMIT and len(collected) > GLOBAL_LIMIT:
        collected = collected[:GLOBAL_LIMIT]

    return collected

def debug_stats(items: List[dict]) -> None:
    by_domain: Dict[str, int] = {}
    for it in items:
        d = it.get("domain") or ""
        by_domain[d] = by_domain.get(d, 0) + 1
    top = sorted(by_domain.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print("[STATS] total:", len(items), "| top domains:", ", ".join(f"{d}:{n}" for d, n in top))

# --------- main ----------
def main() -> None:
    here = Path(__file__).resolve().parent
    root = here.parent

    out_news = root / "frontend" / "data" / "news.json"
    out_meta = root / "frontend" / "data" / "news_meta.json"

    cfg = load_yaml(here / "sources.yml")
    sources = cfg.get("sources", [])

    print(f"[RUN] sources: {len(sources)}")
    fresh = aggregate(sources)
    print(f"[INFO] fresh after aggregate: {len(fresh)}")

    existing = load_existing_news(out_news)
    print(f"[INFO] existing in file: {len(existing)}")

    items = merge_and_trim(existing, fresh, ARCHIVE_LIMIT)
    print(f"[INFO] merged total (<= {ARCHIVE_LIMIT}): {len(items)}")

    debug_stats(items)

    write_json(out_news, items)
    meta = {"updated_at": datetime.now(tz=timezone.utc).isoformat(), "count": len(items)}
    write_json(out_meta, meta)

    print(f"[DONE] saved {len(items)} items -> {out_news}")
    print(f"[DONE] meta  -> {out_meta}  updated_at={meta['updated_at']}")

# --------- точка входа ----------
if __name__ == "__main__":
    import sys, os, traceback
    try:
        print("[BOOT] starting aggregator")
        print("[BOOT] python:", sys.version)
        print("[BOOT] exe   :", sys.executable)
        print("[BOOT] cwd   :", os.getcwd())
        main()
        print("[BOOT] done")
    except Exception as e:
        print("[ERR] unhandled:", e)
        traceback.print_exc()
        raise
