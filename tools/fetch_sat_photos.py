"""Download SAT model photos from satpricep.by for the weekly partner shorts.

The partner allowed us to use their catalog photos. Runs in GitHub Actions
(the site isn't reachable from every network); saves JPEGs to
frontend/assets/partners/sat/ and writes promotion/config/sat_photos.json:
{"<catalog page url>": ["frontend/assets/partners/sat/<name>.jpg", ...]}.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "promotion" / "config" / "sat_shorts.json"
MANIFEST = ROOT / "promotion" / "config" / "sat_photos.json"
OUT_DIR = ROOT / "frontend" / "assets" / "partners" / "sat"
PER_PAGE = 5
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}

GALLERY_RE = re.compile(r"""["'(]([^"'()\s]*/upload/[^"'()\s]*?/940_640_\d/[^"'()\s]+\.(?:webp|jpe?g|png))""", re.I)


def page_images(html: str, base: str) -> list[str]:
    # Gallery photos only: the og:image of category/home pages is the SAT logo.
    return list(dict.fromkeys(urljoin(base, m) for m in GALLERY_RE.findall(html)))


def page_name(url: str) -> str:
    path = urlparse(url).path.strip("/").split("/")
    return re.sub(r"[^a-z0-9-]+", "-", (path[-1] if path and path[-1] else "home").lower())[:60]


def save_jpeg(data: bytes, path: Path) -> None:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        if image.width > 1400:
            image = image.resize((1400, round(image.height * 1400 / image.width)), Image.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "JPEG", quality=86, optimize=True)


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    pages = list(dict.fromkeys(e["url"] for e in config["episodes"] if e.get("url")))
    manifest: dict[str, list[str]] = {}
    session = requests.Session()
    for page in pages:
        try:
            response = session.get(page, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            print(f"[skip] {page}: {exc}")
            continue
        images = page_images(response.text, page)[:PER_PAGE]
        saved: list[str] = []
        for index, image_url in enumerate(images, 1):
            target = OUT_DIR / f"{page_name(page)}-{index}.jpg"
            try:
                data = session.get(image_url, headers={**HEADERS, "Referer": page}, timeout=30)
                data.raise_for_status()
                save_jpeg(data.content, target)
                saved.append(target.relative_to(ROOT).as_posix())
            except Exception as exc:
                print(f"[skip] {image_url}: {exc}")
        print(f"[ok] {page}: {len(saved)} photos")
        if saved:
            manifest[page] = saved
    if not manifest:
        print("No photos downloaded", file=sys.stderr)
        return 1
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
