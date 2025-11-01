# aggregator/main.py
# -*- coding: utf-8 -*-
import json
import time
import yaml # type: ignore
import feedparser # type: ignore
import requests # type: ignore
from bs4 import BeautifulSoup # type: ignore
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import Counter
import re
from urllib.parse import urlparse, urljoin

# ---------- настройки ----------
UA = "Mozilla/5.0 (compatible; SpecAvtoNews/1.0; +https://example.com)"
REQ_TIMEOUT = 8               # таймаут HTTP при догрузке статьи
DAYS_BACK = 30                # сколько дней берём в ленту
GLOBAL_LIMIT = 500            # общий лимит новостей
PER_FEED_LIMIT = 120          # лимит на один RSS

# Разрешённые домены, для которых можно аккуратно догружать текст/картинку со страницы
ALLOWED_SCRAPE = {
    "tass.ru", "motor.ru", "drom.ru", "vedomosti.ru", "logirus.ru"
}
def _pick_from_srcset(srcset: str) -> str | None:
    """
    Берём самый «крупный» URL из srcset вида "a.jpg 320w, b.jpg 640w, c.jpg 1280w".
    """
    try:
        best = None
        best_w = -1
        for part in srcset.split(','):
            url_w = part.strip().split()
            if not url_w:
                continue
            url = url_w[0].strip()
            w = -1
            if len(url_w) > 1 and url_w[1].endswith('w'):
                try:
                    w = int(re.sub(r'\D', '', url_w[1]))
                except Exception:
                    w = -1
            if w > best_w:
                best = url
                best_w = w
        return best
    except Exception:
        return None

def _img_src_from_tag(img) -> str | None:
    """
    Достаём лучший src из <img>.
    """
    if not img:
        return None
    for attr in ("src", "data-src", "data-original", "data-lazy-src"):
        val = img.get(attr)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    # srcset (возьмём самый большой)
    srcset = img.get("srcset")
    if srcset:
        best = _pick_from_srcset(srcset)
        if best:
            return best.strip()
    return None

def _looks_tiny(url: str) -> bool:
    """
    Отсекаем явные «иконки/пиксели» по шаблонам im=1x1, 16x16, sprite и т.п.
    (грубая эвристика).
    """
    lower = url.lower()
    if any(x in lower for x in ("/sprite", "icon", "logo", "1x1", "pixel")):
        return True
    if re.search(r'(\b|_)(16|24|32|40|48|64)x\1?\d{1,3}', lower):
        return True
    return False


# ---------- утилиты ввода/вывода ----------
def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

# ---------- даты ----------
def _best_time(entry) -> datetime:
    # приоритет: parsed поля → текстовые поля → сейчас
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    for key in ("published", "updated", "created"):
        txt = entry.get(key)
        if txt:
            try:
                t = feedparser._parse_date(txt)
                if t:
                    return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
            except Exception:
                pass
    return datetime.now(tz=timezone.utc)

# ---------- загрузка RSS ----------
def fetch_feed(url: str):
    parsed = feedparser.parse(url, request_headers={"User-Agent": UA})
    if parsed.bozo and getattr(parsed, "bozo_exception", None):
        print(f"[WARN] {url} bozo={parsed.bozo} err={parsed.bozo_exception}")
    return (parsed.entries or [])[:PER_FEED_LIMIT]

# ---------- догрузка со страницы ----------
def fetch_page(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=REQ_TIMEOUT)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

def extract_content_from_html(html: str, page_url: str) -> tuple[str | None, str | None]:
    """
    Возвращает (image_url, content_html):
      - image_url: приоритетно og:image/og:image:secure_url/twitter:image,
                   затем первая крупная <img> из основного контента.
      - content_html: 2–4 осмысленных абзаца <p> из основной области статьи.
    """
    soup = BeautifulSoup(html, "lxml")

    # 1) Метаданные с картинкой
    img_candidates = []
    for sel in [
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "og:image"}),
        ("meta", {"property": "og:image:secure_url"}),
        ("meta", {"name": "og:image:secure_url"}),
        ("meta", {"property": "twitter:image"}),
        ("meta", {"name": "twitter:image"}),
    ]:
        m = soup.find(*sel)
        if m and m.get("content"):
            img_candidates.append(m["content"].strip())

    def absolutize(u: str | None) -> str | None:
        if not u:
            return None
        try:
            return urljoin(page_url, u)
        except Exception:
            return u

    # 2) Поиск контейнера статьи
    candidates = []
    selectors = [
        "article", "[role=article]", ".article", ".article__content",
        ".news-item", ".news", ".content", "#content", ".post",
        ".post-content", ".entry-content", ".story", ".page-content"
    ]
    for sel in selectors:
        for el in soup.select(sel):
            text_len = len(el.get_text(" ", strip=True))
            if text_len > 200:
                candidates.append((text_len, el))
    target = max(candidates, default=(0, None))[1] if candidates else soup.body

    # 3) Основной текст (берём 2–4 абзаца)
    content_html = None
    first_img_url = None
    if target:
        ps = [p for p in target.find_all("p") if len(p.get_text(strip=True)) > 40]
        if ps:
            chunk = ps[:4]
            for p in chunk:
                for bad in p.select("script, style, noscript, iframe"):
                    bad.decompose()
            content_html = "".join(str(p) for p in chunk)

        # попробуем найти первую подходящую картинку внутри основного блока
        for img in target.find_all("img"):
            cand = _img_src_from_tag(img)
            if not cand:
                continue
            cand = absolutize(cand)
            if not cand or _looks_tiny(cand):
                continue
            first_img_url = cand
            break

    # 4) Выбор итоговой картинки: приоритет meta → контентная img
    image_url = None
    for c in img_candidates:
        u = absolutize(c)
        if u and not _looks_tiny(u):
            image_url = u
            break
    if not image_url and first_img_url:
        image_url = first_img_url

    return image_url, content_html


