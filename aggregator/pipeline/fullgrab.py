# aggregator/pipeline/fullgrab.py
from __future__ import annotations
import os, re, time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
import requests # pyright: ignore[reportMissingModuleSource]
from bs4 import BeautifulSoup # type: ignore
import trafilatura # type: ignore

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

@dataclass
class GrabResult:
    html: str              # чистый HTML основного контента
    lead_image: str | None # первая картинка (если найдена)

def absolutize_urls(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    # ссылки
    for a in soup.select("a[href]"):
        a["href"] = urljoin(base_url, a.get("href"))
    # картинки
    for img in soup.select("img[src]"):
        img["src"] = urljoin(base_url, img.get("src"))
    return str(soup)

def sanitize(html: str) -> str:
    # оставляем безопасные теги и атрибуты
    soup = BeautifulSoup(html or "", "lxml")
    allowed_tags = {
        "p","a","strong","em","b","i","u","ul","ol","li","blockquote","figure","figcaption",
        "img","h2","h3","h4","h5","h6","table","thead","tbody","tr","td","th","br","hr","span"
    }
    allowed_attrs = {"a": ["href","title","rel","target"],
                     "img": ["src","alt","title","width","height","srcset","sizes"],
                     "*": ["class","id","style"]}

    for tag in list(soup.find_all(True)):
        if tag.name not in allowed_tags:
            tag.unwrap()
            continue
        # фильтр атрибутов
        attrs = dict(tag.attrs)
        tag.attrs = {}
        for k,v in attrs.items():
            if k in (allowed_attrs.get(tag.name, []) + allowed_attrs.get("*", [])):
                tag.attrs[k] = v
    return str(soup)

def extract_lead_image(soup: BeautifulSoup) -> str | None:
    # meta og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"): 
        return og["content"]
    # первая картинка в тексте
    img = soup.find("img", src=True)
    return img["src"] if img else None

def grab_full_html(url: str) -> GrabResult | None:
    try:
        # 1) качаем страницу
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text

        # 2) пытаемся вытащить основное содержимое
        downloaded = trafilatura.extract(html, include_links=True, include_tables=True, favor_recall=True,
                                         with_metadata=False, url=url, output_format="xml")  # «богатый» разбор
        if downloaded:
            # преобразуем обратно в HTML
            html_content = trafilatura.extract(html, include_links=True, include_tables=True, favor_recall=True,
                                               with_metadata=False, url=url, output_format="html")
        else:
            # запасной путь — просто <article> или <main>
            soup = BeautifulSoup(html, "lxml")
            node = soup.find("article") or soup.find("main") or soup.find("div", attrs={"itemprop":"articleBody"})
            html_content = str(node) if node else ""

        if not html_content:
            return None

        # 3) делаем ссылки/картинки абсолютными и слегка чистим
        html_content = absolutize_urls(html_content, url)
        html_content = sanitize(html_content)

        # 4) ведущая картинка
        soup2 = BeautifulSoup(html, "lxml")
        lead = extract_lead_image(soup2)
        if lead:
            from urllib.parse import urljoin
            lead = urljoin(url, lead)

        return GrabResult(html=html_content, lead_image=lead)
    except Exception:
        return None
