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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
AGGREGATOR = ROOT / "aggregator"
if str(AGGREGATOR) not in sys.path:
    sys.path.insert(0, str(AGGREGATOR))

from telegram_visual import render_social_card

FRONTEND = ROOT / "frontend"
NEWS_JSON = FRONTEND / "data" / "news.json"
NEWS_INDEX_JSON = FRONTEND / "data" / "news-index.json"
HOME_HTML = FRONTEND / "index.html"
REGULATIONS_JSON = FRONTEND / "data" / "regulations.json"
KNOWLEDGE_ARTICLES_JSON = FRONTEND / "data" / "knowledge_articles.json"
NEWS_DIR = FRONTEND / "news"
TOPICS_DIR = FRONTEND / "topics"
BRANDS_DIR = FRONTEND / "brands"
REGULATIONS_DIR = FRONTEND / "regulations"
KNOWLEDGE_DIR = FRONTEND / "knowledge"
SOCIAL_DIR = FRONTEND / "social"
BASE_URL = "https://spec-avtoportal.ru"
METRIKA_ID = 106240080
METRIKA_SCRIPT_TAG = '<script defer src="/metrika.js"></script>'
METRIKA_NOSCRIPT = (
    '<noscript><div><img src="https://mc.yandex.ru/watch/106240080" '
    'style="position:absolute; left:-9999px;" alt="" /></div></noscript>'
)

