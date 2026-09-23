from __future__ import annotations

import base64
import os
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

from .storyboard import Scene


BG = (18, 21, 25)
ORANGE = (255, 107, 0)


def _download_source(url: str, output: Path) -> bool:
    if not url:
        return False
    try:
        response = requests.get(url, timeout=25, headers={"User-Agent": "SpecAvtoPortal/2.0"})
        response.raise_for_status()
        output.write_bytes(response.content)
        with Image.open(output) as image:
            image.verify()
        return True
    except Exception as exc:
        print(f"[visual] source image failed: {exc}")
        output.unlink(missing_ok=True)
        return False


def _fallback_art(scene: Scene, output: Path, width: int = 1024, height: int = 1536) -> None:
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    for x in range(0, width, 96):
        draw.line((x, 0, x, height), fill=(36, 40, 46), width=1)
    for y in range(0, height, 96):
        draw.line((0, y, width, y), fill=(36, 40, 46), width=1)

    # Abstract trailer silhouette; text is added by the renderer, never by AI art.
    trailer_y = int(height * 0.48)
    draw.rounded_rectangle(
        (int(width * 0.14), trailer_y, int(width * 0.86), trailer_y + int(height * 0.16)),
        radius=26,
        fill=(42, 47, 54),
        outline=(87, 94, 104),
        width=4,
    )
    draw.rectangle(
        (int(width * 0.14), trailer_y + int(height * 0.16), int(width * 0.77), trailer_y + int(height * 0.17)),
        fill=ORANGE,
    )
    for cx in (0.31, 0.52, 0.73):
        x = int(width * cx)
        r = int(width * 0.045)
        draw.ellipse((x-r, trailer_y + int(height * 0.19)-r, x+r, trailer_y + int(height * 0.19)+r), fill=(12, 14, 17), outline=(126, 133, 143), width=5)

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        (int(width * 0.05), int(height * 0.02), int(width * 0.85), int(height * 0.52)),
        fill=(255, 107, 0, 55),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=90))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    image.save(output, "PNG", optimize=True)


def generate_scene_visual(scene: Scene, output: Path) -> str:
    """Generate scene art with OpenAI, then fall back to source imagery or branded procedural art."""
    output.parent.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    ai_images = os.getenv("AI_IMAGES", "1").strip() == "1"

    if api_key and ai_images:
        try:
            from openai import OpenAI

            model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst").strip()
            quality = os.getenv("OPENAI_IMAGE_QUALITY", "medium").strip()
            client = OpenAI(api_key=api_key)
            result = client.images.generate(
                model=model,
                prompt=scene.visual_prompt,
                size=os.getenv("OPENAI_IMAGE_SIZE", "1024x1792").strip(),
                quality=quality,
                output_format="png",
            )
            payload = result.data[0].b64_json
            if not payload:
                raise RuntimeError("image API returned no image data")
            output.write_bytes(base64.b64decode(payload))
            print(f"[visual] AI scene {scene.id}: {model}/{quality}")
            return "ai"
        except Exception as exc:
            print(f"[visual] AI image fallback for {scene.id}: {exc}")

    if scene.source_image_url:
        raw = output.with_suffix(".source")
        if _download_source(scene.source_image_url, raw):
            try:
                with Image.open(raw) as image:
                    image.convert("RGB").save(output, "PNG", optimize=True)
                raw.unlink(missing_ok=True)
                print(f"[visual] source scene {scene.id}")
                return "source"
            except Exception:
                raw.unlink(missing_ok=True)

    _fallback_art(scene, output)
    print(f"[visual] procedural scene {scene.id}")
    return "procedural"
