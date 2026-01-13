import hashlib
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..config import cfg
from ..content.digest import Slide


# ----------------- Helpers -----------------
def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(p):
        return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int):
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _ffmpeg_exists():
    subprocess.check_call(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _guess_ext_from_url(url: str) -> str:
    base = url.split("?", 1)[0].split("#", 1)[0]
    ext = Path(base).suffix.lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        return ext
    return ".img"


def _download_image(url: str, out_path: Path, timeout: int = 25) -> Optional[Path]:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SpecAvtoPortal Autoposter)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        return out_path
    except Exception as e:
        print(f"[img] FAILED: {url} err={e}")
        return None


def _ensure_png(src_path: Path, dst_png: Path) -> Optional[Path]:
    try:
        img = Image.open(src_path).convert("RGB")
        img.save(dst_png)
        return dst_png
    except Exception:
        try:
            subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src_path), str(dst_png)])
            return dst_png if dst_png.exists() else None
        except Exception as e2:
            print(f"[img] convert FAILED ({src_path.name}): {e2}")
            return None


def _cover_crop(im: Image.Image, W: int, H: int) -> Image.Image:
    iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return Image.new("RGB", (W, H), (20, 20, 24))
    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    im2 = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    return im2.crop((left, top, left + W, top + H))


def _rounded(draw: ImageDraw.ImageDraw, box, r: int, fill, outline=None, width: int = 1):
    try:
        draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)
    except Exception:
        draw.rectangle(box, fill=fill, outline=outline, width=width)


def _load_logo() -> Optional[Image.Image]:
    # tools/autoposter/assets/logo.png
    logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    if logo_path.exists():
        try:
            return Image.open(logo_path).convert("RGBA")
        except Exception:
            return None
    return None


def _news_num(header: str) -> str:
    digits = "".join([c for c in (header or "") if c.isdigit()])
    return digits or ""


def _is_news(slide: Slide) -> bool:
    return "новость" in (slide.header or "").lower()


def _choose_template(slide: Slide) -> str:
    # Можно форсировать через ENV: TEMPLATE_FORCE=A/D/E
    forced = (os.getenv("TEMPLATE_FORCE") or "").strip().upper()
    if forced in {"A", "D", "E"}:
        return forced

    # title/cta можно тоже рандомить, но чаще приятнее стабильно
    # оставим: title -> D, cta -> A
    k = (getattr(slide, "key", None) or slide.header or "x").encode("utf-8")
    h = int(hashlib.md5(k).hexdigest(), 16)
    if not _is_news(slide):
        return "D" if "топ" in (slide.header or "").lower() else "A"

    return ["A", "D", "E"][h % 3]


# ----------------- Templates -----------------
def _draw_topbar_common(img: Image.Image, d: ImageDraw.ImageDraw, W: int, pad: int, top_h: int, style: str, header: str):
    logo = _load_logo()
    x = pad
    if logo:
        lw = int(top_h * 0.70)
        try:
            ow, oh = logo.size
            sc = lw / max(1, ow)
            logo2 = logo.resize((lw, int(oh * sc)), Image.LANCZOS)
            img.alpha_composite(logo2, (x, int((top_h - logo2.size[1]) / 2)))
            x += lw + int(pad * 0.35)
        except Exception:
            pass

    # надпись “Новости” + номер без #
    if _is_news(Slide(header=header, lines=[], footer="", seconds=1)):  # quick check
        num = _news_num(header)
        if style == "D":
            top_font = _font(int(top_h * 0.36), True)
            d.text((x, int(top_h * 0.25)), "Новости", font=top_font, fill=(20, 20, 20))
            if num:
                d.text((x + int(d.textlength("Новости", font=top_font)) + int(pad * 0.4), int(top_h * 0.25)),
                       num, font=top_font, fill=(220, 120, 0))
        else:
            top_font = _font(int(top_h * 0.34), True)
            d.text((x, int(top_h * 0.22)), "Новости", font=top_font, fill=(255, 255, 255))
            if num:
                # маленький бейдж
                badge_font = _font(int(top_h * 0.38), True)
                bw = int(d.textlength(num, font=badge_font)) + int(pad * 0.6)
                bh = int(top_h * 0.72)
                bx = x + int(d.textlength("Новости", font=top_font)) + int(pad * 0.5)
                by = int((top_h - bh) / 2)
                _rounded(d, [bx, by, bx + bw, by + bh], r=int(bh * 0.35), fill=(255, 140, 0, 235))
                d.text((bx + int(pad * 0.25), int(top_h * 0.18)), num, font=badge_font, fill=(15, 15, 15))


