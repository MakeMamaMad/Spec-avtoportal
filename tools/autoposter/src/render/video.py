import os
import subprocess
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..config import cfg
from ..content.digest import Slide


# ---------- styling ----------
ACCENT = (255, 140, 0)       # оранжевый (под “СпецАвто”)
ACCENT2 = (56, 189, 248)     # голубой (акцент)
BG_DARK = (12, 18, 28)       # тёмно-синий
PANEL = (20, 28, 44)         # панель снизу
WHITE = (255, 255, 255)
MUTED = (190, 200, 210)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(p):
        return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int):
    words = text.split()
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
        print(f"[img] download: {url}")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (SpecAvtoPortal Autoposter)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            status = getattr(resp, "status", "unknown")
            ctype = resp.headers.get("Content-Type", "")
        out_path.write_bytes(data)
        print(f"[img] ok: status={status} bytes={len(data)} content-type={ctype} -> {out_path.name}")
        return out_path
    except Exception as e:
        print(f"[img] FAILED: {url} err={e}")
        return None


def _ensure_png(src_path: Path, dst_png: Path) -> Optional[Path]:
    try:
        img = Image.open(src_path)
        img = img.convert("RGB")
        img.save(dst_png)
        print(f"[img] pillow convert ok -> {dst_png.name}")
        return dst_png
    except Exception as e:
        print(f"[img] pillow convert FAILED ({src_path.name}): {e}. Try ffmpeg...")
        try:
            subprocess.check_call([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src_path),
                str(dst_png),
            ])
            if dst_png.exists():
                print(f"[img] ffmpeg convert ok -> {dst_png.name}")
                return dst_png
        except Exception as e2:
            print(f"[img] ffmpeg convert FAILED ({src_path.name}): {e2}")
            return None
    return None


def _cover_crop(im: Image.Image, W: int, H: int) -> Image.Image:
    iw, ih = im.size
    if iw == 0 or ih == 0:
        return Image.new("RGB", (W, H), BG_DARK)

    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    im2 = im.resize((nw, nh), Image.LANCZOS)

    left = (nw - W) // 2
    top = (nh - H) // 2
    return im2.crop((left, top, left + W, top + H))


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int, fill):
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill)
    except Exception:
        draw.rectangle(box, fill=fill)


def _load_logo() -> Optional[Image.Image]:
    # ожидаем, что лого лежит здесь: tools/autoposter/assets/logo.png
    logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    if logo_path.exists():
        try:
            return Image.open(logo_path).convert("RGBA")
        except Exception:
            return None
    return None


def _parse_news_number(header: str) -> Optional[str]:
    # "Новость 2" -> "2"
    digits = "".join([c for c in header if c.isdigit()])
    return digits or None


def _is_news_slide(slide: Slide) -> bool:
    h = (slide.header or "").lower()
    return "новость" in h


def _is_cta_slide(slide: Slide) -> bool:
    return (slide.header or "").strip().lower() in ["где читать", "где читать?"]


