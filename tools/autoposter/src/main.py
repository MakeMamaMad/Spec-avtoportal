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


# -----------------------------
# CONFIG (env)
# -----------------------------
SITE_URL = os.getenv("SITE_URL", "https://spec-avtoportal.ru/").strip()
TELEGRAM_URL = os.getenv("TELEGRAM_URL", "https://t.me/specavtoportal").strip()
CONTENT_JSON_PATH = os.getenv("CONTENT_JSON_PATH", "frontend/data/news.json").strip()

VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1920"))
FPS = int(os.getenv("FPS", "30"))

TOTAL_SECONDS = float(os.getenv("TOTAL_SECONDS", "30"))
INTRO_SECONDS = float(os.getenv("INTRO_SECONDS", "1.5"))
OUTRO_SECONDS = float(os.getenv("OUTRO_SECONDS", "2.5"))

PICK_TARGET = int(os.getenv("PICK_TARGET", "4"))  # будет резать до 3 при длинной озвучке

VOICE = os.getenv("VOICE", "ru-RU-DmitryNeural").strip()
TTS_RATE = os.getenv("TTS_RATE", "-10%").strip()

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


def clean_text(s: str) -> str:
    s = (s or "").strip()
    # ✅ убираем HTML сущности типа &nbsp;
    s = html_std.unescape(s)
    s = s.replace("\xa0", " ")
    s = s.replace("\u200b", "")  # zero-width
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
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"used_urls": [], "used_ids": []}


