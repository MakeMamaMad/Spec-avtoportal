# aggregator/pipeline/fullgrab.py
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from typing import Optional

import requests  # type: ignore
from bs4 import BeautifulSoup  # type: ignore
import trafilatura  # type: ignore

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Пер-источник оверрайды (дополняйте по мере необходимости)
SOURCE_OVERRIDES = {
    "grozovy.ru": {
        "content_selector": "article, .entry-content, .post-content, .single-content",
        "image_selector": "meta[property='og:image'], meta[name='twitter:image'], article img, .entry-content img, .post-content img, .single-content img",
    },
    "zr.ru": {  # «За рулём»
        "force_fetch_article": True,
        "content_selector": "article, .article__content, .content, .post-content",
        "image_selector": "meta[property='og:image'], meta[name='twitter:image'], article img, .article__content img, .content img",
    },
}

BAD_IMG_EXT = (".svg", ".ico")

@dataclass
class GrabResult:
    html: str              # очищенный HTML основного контента (абзацы)
    lead_image: Optional[str]  # первая нормальная картинка (если нашлась)

def _domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host

def _looks_like_img(url: str | None) -> bool:
    if not url:
        return False
    low = url.lower()
    if any(low.endswith(ext) for ext in BAD_IMG_EXT):
        return False
    return True  # допускаем webp/avif/resize-URL без расширений

def _abs(url: str | None, base: str) -> Optional[str]:
    if not url:
        return None
    try:
        return urljoin(base, url)
    except Exception:
        return url

def _first_image_generic(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    # 1) og/twitter/link rel=image_src
    metas = [
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("link", {"rel": "image_src"}),
    ]
    for tag, attrs in metas:
        el = soup.find(tag, attrs=attrs)
        if el:
            cand = el.get("content") or el.get("href")
            cand = _abs(cand, base_url)
            if _looks_like_img(cand):
                return cand

    # 2) первый <img> (учитываем srcset/data-src)
    img = soup.find("img")
    if img:
        cand = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
        if not cand and img.get("srcset"):
            # берём первый URL из srcset
            cand = img.get("srcset").split(",")[0].split()[0]
        cand = _abs(cand, base_url)
        if _looks_like_img(cand):
            return cand

    return None

def _best_image_by_selector(soup: BeautifulSoup, base_url: str, selector: str) -> Optional[str]:
    for node in soup.select(selector):
        cand = node.get("src") or node.get("data-src") or node.get("data-original") or node.get("data-lazy-src") or node.get("content") or node.get("href")
        if not cand and node.get("srcset"):
            cand = node.get("srcset").split(",")[0].split()[0]
        cand = _abs(cand, base_url)
        if _looks_like_img(cand):
            return cand
    return None

def _sanitize_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    # убираем скрипты/стили
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    # лишние пустые теги
    for tag in soup.find_all():
        if tag.name in ("picture", "source"):
            tag.decompose()
    # нормализуем абзацы/разрывы
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # обратно — в простой HTML с <p>
    parts = [f"<p>{p}</p>" for p in [x.strip() for x in text.split("\n\n")] if p.strip()]
    return "\n".join(parts)

def grab(url: str) -> Optional[GrabResult]:
    """
    Скачиваем страницу статьи и достаём:
      - очищённый HTML (абзацы в <p>)
      - ведущую картинку
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        r.raise_for_status()
        final_url = r.url
        html = r.text

        # Текст: пробуем trafilatura как основной экстрактор
        # (подсовываем уже скачанный html)
        extracted = None
        try:
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_images=False,
                include_tables=False,
                url=final_url,
            )
        except Exception:
            extracted = None

        if not extracted:
            # фолбэк — вытащим основной контейнер по дефолтным селекторам
            soup = BeautifulSoup(html, "lxml")
            content = None
            dom = _domain(final_url)
            over = SOURCE_OVERRIDES.get(dom, {})
            sel = over.get("content_selector") or "article, .article, .post, .post-content, .entry-content, .content"
            node = soup.select_one(sel)
            content = node.decode() if node else soup.body.decode() if soup.body else html
            html_content = _sanitize_html(content)
        else:
            html_content = _sanitize_html(extracted)

        # Ведущая картинка
        soup2 = BeautifulSoup(html, "lxml")
        dom = _domain(final_url)
        over = SOURCE_OVERRIDES.get(dom, {})
        img = None
        if "image_selector" in over:
            img = _best_image_by_selector(soup2, final_url, over["image_selector"])
        if not img:
            img = _first_image_generic(soup2, final_url)

        return GrabResult(html=html_content, lead_image=img)
    except Exception:
        return None