BRAND_RULES = [
    {
        "slug": "satpricep",
        "name": "SAT / satpricep.by",
        "description": "Новости Завода Спецавтотехника, прицепной техники SAT, новых моделей и проектов satpricep.by.",
        "patterns": (r"satpricep", r"спецавтотехник", r"\bsat\d{2,4}\b"),
        "partner": True,
        "partner_url": "https://www.satpricep.by/",
    },
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

SAT_PRODUCTS = [
    {
        "id": "sat500",
        "name": "SAT500",
        "subtitle": "Алюминиевый самосвальный полуприцеп-зерновоз",
        "spec": "от 49 м³ · до 44 т · 4 оси",
        "url": "https://www.satpricep.by/catalog/polupritsepy/polupritsepy-zernovozy/polupritsep-samosvalnyy-alyuminievyy-sat500/",
        "needles": ("зерновоз", "зерно", "сельхоз", "сыпуч", "урожай", "элеватор"),
    },
    {
        "id": "sat150",
        "name": "SAT150",
        "subtitle": "Полуприцеп с подвижным полом",
        "spec": "90–105 м³ · горизонтальная разгрузка",
        "url": "https://www.satpricep.by/catalog/polupritsepy/s-podvizhnyim-polom/polupritsep-s-podvizhnym-polom-sat150/",
        "needles": ("подвижн", "сдвижн", "щеп", "опил", "торф", "отход", "мусор", "паллет"),
    },
    {
        "id": "sat600",
        "name": "SAT600",
        "subtitle": "Трёхъярусный полуприцеп-скотовоз",
        "spec": "до 27 т · 3 оси",
        "url": "https://www.satpricep.by/catalog/polupritsepy/polupritsep-skotovoz-svinovoz/polupritsep-skotovoz-svinovoz-tryekhyarusnyy-sat600/",
        "needles": ("скотовоз", "скот", "свин", "поросят", "животн", "овец", "ягнят"),
    },
    {
        "id": "sat-lowload",
        "name": "SAT183 / SAT186",
        "subtitle": "Низкорамные полуприцепы для техники и тяжёлых грузов",
        "spec": "до 72 т · платформа до 12 м",
        "url": "https://www.satpricep.by/catalog/transportnye-organizatsii/",
        "needles": ("низкорам", "трал", "негабарит", "тяжеловес", "спецтехник", "экскаватор", "бульдозер"),
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
    """Return only the short editorial/feed summary for public rendering.

    Full source content may remain in news.json as ingestion material, but it is
    intentionally never republished on an indexable page. This avoids mirroring
    third-party articles and also means foreign full-text content never needs to
    be machine-translated.
    """
    return summary_text(item), False


def cyrillic_ratio(value: str) -> float:
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", value or "")
    if not letters:
        return 0.0
    russian = sum(1 for char in letters if re.match(r"[А-Яа-яЁё]", char))
    return russian / len(letters)


def news_quality_issues(item: dict[str, Any]) -> list[str]:
    """Return reasons why a news page should not be submitted for indexing."""
    issues: list[str] = []
    title = strip_html(get_field(item, "title", "headline", "name"))
    summary = summary_text(item)
    url = source_url(item)

    if not str(item.get("slug") or "").strip():
        issues.append("missing_slug")
    if len(title) < 18:
        issues.append("short_title")
    if len(summary) < 80:
        issues.append("thin_summary")
    if cyrillic_ratio(f"{title} {summary}") < 0.35:
        issues.append("non_russian")
    if not url.startswith(("http://", "https://")):
        issues.append("missing_source")
    return issues


def is_indexable_news(item: dict[str, Any]) -> bool:
    return not news_quality_issues(item)


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
        get_field(item, "source", "source_name", "site"),
        get_field(item, "domain"),
        " ".join(tags(item)),
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


def social_card_needed(item: dict[str, Any], max_age_days: int = 7) -> bool:
    """Generate branded cards only for fresh stories that can still be published socially."""
    published = parse_date(get_field(item, "published_at", "date", "pub_date"))
    if published is None:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - published.astimezone(timezone.utc)
    return -timedelta(hours=6) <= age <= timedelta(days=max_age_days)


def absolute_image(item: dict[str, Any]) -> str:
    """Image used by social metadata; fresh news gets a branded generated card."""
    slug = str(item.get("slug") or "").strip()
    if slug and social_card_needed(item):
        return f"{BASE_URL}/social/{slug}.png"
    return source_image(item) or f"{BASE_URL}/assets/logo.png"


def article_url(item: dict[str, Any]) -> str:
    return f"{BASE_URL}/news/{item['slug']}/"


KNOWLEDGE_LINK_RULES = {
    "nagruzka-na-os": ("нагрузк", "осев", "перегруз", "весогабарит", "весовой контроль", "тяжеловес", "автопоезд"),
    "gabarity-i-massy": ("габарит", "масса", "длина", "ширина", "высота", "автопоезд", "тяжеловес", "крупногабарит"),
    "tr-ts-018-2011": ("тр тс", "018/2011", "сертификац", "оттс", "изменен", "конструкц", "соответств", "категория o"),
    "kreplenie-gruzov": ("креплен", "крепеж", "ремн", "точк креплен", "паллет", "фиксац", "стяж"),
    "tehnicheskoe-obsluzhivanie-polupricepa": ("обслужив", "техническ", "ремонт", "тормоз", "подвеск", "шина", "ступиц", "неисправ", "осмотр", "диагност"),
    "kak-vybrat-polupricep": ("полуприцеп", "прицеп", "зерновоз", "самосвал", "рефриж", "тент", "низкорам", "цистерн", "кузов", "грузопод"),
}


def news_haystack(item: dict[str, Any]) -> str:
    return " ".join([
        get_field(item, "title", "headline", "name"),
        summary_text(item),
        get_field(item, "content", "content_text", "full_text"),
        " ".join(tags(item)),
    ]).lower()


def knowledge_matches_for_news(item: dict[str, Any], knowledge_articles: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    title = get_field(item, "title", "headline", "name").lower()
    haystack = news_haystack(item)
    scored: list[tuple[int, dict[str, Any]]] = []
    for knowledge_item in knowledge_articles.get("items", []):
        slug = str(knowledge_item.get("slug") or "")
        needles = KNOWLEDGE_LINK_RULES.get(slug, ())
        score = sum(3 for needle in needles if needle in title)
        score += sum(1 for needle in needles if needle in haystack)
        if score > 0:
            scored.append((score, knowledge_item))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("title") or "")))
    return [knowledge_item for _, knowledge_item in scored[:limit]]


def knowledge_links_html(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return ""
    cards = []
    for item in matches:
        eyebrow = html.escape(get_field(item, "eyebrow", default="База знаний"))
        title = html.escape(get_field(item, "title", default="Материал"))
        description = html.escape(clamp(get_field(item, "description"), 150))
        cards.append(
            f'<a class="context-link-card" href="/knowledge/{html.escape(str(item["slug"]), quote=True)}/">'
            f'<span>{eyebrow}</span>'
            f'<strong>{title}</strong>'
            + (f'<p>{description}</p>' if description else '')
            + '<b>Разобраться →</b>'
            '</a>'
        )
    return (
        '<section class="article-context">'
        '<div class="article-context__heading"><p class="section-kicker">Полезно по теме</p><h2>Практические материалы</h2></div>'
        f'<div class="context-link-grid">{"".join(cards)}</div>'
        '</section>'
    )


def news_matches_for_knowledge(knowledge_item: dict[str, Any], items: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    slug = str(knowledge_item.get("slug") or "")
    needles = KNOWLEDGE_LINK_RULES.get(slug, ())
    scored: list[tuple[int, float, dict[str, Any]]] = []
    for item in items:
        title = get_field(item, "title", "headline", "name").lower()
        haystack = news_haystack(item)
        score = sum(3 for needle in needles if needle in title)
        score += sum(1 for needle in needles if needle in haystack)
        if score <= 0:
            continue
        published = parse_date(get_field(item, "published_at", "date", "pub_date"))
        stamp = published.timestamp() if published else 0.0
        scored.append((score, stamp, item))
    scored.sort(key=lambda row: (-row[0], -row[1]))
    return [item for _, _, item in scored[:limit]]


def regulation_knowledge_matches(regulation: dict[str, Any], knowledge_articles: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = {
        "tr-ts-018-2011": ["tr-ts-018-2011", "kak-vybrat-polupricep"],
        "gost-3163-2020": ["tehnicheskoe-obsluzhivanie-polupricepa", "kak-vybrat-polupricep"],
        "gost-34598-2019": ["kak-vybrat-polupricep"],
        "gost-r-70472-2023": ["kreplenie-gruzov"],
        "gost-r-70473-2022": ["kreplenie-gruzov"],
        "gost-r-70474-2023": ["kreplenie-gruzov"],
        "gost-r-70477-2022": ["kreplenie-gruzov"],
        "mintrans-212-2026": ["tehnicheskoe-obsluzhivanie-polupricepa", "nagruzka-na-os"],
    }
    wanted = mapping.get(str(regulation.get("slug") or ""), [])
    by_slug = {str(item.get("slug") or ""): item for item in knowledge_articles.get("items", [])}
    return [by_slug[slug] for slug in wanted if slug in by_slug]


def sat_product_by_id(product_id: str) -> dict[str, Any] | None:
    for product in SAT_PRODUCTS:
        if product["id"] == product_id:
            return product
    return None


def sat_product_for_news(item: dict[str, Any]) -> dict[str, Any] | None:
    domain = source_domain(item).lower()
    source = source_name(item).lower()
    item_tags = [tag.lower() for tag in tags(item)]
    if "satpricep.by" in domain or "satpricep" in source or "satpricep" in item_tags or "партнёр" in item_tags:
        return None

    title = get_field(item, "title", "headline", "name").lower()
    haystack = news_haystack(item)
    scored: list[tuple[int, dict[str, Any]]] = []
    for product in SAT_PRODUCTS:
        needles = product.get("needles", ())
        score = sum(4 for needle in needles if needle in title)
        score += sum(1 for needle in needles if needle in haystack)
        if score >= 3:
            scored.append((score, product))
    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]["name"])))
    return scored[0][1]


