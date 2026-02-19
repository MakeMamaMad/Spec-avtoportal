import os
import json
import random
import asyncio
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlencode, urlunparse, parse_qsl
import html as html_std

import requests
from dateutil import parser as dtparser
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import edge_tts
from gtts import gTTS

from .economic_templates import pick_random_episode, Slide as EconSlide


# -----------------------------
# CONFIG (env)
# -----------------------------
MODE = os.getenv("MODE", "news").strip().lower()  # "news" | "economics"

SITE_URL = os.getenv("SITE_URL", "https://spec-avtoportal.ru/").strip()
TELEGRAM_URL = os.getenv("TELEGRAM_URL", "https://t.me/specavtoportal").strip()
CONTENT_JSON_PATH = os.getenv("CONTENT_JSON_PATH", "frontend/data/news.json").strip()

VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1920"))
FPS = int(os.getenv("FPS", "30"))

TOTAL_SECONDS = float(os.getenv("TOTAL_SECONDS", "30"))
INTRO_SECONDS = float(os.getenv("INTRO_SECONDS", "1.5"))
OUTRO_SECONDS = float(os.getenv("OUTRO_SECONDS", "2.5"))

# news-mode picks
PICK_TARGET = int(os.getenv("PICK_TARGET", "4"))  # 3-4 новостей

# economics-mode
ECON_SEED = os.getenv("ECON_SEED", "").strip()
ECON_ALLOWED = os.getenv("ECON_ALLOWED", "").strip()  # например: "downtime,tires,axle"
ECON_FORCE_KEY = os.getenv("ECON_FORCE_KEY", "").strip()  # например: "downtime"

VOICE = os.getenv("VOICE", "ru-RU-DmitryNeural").strip()
TTS_RATE = os.getenv("TTS_RATE", "+15%").strip()

# если 1 — подгоняем аудио под TOTAL_SECONDS (ускоряем при необходимости)
AUDIO_FIT = os.getenv("AUDIO_FIT", "1").strip() == "1"

SUMMARY_MAX = int(os.getenv("SUMMARY_MAX", "120"))
LOGO_PATH = os.getenv("LOGO_PATH", "frontend/spec_avtoportal_favicon.ico").strip()

STATE_PATH = Path("tools/autoposter/state/posted.json")
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("tools/autoposter/out")
TMP_DIR = Path("tools/autoposter/tmp")
CARDS_DIR = TMP_DIR / "cards"
ASSETS_DIR = TMP_DIR / "assets"

for p in [OUT_DIR, TMP_DIR, CARDS_DIR, ASSETS_DIR]:
    p.mkdir(parents=True, exist_ok=True)


# -----------------------------
# UTIL
# -----------------------------
def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = (p.stdout or b"").decode("utf-8", errors="replace")
    err = (p.stderr or b"").decode("utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\nSTDERR:\n{err}\n\nSTDOUT:\n{out}")
    return out


def ffprobe_duration(path: Path) -> float:
    out = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path)
    ])
    j = json.loads(out)
    try:
        return float(j["format"]["duration"])
    except Exception:
        return 0.0


def clean_text(s: str) -> str:
    s = (s or "").strip()
    s = html_std.unescape(s)
    s = s.replace("\xa0", " ")
    s = s.replace("\u200b", "")
    s = " ".join(s.split())
    return s


def truncate(s: str, n: int) -> str:
    s = clean_text(s)
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def with_utm(url: str, source="youtube", medium="shorts", campaign="news_digest") -> str:
    try:
        u = urlparse(url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        q.setdefault("utm_source", source)
        q.setdefault("utm_medium", medium)
        q.setdefault("utm_campaign", campaign)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q), u.fragment))
    except Exception:
        return url


