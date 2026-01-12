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

    def cut(s: str, n: int = 78) -> str:
        s = " ".join((s or "").split()).strip()
        return s if len(s) <= n else (s[: n - 1].rstrip() + "…")

    slides: List[Slide] = [
        Slide(
            header="ТОП-3 за неделю",
            lines=["Прицепы • Полуприцепы • Грузовики", "Инфраструктура • Госзакупки"],
            footer="Дайджест SpecAvtoPortal",
            seconds=cfg.SLIDE_TITLE_SECONDS,
            # титульный слайд можно без картинки (или можно взять картинку 1-й новости)
            image_url=getattr(items[0], "image", None),
        )
    ]

    for i, it in enumerate(items, start=1):
        slides.append(
            Slide(
                header=f"Новость #{i}",
                lines=[cut(it.title)],
                footer="Коротко: что важно рынку",
                seconds=cfg.SLIDE_NEWS_SECONDS,
                image_url=getattr(it, "image", None),  # <-- КАРТИНКА НОВОСТИ
            )
        )

    slides.append(
        Slide(
            header="Где читать",
            lines=["Сайт: spec-avtoportal.ru", "TG: t.me/specavtoportal", "Ссылки — в профиле / шапке"],
            footer="Подписывайся / сохраняй",
            seconds=cfg.SLIDE_CTA_SECONDS,
            image_url=getattr(items[0], "image", None),
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
