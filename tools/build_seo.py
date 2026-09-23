#!/usr/bin/env python3
"""Build SEO-ready static news pages for SpecAvtoPortal.

Default mode:
- assigns persistent id/slug values to items that do not have them;
- generates /frontend/news/<slug>/index.html;
- generates sitemap.xml and robots.txt.

With --metadata-only only id/slug values are written back to news.json.
The script uses only Python stdlib so it can run in GitHub Pages builds.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
NEWS_JSON = FRONTEND / "data" / "news.json"
NEWS_DIR = FRONTEND / "news"
TOPICS_DIR = FRONTEND / "topics"
BRANDS_DIR = FRONTEND / "brands"
BASE_URL = "https://spec-avtoportal.ru"

BRAND_RULES = [
    {
        "slug": "krone",
        "name": "KRONE",
        "description": "Новости и материалы о прицепной технике, разработках и проектах KRONE.",
        "patterns": (r"\bkrone\b",),
    },
    {
        "slug": "maz",
        "name": "МАЗ",
        "description": "Новости МАЗ: грузовая техника, новые модели, производство и отраслевые проекты.",
        "patterns": (r"(?<![а-яa-z0-9])маз(?![а-яa-z0-9])", r"\bmaz\b"),
    },
    {
        "slug": "kamaz",
        "name": "КАМАЗ",
        "description": "Новости КАМАЗ: грузовики, тягачи, производство, модели и технологии.",
        "patterns": (r"(?<![а-яa-z0-9])камаз(?![а-яa-z0-9])", r"\bkamaz\b"),
    },
    {
        "slug": "kogel",
        "name": "Kögel",
        "description": "Новости и материалы о полуприцепах, технологиях и проектах Kögel.",
        "patterns": (r"\bk[öo]gel\b",),
    },
    {
        "slug": "mercedes-benz-trucks",
        "name": "Mercedes-Benz Trucks",
        "description": "Новости Mercedes-Benz Trucks, грузовиков Actros и технологий коммерческого транспорта.",
        "patterns": (r"mercedes(?:-benz)?", r"\bactros\b"),
    },
    {
        "slug": "schmitz-cargobull",
        "name": "Schmitz Cargobull",
        "description": "Новости Schmitz Cargobull: полуприцепы, сервис, цифровые решения и производство.",
        "patterns": (r"\bschmitz\b", r"\bcargobull\b"),
    },
    {
        "slug": "saf-holland",
        "name": "SAF-Holland",
        "description": "Новости SAF-Holland: осевые системы, компоненты и технологии для прицепной техники.",
        "patterns": (r"saf[- ]holland",),
    },
    {
        "slug": "bpw",
        "name": "BPW",
        "description": "Новости BPW: оси, компоненты, телематика и решения для коммерческого транспорта.",
        "patterns": (r"\bbpw\b",),
    },
]

TOPIC_RULES = [
    {
        "slug": "rynok-i-proizvodstvo",
        "name": "Рынок и производство",
        "description": "Новости производства, продаж, заводов и изменений на рынке грузовой и прицепной техники.",
        "needles": ("рынок", "продаж", "производ", "завод", "manufactur"),
    },
    {
        "slug": "gruzovaya-tehnika",
        "name": "Грузовая техника",
        "description": "Грузовики, тягачи, МАЗ, КАМАЗ и другие производители коммерческой техники.",
        "needles": ("маз", "камаз", "тягач", "грузовик", "truck"),
    },
    {
        "slug": "pritsepnaya-tehnika",
        "name": "Прицепная техника",
        "description": "Прицепы, полуприцепы, шасси, компоненты и технологии прицепной техники.",
        "needles": ("полуприцеп", "прицеп", "trailer"),
    },
    {
        "slug": "sobytiya-otrasli",
        "name": "События отрасли",
        "description": "Выставки, форумы, конференции и ключевые события рынка коммерческого транспорта.",
        "needles": ("выстав", "форум", "конференц", "expo", "show"),
    },
    {
        "slug": "novye-tehnologii",
        "name": "Новые технологии",
        "description": "Электрификация, автоматизация, цифровые решения и новые технологии в грузовой отрасли.",
        "needles": ("электр", "водород", "батар", "автомат", "робот", "цифров"),
    },
    {
        "slug": "tamozhnya-i-logistika",
        "name": "Таможня и логистика",
        "description": "Перевозки, логистика, таможня, границы и изменения в организации грузопотоков.",
        "needles": ("тамож", "границ", "логист", "перевоз"),
    },
]

RU_MAP = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
    "х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
})


def get_field(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return str(value)
    return default


def strip_html(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</\s*(p|div|li|h[1-6])\s*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()


def clamp(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    cut = value[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or value[: limit - 1]).rstrip() + "…"


def identity_key(item: dict[str, Any]) -> str:
    for key in ("canonical_url", "url", "link", "guid"):
        value = item.get(key)
        if value:
            return str(value).strip()
    return "|".join([
        get_field(item, "title", "headline", "name"),
        get_field(item, "source", "source_name", "site"),
        get_field(item, "published_at", "date", "pub_date"),
    ])


def make_id(item: dict[str, Any]) -> str:
    return hashlib.sha1(identity_key(item).encode("utf-8", "ignore")).hexdigest()[:12]


def slugify(value: str) -> str:
    value = value.lower().translate(RU_MAP)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    value = re.sub(r"-+", "-", value)
    return value[:72].rstrip("-")


def ensure_identity(item: dict[str, Any]) -> bool:
    changed = False
    item_id = str(item.get("id") or "").strip()
    if not item_id:
        item_id = make_id(item)
        item["id"] = item_id
        changed = True

    slug = str(item.get("slug") or "").strip()
    if not slug:
        title = get_field(item, "title", "headline", "name", default="news")
        stem = slugify(title) or "news"
        item["slug"] = f"{stem}-{item_id[:8]}"
        changed = True
    return changed


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def iso_date(value: str) -> str:
    dt = parse_date(value)
    return dt.date().isoformat() if dt else ""


def display_date(value: str) -> str:
    dt = parse_date(value)
    if not dt:
        return ""
    months = [
        "января","февраля","марта","апреля","мая","июня",
        "июля","августа","сентября","октября","ноября","декабря",
    ]
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"


def summary_text(item: dict[str, Any]) -> str:
    raw = get_field(item, "summary", "lead", "description")
    return strip_html(raw)


def article_text(item: dict[str, Any]) -> tuple[str, bool]:
    """Return the longest text explicitly supplied by the feed."""
    full = strip_html(get_field(item, "content", "content_text", "full_text"))
    summary = summary_text(item)
    if full and len(full) > len(summary) + 120:
        return full, True
    return summary, False


def source_url(item: dict[str, Any]) -> str:
    return get_field(item, "canonical_url", "url", "link", "source_url")


def source_name(item: dict[str, Any]) -> str:
    value = get_field(item, "source_name", "source", "site")
    if value:
        return value
    url = source_url(item)
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def tags(item: dict[str, Any]) -> list[str]:
    value = item.get("tags") or item.get("rubrics") or []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def cover_label(item: dict[str, Any]) -> str:
    item_tags = tags(item)
    if item_tags:
        first = str(item_tags[0]).strip()
        if first and first.lower() != "новости":
            return first
    return "Отраслевой материал"


def source_domain(item: dict[str, Any]) -> str:
    domain = get_field(item, "domain").strip()
    if domain:
        return domain.replace("www.", "")
    url = source_url(item)
    try:
        return urlparse(url).netloc.replace("www.", "") or "СпецАвтоПортал"
    except Exception:
        return "СпецАвтоПортал"


def cover_topic(item: dict[str, Any]) -> str:
    title = get_field(item, "title", "headline", "name").lower()
    rules = [
        (("границ", "тамож"), "Контроль на границе"),
        (("тамож",), "Таможня и логистика"),
        (("тормоз",), "Тормозные системы"),
        (("полуприцеп", "прицеп"), "Прицепная техника"),
        (("маз", "камаз", "тягач", "грузовик"), "Грузовая техника"),
        (("логист", "перевоз"), "Логистика"),
        (("гост", "регламент", "закон", "требован"), "Регулирование"),
        (("выстав", "форум", "конференц"), "События отрасли"),
        (("электр", "водород", "батар"), "Новые технологии"),
        (("рынок", "продаж", "производ"), "Рынок и производство"),
    ]
    for needles, label in rules:
        if any(needle in title for needle in needles):
            return label
    label = cover_label(item)
    return label if label != "Отраслевой материал" else "Отраслевой обзор"


def brands_for(item: dict[str, Any]) -> list[dict[str, Any]]:
    haystack = " ".join([
        get_field(item, "title", "headline", "name"),
        summary_text(item),
    ]).lower()
    return [
        brand for brand in BRAND_RULES
        if any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in brand["patterns"])
    ]


def brand_url(brand: dict[str, Any]) -> str:
    return f"{BASE_URL}/brands/{brand['slug']}/"


def topics_for(item: dict[str, Any]) -> list[dict[str, Any]]:
    haystack = " ".join([
        get_field(item, "title", "headline", "name"),
        summary_text(item),
    ]).lower()
    return [
        topic for topic in TOPIC_RULES
        if any(needle in haystack for needle in topic["needles"])
    ]


def topic_url(topic: dict[str, Any]) -> str:
    return f"{BASE_URL}/topics/{topic['slug']}/"


def source_image(item: dict[str, Any]) -> str:
    """Return only a real source image suitable for visible article media."""
    image = get_field(item, "image_url", "image", "img")
    if image.startswith(("http://", "https://")):
        return image
    return ""


def absolute_image(item: dict[str, Any]) -> str:
    """Image used by social metadata; branded logo is acceptable as invisible fallback."""
    return source_image(item) or f"{BASE_URL}/assets/logo.png"


def article_url(item: dict[str, Any]) -> str:
    return f"{BASE_URL}/news/{item['slug']}/"


def random_news_for(item: dict[str, Any], items: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    """Deterministic pseudo-random picks so each article has a stable varied sidebar."""
    current_slug = str(item.get("slug") or "")
    candidates = [candidate for candidate in items if candidate.get("slug") and candidate.get("slug") != current_slug]

    def score(candidate: dict[str, Any]) -> str:
        seed = f"{current_slug}|{candidate.get('slug', '')}"
        return hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()

    return sorted(candidates, key=score)[:limit]


def random_news_html(item: dict[str, Any], items: list[dict[str, Any]]) -> str:
    cards = []
    for candidate in random_news_for(item, items):
        title = html.escape(get_field(candidate, "title", "headline", "name", default="Материал"))
        date = display_date(get_field(candidate, "published_at", "date", "pub_date"))
        candidate_tags = tags(candidate)
        tag = html.escape(candidate_tags[0]) if candidate_tags else "Новости"
        date_html = f'<span>{html.escape(date)}</span>' if date else ""
        cards.append(
            '<a class="article-random-card" href="' + article_url(candidate) + '">'
            '<span class="article-random-card__meta">'
            f'<span class="article-random-card__tag">{tag}</span>{date_html}'
            '</span>'
            f'<strong class="article-random-card__title">{title}</strong>'
            '<span class="article-random-card__arrow">Открыть ↗</span>'
            '</a>'
        )
    return "".join(cards)


def json_ld(item: dict[str, Any]) -> str:
    title = get_field(item, "title", "headline", "name", default="Новость")
    published = get_field(item, "published_at", "date", "pub_date")
    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": clamp(summary_text(item), 300),
        "mainEntityOfPage": {"@type": "WebPage", "@id": article_url(item)},
        "url": article_url(item),
        "publisher": {
            "@type": "Organization",
            "name": "СпецАвтоПортал",
            "url": BASE_URL,
            "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/assets/logo.png"},
        },
    }
    if published:
        payload["datePublished"] = published
        payload["dateModified"] = published
    image = absolute_image(item)
    if image:
        payload["image"] = [image]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")


def render_page(item: dict[str, Any], items: list[dict[str, Any]]) -> str:
    title_raw = get_field(item, "title", "headline", "name", default="Новость")
    title = html.escape(title_raw)
    summary_raw = summary_text(item)
    article_raw, has_full_text = article_text(item)
    article_body = html.escape(article_raw)
    description = html.escape(clamp(summary_raw or article_raw or title_raw, 160), quote=True)
    canonical = article_url(item)
    image = html.escape(absolute_image(item), quote=True)
    display_image = html.escape(source_image(item), quote=True)
    published_raw = get_field(item, "published_at", "date", "pub_date")
    published_label = display_date(published_raw)
    src_name = html.escape(source_name(item))
    src_url = html.escape(source_url(item), quote=True)
    item_tags = tags(item)
    first_tag = html.escape(item_tags[0]) if item_tags else "Новости"
    cover_tag = html.escape(cover_label(item))
    cover_topic_text = html.escape(cover_topic(item))
    cover_source = html.escape(source_domain(item))

    tag_html = "".join(
        f'<span class="tag-badge">{html.escape(tag)}</span>' for tag in item_tags[:5]
    )
    article_brands = brands_for(item)
    brand_html = ""
    if article_brands:
        brand_links = "".join(
            f'<a href="{brand_url(brand)}">{html.escape(brand["name"])}</a>'
            for brand in article_brands[:4]
        )
        brand_html = (
            '<div class="article-brand-links">'
            '<span>Бренды в материале</span>'
            f'<div>{brand_links}</div>'
            '</div>'
        )

    body = ""
    if article_body:
        paragraphs = [p.strip() for p in article_body.split("\n\n") if p.strip()]
        body = "".join(f"<p>{p}</p>" for p in paragraphs)
    if not body:
        body = "<p>Текст материала не передан источником. Подробности доступны в первоисточнике.</p>"
    body_label = "Материал" if has_full_text else "Кратко"

    editorial_cover = f"""
        <div class="article-cover" aria-hidden="true">
          <div class="article-cover__grid"></div>
          <div class="article-cover__top">
            <span class="article-cover__eyebrow">СпецАвтоПортал / материал</span>
            <span class="article-cover__date">{published_label or "Архив"}</span>
          </div>
          <div class="article-cover__body">
            <span class="article-cover__category">{cover_tag}</span>
            <strong class="article-cover__topic">{cover_topic_text}</strong>
            <span class="article-cover__source">Источник · {cover_source}</span>
          </div>
          <div class="article-cover__mark">САП</div>
        </div>
    """

    if display_image:
        visual = (
            '<div class="article-visual article-visual--photo">'
            f'<img src="{display_image}" alt="" class="article-image" '
            'onerror="this.closest(\'.article-visual\').classList.add(\'is-broken\')" />'
            + editorial_cover +
            '</div>'
        )
    else:
        visual = '<div class="article-visual article-visual--cover">' + editorial_cover + '</div>'

    source_button = ""
    if src_url:
        source_button = (
            f'<a class="primary-btn" href="{src_url}" target="_blank" '
            'rel="nofollow noopener noreferrer">Читать в первоисточнике ↗</a>'
        )

    related_html = random_news_html(item, items)

    published_meta = (
        f'<meta property="article:published_time" content="{html.escape(published_raw, quote=True)}" />'
        if published_raw else ""
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="article" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{html.escape(title_raw, quote=True)}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:image" content="{image}" />
  {published_meta}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{html.escape(title_raw, quote=True)}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{image}" />
  <meta name="theme-color" content="#111417" />
  <link rel="stylesheet" href="/styles.css?v=14" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{json_ld(item)}</script>
  <script data-goatcounter="https://specavtoportal.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body class="article-page">
  <div class="topline">
    <div class="container topline-inner">
      <span>Профессиональное медиа о грузовой технике</span>
      <span class="topline-dot"></span>
      <span>{first_tag}</span>
    </div>
  </div>

  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link nav-link-active">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/law.html" class="nav-link">ГОСТы и законы</a>
        <a href="/guides.html" class="nav-link">Гайды</a>
        <a href="/video.html" class="nav-link">Видео</a>
      </nav>
      <a href="/go/tg.html?utm_source=article&utm_medium=header" class="tg-badge" target="_blank" rel="noopener">
        <span class="tg-badge__icon">↗</span><span>Telegram</span>
      </a>
    </div>
  </header>

  <main class="page-main">
    <div class="container article-layout">
      <article class="article">
        <p class="article-breadcrumbs"><a href="/">Новости</a>{f' · <span>{first_tag}</span>' if first_tag.lower() != 'новости' else ''}</p>
        <header class="article-header">
          <h1 class="article-title">{title}</h1>
          <div class="article-meta">
            {f'<time datetime="{html.escape(published_raw, quote=True)}">{published_label}</time>' if published_label else ''}
            {f'<span>{src_name}</span>' if src_name else ''}
          </div>
          <div class="news-card-tags">{tag_html}</div>
          {brand_html}
        </header>
        {visual}
        <section class="article-body">
          <div class="article-body__heading">
            <p class="section-kicker">{body_label}</p>
            <span class="article-body__rule"></span>
          </div>
          {f'<p class="article-lead">{html.escape(summary_raw)}</p>' if has_full_text and summary_raw else ''}
          <div class="article-copy">{body}</div>
        </section>
        <footer class="article-footer">
          {source_button}
          <a href="/" class="secondary-btn">← К ленте новостей</a>
        </footer>
      </article>

      <aside class="article-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">СпецАвтоПортал</p>
          <h3>Следите за отраслью ежедневно</h3>
          <p class="sidebar-text">Свежие новости, нормативы и практические материалы для профессионального рынка.</p>
          <a class="tg-promo__button" style="display:inline-flex;margin-top:16px" href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a>
        </section>
        <section class="sidebar-block article-random-news">
          <p class="sidebar-eyebrow">Ещё новости</p>
          <div class="article-random-list">{related_html}</div>
        </section>
      </aside>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/law.html">ГОСТы и законы</a><a href="/guides.html">Гайды</a><a href="/video.html">Видео</a><a href="https://t.me/specavtoportal">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def render_brand_page(brand: dict[str, Any], brand_items: list[dict[str, Any]]) -> str:
    name = html.escape(brand["name"])
    description = html.escape(brand["description"], quote=True)
    canonical = brand_url(brand)

    cards = []
    for item in brand_items[:60]:
        title = html.escape(get_field(item, "title", "headline", "name", default="Материал"))
        date = display_date(get_field(item, "published_at", "date", "pub_date"))
        source = html.escape(source_domain(item))
        summary = html.escape(clamp(summary_text(item), 240))
        meta = " · ".join(part for part in [date, source] if part)
        cards.append(
            '<article class="topic-card">'
            f'<div class="topic-card__meta">{html.escape(meta)}</div>'
            f'<h2><a href="{article_url(item)}">{title}</a></h2>'
            + (f'<p>{summary}</p>' if summary else '')
            + f'<a class="topic-card__link" href="{article_url(item)}">Открыть материал ↗</a>'
            '</article>'
        )

    schema_payload = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": brand["name"],
        "description": brand["description"],
        "url": canonical,
        "about": {"@type": "Brand", "name": brand["name"]},
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index + 1,
                    "url": article_url(item),
                    "name": get_field(item, "title", "headline", "name", default="Материал"),
                }
                for index, item in enumerate(brand_items[:60])
            ],
        },
    }
    schema = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    other_links = "".join(
        f'<a href="/brands/{other["slug"]}/">{html.escape(other["name"])} <span>→</span></a>'
        for other in BRAND_RULES if other["slug"] != brand["slug"]
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name} — новости и материалы | СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{name} — СпецАвтоПортал" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <meta name="theme-color" content="#111417" />
  <link rel="stylesheet" href="/styles.css?v=14" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
  <script data-goatcounter="https://specavtoportal.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body class="topic-page brand-page">
  <div class="topline">
    <div class="container topline-inner">
      <span>Профессиональное медиа о грузовой технике</span>
      <span class="topline-dot"></span>
      <span>Производители и бренды</span>
    </div>
  </div>

  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link nav-link-active">Бренды</a>
        <a href="/law.html" class="nav-link">ГОСТы и законы</a>
        <a href="/guides.html" class="nav-link">Гайды</a>
        <a href="/video.html" class="nav-link">Видео</a>
      </nav>
      <a href="https://t.me/specavtoportal" class="tg-badge" target="_blank" rel="noopener"><span>Telegram ↗</span></a>
    </div>
  </header>

  <main>
    <section class="topic-hero brand-hero">
      <div class="container topic-hero__inner">
        <div>
          <p class="section-kicker">Производитель / бренд</p>
          <h1>{name}</h1>
          <p>{html.escape(brand["description"])}</p>
        </div>
        <div class="topic-hero__count">
          <strong>{len(brand_items)}</strong>
          <span>материалов</span>
        </div>
      </div>
    </section>

    <section class="container topic-layout">
      <div class="topic-feed">
        {''.join(cards)}
      </div>
      <aside class="topic-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Другие бренды</p>
          <div class="topic-nav">{other_links}</div>
          <a class="text-link brand-all-link" href="/brands/">Все бренды <span>→</span></a>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/brands/">Бренды</a><a href="/law.html">ГОСТы и законы</a><a href="/guides.html">Гайды</a><a href="https://t.me/specavtoportal">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def render_brand_directory(brand_counts: dict[str, int]) -> str:
    cards = []
    for brand in BRAND_RULES:
        count = brand_counts.get(brand["slug"], 0)
        cards.append(
            f'<a class="brand-directory-card" href="/brands/{brand["slug"]}/">'
            f'<span class="brand-directory-card__count">{count} материалов</span>'
            f'<strong>{html.escape(brand["name"])}</strong>'
            f'<p>{html.escape(brand["description"])}</p>'
            '<span class="brand-directory-card__link">Открыть архив →</span>'
            '</a>'
        )

    schema_payload = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Производители и бренды",
        "description": "Архив новостей и материалов о производителях грузовой и прицепной техники.",
        "url": f"{BASE_URL}/brands/",
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index + 1,
                    "url": brand_url(brand),
                    "name": brand["name"],
                }
                for index, brand in enumerate(BRAND_RULES)
            ],
        },
    }
    schema = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Производители и бренды — СпецАвтоПортал</title>
  <meta name="description" content="Новости и материалы о производителях грузовой техники, прицепов, полуприцепов и компонентов." />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{BASE_URL}/brands/" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="Производители и бренды — СпецАвтоПортал" />
  <meta property="og:description" content="Архив новостей о производителях грузовой и прицепной техники." />
  <meta property="og:url" content="{BASE_URL}/brands/" />
  <link rel="stylesheet" href="/styles.css?v=14" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
</head>
<body class="brand-directory-page">
  <div class="topline">
    <div class="container topline-inner">
      <span>Профессиональное медиа о грузовой технике</span>
      <span class="topline-dot"></span>
      <span>Производители и бренды</span>
    </div>
  </div>
  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link nav-link-active">Бренды</a>
        <a href="/law.html" class="nav-link">ГОСТы и законы</a>
        <a href="/guides.html" class="nav-link">Гайды</a>
        <a href="/video.html" class="nav-link">Видео</a>
      </nav>
      <a href="https://t.me/specavtoportal" class="tg-badge" target="_blank" rel="noopener"><span>Telegram ↗</span></a>
    </div>
  </header>
  <main>
    <section class="topic-hero brand-directory-hero">
      <div class="container">
        <p class="section-kicker">Архив отрасли</p>
        <h1>Производители и бренды</h1>
        <p>Материалы о компаниях, моделях, технологиях и проектах производителей грузовой и прицепной техники.</p>
      </div>
    </section>
    <section class="container brand-directory-grid">
      {''.join(cards)}
    </section>
  </main>
  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/brands/">Бренды</a><a href="/law.html">ГОСТы и законы</a><a href="/guides.html">Гайды</a><a href="https://t.me/specavtoportal">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def render_topic_page(topic: dict[str, Any], topic_items: list[dict[str, Any]]) -> str:
    name = html.escape(topic["name"])
    description = html.escape(topic["description"], quote=True)
    canonical = topic_url(topic)

    cards = []
    for item in topic_items[:60]:
        title = html.escape(get_field(item, "title", "headline", "name", default="Материал"))
        date = display_date(get_field(item, "published_at", "date", "pub_date"))
        source = html.escape(source_domain(item))
        summary = html.escape(clamp(summary_text(item), 240))
        meta = " · ".join(part for part in [date, source] if part)
        cards.append(
            '<article class="topic-card">'
            f'<div class="topic-card__meta">{html.escape(meta)}</div>'
            f'<h2><a href="{article_url(item)}">{title}</a></h2>'
            + (f'<p>{summary}</p>' if summary else '')
            + f'<a class="topic-card__link" href="{article_url(item)}">Открыть материал ↗</a>'
            '</article>'
        )

    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": topic["name"],
        "description": topic["description"],
        "url": canonical,
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index + 1,
                    "url": article_url(item),
                    "name": get_field(item, "title", "headline", "name", default="Материал"),
                }
                for index, item in enumerate(topic_items[:60])
            ],
        },
    }
    schema = json.dumps(item_list, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name} — новости и материалы | СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{name} — СпецАвтоПортал" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <meta name="theme-color" content="#111417" />
  <link rel="stylesheet" href="/styles.css?v=14" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
  <script data-goatcounter="https://specavtoportal.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</head>
<body class="topic-page">
  <div class="topline">
    <div class="container topline-inner">
      <span>Профессиональное медиа о грузовой технике</span>
      <span class="topline-dot"></span>
      <span>Тематический раздел</span>
    </div>
  </div>

  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/law.html" class="nav-link">ГОСТы и законы</a>
        <a href="/guides.html" class="nav-link">Гайды</a>
        <a href="/video.html" class="nav-link">Видео</a>
      </nav>
      <a href="https://t.me/specavtoportal" class="tg-badge" target="_blank" rel="noopener"><span>Telegram ↗</span></a>
    </div>
  </header>

  <main>
    <section class="topic-hero">
      <div class="container topic-hero__inner">
        <div>
          <p class="section-kicker">Тематический раздел</p>
          <h1>{name}</h1>
          <p>{html.escape(topic["description"])}</p>
        </div>
        <div class="topic-hero__count">
          <strong>{len(topic_items)}</strong>
          <span>материалов</span>
        </div>
      </div>
    </section>

    <section class="container topic-layout">
      <div class="topic-feed">
        {''.join(cards)}
      </div>
      <aside class="topic-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Другие темы</p>
          <div class="topic-nav">
            {''.join(f'<a href="/topics/{other["slug"]}/">{html.escape(other["name"])} <span>→</span></a>' for other in TOPIC_RULES if other["slug"] != topic["slug"])}
          </div>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/law.html">ГОСТы и законы</a><a href="/guides.html">Гайды</a><a href="/video.html">Видео</a><a href="https://t.me/specavtoportal">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def write_sitemap(items: list[dict[str, Any]]) -> None:
    static_pages = [
        (f"{BASE_URL}/", ""),
        (f"{BASE_URL}/law.html", ""),
        (f"{BASE_URL}/guides.html", ""),
        (f"{BASE_URL}/video.html", ""),
    ]
    rows = []
    for url, lastmod in static_pages:
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        rows.append(f"  <url><loc>{xml_escape(url)}</loc>{lm}</url>")

    for topic in TOPIC_RULES:
        rows.append(f"  <url><loc>{xml_escape(topic_url(topic))}</loc></url>")

    rows.append(f"  <url><loc>{xml_escape(f'{BASE_URL}/brands/')}</loc></url>")
    for brand in BRAND_RULES:
        rows.append(f"  <url><loc>{xml_escape(brand_url(brand))}</loc></url>")

    for item in items:
        lastmod = iso_date(get_field(item, "published_at", "date", "pub_date"))
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        rows.append(f"  <url><loc>{xml_escape(article_url(item))}</loc>{lm}</url>")

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "\n".join(rows)
    sitemap += "\n</urlset>\n"
    (FRONTEND / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /data/\n\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n"
    )
    (FRONTEND / "robots.txt").write_text(robots, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()

    items = json.loads(NEWS_JSON.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        items = items.get("items", [])

    changed = sum(1 for item in items if ensure_identity(item))
    NEWS_JSON.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SEO] identity ready: {len(items)} items; changed: {changed}")

    if args.metadata_only:
        return

    if NEWS_DIR.exists():
        shutil.rmtree(NEWS_DIR)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    if TOPICS_DIR.exists():
        shutil.rmtree(TOPICS_DIR)
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)

    if BRANDS_DIR.exists():
        shutil.rmtree(BRANDS_DIR)
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)

    for item in items:
        out_dir = NEWS_DIR / item["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_page(item, items), encoding="utf-8")

    topic_counts = {}
    for topic in TOPIC_RULES:
        topic_items = [item for item in items if topic in topics_for(item)]
        topic_counts[topic["slug"]] = len(topic_items)
        out_dir = TOPICS_DIR / topic["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_topic_page(topic, topic_items), encoding="utf-8")

    brand_counts = {}
    for brand in BRAND_RULES:
        brand_items = [item for item in items if brand in brands_for(item)]
        brand_counts[brand["slug"]] = len(brand_items)
        out_dir = BRANDS_DIR / brand["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_brand_page(brand, brand_items), encoding="utf-8")

    (BRANDS_DIR / "index.html").write_text(render_brand_directory(brand_counts), encoding="utf-8")

    write_sitemap(items)
    print(f"[SEO] generated {len(items)} static article pages")
    print(f"[SEO] generated topic hubs: {topic_counts}")
    print(f"[SEO] generated brand hubs: {brand_counts}")
    print(f"[SEO] sitemap: {FRONTEND / 'sitemap.xml'}")
    print(f"[SEO] robots: {FRONTEND / 'robots.txt'}")


if __name__ == "__main__":
    main()
