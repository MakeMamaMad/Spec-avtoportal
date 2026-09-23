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
BASE_URL = "https://spec-avtoportal.ru"

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


def render_page(item: dict[str, Any]) -> str:
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
  <link rel="stylesheet" href="/styles.css?v=9" />
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
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Источник</p>
          <h3>{src_name or 'Первоисточник'}</h3>
          <p class="sidebar-text">Если источник передаёт полный текст через RSS, он публикуется здесь. В остальных случаях доступна выжимка и ссылка на оригинал.</p>
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

    for item in items:
        out_dir = NEWS_DIR / item["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_page(item), encoding="utf-8")

    write_sitemap(items)
    print(f"[SEO] generated {len(items)} static article pages")
    print(f"[SEO] sitemap: {FRONTEND / 'sitemap.xml'}")
    print(f"[SEO] robots: {FRONTEND / 'robots.txt'}")


if __name__ == "__main__":
    main()
