"""Deterministic 1080x1080 Telegram cards for SpecAvtoPortal."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

SIZE = 1080
BG = "#15181C"
BG_2 = "#1D2228"
ORANGE = "#FF6B00"
TEXT = "#F3F4F6"
MUTED = "#A7ADB4"
GRID = "#2B3036"

FONT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
)
FONT_REGULAR_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
)


def _font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _clean(text: str) -> str:
    value = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", value).strip()


def _fit_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = _clean(text).split()
    if not words:
        return []

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    consumed = " ".join(lines)
    original = " ".join(words)
    if consumed != original and lines:
        tail = lines[-1].rstrip(" .,:;!-")
        while tail and draw.textbbox((0, 0), tail + "…", font=font)[2] > max_width:
            tail = tail.rsplit(" ", 1)[0] if " " in tail else tail[:-1]
        lines[-1] = (tail or lines[-1][:12]).rstrip() + "…"
    return lines


def _category(item: dict[str, Any]) -> str:
    title = _clean(item.get("title") or "").lower()
    tags = " ".join(str(x) for x in (item.get("tags") or [])).lower()
    haystack = f"{title} {tags}"

    rules = (
        ("РЕГЛАМЕНТЫ", ("гост", "тр тс", "регламент", "закон", "сертиф", "штраф")),
        ("РЫНОК", ("рынок", "цена", "продаж", "подорож", "производств")),
        ("ЛОГИСТИКА", ("логист", "перевоз", "тамож", "границ", "маршрут")),
        ("ПРОИЗВОДИТЕЛИ", ("завод", "производител", "бренд", "krone", "маз", "камаз", "kögel")),
        ("ТЕХНИКА", ("полуприцеп", "прицеп", "тягач", "грузовик", "ось", "тормоз")),
    )
    for label, needles in rules:
        if any(needle in haystack for needle in needles):
            return label
    return "ОТРАСЛЬ"


def _summary(item: dict[str, Any]) -> str:
    raw = _clean(item.get("summary") or item.get("description") or "")
    if not raw:
        return "Главное событие отрасли — коротко и по делу."
    first = re.split(r"(?<=[.!?])\s+", raw)[0]
    return first[:170].rstrip(" ,.;:-")


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(image)

    # Editorial technical grid.
    for x in range(80, SIZE, 120):
        draw.line((x, 0, x, SIZE), fill=GRID, width=1)
    for y in range(80, SIZE, 120):
        draw.line((0, y, SIZE, y), fill=GRID, width=1)

    # Dark panels give depth while staying deterministic.
    draw.rectangle((0, 0, SIZE, 150), fill=BG_2)
    draw.rectangle((770, 150, SIZE, SIZE), fill="#181C21")
    draw.rectangle((80, 146, 250, 152), fill=ORANGE)
    return image, draw


def _brand(draw: ImageDraw.ImageDraw) -> None:
    brand_font = _font(FONT_BOLD_CANDIDATES, 30)
    small = _font(FONT_BOLD_CANDIDATES, 18)

    # Compact SAP mark.
    draw.rounded_rectangle((80, 48, 142, 108), radius=12, fill=ORANGE)
    draw.text((96, 62), "САП", font=small, fill="#FFFFFF")
    draw.text((162, 57), "СпецАвтоПортал", font=brand_font, fill=TEXT)


def render_important_card(item: dict[str, Any], output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    image, draw = _canvas()
    _brand(draw)

    category_font = _font(FONT_BOLD_CANDIDATES, 24)
    title_font = _font(FONT_BOLD_CANDIDATES, 68)
    summary_font = _font(FONT_REGULAR_CANDIDATES, 27)
    badge_font = _font(FONT_BOLD_CANDIDATES, 20)

    category = _category(item)
    draw.text((80, 205), category, font=category_font, fill=ORANGE)

    title = _clean(item.get("title") or "Важная новость")
    title_lines = _fit_lines(draw, title, title_font, 770, 5)
    y = 270
    for line in title_lines:
        draw.text((80, y), line, font=title_font, fill=TEXT)
        y += 82

    summary = _summary(item)
    summary_lines = _fit_lines(draw, summary, summary_font, 710, 2)
    summary_y = 850
    for line in summary_lines:
        draw.text((80, summary_y), line, font=summary_font, fill=MUTED)
        summary_y += 38

    draw.rounded_rectangle((790, 860, 1000, 924), radius=16, fill=ORANGE)
    draw.text((848, 879), "ВАЖНО", font=badge_font, fill="#FFFFFF")

    # Abstract trailer / axle motif.
    draw.rectangle((815, 300, 982, 390), outline="#353B42", width=4)
    draw.line((815, 390, 945, 390), fill=ORANGE, width=6)
    for cx in (850, 910, 970):
        draw.ellipse((cx - 18, 405, cx + 18, 441), outline=MUTED, width=4)

    image.save(output, "PNG", optimize=True)
    return output


def render_digest_card(slot: str, output: str | Path, when: datetime | None = None) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    image, draw = _canvas()
    _brand(draw)

    when = when or datetime.now()
    digest_type = "Утренняя\nсводка" if slot == "am" else "Вечерняя\nсводка"

    date_font = _font(FONT_BOLD_CANDIDATES, 23)
    title_font = _font(FONT_BOLD_CANDIDATES, 84)
    sub_font = _font(FONT_REGULAR_CANDIDATES, 27)
    topics_font = _font(FONT_BOLD_CANDIDATES, 19)

    months = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    date_text = f"{when.day} {months[when.month - 1]}"
    date_width = draw.textbbox((0, 0), date_text, font=date_font)[2]
    draw.text((1000 - date_width, 62), date_text, font=date_font, fill=MUTED)

    y = 275
    for line in digest_type.split("\n"):
        draw.text((80, y), line, font=title_font, fill=TEXT)
        y += 102

    sub = "главное о рынке прицепов, полуприцепов\nи грузовой техники"
    sy = 585
    for line in sub.split("\n"):
        draw.text((80, sy), line, font=sub_font, fill=MUTED)
        sy += 40

    draw.line((80, 760, 730, 760), fill=ORANGE, width=7)
    draw.text(
        (80, 805),
        "НОВОСТИ · РЫНОК · ТЕХНИКА · РЕГЛАМЕНТЫ",
        font=topics_font,
        fill=TEXT,
    )

    # Big restrained accent block.
    draw.rounded_rectangle((805, 650, 1000, 920), radius=32, outline="#343A41", width=3)
    draw.rectangle((855, 715, 950, 730), fill=ORANGE)
    draw.rectangle((855, 765, 930, 780), fill="#59616A")
    draw.rectangle((855, 815, 970, 830), fill="#343A41")

    image.save(output, "PNG", optimize=True)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=("important", "digest"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="Новый ГОСТ вступил в силу")
    parser.add_argument("--summary", default="Что изменилось для перевозчиков и как подготовиться.")
    parser.add_argument("--slot", choices=("am", "pm"), default="am")
    args = parser.parse_args()

    if args.type == "important":
        render_important_card(
            {"title": args.title, "summary": args.summary, "tags": ["регулирование"]},
            args.output,
        )
    else:
        render_digest_card(args.slot, args.output)