def sat_products_for_knowledge(item: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = {
        "kak-vybrat-polupricep": ["sat500", "sat150", "sat600", "sat-lowload"],
    }
    return [
        product
        for product_id in mapping.get(str(item.get("slug") or ""), [])
        if (product := sat_product_by_id(product_id)) is not None
    ]


def sat_recommendation_html(products: list[dict[str, Any]], placement: str) -> str:
    if not products:
        return ""
    cards = []
    for product in products:
        separator = "&" if "?" in product["url"] else "?"
        url = (
            f'{product["url"]}{separator}'
            f'utm_source=spec-avtoportal&utm_medium=contextual_partner&utm_campaign={product["id"]}&utm_content={placement}'
        )
        cards.append(
            '<a class="sat-product-card" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="sponsored noopener">'
            '<span class="sat-product-card__brand">SAT</span>'
            f'<strong>{html.escape(product["name"])}</strong>'
            f'<p>{html.escape(product["subtitle"])}</p>'
            f'<b>{html.escape(product["spec"])}</b>'
            '<em>Смотреть модель ↗</em>'
            '</a>'
        )
    return (
        '<section class="sat-recommendation">'
        '<div class="sat-recommendation__head">'
        '<div><span>Партнёр проекта</span><strong>SATPRICEP</strong></div>'
        '<p>Подбор по теме материала</p>'
        '</div>'
        f'<div class="sat-product-grid">{"".join(cards)}</div>'
        '<div class="sat-recommendation__note">Реклама · характеристики и наличие уточняйте у производителя</div>'
        '</section>'
    )


def related_news_for(item: dict[str, Any], items: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    """Choose related stories by shared brands/topics/tags, then recency."""
    current_slug = str(item.get("slug") or "")
    current_brands = {brand["slug"] for brand in brands_for(item)}
    current_topics = {topic["slug"] for topic in topics_for(item)}
    current_tags = {tag.lower() for tag in tags(item)}

    scored: list[tuple[int, float, dict[str, Any]]] = []
    fallback: list[tuple[float, dict[str, Any]]] = []
    for candidate in items:
        if not candidate.get("slug") or candidate.get("slug") == current_slug:
            continue
        if not is_indexable_news(candidate):
            continue

        candidate_brands = {brand["slug"] for brand in brands_for(candidate)}
        candidate_topics = {topic["slug"] for topic in topics_for(candidate)}
        candidate_tags = {tag.lower() for tag in tags(candidate)}
        score = 8 * len(current_brands & candidate_brands)
        score += 4 * len(current_topics & candidate_topics)
        score += 2 * len(current_tags & candidate_tags)

        published = parse_date(get_field(candidate, "published_at", "date", "pub_date"))
        stamp = published.timestamp() if published else 0.0
        fallback.append((stamp, candidate))
        if score > 0:
            scored.append((score, stamp, candidate))

    scored.sort(key=lambda row: (-row[0], -row[1]))
    selected = [candidate for _, _, candidate in scored[:limit]]
    if len(selected) < limit:
        used = {str(candidate.get("slug") or "") for candidate in selected}
        fallback.sort(key=lambda row: -row[0])
        for _, candidate in fallback:
            if str(candidate.get("slug") or "") in used:
                continue
            selected.append(candidate)
            used.add(str(candidate.get("slug") or ""))
            if len(selected) >= limit:
                break
    return selected


def random_news_html(item: dict[str, Any], items: list[dict[str, Any]]) -> str:
    cards = []
    for candidate in related_news_for(item, items):
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
        "author": {
            "@type": "Organization",
            "name": "Редакция СпецАвтоПортала",
            "url": f"{BASE_URL}/about.html",
        },
        "publisher": {
            "@type": "Organization",
            "name": "СпецАвтоПортал",
            "url": BASE_URL,
            "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/assets/logo.png"},
        },
        "inLanguage": "ru-RU",
        "isAccessibleForFree": True,
        "articleSection": cover_topic(item),
    }
    if published:
        payload["datePublished"] = published
        payload["dateModified"] = get_field(item, "updated_at", default=published)
    image = absolute_image(item)
    if image:
        payload["image"] = [image]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")


def render_page(item: dict[str, Any], items: list[dict[str, Any]], knowledge_articles: dict[str, Any]) -> str:
    title_raw = get_field(item, "title", "headline", "name", default="Новость")
    title = html.escape(title_raw)
    summary_raw = summary_text(item)
    article_raw, has_full_text = article_text(item)
    article_body = html.escape(article_raw)
    indexable = is_indexable_news(item)
    robots = "index,follow,max-image-preview:large" if indexable else "noindex,follow"
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
        body = "<p>Краткое описание материала пока недоступно. Подробности доступны в первоисточнике.</p>"
    body_label = "Кратко"
    editorial_note = (
        '<p class="article-editorial-note">'
        'СпецАвтоПортал публикует краткое отраслевое изложение. '
        'Полный текст и исходные данные доступны у первоисточника.'
        '</p>'
    )

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
    knowledge_html = knowledge_links_html(knowledge_matches_for_news(item, knowledge_articles))
    sat_product = sat_product_for_news(item)
    sat_html = sat_recommendation_html([sat_product] if sat_product else [], "news")

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
  <meta name="robots" content="{robots}" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="article" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{html.escape(title_raw, quote=True)}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:image" content="{image}" />
  <meta property="og:image:type" content="image/png" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  {published_meta}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{html.escape(title_raw, quote=True)}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{image}" />
  <meta name="theme-color" content="#111417" />
  <link rel="stylesheet" href="/styles.css?v=19" />
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
        <a href="/knowledge.html" class="nav-link">База знаний</a>
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
          {editorial_note}
          <div class="article-copy">{body}</div>
        </section>
        {knowledge_html}
        {sat_html}
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
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/brands/">Бренды</a><a href="/law.html">Нормативы</a><a href="https://t.me/specavtoportal">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


HUB_PAGE_SIZE = 36


def pagination_html(base_path: str, page: int, total_pages: int) -> str:
    if total_pages <= 1:
        return ""
    links = []
    if page > 1:
        prev_href = base_path if page == 2 else f"{base_path}page/{page - 1}/"
        links.append(f'<a class="secondary-btn" href="{prev_href}">← Новее</a>')
    links.append(f'<span class="result-count">Страница {page} из {total_pages}</span>')
    if page < total_pages:
        links.append(f'<a class="secondary-btn" href="{base_path}page/{page + 1}/">Старее →</a>')
    return '<nav class="hub-pagination" aria-label="Навигация по архиву">' + "".join(links) + "</nav>"


def pagination_head(base_url: str, page: int, total_pages: int) -> str:
    tags = []
    if page > 1:
        prev_url = base_url if page == 2 else f"{base_url}page/{page - 1}/"
        tags.append(f'<link rel="prev" href="{prev_url}" />')
    if page < total_pages:
        tags.append(f'<link rel="next" href="{base_url}page/{page + 1}/" />')
    return "\n  ".join(tags)