def save_state(st: dict):
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def read_news() -> list[dict]:
    p = Path(CONTENT_JSON_PATH)
    if not p.exists():
        raise RuntimeError(f"news.json not found: {CONTENT_JSON_PATH}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("news.json must be a list")
    return data


# -----------------------------
# PICK NEWS (random, no repeats)
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
        candidates = []
        for it in news:
            if not isinstance(it, dict):
                continue
            title = pick_title(it)
            url = pick_url(it)
            if not title or not url:
                continue
            if url in used_urls:
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
# COPYWRITING ("what it means")
# -----------------------------
MEANING_BANK = {
    "rules": [
        "Что это значит: выше риск проверок и штрафов — проверь документы, свет, крепёж и узлы перед рейсом.",
        "Что это значит: возможны новые требования — подготовь технику и документы заранее, чтобы не ловить простой.",
    ],
    "market": [
        "Что это значит: рынок качает — это влияет на цены и сроки. Закладывай запас по бюджету и планируй закупки заранее.",
        "Что это значит: возможны изменения стоимости владения — проверь цены на технику и расходники.",
    ],
    "supply": [
        "Что это значит: могут измениться сроки и наличие — держи альтернативы и планируй ремонты заранее.",
        "Что это значит: цепочки поставок меняются — уточняй сроки у поставщиков и не тяни с заказами.",
    ],
    "ops": [
        "Что это значит: это про эксплуатацию — проверь узлы и регламент ТО, чтобы не встать в рейсе.",
        "Что это значит: проблему лучше поймать заранее — диагностика дешевле простоя.",
    ],
    "logistics": [
        "Что это значит: меняются условия перевозок — это влияет на сроки и расходы на рейс.",
        "Что это значит: возможна перестройка маршрутов — держи альтернативные окна и направления.",
    ],
    "other": [
        "Что это значит: новость смежная — оцени влияние на перевозки и рынок техники.",
        "Что это значит: влияние неочевидно — смотри детали по ссылке.",
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


def build_voice_text(items: list[dict]) -> str:
    parts = ["Главные новости по коммерческому транспорту. Коротко."]
    for it in items:
        title = clean_text(pick_title(it))
        parts.append(f"Новость: {title}. {meaning_for(title)}")
    parts.append("Ссылки и детали — в телеграм. Архив — на сайте Спек Автопортал.")
    return " ".join(parts)


def estimate_speech_seconds(text: str) -> float:
    words = len(text.split())
    return max(10.0, words / 2.4)


# -----------------------------
# CARD RENDER (Pillow) — REDESIGN v2 (YouTube-aggressive)
# -----------------------------
def ensure_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in candidates:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def download_image(url: str, out: Path) -> bool:
    try:
        r = requests.get(url, timeout=20)
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
    """Градиент снизу: прозрачный -> чёрный."""
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


def make_card(idx: int, item: dict, logo: Image.Image, out_png: Path):
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT

    # агрессивнее: титул чуть короче, summary 1 строка
    title = truncate(pick_title(item), 88)
    summary = truncate(pick_summary(item), min(SUMMARY_MAX, 90))

    url = pick_url(item)
    domain = ""
    try:
        domain = urlparse(url).netloc.replace("www.", "")
    except Exception:
        domain = ""

    # цвета
    BG = (10, 12, 16)
    WHITE = (255, 255, 255)
    GRAY = (210, 210, 210)
    YELLOW = (255, 196, 0)

    base = Image.new("RGB", (W, H), BG)

    # фон: картинка размытой подложкой (если есть)
    img_url = pick_image(item)
    img_path = ASSETS_DIR / f"img_{idx:02d}.bin"
    news_img = None
    if img_url and download_image(img_url, img_path):
        try:
            news_img = Image.open(img_path).convert("RGB")
        except Exception:
            news_img = None

    if news_img is not None:
        bg = news_img.copy().resize((W, H))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=16))
        base = Image.blend(base, bg, alpha=0.62)

        # основной кадр: без жирной рамки, просто аккуратный "карточный" блок
        pic = news_img.copy()
        pic.thumbnail((int(W * 0.92), int(H * 0.55)))
        px = (W - pic.size[0]) // 2
        py = int(H * 0.12)

        # легкая тень
        shadow = Image.new("RGBA", (pic.size[0] + 30, pic.size[1] + 30), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rectangle([15, 15, 15 + pic.size[0], 15 + pic.size[1]], fill=(0, 0, 0, 140))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
        base_rgba = base.convert("RGBA")
        base_rgba.paste(shadow, (px - 15, py - 15), shadow)
        base_rgba.paste(pic, (px, py))
        base = base_rgba.convert("RGB")
    else:
        # если нет картинки — просто фон + градиент
        pass

    # градиент снизу под текст
    base = add_bottom_gradient(base, start_y=int(H * 0.52), end_y=H, max_alpha=235)

    draw = ImageDraw.Draw(base)

    # шрифты
    font_paths_bold = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    font_paths_reg = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    f_brand = ensure_font(font_paths_bold, 40)
    f_sub = ensure_font(font_paths_reg, 30)
    f_title = ensure_font(font_paths_bold, 64)   # крупнее
    f_sum = ensure_font(font_paths_reg, 38)
    f_small = ensure_font(font_paths_reg, 30)

    # верхняя "лента" компактнее
    bar_h = 82
    draw.rectangle([0, 0, W, bar_h], fill=(0, 0, 0))

    lg = logo.copy()
    lg.thumbnail((54, 54))
    base.paste(lg, (20, 14), lg)

    draw.text((86, 14), "SpecAvtoPortal", font=f_brand, fill=WHITE)
    draw.text((86, 48), "Shorts • Новости рынка", font=f_sub, fill=(170, 170, 170))

    # номер в желтом кружке (оставляем)
    badge_r = 30
    bx, by = W - 20 - badge_r * 2, 11
    draw.ellipse([bx, by, bx + badge_r * 2, by + badge_r * 2], fill=YELLOW)
    draw.text((bx + 21, by + 12), str(idx), font=f_brand, fill=(0, 0, 0))

    # текстовая зона (агрессивный стиль)
    left = 56
    y = int(H * 0.62)

    # заголовок: 2 строки макс
    t_lines = wrap_by_chars(title.upper(), 22)[:2]
    for ln in t_lines:
        draw.text((left, y), ln, font=f_title, fill=WHITE)
        y += 76

    # summary: 1 строка макс
    if summary:
        y += 6
        s_line = wrap_by_chars(summary, 40)[:1]
        for ln in s_line:
            draw.text((left, y), ln, font=f_sum, fill=GRAY)
            y += 48

    # нижний акцент: желтая линия + CTA
    line_y = H - 140
    draw.rectangle([left, line_y, W - left, line_y + 6], fill=YELLOW)

    draw.text((left, H - 118), "Подробности — в Telegram • Архив — на сайте", font=f_small, fill=WHITE)

    # источник
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

    draw.text((70, 320), "НОВОСТИ", font=f1, fill=WHITE)
    draw.text((70, 420), "ТЯГАЧИ • ПОЛУПРИЦЕПЫ", font=f2, fill=WHITE)
    draw.rectangle([70, 510, 520, 518], fill=YELLOW)
    draw.text((70, 540), "за 30 секунд • без воды", font=f3, fill=(210, 210, 210))

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

    draw.text((70, 780), "Подписывайся — 6 роликов в сутки", font=f3, fill=(210, 210, 210))

    img.save(out_png, "PNG")


def compute_slide_durations(n_items: int) -> list[float]:
    available = TOTAL_SECONDS - INTRO_SECONDS - OUTRO_SECONDS
    per = available / max(1, n_items)
    per = min(10.0, max(6.0, per))
    durs = [per] * n_items
    s = sum(durs)
    if s != 0:
        factor = available / s
        durs = [x * factor for x in durs]
    return durs


# -----------------------------
# TTS: edge-tts -> fallback gTTS
# -----------------------------
async def edge_tts_to_wav(text: str, out_wav: Path):
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=TTS_RATE)
    await communicate.save(str(out_wav))


def gtts_to_wav(text: str, out_wav: Path):
    mp3_path = out_wav.with_suffix(".mp3")
    tts = gTTS(text=text, lang="ru")
    tts.save(str(mp3_path))
    run(["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "44100", "-ac", "1", str(out_wav)])


def tts_generate(text: str, out_wav: Path):
    try:
        asyncio.run(edge_tts_to_wav(text, out_wav))
        print("[TTS] edge-tts OK")
        return
    except Exception as e:
        print("[TTS] edge-tts failed, fallback to gTTS:", repr(e))
    gtts_to_wav(text, out_wav)
    print("[TTS] gTTS OK")


# -----------------------------
# VIDEO (ffmpeg slideshow)
# -----------------------------
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
            "tags": ["полуприцеп", "тягач", "грузовик", "логистика", "перевозки", "новости"],
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

    items = pick_news_items(news, st)

    voice_text = build_voice_text(items)
    if estimate_speech_seconds(voice_text) > TOTAL_SECONDS + 2 and len(items) >= 4:
        items = items[:3]
        voice_text = build_voice_text(items)

    logo = load_logo_rgba()

    intro_png = CARDS_DIR / "00_intro.png"
    make_intro_card(logo, intro_png)

    slide_pngs = []
    for i, it in enumerate(items, 1):
        out_png = CARDS_DIR / f"{i:02d}.png"
        make_card(i, it, logo, out_png)
        slide_pngs.append(out_png)

    outro_png = CARDS_DIR / "99_outro.png"
    make_outro_card(logo, outro_png)

    # thumbnail: первая карточка
    thumb_png = OUT_DIR / "thumbnail.png"
    Image.open(slide_pngs[0]).save(thumb_png, "PNG")

    slide_durs = compute_slide_durations(len(items))
    pngs = [intro_png] + slide_pngs + [outro_png]
    durs = [INTRO_SECONDS] + slide_durs + [OUTRO_SECONDS]

    audio_wav = TMP_DIR / "voice.wav"
    tts_generate(voice_text, audio_wav)

    out_video = OUT_DIR / "shorts_news.mp4"
    ffmpeg_slideshow(pngs, durs, audio_wav, out_video)

    today = datetime.now().strftime("%d.%m.%Y")
    title = f"Новости тягачей и полуприцепов — {today}"

    site_link = with_utm(SITE_URL, source="youtube", medium="shorts", campaign="news_short")
    tg_link = with_utm(TELEGRAM_URL, source="youtube", medium="shorts", campaign="news_short")

    lines = [
        "Короткая сводка: 3–4 новости + что это значит для эксплуатации.",
        "",
        f"Telegram (детали): {tg_link}",
        f"Сайт (архив): {site_link}",
        "",
        "Источники:",
    ]
    for it in items:
        u = pick_url(it)
        lines.append(with_utm(u, source="youtube", medium="shorts", campaign="news_short"))

    description = "\n".join(lines)
    (OUT_DIR / "caption.txt").write_text(description, encoding="utf-8")

    video_id = youtube_upload(out_video, title=title, description=description, privacy=os.getenv("YOUTUBE_PRIVACY", "public"))
    youtube_set_thumbnail(video_id, thumb_png)

    used_urls = list(dict.fromkeys(st.get("used_urls", []) + [pick_url(it) for it in items if pick_url(it)]))
    used_ids = list(dict.fromkeys([str(x) for x in st.get("used_ids", [])] + [str(it.get("id")) for it in items if it.get("id") is not None]))

    st["used_urls"] = used_urls[-2000:]
    st["used_ids"] = used_ids[-2000:]
    save_state(st)

    print("[OK] Generated and uploaded:", out_video, "video_id=", video_id)


if __name__ == "__main__":
    main()
