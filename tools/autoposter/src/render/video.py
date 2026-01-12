import os
import subprocess
from pathlib import Path
from typing import List

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

def _render_slide_png(slide: Slide, out_png: Path):
    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT
    bg = (12, 12, 14); top = (20, 20, 24); bot = (20, 20, 24)
    white = (255, 255, 255); muted = (200, 200, 200)

    if W >= 1080:
        title_font = _font(72, True)
        body_font = _font(54, False)
        footer_font = _font(38, False)
        top_h = 170; bot_h = 150; pad = 60
        line_h = 76
    else:
        title_font = _font(52, True)
        body_font = _font(38, False)
        footer_font = _font(28, False)
        top_h = 110; bot_h = 110; pad = 36
        line_h = 52

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, top_h], fill=top)
    d.rectangle([0, H - bot_h, W, H], fill=bot)

    d.text((pad, int(top_h*0.25)), slide.header, font=title_font, fill=white)

    y = int(H*0.18)
    for line in slide.lines:
        for l in _wrap(d, line, body_font, W - pad*2):
            d.text((pad, y), l, font=body_font, fill=(240, 240, 240))
            y += line_h
        y += int(line_h*0.35)

    d.text((pad, H - int(bot_h*0.7)), slide.footer, font=footer_font, fill=muted)
    d.text((W - int(pad*8.5), H - int(bot_h*0.7)), "t.me/specavtoportal", font=footer_font, fill=muted)

    img.save(out_png)

def _ffmpeg_exists():
    subprocess.check_call(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def render_digest_video(slides: List[Slide], out_mp4: Path):
    _ffmpeg_exists()
    work = out_mp4.parent / "_work"
    work.mkdir(parents=True, exist_ok=True)

    segments = []
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
           f.write(f"file '{seg_path.name}'\n")

    subprocess.check_call([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat),
        "-c", "copy",
        str(out_mp4),
    ])
    return out_mp4