def render_brand_page(
    brand: dict[str, Any],
    brand_items: list[dict[str, Any]],
    page: int = 1,
    page_size: int = HUB_PAGE_SIZE,
) -> str:
    name = html.escape(brand["name"])
    description = html.escape(brand["description"], quote=True)
    total_pages = max(1, (len(brand_items) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    page_items = brand_items[start:start + page_size]
    canonical = brand_url(brand) if page == 1 else f"{brand_url(brand)}page/{page}/"
    page_suffix = "" if page == 1 else f" — страница {page}"
    page_nav = pagination_html(f"/brands/{brand['slug']}/", page, total_pages)
    head_nav = pagination_head(brand_url(brand), page, total_pages)

    cards = []
    for item in page_items:
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
                for index, item in enumerate(page_items, start=start + 1)
            ],
        },
    }
    schema = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    other_links = "".join(
        f'<a href="/brands/{other["slug"]}/">{html.escape(other["name"])} <span>→</span></a>'
        for other in BRAND_RULES if other["slug"] != brand["slug"]
    )
    partner_html = ""
    if brand.get("partner") and brand.get("partner_url"):
        partner_html = (
            '<div class="brand-partner-note">'
            '<span>Партнёр проекта</span>'
            f'<a href="{html.escape(str(brand["partner_url"]), quote=True)}?utm_source=spec-avtoportal&utm_medium=brand_hub&utm_campaign=partner" '
            'target="_blank" rel="sponsored noopener">Перейти на satpricep.by ↗</a>'
            '</div>'
        )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name} — новости и материалы{page_suffix} | СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  {head_nav}
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{name} — СпецАвтоПортал" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <meta name="theme-color" content="#111417" />
  <link rel="stylesheet" href="/styles.css?v=19" />
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
        <a href="/knowledge.html" class="nav-link">База знаний</a>
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
          {partner_html}
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
        {page_nav}
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
        partner_badge = '<span class="brand-directory-card__partner">Партнёр проекта</span>' if brand.get("partner") else ''
        cards.append(
            f'<a class="brand-directory-card" href="/brands/{brand["slug"]}/">'
            f'{partner_badge}'
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
  <link rel="stylesheet" href="/styles.css?v=19" />
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
        <a href="/knowledge.html" class="nav-link">База знаний</a>
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


def render_topic_page(
    topic: dict[str, Any],
    topic_items: list[dict[str, Any]],
    page: int = 1,
    page_size: int = HUB_PAGE_SIZE,
) -> str:
    name = html.escape(topic["name"])
    description = html.escape(topic["description"], quote=True)
    total_pages = max(1, (len(topic_items) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    page_items = topic_items[start:start + page_size]
    canonical = topic_url(topic) if page == 1 else f"{topic_url(topic)}page/{page}/"
    page_suffix = "" if page == 1 else f" — страница {page}"
    page_nav = pagination_html(f"/topics/{topic['slug']}/", page, total_pages)
    head_nav = pagination_head(topic_url(topic), page, total_pages)

    cards = []
    for item in page_items:
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
                for index, item in enumerate(page_items, start=start + 1)
            ],
        },
    }
    schema = json.dumps(item_list, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name} — новости и материалы{page_suffix} | СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  {head_nav}
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{name} — СпецАвтоПортал" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <meta name="theme-color" content="#111417" />
  <link rel="stylesheet" href="/styles.css?v=19" />
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
        <a href="/knowledge.html" class="nav-link">База знаний</a>
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
        {page_nav}
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
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/brands/">Бренды</a><a href="/law.html">Нормативы</a><a href="https://t.me/specavtoportal">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def load_knowledge_articles() -> dict[str, Any]:
    if not KNOWLEDGE_ARTICLES_JSON.exists():
        return {"items": [], "updated_at": ""}
    payload = json.loads(KNOWLEDGE_ARTICLES_JSON.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"items": [], "updated_at": ""}
    payload.setdefault("items", [])
    payload.setdefault("updated_at", "")
    return payload


def knowledge_url(item: dict[str, Any]) -> str:
    return f"{BASE_URL}/knowledge/{item['slug']}/"


def render_knowledge_article(item: dict[str, Any], updated_at: str, news_items: list[dict[str, Any]]) -> str:
    title_raw = get_field(item, "title", default="Материал базы знаний")
    title = html.escape(title_raw)
    eyebrow = html.escape(get_field(item, "eyebrow", default="База знаний"))
    description_raw = get_field(item, "description", default=title_raw)
    description = html.escape(clamp(description_raw, 165), quote=True)
    lead = html.escape(get_field(item, "lead"))
    canonical = knowledge_url(item)

    section_html = []
    for section in item.get("sections", []):
        if not isinstance(section, dict):
            continue
        heading = html.escape(get_field(section, "heading"))
        blocks = []
        for paragraph in section.get("paragraphs", []) if isinstance(section.get("paragraphs"), list) else []:
            blocks.append(f"<p>{html.escape(str(paragraph))}</p>")
        bullets = section.get("bullets") if isinstance(section.get("bullets"), list) else []
        if bullets:
            blocks.append("<ul>" + "".join(f"<li>{html.escape(str(x))}</li>" for x in bullets) + "</ul>")
        numbered = section.get("numbered") if isinstance(section.get("numbered"), list) else []
        if numbered:
            blocks.append("<ol>" + "".join(f"<li>{html.escape(str(x))}</li>" for x in numbered) + "</ol>")
        facts = section.get("facts") if isinstance(section.get("facts"), list) else []
        if facts:
            fact_rows = []
            for row in facts:
                if isinstance(row, list) and len(row) >= 2:
                    fact_rows.append(
                        '<div class="knowledge-fact">'
                        f'<span>{html.escape(str(row[0]))}</span>'
                        f'<strong>{html.escape(str(row[1]))}</strong>'
                        '</div>'
                    )
            if fact_rows:
                blocks.append('<div class="knowledge-facts">' + "".join(fact_rows) + '</div>')
        section_html.append(
            '<section class="knowledge-article__section">'
            f'<h2>{heading}</h2>'
            + "".join(blocks)
            + '</section>'
        )

    source_html = []
    for source in item.get("sources", []) if isinstance(item.get("sources"), list) else []:
        if not isinstance(source, dict):
            continue
        label = html.escape(get_field(source, "label", default="Источник"))
        url = get_field(source, "url")
        if not url:
            continue
        href = html.escape(url, quote=True)
        rel = ' rel="noopener"' if url.startswith(("http://", "https://")) else ""
        target = ' target="_blank"' if url.startswith(("http://", "https://")) else ""
        source_html.append(f'<a href="{href}"{target}{rel}>{label}<span>↗</span></a>')

    recent_news = news_matches_for_knowledge(item, news_items)
    recent_news_html = ""
    if recent_news:
        cards = []
        for news_item in recent_news:
            news_title = html.escape(get_field(news_item, "title", "headline", "name", default="Материал"))
            news_date = html.escape(display_date(get_field(news_item, "published_at", "date", "pub_date")))
            news_source = html.escape(source_domain(news_item))
            news_meta = " · ".join(part for part in [news_date, news_source] if part)
            cards.append(
                f'<a class="knowledge-news-card" href="/news/{html.escape(str(news_item["slug"]), quote=True)}/">'
                f'<span>{news_meta}</span><strong>{news_title}</strong><b>Читать новость →</b></a>'
            )
        recent_news_html = (
            '<section class="knowledge-related-news"><p class="section-kicker">По теме</p><h2>Свежие новости</h2>'
            f'<div class="knowledge-news-grid">{"".join(cards)}</div></section>'
        )

    sat_html = sat_recommendation_html(sat_products_for_knowledge(item), "knowledge")

    partner_html = ""
    partner = item.get("partner")
    if not sat_html and isinstance(partner, dict) and partner.get("url"):
        partner_html = f"""
        <section class="knowledge-partner">
          <p class="sidebar-eyebrow">{html.escape(get_field(partner, "label", default="Партнёр проекта"))}</p>
          <h3>{html.escape(get_field(partner, "title"))}</h3>
          <p>{html.escape(get_field(partner, "text"))}</p>
          <a href="{html.escape(get_field(partner, "url"), quote=True)}" target="_blank" rel="sponsored noopener">Перейти к партнёру <span>↗</span></a>
        </section>
        """

    schema_payload = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title_raw,
        "description": description_raw,
        "url": canonical,
        "dateModified": updated_at or None,
        "author": {"@type": "Organization", "name": "СпецАвтоПортал"},
        "publisher": {"@type": "Organization", "name": "СпецАвтоПортал", "url": BASE_URL},
    }
    schema_payload = {k: v for k, v in schema_payload.items() if v is not None}
    schema = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} | База знаний — СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="article" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <link rel="stylesheet" href="/styles.css?v=19" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