def _render_slide_png(slide: Slide, out_png: Path):
    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT

    # размеры шрифтов под 720x1280 и 1080x1920
    if W >= 1080:
        top_font = _font(44, True)
        num_font = _font(54, True)
        title_font = _font(56, True)
        body_font = _font(40, False)
        footer_font = _font(34, False)
        pad = 60
        radius = 34
    else:
        top_font = _font(30, True)
        num_font = _font(38, True)
        title_font = _font(40, True)
        body_font = _font(30, False)
        footer_font = _font(26, False)
        pad = 36
        radius = 26

    # layout: верхняя картинка ~55%, низ — панель с текстом
    img_h = int(H * 0.55)
    panel_y = img_h

    # фон по умолчанию
    base = Image.new("RGB", (W, H), BG_DARK)

    # ---------- верхняя картинка ----------
    image_url = getattr(slide, "image_url", None)
    if image_url:
        work_dir = out_png.parent
        ext = _guess_ext_from_url(image_url)
        raw_path = work_dir / "images" / f"img_{out_png.stem}{ext}"
        saved = _download_image(image_url, raw_path)
        if saved:
            png_path = work_dir / "images" / f"img_{out_png.stem}.png"
            ok_png = _ensure_png(saved, png_path)
            if ok_png:
                try:
                    im = Image.open(ok_png).convert("RGB")
                    top_img = _cover_crop(im, W, img_h)
                    base.paste(top_img, (0, 0))
                except Exception as e:
                    print(f"[img] open/apply FAILED ({ok_png.name}): {e}")

    # если картинки нет — делаем мягкий градиент
    if not image_url:
        grad = Image.new("RGB", (W, img_h), BG_DARK)
        g = ImageDraw.Draw(grad)
        for y in range(img_h):
            t = y / max(1, img_h - 1)
            col = (
                int(BG_DARK[0] * (1 - t) + ACCENT2[0] * t * 0.25),
                int(BG_DARK[1] * (1 - t) + ACCENT2[1] * t * 0.25),
                int(BG_DARK[2] * (1 - t) + ACCENT2[2] * t * 0.25),
            )
            g.line([(0, y), (W, y)], fill=col)
        base.paste(grad, (0, 0))

    # слегка блюрим верх, чтобы не спорил с текстом/лого
    top_region = base.crop((0, 0, W, img_h)).filter(ImageFilter.GaussianBlur(radius=2))
    base.paste(top_region, (0, 0))

    img = base.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # ---------- нижняя панель ----------
    d.rectangle([0, panel_y, W, H], fill=(PANEL[0], PANEL[1], PANEL[2], 255))

    # декоративная линия-акцент
    d.rectangle([0, panel_y, W, panel_y + int(pad * 0.18)], fill=(ACCENT[0], ACCENT[1], ACCENT[2], 255))

    # ---------- топ-бар на картинке ----------
    topbar_h = int(pad * 1.6)
    d.rectangle([0, 0, W, topbar_h], fill=(0, 0, 0, 120))

    # logo
    logo = _load_logo()
    logo_w = int(topbar_h * 0.78)
    x = pad
    if logo:
        try:
            lw, lh = logo.size
            scale = logo_w / max(1, lw)
            logo2 = logo.resize((logo_w, int(lh * scale)), Image.LANCZOS)
            img.alpha_composite(logo2, (x, int((topbar_h - logo2.size[1]) / 2)))
            x += logo_w + int(pad * 0.35)
        except Exception:
            pass

    # надпись "Новости" + номер
    if _is_news_slide(slide):
        num = _parse_news_number(slide.header) or ""
        d.text((x, int(topbar_h * 0.22)), "Новости", font=top_font, fill=WHITE)
        if num:
            nx = x + int(d.textlength("Новости", font=top_font)) + int(pad * 0.35)
            # маленький цветной бейдж под номер
            badge_w = int(d.textlength(num, font=num_font)) + int(pad * 0.7)
            badge_h = int(topbar_h * 0.8)
            badge_y = int((topbar_h - badge_h) / 2)
            _rounded_rect(d, [nx - int(pad * 0.25), badge_y, nx - int(pad * 0.25) + badge_w, badge_y + badge_h], radius=int(radius * 0.75), fill=(ACCENT[0], ACCENT[1], ACCENT[2], 230))
            d.text((nx + int(pad * 0.05), int(topbar_h * 0.15)), num, font=num_font, fill=(10, 10, 10))
    else:
        # для титула/CTA просто заголовок
        d.text((x, int(topbar_h * 0.22)), slide.header, font=top_font, fill=WHITE)

    # ---------- текст в нижней панели ----------
    panel_pad = pad
    text_x = panel_pad
    text_y = panel_y + int(panel_pad * 0.6)
    max_w = W - panel_pad * 2

    # основной текст (slide.lines)
    for line in slide.lines:
        for l in _wrap(d, line, title_font if _is_news_slide(slide) else body_font, max_w):
            d.text((text_x, text_y), l, font=title_font if _is_news_slide(slide) else body_font, fill=WHITE)
            text_y += int((title_font.size if _is_news_slide(slide) else body_font.size) * 1.25)
        text_y += int(pad * 0.2)

    # footer
    d.text((text_x, H - int(pad * 1.5)), slide.footer, font=footer_font, fill=MUTED)

    # tg справа снизу
    tg = "t.me/specavtoportal"
    tw = int(d.textlength(tg, font=footer_font))
    d.text((W - pad - tw, H - int(pad * 1.5)), tg, font=footer_font, fill=MUTED)

    img.convert("RGB").save(out_png)


def render_digest_video(slides: List[Slide], out_mp4: Path):
    _ffmpeg_exists()
    work = out_mp4.parent / "_work"
    work.mkdir(parents=True, exist_ok=True)

    segments: List[Path] = []
    for i, s in enumerate(slides, start=1):
        png = work / f"slide_{i:02d}.png"
        seg = work / f"seg_{i:02d}.mp4"
        _render_slide_png(s, png)
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
