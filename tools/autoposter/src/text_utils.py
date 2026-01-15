import re
import html

_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

def strip_html(s: str) -> str:
    if not s:
        return ""
    s = str(s)

    # делаем переносы строк на местах типичных блочных тегов
    s = re.sub(r"</(p|div|figure|li|h\d)>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)

    # убрать всё остальное
    s = _TAG_RE.sub(" ", s)

    # html entities -> нормальные символы
    s = html.unescape(s)

    # нормализация пробелов/переносов
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def extract_img_src_from_html(s: str) -> str:
    if not s:
        return ""
    m = _IMG_RE.search(str(s))
    return m.group(1) if m else ""


def clamp(text: str, max_len: int = 220) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"