</head>
<body class="knowledge-article-page">
  <div class="topline"><div class="container topline-inner"><span>Профессиональное медиа о грузовой технике</span><span class="topline-dot"></span><span>База знаний</span></div></div>
  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/knowledge.html" class="nav-link nav-link-active">База знаний</a>
      </nav>
      <a href="https://t.me/specavtoportal" class="tg-badge" target="_blank" rel="noopener"><span>Telegram ↗</span></a>
    </div>
  </header>

  <main>
    <section class="knowledge-article-hero">
      <div class="container">
        <p class="section-kicker"><a href="/knowledge.html">База знаний</a> · {eyebrow}</p>
        <h1>{title}</h1>
        <p>{lead}</p>
        <div class="knowledge-article-hero__meta">Обновлено · {html.escape(updated_at or "—")}</div>
      </div>
    </section>

    <section class="container knowledge-article-layout">
      <article class="knowledge-article">
        {''.join(section_html)}
        {sat_html}
        {recent_news_html}
      </article>
      <aside class="knowledge-article-sidebar">
        {partner_html}
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Источники и документы</p>
          <div class="knowledge-sources">{''.join(source_html)}</div>
        </section>
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Материал носит справочный характер. Для нормативных требований проверяйте актуальную редакцию официального документа и ограничения конкретного маршрута.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/guides.html">Гайды</a><a href="/brands/">Бренды</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def load_regulations() -> dict[str, Any]:
    if not REGULATIONS_JSON.exists():
        return {"items": [], "archived": [], "verified_at": ""}
    payload = json.loads(REGULATIONS_JSON.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"items": [], "archived": [], "verified_at": ""}
    payload.setdefault("items", [])
    payload.setdefault("archived", [])
    payload.setdefault("verified_at", "")
    return payload


def regulation_url(item: dict[str, Any]) -> str:
    return f"{BASE_URL}/regulations/{item['slug']}/"


def render_regulation_page(item: dict[str, Any], verified_at: str, knowledge_articles: dict[str, Any]) -> str:
    title = html.escape(get_field(item, "title", default="Нормативный документ"))
    code = html.escape(get_field(item, "code", default="Норматив"))
    doc_type = html.escape(get_field(item, "type", default="Документ"))
    status = html.escape(get_field(item, "status", default="Статус не указан"))
    scope = html.escape(get_field(item, "scope"))
    why = html.escape(get_field(item, "why_it_matters"))
    jurisdiction = html.escape(get_field(item, "jurisdiction"))
    effective_from = html.escape(get_field(item, "effective_from"))
    effective_until = html.escape(get_field(item, "effective_until"))
    source_name = html.escape(get_field(item, "official_source", default="Официальный источник"))
    source_url_value = get_field(item, "official_url")
    source_url_escaped = html.escape(source_url_value, quote=True)
    verified = html.escape(verified_at)
    canonical = regulation_url(item)
    keywords = item.get("keywords") if isinstance(item.get("keywords"), list) else []
    keyword_html = "".join(
        f'<span class="tag-badge">{html.escape(str(keyword))}</span>'
        for keyword in keywords[:8]
    )
    description_raw = clamp(
        get_field(item, "scope", "why_it_matters", default=f"{code}: нормативный документ"),
        160,
    )
    description = html.escape(description_raw, quote=True)

    meta_rows = [
        ("Статус", status),
        ("Юрисдикция", jurisdiction),
        ("Действует с", effective_from),
    ]
    if effective_until:
        meta_rows.append(("Действует до", effective_until))
    if verified:
        meta_rows.append(("Проверено редакцией", verified))
    meta_html = "".join(
        f'<div><span>{html.escape(label)}</span><strong>{value}</strong></div>'
        for label, value in meta_rows if value
    )
    practice_html = knowledge_links_html(regulation_knowledge_matches(item, knowledge_articles))

    schema_payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"{get_field(item, 'code')} — {get_field(item, 'title')}",
        "description": description_raw,
        "url": canonical,
        "dateModified": verified_at or None,
        "about": {
            "@type": "Legislation",
            "name": get_field(item, "code"),
            "legislationType": get_field(item, "type"),
            "legislationJurisdiction": get_field(item, "jurisdiction"),
            "url": source_url_value,
        },
    }
    schema_payload = {k: v for k, v in schema_payload.items() if v is not None}
    schema = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{code} — {title} | СпецАвтоПортал</title>
  <meta name="description" content="{description}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="article" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{code} — {title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{canonical}" />
  <link rel="stylesheet" href="/styles.css?v=19" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