def _render_A(slide: Slide, out_png: Path):
    # Modern media card: фото сверху + белая карточка снизу
    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT
    pad = 60 if W >= 1080 else 36
    r = 36 if W >= 1080 else 26

    img_h = int(H * 0.55)
    base = Image.new("RGB", (W, H), (235, 238, 242))

    # top image
    if slide.image_url:
        work = out_png.parent
        ext = _guess_ext_from_url(slide.image_url)
        raw = work / "images" / f"img_{out_png.stem}{ext}"
        saved = _download_image(slide.image_url, raw)
        if saved:
            png = work / "images" / f"img_{out_png.stem}.png"
            ok = _ensure_png(saved, png)
            if ok and ok.exists():
                im = Image.open(ok).convert("RGB")
                top = _cover_crop(im, W, img_h)
                # легкий градиент для читаемости
                top = top.filter(ImageFilter.GaussianBlur(radius=1))
                base.paste(top, (0, 0))

    img = base.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # top bar
    topbar_h = int(pad * 1.6)
    d.rectangle([0, 0, W, topbar_h], fill=(0, 0, 0, 95))
    _draw_topbar_common(img, d, W, pad, topbar_h, "A", slide.header)

    # white card
    card_top = img_h - int(pad * 0.2)
    card = [pad, card_top, W - pad, H - pad]
    # shadow
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow, "RGBA")
    _rounded(sd, [card[0] + 6, card[1] + 10, card[2] + 6, card[3] + 10], r=r, fill=(0, 0, 0, 60))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
    img.alpha_composite(shadow)

    _rounded(d, card, r=r, fill=(255, 255, 255, 245), outline=(220, 225, 232, 255), width=2)

    # accent line
    d.rectangle([card[0], card[1], card[2], card[1] + int(pad * 0.18)], fill=(255, 140, 0, 255))

    title_font = _font(56 if W >= 1080 else 38, True)
    body_font = _font(40 if W >= 1080 else 28, False)
    footer_font = _font(34 if W >= 1080 else 24, False)

    tx = card[0] + int(pad * 0.8)
    ty = card[1] + int(pad * 0.65)
    max_w = card[2] - tx - int(pad * 0.8)

    title = (slide.lines[0] if slide.lines else "")
    summary = (slide.lines[1] if len(slide.lines) > 1 else "")

    for l in _wrap(d, title, title_font, max_w)[:3]:
        d.text((tx, ty), l, font=title_font, fill=(18, 24, 34, 255))
        ty += int(title_font.size * 1.15)

    ty += int(pad * 0.25)

    # summary (не повтор заголовка — уже в digest.py)
    for l in _wrap(d, summary, body_font, max_w)[:4]:
        d.text((tx, ty), l, font=body_font, fill=(45, 55, 70, 255))
        ty += int(body_font.size * 1.25)

    # footer row
    fy = card[3] - int(pad * 1.1)
    d.text((tx, fy), slide.footer or "SpecAvtoPortal", font=footer_font, fill=(90, 100, 115, 255))
    tg = "t.me/specavtoportal"
    tw = int(d.textlength(tg, font=footer_font))
    d.text((card[2] - int(pad * 0.8) - tw, fy), tg, font=footer_font, fill=(90, 100, 115, 255))

    img.convert("RGB").save(out_png)


