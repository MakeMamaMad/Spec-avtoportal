from __future__ import annotations

import math
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from ..ai.storyboard import Scene, Storyboard


WIDTH = 1080
HEIGHT = 1920
FPS = 30
ORANGE = (255, 107, 0)
WHITE = (246, 247, 249)
MUTED = (180, 187, 196)
DARK = (15, 18, 22)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed: {err[-5000:]}")


def media_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        return float((proc.stdout or b"0").decode().strip())
    except Exception:
        return 0.0


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    iw, ih = image.size
    scale = max(width / max(iw, 1), height / max(ih, 1))
    nw, nh = int(iw * scale), int(ih * scale)
    resized = image.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - width) // 2)
    top = max(0, (nh - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    words = str(text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    if current and len(lines) < max_lines:
        lines.append(current)

    consumed = " ".join(lines)
    original = " ".join(words)
    if lines and consumed != original:
        last = lines[-1].rstrip(" .,:;!-")
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = (last or lines[-1][:8]) + "…"
    return lines


def _gradient_overlay(width: int, height: int) -> Image.Image:
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        top = max(0.0, 1.0 - y / 620.0)
        bottom = max(0.0, (y - 980.0) / max(1.0, height - 980.0))
        alpha = int(min(235, 65 + top * 100 + bottom * 175))
        draw.line((0, y, width, y), fill=(7, 9, 12, alpha))
    return overlay


def render_scene_frame(
    scene: Scene,
    visual_path: Path,
    output: Path,
    *,
    index: int,
    total: int,
    format_name: str,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(visual_path) as source:
            base = _cover(source, WIDTH, HEIGHT)
    except Exception:
        base = Image.new("RGB", (WIDTH, HEIGHT), DARK)

    # Editorial cinematic treatment.
    base = base.filter(ImageFilter.GaussianBlur(radius=0.3))
    image = Image.alpha_composite(base.convert("RGBA"), _gradient_overlay(WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image, "RGBA")

    brand_font = _font(32, True)
    label_font = _font(25, True)
    title_font = _font(72 if len(scene.overlay) < 52 else 61, True)
    small_font = _font(26, False)

    # Top identity bar.
    draw.rounded_rectangle((54, 52, 118, 116), radius=14, fill=ORANGE + (255,))
    draw.text((71, 72), "САП", font=_font(18, True), fill=(255, 255, 255, 255))
    draw.text((140, 64), "СпецАвтоПортал", font=brand_font, fill=WHITE + (255,))
    counter = f"{index:02d}/{total:02d}"
    counter_w = draw.textbbox((0, 0), counter, font=label_font)[2]
    draw.text((WIDTH - 56 - counter_w, 72), counter, font=label_font, fill=MUTED + (255,))

    # Format / section marker.
    format_label = "BREAKING" if format_name.lower() in {"breaking", "news"} else "РАЗБОР"
    badge_w = draw.textbbox((0, 0), format_label, font=label_font)[2] + 44
    draw.rounded_rectangle((56, 132, 56 + badge_w, 182), radius=22, fill=(15, 18, 22, 200), outline=ORANGE + (220,), width=2)
    draw.text((78, 143), format_label, font=label_font, fill=ORANGE + (255,))

    # Headline block. Safe zone leaves room for native social UI at bottom.
    x = 64
    max_w = WIDTH - 128
    lines = _wrap(draw, scene.overlay.upper(), title_font, max_w, 4)
    y = 1110 - max(0, len(lines) - 2) * 72
    draw.rectangle((x, y - 26, x + 130, y - 17), fill=ORANGE + (255,))
    for line in lines:
        draw.text((x, y), line, font=title_font, fill=WHITE + (255,), stroke_width=2, stroke_fill=(0, 0, 0, 160))
        y += int(getattr(title_font, "size", 64) * 1.12)

    draw.text((64, 1735), "spec-avtoportal.ru", font=small_font, fill=MUTED + (255,))
    draw.text((64, 1780), "рынок · техника · регламенты", font=small_font, fill=(128, 136, 146, 255))

    image.convert("RGB").save(output, "PNG", optimize=True)
    return output


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _ass_escape(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _subtitle_chunks(text: str, words_per_chunk: int = 4) -> list[str]:
    words = re.findall(r"\S+", str(text or ""))
    return [" ".join(words[i:i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)] or [""]


def _color_highlights(text: str, highlights: list[str]) -> str:
    escaped = _ass_escape(text)
    for highlight in sorted([x for x in highlights if x], key=len, reverse=True):
        pattern = re.compile(re.escape(_ass_escape(highlight)), flags=re.IGNORECASE)
        escaped = pattern.sub(lambda m: r"{\c&H006BFF&}" + m.group(0) + r"{\c&HFFFFFF&}", escaped)
    return escaped


def build_ass(storyboard: Storyboard, durations: list[float], output: Path) -> Path:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,DejaVu Sans,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H99000000,-1,0,0,0,100,100,0,0,3,3,0,2,90,90,255,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events: list[str] = []
    scene_start = 0.0
    for scene, duration in zip(storyboard.scenes, durations):
        chunks = _subtitle_chunks(scene.narration, 4)
        per = duration / max(1, len(chunks))
        for idx, chunk in enumerate(chunks):
            start = scene_start + idx * per
            end = scene_start + min(duration, (idx + 1) * per + 0.05)
            text = _color_highlights(chunk, scene.highlight_words)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
            )
        scene_start += duration

    output.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output


def _scaled_durations(storyboard: Storyboard, audio_seconds: float) -> list[float]:
    base = [max(3.0, float(scene.seconds)) for scene in storyboard.scenes]
    planned = sum(base)
    target = max(planned, audio_seconds + 0.45)
    factor = target / max(planned, 1.0)
    return [x * factor for x in base]


def render_short(
    storyboard: Storyboard,
    visual_paths: list[Path],
    audio_path: Path,
    output: Path,
    work_dir: Path,
) -> dict[str, object]:
    if len(storyboard.scenes) != len(visual_paths):
        raise ValueError("scene/visual count mismatch")

    work_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = work_dir / "frames"
    segments_dir = work_dir / "segments"
    frames_dir.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)

    audio_seconds = media_duration(audio_path)
    durations = _scaled_durations(storyboard, audio_seconds)
    segments: list[Path] = []

    for index, (scene, visual, duration) in enumerate(zip(storyboard.scenes, visual_paths, durations), 1):
        frame = frames_dir / f"scene_{index:02d}.png"
        segment = segments_dir / f"scene_{index:02d}.mp4"
        render_scene_frame(
            scene,
            visual,
            frame,
            index=index,
            total=len(storyboard.scenes),
            format_name=storyboard.format,
        )
        fade_out = max(0.05, duration - 0.20)
        vf = (
            "zoompan="
            "z='min(max(zoom,pzoom)+0.00055,1.055)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"fade=t=in:st=0:d=0.18,fade=t=out:st={fade_out:.3f}:d=0.18,"
            "format=yuv420p"
        )
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(frame),
            "-t", f"{duration:.3f}",
            "-vf", vf,
            "-r", str(FPS),
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(segment),
        ])
        segments.append(segment)

    concat_file = work_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{segment.resolve()}'\n" for segment in segments),
        encoding="utf-8",
    )
    silent = work_dir / "silent.mp4"
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(silent),
    ])

    subtitles = build_ass(storyboard, durations, work_dir / "subtitles.ass")
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(silent),
        "-i", str(audio_path),
        "-vf", f"ass={subtitles.as_posix()}",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output),
    ])

    first_frame = frames_dir / "scene_01.png"
    return {
        "video": str(output),
        "thumbnail": str(first_frame),
        "audio_seconds": audio_seconds,
        "video_seconds": media_duration(output),
        "durations": durations,
    }
