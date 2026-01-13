from dataclasses import dataclass
from typing import List, Optional

from ..config import cfg
from .sources import ContentItem


@dataclass
class Slide:
    header: str
    lines: List[str]
    footer: str
    seconds: float
    image_url: Optional[str] = None
    # для стабильного выбора шаблона по хэшу
    key: Optional[str] = None


@dataclass
class DigestPlan:
    slides: List[Slide]
    youtube_title: str
    youtube_description: str
    caption: str


def build_digest(items: List[ContentItem]) -> DigestPlan:
    items = [x for x in items if x.title and x.url][:3]
    if not items:
        raise ValueError("No items for digest")

    def clean(s: str) -> str:
        return " ".join((s or "").replace("\xa0", " ").split()).strip()

    def cut(s: str, n: int) -> str:
        s = clean(s)
        return s if len(s) <= n else (s[: n - 1].rstrip() + "…")

    def pick_summary(it: ContentItem) -> str:
        # берём больше описания, без повтора заголовка
        s = clean(getattr(it, "summary", "") or "")
        if not s:
            return "Коротко: подробности — по ссылке."
        # если вдруг summary повторяет title — отрежем и оставим хвост
        t = clean(it.title)
        if t and s.lower().startswith(t.lower()):
            s = s[len(t):].lstrip(" —:;,.")
        # сделаем длиннее, чтобы снизу не было пустоты
        return cut(s, 220)

    slides: List[Slide] = [
        Slide(
            header="ТОП-3 за неделю",
            lines=["Прицепы • Полуприцепы • Грузовики", "Инфраструктура • Госзакупки"],
            footer="Дайджест SpecAvtoPortal",
            seconds=cfg.SLIDE_TITLE_SECONDS,
            image_url=getattr(items[0], "image", None),
            key="title",
        )
    ]

    for i, it in enumerate(items, start=1):
        slides.append(
            Slide(
                header=f"Новость {i}",  # без #
                lines=[
                    cut(it.title, 120),
                    pick_summary(it),     # больше описания
                ],
                footer=(it.source or "").strip() or "SpecAvtoPortal",
                seconds=cfg.SLIDE_NEWS_SECONDS,
                image_url=getattr(it, "image", None),
                key=it.url,
            )
        )

    slides.append(
        Slide(
            header="Где читать",
            lines=[
                "Сайт: spec-avtoportal.ru",
                "TG: t.me/specavtoportal",
                "Ссылки — в профиле / шапке",
            ],
            footer="Подписывайся / сохраняй",
            seconds=cfg.SLIDE_CTA_SECONDS,
            image_url=getattr(items[0], "image", None),
            key="cta",
        )
    )

    tags = ["#прицепы", "#полуприцепы", "#грузовики", "#логистика", "#госзакупки", "#инфраструктура"]
    links = "\n".join([f"{i+1}) {it.url}" for i, it in enumerate(items)])

    caption = (
        "ТОП-3 новости недели\n\n"
        f"{links}\n\n"
        f"TG: {cfg.TELEGRAM_URL}\n"
        f"Сайт: {cfg.SITE_URL}\n\n"
        + " ".join(tags)
    )

    yt_title = "ТОП-3 новости недели | SpecAvtoPortal"
    yt_desc = caption + "\n"
    return DigestPlan(slides=slides, youtube_title=yt_title, youtube_description=yt_desc, caption=caption)
