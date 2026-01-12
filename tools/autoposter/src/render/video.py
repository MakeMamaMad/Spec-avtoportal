import os
import subprocess
import urllib.request
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from ..config import cfg
from ..content.digest import Slide


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


def _download_image(url: str, out_path: Path, timeout: int = 20) -> Optional[Path]:
    """
    Download image by URL. Returns saved path or None if failed.
    """
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (SpecAvtoPortal Autoposter)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        out_path.write_bytes(data)
        return out_path
    except Exception:
        return None


def _ensure_png(src_path: Path, dst_png: Path) -> Optional[Path]:
    """
    Convert src image to PNG (for Pillow stability). Uses Pillow first, falls back to ffmpeg.
    """
    try:
        img = Image.open(src_path)
        img = img.convert("RGB")
        img.save(dst_png)
        return dst_png
    except Exception:
        # fallback via ffmpeg (handles webp reliably)
        try:
            subprocess.check_call([
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src_path),
                str(dst_png),
            ])
            if dst_png.exists():
                return dst_png
        except Exception:
            return None
    return None


def _cover_crop(im: Image.Image, W: int, H: int) -> Image.Image:
    """
    Resize image to cover W x H and crop center.
    """
    iw, ih = im.size
    if iw == 0 or ih == 0:
        return Image.new("RGB", (W, H), (12, 12, 14))

    scale = max(W / iw, H / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    im2 = im.resize((nw, nh), Image.LANCZOS)

    left = (nw - W) // 2
    top = (nh - H) // 2
    return im2.crop((left, top, left + W, top + H))


def _render_slide_png(slide: Slide, out_png: Path):
    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT

    white = (255, 255, 255)
    muted = (210, 210, 210)

    if W >= 1080:
        title_font = _font(72, True)
        body_font = _font(54, False)
        footer_font = _font(38, False)
        top_h = 170
        bot_h = 150
        pad = 60
        line_h = 76
    else:
        title_font = _font(52, True)
        body_font = _font(38, False)
        footer_font = _font(28, False)
        top_h = 110
        bot_h = 110
        pad = 36
        line_h = 52

    # --- background: either image or plain ---
    bg = Image.new("RGB", (W, H), (12, 12, 14))

    image_url = getattr(slide, "image_url", None)
    if image_url:
        work_dir = out_png.parent  # out/_work
        raw_path = work_dir / "images" / (f"img_{out_png.stem}.bin")
        saved = _download_image(image_url, raw_path)
        if saved:
            png_path = work_dir / "images" / (f"img_{out_png.stem}.png")
            ok_png = _ensure_png(saved, png_path)
            if ok_png:
                try:
                    im = Image.open(ok_png).convert("RGB")
                    bg = _cover_crop(im, W, H)
                except Exception:
                    pass

    # switch to RGBA for overlays
    img = bg.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")

    # overlays (semi-transparent)
    d.rectangle([0, 0, W, top_h], fill=(0, 0, 0, 170))
    d.rectangle([0, H - bot_h, W, H], fill=(0, 0, 0, 170))

    # header
    d.text((pad, int(top_h * 0.25)), slide.header, font=title_font, fill=white)

    # body
    y = int(H * 0.18)
    for line in slide.lines:
        for l in _wrap(d, line, body_font, W - pad * 2):
            d.text((pad, y), l, font=body_font, fill=(245, 245, 245, 255))
            y += line_h
        y += int(line_h * 0.35)

    # footer
    d.text((pad, H - int(bot_h * 0.7)), slide.footer, font=footer_font, fill=muted)
    d.text((W - int(pad * 8.5), H - int(bot_h * 0.7)), "t.me/specavtoportal", font=footer_font, fill=muted)

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

    # concat list (IMPORTANT: write only filenames; run ffmpeg in work dir)
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