def read_news() -> list[dict]:
    p = Path(CONTENT_JSON_PATH)
    if not p.exists():
        raise RuntimeError(f"news.json not found: {CONTENT_JSON_PATH}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("news.json must be a list")
    return data


def pick_url(item: dict) -> str:
    for k in ("url", "link", "href", "source_url"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v.strip()
    return ""


def pick_title(item: dict) -> str:
    for k in ("title", "headline", "name"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def pick_summary(item: dict) -> str:
    for k in ("summary", "description", "excerpt", "text"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def pick_image(item: dict) -> str:
    for k in ("image", "image_url", "thumbnail", "thumb", "og_image", "cover"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v.strip()
    media = item.get("media")
    if isinstance(media, dict):
        for k in ("image", "thumbnail", "url"):
            v = media.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v.strip()
    return ""


def pick_date(item: dict):
    for k in ("published_at", "published", "date", "datetime", "time", "ts"):
        v = item.get(k)
        if not v:
            continue
        try:
            if isinstance(v, (int, float)):
                return datetime.fromtimestamp(float(v), tz=timezone.utc)
            if isinstance(v, str):
                d = dtparser.parse(v)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d
        except Exception:
            continue
    return None


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    else:
        st = {}

    st.setdefault("used_urls", [])
    st.setdefault("used_ids", [])
    st.setdefault("used_eps", [])  # economics episodes
    return st


def save_state(st: dict):
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


# -----------------------------
# NEWS PICKING (for MODE=news)
# -----------------------------
IMPORTANT_WORDS = [
    "полуприцеп", "прицеп", "тягач", "грузовик", "фура", "шасси",
    "ось", "тормоз", "подвеск", "шины", "ремонт", "сервис",
    "завод", "производ", "выпуск", "поставка", "дефицит",
    "цена", "рынок", "штраф", "контроль", "регламент", "гост", "санкц"
]


def score_item(item: dict) -> float:
    title = clean_text(pick_title(item)).lower()
    s = 0.0
    for w in IMPORTANT_WORDS:
        if w in title:
            s += 1.5
    d = pick_date(item)
    if d:
        age_h = max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 3600.0)
        s += max(0.0, 6.0 - min(6.0, age_h / 24.0))
    return s


def pick_news_items(news: list[dict], st: dict) -> list[dict]:
    used_urls = set(st.get("used_urls", []))
    used_ids = set(str(x) for x in st.get("used_ids", []))

    candidates = []
    for it in news:
        if not isinstance(it, dict):
            continue
        title = pick_title(it)
        url = pick_url(it)
        if not title or not url:
            continue
        _id = str(it.get("id", "")) if it.get("id") is not None else ""
        if url in used_urls:
            continue
        if _id and _id in used_ids:
            continue
        candidates.append(it)

    if len(candidates) < 3:
        candidates = [it for it in news if isinstance(it, dict) and pick_title(it) and pick_url(it)]

    if len(candidates) < 3:
        raise RuntimeError("Too few candidates for shorts (need at least 3)")

    scored = [(score_item(it), it) for it in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    top_pool = [it for _, it in scored[: max(40, PICK_TARGET * 12)]]
    random.shuffle(top_pool)

    picked = []
    for it in top_pool:
        url = pick_url(it)
        if url and all(pick_url(x) != url for x in picked):
            picked.append(it)
        if len(picked) >= PICK_TARGET:
            break

    return picked[:PICK_TARGET]


# -----------------------------
# ECONOMICS: image pool from news.json
# -----------------------------
def build_image_pool(news: list[dict], min_pool: int = 30) -> list[str]:
    imgs = []
    for it in news:
        img = pick_image(it)
        if img:
            imgs.append(img)
    uniq = list(dict.fromkeys(imgs))
    if len(uniq) >= min_pool:
        return uniq[:min_pool]
    return uniq


def pick_images_for_slides(pool: list[str], n: int, rng: random.Random) -> list[str]:
    if not pool:
        return [""] * n
    if len(pool) >= n:
        return rng.sample(pool, n)
    out = []
    for i in range(n):
        out.append(pool[i % len(pool)])
    return out


# -----------------------------
# COPYWRITING (for MODE=news)
# -----------------------------
MEANING_BANK = {
    "rules": [
        "Что это значит: выше риск проверок и штрафов — проверь документы и узлы.",
        "Что это значит: возможны новые требования — готовь технику заранее.",
    ],
    "market": [
        "Что это значит: рынок влияет на цену и сроки — планируй закупки заранее.",
        "Что это значит: стоимость владения может вырасти — следи за ценами на расходники.",
    ],
    "supply": [
        "Что это значит: сроки и наличие могут меняться — держи альтернативы.",
        "Что это значит: поставки перестраиваются — не тяни с заказами.",
    ],
    "ops": [
        "Что это значит: это про эксплуатацию — проверяй узлы, чтобы не встать в рейсе.",
        "Что это значит: диагностика дешевле простоя — следи за симптомами.",
    ],
    "logistics": [
        "Что это значит: может измениться маршрут и стоимость рейса — учитывай заранее.",
        "Что это значит: сроки доставки могут сдвигаться — держи запас по времени.",
    ],
    "other": [
        "Что это значит: влияние неочевидно — детали по ссылке.",
        "Что это значит: оцени влияние на перевозки и рынок техники.",
    ],
}


def classify(title: str) -> str:
    t = clean_text(title).lower()
    if any(k in t for k in ["штраф", "контроль", "закон", "регламент", "гост", "санкц", "сертиф", "провер"]):
        return "rules"
    if any(k in t for k in ["цена", "подорож", "дешев", "рынок", "спрос", "продаж", "пошлин", "инфляц"]):
        return "market"
    if any(k in t for k in ["завод", "выпуск", "производ", "поставка", "дефицит", "импорт", "экспорт"]):
        return "supply"
    if any(k in t for k in ["ремонт", "сервис", "тормоз", "ось", "подвеск", "шины", "тягач", "полуприцеп", "прицеп", "грузовик", "шасси"]):
        return "ops"
    if any(k in t for k in ["логистик", "перевоз", "контейнер", "терминал", "порт", "склад", "интермодал"]):
        return "logistics"
    return "other"


def meaning_for(title: str) -> str:
    c = classify(title)
    return random.choice(MEANING_BANK.get(c, MEANING_BANK["other"]))


def build_voice_text_news(items: list[dict]) -> str:
    parts = ["Новости коммерческого транспорта. Коротко."]
    for it in items:
        title = clean_text(pick_title(it))
        parts.append(f"{title}. {meaning_for(title)}")
    parts.append("Ссылки — в описании. Архив — на сайте, детали — в телеграм.")
    return " ".join(parts)


# -----------------------------
# ECONOMICS: bullet helper (more text on cards)
# -----------------------------
ECON_BULLETS = {
    "tires": [
        ["Проверь давление", "Смотри износ по краю", "Учитывай углы/схождение"],
        ["Комплект — дорогой актив", "Низкое давление убивает ресурс", "Контроль = экономия"],
        ["Простой из-за резины — боль", "Меняй вовремя, не «в ноль»", "Держи запас по рейсу"],
        ["Чек-лист контроля — в TG", "Сайт: архив разборов", "Без воды, с цифрами"],
    ],
    "downtime": [
        ["Потери растут каждый день", "Рейс не случился — минус деньги", "Плюс расходы на стоянку"],
        ["Проверь причины простоев", "ТО дешевле, чем простой", "Симптомы — ловить заранее"],
        ["3 дня простоя — уже удар", "Планируй ремонт заранее", "Следи за критичными узлами"],
        ["Чек-лист «до рейса» — в TG", "Сайт: архив", "Схемы и короткие выводы"],
    ],
    "axle": [
        ["Ось/ступица = риск простоя", "Диагностика дешевле ремонта", "Не игнорируй шум/люфт"],
        ["Смотри нагрев ступицы", "Проверяй смазку/уплотнения", "Контроль — по регламенту"],
        ["Эвакуатор + простой", "Плюс ремонт и сроки", "Лучше предотвратить заранее"],
        ["Чек-лист по оси — в TG", "Сайт: архив", "Практика без воды"],
    ],
    "overweight": [
        ["Перегруз = штраф + простой", "Риски по маршруту", "Документы и вес — под контроль"],
        ["Смотри распределение веса", "Не грузись «на глаз»", "Проверяй осевые нагрузки"],
        ["Одна ошибка — дорого", "Простой ломает экономику", "Дисциплина = прибыль"],
        ["Чек-лист по перегрузу — в TG", "Сайт: архив", "Коротко и по делу"],
    ],
    "used_buy": [
        ["Цена — не главное", "Скрытый ремонт съедает маржу", "Плюс простой на подготовке"],
        ["Смотри оси/тормоза/раму", "Пневматика и утечки", "Следы ремонта/перекоса"],
        ["Не покупай без проверки", "Диагностика окупается", "Торг — только с фактами"],
        ["Чек-лист осмотра — в TG", "Сайт: архив", "Без воды, по пунктам"],
    ],
}


def econ_subtitle(ep_key: str, slide_idx_1based: int, fallback: str) -> str:
    bullets = ECON_BULLETS.get(ep_key)
    if bullets and 1 <= slide_idx_1based <= len(bullets):
        return "\n".join(bullets[slide_idx_1based - 1][:3])
    return fallback or ""


# -----------------------------
# CARD RENDER (Pillow)
# -----------------------------
def ensure_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in candidates:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def download_image(url: str, out: Path) -> bool:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.content:
            return False
        out.write_bytes(r.content)
        return True
    except Exception:
        return False


def load_logo_rgba() -> Image.Image:
    raw = (LOGO_PATH or "").strip()
    raw = os.path.expandvars(os.path.expanduser(raw))

    candidates = []
    if raw:
        candidates.append(Path(raw))

    ws = os.getenv("GITHUB_WORKSPACE", "").strip()
    if ws and raw:
        candidates.append(Path(ws) / raw.lstrip("/\\"))
        candidates.append(Path(ws) / raw.replace("\\", "/").lstrip("/"))

    if ws:
        candidates.append(Path(ws) / "frontend" / "spec_avtoportal_favicon.ico")

    for p in candidates:
        if p.exists():
            return Image.open(p).convert("RGBA")

    raise RuntimeError(f"Logo not found. Tried: {[str(c) for c in candidates]}")


def wrap_by_chars(text: str, max_chars: int) -> list[str]:
    words = clean_text(text).split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def add_bottom_gradient(img: Image.Image, start_y: int, end_y: int, color=(0, 0, 0), max_alpha=220) -> Image.Image:
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = overlay.load()
    start_y = max(0, min(h - 1, start_y))
    end_y = max(0, min(h, end_y))
    if end_y <= start_y:
        return img

    for y in range(start_y, end_y):
        t = (y - start_y) / max(1, (end_y - start_y))
        a = int(t * max_alpha)
        for x in range(w):
            px[x, y] = (color[0], color[1], color[2], a)

    out = Image.alpha_composite(img.convert("RGBA"), overlay)
    return out.convert("RGB")


def parse_bullets(subtitle: str) -> list[str]:
    subtitle = (subtitle or "").strip()
    if not subtitle:
        return []
    # если пришло с \n — считаем это пунктами
    if "\n" in subtitle:
        lines = [clean_text(x) for x in subtitle.split("\n") if clean_text(x)]
        return lines[:3]
    # иначе: делаем 2-3 строки авто-переносом
    return wrap_by_chars(subtitle, 36)[:3]


def make_card_generic(
    idx: int,
    title: str,
    subtitle: str,
    image_url: str,
    source_url: str,
    logo: Image.Image,
    out_png: Path
):
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT

    title = truncate(title, 88)

    # subtitle в economics будет буллетами; в news — обрежем и тоже сделаем читаемо
    subtitle = truncate(subtitle, min(SUMMARY_MAX, 140))

    domain = ""
    if source_url:
        try:
            domain = urlparse(source_url).netloc.replace("www.", "")
        except Exception:
            domain = ""

    BG = (10, 12, 16)
    WHITE = (255, 255, 255)
    GRAY = (210, 210, 210)
    YELLOW = (255, 196, 0)

    base = Image.new("RGB", (W, H), BG)

    news_img = None
    if image_url:
        img_path = ASSETS_DIR / f"img_{idx:02d}.bin"
        if download_image(image_url, img_path):
            try:
                news_img = Image.open(img_path).convert("RGB")
            except Exception:
                news_img = None

    if news_img is not None:
        bg = news_img.copy().resize((W, H))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=16))
        base = Image.blend(base, bg, alpha=0.62)

        pic = news_img.copy()
        pic.thumbnail((int(W * 0.92), int(H * 0.55)))
        px = (W - pic.size[0]) // 2
        py = int(H * 0.12)

        shadow = Image.new("RGBA", (pic.size[0] + 30, pic.size[1] + 30), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rectangle([15, 15, 15 + pic.size[0], 15 + pic.size[1]], fill=(0, 0, 0, 140))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
        base_rgba = base.convert("RGBA")
        base_rgba.paste(shadow, (px - 15, py - 15), shadow)
        base_rgba.paste(pic, (px, py))
        base = base_rgba.convert("RGB")

    # усиливаем читаемость низа
    base = add_bottom_gradient(base, start_y=int(H * 0.50), end_y=H, max_alpha=240)
    draw = ImageDraw.Draw(base)

    font_paths_bold = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    font_paths_reg = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    f_brand = ensure_font(font_paths_bold, 40)
    f_sub = ensure_font(font_paths_reg, 30)
    f_title = ensure_font(font_paths_bold, 64)
    f_bul = ensure_font(font_paths_reg, 40)
    f_small = ensure_font(font_paths_reg, 30)

    # top bar
    bar_h = 82
    draw.rectangle([0, 0, W, bar_h], fill=(0, 0, 0))

    lg = logo.copy()
    lg.thumbnail((54, 54))
    base.paste(lg, (20, 14), lg)

    draw.text((86, 14), "SpecAvtoPortal", font=f_brand, fill=WHITE)
    draw.text((86, 48), "Shorts • Экономика владения", font=f_sub, fill=(170, 170, 170))

    # badge idx
    badge_r = 30
    bx, by = W - 20 - badge_r * 2, 11
    draw.ellipse([bx, by, bx + badge_r * 2, by + badge_r * 2], fill=YELLOW)
    draw.text((bx + 21, by + 12), str(idx), font=f_brand, fill=(0, 0, 0))

    left = 56
    y = int(H * 0.62)

    # title lines
    t_lines = wrap_by_chars(title.upper(), 22)[:2]
    for ln in t_lines:
        draw.text((left, y), ln, font=f_title, fill=WHITE)
        y += 76

    # bullets (2-3)
    bullets = parse_bullets(subtitle)
    if bullets:
        y += 6
        for b in bullets[:3]:
            b = clean_text(b)
            if not b:
                continue
            # небольшой авто-перенос внутри буллета
            sublines = wrap_by_chars(b, 34)[:1]
            for sl in sublines:
                draw.text((left, y), f"• {sl}", font=f_bul, fill=GRAY)
                y += 54

    # bottom CTA
    line_y = H - 140
    draw.rectangle([left, line_y, W - left, line_y + 6], fill=YELLOW)
    draw.text((left, H - 118), "Разбор и чек-листы — в Telegram • Архив — на сайте", font=f_small, fill=WHITE)

    if domain:
        draw.text((left, H - 78), f"Источник: {domain}", font=f_small, fill=(190, 190, 190))

    base.save(out_png, "PNG")


def make_intro_card(logo: Image.Image, out_png: Path):
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    BG = (0, 0, 0)
    YELLOW = (255, 196, 0)
    WHITE = (255, 255, 255)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    font_paths_bold = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    font_paths_reg = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    f1 = ensure_font(font_paths_bold, 92)
    f2 = ensure_font(font_paths_bold, 54)
    f3 = ensure_font(font_paths_reg, 40)

    lg = logo.copy()
    lg.thumbnail((160, 160))
    img.paste(lg, (70, 120), lg)

    draw.text((70, 320), "ЭКОНОМИКА", font=f1, fill=WHITE)
    draw.text((70, 420), "ПОЛУПРИЦЕПЫ • ПРИЦЕПЫ", font=f2, fill=WHITE)
    draw.rectangle([70, 510, 520, 518], fill=YELLOW)
    draw.text((70, 540), "коротко • по пунктам • без воды", font=f3, fill=(210, 210, 210))

    img.save(out_png, "PNG")


def make_outro_card(logo: Image.Image, out_png: Path):
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    BG = (8, 10, 14)
    YELLOW = (255, 196, 0)
    WHITE = (255, 255, 255)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    font_paths_bold = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    font_paths_reg = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    f1 = ensure_font(font_paths_bold, 72)
    f2 = ensure_font(font_paths_bold, 46)
    f3 = ensure_font(font_paths_reg, 40)

    lg = logo.copy()
    lg.thumbnail((130, 130))
    img.paste(lg, (70, 90), lg)

    draw.text((70, 260), "Ссылки и детали", font=f1, fill=WHITE)
    draw.rectangle([70, 350, 520, 358], fill=YELLOW)

    draw.text((70, 400), "Telegram:", font=f2, fill=WHITE)
    draw.text((70, 470), TELEGRAM_URL, font=f3, fill=YELLOW)

    draw.text((70, 580), "Сайт:", font=f2, fill=WHITE)
    draw.text((70, 650), SITE_URL, font=f3, fill=YELLOW)

    img.save(out_png, "PNG")


# -----------------------------
# TTS + AUDIO FIT
# -----------------------------
async def edge_tts_to_wav(text: str, out_wav: Path):
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=TTS_RATE)
    await communicate.save(str(out_wav))


def gtts_to_wav(text: str, out_wav: Path):
    mp3_path = out_wav.with_suffix(".mp3")
    tts = gTTS(text=text, lang="ru")
    tts.save(str(mp3_path))
    run(["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "44100", "-ac", "1", str(out_wav)])


def atempo_filter(speed: float) -> str:
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5 and s > 0:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def fit_audio_to_target(in_wav: Path, out_wav: Path, target_sec: float):
    dur = ffprobe_duration(in_wav)
    if dur <= 0.01:
        shutil.copyfile(in_wav, out_wav)
        return

    if dur <= target_sec:
        shutil.copyfile(in_wav, out_wav)
        return

    speed = dur / target_sec
    speed = min(speed, 1.35)

    af = atempo_filter(speed)
    run(["ffmpeg", "-y", "-i", str(in_wav), "-filter:a", af, "-ar", "44100", "-ac", "1", str(out_wav)])


def tts_generate(text: str, out_wav: Path):
    tmp = out_wav.with_name(out_wav.stem + "_raw.wav")
    try:
        asyncio.run(edge_tts_to_wav(text, tmp))
        print("[TTS] edge-tts OK rate=", TTS_RATE)
    except Exception as e:
        print("[TTS] edge-tts failed, fallback to gTTS:", repr(e))
        gtts_to_wav(text, tmp)
        print("[TTS] gTTS OK")

    if AUDIO_FIT:
        target_audio = max(5.0, TOTAL_SECONDS - 0.25)
        fit_audio_to_target(tmp, out_wav, target_audio)
        print("[TTS] audio fit:", ffprobe_duration(tmp), "->", ffprobe_duration(out_wav))
    else:
        shutil.copyfile(tmp, out_wav)

    tmp.unlink(missing_ok=True)


# -----------------------------
# VIDEO
# -----------------------------
def compute_durations_from_audio(n_slides: int, audio_sec: float) -> list[float]:
    target_total = min(TOTAL_SECONDS, max(audio_sec, 10.0))
    available = max(3.0, target_total - INTRO_SECONDS - OUTRO_SECONDS)

    per = available / max(1, n_slides)
    per = min(10.0, max(5.5, per))

    durs = [per] * n_slides
    s = sum(durs)
    if s > 0:
        factor = available / s
        durs = [x * factor for x in durs]

    return [INTRO_SECONDS] + durs + [OUTRO_SECONDS]


def ffmpeg_slideshow(pngs: list[Path], durations: list[float], audio_wav: Path, out_mp4: Path):
    if len(pngs) != len(durations):
        raise ValueError("pngs and durations must match")

    cmd = ["ffmpeg", "-y"]
    for p, d in zip(pngs, durations):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(p)]

    cmd += ["-i", str(audio_wav)]

    n = len(pngs)
    inputs = "".join([f"[{i}:v]" for i in range(n)])
    vf = f"{inputs}concat=n={n}:v=1:a=0,format=yuv420p[v]"

    cmd += [
        "-filter_complex", vf,
        "-map", "[v]",
        "-map", f"{n}:a",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(out_mp4),
    ]
    run(cmd)


# -----------------------------
# YOUTUBE upload + thumbnail
# -----------------------------
def youtube_upload(video_path: Path, title: str, description: str, privacy: str = "public") -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_file = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")
    privacy = os.getenv("YOUTUBE_PRIVACY", privacy)

    creds = Credentials.from_authorized_user_file(token_file, scopes=["https://www.googleapis.com/auth/youtube.upload"])
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(token_file).write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "19",
            "tags": ["полуприцеп", "прицеп", "тягач", "грузовик", "логистика", "перевозки", "экономика"],
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    vid = resp.get("id")
    print("Uploaded video id:", vid)
    return vid


def youtube_set_thumbnail(video_id: str, thumb_path: Path):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_file = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")

    creds = Credentials.from_authorized_user_file(token_file, scopes=["https://www.googleapis.com/auth/youtube.upload"])
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(token_file).write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)

    media = MediaFileUpload(str(thumb_path), mimetype="image/png")
    req = youtube.thumbnails().set(videoId=video_id, media_body=media)
    resp = req.execute()
    print("Thumbnail set response:", resp)


# -----------------------------
# MAIN
# -----------------------------
def main():
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    st = load_state()
    news = read_news()
    logo = load_logo_rgba()
    img_pool = build_image_pool(news, min_pool=30)

    yt_title = ""
    voice_text = ""
    caption_lines: list[str] = []

    slides_to_render: list[dict] = []
    used_urls_add: list[str] = []
    used_ids_add: list[str] = []
    used_eps_add: list[str] = []

    if MODE == "economics":
        seed = int(ECON_SEED) if ECON_SEED.isdigit() else None
        allowed = [x.strip() for x in ECON_ALLOWED.split(",") if x.strip()] if ECON_ALLOWED else None

        used_eps = set(st.get("used_eps", []))
        rng = random.Random(seed if seed is not None else random.randrange(1_000_000_000))

        if ECON_FORCE_KEY:
            ep = pick_random_episode(seed=seed, tg_url=TELEGRAM_URL, site_url=SITE_URL, allowed=[ECON_FORCE_KEY])
        else:
            ep = None
            for _ in range(10):
                cand = pick_random_episode(seed=rng.randrange(1_000_000_000), tg_url=TELEGRAM_URL, site_url=SITE_URL, allowed=allowed)
                if cand.key not in used_eps:
                    ep = cand
                    break
            if ep is None:
                ep = pick_random_episode(seed=rng.randrange(1_000_000_000), tg_url=TELEGRAM_URL, site_url=SITE_URL, allowed=allowed)

        used_eps_add.append(ep.key)

        yt_title = ep.title
        voice_text = ep.voice_text
        caption_lines = ep.description_lines[:]

        imgs = pick_images_for_slides(img_pool, len(ep.slides), rng)

        for i, s in enumerate(ep.slides, 1):
            assert isinstance(s, EconSlide)
            # ✅ больше текста: 2–3 буллета снизу (без цифр на первом слайде)
            sub = econ_subtitle(ep.key, i, s.subtitle or "")
            slides_to_render.append({
                "idx": i,
                "title": s.title,
                "subtitle": sub,
                "image_url": imgs[i - 1] if imgs else "",
                "source_url": "",
            })

        caption_lines += ["", f"Telegram: {TELEGRAM_URL}", f"Сайт: {SITE_URL}"]

    else:
        items = pick_news_items(news, st)
        voice_text = build_voice_text_news(items)
        today = datetime.now().strftime("%d.%m.%Y")
        yt_title = f"Новости тягачей и полуприцепов — {today}"

        for i, it in enumerate(items, 1):
            slides_to_render.append({
                "idx": i,
                "title": pick_title(it),
                "subtitle": truncate(pick_summary(it), min(SUMMARY_MAX, 140)),
                "image_url": pick_image(it),
                "source_url": pick_url(it),
            })

            u = pick_url(it)
            if u:
                used_urls_add.append(u)
            if it.get("id") is not None:
                used_ids_add.append(str(it.get("id")))

        site_link = with_utm(SITE_URL, source="youtube", medium="shorts", campaign="news_short")
        tg_link = with_utm(TELEGRAM_URL, source="youtube", medium="shorts", campaign="news_short")

        caption_lines = [
            "Короткая сводка: 3–4 новости + что это значит для эксплуатации.",
            "",
            f"Telegram (детали): {tg_link}",
            f"Сайт (архив): {site_link}",
            "",
            "Источники:",
        ]
        for it in items:
            u = pick_url(it)
            if u:
                caption_lines.append(with_utm(u, source="youtube", medium="shorts", campaign="news_short"))

    # ---- RENDER CARDS ----
    intro_png = CARDS_DIR / "00_intro.png"
    make_intro_card(logo, intro_png)

    slide_pngs = []
    for s in slides_to_render:
        out_png = CARDS_DIR / f"{int(s['idx']):02d}.png"
        make_card_generic(
            idx=int(s["idx"]),
            title=str(s["title"]),
            subtitle=str(s["subtitle"]),
            image_url=str(s["image_url"]),
            source_url=str(s["source_url"]),
            logo=logo,
            out_png=out_png
        )
        slide_pngs.append(out_png)

    outro_png = CARDS_DIR / "99_outro.png"
    make_outro_card(logo, outro_png)

    # thumbnail = first slide
    thumb_png = OUT_DIR / "thumbnail.png"
    Image.open(slide_pngs[0]).save(thumb_png, "PNG")

    # ---- AUDIO ----
    audio_wav = TMP_DIR / "voice.wav"
    tts_generate(voice_text, audio_wav)
    audio_sec = ffprobe_duration(audio_wav)

    # durations from audio
    pngs = [intro_png] + slide_pngs + [outro_png]
    durs = compute_durations_from_audio(len(slides_to_render), audio_sec)

    # ---- VIDEO ----
    out_video = OUT_DIR / "shorts_news.mp4"
    ffmpeg_slideshow(pngs, durs, audio_wav, out_video)

    # ---- CAPTION ----
    description = "\n".join(caption_lines).strip()
    (OUT_DIR / "caption.txt").write_text(description, encoding="utf-8")

    # ---- UPLOAD ----
    video_id = youtube_upload(out_video, title=yt_title, description=description, privacy=os.getenv("YOUTUBE_PRIVACY", "public"))
    youtube_set_thumbnail(video_id, thumb_png)

    # ---- UPDATE STATE ----
    used_urls = list(dict.fromkeys(st.get("used_urls", []) + used_urls_add))
    used_ids = list(dict.fromkeys([str(x) for x in st.get("used_ids", [])] + used_ids_add))
    used_eps = list(dict.fromkeys([str(x) for x in st.get("used_eps", [])] + used_eps_add))

    st["used_urls"] = used_urls[-2000:]
    st["used_ids"] = used_ids[-2000:]
    st["used_eps"] = used_eps[-500:]

    save_state(st)

    print("[OK] MODE=", MODE, "audio_sec=", audio_sec, "video=", out_video, "video_id=", video_id, "title=", yt_title)


if __name__ == "__main__":
    main()