# ---------- нормализация записи ----------
def norm_entry(entry, source_name: str) -> dict:
    link = (entry.get("link") or "").strip()
    title = (entry.get("title") or "").strip() or "(без заголовка)"
    summary = (entry.get("summary") or entry.get("description") or "").strip()

    dt = _best_time(entry)

    # из RSS
    image = None
    media = entry.get("media_content") or entry.get("media_thumbnail") or []
    if media:
        image = media[0].get("url")
    if not image:
        enclosures = entry.get("enclosures") or []
        if enclosures:
            image = enclosures[0].get("href")

    # content_html из RSS
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

    # --- ДОГРУЗКА СО СТРАНИЦЫ (фикс области видимости html) ---
    html = None
    if domain in ALLOWED_SCRAPE and link:
        try:
            html = fetch_page(link)
        except Exception:
            html = None
        if html:
            try:
                img_from_page, content_from_page = extract_content_from_html(html, link)
                if (not content_html) and content_from_page and len(content_from_page) > 120:
                    content_html = content_from_page
                if (not image) and img_from_page:
                    image = img_from_page
            except Exception:
                pass
    # --- конец догрузки ---

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


# ---------- дедупликация ----------
def dedupe(items: list) -> list:
    seen_links = set()
    seen_title_domain = set()
    out = []
    for it in items:
        link = (it.get("link") or "").strip().lower()
        key2 = ((it.get("domain") or "").lower(), (it.get("title") or "").strip().lower())
        if link and link not in seen_links:
            seen_links.add(link)
            out.append(it)
        elif key2 not in seen_title_domain:
            seen_title_domain.add(key2)
            out.append(it)
    return out

# ---------- агрегация ----------
def aggregate(sources: list) -> list:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
    bucket = []
    for src in sources:
        name = src.get("name") or "unknown"
        url = src.get("url")
        if not url:
            print(f"[SKIP] {name}: empty url")
            continue
        try:
            entries = fetch_feed(url)
            normalized = [norm_entry(e, name) for e in entries]
            bucket.extend(normalized)
            print(f"[OK] {name}: +{len(normalized)}")
        except Exception as e:
            print(f"[ERR] {name}: {e}")

    # сортировка → дата-фильтр → дедуп → лимит
    bucket.sort(key=lambda x: x["published_at"], reverse=True)
    fresh = [x for x in bucket if datetime.fromisoformat(x["published_at"]) >= cutoff]
    fresh = dedupe(fresh)[:GLOBAL_LIMIT]
    return fresh

def debug_stats(items: list) -> None:
    c = Counter([x.get("domain") for x in items if x.get("domain")])
    print("[STATS] by domain:", dict(c.most_common(20)))

# ---------- точка входа ----------
def main():
    here = Path(__file__).resolve().parent
    root = here.parent
    cfg_path = here / "sources.yml"
    out_news = root / "frontend" / "data" / "news.json"
    out_meta = root / "frontend" / "data" / "news_meta.json"

    cfg = load_yaml(cfg_path)
    sources = cfg.get("sources") or cfg.get("feeds")
    if not sources:
        raise RuntimeError(f"В {cfg_path} нет ключа 'sources' или 'feeds'")

    items = aggregate(sources)
    debug_stats(items)

    write_json(out_news, items)
    meta = {"updated_at": datetime.now(tz=timezone.utc).isoformat(), "count": len(items)}
    write_json(out_meta, meta)

    print(f"[DONE] saved {len(items)} items to {out_news}")
    print(f"[DONE] meta -> {out_meta}")

if __name__ == "__main__":
    main()