def _render_D(slide: Slide, out_png: Path):
    # Light newspaper style
    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT
    pad = 60 if W >= 1080 else 36
    r = 28 if W >= 1080 else 20
    img_h = int(H * 0.50)

    base = Image.new("RGB", (W, H), (245, 241, 235))
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # "paper" card
    paper = [pad, pad, W - pad, H - pad]
    _rounded(d, paper, r=r, fill=(255, 253, 250, 255), outline=(220, 214, 205, 255), width=2)

    # header line
    head_h = int(pad * 1.7)
    d.rectangle([paper[0], paper[1], paper[2], paper[1] + head_h], fill=(250, 248, 244, 255))
    d.line([(paper[0] + int(pad * 0.6), paper[1] + head_h), (paper[2] - int(pad * 0.6), paper[1] + head_h)], fill=(200, 190, 178, 255), width=2)

    _draw_topbar_common(img, d, W, paper[0] + int(pad * 0.6), head_h, "D", slide.header)

    # photo frame
    frame = [paper[0] + int(pad * 0.6), paper[1] + head_h + int(pad * 0.6), paper[2] - int(pad * 0.6), paper[1] + head_h + int(pad * 0.6) + img_h]
    _rounded(d, frame, r=int(r * 0.7), fill=(235, 232, 226, 255), outline=(210, 202, 192, 255), width=2)

    if slide.image_url:
        work = out_png.parent
        ext = _guess_ext_from_url(slide.image_url)
        raw = work / "images" / f"img_{out_png.stem}{ext}"
        saved = _download_image(slide.image_url, raw)
        if saved:
            png = work / "images" / f"img_{out_png.stem}.png"
            ok = _ensure_png(saved, png)
            if ok and ok.exists():
                im = Image.open(ok).convert("RGB")
                top = _cover_crop(im, frame[2] - frame[0], frame[3] - frame[1])
                img.alpha_composite(top.convert("RGBA"), (frame[0], frame[1]))

    # text area
    title_font = _font(54 if W >= 1080 else 36, True)
    body_font = _font(38 if W >= 1080 else 26, False)
    footer_font = _font(32 if W >= 1080 else 23, False)

    tx = paper[0] + int(pad * 0.8)
    ty = frame[3] + int(pad * 0.7)
    max_w = paper[2] - tx - int(pad * 0.8)

    title = (slide.lines[0] if slide.lines else "")
    summary = (slide.lines[1] if len(slide.lines) > 1 else "")

    for l in _wrap(d, title, title_font, max_w)[:3]:
        d.text((tx, ty), l, font=title_font, fill=(25, 25, 25, 255))
        ty += int(title_font.size * 1.18)

    ty += int(pad * 0.25)
    for l in _wrap(d, summary, body_font, max_w)[:4]:
        d.text((tx, ty), l, font=body_font, fill=(60, 60, 60, 255))
        ty += int(body_font.size * 1.25)

    # footer
    fy = paper[3] - int(pad * 1.1)
    d.text((tx, fy), slide.footer or "SpecAvtoPortal", font=footer_font, fill=(120, 110, 100, 255))
    tg = "t.me/specavtoportal"
    tw = int(d.textlength(tg, font=footer_font))
    d.text((paper[2] - int(pad * 0.8) - tw, fy), tg, font=footer_font, fill=(120, 110, 100, 255))

    img.convert("RGB").save(out_png)