</head>
<body class="regulation-page">
  <div class="topline"><div class="container topline-inner"><span>Профессиональное медиа о грузовой технике</span><span class="topline-dot"></span><span>Нормативная база</span></div></div>
  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/knowledge.html" class="nav-link nav-link-active">База знаний</a>
      </nav>
      <a href="https://t.me/specavtoportal" class="tg-badge" target="_blank" rel="noopener"><span>Telegram ↗</span></a>
    </div>
  </header>

  <main>
    <section class="regulation-hero">
      <div class="container">
        <p class="section-kicker"><a href="/knowledge.html">База знаний</a> · <a href="/law.html">Нормативы</a> · {doc_type}</p>
        <span class="regulation-status">{status}</span>
        <h1>{code}</h1>
        <p class="regulation-hero__title">{title}</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <div class="regulation-meta-grid">{meta_html}</div>

        <section class="regulation-section">
          <p class="section-kicker">Область применения</p>
          <h2>Что регулирует документ</h2>
          <p>{scope or "Краткое описание области применения уточняется редакцией."}</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Практический смысл</p>
          <h2>Почему это важно</h2>
          <p>{why or "Практические комментарии к документу готовятся."}</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Ключевые темы</p>
          <div class="news-card-tags">{keyword_html}</div>
        </section>
        {practice_html}
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Первоисточник</p>
          <h3>{source_name}</h3>
          <p class="sidebar-text">Перед применением требований проверяйте текущую редакцию и статус документа в официальном источнике.</p>
          <a class="partner-card__button" href="{source_url_escaped}" target="_blank" rel="noopener">Открыть официальный документ <span>↗</span></a>
        </section>
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Материал носит справочный характер и не заменяет текст нормативного акта, стандарта или профессиональную правовую/техническую консультацию.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/guides.html">Гайды</a><a href="/brands/">Бренды</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def render_regulations_index(regulations: dict[str, Any]) -> str:
    items = regulations.get("items") if isinstance(regulations.get("items"), list) else []
    archived = regulations.get("archived") if isinstance(regulations.get("archived"), list) else []
    verified_at = str(regulations.get("verified_at") or "")

    cards = []
    for item in items:
        title = html.escape(get_field(item, "title"))
        code = html.escape(get_field(item, "code"))
        doc_type = html.escape(get_field(item, "type"))
        status = html.escape(get_field(item, "status"))
        scope = html.escape(clamp(get_field(item, "scope"), 220))
        cards.append(
            '<article class="regulation-card">'
            '<div class="regulation-card__top">'
            f'<span>{doc_type}</span><strong>{status}</strong>'
            '</div>'
            f'<h2><a href="/regulations/{html.escape(str(item["slug"]), quote=True)}/">{code}</a></h2>'
            f'<p class="regulation-card__title">{title}</p>'
            f'<p>{scope}</p>'
            f'<a class="topic-card__link" href="/regulations/{html.escape(str(item["slug"]), quote=True)}/">Разобрать документ →</a>'
            '</article>'
        )

    archived_html = "".join(
        '<li>'
        f'<strong>{html.escape(get_field(item, "code"))}</strong>'
        f'<span>{html.escape(get_field(item, "status"))}</span>'
        f'<p>{html.escape(get_field(item, "note"))}</p>'
        '</li>'
        for item in archived
    )

    schema_payload = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Нормативы и ГОСТы по грузовой и прицепной технике",
        "description": "Проверенный каталог действующих нормативных документов для грузовой и прицепной техники.",
        "url": f"{BASE_URL}/law.html",
        "dateModified": verified_at or None,
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index + 1,
                    "url": regulation_url(item),
                    "name": get_field(item, "code"),
                }
                for index, item in enumerate(items)
            ],
        },
    }
    schema_payload = {k: v for k, v in schema_payload.items() if v is not None}
    schema = json.dumps(schema_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Нормативы и ГОСТы — База знаний | СпецАвтоПортал</title>
  <meta name="description" content="Проверенный каталог действующих ГОСТов, технических регламентов и правил для грузовой и прицепной техники." />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{BASE_URL}/law.html" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="Нормативы и ГОСТы — СпецАвтоПортал" />
  <meta property="og:description" content="Действующие нормативы для прицепов, полуприцепов, крепления грузов и безопасной эксплуатации." />
  <meta property="og:url" content="{BASE_URL}/law.html" />
  <link rel="stylesheet" href="/styles.css?v=19" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
</head>
<body class="regulations-index-page">
  <div class="topline"><div class="container topline-inner"><span>Профессиональное медиа о грузовой технике</span><span class="topline-dot"></span><span>База знаний</span></div></div>
  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/knowledge.html" class="nav-link nav-link-active">База знаний</a>
      </nav>
      <a href="https://t.me/specavtoportal" class="tg-badge" target="_blank" rel="noopener"><span>Telegram ↗</span></a>
    </div>
  </header>

  <main>
    <section class="knowledge-child-hero">
      <div class="container">
        <p class="section-kicker"><a href="/knowledge.html">База знаний</a> · Нормативы</p>
        <h1>Нормативы и ГОСТы</h1>
        <p class="hero-subtitle">Проверенная подборка действующих документов по прицепам, полуприцепам, креплению грузов и безопасной эксплуатации коммерческого транспорта.</p>
        <p class="regulations-verified">Последняя проверка редакцией: {html.escape(verified_at or "—")}</p>
      </div>
    </section>

    <section class="container regulations-grid">
      {''.join(cards)}
    </section>

    <section class="container regulations-archive">
      <p class="section-kicker">Архив</p>
      <h2>Документы, которые больше не считаем действующими</h2>
      <p>Храним этот список, чтобы устаревшие нормы случайно не вернулись в активную базу.</p>
      <ul>{archived_html}</ul>
    </section>

    <section class="container regulations-disclaimer">
      <strong>Важно:</strong> перед практическим применением всегда сверяйтесь с официальным текстом и актуальной редакцией документа.
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/guides.html">Гайды</a><a href="/brands/">Бренды</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""


def compact_news_item(item: dict[str, Any]) -> dict[str, Any]:
    """Lightweight public index used by the homepage instead of the multi-MB raw feed."""
    return {
        "id": str(item.get("id") or ""),
        "slug": str(item.get("slug") or ""),
        "title": get_field(item, "title", "headline", "name"),
        "summary": summary_text(item),
        "published_at": get_field(item, "published_at", "date", "pub_date"),
        "source_name": source_name(item),
        "image_url": source_image(item),
        "tags": tags(item)[:6],
    }


def news_sort_key(item: dict[str, Any]) -> float:
    published = parse_date(get_field(item, "published_at", "date", "pub_date"))
    return published.timestamp() if published else 0.0


def write_news_index(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_items = [item for item in items if is_indexable_news(item)]
    public_items.sort(key=news_sort_key, reverse=True)
    payload = [compact_news_item(item) for item in public_items]
    NEWS_INDEX_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return public_items


def home_feature_html(item: dict[str, Any], primary: bool) -> str:
    title = html.escape(get_field(item, "title", "headline", "name", default="Без заголовка"))
    summary = html.escape(clamp(summary_text(item), 230 if primary else 115))
    image = html.escape(source_image(item), quote=True)
    date = html.escape(display_date(get_field(item, "published_at", "date", "pub_date")))
    source = html.escape(source_name(item))
    item_tags = tags(item)
    tag = html.escape(item_tags[0] if item_tags else "Новости")
    url = f"/news/{html.escape(str(item['slug']), quote=True)}/"

    media = ""
    if image:
        media = (
            f'<a class="featured-media" href="{url}" aria-label="{title}">'
            f'<img src="{image}" alt="" class="featured-image" loading="{"eager" if primary else "lazy"}"></a>'
        )
    meta = "".join(f"<span>{value}</span>" for value in (date, source) if value)
    summary_html = f'<p class="featured-summary">{summary}</p>' if summary else ""
    return (
        media
        + '<div class="featured-content"><div class="featured-topline">'
        + f'<span class="featured-tag">{tag}</span></div>'
        + f'<h3><a href="{url}">{title}</a></h3>'
        + summary_html
        + f'<div class="featured-meta">{meta}</div></div>'
    )


def home_card_html(item: dict[str, Any], position: int, total: int) -> str:
    title = html.escape(get_field(item, "title", "headline", "name", default="Без заголовка"))
    summary = html.escape(clamp(summary_text(item), 320 if position == 0 else 220))
    date = html.escape(display_date(get_field(item, "published_at", "date", "pub_date")))
    source = html.escape(source_name(item))
    item_topics = topics_for(item)
    item_tags = tags(item)
    primary_tag = html.escape(
        item_topics[0]["name"] if item_topics else (item_tags[0] if item_tags else "Новости")
    )
    url = f"/news/{html.escape(str(item['slug']), quote=True)}/"
    lead = position == 0
    wide = position == total - 1 and position > 0 and max(0, total - 1) % 2 == 1
    classes = "news-card" + (" news-card--lead" if lead else "") + (" news-card--wide" if wide else "")
    meta = "".join(f"<span>{value}</span>" for value in (date, source) if value)
    summary_html = f'<p class="news-card-summary">{summary}</p>' if summary else ""
    return (
        f'<article class="{classes}"><div class="news-card-body">'
        f'<span class="news-card-category">{primary_tag}</span>'
        f'<div class="news-card-meta">{meta}</div>'
        f'<h3 class="news-card-title"><a href="{url}">{title}</a></h3>'
        f'{summary_html}'
        f'<div class="news-card-footer"><a class="news-card-read" href="{url}">'
        'Открыть материал <span>↗</span></a></div>'
        '</div></article>'
    )


def replace_home_block(page: str, name: str, payload: str) -> str:
    pattern = rf"<!-- {re.escape(name)}_START -->.*?<!-- {re.escape(name)}_END -->"
    replacement = f"<!-- {name}_START -->{payload}<!-- {name}_END -->"
    updated, count = re.subn(pattern, replacement, page, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Homepage SEO marker not found: {name}")
    return updated


def build_homepage(items: list[dict[str, Any]]) -> None:
    """Pre-render the first screen so crawlers/users do not depend on JavaScript."""
    if not HOME_HTML.exists():
        return
    page = HOME_HTML.read_text(encoding="utf-8")
    featured = [item for item in items if source_image(item)][:3]
    if len(featured) < 3:
        used = {str(item.get("slug") or "") for item in featured}
        featured.extend(item for item in items if str(item.get("slug") or "") not in used)
        featured = featured[:3]

    primary = home_feature_html(featured[0], True) if featured else ""
    secondary = "".join(
        f'<article class="featured-mini">{home_feature_html(item, False)}</article>'
        for item in featured[1:3]
    )
    visible = items[:12]
    cards = "".join(home_card_html(item, index, len(visible)) for index, item in enumerate(visible))
    topic_counts = {
        topic["slug"]: sum(1 for item in items if topic in topics_for(item))
        for topic in TOPIC_RULES
    }
    top_tags = "".join(
        f'<li><a href="/topics/{topic["slug"]}/">{html.escape(topic["name"])} · {topic_counts[topic["slug"]]}</a></li>'
        for topic in sorted(TOPIC_RULES, key=lambda row: topic_counts[row["slug"]], reverse=True)
        if topic_counts[topic["slug"]]
    )
    bootstrap = json.dumps(
        [compact_news_item(item) for item in items[:36]],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\/")

    page = replace_home_block(page, "SEO_FEATURED_PRIMARY", primary)
    page = replace_home_block(page, "SEO_FEATURED_SECONDARY", secondary)
    page = replace_home_block(page, "SEO_NEWS_LIST", cards)
    page = replace_home_block(page, "SEO_TOP_TAGS", top_tags)
    page = replace_home_block(page, "SEO_NEWS_COUNT", str(len(items)))
    latest = display_date(get_field(items[0], "published_at", "date", "pub_date")) if items else "—"
    page = replace_home_block(page, "SEO_LATEST_DATE", html.escape(latest))
    page = replace_home_block(
        page,
        "SEO_RESULT_COUNT",
        f'{len(items):,}'.replace(",", " ") + " материалов" if items else "",
    )
    page = replace_home_block(
        page,
        "SEO_BOOTSTRAP",
        f'<script id="seo-news-bootstrap" type="application/json">{bootstrap}</script>',
    )
    HOME_HTML.write_text(page, encoding="utf-8")


def write_news_sitemap(items: list[dict[str, Any]]) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    rows: list[str] = []
    for item in items:
        published = parse_date(get_field(item, "published_at", "date", "pub_date"))
        if not published:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published.astimezone(timezone.utc) < cutoff:
            continue
        title = xml_escape(get_field(item, "title", "headline", "name"))
        published_iso = xml_escape(published.astimezone(timezone.utc).isoformat())
        rows.append(
            "  <url>"
            f"<loc>{xml_escape(article_url(item))}</loc>"
            "<news:news><news:publication>"
            "<news:name>СпецАвтоПортал</news:name><news:language>ru</news:language>"
            "</news:publication>"
            f"<news:publication_date>{published_iso}</news:publication_date>"
            f"<news:title>{title}</news:title>"
            "</news:news></url>"
        )
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
    )
    sitemap += "\n".join(rows)
    sitemap += "\n</urlset>\n"
    (FRONTEND / "news-sitemap.xml").write_text(sitemap, encoding="utf-8")


def write_sitemap(
    items: list[dict[str, Any]],
    regulations: dict[str, Any] | None = None,
    knowledge_articles: dict[str, Any] | None = None,
) -> None:
    static_pages = [
        (f"{BASE_URL}/", ""),
        (f"{BASE_URL}/knowledge.html", ""),
        (f"{BASE_URL}/law.html", ""),
        (f"{BASE_URL}/guides.html", ""),
        (f"{BASE_URL}/about.html", ""),
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

    if regulations:
        for item in regulations.get("items", []):
            if item.get("slug"):
                rows.append(f"  <url><loc>{xml_escape(regulation_url(item))}</loc></url>")

    if knowledge_articles:
        for item in knowledge_articles.get("items", []):
            if item.get("slug"):
                rows.append(f"  <url><loc>{xml_escape(knowledge_url(item))}</loc></url>")

    indexable_items = [item for item in items if is_indexable_news(item)]
    for item in indexable_items:
        lastmod = iso_date(get_field(item, "updated_at", "published_at", "date", "pub_date"))
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        rows.append(f"  <url><loc>{xml_escape(article_url(item))}</loc>{lm}</url>")

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "\n".join(rows)
    sitemap += "\n</urlset>\n"
    (FRONTEND / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    write_news_sitemap(indexable_items)
    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /data/\n\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n"
        f"Sitemap: {BASE_URL}/news-sitemap.xml\n"
    )
    (FRONTEND / "robots.txt").write_text(robots, encoding="utf-8")


def inject_metrika_into_pages() -> int:
    """Inject Yandex Metrika into every deployable HTML page exactly once."""
    changed = 0
    for path in FRONTEND.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        original = text
        if METRIKA_SCRIPT_TAG not in text and "</head>" in text:
            text = text.replace("</head>", f"  {METRIKA_SCRIPT_TAG}\\n</head>", 1)
        if "mc.yandex.ru/watch/106240080" not in text:
            text = re.sub(
                r"(<body\\b[^>]*>)",
                r"\\1\\n  " + METRIKA_NOSCRIPT,
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
    return changed


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

    if REGULATIONS_DIR.exists():
        shutil.rmtree(REGULATIONS_DIR)
    REGULATIONS_DIR.mkdir(parents=True, exist_ok=True)

    if KNOWLEDGE_DIR.exists():
        shutil.rmtree(KNOWLEDGE_DIR)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    if SOCIAL_DIR.exists():
        shutil.rmtree(SOCIAL_DIR)
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)

    knowledge_articles = load_knowledge_articles()
    knowledge_updated = str(knowledge_articles.get("updated_at") or "")
    for knowledge_item in knowledge_articles.get("items", []):
        if not knowledge_item.get("slug"):
            continue
        out_dir = KNOWLEDGE_DIR / str(knowledge_item["slug"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(
            render_knowledge_article(knowledge_item, knowledge_updated, items),
            encoding="utf-8",
        )

    regulations = load_regulations()
    verified_at = str(regulations.get("verified_at") or "")
    for regulation in regulations.get("items", []):
        if not regulation.get("slug"):
            continue
        out_dir = REGULATIONS_DIR / str(regulation["slug"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(
            render_regulation_page(regulation, verified_at, knowledge_articles),
            encoding="utf-8",
        )
    (FRONTEND / "law.html").write_text(render_regulations_index(regulations), encoding="utf-8")

    public_items = write_news_index(items)
    build_homepage(public_items)
    quality_blocked = len(items) - len(public_items)

    social_cards = 0
    for item in items:
        out_dir = NEWS_DIR / item["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        if social_card_needed(item):
            render_social_card(item, SOCIAL_DIR / f"{item['slug']}.png")
            social_cards += 1
        (out_dir / "index.html").write_text(render_page(item, items, knowledge_articles), encoding="utf-8")

    topic_counts = {}
    for topic in TOPIC_RULES:
        topic_items = [item for item in public_items if topic in topics_for(item)]
        topic_counts[topic["slug"]] = len(topic_items)
        out_dir = TOPICS_DIR / topic["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        total_pages = max(1, (len(topic_items) + HUB_PAGE_SIZE - 1) // HUB_PAGE_SIZE)
        (out_dir / "index.html").write_text(render_topic_page(topic, topic_items, page=1), encoding="utf-8")
        for page_number in range(2, total_pages + 1):
            page_dir = out_dir / "page" / str(page_number)
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(
                render_topic_page(topic, topic_items, page=page_number),
                encoding="utf-8",
            )

    brand_counts = {}
    for brand in BRAND_RULES:
        brand_items = [item for item in public_items if brand in brands_for(item)]
        brand_counts[brand["slug"]] = len(brand_items)
        out_dir = BRANDS_DIR / brand["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        total_pages = max(1, (len(brand_items) + HUB_PAGE_SIZE - 1) // HUB_PAGE_SIZE)
        (out_dir / "index.html").write_text(render_brand_page(brand, brand_items, page=1), encoding="utf-8")
        for page_number in range(2, total_pages + 1):
            page_dir = out_dir / "page" / str(page_number)
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(
                render_brand_page(brand, brand_items, page=page_number),
                encoding="utf-8",
            )

    (BRANDS_DIR / "index.html").write_text(render_brand_directory(brand_counts), encoding="utf-8")

    write_sitemap(items, regulations, knowledge_articles)
    metrika_pages = inject_metrika_into_pages()
    print(f"[SEO] Yandex Metrika 106240080 injected into {metrika_pages} HTML pages")
    print(f"[SEO] generated {len(items)} static article pages")
    print(f"[SEO] public/indexable news: {len(public_items)}; quality-gated: {quality_blocked}")
    print(f"[SEO] lightweight news index: {NEWS_INDEX_JSON}")
    print(f"[SEO] generated {social_cards} fresh social cards")
    print(f"[SEO] generated {len(knowledge_articles.get('items', []))} knowledge articles")
    print(f"[SEO] generated {len(regulations.get('items', []))} regulation pages")
    print(f"[SEO] generated topic hubs: {topic_counts}")
    print(f"[SEO] generated brand hubs: {brand_counts}")
    print(f"[SEO] sitemap: {FRONTEND / 'sitemap.xml'}")
    print(f"[SEO] news sitemap: {FRONTEND / 'news-sitemap.xml'}")
    print(f"[SEO] robots: {FRONTEND / 'robots.txt'}")


if __name__ == "__main__":
    main()
