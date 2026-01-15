import datetime
import re
import html
from pathlib import Path

from .config import cfg
from .content.sources import load_items
from .content.digest import build_digest
from .render.video import render_digest_video
from .publish.youtube import upload_video
from .utils.state import load_posted_urls, save_posted_urls


_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def strip_html(s: str) -> str:
    """Убирает HTML-теги, декодирует entities, нормализует пробелы/переносы."""
    if not s:
        return ""
    s = str(s)

    # переносы для типичных блочных тегов
    s = re.sub(r"</(p|div|figure|li|h\d)>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)

    # убрать остальные теги
    s = _TAG_RE.sub(" ", s)

    # entities -> символы
    s = html.unescape(s)

    # нормализация
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def extract_img_src_from_html(s: str) -> str:
    """Достаёт первую картинку из HTML summary вида <img src="...">."""
    if not s:
        return ""
    m = _IMG_RE.search(str(s))
    return m.group(1) if m else ""


def clamp(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _get_attr(obj, names, default=""):
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is not None:
                return v
    return default


def _set_attr_if_exists(obj, names, value):
    for n in names:
        if hasattr(obj, n):
            try:
                setattr(obj, n, value)
                return True
            except Exception:
                pass
    return False


def sanitize_item(it):
    """
    Чистит title/summary от HTML и пробует заполнить image из summary,
    если image отсутствует.
    """
    # Возможные имена полей — на случай разных моделей Item
    title_raw = _get_attr(it, ["title", "name", "headline"], "")
    summary_raw = _get_attr(it, ["summary", "description", "excerpt"], "")

    title_clean = clamp(strip_html(title_raw), 90)
    summary_clean = clamp(strip_html(summary_raw), 260)

    _set_attr_if_exists(it, ["title", "name", "headline"], title_clean)
    _set_attr_if_exists(it, ["summary", "description", "excerpt"], summary_clean)

    # image может быть None/"" — тогда попробуем вытащить из HTML summary
    image_val = _get_attr(it, ["image", "image_url", "thumbnail", "thumb"], "")
    if not image_val:
        img_from_summary = extract_img_src_from_html(summary_raw)
        if img_from_summary:
            _set_attr_if_exists(it, ["image", "image_url", "thumbnail", "thumb"], img_from_summary)


def sanitize_plan_strings(plan):
    """
    На всякий случай чистим HTML в уже сформированных строках описания.
    Если plan — dataclass с frozen=True, setattr упадёт — тогда просто пропустим.
    """
    for field, max_len in [
        ("caption", 1500),
        ("youtube_description", 4000),
        ("youtube_title", 90),
    ]:
        if hasattr(plan, field):
            try:
                raw = getattr(plan, field) or ""
                clean = clamp(strip_html(raw), max_len)
                setattr(plan, field, clean)
            except Exception:
                pass


def main():
    items = load_items()
    if not items:
        raise SystemExit(f"No items found. Check CONTENT_JSON_PATH={cfg.CONTENT_JSON_PATH}")

    posted = load_posted_urls()
    picked = []
    for it in items:
        if it.url not in posted:
            picked.append(it)
        if len(picked) >= 3:
            break

    if not picked:
        print("[autoposter] Nothing new to post (all items already posted).")
        return

    # ✅ ВАЖНО: чистим HTML ДО build_digest(), чтобы на слайды/описание ушёл нормальный текст
    for it in picked:
        sanitize_item(it)

    plan = build_digest(picked)

    # ✅ дополнительная страховка: чистим HTML в caption/описании, если вдруг там остались теги
    sanitize_plan_strings(plan)

    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    mp4_path = out_dir / f"digest_{ts}.mp4"
    caption_path = out_dir / "caption.txt"

    render_digest_video(plan.slides, mp4_path)
    caption_path.write_text(plan.caption, encoding="utf-8")

    yt_id = upload_video(
        file_path=str(mp4_path),
        title=plan.youtube_title,
        description=plan.youtube_description,
        tags=["прицепы", "полуприцепы", "грузовики", "логистика", "госзакупки", "инфраструктура"],
        privacy_status=cfg.YOUTUBE_PRIVACY,
    )
    print("[autoposter] YouTube uploaded:", yt_id)

    for it in picked:
        posted.add(it.url)
    save_posted_urls(posted)
    print("[autoposter] State updated. posted_urls:", len(posted))


if __name__ == "__main__":
    main()