def _render_E(slide: Slide, out_png: Path):
    # Dark industrial: graphite + orange accents
    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT
    pad = 60 if W >= 1080 else 36
    r = 26 if W >= 1080 else 18
    img_h = int(H * 0.52)

    base = Image.new("RGB", (W, H), (14, 18, 24))
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # metal frame card
    card = [pad, pad, W - pad, H - pad]
    _rounded(d, card, r=r, fill=(22, 26, 34, 255), outline=(70, 75, 84, 255), width=3)

    # bolts
    bolt_r = int(pad * 0.18)
    for (bx, by) in [(card[0] + int(pad * 0.4), card[1] + int(pad * 0.4)),
                     (card[2] - int(pad * 0.4), card[1] + int(pad * 0.4)),
                     (card[0] + int(pad * 0.4), card[3] - int(pad * 0.4)),
                     (card[2] - int(pad * 0.4), card[3] - int(pad * 0.4))]:
        d.ellipse([bx - bolt_r, by - bolt_r, bx + bolt_r, by + bolt_r], fill=(55, 60, 70, 255), outline=(120, 120, 130, 180), width=2)

    # top strip
    top_h = int(pad * 1.5)
    d.rectangle([card[0], card[1], card[2], card[1] + top_h], fill=(10, 10, 12, 160))
    _draw_topbar_common(img, d, W, card[0] + int(pad * 0.6), top_h, "E", slide.header)

    # orange divider
    d.rectangle([card[0], card[1] + top_h, card[2], card[1] + top_h + int(pad * 0.14)], fill=(255, 140, 0, 255))

    # photo window
    frame = [card[0] + int(pad * 0.6), card[1] + top_h + int(pad * 0.6), card[2] - int(pad * 0.6), card[1] + top_h + int(pad * 0.6) + img_h]
    _rounded(d, frame, r=int(r * 0.7), fill=(12, 12, 14, 255), outline=(255, 140, 0, 180), width=2)

    if slide.image_url:
        work = out_png.parent
        ext = _guess_ext_from_url(slide.image_url)
        raw = work / "images" / f"img_{out_png.stem}{ext}"
        saved = _download_image(slide.image_url, raw)
        if saved:
            png = work / "images" / f"img_{out_png.stem}.png"
            ok = _ensure_png(saved, png)
            if ok and ok.exists():
                im = Image.open(ok).convert("RGB")
                top = _cover_crop(im, frame[2] - frame[0], frame[3] - frame[1])
                img.alpha_composite(top.convert("RGBA"), (frame[0], frame[1]))

    # text area
    title_font = _font(54 if W >= 1080 else 36, True)
    body_font = _font(38 if W >= 1080 else 26, False)
    footer_font = _font(32 if W >= 1080 else 23, False)

    tx = card[0] + int(pad * 0.8)
    ty = frame[3] + int(pad * 0.8)
    max_w = card[2] - tx - int(pad * 0.8)

    title = (slide.lines[0] if slide.lines else "")
    summary = (slide.lines[1] if len(slide.lines) > 1 else "")

    for l in _wrap(d, title, title_font, max_w)[:3]:
        d.text((tx, ty), l, font=title_font, fill=(245, 245, 245, 255))
        ty += int(title_font.size * 1.18)

    ty += int(pad * 0.25)
    for l in _wrap(d, summary, body_font, max_w)[:4]:
        d.text((tx, ty), l, font=body_font, fill=(205, 210, 220, 255))
        ty += int(body_font.size * 1.25)

    # footer
    fy = card[3] - int(pad * 1.1)
    d.text((tx, fy), slide.footer or "SpecAvtoPortal", font=footer_font, fill=(255, 140, 0, 240))
    tg = "t.me/specavtoportal"
    tw = int(d.textlength(tg, font=footer_font))
    d.text((card[2] - int(pad * 0.8) - tw, fy), tg, font=footer_font, fill=(200, 200, 200, 220))

    img.convert("RGB").save(out_png)


def _render_slide(slide: Slide, out_png: Path):
    t = _choose_template(slide)
    if t == "A":
        return _render_A(slide, out_png)
    if t == "D":
        return _render_D(slide, out_png)
    return _render_E(slide, out_png)


# ----------------- Video assembly -----------------
def render_digest_video(slides: List[Slide], out_mp4: Path):
    _ffmpeg_exists()
    work = out_mp4.parent / "_work"
    work.mkdir(parents=True, exist_ok=True)

    segments: List[Path] = []
    for i, s in enumerate(slides, start=1):
        png = work / f"slide_{i:02d}.png"
        seg = work / f"seg_{i:02d}.mp4"

        _render_slide(s, png)

        subprocess.check_call([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(png),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(s.seconds),
            "-r", str(cfg.FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(seg),
        ])
        segments.append(seg)

    concat = work / "concat.txt"
    with open(concat, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"file '{seg.name}'\n")

    subprocess.check_call([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", "concat.txt",
        "-c", "copy",
        str(out_mp4.resolve()),
    ], cwd=str(work))

    return out_mp4
